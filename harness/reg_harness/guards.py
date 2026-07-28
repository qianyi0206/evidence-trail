from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable

from reg_harness.types import AgentState, EvidenceItem

# OCR / CN standards often write "1 000" / "2 000" (space or NBSP as thousands sep).
_THOUSANDS_SEP_RE = re.compile(r"(?<=\d)[\s\u00a0,](?=\d{3}(?:\D|$))")
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)*(?!\d)")
_CITATION_RE = re.compile(r"E([1-9]\d*)", flags=re.IGNORECASE)

_UNIT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("km/h", re.compile(r"(?:km\s*/\s*h|千米\s*/?\s*(?:小时|时))", re.I)),
    (
        "m/s2",
        re.compile(r"(?:m\s*/\s*s(?:²|2|\^2)|米\s*/?\s*秒(?:²|2|\^2))", re.I),
    ),
    ("m/s", re.compile(r"(?:m\s*/\s*s|米\s*/?\s*秒)", re.I)),
    ("ms", re.compile(r"(?:ms|毫秒)", re.I)),
    ("s", re.compile(r"(?:秒|(?<![A-Za-z])s(?![A-Za-z]))", re.I)),
    ("lx", re.compile(r"(?:lx|勒克斯)", re.I)),
    ("mm", re.compile(r"(?:mm|毫米)", re.I)),
    ("cm", re.compile(r"(?:cm|厘米)", re.I)),
    ("km", re.compile(r"(?:km|千米|公里)", re.I)),
    ("m", re.compile(r"(?:米|(?<![A-Za-z])m(?![A-Za-z]))", re.I)),
    ("kg", re.compile(r"(?:kg|千克|公斤)", re.I)),
    ("kn", re.compile(r"(?:kN|千牛)", re.I)),
    ("n", re.compile(r"(?:牛顿|(?<![A-Za-z])N(?![A-Za-z]))")),
    ("percent", re.compile(r"(?:%|％|百分比|百分之)", re.I)),
    ("celsius", re.compile(r"(?:℃|°\s*C|摄氏度)", re.I)),
    ("hz", re.compile(r"(?:Hz|赫兹)", re.I)),
)

_OPERATOR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("min", re.compile(r"不小于|不低于|至少|最低|≥|>=")),
    ("max", re.compile(r"不大于|不高于|不超过|不得超过|至多|最多|最大|≤|<=")),
    ("lt", re.compile(r"(?<!不)小于|低于|(?<![=<])<(?![=])")),
    ("gt", re.compile(r"(?<!不)大于|高于|(?<![=>])>(?![=])")),
    ("deadline", re.compile(r"不迟于|最迟")),
    ("equal", re.compile(r"等于|恰为|固定为")),
)

_MODALITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "forbid",
        re.compile(r"不应|不得|禁止|不允许|无需|不需要|不能|未发出|未触发|未启动|没有"),
    ),
    ("require", re.compile(r"(?<!不)应当|(?<!不)应|必须|需要")),
    ("permit", re.compile(r"可以|允许|可采用|可调整")),
)
_NEGATIVE_POLARITY_RE = re.compile(
    r"不应|不得|禁止|不允许|无需|不需要|不能|未发出|未触发|未启动|没有"
)
_SUBSTANCE_STOP_TERMS = (
    "本标准",
    "系统",
    "车辆",
    "试验",
    "规定",
    "要求",
    "应当",
    "不应",
    "不得",
    "必须",
    "可以",
    "允许",
    "需要",
)

_CONDITION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![A-Za-z0-9])[MN]\d(?![A-Za-z0-9])", re.I),
    re.compile(r"(?<![A-Za-z0-9])TTC(?![A-Za-z0-9])", re.I),
    re.compile(r"最大设计总质量|整备质量|满载|空载|加载状态|载荷状态"),
    re.compile(r"静止(?:车辆)?目标|运动(?:车辆)?目标|自行车|行人|两轮车"),
    re.compile(r"直线|左转|右转|白天|夜间|干燥|湿滑"),
)
_DIMENSION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "acceleration",
        re.compile(r"加速度|减速度|\b(?:acceleration|deceleration)\b", re.I),
    ),
    ("speed", re.compile(r"速度|车速|相对碰撞速度|\b(?:speed|velocity)\b", re.I)),
    (
        "time",
        re.compile(r"TTC|时间|时长|延迟|不迟于|最迟|\b(?:time|duration|delay)\b", re.I),
    ),
    ("illuminance", re.compile(r"光照|照度|\b(?:illuminance|lux)\b", re.I)),
    (
        "distance",
        re.compile(r"距离|长度|宽度|高度|尺寸|\b(?:distance|length|width|height)\b", re.I),
    ),
    ("mass", re.compile(r"质量|载荷|\b(?:mass|load)\b", re.I)),
)
_DIMENSION_UNITS: dict[str, frozenset[str]] = {
    "speed": frozenset({"km/h", "m/s"}),
    "time": frozenset({"ms", "s"}),
    "illuminance": frozenset({"lx"}),
    "acceleration": frozenset({"m/s2"}),
    "distance": frozenset({"mm", "cm", "m", "km"}),
    "mass": frozenset({"kg"}),
}

