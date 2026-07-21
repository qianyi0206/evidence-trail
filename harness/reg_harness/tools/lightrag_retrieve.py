from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

from reg_harness.compact import compact_evidence, observation_from_items
from reg_harness.config import Settings
from reg_harness.knowledge.evidence_catalog import EvidenceCatalog, merge_evidence_ids
from reg_harness.slots import refresh_slots
from reg_harness.types import AgentState, EvidenceItem, ToolResult
from reg_harness.tools.base import Tool


def _headers(settings: Settings) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.api_key_header:
        headers["X-API-Key"] = settings.api_key_header
        headers["Authorization"] = f"Bearer {settings.api_key_header}"
    return headers


def _items_from_payload(payload: dict[str, Any]) -> list[EvidenceItem]:
    data = payload.get("data") or {}
    items: list[EvidenceItem] = []
    for rel in data.get("relationships") or []:
        text = (
            f"{rel.get('src_id', '')} --{rel.get('keywords', '')}--> {rel.get('tgt_id', '')}\n"
            f"{rel.get('description', '')}"
        ).strip()
        items.append(
            EvidenceItem(
                kind="relationship",
                text=text,
                file_path=str(rel.get("file_path") or ""),
                raw=rel,
            )
        )
    for ent in data.get("entities") or []:
        text = (
            f"{ent.get('entity_name', '')} [{ent.get('entity_type', '')}]\n"
            f"{ent.get('description', '')}"
        ).strip()
        items.append(
            EvidenceItem(
                kind="entity",
                text=text,
                file_path=str(ent.get("file_path") or ""),
                raw=ent,
            )
        )
    for chunk in data.get("chunks") or []:
        text = str(chunk.get("content") or "").strip()
        items.append(
            EvidenceItem(
                kind="chunk",
                text=text,
                file_path=str(chunk.get("file_path") or ""),
                raw=chunk,
            )
        )
    return items


def _resolve_workspace(settings: Settings) -> str:
    """Prefer configured Settings.workspace; only fall back to live /health when unset."""
    cached = getattr(settings, "_resolved_workspace", None)
    if cached:
        return str(cached)
    workspace = (getattr(settings, "workspace", None) or "").strip()
    if not workspace and httpx is not None:
        try:
            with httpx.Client(timeout=5.0, trust_env=False) as client:
                resp = client.get(f"{settings.lightrag_url.rstrip('/')}/health")
                if resp.status_code == 200:
                    conf = (resp.json() or {}).get("configuration") or {}
                    live = str(conf.get("workspace") or "").strip()
                    if live:
                        workspace = live
        except Exception:  # noqa: BLE001
            pass
    elif workspace and httpx is not None:
        # Optional mismatch warning — never override a configured workspace.
        try:
            with httpx.Client(timeout=5.0, trust_env=False) as client:
                resp = client.get(f"{settings.lightrag_url.rstrip('/')}/health")
                if resp.status_code == 200:
                    conf = (resp.json() or {}).get("configuration") or {}
                    live = str(conf.get("workspace") or "").strip()
                    if live and live != workspace:
                        import logging

                        logging.getLogger(__name__).warning(
                            "Configured workspace=%s differs from live /health workspace=%s; "
                            "using configured value for chunk backfill",
                            workspace,
                            live,
                        )
        except Exception:  # noqa: BLE001
            pass
    workspace = workspace or "aeb_demo"
    settings._resolved_workspace = workspace  # type: ignore[attr-defined]
    return workspace


def _chunk_store_path(settings: Settings) -> Path | None:
    workspace = _resolve_workspace(settings)
    path = (
        Path(settings.aeb_root)
        / "data"
        / "rag_storage"
        / workspace
        / "kv_store_text_chunks.json"
    )
    return path if path.is_file() else None


