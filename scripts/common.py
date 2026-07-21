from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
MANIFEST_PATH = ROOT / "corpus" / "manifest.json"
STATE_DIR = ROOT / "state"


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise RuntimeError(f"Missing {path}. Run 'make configure' first.")

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    values = _read_env_file(path)
    profile_name = os.getenv("AEB_PROFILE_ENV", "").strip()
    if not profile_name:
        return values

    profile_path = (ROOT / profile_name).resolve()
    try:
        profile_path.relative_to(ROOT.resolve())
    except ValueError as error:
        raise RuntimeError(f"Profile env must stay inside {ROOT}: {profile_name}") from error
    values.update(_read_env_file(profile_path))
    return values


def safe_workspace(env: dict[str, str]) -> str:
    workspace = env.get("WORKSPACE", "aeb_demo").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", workspace):
        raise RuntimeError(f"Unsafe workspace label: {workspace}")
    return workspace


def workspace_state_path(env: dict[str, str], stem: str) -> Path:
    workspace = safe_workspace(env)
    legacy = STATE_DIR / f"{stem}.json"
    if workspace == "aeb_demo" and legacy.exists():
        return legacy
    return STATE_DIR / f"{stem}.{workspace}.json"


def ingest_path_for_record(env: dict[str, str], record: dict[str, Any]) -> Path:
    profile_source = env.get("GB39901_SOURCE_DOCUMENT", "").strip()
    if profile_source and record.get("source_id") == "gb_39901_2025":
        path = (ROOT / profile_source).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError as error:
            raise RuntimeError(
                f"GB39901_SOURCE_DOCUMENT must stay inside {ROOT}: {profile_source}"
            ) from error
        return path
    return ROOT / record["prepared_file"]


def require_env(env: dict[str, str], names: list[str]) -> None:
    missing = [name for name in names if not env.get(name, "").strip()]
    if missing:
        raise RuntimeError(f"Missing required .env values: {', '.join(missing)}")


def is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in (
            "replace_with",
            "your-openai-compatible-host.example",
            "your_api_key",
            "<api",
            "<model",
        )
    )


def api_headers(env: dict[str, str]) -> dict[str, str]:
    key = env.get("LIGHTRAG_API_KEY", "").strip()
    return {"X-API-Key": key} if key else {}


def lightrag_url(env: dict[str, str], path: str) -> str:
    return env.get("LIGHTRAG_API_URL", "http://lightrag:9621").rstrip("/") + path


def neo4j_query(env: dict[str, str], statement: str, parameters: dict[str, Any] | None = None) -> list[list[Any]]:
    base_url = env.get("NEO4J_HTTP_URL", "http://neo4j:7474").rstrip("/")
    database = env.get("NEO4J_DATABASE", "neo4j")
    username = env.get("NEO4J_USERNAME", "neo4j")
    password = env["NEO4J_PASSWORD"]
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    response = httpx.post(
        f"{base_url}/db/{database}/tx/commit",
        headers={"Authorization": f"Basic {auth}"},
        json={"statements": [{"statement": statement, "parameters": parameters or {}}]},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"Neo4j query failed: {payload['errors']}")
    results = payload.get("results", [])
    if not results:
        return []
    return [row["row"] for row in results[0].get("data", [])]


def embedding_fingerprint(env: dict[str, str]) -> dict[str, Any]:
    host = urlsplit(env["EMBEDDING_BINDING_HOST"])
    safe_host = f"{host.scheme}://{host.netloc}{host.path.rstrip('/')}"
    config = {
        "binding": env.get("EMBEDDING_BINDING", "openai"),
        "host": safe_host,
        "model": env["EMBEDDING_MODEL"],
        "dimension": int(env["EMBEDDING_DIM"]),
        "token_limit": int(env["EMBEDDING_TOKEN_LIMIT"]),
    }
    serialized = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return {"sha256": hashlib.sha256(serialized.encode()).hexdigest(), "config": config}


def active_documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    documents = [
        record
        for record in manifest.get("documents", [])
        if record.get("enabled", True)
    ]
    if not documents:
        raise RuntimeError("Corpus manifest has no enabled documents")
    return documents


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)
