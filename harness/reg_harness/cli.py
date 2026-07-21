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
from reg_harness.loop import pretty_print_result, state_to_dict
from reg_harness.runtime import build_stack
from reg_harness.tools.registry import default_registry
from reg_harness.types import AgentState


def _cmd_ask(args: argparse.Namespace) -> int:
    stack = build_stack(profile_env=args.profile_env)
    state = stack.ask(
        args.question,
        policy=args.policy,
        max_steps=args.max_steps,
        bootstrap=bool(args.bootstrap),
    )
    print(pretty_print_result(state))
    if args.dump_trace:
        path = Path(args.dump_trace)
        path.write_text(json.dumps(state_to_dict(state), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"trace written: {path}", file=sys.stderr)
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
    ask.add_argument("--dump-trace", type=str, default=None, help="Write full state JSON to path")
    ask.set_defaults(func=_cmd_ask)

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
