from __future__ import annotations

import hashlib
import html
import json
import math
import re
import unicodedata
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
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    temp.replace(path)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    scores = precision_recall_f1(len(matched), len(predicted_map), len(gold_map))
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