_INDEX_KEYS = frozenset(
    {
        "index",
        "item_index",
        "ordinal",
        "order",
        "序号",
        "编号索引",
        "列表序号",
    }
)


@dataclass(frozen=True)
class NumericFact:
    raw: str
    number: str
    unit: str | None
    dimension: str | None
    identifier: bool
    operators: frozenset[str]
    conditions: frozenset[str]


def normalize_numeric_text(text: str) -> str:
    """Collapse spaced/comma thousands so '1 000' and '1000' match."""
    if not text:
        return ""
    prev = None
    cur = str(text)
    # Iterate: "1 000 000" needs multiple passes.
    while prev != cur:
        prev = cur
        cur = _THOUSANDS_SEP_RE.sub("", cur)
    return cur


def _canonical_number(raw: str) -> str:
    value = raw.strip().lstrip("+")
    # Clause identifiers such as 6.11.3 are not decimal numbers.
    if value.count(".") > 1:
        return value
    try:
        number = float(value)
    except ValueError:
        return value
    if not math.isfinite(number):
        return value
    return str(int(number)) if number.is_integer() else format(number, ".15g")


def collect_context_numbers(items: list[EvidenceItem]) -> set[str]:
    """Backward-compatible bag-wide numeric inventory used by diagnostics."""
    joined = normalize_numeric_text("\n".join(item.text or "" for item in items))
    return {_canonical_number(match.group(0)) for match in _NUMBER_RE.finditer(joined)}


def extract_answer_numbers(value: Any) -> list[str]:
    """Backward-compatible recursive numeric extraction."""
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
        numbers.append(_canonical_number(str(value)))
    elif isinstance(value, str):
        numbers.extend(
            _canonical_number(match.group(0))
            for match in _NUMBER_RE.finditer(normalize_numeric_text(value))
        )
    return numbers


def _unit_in_text(text: str) -> str | None:
    for canonical, pattern in _UNIT_PATTERNS:
        if pattern.search(text):
            return canonical
    return None


def _operators(text: str) -> frozenset[str]:
    return frozenset(name for name, pattern in _OPERATOR_PATTERNS if pattern.search(text))


def _modalities(text: str) -> frozenset[str]:
    return frozenset(name for name, pattern in _MODALITY_PATTERNS if pattern.search(text))


def _conditions(text: str) -> frozenset[str]:
    found: set[str] = set()
    for pattern in _CONDITION_PATTERNS:
        for match in pattern.finditer(text):
            found.add(match.group(0).strip().lower())
    return frozenset(found)


def _dimension(text: str, *, anchor: int | None = None) -> str | None:
    nearest: tuple[int, str] | None = None
    anchor = len(text) // 2 if anchor is None else anchor
    for name, pattern in _DIMENSION_PATTERNS:
        for match in pattern.finditer(text):
            distance = min(abs(match.start() - anchor), abs(match.end() - anchor))
            if nearest is None or distance < nearest[0]:
                nearest = (distance, name)
    return nearest[1] if nearest else None


def _looks_like_enumeration(text: str, match: re.Match[str]) -> bool:
    raw = match.group(0)
    if "." in raw or raw.startswith(("+", "-")):
        return False
    suffix = text[match.end() : match.end() + 2]
    if not re.match(r"\s*[、.)）]", suffix):
        return False
    prefix = text[max(0, match.start() - 2) : match.start()]
    return match.start() == 0 or not prefix or prefix[-1] in "\n\r\t ；;"


