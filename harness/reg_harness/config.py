from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path


HARNESS_ROOT = Path(__file__).resolve().parents[1]
AEB_ROOT = HARNESS_ROOT.parent


def _env_flag(env: dict[str, str], name: str, default: bool = False) -> bool:
    raw = (env.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(
        f"{name} must be one of: 1, true, yes, on, 0, false, no, off"
    )


def _env_int(
    env: dict[str, str],
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = (env.get(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if minimum is not None and value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise RuntimeError(f"{name} must be <= {maximum}")
    return value


def _env_float(
    env: dict[str, str],
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_exclusive: bool = False,
) -> float:
    raw = (env.get(name) or "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError as error:
        raise RuntimeError(f"{name} must be a number") from error
    if not math.isfinite(value):
        raise RuntimeError(f"{name} must be finite")
    if minimum is not None:
        if minimum_exclusive and value <= minimum:
            raise RuntimeError(f"{name} must be > {minimum:g}")
        if not minimum_exclusive and value < minimum:
            raise RuntimeError(f"{name} must be >= {minimum:g}")
    if maximum is not None and value > maximum:
        raise RuntimeError(f"{name} must be <= {maximum:g}")
    return value


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


def _profile_path(root: Path, profile: str) -> Path:
    candidate = Path(profile)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    resolved_root = root.resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as error:
        raise RuntimeError(
            f"Profile env file must stay inside {resolved_root}: {profile}"
        ) from error
    if not candidate.is_file():
        raise RuntimeError(f"Profile env file does not exist: {candidate}")
    return candidate


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
        env.update(_parse_env_file(_profile_path(root, profile)))

    extra_body = None
    raw_extra = env.get("OPENAI_LLM_EXTRA_BODY", "").strip()
    if raw_extra:
        import json

        try:
            extra_body = json.loads(raw_extra)
        except json.JSONDecodeError as error:
            raise RuntimeError("OPENAI_LLM_EXTRA_BODY must be valid JSON") from error
        if not isinstance(extra_body, dict):
            raise RuntimeError("OPENAI_LLM_EXTRA_BODY must be a JSON object")

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
    rerank_api_key = (env.get("RERANK_BINDING_API_KEY") or "").strip()
    if not rerank_api_key and (
        rerank_binding.lower() == "aliyun"
        or "dashscope.aliyuncs.com" in rerank_host.lower()
    ):
        rerank_api_key = (env.get("DASHSCOPE_API_KEY") or "").strip()
    # Default on when remote rerank is configured; HARNESS_BAG_RERANK can force off/on.
    bag_rerank_default = bool(rerank_binding and rerank_model and rerank_host and rerank_api_key)
    bag_rerank_enabled = _env_flag(env, "HARNESS_BAG_RERANK", default=bag_rerank_default)
    min_rerank_score = _env_float(
        env,
        "MIN_RERANK_SCORE",
        0.0,
        minimum=0.0,
        maximum=1.0,
    )
    chunk_backfill_enabled = _env_flag(env, "HARNESS_CHUNK_BACKFILL", default=True)
    catalog_mode = (env.get("HARNESS_CATALOG_MODE") or "none").strip().lower()
    if catalog_mode not in {"none", "gold", "index"}:
        raise RuntimeError(
            "HARNESS_CATALOG_MODE must be one of: none, gold, index"
        )
    if catalog_mode == "index":
        raise RuntimeError(
            "HARNESS_CATALOG_MODE=index is not implemented yet; use none or gold"
        )
    graph_default_mode = (env.get("HARNESS_GRAPH_DEFAULT_MODE") or "mix").strip().lower()
    if graph_default_mode not in {"naive", "hybrid", "mix"}:
        raise RuntimeError(
            "HARNESS_GRAPH_DEFAULT_MODE must be one of: naive, hybrid, mix"
        )
    workspace = (env.get("WORKSPACE") or "aeb_demo").strip()
    temperature = _env_float(
        env,
        "HARNESS_TEMPERATURE",
        0.0,
        minimum=0.0,
        maximum=2.0,
    )
    request_timeout = _env_float(
        env,
        "HARNESS_TIMEOUT",
        120.0,
        minimum=0.0,
        minimum_exclusive=True,
    )
    default_max_steps = _env_int(
        env,
        "HARNESS_MAX_STEPS",
        6,
        minimum=1,
        maximum=100,
    )
    retrieve_top_k = _env_int(
        env,
        "HARNESS_TOP_K",
        20,
        minimum=1,
        maximum=100,
    )
    context_tokens = _env_int(
        env,
        "HARNESS_CONTEXT_TOKENS",
        12000,
        minimum=256,
        maximum=200000,
    )
    chunk_backfill_max = _env_int(
        env,
        "HARNESS_CHUNK_BACKFILL_MAX",
        8,
        minimum=1,
        maximum=100,
    )
    chunk_backfill_min_cooccur = _env_int(
        env,
        "HARNESS_CHUNK_BACKFILL_MIN_COOCCUR",
        1,
        minimum=1,
        maximum=100,
    )
    bag_limit = _env_int(
        env,
        "HARNESS_BAG_LIMIT",
        20,
        minimum=1,
        maximum=100,
    )
    bag_max_entities = _env_int(
        env,
        "HARNESS_BAG_MAX_ENTITIES",
        5,
        minimum=1,
        maximum=100,
    )
    bag_max_relations = _env_int(
        env,
        "HARNESS_BAG_MAX_RELATIONS",
        5,
        minimum=1,
        maximum=100,
    )
    entity_token_fraction = _env_float(
        env,
        "HARNESS_ENTITY_TOKEN_FRACTION",
        0.15,
        minimum=0.1,
        maximum=0.4,
    )
    relation_token_fraction = _env_float(
        env,
        "HARNESS_RELATION_TOKEN_FRACTION",
        0.15,
        minimum=0.1,
        maximum=0.4,
    )
    if entity_token_fraction + relation_token_fraction > 0.7:
        raise RuntimeError(
            "HARNESS_ENTITY_TOKEN_FRACTION + "
            "HARNESS_RELATION_TOKEN_FRACTION must be <= 0.7"
        )

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
        temperature=temperature,
        request_timeout=request_timeout,
        default_max_steps=default_max_steps,
        retrieve_top_k=retrieve_top_k,
        context_tokens=context_tokens,
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
        chunk_backfill_max=chunk_backfill_max,
        chunk_backfill_min_cooccur=chunk_backfill_min_cooccur,
        bag_limit=bag_limit,
        bag_max_entities=bag_max_entities,
        bag_max_relations=bag_max_relations,
        entity_token_fraction=entity_token_fraction,
        relation_token_fraction=relation_token_fraction,
    )
