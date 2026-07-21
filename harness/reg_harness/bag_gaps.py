"""Lightweight evidence-bag gap hints (no gold, no pilot answer keys).

Detects generic structural holes so the decision LLM can plan a follow-up
retrieve instead of composing early or spinning the same query.
"""

from __future__ import annotations

import re
from typing import Any

from reg_harness.types import EvidenceItem

# 「见表N」「按照表 2」「表A.1」等引用（N 任意，不绑定具体表号）
_TABLE_REF_RE = re.compile(
    r"(?:见|按|按照|依据|根据|如|参阅|参照)?\s*表\s*([A-Za-z]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_TABLE_MARK_RE = re.compile(r"表\s*([A-Za-z]?\d+(?:\.\d+)?)", re.IGNORECASE)
# Avoid \b: CJK letters are \w in Python, so "依据8.1" would miss the clause.
_CLAUSE_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+){1,3})(?![\d.])")
_TRUNC_MARK = "…[truncated]"


def bag_blob(evidence: list[EvidenceItem]) -> str:
    return "\n".join(item.text or "" for item in evidence)


def referenced_tables(text: str) -> set[str]:
    found = set()
    for match in _TABLE_REF_RE.finditer(text or ""):
        tid = match.group(1).strip()
        if tid:
            found.add(tid.upper() if tid[:1].isalpha() else tid)
    return found


def _normalize_table_id(tid: str) -> str:
    tid = tid.strip()
    return tid.upper() if tid[:1].isalpha() else tid


def table_body_present(text: str, table_id: str) -> bool:
    """Heuristic: chunk looks like it contains the table body, not only a pointer."""
    if not text:
        return False
    tid = re.escape(table_id)
    # Require an explicit table mark. Do not treat a bare digit anywhere in the
    # text as a hit (short ids like "1"/"2" false-positive on narrative chunks).
    has_mark = bool(
        re.search(rf"表\s*{tid}\b", text, flags=re.IGNORECASE)
        or re.search(rf"table[_-]?a?_?{tid}\b", text, flags=re.IGNORECASE)
        or (
            "unit_id:table" in text.lower()
            and re.search(
                rf"(?:unit_id\s*:\s*table[_-]?|table[_-]?){tid}\b",
                text,
                flags=re.IGNORECASE,
            )
        )
    )
    if not has_mark:
        return False
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    # Pointer-only lines rarely carry many numbers; table bodies do.
    if len(numbers) >= 4:
        return True
    # Short but dense table fragment
    if len(numbers) >= 2 and (
        "km/h" in text
        or "km／h" in text
        or "最大相对" in text
        or "<table" in text.lower()
        or text.count("|") >= 3
        or text.count("\t") >= 2
    ):
        return True
    return False


def unresolved_table_refs(evidence: list[EvidenceItem]) -> list[str]:
    blob = bag_blob(evidence)
    refs = referenced_tables(blob)
    if not refs:
        return []
    unresolved = []
    for tid in sorted(refs, key=lambda x: (len(x), x)):
        if any(table_body_present(item.text or "", tid) for item in evidence):
            continue
        unresolved.append(tid)
    return unresolved


def question_clause_candidates(question: str) -> list[str]:
    return sorted(set(_CLAUSE_RE.findall(question or "")), key=lambda x: (len(x), x))


def missing_question_clauses(question: str, evidence: list[EvidenceItem]) -> list[str]:
    """Clauses explicitly named in the question but absent from the bag."""
    needed = question_clause_candidates(question)
    if not needed:
        return []
    blob = bag_blob(evidence)
    missing = []
    for clause in needed:
        # Digit-aware boundaries only (CJK is \w in Python and would hide 条款).
        if re.search(rf"(?<![\d.]){re.escape(clause)}(?![\d.])", blob):
            continue
        missing.append(clause)
    return missing


def truncated_item_count(evidence: list[EvidenceItem], *, cap: int = 4500) -> int:
    """Items that will almost certainly truncate under default compose caps."""
    n = 0
    for item in evidence:
        text = item.text or ""
        if len(text) > cap:
            n += 1
    return n


def analyze_bag_gaps(
    evidence: list[EvidenceItem],
    question: str = "",
) -> dict[str, Any]:
    unresolved = unresolved_table_refs(evidence)
    missing_clauses = missing_question_clauses(question, evidence)
    long_items = truncated_item_count(evidence)
    suggested_queries: list[str] = []
    for tid in unresolved[:4]:
        suggested_queries.append(f"表{tid} 全文 数值 要求")
    for clause in missing_clauses[:4]:
        suggested_queries.append(f"条款 {clause} 原文")
    # Lighting / physical condition keywords often sit in test general sections
    q = question or ""
    blob = bag_blob(evidence)
    # Need a real lux figure, not merely the word 照度/光照 without a value.
    has_lx_value = bool(
        re.search(
            r"\d[\d\s\u00a0]*\s*lx|"
            r"不小于\s*\d[\d\s\u00a0]*(?:\s*lx)?|"
            r"光照强度[^\n]{0,24}\d|"
            r"\d[\d\s\u00a0]*勒克",
            blob,
            flags=re.IGNORECASE,
        )
    )
    if re.search(r"光照|照度|lx|勒克斯", q) and not has_lx_value:
        # Generic follow-ups only — no fixed lux numbers or clause IDs.
        suggested_queries.append("试验 光照强度 不小于 lx")
        suggested_queries.append("光照强度 其他试验 lx")
    # Re-query tokens present in the question only — no chapter/answer-key playbooks.
    if re.search(r"说明书|使用说明", q) and len(blob) < 800:
        suggested_queries.append("说明书 AEBS 应包含 内容")
    if re.search(r"同一型式", q) and not re.search(r"同一型式", blob):
        suggested_queries.append("同一型式 判定 条件")

    # de-dup preserve order
    seen: set[str] = set()
    uniq_q: list[str] = []
    for item in suggested_queries:
        if item not in seen:
            seen.add(item)
            uniq_q.append(item)

    return {
        "unresolved_tables": unresolved,
        "missing_question_clauses": missing_clauses,
        "long_items": long_items,
        "suggested_queries": uniq_q,
        "has_gaps": bool(unresolved or missing_clauses or uniq_q),
    }


def format_gap_hints(
    evidence: list[EvidenceItem],
    question: str = "",
    *,
    prefix: str = "\n【取证缺口】",
) -> str:
    analysis = analyze_bag_gaps(evidence, question)
    if not analysis.get("has_gaps") and not analysis.get("long_items"):
        return ""
    lines = [prefix]
    if analysis["unresolved_tables"]:
        tables = "、".join(f"表{t}" for t in analysis["unresolved_tables"][:6])
        lines.append(
            f"- 证据仅引用 {tables}，未见表体数值行 → 请 vector_search/graph_search "
            f'query 如「表X 数值/要求」，mode 可试 naive。'
        )
    if analysis["missing_question_clauses"]:
        clauses = "、".join(analysis["missing_question_clauses"][:6])
        lines.append(f"- 题干条款 {clauses} 尚未出现在证据袋 → 按条款号定向检索。")
    if analysis["long_items"]:
        lines.append(
            f"- 有 {analysis['long_items']} 条长证据，compose 时可能截断；"
            "可换更窄 query 再取关键子段，或 force compose 并在 reason 注明截断。"
        )
    if analysis["suggested_queries"]:
        lines.append("- 建议下一次检索 query 候选：")
        for q in analysis["suggested_queries"][:5]:
            lines.append(f'  · {q}')
    return "\n".join(lines)
