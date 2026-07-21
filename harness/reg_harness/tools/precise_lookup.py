from __future__ import annotations

from typing import Any

from reg_harness.compact import compact_evidence
from reg_harness.knowledge.evidence_catalog import EvidenceCatalog
from reg_harness.slots import refresh_slots
from reg_harness.types import AgentState, ToolResult
from reg_harness.tools.base import Tool


def _active_kb(state: AgentState, catalog: EvidenceCatalog) -> str:
    intent = (state.meta or {}).get("intent") or {}
    kb_list = intent.get("kb") or []
    if isinstance(kb_list, list) and kb_list:
        return str(kb_list[0])
    return catalog.default_kb


class ClauseLookupTool(Tool):
    name = "clause_lookup"
    description = "Precise clause/appendix lookup from the evidence catalog (auditable IDs)."
    parameters = {
        "type": "object",
        "properties": {
            "clause": {"type": "string", "description": "e.g. 6.11 or 5.4"},
            "kb": {"type": "string", "description": "optional kb id"},
        },
        "required": ["clause"],
    }

    def __init__(self, catalog: EvidenceCatalog, settings: Any = None):
        self.catalog = catalog
        self.settings = settings

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        clause = str(args.get("clause") or args.get("query") or "").strip()
        if not clause:
            return ToolResult(
                name=self.name,
                ok=False,
                content="clause_lookup 需要 args.clause，例如 \"6.11\" 或 \"5.4\"。",
                error="missing_clause",
                continue_loop=True,
            )
        kb = str(args.get("kb") or _active_kb(state, self.catalog))
        signature = f"{self.name}|{kb}|{clause}"
        if state.register_call(signature):
            return ToolResult(
                name=self.name,
                ok=False,
                content=f"重复 clause_lookup 已拦截: {clause}",
                error="duplicate_call",
                continue_loop=True,
            )

        records = self.catalog.lookup_clause(clause, kb=kb)
        if not records:
            # try without kb filter
            records = self.catalog.lookup_clause(clause, kb=None)
        if not records:
            return ToolResult(
                name=self.name,
                ok=False,
                content=f"未找到条款 {clause!r}（kb={kb}）。可改用 graph_search/vector_search。",
                error="not_found",
                continue_loop=True,
            )

        added = 0
        seen = {item.text for item in state.evidence}
        seen_ids = {eid for item in state.evidence for eid in item.evidence_ids}
        for record in records[:5]:
            item = record.to_evidence_item(source_tool=self.name)
            if item.text in seen or record.id in seen_ids:
                continue
            state.evidence.append(item)
            seen.add(item.text)
            seen_ids.add(record.id)
            added += 1

        bag_limit = int(getattr(self.settings, "bag_limit", 20) or 20) if self.settings else 20
        state.evidence = compact_evidence(
            state.evidence,
            state.question,
            max_items=bag_limit,
            settings=self.settings,
            query=clause,
        )
        if state.slots:
            refresh_slots(state.slots, state.evidence)

        ids = [record.id for record in records[:5]]
        titles = [f"{record.id}: {record.title}" for record in records[:5]]
        content = (
            f"clause={clause} kb={kb} hits={len(records)} added={added}\n"
            + "\n".join(f"- {line}" for line in titles)
            + f"\nids={ids}"
        )
        return ToolResult(
            name=self.name,
            ok=True,
            content=content,
            data={"clause": clause, "kb": kb, "ids": ids, "added": added},
        )


class TableLookupTool(Tool):
    name = "table_lookup"
    description = "Precise table-row lookup by table number and conditions (vehicle/speed/load)."
    parameters = {
        "type": "object",
        "properties": {
            "table": {"type": "string", "description": "table number"},
            "vehicle": {"type": "string"},
            "ego_kmh": {"type": "number"},
            "target_kmh": {"type": "number"},
            "load_state": {"type": "string"},
            "scenario": {"type": "string"},
            "kb": {"type": "string"},
        },
        "required": ["table"],
    }

    def __init__(self, catalog: EvidenceCatalog, settings: Any = None):
        self.catalog = catalog
        self.settings = settings

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        table = args.get("table")
        if table is None or str(table).strip() == "":
            return ToolResult(
                name=self.name,
                ok=False,
                content="table_lookup 需要 args.table，例如 2 或 \"2\"。",
                error="missing_table",
                continue_loop=True,
            )
        vehicle = args.get("vehicle") or args.get("vehicle_category")
        ego = args.get("ego_kmh") or args.get("ego_speed") or args.get("vehicle_speed")
        target = args.get("target_kmh") or args.get("target_speed")
        load_state = args.get("load_state")
        scenario = args.get("scenario")
        kb = str(args.get("kb") or _active_kb(state, self.catalog))

        def _num(value: Any) -> float | int | None:
            if value is None or value == "":
                return None
            try:
                number = float(value)
                if number.is_integer():
                    return int(number)
                return number
            except (TypeError, ValueError):
                return None

        signature = f"{self.name}|{kb}|{table}|{vehicle}|{ego}|{target}|{load_state}|{scenario}"
        if state.register_call(signature):
            return ToolResult(
                name=self.name,
                ok=False,
                content=f"重复 table_lookup 已拦截: table={table}",
                error="duplicate_call",
                continue_loop=True,
            )

        records = self.catalog.lookup_table(
            table,
            vehicle=str(vehicle) if vehicle else None,
            ego_kmh=_num(ego),
            target_kmh=_num(target),
            load_state=str(load_state) if load_state else None,
            scenario=str(scenario) if scenario else None,
            kb=kb,
        )
        if not records:
            return ToolResult(
                name=self.name,
                ok=False,
                content=(
                    f"未命中表 {table} 条件 vehicle={vehicle} ego={ego} target={target} "
                    f"load={load_state} scenario={scenario}。可能无此试验行 → 考虑拒答。"
                ),
                error="not_found",
                continue_loop=True,
            )

        added = 0
        seen = {item.text for item in state.evidence}
        seen_ids = {eid for item in state.evidence for eid in item.evidence_ids}
        for record in records[:6]:
            item = record.to_evidence_item(source_tool=self.name)
            if item.text in seen or record.id in seen_ids:
                continue
            state.evidence.append(item)
            seen.add(item.text)
            seen_ids.add(record.id)
            added += 1

        bag_limit = int(getattr(self.settings, "bag_limit", 20) or 20) if self.settings else 20
        state.evidence = compact_evidence(
            state.evidence,
            state.question,
            max_items=bag_limit,
            settings=self.settings,
            query=str(table),
        )
        if state.slots:
            refresh_slots(state.slots, state.evidence)

        lines = []
        for record in records[:6]:
            facts = record.normalized_facts
            lines.append(f"- {record.id} facts={facts} title={record.title}")
        content = (
            f"table={table} hits={len(records)} added={added}\n" + "\n".join(lines)
        )
        return ToolResult(
            name=self.name,
            ok=True,
            content=content,
            data={
                "table": str(table),
                "ids": [record.id for record in records[:6]],
                "added": added,
                "kb": kb,
            },
        )
