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

    with httpx.Client(timeout=timeout, trust_env=False) as client:
        response = client.post(base_url.rstrip("/"), headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()

    if is_aliyun_endpoint(base_url):
        results = (body.get("output") or {}).get("results") or []
    else:
        results = body.get("results") or []

    out: list[dict[str, Any]] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("index"))
            score = float(row.get("relevance_score", row.get("score", 0.0)))
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
