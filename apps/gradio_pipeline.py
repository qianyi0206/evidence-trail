#!/usr/bin/env python3
"""EvidenceTrail Gradio demo — ask → pipeline timeline → bag → answer + KG shots.

From demo/aeb:
  pip install -r requirements-ui.txt
  cd harness && pip install -e . && cd ..
  make v4-up
  python apps/gradio_pipeline.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "harness"
SHOTS = ROOT / "docs" / "screenshots"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from reg_harness.loop import state_to_dict  # noqa: E402
from reg_harness.runtime import build_stack  # noqa: E402

# Preferred screenshot names (drop files into docs/screenshots/)
SHOT_OVERVIEW = "neo4j-v4-overview.png"
SHOT_FOCUS = "neo4j-v4-focus.png"
SHOT_ALTS = (
    "neo4j-v4-overview.jpg",
    "neo4j-v4-focus.jpg",
    "neo4j-browser.png",
)


def _resolve_profile(profile: str | None) -> str | None:
    if not profile:
        return None
    p = Path(profile)
    if p.is_file():
        return str(p.resolve())
    cand = ROOT / profile
    if cand.is_file():
        return str(cand.resolve())
    return profile


def _find_shots() -> list[Path]:
    found: list[Path] = []
    for name in (SHOT_OVERVIEW, SHOT_FOCUS, *SHOT_ALTS):
        path = SHOTS / name
        if path.is_file() and path not in found:
            found.append(path)
    # Any other neo4j* images
    if SHOTS.is_dir():
        for path in sorted(SHOTS.glob("neo4j*.png")) + sorted(SHOTS.glob("neo4j*.jpg")):
            if path not in found:
                found.append(path)
    return found


def _readable_answer(final: dict[str, Any] | None, refuse: str | None) -> str:
    if not final:
        if refuse:
            return f"**拒答 / 未完成**\n\n{refuse}"
        return "（尚无结果，请先提问）"

    answerable = final.get("answerable")
    reason = final.get("reason") or refuse or ""
    answer = final.get("answer")
    claims = final.get("claims")
    citations = final.get("citations")

    lines: list[str] = []
    if answerable is True:
        lines.append("**状态**: 有据作答")
    elif answerable is False:
        lines.append("**状态**: 拒答 / 证据不足（answerable=false）")
    else:
        lines.append("**状态**: 已返回结果")

    if reason:
        lines.append(f"**说明**: {reason}")

    if answer is not None:
        lines.append("")
        lines.append("**答案内容**:")
        if isinstance(answer, (dict, list)):
            lines.append("```json")
            lines.append(json.dumps(answer, ensure_ascii=False, indent=2))
            lines.append("```")
        else:
            lines.append(str(answer))

    if claims:
        lines.append("")
        lines.append("**原子声明 (claims)**:")
        if isinstance(claims, list):
            for c in claims:
                lines.append(f"- {c}")
        else:
            lines.append(str(claims))

    if citations:
        lines.append("")
        lines.append(f"**引用**: {citations}")

    return "\n".join(lines)


def _format_pipeline(trace: list[dict[str, Any]]) -> str:
    if not trace:
        return "（无轨迹）"
    lines: list[str] = ["## 流水线轨迹", ""]
    step_i = 0
    for item in trace:
        event = str(item.get("event") or "")
        if event == "decision":
            step_i += 1
            dec = item.get("decision") or {}
            action = dec.get("action") or "?"
            args = dec.get("args") if isinstance(dec.get("args"), dict) else {}
            thought = str(dec.get("thought") or "")[:200]
            lines.append(f"### {step_i}. 规划 → `{action}`")
            if args:
                q = args.get("query") or args.get("mode")
                if q:
                    lines.append(f"- query/mode: `{q}`")
                else:
                    lines.append(f"- args: `{json.dumps(args, ensure_ascii=False)[:180]}`")
            if thought:
                lines.append(f"- thought: {thought}")
            lines.append("")
        elif event == "tool_result":
            tool = item.get("tool") or "?"
            ok = item.get("ok")
            content = str(item.get("content") or "")[:360].replace("\n", " ")
            lines.append(f"- 工具 **{tool}** · ok={ok}")
            if content:
                lines.append(f"  - {content}")
            lines.append("")
        elif event == "sufficiency_audit":
            lines.append(
                f"- **充分性**: sufficient=`{item.get('sufficient')}` · "
                f"{item.get('reason') or ''} · "
                f"stagnant={item.get('stagnant_rounds')} · "
                f"dup={item.get('duplicate_streak')}"
            )
            lines.append("")
        elif event in {
            "force_compose",
            "override_retrieve_to_compose",
            "suggest_compose",
        }:
            lines.append(
                f"- **收网** `{event}` "
                f"{item.get('reason') or item.get('force_compose_reason') or ''}"
            )
            lines.append("")
        elif event in {"invalid_decision", "llm_error", "force_finalize_max_steps"}:
            lines.append(f"- **控制** `{event}`")
            lines.append("")
    return "\n".join(lines)


def _format_evidence(full_state: Any) -> str:
    items = getattr(full_state, "evidence", None) or []
    if not items:
        return "（证据袋为空）"
    by_kind: dict[str, int] = {}
    for it in items:
        by_kind[it.kind] = by_kind.get(it.kind, 0) + 1
    lines = [
        f"**条数**: {len(items)}",
        "**按 kind**: " + ", ".join(f"`{k}`={v}" for k, v in sorted(by_kind.items())),
        "",
        "事实与数值以 **chunk（原文）** 为准；entity / relationship 为图摘要辅证。",
        "",
    ]
    # Prefer chunks first in display
    ordered = sorted(
        enumerate(items, 1),
        key=lambda pair: (0 if pair[1].kind == "chunk" else 1, pair[0]),
    )
    for orig_i, it in ordered[:14]:
        preview = (it.text or "").replace("\n", " ").strip()
        if len(preview) > 240:
            preview = preview[:240] + "…"
        src = it.source_tool or ""
        lines.append(
            f"**[{orig_i}]** `{it.kind}`"
            + (f" · {src}" if src else "")
            + (f" · score={it.score:.3f}" if it.score is not None else "")
        )
        lines.append(f"> {preview}")
        lines.append("")
    if len(items) > 14:
        lines.append(f"_… 另有 {len(items) - 14} 条未展开_")
    return "\n".join(lines)


def _pipeline_bar(trace: list[dict[str, Any]]) -> str:
    events = [str(t.get("event") or "") for t in trace]
    stages = [
        ("规划", any(e == "decision" for e in events)),
        ("检索/入袋", any(e == "tool_result" for e in events)),
        ("充分性", any(e == "sufficiency_audit" for e in events)),
        (
            "收网",
            any(
                e
                in {
                    "force_compose",
                    "override_retrieve_to_compose",
                    "suggest_compose",
                }
                for e in events
            ),
        ),
        (
            "作答/拒答",
            any(
                "compose" in e or "finalize" in e or e == "force_finalize_max_steps"
                for e in events
            ),
        ),
    ]
    return " → ".join(("● " if hit else "○ ") + name for name, hit in stages)


def _kg_caption() -> str:
    shots = _find_shots()
    lines = [
        "## v4 知识图谱（静态截图）",
        "",
        "Workspace: `aeb_gb39901_v4_relation_guard` · 本地 Neo4j Browser 截图，**非**前端实时拉图。",
        "图用于定位与扩关联；作答时回源 **chunk 原文**（图求广、文答题）。",
        "",
    ]
    if not shots:
        lines.extend(
            [
                f"_尚未找到截图。请将 v4 总览图放到_ `{SHOTS.relative_to(ROOT) / SHOT_OVERVIEW}`",
                f"_可选局部图：_ `{SHOTS.relative_to(ROOT) / SHOT_FOCUS}`",
                "",
                "截图后刷新本页即可显示。",
            ]
        )
    else:
        lines.append(f"已加载 **{len(shots)}** 张： " + ", ".join(f"`{p.name}`" for p in shots))
    return "\n".join(lines)


class DemoApp:
    def __init__(self, profile_env: str | None):
        self.profile_env = _resolve_profile(profile_env)
        self._stack = None
        self._last_profile: str | None = None

    def stack(self, profile_env: str | None = None):
        resolved = _resolve_profile(profile_env) if profile_env is not None else self.profile_env
        if self._stack is None or resolved != self._last_profile:
            self.profile_env = resolved
            self._last_profile = resolved
            self._stack = build_stack(profile_env=resolved)
        return self._stack

    def run(
        self, question: str, max_steps: int, profile_env: str | None
    ) -> tuple[str, str, str, str, str]:
        question = (question or "").strip()
        if not question:
            empty = "请输入问题，或点下方示例。"
            return empty, "", "", "", "{}"

        try:
            state = self.stack(profile_env).ask(
                question,
                max_steps=int(max_steps) if max_steps else None,
            )
        except Exception as exc:  # noqa: BLE001
            err = (
                f"### 运行失败\n\n`{type(exc).__name__}: {exc}`\n\n"
                "请确认：\n"
                "1. 已在 `demo/aeb` 执行 `make v4-up`\n"
                "2. `.env` 中 LLM / Embedding / Neo4j 配置有效\n"
                "3. LightRAG 健康检查：http://127.0.0.1:9621/health\n"
            )
            return err, "", "", "", json.dumps({"error": str(exc)}, ensure_ascii=False)

        readable = _readable_answer(state.final_answer, state.refuse_reason)
        overview = (
            f"**步数** {state.step} · **done** `{state.done}` · **phase** `{state.phase}`  \n"
            f"**流程** {_pipeline_bar(list(state.trace or []))}  \n"
            f"**证据条数** {len(state.evidence)} · "
            f"**refuse** {state.refuse_reason or '—'}"
        )
        pipeline = _format_pipeline(list(state.trace or []))
        evidence = _format_evidence(state)
        raw = json.dumps(
            {
                "question": state.question,
                "steps": state.step,
                "evidence_count": len(state.evidence),
                "trace_events": [t.get("event") for t in state.trace],
                "final_answer": state.final_answer,
                "refuse_reason": state.refuse_reason,
            },
            ensure_ascii=False,
            indent=2,
        )
        return readable, overview, pipeline, evidence, raw


def build_ui(profile_env: str | None, share: bool, server_port: int) -> None:
    try:
        import gradio as gr
    except ImportError as exc:
        raise SystemExit(
            "需要 Gradio：pip install -r requirements-ui.txt\n" + str(exc)
        ) from exc

    demo = DemoApp(profile_env)
    default_profile = profile_env or str(ROOT / ".env.gb39901_v4")
    examples = [
        ["GB 39901—2025 适用于哪两类汽车？"],
        ["完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。"],
        [
            "M1 类试验车辆以 60 km/h、静止车辆目标、最大设计总质量状态试验时，"
            "允许的最大相对碰撞速度是多少？"
        ],
        ["制造商能否完全用仿真替代 6.11 的五项误响应试验？如果可以，需要满足哪些条件？"],
    ]
    shot_paths = [str(p) for p in _find_shots()]

    with gr.Blocks(
        title="EvidenceTrail · 取证演示",
        theme=gr.themes.Soft(),
        css=".wrap {max-width: 1100px; margin: auto;}",
    ) as app:
        with gr.Column(elem_classes=["wrap"]):
            gr.Markdown(
                f"""