def _looks_like_identifier(text: str, match: re.Match[str]) -> bool:
    raw = re.escape(match.group(0))
    window = text[max(0, match.start() - 10) : match.end() + 10]
    if match.group(0).count(".") > 1:
        return True
    return bool(
        re.search(
            rf"(?:表|图|附录|条款|第)\s*{raw}|{raw}\s*(?:条|款|节|规定)",
            window,
        )
    )


def _fact_context_bounds(text: str, match: re.Match[str]) -> tuple[int, int]:
    """Keep number/condition binding inside one source sentence or table row."""
    left = max(0, match.start() - 96)
    right = min(len(text), match.end() + 96)
    for delimiter in "\n\r；;。":
        previous = text.rfind(delimiter, left, match.start())
        if previous >= 0:
            left = max(left, previous + 1)
        following = text.find(delimiter, match.end(), right)
        if following >= 0:
            right = min(right, following)
    return left, right


def extract_numeric_facts(text: str) -> list[NumericFact]:
    """Extract number, unit and nearby applicability conditions from one claim."""
    normalized = normalize_numeric_text(text)
    matches = list(_NUMBER_RE.finditer(normalized))
    only_unit = _unit_in_text(normalized) if len(matches) == 1 else None
    facts: list[NumericFact] = []
    for match in matches:
        if _looks_like_enumeration(normalized, match):
            continue
        context_start, context_end = _fact_context_bounds(normalized, match)
        window = normalized[context_start:context_end]
        near_start = max(context_start, match.start() - 32)
        near_end = min(context_end, match.end() + 32)
        near = normalized[near_start:near_end]
        after = normalized[match.end() : match.end() + 24]
        identifier = _looks_like_identifier(normalized, match)
        facts.append(
            NumericFact(
                raw=match.group(0),
                number=_canonical_number(match.group(0)),
                unit=_unit_in_text(after) or only_unit,
                dimension=(
                    None
                    if identifier
                    else _dimension(near, anchor=match.start() - near_start)
                ),
                identifier=identifier,
                operators=_operators(near),
                conditions=_conditions(window),
            )
        )
    return facts


def _answer_segments(value: Any, *, path: tuple[str, ...] = ()) -> list[str]:
    """Flatten an answer while retaining sibling condition/unit context."""
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, dict):
        segments: list[str] = []
        for key, child in value.items():
            child_path = (*path, str(key))
            if (
                str(key).strip().lower() in _INDEX_KEYS
                and isinstance(child, int)
                and not isinstance(child, bool)
            ):
                continue
            sibling_context = " ".join(
                f"{sibling_key}={sibling}"
                for sibling_key, sibling in value.items()
                if sibling_key != key
                and isinstance(sibling, (str, int, float))
                and not isinstance(sibling, bool)
                and not extract_numeric_facts(str(sibling))
            )
            child_segments = _answer_segments(child, path=child_path)
            for segment in child_segments:
                segments.append(
                    f"{'/'.join(child_path)} {segment} {sibling_context}".strip()
                )
        return segments
    if isinstance(value, list):
        return [
            segment
            for child in value
            for segment in _answer_segments(child, path=path)
        ]
    return [str(value)]


def invalid_citations(
    citations: Any,
    *,
    valid_labels: Iterable[str] | None = None,
    evidence_count: int | None = None,
) -> list[str]:
    """Return malformed labels or labels absent from the actual rendered prompt."""
    if not isinstance(citations, list) or not citations:
        return ["missing"]
    if valid_labels is None:
        valid = (
            {f"E{index}" for index in range(1, evidence_count + 1)}
            if evidence_count is not None
            else set()
        )
    else:
        valid = {str(label).strip().upper() for label in valid_labels}
    invalid: list[str] = []
    for citation in citations:
        raw = str(citation).strip()
        match = _CITATION_RE.fullmatch(raw)
        if not match or raw.upper() not in valid:
            invalid.append(raw)
    return invalid


