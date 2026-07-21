"""Live terminal rendering of harness trace events (interactive CLI)."""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, TextIO


def _out(msg: str, file: TextIO = sys.stderr, end: str = "\n") -> None:
    print(msg, end=end, file=file, flush=True)


_KEY_LABELS = {
    "relationship": "关系",
    "sub_scenario_count": "子场景数量",
    "sub_scenarios": "子场景",
    "common_pass_behavior": "共同通过行为",
    "common_pass_criteria": "共同合格判据",
    "verification_tests": "验证试验",
    "latest_warning_timing": "最迟预警时机",
    "exceptions": "例外",
    "applicable_vehicle_categories": "适用车型",
    "test_clause": "试验条款",
    "ttc_condition": "TTC 条件",
    "speed_condition": "速度条件",
}


def _format_value_lines(value: Any, *, indent: int = 0) -> list[str]:
    pad = "  " * indent
    if value is None:
        return [f"{pad}（空）"]
    if isinstance(value, dict):
        lines: list[str] = []
        for key, child in value.items():
            label = _KEY_LABELS.get(str(key), str(key))
            if isinstance(child, list):
                lines.append(f"{pad}{label}:")
                for i, item in enumerate(child, 1):
                    lines.append(f"{pad}  {i}. {item}")
            elif isinstance(child, dict):
                lines.append(f"{pad}{label}:")
                lines.extend(_format_value_lines(child, indent=indent + 1))
            else:
                lines.append(f"{pad}{label}: {child}")
        return lines
    if isinstance(value, list):
        return [f"{pad}{i}. {item}" for i, item in enumerate(value, 1)]
    return [f"{pad}{value}"]


def format_final_answer(final: dict[str, Any] | None, refuse: str | None = None) -> str:
    """Clear final block: one header + readable answer body (process log is separate)."""
    sep = "-" * 48
    head = [
        "",
        sep,
        "最终答案",
        sep,
    ]
    if not final:
        head.append(refuse or "（无最终答案）")
        head.append(sep)
        return "\n".join(head)

    answerable = final.get("answerable")
    if answerable is True:
        head.append("能否作答: 是")
    elif answerable is False:
        head.append("能否作答: 否（证据不足或拒答）")
    else:
        head.append("能否作答: （未标明）")

    body = final.get("answer")
    if body is None and answerable is False:
        body = final.get("reason") or refuse or "证据不足"

    head.append("")
    head.append("答案:")
    if body is None:
        head.append("  （无 answer 字段）")
        if final.get("reason"):
            head.append(f"  说明: {final.get('reason')}")
    else:
        for line in _format_value_lines(body, indent=1):
            head.append(line)

    if final.get("reason") and body is not None:
        head.append("")
        head.append(f"说明: {final.get('reason')}")

    cites = final.get("citations")
    if cites:
        head.append(f"引用: {cites}")

    head.append(sep)
    return "\n".join(head)


class LiveSession:
    """Process log on stderr; mute compose token spam so final answer stands alone."""

    def __init__(self, *, verbose: bool = True, file: TextIO = sys.stderr):
        self.verbose = verbose
        self.file = file
        self._llm_role: str | None = None

    def on_token(self, tok: str) -> None:
        # Only stream planning JSON; final answer is printed once at the end.
        if self._llm_role == "compose":
            return
        print(tok, end="", file=self.file, flush=True)

    def on_event(self, item: dict[str, Any], state: Any) -> None:
        event = str(item.get("event") or "")
        step = item.get("step", "?")
        bag_n = len(getattr(state, "evidence", None) or [])
        file = self.file
        verbose = self.verbose

        if event == "start":
            _out(f"\n{'-' * 48}", file=file)
            _out("取证过程", file=file)
            _out(f"问题: {item.get('question') or getattr(state, 'question', '')}", file=file)
            _out(f"{'-' * 48}", file=file)
            return

        if event == "awaiting_agent_plan":
            _out(f"[{step}] 等待规划…", file=file)
            return

        if event == "llm_start":
            role = str(item.get("role") or "llm")
            self._llm_role = role
            if role == "compose":
                _out(f"\n[{step}] 正在生成最终答案…", file=file)
            else:
                _out(f"\n[{step}] 模型规划中（流式）:", file=file)
                _out("  ", file=file, end="")
            return

        if event == "llm_end":
            if self._llm_role != "compose":
                _out("", file=file)
            self._llm_role = None
            return

        if event == "decision":
            dec = item.get("decision") or {}
            action = dec.get("action") or "?"
            args = dec.get("args") if isinstance(dec.get("args"), dict) else {}
            _out(f"[{step}] 规划结果 → {action}", file=file)
            if args:
                q = args.get("query")
                mode = args.get("mode")
                bits = []
                if mode:
                    bits.append(f"mode={mode}")
                if q:
                    qs = str(q)
                    bits.append(f"query={qs if len(qs) < 80 else qs[:80] + '…'}")
                if bits:
                    _out(f"       {', '.join(bits)}", file=file)
            thought = str(dec.get("thought") or "").strip()
            if thought and verbose:
                t = thought if len(thought) <= 120 else thought[:120] + "…"
                _out(f"       想法: {t}", file=file)
            return

        if event == "tool_result":
            tool = item.get("tool") or "?"
            ok = item.get("ok")
            kinds: dict[str, int] = {}
            for ev in getattr(state, "evidence", None) or []:
                kinds[ev.kind] = kinds.get(ev.kind, 0) + 1
            kind_s = ",".join(f"{k}={v}" for k, v in sorted(kinds.items())) or "—"
            _out(
                f"[{step}] 工具 {tool}  ok={ok}  证据袋={bag_n} ({kind_s})",
                file=file,
            )
            return

        if event == "sufficiency_audit":
            _out(
                f"[{step}] 充分性: {item.get('sufficient')}  "
                f"({item.get('reason') or ''})",
                file=file,
            )
            return

        if event in {
            "suggest_compose",
            "force_compose",
            "override_retrieve_to_compose",
            "forced_compose",
        }:
            _out(f"[{step}] 收网: {event}", file=file)
            return

        if event in {"invalid_decision", "llm_error", "force_finalize_max_steps"}:
            _out(f"[{step}] 警告: {event} {item.get('error') or ''}", file=file)
            return


def make_live_printer(*, verbose: bool = True, file: TextIO = sys.stderr) -> LiveSession:
    return LiveSession(verbose=verbose, file=file)


def make_token_printer(file: TextIO = sys.stderr) -> Callable[[str], None]:
    """Backward-compatible: always print tokens (prefer LiveSession.on_token)."""

    def on_token(tok: str) -> None:
        print(tok, end="", file=file, flush=True)

    return on_token
