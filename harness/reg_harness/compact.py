"""Evidence bag ranking / truncation.

Primary path: bag-side rerank model (same DashScope/qwen3-rerank stack as LightRAG).
Fallback: light kind + question-token overlap (no domain chapter dictionaries).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Sequence

from reg_harness.structure import focus_terms_from_question
from reg_harness.types import EvidenceItem

logger = logging.getLogger(__name__)


def _focus_terms(question: str) -> list[str]:
    return focus_terms_from_question(question)


def heuristic_score(item: EvidenceItem, question: str) -> float:
    """Minimal fallback ranker — no fixed clause/chapter table."""
    text = item.text or ""
    score = 0.0
    if item.kind in {"chunk", "catalog"}:
        score += 5.0
    elif item.kind == "relationship":
        score += 2.0
    elif item.kind == "entity":
        score += 1.0
    for term in _focus_terms(question):
        if term and term in text:
            score += 1.5
    if re.search(r"source_clause\s*=", text) or "来源条款" in text:
        score += 1.0
    if "<tr>" in text or re.search(r"表\s*[A-Za-z]?\d+", text):
        score += 1.0
    return score


# Back-compat alias for older imports/tests
def score_item(item: EvidenceItem, question: str) -> float:
    return heuristic_score(item, question)


def _dedupe(items: Sequence[EvidenceItem]) -> list[EvidenceItem]:
    kept: list[EvidenceItem] = []
    seen: set[str] = set()
    for item in items:
        key = (item.text or "")[:300]
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(item)
    return kept


def _settings_bag_rerank_ready(settings: Any | None) -> bool:
    if settings is None:
        return False
    if not bool(getattr(settings, "bag_rerank_enabled", False)):
        return False
    model = (getattr(settings, "rerank_model", None) or "").strip()
    host = (getattr(settings, "rerank_host", None) or "").strip()
    key = (getattr(settings, "rerank_api_key", None) or "").strip()
    return bool(model and host and key)


def _rank_with_rerank(
    items: list[EvidenceItem],
    query: str,
    settings: Any,
    *,
    max_items: int,
) -> list[EvidenceItem] | None:
    from reg_harness.rerank import rerank_documents, truncate_for_rerank

    docs = [truncate_for_rerank(item.text or "") for item in items]
    # Skip empty docs but keep indices aligned via filter
    valid_pairs = [(i, doc) for i, doc in enumerate(docs) if doc.strip()]
    if not valid_pairs:
        return []
    indices = [i for i, _ in valid_pairs]
    documents = [doc for _, doc in valid_pairs]
    try:
        timeout = float(getattr(settings, "request_timeout", 60) or 60)
        results = rerank_documents(
            query,
            documents,
            model=str(settings.rerank_model),
            base_url=str(settings.rerank_host),
            api_key=str(settings.rerank_api_key),
            top_n=min(max_items, len(documents)),
            timeout=min(timeout, 90.0),
        )
    except Exception as error:  # noqa: BLE001
        logger.warning("bag rerank failed, fallback to heuristic: %s", error)
        return None

    if not results:
        return None

    min_score = float(getattr(settings, "min_rerank_score", 0.0) or 0.0)
    ordered: list[EvidenceItem] = []
    used: set[int] = set()
    for row in results:
        local_idx = int(row["index"])
        if local_idx < 0 or local_idx >= len(indices):
            continue
        orig = indices[local_idx]
        if orig in used:
            continue
        score = float(row.get("relevance_score") or 0.0)
        if score < min_score:
            continue
        item = items[orig]
        item.score = score
        ordered.append(item)
        used.add(orig)
        if len(ordered) >= max_items:
            break

    # Append any missing (below min_score or absent from API) by original order
    if len(ordered) < max_items:
        for i, item in enumerate(items):
            if i in used:
                continue
            if item.score is None:
                item.score = heuristic_score(item, query)
            ordered.append(item)
            used.add(i)
            if len(ordered) >= max_items:
                break
    return ordered[:max_items]


def _rank_heuristic(
    items: list[EvidenceItem],
    question: str,
    *,
    max_items: int,
) -> list[EvidenceItem]:
    ranked = sorted(items, key=lambda item: -heuristic_score(item, question))
    out: list[EvidenceItem] = []
    for item in ranked:
        item.score = heuristic_score(item, question)
        out.append(item)
        if len(out) >= max_items:
            break
    return out


def apply_text_primary_quota(
    items: list[EvidenceItem],
    *,
    max_items: int,
    max_entities: int = 5,
    max_relations: int = 5,
) -> list[EvidenceItem]:
    """Reserve most bag seats for source text; soft-cap graph abstracts.

    Final order: precise catalog text → chunks → relations → entities → other.
    """
    if not items:
        return []
    limit = max(1, max_items)
    max_entities = max(0, max_entities)
    max_relations = max(0, max_relations)

    def _score_key(item: EvidenceItem) -> float:
        return float(item.score) if item.score is not None else 0.0

    catalogs = sorted(
        [i for i in items if i.kind == "catalog"],
        key=_score_key,
        reverse=True,
    )
    chunks = sorted(
        [i for i in items if i.kind == "chunk"],
        key=_score_key,
        reverse=True,
    )
    relations = sorted(
        [i for i in items if i.kind == "relationship"],
        key=_score_key,
        reverse=True,
    )
    entities = sorted(
        [i for i in items if i.kind == "entity"],
        key=_score_key,
        reverse=True,
    )
    others = [
        i
        for i in items
        if i.kind not in {"catalog", "chunk", "relationship", "entity"}
    ]

    # At least half the bag for authoritative source text when any exists.
    text_items = catalogs + chunks
    if text_items:
        graph_budget = min(max_entities + max_relations, limit // 2)
        take_rel = min(len(relations), max_relations, graph_budget)
        take_ent = min(len(entities), max_entities, max(0, graph_budget - take_rel))
        text_budget = limit - take_rel - take_ent
    else:
        take_rel = min(len(relations), max_relations, limit)
        take_ent = min(len(entities), max_entities, max(0, limit - take_rel))
        text_budget = 0

    out: list[EvidenceItem] = []
    out.extend(text_items[:text_budget])
    out.extend(relations[:take_rel])
    out.extend(entities[:take_ent])
    for item in others:
        if len(out) >= limit:
            break
        out.append(item)
    # Fill remaining seats with more source text first, not more abstracts.
    if len(out) < limit:
        for item in text_items[text_budget:]:
            if len(out) >= limit:
                break
            out.append(item)
    if len(out) < limit:
        for item in relations[take_rel:] + entities[take_ent:]:
            if len(out) >= limit:
                break
            # hard caps even when filling short bags with no chunks
            n_rel = sum(1 for x in out if x.kind == "relationship")
            n_ent = sum(1 for x in out if x.kind == "entity")
            if item.kind == "relationship" and n_rel >= max_relations:
                continue
            if item.kind == "entity" and n_ent >= max_entities:
                continue
            out.append(item)
    return out[:limit]


def compact_evidence(
    items: list[EvidenceItem],
    question: str,
    *,
    max_items: int = 16,
    settings: Any | None = None,
    query: str | None = None,
) -> list[EvidenceItem]:
    """Keep highest-signal evidence for the bag.

    1) dedupe
    2) score (bag rerank if configured, else heuristic)
    3) text-primary kind quota (chunks dominate seats)
    """
    deduped = _dedupe(items)
    if not deduped:
        return []
    rank_query = (query or question or "").strip() or (question or "")
    limit = max(1, max_items)

    # Score a wide candidate pool, then apply quota (not the reverse).
    pool_limit = max(limit * 3, limit)
    if _settings_bag_rerank_ready(settings) and rank_query:
        ranked = _rank_with_rerank(deduped, rank_query, settings, max_items=pool_limit)
        if ranked is None:
            ranked = _rank_heuristic(deduped, rank_query or question, max_items=pool_limit)
    else:
        ranked = _rank_heuristic(deduped, rank_query or question, max_items=pool_limit)

    max_ent = int(getattr(settings, "bag_max_entities", 5) or 5) if settings else 5
    max_rel = int(getattr(settings, "bag_max_relations", 5) or 5) if settings else 5
    return apply_text_primary_quota(
        ranked,
        max_items=limit,
        max_entities=max_ent,
        max_relations=max_rel,
    )


def observation_from_items(
    items: list[EvidenceItem],
    *,
    mode: str,
    added: int,
    bag_size: int,
) -> str:
    lines = [f"mode={mode} added={added} bag_size={bag_size}"]
    for index, item in enumerate(items[:6], 1):
        preview = (item.text or "").replace("\n", " ")[:140]
        score = f"{item.score:.3f}" if item.score is not None else "-"
        lines.append(f"{index}. [{item.kind}|score={score}] {preview}")
    return "\n".join(lines)
