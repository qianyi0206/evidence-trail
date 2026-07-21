from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python -m reg_harness.cli` from harness/ without install
_HARNESS_ROOT = Path(__file__).resolve().parents[1]
if str(_HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HARNESS_ROOT))

from reg_harness.config import load_settings
from reg_harness.live import format_final_answer, make_live_printer
from reg_harness.loop import pretty_print_result, state_to_dict
from reg_harness.runtime import build_stack
from reg_harness.tools.registry import default_registry
from reg_harness.types import AgentState


def _run_ask(
    stack,
    question: str,
    *,
    policy: str = "auto",
    max_steps: int | None = None,
    bootstrap: bool = False,
    live: bool = True,
    dump_trace: str | None = None,
    quiet_json: bool = False,
) -> int:
    live_ui = make_live_printer(verbose=True) if live else None
    prev_hook = getattr(stack.chat, "on_token", None)
    if live and live_ui is not None:
        # Stream planning tokens only; compose tokens muted (answer printed once at end).
        stack.chat.on_token = live_ui.on_token
        stack.chat.stream_enabled = True
        print(f"\n>>> {question}", flush=True)
    else:
        stack.chat.on_token = None
    try:
        state = stack.ask(
            question,
            policy=policy,
            max_steps=max_steps,
            bootstrap=bootstrap,
            event_hook=live_ui.on_event if live_ui else None,
        )
    finally:
        stack.chat.on_token = prev_hook

    # Blank line then final answer on stdout — easy to find after process log.
    print(format_final_answer(state.final_answer, state.refuse_reason), flush=True)
    if not quiet_json and not live:
        print(pretty_print_result(state))
    elif live:
        print(
            f"（过程: steps={state.step}, 证据={len(state.evidence)}）",
            flush=True,
        )
    if dump_trace:
        path = Path(dump_trace)
        path.write_text(
            json.dumps(state_to_dict(state), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"trace → {path}", file=sys.stderr, flush=True)
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    stack = build_stack(profile_env=args.profile_env)
    return _run_ask(
        stack,
        args.question,
        policy=args.policy,
        max_steps=args.max_steps,
        bootstrap=bool(args.bootstrap),
        live=bool(args.live),
        dump_trace=args.dump_trace,
        quiet_json=bool(args.live),
    )


def _cmd_chat(args: argparse.Namespace) -> int:
    """Interactive REPL: type questions, watch the evidence chain live."""
    stack = build_stack(profile_env=args.profile_env)
    desc = stack.describe()
    print(
        "\nEvidenceTrail 交互取证  (输入问题回车；quit / exit / 空行退出)\n"
        f"  profile={args.profile_env or 'default'}  "
        f"tools={desc.get('tools')}  "
        f"lightrag={desc.get('lightrag_url')}\n"
        f"  max_steps={args.max_steps or 'default'}  "
        f"catalog={desc.get('catalog_mode')}  "
        f"pilot={desc.get('pilot_heuristics')}\n",
        flush=True,
    )
    turn = 0
    while True:
        try:
            line = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。", flush=True)
            break
        if not line or line.lower() in {"quit", "exit", "q"}:
            print("再见。", flush=True)
            break
        if line.lower() in {"help", "?"}:
            print(
                "命令: 直接输入问题 | quit 退出 | help 帮助\n"
                "过程会实时打印: 规划 → 工具 → 充分性 → 收网 → 答案",
                flush=True,
            )
            continue
        turn += 1
        dump = None
        if args.dump_dir:
            Path(args.dump_dir).mkdir(parents=True, exist_ok=True)
            dump = str(Path(args.dump_dir) / f"turn_{turn:03d}.json")
        try:
            _run_ask(
                stack,
                line,
                policy=args.policy,
                max_steps=args.max_steps,
                bootstrap=bool(args.bootstrap),
                live=True,
                dump_trace=dump,
                quiet_json=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"\n错误: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            print(
                "请确认 make v4-up 已启动，且 .env 中 LLM/向量密钥有效。",
                file=sys.stderr,
                flush=True,
            )
    return 0


def _cmd_retrieve(args: argparse.Namespace) -> int:
    settings = load_settings(profile_env=args.profile_env)
    registry = default_registry(settings)
    state = AgentState(question=args.question)
    tool = "vector_search" if args.mode == "naive" else "graph_search"
    result = registry.run(tool, state, {"query": args.question, "mode": args.mode})
    print(result.content)
    print(f"\nbag_size={len(state.evidence)} ok={result.ok}")
    return 0 if result.ok else 1


def _cmd_lookup(args: argparse.Namespace) -> int:
    settings = load_settings(profile_env=args.profile_env)
    registry = default_registry(settings)
    state = AgentState(question=args.question or "lookup")
    state.meta["intent"] = {"kb": [settings.active_kb]}
    if args.kind == "clause":
        result = registry.run("clause_lookup", state, {"clause": args.target})
    else:
        payload: dict = {"table": args.target}
        if args.vehicle:
            payload["vehicle"] = args.vehicle
        if args.ego_kmh is not None:
            payload["ego_kmh"] = args.ego_kmh
        if args.load_state:
            payload["load_state"] = args.load_state
        if args.scenario:
            payload["scenario"] = args.scenario
        result = registry.run("table_lookup", state, payload)
    print(result.content)
    ids = sorted({eid for item in state.evidence for eid in item.evidence_ids})
    print(f"\nok={result.ok} bag={len(state.evidence)} evidence_ids={ids}")
    return 0 if result.ok else 1


def _cmd_intent(args: argparse.Namespace) -> int:
    from reg_harness.intent import resolve_intent

    settings = load_settings(profile_env=getattr(args, "profile_env", None))
    result = resolve_intent(
        args.question,
        args.policy,
        pilot_heuristics=bool(getattr(settings, "pilot_heuristics", False)),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _cmd_describe(args: argparse.Namespace) -> int:
    stack = build_stack(profile_env=args.profile_env)
    print(json.dumps(stack.describe(), ensure_ascii=False, indent=2))
    return 0


def _cmd_librarian(args: argparse.Namespace) -> int:
    stack = build_stack(profile_env=args.profile_env)
    if args.action == "propose-ingest":
        plan = stack.librarian.propose_ingest(
            args.source_file,
            preferred_profile=args.profile,
            preferred_kb=args.kb,
        )
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.action == "propose-merge":
        sources = [item.strip() for item in args.sources.split(",") if item.strip()]
        plan = stack.librarian.propose_merge(sources, args.target)
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        return 0
    print("unknown librarian action", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regulation Evidence Harness CLI")
    parser.add_argument(
        "--profile-env",
        default=None,
        help="Optional profile file relative to demo/aeb (e.g. .env.gb39901_v4)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="Run the full harness loop on a question")
    ask.add_argument("question", type=str)
    ask.add_argument(
        "--policy",
        default="auto",
        choices=["auto", "simple", "complex", "unanswerable_guard"],
    )
    ask.add_argument("--max-steps", type=int, default=None)
    ask.add_argument(
        "--bootstrap",
        action="store_true",
        help="Optional: force one retrieve before the agent loop (default off)",
    )
    ask.add_argument(
        "--live",
        action="store_true",
        default=True,
        help="Stream pipeline steps to the terminal (default on)",
    )
    ask.add_argument(
        "--no-live",
        action="store_false",
        dest="live",
        help="Only print final JSON (old behavior)",
    )
    ask.add_argument("--dump-trace", type=str, default=None, help="Write full state JSON to path")
    ask.set_defaults(func=_cmd_ask)

    chat = sub.add_parser(
        "chat",
        help="Interactive REPL: type questions and watch the evidence chain live",
    )
    chat.add_argument(
        "--policy",
        default="auto",
        choices=["auto", "simple", "complex", "unanswerable_guard"],
    )
    chat.add_argument("--max-steps", type=int, default=None)
    chat.add_argument("--bootstrap", action="store_true")
    chat.add_argument(
        "--dump-dir",
        type=str,
        default=None,
        help="If set, write turn_001.json traces into this directory",
    )
    chat.set_defaults(func=_cmd_chat)

    retrieve = sub.add_parser("retrieve", help="Call a single LightRAG retrieve tool")
    retrieve.add_argument("question", type=str)
    retrieve.add_argument(
        "--mode",
        default="hybrid",
        choices=["naive", "hybrid", "mix", "local", "global"],
    )
    retrieve.set_defaults(func=_cmd_retrieve)

    lookup = sub.add_parser("lookup", help="Precise clause/table lookup from evidence catalog")
    lookup.add_argument("kind", choices=["clause", "table"])
    lookup.add_argument("target", help="Clause id like 6.11 or table number like 2")
    lookup.add_argument("--question", default="", help="Optional question context for state")
    lookup.add_argument("--vehicle", default=None)
    lookup.add_argument("--ego-kmh", type=float, default=None)
    lookup.add_argument("--load-state", default=None)
    lookup.add_argument("--scenario", default=None)
    lookup.set_defaults(func=_cmd_lookup)

    intent_p = sub.add_parser("intent", help="Show lightweight intent routing result")
    intent_p.add_argument("question", type=str)
    intent_p.add_argument(
        "--policy",
        default="auto",
        choices=["auto", "simple", "complex", "unanswerable_guard"],
    )
    intent_p.set_defaults(func=_cmd_intent)

    describe = sub.add_parser("describe", help="Show wired framework stack (KBs, tools, profiles)")
    describe.set_defaults(func=_cmd_describe)

    lib = sub.add_parser("librarian", help="Offline document onboarding stubs (no heavy ingest)")
    lib.add_argument("action", choices=["propose-ingest", "propose-merge"])
    lib.add_argument("--source-file", default="", help="for propose-ingest")
    lib.add_argument("--profile", default=None, help="schema profile id")
    lib.add_argument("--kb", default=None, help="target kb id")
    lib.add_argument("--sources", default="", help="comma kb ids for propose-merge")
    lib.add_argument("--target", default="gb39901_union", help="merge target kb id")
    lib.set_defaults(func=_cmd_librarian)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