# EvidenceTrail · 取证流水线演示

**GB 39901 v4** · 图求广、文答题 · 证据不足则拒答  

底层调用 Harness Agent（规划 → 图/向量检索 → 证据袋与回源 → 充分性收网 → compose / 门控）。  
默认 **skill 路径**（不加载金标 catalog）。需本机 `make v4-up`。

profile: `{Path(default_profile).name if default_profile else "—"}`
                """
            )

            with gr.Row():
                with gr.Column(scale=4):
                    q = gr.Textbox(
                        label="问题",
                        lines=4,
                        placeholder="输入法规相关问题，或点选示例…",
                    )
                    with gr.Row():
                        steps = gr.Slider(4, 12, value=6, step=1, label="max_steps")
                        profile = gr.Textbox(
                            label="profile_env",
                            value=default_profile,
                            scale=2,
                        )
                    btn = gr.Button("开始取证", variant="primary")
                    gr.Examples(examples=examples, inputs=[q], label="示例题")
                with gr.Column(scale=5):
                    overview = gr.Markdown(value="*运行后显示步数与流程覆盖*")
                    answer_md = gr.Markdown(label="最终答案", value="*等待提问*")

            with gr.Accordion("流水线轨迹", open=True):
                pipeline = gr.Markdown()

            with gr.Accordion("证据袋摘要", open=True):
                evidence = gr.Markdown()

            with gr.Accordion("调试 JSON / 精简 trace", open=False):
                raw = gr.Code(language="json", label="trace 摘要")

            gr.Markdown(_kg_caption())
            if shot_paths:
                gr.Gallery(
                    value=shot_paths,
                    label="Neo4j v4 截图",
                    columns=min(2, len(shot_paths)),
                    height=360,
                    object_fit="contain",
                )
            else:
                gr.Markdown(
                    f"将截图保存为：\n"
                    f"- `{SHOTS / SHOT_OVERVIEW}`\n"
                    f"- `{SHOTS / SHOT_FOCUS}`（可选）\n"
                    f"然后重启本应用。"
                )

            gr.Markdown(
                "架构：[docs/architecture.svg](../docs/architecture.svg) · "
                "说明：[apps/README.md](README.md)"
            )

        def _on_run(question: str, max_steps: float, profile_path: str):
            return demo.run(question, int(max_steps), profile_path)

        btn.click(
            _on_run,
            inputs=[q, steps, profile],
            outputs=[answer_md, overview, pipeline, evidence, raw],
        )

    app.queue()
    # Some agent/sandbox environments fail Gradio's post-bind localhost probe.
    # Treat probe as OK so local URL still works for the host browser.
    try:
        import gradio.networking as _gradio_networking

        _gradio_networking.url_ok = lambda _url: True  # type: ignore[assignment]
    except Exception:
        pass
    print(f"Gradio UI → http://127.0.0.1:{server_port}", flush=True)
    app.launch(
        server_name="127.0.0.1",
        server_port=server_port,
        share=share,
        show_error=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="EvidenceTrail Gradio pipeline demo")
    parser.add_argument(
        "--profile-env",
        default=".env.gb39901_v4",
        help="Env profile (path relative to demo/aeb or absolute)",
    )
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()
    build_ui(
        profile_env=args.profile_env,
        share=bool(args.share),
        server_port=args.port,
    )


if __name__ == "__main__":
    main()
