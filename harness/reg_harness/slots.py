from __future__ import annotations

from typing import Any

from reg_harness.structure import parse_structure_signals
from reg_harness.types import EvidenceItem, Slot


# Pilot-only answer cues that must not appear as slot keywords unless present in the question.
_PILOT_ANSWER_CUES = (
    "铁板",
    "行人",
    "自行车",
    "右转",
    "邻道",
    "6.11",
    "5.4",
    "6.5",
    "6.10",
    "6.13",
)


def build_slots(
    question: str,
    policy: str,
    *,
    pilot_heuristics: bool = False,
) -> list[Slot]:
    """Build gap checklist.

    Default P1: gap *types* with keywords derived from the question text only.
    pilot_heuristics=True: legacy P2 slots that may inject document-specific cues.
    """
    if pilot_heuristics:
        return _build_slots_pilot(question, policy)
    return _build_slots_generic(question, policy)


def _build_slots_generic(question: str, policy: str) -> list[Slot]:
    text = question or ""
    signals = parse_structure_signals(text)
    # Keywords only from tokens that appear in the question (or parsed from it).
    q_tokens = list(signals.question_tokens)
    slots: list[Slot] = []

    if signals.has_enumeration_cue:
        slots.append(
            Slot(
                id="list_items",
                description="枚举/列表项是否在证据中有支撑",
                keywords=q_tokens[:12],
                hint_query=text[:120],
            )
        )

    if signals.has_comparison_cue:
        slots.append(
            Slot(
                id="compare_or_exception",
                description="比较双方或例外条件",
                keywords=q_tokens[:12],
                hint_query=text[:120],
            )
        )

    if signals.has_table_word or signals.speeds_kmh or "km/h" in text or "速度" in text:
        cond_kw = (
            signals.vehicle_categories
            + signals.speeds_kmh
            + signals.table_candidates
            + [t for t in q_tokens if t not in signals.vehicle_categories][:8]
        )
        slots.append(
            Slot(
                id="conditions",
                description="题干条件（车型/速度/表/载荷等，仅来自题干）",
                keywords=_unique(cond_kw)[:16],
                hint_query=text,
            )
        )
        slots.append(
            Slot(
                id="threshold_or_cell",
                description="所问阈值或表格单元",
                keywords=_unique(signals.speeds_kmh + signals.table_candidates + q_tokens[:8])[
                    :12
                ],
                hint_query=text,
            )
        )

    if signals.has_existence_cue or policy == "unanswerable_guard":
        slots.append(
            Slot(
                id="existence",
                description="题干条件组合在源中是否存在",
                keywords=q_tokens[:10],
                hint_query=text,
            )
        )

    if not slots:
        slots.append(
            Slot(
                id="main_fact",
                description="问题直接询问的事实",
                keywords=q_tokens[:12] or [text[:40]],
                hint_query=text,
            )
        )

    anchor_kw = list(signals.clause_candidates)
    if not anchor_kw:
        # Generic locator morphology only — not a specific clause number.
        anchor_kw = [t for t in ("条款", "source_clause", "来源条款") if True]
    slots.append(
        Slot(
            id="source_anchor",
            description="出处定位（条款/表/文件）",
            keywords=anchor_kw[:8],
            hint_query=text,
        )
    )
    return slots


