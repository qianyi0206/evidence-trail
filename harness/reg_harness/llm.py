from __future__ import annotations

import json
import re
import sys
from typing import Any, Callable, TextIO

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - allow pure unit tests without httpx
    httpx = None  # type: ignore[assignment]

from reg_harness.config import Settings

TokenHook = Callable[[str], None]


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError(f"LLM did not return JSON object: {text[:200]}")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("LLM JSON root is not an object")
    return value


def _delta_text(delta: dict[str, Any]) -> str:
    """Extract visible text from an OpenAI-style stream delta."""
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("content"), str):
                    parts.append(block["content"])
        return "".join(parts)
    # Some gateways put partial text under reasoning_content; skip for JSON actions.
    return ""


class ChatClient:
    """OpenAI-compatible chat client.

    When ``on_token`` is set (or passed to ``complete_json``), requests use
    ``stream=true`` and tokens are emitted for live terminal display. Full text
    is still assembled and parsed as JSON for the agent loop.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        # Instance-level hook used by interactive CLI (live mode).
        self.on_token: TokenHook | None = None
        self.stream_enabled: bool = True

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        on_token: TokenHook | None = None,
        stream: bool | None = None,
    ) -> dict[str, Any]:
        hook = on_token if on_token is not None else self.on_token
        use_stream = bool(hook) and (stream if stream is not None else self.stream_enabled)
        if use_stream:
            try:
                return self._complete_json_stream(system, user, on_token=hook)
            except Exception:
                # Provider may reject stream; fall back once without hook noise.
                return self._complete_json_blocking(system, user)
        return self._complete_json_blocking(system, user)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
        return headers

    def _base_payload(self, system: str, user: str) -> dict[str, Any]:
        if not self.settings.llm_host:
            raise RuntimeError("LLM_BINDING_HOST is not configured in .env")
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "temperature": self.settings.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.settings.llm_extra_body:
            reserved = {"messages", "model", "temperature", "stream"}
            for key, value in self.settings.llm_extra_body.items():
                if key not in reserved:
                    payload[key] = value
        return payload

    def _complete_json_blocking(self, system: str, user: str) -> dict[str, Any]:
        if httpx is None:
            raise RuntimeError("httpx is required for live LLM calls")
        payload = self._base_payload(system, user)
        with httpx.Client(
            timeout=self.settings.request_timeout, trust_env=False
        ) as client:
            response = client.post(
                self.settings.chat_completions_url,
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
        return _extract_json_object(content)

    def _complete_json_stream(
        self,
        system: str,
        user: str,
        *,
        on_token: TokenHook | None,
    ) -> dict[str, Any]:
        if httpx is None:
            raise RuntimeError("httpx is required for live LLM calls")
        payload = self._base_payload(system, user)
        payload["stream"] = True
        # Longer read timeout: streams can idle between tokens.
        timeout = httpx.Timeout(
            connect=30.0,
            read=float(self.settings.request_timeout),
            write=30.0,
            pool=30.0,
        )
        pieces: list[str] = []
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            with client.stream(
                "POST",
                self.settings.chat_completions_url,
                headers=self._headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="replace")
                    line = line.strip()
                    if not line.startswith("data:"):
                        # Some proxies send bare JSON lines
                        if line.startswith("{") and "choices" in line:
                            try:
                                chunk = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                        else:
                            continue
                    else:
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            if data == "[DONE]":
                                break
                            continue
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice0 = choices[0] or {}
                    delta = choice0.get("delta") or {}
                    # Non-stream-shaped fallback mid-stream
                    if not delta and isinstance(choice0.get("message"), dict):
                        msg_c = choice0["message"].get("content")
                        if isinstance(msg_c, str) and msg_c:
                            pieces.append(msg_c)
                            if on_token:
                                on_token(msg_c)
                        continue
                    text = _delta_text(delta)
                    if text:
                        pieces.append(text)
                        if on_token:
                            on_token(text)
        content = "".join(pieces)
        if not content.strip():
            # Empty stream → try non-stream once
            return self._complete_json_blocking(system, user)
        return _extract_json_object(content)


def default_token_printer(file: TextIO = sys.stderr) -> TokenHook:
    def _print(tok: str) -> None:
        print(tok, end="", file=file, flush=True)

    return _print
