from __future__ import annotations

import json
from typing import Any

from reg_harness.guards import validate_final_answer
from reg_harness.llm import ChatClient
from reg_harness.slots import refresh_slots, slot_summary
from reg_harness.types import AgentState, ToolResult
from reg_harness.tools.base import Tool

COMPOSE_SYSTEM = """你是法规答题器。只能依据下方「证据袋」中的内容作答，禁止使用训练记忆或外部知识补全法规事实。

输出唯一 JSON 对象（不要 Markdown）：
{
  "answerable": true/false,
  "answer": { ... 结构化答案 ... },
  "claims": ["原子声明1", "..."],
  "citations": ["E1", "E2"],
  "reason": "简要说明依据；若 answerable=false，说明证据缺什么"
}

## 读证据（必须）
- 证据按三节组织：Text units（原文/精确目录证据）→ Relations → Entities。
- 通读全部 [E#]，**数字、条款、表行以 Text units（kind=chunk/catalog）为准**。
- relationship/entity 仅为图摘要/导航，可交叉印证，不可单独作为数值依据。
- 枚举题：先从证据中列出所有出现的条款号与场景/项目名称，再判断是否齐全。
- 表/数值题：在证据中查找表号、车型、速度、载荷等条件行，注意被截断标记 …[truncated]。
- 若证据只写「见表N」却无表体数值，不要编造表N数字；answerable=false 或只答已有部分并在 reason 写明缺表N。

## 关键数值（必须）
- 题干含「不迟于 / 至少 / 最迟 / 不小于 / 不大于 / 阈值 / TTC / 速度 / 光照」时：
  答案中必须给出证据里出现的**带单位数字**（时间/速度/照度/减速度等），禁止只用无数字的笼统定性句顶替。
- 同一主题若证据同时有「通用句」和「带数字细则」，优先采信带数字细则。
- claims 应拆成短句，每条尽量对应一个可核验事实（场景名、阈值、条款号各一条）。

## 证伪 / 不可答（answerable 约定）
- 题干问「是否强制 / 是否必须 / 是否固定 / 是否都要采用同一… / 请给出不可变的…」：
  - 若证据表明**标准未强制、允许调整、仅为示例、表中不存在该条件行** → **answerable=false**；
    在 reason/answer 中说明否定依据（可引用条款），不要标 true 再给「不是」的长文。
  - 仅当证据正面给出所求清单/数值且问题不是「有无该规定」时，才 answerable=true。
- 表中无题干所问条件行（速度档/车型/载荷组合）→ answerable=false。
- 证据被截断导致枚举明显不全 → answerable=false，reason 写清截断/缺哪一节；不要猜补。

## 作答纪律
- 数字、阈值必须在证据原文中有同形支撑。
- 禁止编造证据中未出现的场景名、条款号、速度档。
- 若证据中已能列出题干要求的各项（名称/条款均已出现），必须作答，不得以「感觉不全」拒答。
- 若场景/主事实已齐、但附属判据偏弱：可对主问题作答，并在 reason 中注明判据原文不足的部分。
- 仅当关键事实在全部证据中确实找不到时，才 answerable=false。
"""


class ComposeAnswerTool(Tool):
    name = "compose_answer"
    description = (
        "Generate a structured answer from the full evidence bag, then run guards. "
        "If guards fail, the loop continues so you can retrieve more."
    )
    parameters = {
        "type": "object",
        "properties": {
            "force": {
                "type": "boolean",
                "description": "ignore incomplete slots (use sparingly)",
            }
        },
    }

    def __init__(self, chat: ChatClient):
        self.chat = chat

    def run(self, state: AgentState, args: dict[str, Any]) -> ToolResult:
        if not state.evidence:
            return ToolResult(
                name=self.name,
                ok=False,
                content="证据袋为空，不能 compose。请先检索。",
                error="empty_bag",
                continue_loop=True,
            )

        if state.slots:
            refresh_slots(state.slots, state.evidence)
            summary = slot_summary(state.slots)
            force = bool(args.get("force"))
            if summary.get("missing") and not force:
                return ToolResult(
                    name=self.name,
                    ok=False,
                    content=(
                        "仍有 missing 槽位，拒绝 compose。"
                        f" missing={summary.get('missing')} "
                        f"suggested={summary.get('suggested_next')}"
                    ),
                    data={"slot_summary": summary},
                    error="slots_incomplete",
                    continue_loop=True,
                )

        from reg_harness.bag_gaps import analyze_bag_gaps, format_gap_hints

        bag = state.evidence_text(for_compose=True)
        gaps = analyze_bag_gaps(state.evidence, state.question)
        gap_note = format_gap_hints(
            state.evidence, state.question, prefix="【袋内缺口提示（作答时勿编造补全）】"
        )
        user = (
            f"问题：{state.question}\n\n"
            f"证据条数：{len(state.evidence)}\n"
        )
        if gap_note:
            user += f"{gap_note}\n\n"
        elif gaps.get("long_items"):
            user += "注意：部分长证据可能含 …[truncated]，勿补全截断后不可见内容。\n\n"
        user += (
            f"请基于下列全部证据作答（共 {len(state.evidence)} 条）：\n\n"
            f"{bag}\n"
        )
        try:
            state.add_trace("llm_start", role="compose")
            draft = self.chat.complete_json(COMPOSE_SYSTEM, user)
            state.add_trace("llm_end", role="compose")
        except Exception as error:  # noqa: BLE001
            return ToolResult(
                name=self.name,
                ok=False,
                content=f"作答模型失败: {error}",
                error=str(error),
                continue_loop=True,
            )

        state.draft_answer = draft
        checked = validate_final_answer(state, draft)
        flags = checked.get("validation_flags") or []

        continue_gather_flags = {
            "forced_refusal_empty_evidence",
            "forced_refusal_ungrounded_numeric",
            "forced_refusal_invalid_citations",
        }
        should_continue_gathering = checked.get("answerable") is False and any(
            flag in continue_gather_flags or flag.startswith("numeric_not_in_context")
            for flag in flags
        )

        if should_continue_gathering:
            state.phase = "gather"
            return ToolResult(
                name=self.name,
                ok=False,
                content=(
                    "作答未通过证据门控，未结束。"
                    f" flags={flags} reason={checked.get('answer', {})}."
                    " 请补充检索或改用 finalize 明确拒答。"
                ),
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
                state.refuse_reason = str(answer.get("reason") or "")
        return ToolResult(
            name=self.name,
            ok=True,
            content=f"compose_ok answerable={checked.get('answerable')} flags={flags}",
            data=checked,
        )
