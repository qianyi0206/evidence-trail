from __future__ import annotations

import re
from typing import Literal

from reg_harness.structure import parse_structure_signals

PolicyName = Literal["auto", "simple", "complex", "unanswerable_guard"]


def infer_policy(
    question: str,
    explicit: str = "auto",
    *,
    pilot_heuristics: bool = False,
) -> PolicyName:
    """Feedforward policy hint.

    Default P1 uses only general process/structure signals from the question.
    pilot_heuristics=True restores legacy keyword mapping (P2 demo).
    """
    if explicit and explicit != "auto":
        if explicit in {"simple", "complex", "unanswerable_guard"}:
            return explicit  # type: ignore[return-value]
        return "complex"

    if pilot_heuristics:
        return _infer_policy_pilot(question)

    signals = parse_structure_signals(question or "")
    if signals.has_existence_cue:
        return "unanswerable_guard"
    if signals.has_enumeration_cue or signals.has_comparison_cue:
        return "complex"
    if signals.has_table_word and not signals.has_enumeration_cue:
        return "simple"
    if re.search(r"\d+\.\d+", question or "") and any(
        token in (question or "") for token in ("试验", "场景", "判据", "要求", "条款")
    ):
        return "complex"
    return "complex"


def _infer_policy_pilot(question: str) -> PolicyName:
    text = question or ""
    if any(
        token in text
        for token in ("是否存在", "有没有规定", "是否规定", "能否从", "是否可以认为")
    ):
        return "unanswerable_guard"
    if any(
        token in text
        for token in ("完整列出", "哪些", "分别", "有何不同", "如何处理", "多跳", "以及")
    ):
        return "complex"
    if re.search(r"\d+\.\d+", text) and any(
        token in text for token in ("试验", "场景", "判据", "要求")
    ):
        return "complex"
    if any(token in text for token in ("表", "km/h", "最大相对碰撞速度", "适用于")):
        return "simple"
    return "complex"


def preferred_retrieve_modes(policy: PolicyName | str) -> list[str]:
    if policy == "simple":
        return ["naive", "hybrid"]
    if policy == "unanswerable_guard":
        return ["naive", "hybrid"]
    return ["hybrid", "mix", "naive"]
