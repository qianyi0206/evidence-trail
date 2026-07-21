from __future__ import annotations

import json
import re
from typing import Any

from reg_harness.config import Settings
from reg_harness.intent import resolve_intent
from reg_harness.llm import ChatClient
from reg_harness.policies import preferred_retrieve_modes
from reg_harness.prompts import SYSTEM_PROMPT, build_user_turn
from reg_harness.slots import build_slots, refresh_slots, slot_summary
from reg_harness.structure import parse_structure_signals
from reg_harness.sufficiency import SufficiencyAudit, audit_bag_sufficiency
from reg_harness.tools.registry import ToolRegistry, default_registry
from reg_harness.types import AgentState, EvidenceItem

# Retrieve-like tools that participate in stagnation / sufficiency.
_RETRIEVE_ACTIONS = frozenset(
    {"vector_search", "graph_search", "clause_lookup", "table_lookup"}
)
# After this many stagnant retrieve rounds with a non-empty bag → hard compose.
_FORCE_COMPOSE_STAGNANT = 3
# Consecutive duplicate_call errors with a non-empty bag → hard compose.
_FORCE_COMPOSE_DUPLICATES = 2


def _bag_signature(
    evidence: list[EvidenceItem],
) -> tuple[int, frozenset[str], frozenset[str]]:
    """Cheap fingerprint: size + clause-like markers + kinds present in the bag."""
    blob = "\n".join(item.text or "" for item in evidence)
    markers = frozenset(re.findall(r"\d+(?:\.\d+)+", blob))
    # Keep short markers only (clause-like), drop pure integers noise somewhat
    markers = frozenset(m for m in markers if "." in m)
    kinds = frozenset(item.kind for item in evidence)
    return (len(evidence), markers, kinds)


def _suggest_compose_message(
    state: AgentState,
    audit: SufficiencyAudit | None = None,
) -> str:
    from reg_harness.bag_gaps import analyze_bag_gaps, format_gap_hints

    n = len(state.evidence)
    chunks = sum(1 for item in state.evidence if item.kind == "chunk")
    gaps = analyze_bag_gaps(state.evidence, state.question)
    audit = audit or audit_bag_sufficiency(state.question, state.evidence)
    parts = [
        f"\n【收网提示】证据袋已连续多步无明显新增（当前 {n} 条，其中 chunk={chunks}）。"
    ]
    if audit.sufficient:
        parts.append(
            "取证审核判定 **证据已足够**：下一步必须 compose_answer（或 finalize 拒答），"
            "禁止继续同意图空转检索。"
        )
    elif audit.hard_gaps or gaps.get("has_gaps"):
        parts.append(
            "仍有结构性缺口：最多再针对缺口 **换 query** 补一轮；"
            "补不到则 compose_answer/finalize 并写明缺口，不要重复同一 query。"
        )
        parts.append(format_gap_hints(state.evidence, state.question, prefix=""))
    else:
        parts.append(
            "请优先 compose_answer 基于现有证据作答或说明缺口；"
            "勿再重复相同检索。若确需补充，必须换 query 或 mode（可试 naive）。"
        )
    return "".join(parts)