def final_answer_contract_errors(prediction: Any) -> list[str]:
    """Validate the positive/refusal result contract without mutating it."""
    if not isinstance(prediction, dict):
        return ["prediction_not_object"]
    answerable = prediction.get("answerable")
    if type(answerable) is not bool:  # bool is intentionally exact, not truthy.
        return ["answerable_must_be_boolean"]

    answer = prediction.get("answer")
    claims = prediction.get("claims")
    citations = prediction.get("citations")
    errors: list[str] = []

    if answerable:
        if not isinstance(answer, dict) or not answer:
            errors.append("positive_answer_must_be_nonempty_object")
        elif answer.get("answerable") is False:
            errors.append("conflicting_nested_answerable")
        if not isinstance(claims, list) or not claims:
            errors.append("positive_claims_must_be_nonempty_array")
        elif any(not isinstance(claim, str) or not claim.strip() for claim in claims):
            errors.append("claims_must_be_nonempty_strings")
        if not isinstance(citations, list) or not citations:
            errors.append("positive_citations_must_be_nonempty_array")
    else:
        if not isinstance(claims, list) or claims:
            errors.append("refusal_claims_must_be_empty")
        if not isinstance(citations, list) or citations:
            errors.append("refusal_citations_must_be_empty")
        answer_reason = answer.get("reason") if isinstance(answer, dict) else None
        reason = prediction.get("reason") or answer_reason
        if not isinstance(reason, str) or not reason.strip():
            errors.append("refusal_reason_required")
        if answer is not None and not isinstance(answer, dict):
            errors.append("refusal_answer_must_be_object")
        elif isinstance(answer, dict) and answer.get("answerable") is True:
            errors.append("conflicting_nested_answerable")
    return errors


def _force_refusal(
    prediction: dict[str, Any],
    *,
    reason: str,
    flags: list[str],
    note: str,
) -> dict[str, Any]:
    output = dict(prediction)
    output.update(
        {
            "answerable": False,
            "answer": {"answerable": False, "reason": reason},
            "claims": [],
            "citations": [],
            "validation_note": note,
            "validation_flags": flags,
        }
    )
    return output


def _numeric_fact_supported(fact: NumericFact, item: EvidenceItem) -> bool:
    # Numeric conclusions must come from source text, not graph summaries.
    if item.kind not in {"chunk", "catalog"}:
        return False
    if fact.dimension and not fact.unit and not fact.identifier:
        # A dimensional answer without a unit is ambiguous even if the magnitude
        # happens to occur in the citation.
        return False
    for candidate in extract_numeric_facts(item.text or ""):
        if candidate.number != fact.number:
            continue
        if fact.unit and candidate.unit != fact.unit:
            continue
        if fact.dimension:
            allowed_units = _DIMENSION_UNITS.get(fact.dimension, frozenset())
            if candidate.dimension != fact.dimension:
                continue
            if allowed_units and candidate.unit not in allowed_units:
                continue
        if fact.operators and not (fact.operators & candidate.operators):
            continue
        if fact.conditions and not fact.conditions.issubset(candidate.conditions):
            continue
        return True
    return False


def _claim_substance(text: str) -> str:
    value = normalize_numeric_text(text).lower()
    value = _NUMBER_RE.sub("", value)
    for _, pattern in _UNIT_PATTERNS:
        value = pattern.sub("", value)
    for term in _SUBSTANCE_STOP_TERMS:
        value = value.replace(term, "")
    return re.sub(r"[^a-z\u4e00-\u9fff]+", "", value)


def _char_bigrams(text: str) -> set[str]:
    if len(text) < 2:
        return {text} if text else set()
    return {text[index : index + 2] for index in range(len(text) - 1)}


def _qualitative_claim_supported(claim: str, cited_items: list[EvidenceItem]) -> bool:
    substance = _claim_substance(claim)
    if not substance:
        return True
    claim_modalities = _modalities(claim)
    claim_negative = bool(_NEGATIVE_POLARITY_RE.search(claim))
    claim_conditions = _conditions(claim)
    claim_grams = _char_bigrams(substance)
    for item in cited_items:
        if item.kind not in {"chunk", "catalog"}:
            continue
        evidence_segments = [
            segment.strip()
            for segment in re.split(r"[\n\r。；;]+", item.text or "")
            if segment.strip()
        ] or [item.text or ""]
        for evidence in evidence_segments:
            if claim_modalities and not (claim_modalities & _modalities(evidence)):
                continue
            if claim_negative != bool(_NEGATIVE_POLARITY_RE.search(evidence)):
                continue
            if claim_conditions and not claim_conditions.issubset(
                _conditions(evidence)
            ):
                continue
            evidence_substance = _claim_substance(evidence)
            if substance in evidence_substance:
                return True
            if not claim_grams:
                return True
            overlap = len(
                claim_grams & _char_bigrams(evidence_substance)
            ) / len(claim_grams)
            if overlap >= 0.35:
                return True
    return False


