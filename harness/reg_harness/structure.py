from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StructureSignals:
    """Weak signals parsed only from the question text (PROTOCOL §3.1)."""

    clause_candidates: list[str] = field(default_factory=list)
    table_candidates: list[str] = field(default_factory=list)
    vehicle_categories: list[str] = field(default_factory=list)
    speeds_kmh: list[str] = field(default_factory=list)
    has_table_word: bool = False
    has_enumeration_cue: bool = False
    has_existence_cue: bool = False
    has_comparison_cue: bool = False
    question_tokens: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "clause_candidates": self.clause_candidates,
            "table_candidates": self.table_candidates,
            "vehicle_categories": self.vehicle_categories,
            "speeds_kmh": self.speeds_kmh,
            "has_table_word": self.has_table_word,
            "has_enumeration_cue": self.has_enumeration_cue,
            "has_existence_cue": self.has_existence_cue,
            "has_comparison_cue": self.has_comparison_cue,
            "question_tokens": self.question_tokens,
        }

    def format_for_prompt(self) -> str:
        parts: list[str] = []
        if self.clause_candidates:
            parts.append("条款候选: " + ", ".join(self.clause_candidates))
        if self.table_candidates:
            parts.append("表号候选: " + ", ".join(self.table_candidates))
        if self.vehicle_categories:
            parts.append("车型: " + ", ".join(self.vehicle_categories))
        if self.speeds_kmh:
            parts.append("速度km/h: " + ", ".join(self.speeds_kmh))
        if self.has_table_word:
            parts.append("题干含「表」")
        if self.has_enumeration_cue:
            parts.append("枚举/列表线索")
        if self.has_existence_cue:
            parts.append("存在性/是否类线索（可走证伪）")
        if self.has_comparison_cue:
            parts.append("比较/例外线索")
        return "；".join(parts)


def parse_structure_signals(question: str) -> StructureSignals:
    text = question or ""
    clauses = re.findall(r"(?:条款|第)?\s*(\d+(?:\.\d+)+[A-Za-z]?)", text)
    # Prefer dotted clause forms; also bare "第X条"
    clauses += re.findall(r"第\s*(\d+(?:\.\d+)*)\s*条", text)
    tables = re.findall(r"表\s*([A-Za-z]?\d+)", text)
    vehicles = [m.upper() for m in re.findall(r"\b([MN]\d)\b", text, flags=re.IGNORECASE)]
    speeds = re.findall(r"(\d+(?:\.\d+)?)\s*km\s*/\s*h", text, flags=re.IGNORECASE)

    # Tokens that appear in the question itself (for coverage keywords) — no external lexicon.
    tokens: list[str] = []
    for value in clauses + tables + vehicles + speeds:
        if value and value not in tokens:
            tokens.append(value)
    for match in re.findall(r"[\u4e00-\u9fff]{2,12}", text):
        if match not in tokens:
            tokens.append(match)
    for match in re.findall(r"[A-Za-z]{2,}|\d+(?:\.\d+)?", text):
        if match not in tokens:
            tokens.append(match)

    return StructureSignals(
        clause_candidates=_unique(clauses),
        table_candidates=_unique(tables),
        vehicle_categories=_unique(vehicles),
        speeds_kmh=_unique(speeds),
        has_table_word="表" in text or bool(tables),
        has_enumeration_cue=any(
            cue in text for cue in ("列出", "哪些", "分别", "完整", "有哪些")
        ),
        has_existence_cue=any(
            cue in text
            for cue in ("是否存在", "有没有", "是否规定", "是否可以", "能否从", "有无")
        ),
        has_comparison_cue=any(
            cue in text for cue in ("区别", "不同", "例外", "如何处理", "相比")
        ),
        question_tokens=tokens[:40],
    )


def focus_terms_from_question(question: str) -> list[str]:
    """Ranking terms must come from the question (or generic regex on it), not a pilot lexicon."""
    signals = parse_structure_signals(question)
    terms: list[str] = []
    terms.extend(signals.vehicle_categories)
    terms.extend(signals.speeds_kmh)
    terms.extend(signals.clause_candidates)
    for table in signals.table_candidates:
        terms.append(table)
        terms.append(f"表{table}")
        terms.append(f"table_{table}")
    # Short Chinese spans already in the question (capped)
    for token in signals.question_tokens:
        if len(token) >= 2 and token not in terms:
            terms.append(token)
        if len(terms) >= 24:
            break
    return terms


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.casefold() if isinstance(value, str) else str(value)
        if not value or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out
