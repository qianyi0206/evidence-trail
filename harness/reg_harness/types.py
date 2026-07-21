from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    name: str
    ok: bool
    content: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    continue_loop: bool = False


@dataclass
class EvidenceItem:
    """Normalized evidence bag entry collected across tool calls."""

    kind: str
    text: str
    file_path: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    score: float | None = None
    source_tool: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Slot:
    """A required information unit for the current question."""

    id: str
    description: str
    keywords: list[str] = field(default_factory=list)
    status: str = "missing"  # missing | partial | covered
    hint_query: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "hint_query": self.hint_query,
            "keywords": self.keywords,
        }


@dataclass
class AgentState:
    question: str
    policy: str = "auto"
    max_steps: int = 6
    step: int = 0
    done: bool = False
    phase: str = "gather"
    evidence: list[EvidenceItem] = field(default_factory=list)
    slots: list[Slot] = field(default_factory=list)
    last_observation: str = ""
    recent_calls: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    final_answer: dict[str, Any] | None = None
    refuse_reason: str | None = None
    draft_answer: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    # Optional live UI hook: callable(event_dict) after each add_trace (not serialized).
    event_hook: Any = field(default=None, repr=False, compare=False)

    def _format_evidence_item(
        self,
        item: EvidenceItem,
        label: int,
        *,
        for_compose: bool,
        max_chars_per_item: int | None,
    ) -> str:
        ids = ",".join(item.evidence_ids) if item.evidence_ids else "-"
        score = f"{item.score:.3f}" if item.score is not None else "-"
        raw = item.text or ""
        cap = max_chars_per_item
        if cap is None:
            if item.kind == "chunk" and (
                "<table" in raw.lower()
                or re.search(r"表\s*[A-Za-z]?\d+", raw)
                or "unit_id:table" in raw
            ):
                cap = 9000 if for_compose else 4000
            elif item.kind == "chunk":
                cap = 5500 if for_compose else 2800
            else:
                cap = 1800 if for_compose else 1000
        text = raw if len(raw) <= cap else raw[:cap] + "…[truncated]"
        return (
            f"[E{label}] kind={item.kind} score={score} ids={ids} "
            f"file={item.file_path}\n{text}"
        )

    def evidence_text(
        self,
        limit: int | None = None,
        *,
        max_chars_per_item: int | None = None,
        max_total_chars: int | None = None,
        for_compose: bool = False,
    ) -> str:
        """Render evidence bag for the decision or compose LLM.

        Compose mode uses MS/LightRAG-style sections:
        Text units (chunks) first, then Relations, then Entities.
        """
        if not self.evidence:
            return "（证据袋为空）"
        if max_total_chars is None:
            max_total_chars = 32000 if for_compose else 20000
        items = self.evidence if limit is None else self.evidence[: max(0, limit)]

        if for_compose:
            sections = [
                ("## Text units（原文，事实以本节为准）", "chunk"),
                ("## Relations（图关系摘要，仅辅证）", "relationship"),
                ("## Entities（图实体摘要，仅辅证）", "entity"),
            ]
            by_kind: dict[str, list[EvidenceItem]] = {
                "chunk": [],
                "relationship": [],
                "entity": [],
                "other": [],
            }
            for item in items:
                if item.kind in by_kind:
                    by_kind[item.kind].append(item)
                else:
                    by_kind["other"].append(item)

            blocks: list[str] = []
            total = 0
            label = 0
            for title, kind in sections:
                group = by_kind.get(kind) or []
                if not group:
                    continue
                header = title
                if total + len(header) + 2 > max_total_chars and blocks:
                    break
                blocks.append(header)
                total += len(header) + 2
                for item in group:
                    label += 1
                    block = self._format_evidence_item(
                        item,
                        label,
                        for_compose=True,
                        max_chars_per_item=max_chars_per_item,
                    )
                    if total + len(block) > max_total_chars and blocks:
                        blocks.append(
                            f"…另有证据因长度上限未展开；请优先采信 Text units 中 kind=chunk 的原文。"
                        )
                        return "\n\n".join(blocks)
                    blocks.append(block)
                    total += len(block) + 2
            for item in by_kind["other"]:
                label += 1
                block = self._format_evidence_item(
                    item,
                    label,
                    for_compose=True,
                    max_chars_per_item=max_chars_per_item,
                )
                if total + len(block) > max_total_chars:
                    break
                blocks.append(block)
                total += len(block) + 2
            return "\n\n".join(blocks) if blocks else "（证据袋为空）"

        # Decision preview: flat list, preserve bag order (already text-primary).
        blocks = []
        total = 0
        for index, item in enumerate(items, 1):
            block = self._format_evidence_item(
                item,
                index,
                for_compose=False,
                max_chars_per_item=max_chars_per_item,
            )
            if total + len(block) > max_total_chars and blocks:
                blocks.append(
                    f"…另有 {len(items) - index + 1} 条证据因长度上限未展开；"
                    "请主要依据已列出的 [E#]，并优先采信 kind=chunk 的原文。"
                )
                break
            blocks.append(block)
            total += len(block) + 2
        return "\n\n".join(blocks)

    def slot_text(self) -> str:
        if not self.slots:
            return "（无槽位）"
        lines = []
        for slot in self.slots:
            lines.append(f"- {slot.id}: {slot.status} — {slot.description}")
        return "\n".join(lines)

    def add_trace(self, event: str, **payload: Any) -> None:
        item = {"step": self.step, "event": event, **payload}
        self.trace.append(item)
        hook = self.event_hook
        if callable(hook):
            try:
                hook(item, self)
            except Exception:  # noqa: BLE001 — live UI must not break the loop
                pass

    def register_call(self, signature: str) -> bool:
        """Return True if this call looks like a duplicate of a recent one."""
        duplicate = signature in self.recent_calls[-6:]
        self.recent_calls.append(signature)
        return duplicate
