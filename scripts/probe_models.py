from __future__ import annotations

import sys

import httpx

from common import is_placeholder, load_env, require_env


REQUIRED = [
    "LLM_BINDING_HOST",
    "LLM_BINDING_API_KEY",
    "LLM_MODEL",
    "EMBEDDING_BINDING_HOST",
    "EMBEDDING_BINDING_API_KEY",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "EMBEDDING_TOKEN_LIMIT",
]


def openai_headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def main() -> None:
    env = load_env()
    require_env(env, REQUIRED)
    placeholders = [name for name in REQUIRED if is_placeholder(env[name])]
    if placeholders:
        raise RuntimeError(
            "Model credentials are not configured. Replace placeholders for: "
            + ", ".join(placeholders)
        )

    dimension = int(env["EMBEDDING_DIM"])
    token_limit = int(env["EMBEDDING_TOKEN_LIMIT"])
    if dimension <= 0 or token_limit <= 0:
        raise RuntimeError("EMBEDDING_DIM and EMBEDDING_TOKEN_LIMIT must be positive integers")

    llm_url = env["LLM_BINDING_HOST"].rstrip("/") + "/chat/completions"
    try:
        response = httpx.post(
            llm_url,
            headers=openai_headers(env["LLM_BINDING_API_KEY"]),
            json={
                "model": env["LLM_MODEL"],
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 2,
                "stream": False,
            },
            timeout=60,
        )
        response.raise_for_status()
        if not response.json().get("choices"):
            raise RuntimeError("chat response does not contain choices")
    except Exception as exc:
        raise RuntimeError(f"Chat endpoint probe failed for model {env['LLM_MODEL']}: {exc}") from exc
    print(f"chat       OK ({env['LLM_MODEL']})")

    embedding_url = env["EMBEDDING_BINDING_HOST"].rstrip("/") + "/embeddings"
    try:
        embedding_payload: dict[str, object] = {
            "model": env["EMBEDDING_MODEL"],
            "input": ["passenger vehicle AEB test"],
            "encoding_format": "float",
        }
        if env.get("EMBEDDING_SEND_DIM", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            embedding_payload["dimensions"] = dimension

        response = httpx.post(
            embedding_url,
            headers=openai_headers(env["EMBEDDING_BINDING_API_KEY"]),
            json=embedding_payload,
            timeout=60,
        )
        response.raise_for_status()
        embedding = response.json()["data"][0]["embedding"]
    except Exception as exc:
        raise RuntimeError(
            f"Embedding endpoint probe failed for model {env['EMBEDDING_MODEL']}: {exc}"
        ) from exc

    actual_dimension = len(embedding)
    if actual_dimension != dimension:
        raise RuntimeError(
            f"Embedding dimension mismatch: .env={dimension}, endpoint={actual_dimension}. "
            "Correct EMBEDDING_DIM before indexing."
        )
    print(f"embedding  OK ({env['EMBEDDING_MODEL']}, dimension={actual_dimension})")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"doctor     FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