def _build_slots_pilot(question: str, policy: str) -> list[Slot]:
    """Legacy P2 checklist with document-oriented keywords. Opt-in only."""
    import re

    text = question or ""
    slots: list[Slot] = []

    if any(token in text for token in ("完整列出", "五类", "哪些场景", "分别有哪些")):
        slots.append(
            Slot(
                id="scenario_list",
                description="完整场景/条目列表（枚举项）",
                keywords=["误响应", "试验", "场景", "6.11", "右转", "铁板", "行人", "自行车"],
                hint_query="6.11 误响应试验 五类场景 列表",
            )
        )
        if any(token in text for token in ("判据", "合格", "准则", "要求")):
            slots.append(
                Slot(
                    id="acceptance",
                    description="共同合格判据/接受准则",
                    keywords=["不发出", "碰撞预警", "紧急制动", "5.4", "判据", "接受"],
                    hint_query="5.4 系统误响应 不应发出碰撞预警和紧急制动 6.11",
                )
            )
        return slots

    if any(token in text for token in ("有何不同", "区别", "如何处理", "例外", "异常")):
        slots.append(
            Slot(
                id="compare_a",
                description="对比对象 A 的条件/要求",
                keywords=["6.5", "6.10", "行车质量", "载荷"],
                hint_query=text[:80] + " 第一组条件",
            )
        )
        slots.append(
            Slot(
                id="compare_b",
                description="对比对象 B 的条件/要求",
                keywords=["6.11", "6.13", "最大设计总质量", "载荷"],
                hint_query=text[:80] + " 第二组条件",
            )
        )
        slots.append(
            Slot(
                id="exception_rule",
                description="例外/替代处理规则",
                keywords=["若", "大于", "替代", "例外", "异常"],
                hint_query="行车质量大于最大设计总质量 如何处理 替代",
            )
        )
        return slots

    if "表" in text or "km/h" in text or "速度" in text:
        slots.append(
            Slot(
                id="conditions",
                description="题干条件：车型/场景/速度/载荷",
                keywords=_extract_condition_keywords_pilot(text),
                hint_query=text,
            )
        )
        slots.append(
            Slot(
                id="threshold",
                description="目标阈值或单元格数值",
                keywords=["最大相对碰撞速度", "km/h", "阈值", "不大于"],
                hint_query=text + " 最大相对碰撞速度",
            )
        )
        if policy == "unanswerable_guard" or any(
            token in text for token in ("80", "是否", "有没有")
        ):
            slots.append(
                Slot(
                    id="existence",
                    description="该条件组合在表中是否存在",
                    keywords=["没有", "未规定", "不适用", "至少", "范围"],
                    hint_query=text + " 是否有对应试验行",
                )
            )
        return slots

    if any(token in text for token in ("仿真", "可信度", "替代", "以及", "还必须")):
        slots.append(
            Slot(
                id="scope",
                description="可替代/适用范围条款",
                keywords=["6.5", "6.6", "6.7", "6.8", "6.9", "6.10", "仿真", "替代"],
                hint_query="碰撞预警 紧急制动 仿真替代 6.5 6.10",
            )
        )
        slots.append(
            Slot(
                id="extra_requirement",
                description="附加要求（如可信度维度）",
                keywords=["可信度", "能力", "准确性", "正确性", "适用性", "可用性", "附录B"],
                hint_query="仿真工具链 可信度 能力 准确性 正确性 适用性 可用性",
            )
        )
        return slots

    slots.append(
        Slot(
            id="main_fact",
            description="问题直接询问的事实",
            keywords=_extract_condition_keywords_pilot(text) or ["GB", "39901"],
            hint_query=text,
        )
    )
    slots.append(
        Slot(
            id="source_anchor",
            description="条款/出处锚点",
            keywords=["条款", "source_clause", "第"],
            hint_query=text + " 条款",
        )
    )
    return slots


def _extract_condition_keywords_pilot(text: str) -> list[str]:
    import re

    keys: list[str] = []
    for match in re.findall(r"\b([MN]\d)\b", text, flags=re.IGNORECASE):
        keys.append(match.upper())
    for match in re.findall(r"(\d+(?:\.\d+)?)\s*km\s*/\s*h", text, flags=re.IGNORECASE):
        keys.append(match)
    for phrase in ("最大设计总质量", "行车质量", "静止车辆", "匀速", "误响应", "M1", "N1"):
        if phrase in text:
            keys.append(phrase)
    return keys


def refresh_slots(slots: list[Slot], evidence: list[EvidenceItem]) -> list[Slot]:
    """Update slot status from current evidence bag (keyword coverage)."""
    if not evidence:
        for slot in slots:
            slot.status = "missing"
        return slots

    blob = "\n".join(item.text for item in evidence)
    for slot in slots:
        if not slot.keywords:
            slot.status = "partial" if evidence else "missing"
            continue
        hits = sum(1 for keyword in slot.keywords if keyword and keyword in blob)
        ratio = hits / max(1, len(slot.keywords))
        if ratio >= 0.45 or hits >= 3:
            slot.status = "covered"
        elif hits >= 1:
            slot.status = "partial"
        else:
            slot.status = "missing"
    return slots


def slot_summary(slots: list[Slot]) -> dict[str, Any]:
    missing = [slot for slot in slots if slot.status == "missing"]
    partial = [slot for slot in slots if slot.status == "partial"]
    covered = [slot for slot in slots if slot.status == "covered"]
    suggested = []
    for slot in missing + partial:
        if slot.hint_query:
            prefer = (
                "graph_search"
                if slot.id
                in {
                    "list_items",
                    "scenario_list",
                    "acceptance",
                    "scope",
                    "extra_requirement",
                    "compare_or_exception",
                }
                else "vector_search"
            )
            suggested.append(
                {
                    "slot_id": slot.id,
                    "suggested_query": slot.hint_query,
                    "prefer_tool": prefer,
                }
            )
    return {
        "covered": [slot.id for slot in covered],
        "partial": [slot.id for slot in partial],
        "missing": [slot.id for slot in missing],
        "all_covered": not missing and not partial and bool(slots),
        "ready_for_answer": not missing and bool(evidence_nonempty_hint(slots, covered)),
        "suggested_next": suggested[:4],
        "slots": [slot.to_dict() for slot in slots],
    }


def evidence_nonempty_hint(slots: list[Slot], covered: list[Slot]) -> bool:
    return bool(covered) or any(slot.status != "missing" for slot in slots)


def pilot_answer_cues_in_keywords(slots: list[Slot], question: str) -> list[str]:
    """Return pilot answer cues used as keywords but absent from the question (for tests)."""
    text = question or ""
    bad: list[str] = []
    for slot in slots:
        for keyword in slot.keywords:
            if keyword in _PILOT_ANSWER_CUES and keyword not in text:
                bad.append(keyword)
    return bad


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