class RegulationHarness:
    """Skill-led agent: model plans; code runs tools and hard gates."""

    def __init__(
        self,
        settings: Settings,
        registry: ToolRegistry | None = None,
        chat: ChatClient | None = None,
    ):
        self.settings = settings
        self.chat = chat or ChatClient(settings)
        self.registry = registry or default_registry(settings, chat=self.chat)

    @classmethod
    def from_env(cls, profile_env: str | None = None) -> "RegulationHarness":
        from reg_harness.config import load_settings

        return cls(settings=load_settings(profile_env=profile_env))

    def run(
        self,
        question: str,
        *,
        policy: str = "auto",
        max_steps: int | None = None,
        bootstrap: bool = False,
        event_hook: Any = None,
    ) -> AgentState:
        pilot = bool(getattr(self.settings, "pilot_heuristics", False))
        steps = max_steps or max(self.settings.default_max_steps, 6)

        # Default skill path: no rule intent/slots. Pilot switch restores legacy scaffolding.
        if pilot:
            intent = resolve_intent(question, policy, pilot_heuristics=True)
            resolved_policy = policy if policy and policy != "auto" else intent.policy
            slots = build_slots(question, resolved_policy, pilot_heuristics=True)
            structure = parse_structure_signals(question)
            intent_dict = intent.to_dict()
            structure_dict = structure.to_dict()
            structure_prompt = structure.format_for_prompt()
            active_kb = intent.kb[0] if intent.kb else self.settings.active_kb
        else:
            resolved_policy = policy if policy and policy != "auto" else "complex"
            slots = []
            intent_dict = {
                "mode": "skill",
                "kb": [self.settings.active_kb],
                "note": "intent/plan by model; no rule router",
            }
            structure_dict = {}
            structure_prompt = ""
            active_kb = self.settings.active_kb

        state = AgentState(
            question=question,
            policy=resolved_policy,
            max_steps=steps,
            slots=slots,
            phase="gather",
            event_hook=event_hook,
            meta={
                "intent": intent_dict,
                "preferred_modes": preferred_retrieve_modes(resolved_policy),  # type: ignore[arg-type]
                "bootstrap": bootstrap,
                "active_kb": active_kb,
                "pilot_heuristics": pilot,
                "structure_signals": structure_dict,
                "enable_precise_lookup": bool(
                    getattr(self.settings, "enable_precise_lookup", False)
                ),
            },
        )
        state.add_trace(
            "start",
            policy=resolved_policy,
            question=question,
            pilot_heuristics=pilot,
            tools=self.registry.names(),
        )

        if bootstrap:
            mode = preferred_retrieve_modes(resolved_policy)[0]  # type: ignore[arg-type]
            tool = "vector_search" if mode == "naive" else "graph_search"
            boot = self.registry.run(
                tool,
                state,
                {"query": question, "mode": mode},
            )
            state.last_observation = boot.content
            state.add_trace(
                "bootstrap_tool",
                tool=tool,
                ok=boot.ok,
                content=boot.content[:800],
                data=boot.data,
            )

        if not state.last_observation:
            if pilot and state.slots:
                refresh_slots(state.slots, state.evidence)
                summary = slot_summary(state.slots)
                state.last_observation = (
                    "尚未检索。请主动取证，不要直接 compose。\n"
                    f"pilot missing={summary.get('missing')} "
                    f"suggested_next={summary.get('suggested_next')}"
                )
                state.add_trace("awaiting_agent_plan", slot_summary=summary)
            else:
                state.last_observation = (
                    "尚未检索。请根据系统说明与工具自行规划取证；"
                    "证据袋为空时不要 compose 最终答案。"
                )
                state.add_trace("awaiting_agent_plan")

        allowed = self.registry.allowed_actions()
        stagnant_rounds = 0
        last_sig: tuple[Any, ...] | None = None
        duplicate_streak = 0
        force_compose = False
        force_compose_reason = ""
        last_audit: SufficiencyAudit | None = None

        while not state.done and state.step < state.max_steps:
            state.step += 1
            if pilot and state.slots:
                refresh_slots(state.slots, state.evidence)

            # Hard gate: after audit / spin detection, skip another LLM plan turn.
            if force_compose and state.evidence and "compose_answer" in allowed:
                state = self._force_compose(
                    state, reason=force_compose_reason or "force_compose"
                )
                if state.done:
                    break
                force_compose = False

            # Decision model still gets a full bag preview (not the old 16×800 cap).
            user = build_user_turn(
                question=state.question,
                evidence_preview=state.evidence_text(for_compose=False),
                last_observation=state.last_observation,
                step=state.step,
                max_steps=state.max_steps,
                phase=state.phase,
                policy=state.policy,
                slot_preview=state.slot_text() if pilot else "",
                intent_preview=(
                    json.dumps(state.meta.get("intent") or {}, ensure_ascii=False)
                    if pilot
                    else ""
                ),
                structure_signals=structure_prompt if pilot else "",
            )
            system = SYSTEM_PROMPT
            if hasattr(self.registry, "prompt_catalog"):
                system = SYSTEM_PROMPT + "\n\n" + self.registry.prompt_catalog()
            try:
                state.add_trace("llm_start", role="decision")
                decision = self.chat.complete_json(system, user)
                state.add_trace("llm_end", role="decision")
            except Exception as error:  # noqa: BLE001
                state.add_trace("llm_error", error=str(error))
                self.registry.run(
                    "finalize",
                    state,
                    {
                        "answerable": False,
                        "reason": f"决策模型失败: {error}",
                        "answer": {"answerable": False, "reason": str(error)},
                    },
                )
                break

            state.add_trace("decision", decision=decision)
            action = str(decision.get("action") or "").strip()
            args = decision.get("args") if isinstance(decision.get("args"), dict) else {}
            thought = str(decision.get("thought") or "")

            # If bag already sufficient / spin detected, rewrite retrieve → compose.
            if (
                force_compose
                and action in _RETRIEVE_ACTIONS
                and state.evidence
                and "compose_answer" in allowed
            ):
                state.add_trace(
                    "override_retrieve_to_compose",
                    original_action=action,
                    reason=force_compose_reason,
                    thought=thought[:300],
                )
                action = "compose_answer"
                args = {"force": True}

            if action not in allowed:
                state.last_observation = (
                    f"非法或未启用 action={action!r} thought={thought!r}。"
                    f"允许: {sorted(allowed)}"
                )
                state.add_trace("invalid_decision", decision=decision)
                continue

            result = self.registry.run(action, state, args)
            observation = result.content or ""

            # --- Post-execute audit (plan → execute → audit) ---
            if action in _RETRIEVE_ACTIONS:
                if result.error == "duplicate_call" or (
                    not result.ok and "重复检索" in (result.content or "")
                ):
                    duplicate_streak += 1
                else:
                    duplicate_streak = 0

                sig = _bag_signature(state.evidence)
                if last_sig is not None and sig[0] <= last_sig[0] and sig[1] <= last_sig[1]:
                    stagnant_rounds += 1
                else:
                    stagnant_rounds = 0
                last_sig = sig

                last_audit = audit_bag_sufficiency(state.question, state.evidence)
                state.add_trace(
                    "sufficiency_audit",
                    **last_audit.to_dict(),
                    stagnant_rounds=stagnant_rounds,
                    duplicate_streak=duplicate_streak,
                )
                observation = observation + last_audit.observation_block()

                if stagnant_rounds >= 2 and state.evidence:
                    hint = _suggest_compose_message(state, last_audit)
                    observation = observation + hint
                    state.add_trace(
                        "suggest_compose",
                        stagnant_rounds=stagnant_rounds,
                        bag_size=len(state.evidence),
                        sufficient=last_audit.sufficient,
                    )

                # Hard force-compose triggers (code, not model politeness).
                if state.evidence and "compose_answer" in allowed:
                    if duplicate_streak >= _FORCE_COMPOSE_DUPLICATES:
                        force_compose = True
                        force_compose_reason = (
                            f"duplicate_streak>={_FORCE_COMPOSE_DUPLICATES}"
                        )
                    elif stagnant_rounds >= _FORCE_COMPOSE_STAGNANT:
                        force_compose = True
                        force_compose_reason = (
                            f"stagnant_rounds>={_FORCE_COMPOSE_STAGNANT}"
                        )
                    elif last_audit.sufficient and stagnant_rounds >= 1:
                        force_compose = True
                        force_compose_reason = "sufficient_and_stagnant"
                    elif (
                        last_audit.sufficient
                        and result.ok
                        and int((result.data or {}).get("added") or 0) == 0
                        and state.step >= 2
                    ):
                        force_compose = True
                        force_compose_reason = "sufficient_zero_added"

            state.last_observation = observation
            state.add_trace(
                "tool_result",
                tool=action,
                ok=result.ok,
                continue_loop=result.continue_loop,
                content=observation[:1200],
                data=result.data,
            )

            if force_compose and state.evidence and not state.done:
                # Immediately compose in the same step budget when possible.
                state = self._force_compose(
                    state, reason=force_compose_reason or "force_compose"
                )
                if state.done:
                    break
                force_compose = False
                continue

            if result.continue_loop:
                state.done = False
                state.phase = "gather"
                continue

        if not state.done:
            state = self._end_of_budget(state)

        return state

    def _force_compose(self, state: AgentState, *, reason: str) -> AgentState:
        """Code-side compose: the audit beat decided the bag is good enough / spinning."""
        state.add_trace(
            "force_compose",
            reason=reason,
            evidence_count=len(state.evidence),
        )
        state.last_observation = (
            f"【强制收网】{reason}：基于当前证据袋 compose，不再空转检索。"
        )
        result = self.registry.run("compose_answer", state, {"force": True})
        state.last_observation = result.content
        state.add_trace(
            "forced_compose",
            ok=result.ok,
            reason=reason,
            content=(result.content or "")[:800],
            data=result.data,
        )
        if not state.done and result.continue_loop:
            state.phase = "gather"
        return state

    def _end_of_budget(self, state: AgentState) -> AgentState:
        state.add_trace("max_steps_reached", evidence_count=len(state.evidence))
        if state.evidence:
            result = self.registry.run("compose_answer", state, {"force": True})
            state.last_observation = result.content
            state.add_trace(
                "forced_compose",
                ok=result.ok,
                content=result.content[:800],
                data=result.data,
            )
            if state.done:
                return state

        self.registry.run(
            "finalize",
            state,
            {
                "answerable": False,
                "reason": "达到 max_steps 仍无法完成可验证作答。",
                "answer": {
                    "answerable": False,
                    "reason": "max_steps_exceeded",
                },
            },
        )
        state.add_trace("force_finalize_max_steps")
        return state


def state_to_dict(state: AgentState) -> dict[str, Any]:
    return {
        "question": state.question,
        "policy": state.policy,
        "phase": state.phase,
        "steps": state.step,
        "done": state.done,
        "evidence_count": len(state.evidence),
        "evidence_ids": sorted(
            {eid for item in state.evidence for eid in item.evidence_ids}
        ),
        "slots": [slot.to_dict() for slot in state.slots],
        "intent": (state.meta or {}).get("intent"),
        "final_answer": state.final_answer,
        "refuse_reason": state.refuse_reason,
        "last_observation": state.last_observation,
        "trace": state.trace,
        "meta": state.meta,
    }


def pretty_print_result(state: AgentState) -> str:
    payload = {
        "policy": state.policy,
        "intent": (state.meta or {}).get("intent"),
        "phase": state.phase,
        "steps": state.step,
        "evidence_count": len(state.evidence),
        "evidence_ids": sorted(
            {eid for item in state.evidence for eid in item.evidence_ids}
        ),
        "slots": [slot.to_dict() for slot in state.slots],
        "final_answer": state.final_answer,
        "trace_events": [item.get("event") for item in state.trace],
        "last_observation": (state.last_observation or "")[:500],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
