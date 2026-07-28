from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
import tempfile
import unicodedata
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = BENCHMARK_ROOT / "data"
RESULTS_DIR = BENCHMARK_ROOT / "results"
REVIEW_DIR = BENCHMARK_ROOT / "review"
AEB_ROOT = BENCHMARK_ROOT.parent

EVIDENCE_PATH = DATA_DIR / "evidence.jsonl"
QUESTIONS_PATH = DATA_DIR / "questions.jsonl"
GRAPH_PATH = DATA_DIR / "task_graph.jsonl"
AUDIT_PATH = DATA_DIR / "audit_units.jsonl"
SCHEMA_PATH = BENCHMARK_ROOT / "schema" / "benchmark.schema.json"

RUN_FORMAT_VERSION = 2
INDEX_FINGERPRINT_SCHEMA_VERSION = 2
_WORKSPACE_RE = re.compile(r"^[A-Za-z0-9_]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise RuntimeError(f"Missing JSONL file: {path}")
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid JSON at {path}:{line_number}: {error}") from error
        if not isinstance(record, dict):
            raise RuntimeError(f"Expected object at {path}:{line_number}")
        records.append(record)
    return records


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def benchmark_data_manifest() -> dict[str, Any]:
    files = [EVIDENCE_PATH, QUESTIONS_PATH, GRAPH_PATH, AUDIT_PATH, SCHEMA_PATH]
    entries = [
        {
            "path": str(path.relative_to(BENCHMARK_ROOT)),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in files
    ]
    return {
        "files": entries,
        "fingerprint": canonical_json_sha256(entries),
    }


def _require_sha256(value: Any, label: str) -> str:
    digest = str(value or "").strip().lower()
    if not _SHA256_RE.fullmatch(digest):
        raise RuntimeError(f"{label} must be a lowercase 64-character SHA-256")
    return digest


def _validate_index_fingerprint_payload(
    payload: Any,
    *,
    workspace: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("Index fingerprint must be a JSON object")
    if payload.get("schema_version") != INDEX_FINGERPRINT_SCHEMA_VERSION:
        raise RuntimeError(
            "Index fingerprint uses an unsupported schema_version; "
            f"expected {INDEX_FINGERPRINT_SCHEMA_VERSION}"
        )
    if payload.get("status") != "ready":
        raise RuntimeError(
            f"Index fingerprint for workspace {workspace!r} is not ready"
        )
    recorded_workspace = str(payload.get("workspace") or workspace).strip()
    if recorded_workspace != workspace:
        raise RuntimeError(
            "Index fingerprint workspace mismatch: "
            f"expected={workspace!r} recorded={recorded_workspace!r}"
        )

    config = payload.get("config")
    if not isinstance(config, dict):
        raise RuntimeError("Index fingerprint config must be an object")
    normalized_config: dict[str, Any] = {}
    for field in ("binding", "host", "model"):
        value = str(config.get(field) or "").strip()
        if not value:
            raise RuntimeError(f"Index fingerprint config.{field} is required")
        normalized_config[field] = value
    for field in ("dimension", "token_limit"):
        integer_value = config.get(field)
        if (
            isinstance(integer_value, bool)
            or not isinstance(integer_value, int)
            or integer_value <= 0
        ):
            raise RuntimeError(
                f"Index fingerprint config.{field} must be a positive integer"
            )
        normalized_config[field] = integer_value

    corpus = payload.get("corpus")
    if not isinstance(corpus, dict):
        raise RuntimeError("Index fingerprint corpus must be an object")
    corpus_digest = _require_sha256(corpus.get("sha256"), "corpus.sha256")
    inputs = corpus.get("inputs")
    if not isinstance(inputs, dict):
        raise RuntimeError("Index fingerprint corpus.inputs must be an object")
    mode = inputs.get("mode")
    if mode == "structural_bundle":
        required_text = ("bundle_file", "source_id", "source_file")
        for field in required_text:
            if not str(inputs.get(field) or "").strip():
                raise RuntimeError(f"corpus.inputs.{field} is required")
        _require_sha256(
            inputs.get("bundle_sha256"),
            "corpus.inputs.bundle_sha256",
        )
        _require_sha256(
            inputs.get("source_sha256"),
            "corpus.inputs.source_sha256",
        )
        unit_count = inputs.get("unit_count")
        if (
            isinstance(unit_count, bool)
            or not isinstance(unit_count, int)
            or unit_count <= 0
        ):
            raise RuntimeError(
                "corpus.inputs.unit_count must be a positive integer"
            )
    elif mode == "prepared_documents":
        if not str(inputs.get("manifest_file") or "").strip():
            raise RuntimeError("corpus.inputs.manifest_file is required")
        _require_sha256(
            inputs.get("manifest_sha256"),
            "corpus.inputs.manifest_sha256",
        )
        documents = inputs.get("documents")
        if not isinstance(documents, list) or not documents:
            raise RuntimeError(
                "corpus.inputs.documents must be a non-empty array"
            )
        for index, document in enumerate(documents):
            if not isinstance(document, dict):
                raise RuntimeError(
                    f"corpus.inputs.documents[{index}] must be an object"
                )
            for field in ("source_id", "prepared_file"):
                if not str(document.get(field) or "").strip():
                    raise RuntimeError(
                        f"corpus.inputs.documents[{index}].{field} is required"
                    )
            _require_sha256(
                document.get("prepared_sha256"),
                f"corpus.inputs.documents[{index}].prepared_sha256",
            )
    else:
        raise RuntimeError(
            "Index fingerprint corpus.inputs.mode must be "
            "structural_bundle or prepared_documents"
        )
    if canonical_json_sha256(inputs) != corpus_digest:
        raise RuntimeError(
            "Index fingerprint corpus.sha256 does not match corpus.inputs"
        )

    return {
        "schema_version": INDEX_FINGERPRINT_SCHEMA_VERSION,
        "status": "ready",
        "workspace": workspace,
        "embedding": {
            "sha256": _require_sha256(payload.get("sha256"), "sha256"),
            "config": normalized_config,
        },
        "corpus": {
            "sha256": corpus_digest,
            "inputs": inputs,
        },
    }


def resolve_index_identity(
    *,
    workspace: str,
    state_dir: Path,
    explicit_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Resolve an immutable index identity for resumable benchmark runs."""
    resolved_workspace = str(workspace or "").strip()
    if not _WORKSPACE_RE.fullmatch(resolved_workspace):
        raise RuntimeError(
            "Workspace must contain only ASCII letters, digits, and underscores"
        )

    explicit = str(explicit_fingerprint or "").strip()
    if explicit:
        if not 8 <= len(explicit) <= 512 or any(
            ord(character) < 32 or ord(character) == 127
            for character in explicit
        ):
            raise RuntimeError(
                "--index-fingerprint must be 8-512 printable characters"
            )
        stable = {
            "workspace": resolved_workspace,
            "immutable_id": explicit,
        }
        return {
            "source": "explicit_remote_id",
            **stable,
            "content_sha256": canonical_json_sha256(stable),
        }

    legacy_path = state_dir / "embedding_fingerprint.json"
    if resolved_workspace == "aeb_demo" and legacy_path.is_file():
        state_path = legacy_path
    else:
        state_path = (
            state_dir
            / f"embedding_fingerprint.{resolved_workspace}.json"
        )
    if not state_path.is_file():
        raise RuntimeError(
            "Missing ready index fingerprint for workspace "
            f"{resolved_workspace!r}: {state_path}. Run verified ingest first, "
            "or pass --index-fingerprint with an immutable remote index ID."
        )
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Invalid index fingerprint file {state_path}: {error}"
        ) from error
    normalized = _validate_index_fingerprint_payload(
        payload,
        workspace=resolved_workspace,
    )
    return {
        "source": "local_ready_state",
        "workspace": resolved_workspace,
        "state_file": state_path.name,
        "content_sha256": canonical_json_sha256(normalized),
        "state": normalized,
    }


def build_run_manifest(
    *,
    runner: str,
    selected_question_ids: Iterable[str],
    modes: Iterable[str],
    configuration: dict[str, Any],
    code_paths: Iterable[Path] = (),
) -> dict[str, Any]:
    code = [
        {
            "path": str(path.relative_to(AEB_ROOT)),
            "sha256": sha256_file(path),
        }
        for path in sorted(set(code_paths))
        if path.is_file()
    ]
    manifest: dict[str, Any] = {
        "format_version": RUN_FORMAT_VERSION,
        "runner": runner,
        "benchmark": benchmark_data_manifest(),
        "selected_question_ids": sorted(set(str(item) for item in selected_question_ids)),
        "modes": list(dict.fromkeys(str(item) for item in modes)),
        "configuration": configuration,
        "code": code,
    }
    manifest["fingerprint"] = canonical_json_sha256(manifest)
    return manifest


def new_run_identity(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        "run_id": str(uuid.uuid4()),
        "run_fingerprint": str(manifest["fingerprint"]),
    }


def validate_result_records(
    records: list[dict[str, Any]],
    *,
    expected_manifest: dict[str, Any] | None = None,
    require_manifest: bool = True,
) -> tuple[str | None, str | None]:
    """Reject duplicate or mixed result rows before resume or scoring."""
    if not records:
        return None, None
    seen: set[tuple[str, str]] = set()
    run_ids: set[str] = set()
    fingerprints: set[str] = set()
    embedded_manifests: list[dict[str, Any]] = []
    for index, record in enumerate(records, 1):
        question_id = str(record.get("question_id", "")).strip()
        mode = str(record.get("mode", "")).strip()
        if not question_id or not mode:
            raise RuntimeError(
                f"Result row {index} lacks non-empty question_id/mode"
            )
        key = (question_id, mode)
        if key in seen:
            raise RuntimeError(
                f"Duplicate result key: question_id={question_id} mode={mode}"
            )
        seen.add(key)
        run_id = str(record.get("run_id", "")).strip()
        fingerprint = str(record.get("run_fingerprint", "")).strip()
        manifest = record.get("run_manifest")
        if run_id:
            run_ids.add(run_id)
        if fingerprint:
            fingerprints.add(fingerprint)
        if require_manifest and (not run_id or not fingerprint):
            raise RuntimeError(
                f"Result row {index} lacks run_id/run_fingerprint"
            )
        if isinstance(manifest, dict):
            embedded_manifests.append(manifest)
            if manifest.get("format_version") != RUN_FORMAT_VERSION:
                raise RuntimeError(
                    f"Result row {index} uses unsupported run_manifest format "
                    f"{manifest.get('format_version')!r}; expected {RUN_FORMAT_VERSION}"
                )
            if canonical_json_sha256(
                {key: value for key, value in manifest.items() if key != "fingerprint"}
            ) != manifest.get("fingerprint"):
                raise RuntimeError(f"Result row {index} has a tampered run_manifest")
            if fingerprint and fingerprint != manifest.get("fingerprint"):
                raise RuntimeError(
                    f"Result row {index} run_fingerprint does not match run_manifest"
                )
            selected_ids = {
                str(item) for item in manifest.get("selected_question_ids", [])
            }
            modes = {str(item) for item in manifest.get("modes", [])}
            if question_id not in selected_ids or mode not in modes:
                raise RuntimeError(
                    f"Result row {index} key {question_id}/{mode} is outside "
                    "its run_manifest selection"
                )
        elif require_manifest:
            raise RuntimeError(
                f"Result row {index} lacks run_manifest; legacy results must be rerun"
            )
    if len(run_ids) > 1 or len(fingerprints) > 1:
        raise RuntimeError(
            f"Mixed benchmark runs detected: run_ids={sorted(run_ids)} "
            f"fingerprints={sorted(fingerprints)}"
        )
    if require_manifest and (not run_ids or not fingerprints):
        raise RuntimeError("Results lack run_id/run_fingerprint")
    if embedded_manifests:
        canonical = canonical_json_sha256(embedded_manifests[0])
        if any(canonical_json_sha256(item) != canonical for item in embedded_manifests[1:]):
            raise RuntimeError("Mixed run_manifest values detected")
    if expected_manifest is not None:
        expected = str(expected_manifest.get("fingerprint", ""))
        actual = next(iter(fingerprints), "")
        if actual != expected:
            raise RuntimeError(
                "Resume configuration does not match the existing run: "
                f"expected={expected} existing={actual}"
            )
    return next(iter(run_ids), None), next(iter(fingerprints), None)


def attach_run_identity(
    record: dict[str, Any],
    *,
    run_id: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    return {
        **record,
        "run_id": run_id,
        "run_fingerprint": manifest["fingerprint"],
        "run_manifest": manifest,
    }


def review_content_sha256(
    question: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, Any]],
) -> str:
    """Bind a human decision to every record that determines its meaning."""
    payload = {
        "question": question,
        "evidence": [
            evidence[item] for item in question.get("gold_evidence_ids", [])
        ],
        "nodes": [nodes[item] for item in question.get("gold_nodes", [])],
        "edges": [edges[item] for item in question.get("gold_edges", [])],
    }
    return canonical_json_sha256(payload)


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\$|\\,|\\text\{([^}]*)\}", r" \1 ", text)
    text = re.sub(r"[\s\u3000]+", "", text)
    text = re.sub(r"[，。；：、,.!?！？;:'\"“”‘’()（）\[\]{}<>《》—–_-]+", "", text)
    return text


def normalize_name(value: Any) -> str:
    text = normalize_text(value)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def char_bigrams(value: Any) -> Counter[str]:
    text = normalize_text(value)
    if len(text) < 2:
        return Counter([text]) if text else Counter()
    return Counter(text[index : index + 2] for index in range(len(text) - 1))


def counter_f1(left: Counter[str], right: Counter[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    overlap = sum((left & right).values())
    precision = overlap / sum(left.values())
    recall = overlap / sum(right.values())
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def claim_similarity(left: Any, right: Any) -> float:
    return counter_f1(char_bigrams(left), char_bigrams(right))


_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?")
_NUMBER_UNIT_RE = re.compile(
    r"(?<![A-Za-z0-9])([-+]?\d+(?:\.\d+)?)\s*"
    r"(km\s*/\s*h|m\s*/\s*s(?:\^?2|²)?|ms|s|秒|m|米|%|％|个月|月|年|次)",
    re.IGNORECASE,
)
_COMPARATORS = (
    (re.compile(r"不小于|至少|>=|≥"), ">="),
    (re.compile(r"不大于|至多|最多|<=|≤"), "<="),
    (re.compile(r"(?<!不)小于|少于|(?<![<>=])<(?![=])"), "<"),
    (re.compile(r"(?<!不)大于|超过|(?<![<>=])>(?![=])"), ">"),
    (re.compile(r"等于|(?<![<>=])=(?![=])"), "="),
)


def semantic_signature(value: Any) -> dict[str, Any]:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    comparison_stripped = re.sub(r"不小于|不大于", "", text)
    negative = bool(
        re.search(
            r"不应|不得|禁止|无需|不能|不允许|不发出|不进行|must\s+not|"
            r"shall\s+not|\bno\b|\bnot\b",
            comparison_stripped,
        )
    )
    positive = bool(
        re.search(
            r"应当|应|必须|需要|允许|发出|进行|must|shall|required",
            comparison_stripped,
        )
    )
    polarity = "negative" if negative else ("positive" if positive else None)
    comparators = {
        canonical
        for pattern, canonical in _COMPARATORS
        if pattern.search(text)
    }
    numbers = {
        str(float(match.group(0))).rstrip("0").rstrip(".")
        for match in _NUMBER_RE.finditer(text)
    }
    number_units = {
        (
            str(float(match.group(1))).rstrip("0").rstrip("."),
            re.sub(r"\s+", "", match.group(2)).replace("％", "%").casefold(),
        )
        for match in _NUMBER_UNIT_RE.finditer(text)
    }
    return {
        "polarity": polarity,
        "comparators": comparators,
        "numbers": numbers,
        "number_units": number_units,
    }


def semantic_conflict(left: Any, right: Any) -> bool:
    """Hard-fail lexical matches that invert obligation or numeric semantics."""
    left_signature = semantic_signature(left)
    right_signature = semantic_signature(right)
    if (
        left_signature["polarity"]
        and right_signature["polarity"]
        and left_signature["polarity"] != right_signature["polarity"]
    ):
        return True
    if (
        left_signature["comparators"]
        and right_signature["comparators"]
        and left_signature["comparators"] != right_signature["comparators"]
    ):
        return True
    if (
        left_signature["numbers"]
        and right_signature["numbers"]
        and left_signature["numbers"] != right_signature["numbers"]
    ):
        return True
    left_units = left_signature["number_units"]
    right_units = right_signature["number_units"]
    if left_units and right_units and left_units != right_units:
        return True
    return False


def precision_recall_f1(
    true_positive: int,
    predicted: int,
    gold: int,
) -> dict[str, float | int]:
    precision = true_positive / predicted if predicted else (1.0 if gold == 0 else 0.0)
    recall = true_positive / gold if gold else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "predicted": predicted,
        "gold": gold,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def index_by_id(records: Iterable[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = str(record.get("id", "")).strip()
        if not record_id:
            raise RuntimeError(f"{label} record lacks id: {record}")
        if record_id in indexed:
            raise RuntimeError(f"Duplicate {label} id: {record_id}")
        indexed[record_id] = record
    return indexed


def _is_scalar_leaf(value: Any) -> bool:
    return not isinstance(value, (dict, list, tuple))


def recursive_normalized_equal(left: Any, right: Any) -> bool:
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left) != set(right):
            return False
        return all(recursive_normalized_equal(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return False
        # Unordered scalar enumerations (e.g. vehicle categories M1/N1).
        if left and all(_is_scalar_leaf(item) for item in left + right):
            def _leaf_key(value: Any) -> str:
                number = safe_float(value)
                if number is not None and not isinstance(value, bool):
                    return f"n:{number}"
                return f"s:{normalize_text(value)}"

            return sorted(_leaf_key(item) for item in left) == sorted(
                _leaf_key(item) for item in right
            )
        return all(recursive_normalized_equal(a, b) for a, b in zip(left, right))
    left_number = safe_float(left)
    right_number = safe_float(right)
    if left_number is not None and right_number is not None:
        return math.isclose(left_number, right_number, abs_tol=1e-9)
    return normalize_text(left) == normalize_text(right)


def set_scores(predicted: Iterable[Any], gold: Iterable[Any]) -> dict[str, Any]:
    predicted_map = {normalize_text(item): item for item in predicted}
    gold_map = {normalize_text(item): item for item in gold}
    matched = set(predicted_map) & set(gold_map)
    scores: dict[str, Any] = precision_recall_f1(
        len(matched),
        len(predicted_map),
        len(gold_map),
    )
    scores["missing"] = [gold_map[key] for key in sorted(set(gold_map) - matched)]
    scores["extra"] = [predicted_map[key] for key in sorted(set(predicted_map) - matched)]
    return scores


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {"raw_text": text}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"raw_text": text}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def find_evidence_in_text(text: str, evidence: Iterable[dict[str, Any]]) -> list[str]:
    normalized = normalize_text(text)
    matches: list[str] = []
    for record in evidence:
        excerpt = normalize_text(record.get("source_excerpt", ""))
        if excerpt and len(excerpt) >= 8 and excerpt in normalized:
            matches.append(record["id"])
            continue
        locator = record.get("locator", {})
        clause = str(locator.get("clause", "")).strip()
        table = str(locator.get("table", "")).strip()
        if clause and normalize_text(f"clause:{clause}") in normalized:
            matches.append(record["id"])
        elif table and normalize_text(f"table:{table}") in normalized:
            matches.append(record["id"])
    return sorted(set(matches))


def question_output_contract(question: dict[str, Any]) -> str:
    method = question["scoring_method"]
    if method == "structured_exact_match":
        keys = list(question["gold_answer"].keys())
        return json.dumps({key: f"<{key}>" for key in keys}, ensure_ascii=False)
    if method == "set_f1":
        return '{"items": ["<item>", "..."], "citations": ["<evidence_id>"]}'
    if method == "claim_f1":
        return '{"claims": ["<atomic claim>", "..."], "citations": ["<evidence_id>"]}'
    if method == "unanswerable":
        return '{"answerable": false, "reason": "<why evidence is insufficient>", "citations": []}'
    raise RuntimeError(f"Unsupported scoring method: {method}")
