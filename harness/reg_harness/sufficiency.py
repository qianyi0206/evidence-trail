"""Post-retrieve sufficiency audit: did the bag already answer the question?

This is the missing "audit" beat after plan → execute. Heuristic and
deterministic — not another free-form LLM guess — so the loop can force
compose when the bag is good enough and stop retrieval spin.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from reg_harness.bag_gaps import (
    analyze_bag_gaps,
    bag_blob,
    missing_question_clauses,
    unresolved_table_refs,
)
from reg_harness.types import EvidenceItem

# "列出五类 / 三类" style enumeration asks.
_ENUM_COUNT_RE = re.compile(r"([一二三四五六七八九十两\d]+)\s*类")
_CN_NUM = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _parse_enum_count(question: str) -> int | None:
    match = _ENUM_COUNT_RE.search(question or "")
    if not match:
        return None
    token = match.group(1)
    if token.isdigit():
        return int(token)
    return _CN_NUM.get(token)


def _clause_hits_in_bag(question: str, blob: str) -> dict[str, bool]:
    """Which clause tokens from the question appear in the bag."""
    from reg_harness.bag_gaps import question_clause_candidates

    hits: dict[str, bool] = {}
    for clause in question_clause_candidates(question):
        hits[clause] = bool(
            re.search(rf"(?<![\d.]){re.escape(clause)}(?![\d.])", blob)
        )
    return hits


@dataclass
class SufficiencyAudit:
    """Result of one post-execute bag audit."""

    sufficient: bool
    reason: str
    evidence_count: int
    chunk_count: int
    missing_clauses: list[str] = field(default_factory=list)
    unresolved_tables: list[str] = field(default_factory=list)
    clause_hits: dict[str, bool] = field(default_factory=dict)
    enum_target: int | None = None
    hard_gaps: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def observation_block(self) -> str:
        status = "足够" if self.sufficient else "可能不足"
        lines = [
            f"\n【取证审核 sufficiency】结论={status}；{self.reason}",
            f"袋内 evidence={self.evidence_count} chunk={self.chunk_count}",
        ]
        if self.clause_hits:
            hit_s = ", ".join(
                f"{c}={'有' if ok else '缺'}" for c, ok in sorted(self.clause_hits.items())
            )
            lines.append(f"题干条款覆盖: {hit_s}")
        if self.missing_clauses:
            lines.append(f"仍缺题干条款: {self.missing_clauses}")
        if self.unresolved_tables:
            lines.append(f"未解析表体: {self.unresolved_tables}")
        if self.sufficient:
            lines.append(
                "→ 代码判定证据已可作答：下一步必须 compose_answer 或 finalize，"
                "禁止再对已检索过的子问题空转检索。"
            )
        elif self.hard_gaps:
            lines.append(
                "→ 仍有硬缺口：只允许针对上述缺口换 query 检索一轮；"
                "若补不到则 compose/finalize 并写明缺口。"
            )
        return "\n".join(lines)


def audit_bag_sufficiency(
    question: str,
    evidence: list[EvidenceItem],
) -> SufficiencyAudit:
    """Deterministic audit: hard gaps block sufficiency; soft size can pass."""
    chunks = [item for item in evidence if item.kind == "chunk"]
    blob = bag_blob(evidence)
    missing = missing_question_clauses(question, evidence)
    unresolved = unresolved_table_refs(evidence)
    gaps = analyze_bag_gaps(evidence, question)
    clause_hits = _clause_hits_in_bag(question, blob)
    enum_target = _parse_enum_count(question)
    notes: list[str] = []

    hard_gaps = bool(missing or unresolved)
    evidence_count = len(evidence)
    chunk_count = len(chunks)

    if evidence_count == 0:
        return SufficiencyAudit(
            sufficient=False,
            reason="证据袋为空",
            evidence_count=0,
            chunk_count=0,
            missing_clauses=missing,
            unresolved_tables=unresolved,
            clause_hits=clause_hits,
            enum_target=enum_target,
            hard_gaps=True,
            notes=["empty_bag"],
        )

    # Hard structural gaps from question morphology / table pointers.
    if hard_gaps:
        return SufficiencyAudit(
            sufficient=False,
            reason="题干条款或表体仍有硬缺口",
            evidence_count=evidence_count,
            chunk_count=chunk_count,
            missing_clauses=missing,
            unresolved_tables=unresolved,
            clause_hits=clause_hits,
            enum_target=enum_target,
            hard_gaps=True,
            notes=["hard_gaps"],
        )

    # Enumeration questions: require some bag bulk so we are not composing on a stub.
    if enum_target and enum_target >= 3:
        # Do not invent gold scene names. One substantial chunk + no hard gaps is enough.
        if chunk_count < 1 or len(blob) < 200:
            notes.append("enum_bag_thin")
            return SufficiencyAudit(
                sufficient=False,
                reason=f"题为枚举({enum_target}类)但袋内正文过薄",
                evidence_count=evidence_count,
                chunk_count=chunk_count,
                missing_clauses=missing,
                unresolved_tables=unresolved,
                clause_hits=clause_hits,
                enum_target=enum_target,
                hard_gaps=False,
                notes=notes,
            )

    # All question clauses present (or none named) and we have real text.
    if chunk_count >= 1 and len(blob) >= 200:
        notes.append("text_present_no_hard_gaps")
        return SufficiencyAudit(
            sufficient=True,
            reason="无硬缺口且袋内已有可用正文，足以 compose",
            evidence_count=evidence_count,
            chunk_count=chunk_count,
            missing_clauses=missing,
            unresolved_tables=unresolved,
            clause_hits=clause_hits,
            enum_target=enum_target,
            hard_gaps=False,
            notes=notes,
        )

    # Thin bag, no hard gaps yet — allow one more retrieve, not sufficient.
    if gaps.get("has_gaps") and not hard_gaps:
        notes.append("soft_gaps_only")
    return SufficiencyAudit(
        sufficient=False,
        reason="袋内正文偏少，可再针对性补一轮",
        evidence_count=evidence_count,
        chunk_count=chunk_count,
        missing_clauses=missing,
        unresolved_tables=unresolved,
        clause_hits=clause_hits,
        enum_target=enum_target,
        hard_gaps=False,
        notes=notes or ["thin_bag"],
    )
