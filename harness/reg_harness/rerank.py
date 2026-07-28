"""Bag-side rerank client (DashScope / standard text-rerank APIs).

Retrieval-side rerank stays inside LightRAG (`enable_rerank` on /query/data).
This module only re-orders the harness evidence bag after merge/backfill.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def shared_rerank_client(owner: Any, *, timeout: float):
    if httpx is None:
        raise RuntimeError("httpx is required for bag rerank")
    client = getattr(owner, "_rerank_http_client", None)
    if client is None:
        client = httpx.Client(timeout=timeout, trust_env=False)
        setattr(owner, "_rerank_http_client", client)
    return client


def close_shared_rerank_client(owner: Any) -> None:
    client = getattr(owner, "_rerank_http_client", None)
    if client is not None:
        client.close()
        delattr(owner, "_rerank_http_client")


def is_aliyun_endpoint(base_url: str) -> bool:
    host = (base_url or "").lower()
    return "dashscope" in host or "text-rerank" in host


def rerank_documents(
    query: str,
    documents: Sequence[str],
    *,
    model: str,
    base_url: str,
    api_key: str,
    top_n: int | None = None,
    timeout: float = 60.0,
    client: Any = None,
) -> list[dict[str, Any]]:
    """Return [{"index": int, "relevance_score": float}, ...] sorted by score desc.

    Raises on transport/HTTP errors so callers can fall back to heuristic ranking.
    """
    if httpx is None:
        raise RuntimeError("httpx is required for bag rerank")
    docs = [str(d or "") for d in documents]
    if not query.strip() or not docs:
        return []
    if not api_key or not base_url or not model:
        raise RuntimeError("rerank model/host/api_key incomplete")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    n = top_n if top_n is not None else len(docs)
    n = max(1, min(n, len(docs)))

    if is_aliyun_endpoint(base_url):
        payload: dict[str, Any] = {
            "model": model,
            "input": {"query": query, "documents": docs},
            "parameters": {"top_n": n, "return_documents": False},
        }
    else:
        payload = {
            "model": model,
            "query": query,
            "documents": docs,
            "top_n": n,
        }

    owns_client = client is None
    active_client = client or httpx.Client(timeout=timeout, trust_env=False)
    try:
        response = active_client.post(
            base_url.rstrip("/"),
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
    finally:
        if owns_client:
            active_client.close()

    if is_aliyun_endpoint(base_url):
        results = (body.get("output") or {}).get("results") or []
    else:
        results = body.get("results") or []

    out: list[dict[str, Any]] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        try:
            raw_index = row.get("index")
            raw_score = row.get("relevance_score", row.get("score", 0.0))
            if raw_index is None or raw_score is None:
                continue
            index = int(raw_index)
            score = float(raw_score)
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(docs):
            out.append({"index": index, "relevance_score": score})
    out.sort(key=lambda item: item["relevance_score"], reverse=True)
    return out


def truncate_for_rerank(text: str, max_chars: int = 1600) -> str:
    raw = (text or "").strip()
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars] + "…"
