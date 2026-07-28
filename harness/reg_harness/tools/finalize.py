from __future__ import annotations

from typing import Any

from reg_harness.guards import validate_final_answer
from reg_harness.types import AgentState, ToolResult
from reg_harness.tools.base import Tool


class FinalizeTool(Tool):
    name = "finalize"
    description = (
        "Explicit stop. Prefer compose_answer for positive answers. "
        "Use finalize mainly to refuse (answerable=false) or to accept a prior draft."
    )
    parameters = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answerable": {"type": "boolean"},
            "reason": {"type": "string", "minLength": 1, "maxLength": 4000},
            "accept_draft": {"type": "boolean"},
            "answer": {"type": "object"},
            "claims": {"type": "array", "items": {"type": "string"}},
            "citations": {
                "type": "array",
                "items": {"type": "string", "pattern": r"^E[1-9]\d*$"},
            },
        },
    }

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        accept_draft = args.get("accept_draft") is True
        if accept_draft and not state.draft_answer:
            return ToolResult(
                name=self.name,
                ok=False,
                content="没有可接受的 draft；请先 compose_answer 或明确拒答。",
                error="missing_draft",
                continue_loop=True,
            )
        if not accept_draft and type(args.get("answerable")) is not bool:
            return ToolResult(
                name=self.name,
                ok=False,
                content="finalize 必须显式提供布尔 answerable。",
                error="invalid_final_contract",
                continue_loop=True,
            )

        # Allow accepting a prior draft only after running the same final guards.
        if accept_draft:
            prediction = dict(state.draft_answer)
        else:
            prediction = {
                "answerable": args["answerable"],
                "answer": args.get("answer") if args.get("answer") is not None else {},
                "claims": args.get("claims", []),
                "citations": args.get("citations", []),
                "reason": args.get("reason"),
            }
        if args.get("reason") and prediction.get("answerable") is False:
            if not prediction.get("answer"):
                prediction["answer"] = {"answerable": False, "reason": args.get("reason")}
            elif isinstance(prediction["answer"], dict):
                prediction["answer"].setdefault("reason", args.get("reason"))

        # Positive answers should go through compose_answer (evidence-grounded generation)
        if prediction.get("answerable") is True and not accept_draft:
            return ToolResult(
                name=self.name,
                ok=False,
                content=(
                    "可答结论请用 compose_answer（会基于证据袋生成并做门控）。"
                    " finalize 仅用于拒答或 accept_draft=true。"
                ),
                error="use_compose_answer",
                continue_loop=True,
            )

        checked = validate_final_answer(state, prediction)
        flags = checked.get("validation_flags") or []

        guard_failed = any(str(flag).startswith("forced_refusal_") for flag in flags)
        if guard_failed:
            return ToolResult(
                name=self.name,
                ok=False,
                content=f"finalize 未通过门控 flags={flags}，请修正输出、继续取证或明确拒答。",
                data=checked,
                error="guard_failed",
                continue_loop=True,
            )

        state.final_answer = checked
        state.done = True
        state.phase = "done"
        if checked.get("answerable") is False:
            answer = checked.get("answer") or {}
            if isinstance(answer, dict):
                state.refuse_reason = str(answer.get("reason") or args.get("reason") or "")
        return ToolResult(
            name=self.name,
            ok=True,
            content=f"finalized answerable={checked.get('answerable')} flags={flags}",
            data=checked,
        )