def _load_chunk_record(settings: Settings, chunk_id: str) -> dict[str, Any] | None:
    store = getattr(settings, "_chunk_store_cache", None)
    if store is None:
        path = _chunk_store_path(settings)
        if path is None:
            settings._chunk_store_cache = {}  # type: ignore[attr-defined]
            return None
        try:
            settings._chunk_store_cache = json.loads(  # type: ignore[attr-defined]
                path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            settings._chunk_store_cache = {}  # type: ignore[attr-defined]
            return None
        store = settings._chunk_store_cache  # type: ignore[attr-defined]
    if not isinstance(store, dict):
        return None
    rec = store.get(chunk_id)
    return rec if isinstance(rec, dict) else None


# LightRAG joins multiple chunk ids with GRAPH_FIELD_SEP ("<SEP>").
_SOURCE_ID_SPLIT_RE = re.compile(r"(?:<SEP>|\|\|\|)")


def split_source_ids(raw_source_id: str) -> list[str]:
    """Split multi-chunk source_id fields into individual chunk keys."""
    value = str(raw_source_id or "").strip()
    if not value:
        return []
    parts = [p.strip() for p in _SOURCE_ID_SPLIT_RE.split(value) if p.strip()]
    return parts or ([value] if value else [])


def _source_ids_from_items(items: list[EvidenceItem]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in items:
        if item.kind not in {"relationship", "entity"}:
            continue
        raw = item.raw or {}
        sid = str(raw.get("source_id") or "").strip()
        if not sid:
            continue
        for part in split_source_ids(sid):
            counts[part] += 1
    return counts


def _existing_chunk_keys(items: list[EvidenceItem]) -> set[str]:
    """Chunk ids already present (payload or prior bag) to avoid duplicate expand."""
    keys: set[str] = set()
    for item in items:
        if item.kind != "chunk":
            continue
        raw = item.raw or {}
        for field in ("id", "chunk_id", "source_id", "_id"):
            val = str(raw.get(field) or "").strip()
            if val:
                keys.update(split_source_ids(val))
        # file_path sometimes encodes unit; not a chunk hash — skip
    return keys


def backfill_chunks_from_graph_hits(
    settings: Settings,
    items: list[EvidenceItem],
    *,
    max_chunks: int = 6,
    min_cooccur: int = 1,
) -> list[EvidenceItem]:
    """Expand graph hits to full source chunks (source_id → text unit).

    Mainstream pattern: graph locates, then pull source text. Skips chunk ids
    already returned by LightRAG. Splits multi-id source_id on <SEP>.
    """
    if not bool(getattr(settings, "chunk_backfill_enabled", True)):
        return []
    counts = _source_ids_from_items(items)
    if not counts:
        return []
    existing_text = {item.text for item in items if item.text}
    already = _existing_chunk_keys(items)
    ranked = [
        (sid, n)
        for sid, n in counts.most_common()
        if n >= min_cooccur and sid not in already
    ]
    out: list[EvidenceItem] = []
    for sid, n in ranked:
        if len(out) >= max_chunks:
            break
        rec = _load_chunk_record(settings, sid)
        if not rec:
            continue
        content = str(rec.get("content") or "").strip()
        if not content or content in existing_text:
            continue
        out.append(
            EvidenceItem(
                kind="chunk",
                text=content,
                file_path=str(rec.get("file_path") or ""),
                source_tool="chunk_backfill",
                raw={
                    "source_id": sid,
                    "id": sid,
                    "cooccur": n,
                    "backfill": True,
                },
            )
        )
        existing_text.add(content)
        already.add(sid)
    return out


class LightRAGRetrieveTool(Tool):
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "focused sub-question"},
            "mode": {"type": "string", "description": "naive|hybrid|mix"},
        },
        "required": ["query"],
    }

    def __init__(
        self,
        settings: Settings,
        name: str,
        default_mode: str,
        description: str,
        catalog: EvidenceCatalog | None = None,
    ):
        self.settings = settings
        self.name = name
        self.default_mode = default_mode
        self.description = description
        self.catalog = catalog

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult(
                name=self.name,
                ok=False,
                content="必须提供针对性 query（子问题），不要空查。",
                error="missing_query",
                continue_loop=True,
            )

        mode = str(args.get("mode") or self.default_mode).strip()
        signature = f"{self.name}|{mode}|{query}"
        if state.register_call(signature):
            return ToolResult(
                name=self.name,
                ok=False,
                content=(
                    f"重复检索已拦截：{signature}。"
                    "请换子问题 query、换 mode，或 evidence_check / compose_answer。"
                ),
                error="duplicate_call",
                continue_loop=True,
            )

        top_k = int(args.get("top_k") or self.settings.retrieve_top_k)
        max_tokens = int(args.get("max_tokens") or self.settings.context_tokens)
        # LightRAG-style multi-bucket budgets: leave ~half for text units.
        ent_frac = float(getattr(self.settings, "entity_token_fraction", 0.25) or 0.25)
        rel_frac = float(getattr(self.settings, "relation_token_fraction", 0.25) or 0.25)
        ent_frac = min(0.4, max(0.1, ent_frac))
        rel_frac = min(0.4, max(0.1, rel_frac))
        if ent_frac + rel_frac > 0.7:
            scale = 0.7 / (ent_frac + rel_frac)
            ent_frac *= scale
            rel_frac *= scale
        max_entity_tokens = max(512, int(max_tokens * ent_frac))
        max_relation_tokens = max(512, int(max_tokens * rel_frac))
        enable_rerank = bool(
            args.get(
                "enable_rerank",
                getattr(self.settings, "enable_rerank", True),
            )
        )
        url = f"{self.settings.lightrag_url}/query/data"
        body = {
            "query": query,
            "mode": mode,
            "top_k": top_k,
            "chunk_top_k": top_k,
            "max_total_tokens": max_tokens,
            "max_entity_tokens": max_entity_tokens,
            "max_relation_tokens": max_relation_tokens,
            "enable_rerank": enable_rerank,
        }
        if httpx is None:
            return ToolResult(
                name=self.name,
                ok=False,
                content="httpx 未安装，无法调用 LightRAG",
                error="httpx_missing",
                continue_loop=True,
            )
        try:
            # trust_env=False: system HTTP(S)_PROXY must not intercept localhost LightRAG
            with httpx.Client(
                timeout=self.settings.request_timeout, trust_env=False
            ) as client:
                response = client.post(url, headers=_headers(self.settings), json=body)
                response.raise_for_status()
                payload = response.json()
        except Exception as error:  # noqa: BLE001
            return ToolResult(
                name=self.name,
                ok=False,
                content=f"LightRAG 检索失败: {error}",
                error=str(error),
                continue_loop=True,
            )

        if payload.get("status") and payload.get("status") != "success":
            message = str(payload.get("message") or payload)
            return ToolResult(
                name=self.name,
                ok=False,
                content=f"LightRAG 返回非 success: {message}",
                data={"payload": payload},
                error=message,
                continue_loop=True,
            )

        items = _items_from_payload(payload)
        backfilled = backfill_chunks_from_graph_hits(
            self.settings,
            items,
            max_chunks=int(getattr(self.settings, "chunk_backfill_max", 6) or 6),
            min_cooccur=int(getattr(self.settings, "chunk_backfill_min_cooccur", 1) or 1),
        )
        items = items + backfilled

        kb = None
        intent = (state.meta or {}).get("intent") or {}
        if isinstance(intent.get("kb"), list) and intent["kb"]:
            kb = str(intent["kb"][0])
        elif self.settings.active_kb:
            kb = self.settings.active_kb

        mapped_ids: list[str] = []
        for item in items:
            item.source_tool = item.source_tool or self.name
            if self.catalog is not None:
                ids = self.catalog.match_ids_for_text(
                    item.text, file_path=item.file_path, kb=kb
                )
                if ids:
                    item.evidence_ids = merge_evidence_ids(item.evidence_ids, ids)
                    mapped_ids.extend(ids)

        seen = {item.text for item in state.evidence}
        added = 0
        # Prefer appending backfilled chunks after graph hits but before compact
        for item in items:
            if not item.text or item.text in seen:
                continue
            state.evidence.append(item)
            seen.add(item.text)
            added += 1

        bag_limit = int(
            args.get("bag_limit")
            or getattr(self.settings, "bag_limit", 20)
            or 20
        )
        state.evidence = compact_evidence(
            state.evidence,
            state.question,
            max_items=bag_limit,
            settings=self.settings,
            query=query,
        )
        if state.slots:
            refresh_slots(state.slots, state.evidence)

        content = observation_from_items(
            state.evidence,
            mode=mode,
            added=added,
            bag_size=len(state.evidence),
        )
        if backfilled:
            content += f"\nchunk_backfill={len(backfilled)}"
        if mapped_ids:
            uniq = list(dict.fromkeys(mapped_ids))[:12]
            content += f"\nmapped_evidence_ids={uniq}"
        missing = [slot.id for slot in state.slots if slot.status != "covered"]
        if missing:
            content += f"\nslots_not_covered={missing}"

        from reg_harness.bag_gaps import analyze_bag_gaps, format_gap_hints

        gaps = analyze_bag_gaps(state.evidence, state.question)
        gap_text = format_gap_hints(state.evidence, state.question)
        if gap_text:
            content += gap_text
        content += (
            "\n提示: 默认 graph 用 mix（图+向量）；可换 query/mode；"
            "有【取证缺口】时先补表号/条款再 compose；"
            "evidence_check 查看袋；足够则 compose_answer，不足可 finalize 拒答。"
        )

        meta = payload.get("metadata") or {}
        return ToolResult(
            name=self.name,
            ok=True,
            content=content,
            data={
                "mode": mode,
                "query": query,
                "added": added,
                "n_items": len(items),
                "backfilled_chunks": len(backfilled),
                "bag_size": len(state.evidence),
                "enable_rerank": enable_rerank,
                "bag_rerank": bool(
                    getattr(self.settings, "bag_rerank_enabled", False)
                ),
                "token_budget": {
                    "max_total_tokens": max_tokens,
                    "max_entity_tokens": max_entity_tokens,
                    "max_relation_tokens": max_relation_tokens,
                },
                "lightrag_meta": meta,
                "mapped_evidence_ids": list(dict.fromkeys(mapped_ids))[:20],
                "bag_gaps": gaps,
            },
        )


def build_retrieve_tools(
    settings: Settings,
    catalog: EvidenceCatalog | None = None,
) -> list[Tool]:
    graph_mode = getattr(settings, "graph_default_mode", None) or "mix"
    return [
        LightRAGRetrieveTool(
            settings,
            name="vector_search",
            default_mode="naive",
            description="Vector search over text chunks. Pass a focused sub-query.",
            catalog=catalog,
        ),
        LightRAGRetrieveTool(
            settings,
            name="graph_search",
            default_mode=str(graph_mode),
            description=(
                "Graph + vector retrieval (default mode mix). "
                "Pass a focused sub-query; mode naive|hybrid|mix."
            ),
            catalog=catalog,
        ),
    ]
