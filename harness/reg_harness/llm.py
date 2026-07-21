from __future__ import annotations

import json
import re
from typing import Any

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - allow pure unit tests without httpx
    httpx = None  # type: ignore[assignment]

from reg_harness.config import Settings


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


class ChatClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        if httpx is None:
            raise RuntimeError("httpx is required for live LLM calls")
        if not self.settings.llm_host:
            raise RuntimeError("LLM_BINDING_HOST is not configured in .env")
        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "temperature": self.settings.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        # Align with indexing: disable thinking when configured.
        # Merge carefully — never overwrite messages/model.
        if self.settings.llm_extra_body:
            reserved = {"messages", "model", "temperature"}
            for key, value in self.settings.llm_extra_body.items():
                if key not in reserved:
                    payload[key] = value

        # trust_env=False avoids broken system proxies for direct LLM endpoints.
        with httpx.Client(
            timeout=self.settings.request_timeout, trust_env=False
        ) as client:
            response = client.post(
                self.settings.chat_completions_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        return _extract_json_object(content)
