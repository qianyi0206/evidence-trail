from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ENV_FILES = {
    ".env.example",
    ".env.gb39901",
    ".env.gb39901_v3",
    ".env.gb39901_v4",
}
SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}
SENSITIVE_NAMES = {".netrc"}

# Keep signatures split so this scanner does not match its own source.
CONTENT_SIGNATURES = {
    "private_key": re.compile(
        ("-----BEGIN " + r"(?:RSA |EC |OPENSSH )?" + "PRIVATE KEY-----").encode()
    ),
    "github_token": re.compile(("gh" + r"[pousr]_[A-Za-z0-9]{20,}").encode()),
    "aws_access_key": re.compile(("AK" + r"IA[0-9A-Z]{16}").encode()),
    "openai_style_key": re.compile(("sk-" + r"[A-Za-z0-9_-]{20,}").encode()),
}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [ROOT / raw.decode() for raw in result.stdout.split(b"\0") if raw]


def forbidden_name(path: Path) -> str | None:
    relative = path.relative_to(ROOT).as_posix()
    if path.name.startswith(".env") and relative not in ALLOWED_ENV_FILES:
        return "environment file"
    if path.suffix.lower() in SENSITIVE_SUFFIXES or path.name in SENSITIVE_NAMES:
        return "credential file"
    return None


def main() -> int:
    findings: list[tuple[str, str]] = []
    for path in tracked_files():
        reason = forbidden_name(path)
        relative = path.relative_to(ROOT).as_posix()
        if reason:
            findings.append((relative, reason))
            continue
        try:
            payload = path.read_bytes()
        except OSError as error:
            findings.append((relative, f"unreadable: {type(error).__name__}"))
            continue
        if len(payload) > 2 * 1024 * 1024:
            continue
        for name, pattern in CONTENT_SIGNATURES.items():
            if pattern.search(payload):
                findings.append((relative, name))

    if findings:
        for relative, reason in findings:
            print(f"tracked-secret-check: {relative}: {reason}", file=sys.stderr)
        return 1
    print("tracked-secret-check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
