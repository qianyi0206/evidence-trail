from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
FIELDS = (
    ("model", "EMBEDDING_MODEL"),
    ("dimension", "EMBEDDING_DIM"),
    ("token_limit", "EMBEDDING_TOKEN_LIMIT"),
)


@dataclass(frozen=True)
class Comparison:
    name: str
    expected: str | int
    actual: str | int

    @property
    def matches(self) -> bool:
        return self.expected == self.actual


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError(f"Missing environment file: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _inside_root(root: Path, setting: str, *, label: str) -> Path:
    path = (root / setting).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise RuntimeError(f"{label} must stay inside {root}: {setting}") from error
    return path


def load_effective_env(root: Path, profile_env: str) -> dict[str, str]:
    values = _read_env_file(root / ".env")
    profile_path = _inside_root(root, profile_env, label="Profile env")
    values.update(_read_env_file(profile_path))
    return values


def fingerprint_path_for(root: Path, env: dict[str, str]) -> Path:
    workspace = (env.get("WORKSPACE") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", workspace):
        raise RuntimeError(f"Unsafe or missing WORKSPACE in profile: {workspace!r}")
    return root / "state" / f"embedding_fingerprint.{workspace}.json"


def compare_snapshot(
    root: Path,
    profile_env: str,
    *,
    fingerprint_path: Path | None = None,
) -> tuple[Path, list[Comparison]]:
    env = load_effective_env(root, profile_env)
    path = fingerprint_path or fingerprint_path_for(root, env)
    if not path.is_file():
        workspace = (env.get("WORKSPACE") or "").strip()
        workspace_path = root / "data" / "rag_storage" / workspace
        has_existing_index = workspace_path.is_dir() and any(
            item.is_file() for item in workspace_path.rglob("*")
        )
        if has_existing_index:
            raise RuntimeError(
                "Missing snapshot fingerprint for non-empty workspace "
                f"{workspace!r}: {path}. Restore the matching fingerprint or rebuild "
                "into a new/empty workspace."
            )
        return path, []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot read snapshot fingerprint {path}: {error}") from error
    if not isinstance(payload, dict) or payload.get("status") != "ready":
        raise RuntimeError(f"Snapshot fingerprint is not ready: {path}")
    config = payload.get("config")
    if not isinstance(config, dict):
        raise RuntimeError(f"Snapshot fingerprint has no embedding config: {path}")

    comparisons: list[Comparison] = []
    for field, env_name in FIELDS:
        expected = config.get(field)
        raw_actual = (env.get(env_name) or "").strip()
        if expected is None:
            raise RuntimeError(f"Snapshot fingerprint is missing config.{field}: {path}")
        if field in {"dimension", "token_limit"}:
            try:
                expected = int(expected)
                actual: str | int = int(raw_actual)
            except (TypeError, ValueError) as error:
                raise RuntimeError(
                    f"{env_name} must be an integer before snapshot compatibility can be checked"
                ) from error
        else:
            actual = raw_actual
        comparisons.append(Comparison(field, expected, actual))
    return path, comparisons


def main(argv: Sequence[str] | None = None, *, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(
        description="Compare the local embedding configuration with a shipped snapshot."
    )
    parser.add_argument("--profile-env", default=".env.gb39901_v4")
    parser.add_argument("--fingerprint", type=Path)
    args = parser.parse_args(argv)

    fingerprint = args.fingerprint
    if fingerprint is not None and not fingerprint.is_absolute():
        fingerprint = _inside_root(root, str(fingerprint), label="Fingerprint")
    path, comparisons = compare_snapshot(
        root,
        args.profile_env,
        fingerprint_path=fingerprint,
    )
    if not comparisons:
        print(
            "snapshot   SKIPPED "
            f"(no ready fingerprint at {path}; treating this as a rebuild path)"
        )
        return 0

    print(f"snapshot   {path.relative_to(root)}")
    for item in comparisons:
        status = "OK" if item.matches else "MISMATCH"
        print(
            f"  {item.name}: expected={item.expected!r} "
            f"actual={item.actual!r} [{status}]"
        )
    if not all(item.matches for item in comparisons):
        print(
            "snapshot   FAILED: configure EMBEDDING_MODEL, EMBEDDING_DIM, and "
            "EMBEDDING_TOKEN_LIMIT for the shipped snapshot, or use the documented "
            "rebuild path.",
            file=sys.stderr,
        )
        return 1
    print("snapshot   OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"snapshot   FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
