from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)")


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def direct_requirements(
    path: Path,
    seen: set[Path] | None = None,
) -> dict[str, str]:
    path = path.resolve()
    visited = set() if seen is None else seen
    if path in visited:
        raise RuntimeError(f"Recursive requirements include: {path.relative_to(ROOT)}")
    visited.add(path)
    requirements: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            include_path = (path.parent / line[3:].strip()).resolve()
            requirements.update(direct_requirements(include_path, visited))
            continue
        match = REQUIREMENT_RE.fullmatch(line)
        if not match:
            raise RuntimeError(
                f"{path.relative_to(ROOT)}:{line_number} must use an exact == pin"
            )
        requirements[normalized(match.group(1))] = match.group(2)
    visited.remove(path)
    return requirements


def locked_requirements(path: Path) -> dict[str, tuple[str, bool]]:
    locked: dict[str, tuple[str, bool]] = {}
    current_name: str | None = None
    current_version = ""
    current_has_hash = False

    def finish() -> None:
        if current_name is not None:
            locked[current_name] = (current_version, current_has_hash)

    for raw in path.read_text(encoding="utf-8").splitlines():
        match = REQUIREMENT_RE.match(raw)
        if match:
            finish()
            current_name = normalized(match.group(1))
            current_version = match.group(2)
            current_has_hash = "--hash=sha256:" in raw
        elif current_name is not None and "--hash=sha256:" in raw:
            current_has_hash = True
    finish()
    return locked


def validate(source: Path, lock: Path) -> list[str]:
    direct = direct_requirements(source)
    locked = locked_requirements(lock)
    errors: list[str] = []
    for name, version in direct.items():
        locked_entry = locked.get(name)
        if locked_entry is None:
            errors.append(f"{name} is missing from {lock.relative_to(ROOT)}")
            continue
        locked_version, has_hash = locked_entry
        if locked_version != version:
            errors.append(
                f"{name} is {version} in {source.relative_to(ROOT)} but "
                f"{locked_version} in {lock.relative_to(ROOT)}"
            )
        if not has_hash:
            errors.append(f"{name} has no SHA-256 in {lock.relative_to(ROOT)}")
    for name, (_, has_hash) in locked.items():
        if not has_hash:
            errors.append(f"{name} has no SHA-256 in {lock.relative_to(ROOT)}")
    return errors


def main() -> int:
    pairs = [
        (ROOT / "requirements.txt", ROOT / "requirements.lock"),
        (ROOT / "requirements-dev.txt", ROOT / "requirements-dev.lock"),
        (ROOT / "requirements-ui.txt", ROOT / "requirements-ui.lock"),
        (ROOT / "tools" / "requirements.txt", ROOT / "tools" / "requirements.lock"),
    ]
    errors = [
        error
        for source, lock in pairs
        for error in validate(source, lock)
    ]
    if errors:
        for error in errors:
            print(f"dependency-lock-check: {error}", file=sys.stderr)
        return 1
    print("dependency-lock-check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
