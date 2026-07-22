from __future__ import annotations

import re
from typing import Any

from reg_harness.types import AgentState, EvidenceItem

# OCR / CN standards often write "1 000" / "2 000" (space or NBSP as thousands sep).
_THOUSANDS_SEP_RE = re.compile(r"(?<=\d)[\s\u00a0,](?=\d{3}(?:\D|$))")


def normalize_numeric_text(text: str) -> str:
    """Collapse spaced/comma thousands so '1 000' and '1000' match."""
    if not text:
        return ""
    prev = None
    cur = text
    # Iterate: "1 000 000" needs multiple passes.
    while prev != cur:
        prev = cur
        cur = _THOUSANDS_SEP_RE.sub("", cur)
    return cur


def collect_context_numbers(items: list[EvidenceItem]) -> set[str]:
    joined = normalize_numeric_text("\n".join(item.text or "" for item in items))
    found: set[str] = set()
    for match in re.findall(r"\d+(?:\.\d+)?", joined):
        found.add(match)
        try:
            value = float(match)
            if value.is_integer():
                found.add(str(int(value)))
        except ValueError:
            pass
    return found


def extract_answer_numbers(value: Any) -> list[str]:
    numbers: list[str] = []
    if isinstance(value, dict):
        for child in value.values():
            numbers.extend(extract_answer_numbers(child))
    elif isinstance(value, list):
        for child in value:
            numbers.extend(extract_answer_numbers(child))
    elif isinstance(value, bool):
        return numbers
    elif isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            numbers.append(str(int(value)))
        else:
            numbers.append(str(value))
    elif isinstance(value, str):
        numbers.extend(re.findall(r"\d+(?:\.\d+)?", normalize_numeric_text(value)))
    return numbers


def invalid_citations(citations: Any, *, evidence_count: int) -> list[str]:
    """Return malformed or out-of-range compose evidence labels."""
    if not isinstance(citations, list) or not citations:
        return ["missing"]
    invalid: list[str] = []
    for citation in citations:
        match = re.fullmatch(r"E([1-9]\d*)", str(citation).strip(), flags=re.IGNORECASE)
        if not match or int(match.group(1)) > evidence_count:
            invalid.append(str(citation))
    return invalid


def validate_final_answer(state: AgentState, prediction: dict[str, Any]) -> dict[str, Any]:
    """Deterministic post-checks (harness observation path)."""
    flags: list[str] = []
    if not isinstance(prediction, dict):
        return {
            "answerable": False,
            "answer": {"answerable": False, "reason": "模型未返回 JSON 对象"},
            "claims": [],
            "citations": [],
            "validation_flags": ["invalid_prediction_type"],
        }

    answerable = prediction.get("answerable")
    if answerable is True and not state.evidence:
        prediction = {
            **prediction,
            "answerable": False,
            "answer": {
                "answerable": False,
                "reason": "证据袋为空，不能给出有依据的法规结论。",
            },
            "claims": [],
            "citations": [],
        }
        flags.append("forced_refusal_empty_evidence")
        answerable = False

    if answerable is True and state.evidence:
        context_numbers = collect_context_numbers(state.evidence)
        unsupported: list[str] = []
        grounded_content = {
            "answer": prediction.get("answer"),
            "claims": prediction.get("claims"),
        }
        for number in extract_answer_numbers(grounded_content):
            if number in context_numbers:
                continue
            try:
                magnitude = float(number)
            except ValueError:
                unsupported.append(number)
                continue
            # Allow pure tiny enumeration indices (0–4); refuse substantive ungrounded numbers.
            if magnitude >= 5:
                unsupported.append(number)
        if unsupported and any(
            float(n) >= 5 for n in unsupported if re.fullmatch(r"\d+(?:\.\d+)?", n)
        ):
            prediction = {
                **prediction,
                "answerable": False,
                "answer": {
                    "answerable": False,
                    "reason": (
                        "答案中的关键数值未出现在证据袋中，已按拒答处理。"
                        f" unsupported={unsupported[:8]}"
                    ),
                },
                "validation_note": "numeric_grounding_failed",
            }
            flags.append("forced_refusal_ungrounded_numeric")
            flags.append("numeric_not_in_context:" + ",".join(unsupported[:8]))

    if answerable is True and state.evidence:
        invalid = invalid_citations(
            prediction.get("citations"), evidence_count=len(state.evidence)
        )
        if invalid:
            prediction = {
                **prediction,
                "answerable": False,
                "answer": {
                    "answerable": False,
                    "reason": (
                        "答案引用未指向证据袋中的有效证据，已按拒答处理。"
                        f" invalid_citations={invalid[:8]}"
                    ),
                    "validation_note": "citation_grounding_failed",
                },
            }
            flags.append("forced_refusal_invalid_citations")
            flags.append("invalid_citations:" + ",".join(invalid[:8]))

    prediction["validation_flags"] = flags
    return prediction
