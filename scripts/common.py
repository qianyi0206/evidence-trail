from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
MANIFEST_PATH = ROOT / "corpus" / "manifest.json"
STATE_DIR = ROOT / "state"
INDEX_FINGERPRINT_SCHEMA_VERSION = 2
T = TypeVar("T")


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


def resolve_inside_root(setting: str, *, root: Path = ROOT, label: str) -> Path:
    path = (root / setting).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise RuntimeError(f"{label} must stay inside {root}: {setting}") from error
    return path


def workspace_state_path(env: dict[str, str], stem: str) -> Path:
    workspace = safe_workspace(env)
    legacy = STATE_DIR / f"{stem}.json"
    if workspace == "aeb_demo" and legacy.exists():
        return legacy
    return STATE_DIR / f"{stem}.{workspace}.json"


def ingest_path_for_record(env: dict[str, str], record: dict[str, Any]) -> Path:
    profile_source = env.get("GB39901_SOURCE_DOCUMENT", "").strip()
    if profile_source and record.get("source_id") == "gb_39901_2025":
        return resolve_inside_root(
            profile_source,
            label="GB39901_SOURCE_DOCUMENT",
        )
    return resolve_inside_root(
        str(record["prepared_file"]),
        label="prepared_file",
    )


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def active_documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    documents = [
        record
        for record in manifest.get("documents", [])
        if record.get("enabled", True)
    ]
    if not documents:
        raise RuntimeError("Corpus manifest has no enabled documents")
    return documents


