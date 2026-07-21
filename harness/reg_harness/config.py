from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


HARNESS_ROOT = Path(__file__).resolve().parents[1]
AEB_ROOT = HARNESS_ROOT.parent


def _env_flag(env: dict[str, str], name: str, default: bool = False) -> bool:
    raw = (env.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    aeb_root: Path
    lightrag_url: str
    llm_host: str
    llm_api_key: str
    llm_model: str
    llm_extra_body: dict | None
    temperature: float = 0.0
    request_timeout: float = 120.0
    default_max_steps: int = 4
    retrieve_top_k: int = 20
    context_tokens: int = 4000
    api_key_header: str = ""
    active_kb: str = "gb39901"
    evidence_jsonl: Path | None = None
    # Default off: skill + model plan. Set HARNESS_PILOT_HEURISTICS=1 for legacy rule routing.
    pilot_heuristics: bool = False
    # Default off: no clause/table tools. Set HARNESS_ENABLE_PRECISE_LOOKUP=1 to register them.
    enable_precise_lookup: bool = False
    # Catalog: none (default) | gold (benchmark evidence.jsonl, only useful with precise lookup)
    catalog_mode: str = "none"
    # LightRAG workspace name (for local chunk store backfill)
    workspace: str = "aeb_demo"
    # graph_search default mode: mix brings graph hits + vector chunks
    graph_default_mode: str = "mix"
    # Pass enable_rerank to /query/data (requires container RERANK_BINDING)
    enable_rerank: bool = True
    # Bag-side rerank after merge/backfill (same RERANK_* credentials when set)
    bag_rerank_enabled: bool = True
    rerank_binding: str = ""
    rerank_model: str = ""
    rerank_host: str = ""
    rerank_api_key: str = ""
    min_rerank_score: float = 0.0
    # Promote source chunks shared by multiple entity/relation hits
    chunk_backfill_enabled: bool = True
    chunk_backfill_max: int = 8
    chunk_backfill_min_cooccur: int = 1
    bag_limit: int = 20
    # Text-primary bag: cap graph abstracts so chunks keep most seats
    bag_max_entities: int = 5
    bag_max_relations: int = 5
    # LightRAG /query/data token buckets (fractions of context_tokens).
    # 0.15/0.15 leaves ~70% for text units; measured better on GB39901 cases than 0.25/0.25.
    entity_token_fraction: float = 0.15
    relation_token_fraction: float = 0.15

    @property
    def chat_completions_url(self) -> str:
        base = self.llm_host.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return base + "/chat/completions"
        return base + "/v1/chat/completions"


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        values[key] = value
    return values


def load_settings(
    profile_env: str | None = None,
    aeb_root: Path | None = None,
) -> Settings:
    """Load demo .env the same way scripts/common.py does, without importing demo scripts."""
    root = aeb_root or AEB_ROOT
    env: dict[str, str] = dict(os.environ)
    base = _parse_env_file(root / ".env")
    env.update(base)

    profile = profile_env or os.environ.get("AEB_PROFILE_ENV") or ""
    if profile:
        profile_path = Path(profile)
        if not profile_path.is_absolute():
            profile_path = root / profile_path
        env.update(_parse_env_file(profile_path))

    extra_body = None
    raw_extra = env.get("OPENAI_LLM_EXTRA_BODY", "").strip()
    if raw_extra:
        import json

        try:
            extra_body = json.loads(raw_extra)
        except json.JSONDecodeError:
            extra_body = None

    # In-docker service name vs host
    host_url = env.get("LIGHTRAG_PUBLIC_URL") or env.get("LIGHTRAG_URL") or "http://127.0.0.1:9621"
    # Prefer host-accessible URL for local harness runs
    if "lightrag:9621" in host_url:
        host_url = "http://127.0.0.1:9621"

    pilot_heuristics = _env_flag(env, "HARNESS_PILOT_HEURISTICS", default=False)
    enable_precise_lookup = _env_flag(env, "HARNESS_ENABLE_PRECISE_LOOKUP", default=False)
    enable_rerank = _env_flag(env, "HARNESS_ENABLE_RERANK", default=True)
    rerank_binding = (env.get("RERANK_BINDING") or "").strip()
    if rerank_binding.lower() in {"null", "none", "off", "0"}:
        rerank_binding = ""
    rerank_model = (env.get("RERANK_MODEL") or "").strip()
    rerank_host = (env.get("RERANK_BINDING_HOST") or "").strip()
    rerank_api_key = (
        env.get("RERANK_BINDING_API_KEY")
        or env.get("LLM_BINDING_API_KEY")
        or env.get("DASHSCOPE_API_KEY")
        or ""
    ).strip()
    # Default on when remote rerank is configured; HARNESS_BAG_RERANK can force off/on.
    bag_rerank_default = bool(rerank_binding and rerank_model and rerank_host and rerank_api_key)
    bag_rerank_enabled = _env_flag(env, "HARNESS_BAG_RERANK", default=bag_rerank_default)
    min_rerank_score = float(env.get("MIN_RERANK_SCORE", "0") or 0)
    chunk_backfill_enabled = _env_flag(env, "HARNESS_CHUNK_BACKFILL", default=True)
    catalog_mode = (env.get("HARNESS_CATALOG_MODE") or "none").strip().lower()
    if catalog_mode not in {"none", "gold", "index"}:
        catalog_mode = "none"
    if catalog_mode == "index":
        raise RuntimeError(
            "HARNESS_CATALOG_MODE=index is not implemented yet; use none or gold"
        )
    graph_default_mode = (env.get("HARNESS_GRAPH_DEFAULT_MODE") or "mix").strip().lower()
    if graph_default_mode not in {"naive", "hybrid", "mix"}:
        graph_default_mode = "mix"
    workspace = (env.get("WORKSPACE") or "aeb_demo").strip()

    evidence_path = env.get("HARNESS_EVIDENCE_JSONL", "").strip()
    evidence_jsonl: Path | None = None
    if catalog_mode == "gold":
        # Gold catalog is opt-in only — never auto-promote from a bare path.
        evidence_jsonl = (
            Path(evidence_path)
            if evidence_path
            else (root / "benchmark" / "data" / "evidence.jsonl")
        )
        if not evidence_jsonl.is_absolute():
            evidence_jsonl = root / evidence_jsonl
    elif evidence_path:
        # Path set without gold mode: ignore path to preserve online isolation.
        import logging

        logging.getLogger(__name__).warning(
            "HARNESS_EVIDENCE_JSONL is set but HARNESS_CATALOG_MODE=%s; "
            "ignoring gold path (set HARNESS_CATALOG_MODE=gold to load it)",
            catalog_mode,
        )

    return Settings(
        aeb_root=root,
        lightrag_url=host_url.rstrip("/"),
        llm_host=env.get("LLM_BINDING_HOST", ""),
        llm_api_key=env.get("LLM_BINDING_API_KEY", ""),
        llm_model=env.get("LLM_MODEL", "gpt-4o-mini"),
        llm_extra_body=extra_body,
        temperature=float(env.get("HARNESS_TEMPERATURE", "0") or 0),
        request_timeout=float(env.get("HARNESS_TIMEOUT", "120") or 120),
        default_max_steps=int(env.get("HARNESS_MAX_STEPS", "6") or 6),
        retrieve_top_k=int(env.get("HARNESS_TOP_K", "20") or 20),
        context_tokens=int(env.get("HARNESS_CONTEXT_TOKENS", "12000") or 12000),
        api_key_header=env.get("LIGHTRAG_API_KEY", ""),
        active_kb=env.get("HARNESS_ACTIVE_KB", "gb39901"),
        evidence_jsonl=evidence_jsonl,
        pilot_heuristics=pilot_heuristics,
        enable_precise_lookup=enable_precise_lookup,
        catalog_mode=catalog_mode,
        workspace=workspace,
        graph_default_mode=graph_default_mode,
        enable_rerank=enable_rerank,
        bag_rerank_enabled=bag_rerank_enabled,
        rerank_binding=rerank_binding,
        rerank_model=rerank_model,
        rerank_host=rerank_host,
        rerank_api_key=rerank_api_key,
        min_rerank_score=min_rerank_score,
        chunk_backfill_enabled=chunk_backfill_enabled,
        chunk_backfill_max=int(env.get("HARNESS_CHUNK_BACKFILL_MAX", "8") or 8),
        chunk_backfill_min_cooccur=int(
            env.get("HARNESS_CHUNK_BACKFILL_MIN_COOCCUR", "1") or 1
        ),
        bag_limit=int(env.get("HARNESS_BAG_LIMIT", "20") or 20),
        bag_max_entities=int(env.get("HARNESS_BAG_MAX_ENTITIES", "5") or 5),
        bag_max_relations=int(env.get("HARNESS_BAG_MAX_RELATIONS", "5") or 5),
        entity_token_fraction=float(
            env.get("HARNESS_ENTITY_TOKEN_FRACTION", "0.15") or 0.15
        ),
        relation_token_fraction=float(
            env.get("HARNESS_RELATION_TOKEN_FRACTION", "0.15") or 0.15
        ),
    )