def _grounding_failures(
    prediction: dict[str, Any], cited_items: list[EvidenceItem]
) -> tuple[list[str], list[str]]:
    unsupported_numbers: list[str] = []
    unsupported_claims: list[str] = []

    claims = prediction.get("claims") or []
    for index, claim in enumerate(claims, 1):
        facts = extract_numeric_facts(claim)
        if any(
            not any(_numeric_fact_supported(fact, item) for item in cited_items)
            for fact in facts
        ):
            unsupported_numbers.extend(
                fact.raw
                for fact in facts
                if not any(_numeric_fact_supported(fact, item) for item in cited_items)
            )
            unsupported_claims.append(f"claim[{index}]")
            continue
        if not _qualitative_claim_supported(claim, cited_items):
            unsupported_claims.append(f"claim[{index}]")

    for segment in _answer_segments(prediction.get("answer")):
        for fact in extract_numeric_facts(segment):
            if not any(_numeric_fact_supported(fact, item) for item in cited_items):
                unsupported_numbers.append(fact.raw)

    return (
        list(dict.fromkeys(unsupported_numbers)),
        list(dict.fromkeys(unsupported_claims)),
    )


def validate_final_answer(state: AgentState, prediction: Any) -> dict[str, Any]:
    """Apply deterministic contract, citation and claim-level grounding checks."""
    if not isinstance(prediction, dict):
        return _force_refusal(
            {},
            reason="模型未返回 JSON 对象。",
            flags=[
                "forced_refusal_invalid_contract",
                "contract:prediction_not_object",
            ],
            note="final_answer_contract_failed",
        )

    answerable = prediction.get("answerable")
    if answerable is True and not state.evidence:
        return _force_refusal(
            prediction,
            reason="证据袋为空，不能给出有依据的法规结论。",
            flags=["forced_refusal_empty_evidence"],
            note="empty_evidence",
        )

    contract_errors = final_answer_contract_errors(prediction)
    if contract_errors:
        return _force_refusal(
            prediction,
            reason="最终答案不符合结构化输出契约，已拒绝结束。",
            flags=[
                "forced_refusal_invalid_contract",
                *[f"contract:{error}" for error in contract_errors],
            ],
            note="final_answer_contract_failed",
        )

    # Normalize a valid refusal into one stable shape.
    if answerable is False:
        answer = prediction.get("answer")
        reason = str(
            prediction.get("reason")
            or (answer.get("reason") if isinstance(answer, dict) else "")
        ).strip()
        output = dict(prediction)
        output["answer"] = {
            **(answer if isinstance(answer, dict) else {}),
            "answerable": False,
            "reason": reason,
        }
        output["claims"] = []
        output["citations"] = []
        output["validation_flags"] = []
        return output

    render = state.render_evidence(for_compose=True)
    invalid = invalid_citations(
        prediction.get("citations"),
        valid_labels=render.labels,
    )
    if invalid:
        return _force_refusal(
            prediction,
            reason=(
                "答案引用未指向实际提供给作答模型的证据，已按拒答处理。"
                f" invalid_citations={invalid[:8]}"
            ),
            flags=[
                "forced_refusal_invalid_citations",
                "invalid_citations:" + ",".join(invalid[:8]),
            ],
            note="citation_grounding_failed",
        )

    by_label = render.by_label()
    cited_items = [
        by_label[str(label).strip().upper()]
        for label in prediction.get("citations") or []
    ]
    unsupported_numbers, unsupported_claims = _grounding_failures(
        prediction, cited_items
    )
    if unsupported_numbers or unsupported_claims:
        flags: list[str] = []
        if unsupported_numbers:
            flags.extend(
                [
                    "forced_refusal_ungrounded_numeric",
                    "numeric_not_in_citations:" + ",".join(unsupported_numbers[:8]),
                ]
            )
        if unsupported_claims:
            flags.extend(
                [
                    "forced_refusal_ungrounded_claims",
                    "claims_not_supported:" + ",".join(unsupported_claims[:8]),
                ]
            )
        return _force_refusal(
            prediction,
            reason=(
                "答案声明未被其引用的原文逐项支撑，已按拒答处理。"
                f" numbers={unsupported_numbers[:8]}"
                f" claims={unsupported_claims[:8]}"
            ),
            flags=flags,
            note="claim_grounding_failed",
        )

    output = dict(prediction)
    output["validation_flags"] = []
    return output