def _serialized_sha256(payload: Any) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def corpus_fingerprint(
    env: dict[str, str],
    *,
    root: Path = ROOT,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    structural_setting = env.get("GB39901_STRUCTURAL_UNITS_FILE", "").strip()
    if structural_setting:
        bundle_path = resolve_inside_root(
            structural_setting,
            root=root,
            label="GB39901_STRUCTURAL_UNITS_FILE",
        )
        if not bundle_path.is_file():
            raise RuntimeError(f"Structural bundle is missing: {bundle_path}")
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        units = bundle.get("units", [])
        if not units:
            raise RuntimeError("Structural bundle has no units")

        for unit in units:
            content = unit.get("content")
            declared = str(unit.get("sha256", "")).strip()
            if not isinstance(content, str) or not declared:
                raise RuntimeError("Structural bundle unit is missing content or sha256")
            # The bundle generator records the hash before normalizing its trailing
            # newline, so validate the same canonical representation here.
            actual = hashlib.sha256(content.rstrip().encode("utf-8")).hexdigest()
            if actual != declared:
                raise RuntimeError(
                    "Structural bundle unit hash mismatch: "
                    f"{unit.get('unit_id', '<unknown>')}"
                )

        source_file = str(bundle.get("source_file", "")).strip()
        source_declared = str(bundle.get("source_sha256", "")).strip()
        if not source_file or not source_declared:
            raise RuntimeError("Structural bundle is missing source_file or source_sha256")
        source_path = resolve_inside_root(
            str(Path("corpus") / "prepared" / Path(source_file).name),
            root=root,
            label="structural source_file",
        )
        if not source_path.is_file():
            raise RuntimeError(f"Structural source document is missing: {source_path}")
        source_actual = sha256_file(source_path)
        if source_actual != source_declared:
            raise RuntimeError(
                "Structural source document hash does not match source_sha256"
            )

        inputs = {
            "mode": "structural_bundle",
            "bundle_file": str(bundle_path.relative_to(root.resolve())),
            "bundle_sha256": sha256_file(bundle_path),
            "source_id": bundle.get("source_id"),
            "source_file": str(source_path.relative_to(root.resolve())),
            "source_sha256": source_actual,
            "unit_count": len(units),
        }
        return {"sha256": _serialized_sha256(inputs), "inputs": inputs}

    effective_manifest = manifest_path or root / "corpus" / "manifest.json"
    effective_manifest = effective_manifest.resolve()
    try:
        effective_manifest.relative_to(root.resolve())
    except ValueError as error:
        raise RuntimeError(
            f"Corpus manifest must stay inside {root}: {effective_manifest}"
        ) from error
    if not effective_manifest.is_file():
        raise RuntimeError(f"Corpus manifest is missing: {effective_manifest}")

    manifest = json.loads(effective_manifest.read_text(encoding="utf-8"))
    prepared_inputs: list[dict[str, Any]] = []
    for record in active_documents(manifest):
        if "prepared_file" not in record:
            raise RuntimeError(
                f"Prepared corpus entry is incomplete: {record.get('source_id')}"
            )
        profile_source = env.get("GB39901_SOURCE_DOCUMENT", "").strip()
        if profile_source and record.get("source_id") == "gb_39901_2025":
            prepared_path = resolve_inside_root(
                profile_source,
                root=root,
                label="GB39901_SOURCE_DOCUMENT",
            )
            declared = ""
        else:
            prepared_path = resolve_inside_root(
                str(record["prepared_file"]),
                root=root,
                label="prepared_file",
            )
            declared = str(record.get("prepared_sha256", "")).strip()
        if not prepared_path.is_file():
            raise RuntimeError(f"Prepared corpus file is missing: {prepared_path}")
        actual = sha256_file(prepared_path)
        if declared and actual != declared:
            raise RuntimeError(
                "Prepared corpus hash does not match manifest: "
                f"{record.get('source_id')}"
            )
        prepared_inputs.append(
            {
                "source_id": record.get("source_id"),
                "prepared_file": str(prepared_path.relative_to(root.resolve())),
                "prepared_sha256": actual,
            }
        )

    inputs = {
        "mode": "prepared_documents",
        "manifest_file": str(effective_manifest.relative_to(root.resolve())),
        "manifest_sha256": sha256_file(effective_manifest),
        "documents": sorted(prepared_inputs, key=lambda item: str(item["source_id"])),
    }
    return {"sha256": _serialized_sha256(inputs), "inputs": inputs}


def index_fingerprint(
    env: dict[str, str],
    *,
    root: Path = ROOT,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": INDEX_FINGERPRINT_SCHEMA_VERSION,
        **embedding_fingerprint(env),
        "corpus": corpus_fingerprint(
            env,
            root=root,
            manifest_path=manifest_path,
        ),
    }


def ensure_index_compatible(
    env: dict[str, str],
    fingerprint_path: Path,
    *,
    root: Path = ROOT,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    current = index_fingerprint(
        env,
        root=root,
        manifest_path=manifest_path,
    )
    if not fingerprint_path.exists():
        return current

    stored = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    if (
        stored.get("schema_version") != INDEX_FINGERPRINT_SCHEMA_VERSION
        or not isinstance(stored.get("corpus"), dict)
    ):
        raise RuntimeError(
            "Legacy index fingerprint has no verifiable corpus hash. Refusing to reuse "
            "the index; explicitly run 'make reset-index CONFIRM=RESET_AEB_INDEX' and "
            "re-ingest it."
        )
    if stored.get("status") != "ready":
        raise RuntimeError(
            "Index fingerprint is not ready, which indicates an interrupted or "
            "unverified ingest. Refusing to reuse the workspace; explicitly run "
            "'make reset-index CONFIRM=RESET_AEB_INDEX' and re-ingest it."
        )
    if stored.get("sha256") != current["sha256"]:
        raise RuntimeError(
            "Embedding configuration changed after indexing. Refusing to mix vector "
            "spaces. Restore the original settings or explicitly run "
            "'make reset-index CONFIRM=RESET_AEB_INDEX'."
        )
    if stored["corpus"].get("sha256") != current["corpus"]["sha256"]:
        raise RuntimeError(
            "Corpus content changed after indexing. Refusing to reuse a stale index; "
            "explicitly run 'make reset-index CONFIRM=RESET_AEB_INDEX' and re-ingest it."
        )
    return current


@contextmanager
def workspace_lock(
    env: dict[str, str],
    *,
    state_dir: Path = STATE_DIR,
) -> Iterator[Path]:
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / f".ingest.{safe_workspace(env)}.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                f"Another ingest process holds the workspace lock: {lock_path}"
            ) from error
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        try:
            yield lock_path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def workspace_locked(function: Callable[..., T]) -> Callable[..., T]:
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> T:
        env = load_env()
        with workspace_lock(env):
            return function(env, *args, **kwargs)

    return wrapped


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
