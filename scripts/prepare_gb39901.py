#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from common import ROOT, load_env, safe_workspace, workspace_state_path, write_json_atomic


SOURCE_PATH = ROOT / "corpus" / "prepared" / "GB+39901-2025.pdf_by_PaddleOCR-VL-1.6.md"
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
CLAUSE_RE = re.compile(r"^((?:\d+(?:\.\d+)*)|(?:[ABC](?:\.\d+)+))\b")
PLAIN_CLAUSE_RE = re.compile(r"^((?:\d+(?:\.\d+){1,})|(?:[ABC](?:\.\d+){1,}))\s")
APPENDIX_RE = re.compile(r"附录\s*([ABC])", re.IGNORECASE)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def marker(clause: str) -> str:
    return (
        "<!-- source_id:gb_39901_2025 "
        "source_file:GB+39901-2025.pdf_by_PaddleOCR-VL-1.6.md "
        f"clause:{clause} -->"
    )


def heading_clause(title: str, current_appendix: str | None) -> tuple[str | None, str | None]:
    appendix = APPENDIX_RE.search(title)
    if appendix:
        current_appendix = appendix.group(1).upper()
        return current_appendix, current_appendix
    if title.strip() == "前言":
        return "前言", current_appendix
    match = CLAUSE_RE.match(title.strip())
    if match:
        return match.group(1), current_appendix
    if current_appendix and title.strip() in {"（规范性）", "功能安全要求", "仿真试验要求", "系统功能安全描述要求"}:
        return current_appendix, current_appendix
    return None, current_appendix


def annotate(source: str) -> tuple[str, dict[str, int]]:
    output: list[str] = []
    current_clause = "frontmatter"
    current_appendix: str | None = None
    previous_blank = True
    markers = 0
    table_rows = 0

    for raw_line in source.splitlines():
        heading = HEADING_RE.match(raw_line)
        if heading:
            detected, current_appendix = heading_clause(heading.group(1), current_appendix)
            if detected:
                current_clause = detected
        else:
            plain_clause = PLAIN_CLAUSE_RE.match(raw_line.strip())
            if plain_clause:
                current_clause = plain_clause.group(1)

        line = raw_line
        if "</tr><tr>" in line:
            row_marker = "</tr>\n" + marker(current_clause) + "\n<tr>"
            table_rows += line.count("</tr><tr>")
            markers += line.count("</tr><tr>")
            line = line.replace("</tr><tr>", row_marker)

        if line.strip() and (previous_blank or heading or "<table" in line):
            output.append(marker(current_clause))
            markers += 1
        output.append(line)
        previous_blank = not raw_line.strip()

    annotated = "\n".join(output).rstrip() + "\n"
    return annotated, {"markers": markers, "table_row_markers": table_rows}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Validate inputs and generated output without writing")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = load_env()
    output_setting = env.get("GB39901_SOURCE_DOCUMENT", "").strip()
    if not output_setting:
        raise RuntimeError("GB39901_SOURCE_DOCUMENT is not configured in the active profile")
    output_path = (ROOT / output_setting).resolve()
    output_path.relative_to(ROOT.resolve())
    if not SOURCE_PATH.is_file():
        raise RuntimeError(f"Missing OCR source: {SOURCE_PATH}")

    source = SOURCE_PATH.read_text(encoding="utf-8")
    annotated, stats = annotate(source)
    if "clause:5.2.1" not in annotated or "clause:A.2.3.1" not in annotated or "clause:B.2.5.3" not in annotated:
        raise RuntimeError("Clause annotation missed required performance, safety, or simulation sections")
    if stats["markers"] < 150 or stats["table_row_markers"] < 50:
        raise RuntimeError(f"Insufficient source anchors: {stats}")

    report = {
        "workspace": safe_workspace(env),
        "source_file": str(SOURCE_PATH.relative_to(ROOT)),
        "output_file": str(output_path.relative_to(ROOT)),
        "source_sha256": sha256_text(source),
        "output_sha256": sha256_text(annotated),
        "source_chars": len(source),
        "output_chars": len(annotated),
        **stats,
    }
    if args.check:
        print("gb-prepare CHECK " + json.dumps(report, ensure_ascii=False))
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(annotated, encoding="utf-8")
    report_path = workspace_state_path(env, "prepared_document")
    write_json_atomic(report_path, report)
    print("gb-prepare OK " + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"gb-prepare FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
