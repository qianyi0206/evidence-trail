from __future__ import annotations

from typing import Any

from reg_harness.guards import collect_context_numbers
from reg_harness.slots import refresh_slots, slot_summary
from reg_harness.types import AgentState, ToolResult
from reg_harness.tools.base import Tool


class EvidenceCheckTool(Tool):
    name = "evidence_check"
    description = "Report evidence bag size/kinds and optional slot gaps; no new legal facts."
    parameters = {
        "type": "object",
        "properties": {"focus": {"type": "string"}},
    }

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        focus = str(args.get("focus") or "")
        if state.slots:
            refresh_slots(state.slots, state.evidence)
        summary = slot_summary(state.slots) if state.slots else {
            "missing": [],
            "partial": [],
            "covered": [],
            "all_covered": bool(state.evidence),
            "ready_for_answer": bool(state.evidence),
            "suggested_next": [],
            "slots": [],
        }

        kinds: dict[str, int] = {}
        for item in state.evidence:
            kinds[item.kind] = kinds.get(item.kind, 0) + 1
        numbers = sorted(
            collect_context_numbers(state.evidence),
            key=lambda value: (len(value), value),
        )
        focus_hits = (
            sum(1 for item in state.evidence if focus and focus in item.text) if focus else 0
        )

        from reg_harness.bag_gaps import analyze_bag_gaps, format_gap_hints

        gaps = analyze_bag_gaps(state.evidence, state.question)
        lines = [
            f"bag_size={len(state.evidence)} kinds={kinds}",
            f"slots_covered={summary.get('covered')} partial={summary.get('partial')} missing={summary.get('missing')}",
            f"ready_for_answer={summary.get('ready_for_answer')} all_covered={summary.get('all_covered')}",
            f"numeric_sample={numbers[:15]}",
        ]
        if focus:
            lines.append(f"focus={focus!r} hits={focus_hits}")
        if gaps.get("unresolved_tables"):
            lines.append(f"unresolved_tables={gaps['unresolved_tables']}")
        if gaps.get("missing_question_clauses"):
            lines.append(f"missing_question_clauses={gaps['missing_question_clauses']}")
        suggested = summary.get("suggested_next") or []
        if suggested:
            lines.append("suggested_next:")
            for item in suggested:
                lines.append(
                    f"  - slot={item['slot_id']} tool={item['prefer_tool']} query={item['suggested_query']!r}"
                )
        if not state.evidence:
            lines.append("WARN: 证据袋为空 → 先 vector_search 或 graph_search，query 用子问题。")
        elif summary.get("missing"):
            lines.append("WARN: 仍有 missing 槽位 → 不要 compose_answer，按 suggested_next 再取证。")
        elif gaps.get("has_gaps"):
            lines.append("WARN: 存在取证缺口（见表号无表体/题干条款未命中）→ 先补检索再 compose。")
        else:
            lines.append("OK: 槽位基本覆盖 → 可 compose_answer。")
        gap_text = format_gap_hints(state.evidence, state.question, prefix="【取证缺口】")
        if gap_text:
            lines.append(gap_text)

        content = "\n".join(lines)
        state.last_observation = content
        return ToolResult(
            name=self.name,
            ok=True,
            content=content,
            data={
                "count": len(state.evidence),
                "kinds": kinds,
                "focus_hits": focus_hits,
                "slot_summary": summary,
                "bag_gaps": gaps,
            },
        )
