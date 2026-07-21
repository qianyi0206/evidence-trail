from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from reg_harness.structure import parse_structure_signals


@dataclass
class IntentResult:
    intent: str
    kb: list[str] = field(default_factory=lambda: ["gb39901"])
    need_graph: bool = False
    need_table: bool = False
    need_clause: bool = False
    tools_prefer: list[str] = field(default_factory=list)
    risk_unanswerable: bool = False
    confidence: float = 0.6
    rationale: str = ""
    policy: str = "complex"
    structure: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_intent(
    question: str,
    explicit_policy: str = "auto",
    *,
    pilot_heuristics: bool = False,
) -> IntentResult:
    """Route a question.

    Default (pilot_heuristics=False): PROTOCOL P1 — structure signals from the
    question only; no pilot tools_prefer playbooks or document-specific scripts.

    pilot_heuristics=True: legacy P2 demo routing (opt-in only).
    """
    if pilot_heuristics:
        return _resolve_intent_pilot(question, explicit_policy)
    return _resolve_intent_generic(question, explicit_policy)


def _resolve_intent_generic(question: str, explicit_policy: str = "auto") -> IntentResult:
    text = question or ""
    kb = ["gb39901"]
    signals = parse_structure_signals(text)
    structure = signals.to_dict()

    need_table = signals.has_table_word or bool(signals.speeds_kmh)
    need_clause = bool(signals.clause_candidates)
    risk = signals.has_existence_cue

    if risk:
        intent = "existence_check"
        policy = "unanswerable_guard"
        rationale = "题干含存在性/是否类线索；应检索核验后再决定拒答或作答。"
        confidence = 0.65
        need_graph = False
    elif need_table and not signals.has_enumeration_cue:
        intent = "table_or_numeric"
        policy = "simple"
        rationale = "题干含表或速度等数值结构信号。"
        confidence = 0.7
        need_graph = False
    elif signals.has_enumeration_cue or signals.has_comparison_cue:
        intent = "synthesis_or_compare"
        policy = "complex"
        rationale = "题干含枚举或比较类过程线索；需多步取证。"
        confidence = 0.65
        need_graph = True
        need_clause = need_clause or True
    else:
        intent = "open"
        policy = "complex"
        rationale = "通用取证；由模型按工具规范自主规划。"
        confidence = 0.55
        need_graph = True

    if explicit_policy and explicit_policy != "auto":
        policy = explicit_policy
        if explicit_policy == "simple":
            need_graph = False
        elif explicit_policy == "complex":
            need_graph = True
        rationale = (rationale or "") + f" | policy覆盖={explicit_policy}"

    # No hard tools_prefer playbook — model chooses from registry catalog.
    return IntentResult(
        intent=intent,
        kb=kb,
        need_graph=need_graph,
        need_table=need_table,
        need_clause=need_clause,
        tools_prefer=[],
        risk_unanswerable=risk,
        confidence=confidence,
        rationale=rationale,
        policy=policy,
        structure=structure,
    )


def _resolve_intent_pilot(question: str, explicit_policy: str = "auto") -> IntentResult:
    """Legacy P2 demo router (document/pilot-oriented). Opt-in only."""
    text = question or ""
    kb = ["gb39901"]
    signals = parse_structure_signals(text)

    if any(
        token in text
        for token in ("是否存在", "有没有规定", "是否规定", "能否从", "是否可以认为")
    ) or (re.search(r"80\s*km", text) and "表" in text):
        return IntentResult(
            intent="unanswerable",
            kb=kb,
            need_graph=False,
            need_table="表" in text,
            need_clause=True,
            tools_prefer=["table_lookup", "vector_search", "evidence_check", "finalize"],
            risk_unanswerable=True,
            confidence=0.75,
            rationale="[pilot] 疑似不可答/对抗前提，优先核验表或条款是否存在。",
            policy="unanswerable_guard",
            structure=signals.to_dict(),
        )

    if "表" in text or (
        "km/h" in text
        and any(token in text for token in ("最大相对碰撞速度", "阈值", "允许"))
    ):
        return IntentResult(
            intent="conditional_table",
            kb=kb,
            need_graph=False,
            need_table=True,
            need_clause=False,
            tools_prefer=["table_lookup", "vector_search", "evidence_check", "compose_answer"],
            risk_unanswerable=False,
            confidence=0.8,
            rationale="[pilot] 表格/数值条件查询，优先 table_lookup。",
            policy="simple",
            structure=signals.to_dict(),
        )

    if any(token in text for token in ("完整列出", "五类", "哪些场景", "共同", "判据")):
        return IntentResult(
            intent="cross_section_synthesis",
            kb=kb,
            need_graph=True,
            need_table=False,
            need_clause=True,
            tools_prefer=[
                "graph_search",
                "clause_lookup",
                "evidence_check",
                "compose_answer",
            ],
            risk_unanswerable=False,
            confidence=0.85,
            rationale="[pilot] 跨条款综合/枚举，需 graph + clause 精查。",
            policy="complex",
            structure=signals.to_dict(),
        )

    if any(token in text for token in ("有何不同", "区别", "如何处理", "例外", "异常")):
        return IntentResult(
            intent="comparison_exception",
            kb=kb,
            need_graph=True,
            need_table=False,
            need_clause=True,
            tools_prefer=["clause_lookup", "graph_search", "evidence_check", "compose_answer"],
            risk_unanswerable=False,
            confidence=0.8,
            rationale="[pilot] 比较/例外题，优先条款精查与图检索。",
            policy="complex",
            structure=signals.to_dict(),
        )

    if any(token in text for token in ("仿真", "可信度", "替代", "还必须", "以及")):
        return IntentResult(
            intent="multi_hop",
            kb=kb,
            need_graph=True,
            need_table=False,
            need_clause=True,
            tools_prefer=["graph_search", "clause_lookup", "evidence_check", "compose_answer"],
            risk_unanswerable=False,
            confidence=0.75,
            rationale="[pilot] 多跳关系题，图检索 + 条款补全。",
            policy="complex",
            structure=signals.to_dict(),
        )

    if any(token in text for token in ("适用于", "定义", "什么是", "何时", "哪些车辆")):
        return IntentResult(
            intent="direct_fact",
            kb=kb,
            need_graph=False,
            need_table=False,
            need_clause=True,
            tools_prefer=["clause_lookup", "vector_search", "evidence_check", "compose_answer"],
            risk_unanswerable=False,
            confidence=0.7,
            rationale="[pilot] 直接事实，条款或向量即可。",
            policy="simple",
            structure=signals.to_dict(),
        )

    if explicit_policy and explicit_policy != "auto":
        base = _resolve_intent_pilot(text, "auto")
        base.policy = explicit_policy
        if explicit_policy == "simple":
            base.need_graph = False
            base.tools_prefer = [
                "vector_search",
                "clause_lookup",
                "evidence_check",
                "compose_answer",
            ]
        elif explicit_policy == "complex":
            base.need_graph = True
            base.tools_prefer = [
                "graph_search",
                "clause_lookup",
                "evidence_check",
                "compose_answer",
            ]
        base.rationale = (base.rationale or "") + f" | policy覆盖={explicit_policy}"
        return base

    return IntentResult(
        intent="other",
        kb=kb,
        need_graph=True,
        need_table=False,
        need_clause=True,
        tools_prefer=["vector_search", "graph_search", "evidence_check", "compose_answer"],
        risk_unanswerable=False,
        confidence=0.5,
        rationale="[pilot] 未命中强规则，默认混合取证。",
        policy="complex",
        structure=signals.to_dict(),
    )
