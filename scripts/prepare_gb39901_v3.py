#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

from common import ROOT, load_env, safe_workspace, workspace_state_path, write_json_atomic


SOURCE_PATH = ROOT / "corpus" / "prepared" / "GB+39901-2025.pdf_by_PaddleOCR-VL-1.6.md"
SOURCE_ID = "gb_39901_2025"
SOURCE_NAME = SOURCE_PATH.name
TABLE_RE = re.compile(r"<table\b[\s\S]*?</table>", re.IGNORECASE)
CAPTION_RE = re.compile(
    r"<div[^>]*>\s*<div[^>]*>\s*(?P<title>表\s*(?:\d+|[ABC]\s*\.\s*\d+)[^<]*)"
    r"</div>\s*</div>",
    re.IGNORECASE,
)
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
CLAUSE_RE = re.compile(r"^((?:\d+(?:\.\d+)*)|(?:[ABC](?:\.\d+)+))\b")
PLAIN_CLAUSE_RE = re.compile(r"^((?:\d+(?:\.\d+){1,})|(?:[ABC](?:\.\d+){1,}))\s")
APPENDIX_RE = re.compile(r"附录\s*([ABC])", re.IGNORECASE)

TABLE_CLAUSE = {
    "1": "5.2.1.1",
    "2": "5.2.1.2",
    "3": "5.2.1.1",
    "4": "5.2.1.2",
    "5": "5.2.1.1",
    "6": "5.2.1.2",
    "7": "5.2.2",
    "8": "5.2.2",
    "9": "5.2.3",
    "10": "5.2.3",
    "11": "5.2.4",
    "12": "5.2.4",
    "13": "6.5",
    "14": "6.5",
    "15": "6.6",
    "16": "6.6",
    "17": "6.7",
    "18": "6.8",
    "19": "6.9",
    "20": "6.10",
    "A.1": "A.2.3.1",
    "A.2": "A.3.3",
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    if current_appendix and title.strip() in {
        "（规范性）",
        "功能安全要求",
        "仿真试验要求",
        "系统功能安全描述要求",
    }:
        return current_appendix, current_appendix
    return None, current_appendix


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def table_id(title: str) -> str:
    match = re.search(r"表\s*(\d+|[ABC]\s*\.\s*\d+)", title, re.IGNORECASE)
    if not match:
        raise RuntimeError(f"Cannot identify table number: {title}")
    return re.sub(r"\s+", "", match.group(1)).upper()


def table_role(identifier: str) -> str:
    if identifier.isdigit() and 1 <= int(identifier) <= 12:
        return "performance_limit"
    if identifier.isdigit() and 13 <= int(identifier) <= 20:
        return "test_input"
    if identifier == "A.1":
        return "functional_safety_goal"
    if identifier == "A.2":
        return "functional_safety_verification"
    return "regulatory_table"


def vehicle_categories(title: str) -> list[str]:
    normalized = title.replace(" ", "")
    categories = []
    if "M_{1}" in normalized or "M1" in normalized:
        categories.append("M1")
    if "N_{1}" in normalized or "N1" in normalized:
        categories.append("N1")
    return categories


def marker(clause: str, extra: str = "") -> str:
    suffix = f" {extra.strip()}" if extra.strip() else ""
    return (
        f"<!-- source_id:{SOURCE_ID} source_file:{SOURCE_NAME} "
        f"clause:{clause}{suffix} -->"
    )


def split_narrative_blocks(
    text: str,
    current_clause: str,
    current_appendix: str | None,
) -> tuple[list[dict[str, str]], str, str | None]:
    blocks: list[dict[str, str]] = []
    lines: list[str] = []
    block_clause = current_clause

    def flush() -> None:
        nonlocal lines
        content = "\n".join(lines).strip()
        if content:
            blocks.append({"kind": "narrative", "clause": block_clause, "content": content})
        lines = []

    for raw_line in text.splitlines():
        detected: str | None = None
        heading = HEADING_RE.match(raw_line)
        if heading:
            detected, current_appendix = heading_clause(heading.group(1), current_appendix)
        else:
            plain = PLAIN_CLAUSE_RE.match(raw_line.strip())
            if plain:
                detected = plain.group(1)
        if detected and detected != current_clause:
            flush()
            current_clause = detected
            block_clause = detected
        lines.append(raw_line)
    flush()
    return blocks, current_clause, current_appendix


def split_large_narrative(block: dict[str, str], max_chars: int) -> list[dict[str, str]]:
    content = block["content"].strip()
    if len(content) <= max_chars:
        return [block]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
    parts: list[dict[str, str]] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                parts.append({**block, "content": "\n\n".join(current)})
                current, current_len = [], 0
            for start in range(0, len(paragraph), max_chars):
                parts.append({**block, "content": paragraph[start : start + max_chars]})
            continue
        added = len(paragraph) + (2 if current else 0)
        if current and current_len + added > max_chars:
            parts.append({**block, "content": "\n\n".join(current)})
            current, current_len = [], 0
        current.append(paragraph)
        current_len += len(paragraph) + (2 if len(current) > 1 else 0)
    if current:
        parts.append({**block, "content": "\n\n".join(current)})
    return parts


def structural_items(source: str, narrative_max_chars: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor = 0
    current_clause = "frontmatter"
    current_appendix: str | None = None
    table_occurrences: dict[str, int] = {}

    for table_match in TABLE_RE.finditer(source):
        captions = list(CAPTION_RE.finditer(source, cursor, table_match.start()))
        if not captions:
            raise RuntimeError(f"Table at offset {table_match.start()} has no preceding caption")
        caption = captions[-1]
        narrative = source[cursor : caption.start()]
        blocks, current_clause, current_appendix = split_narrative_blocks(
            narrative, current_clause, current_appendix
        )
        for block in blocks:
            items.extend(split_large_narrative(block, narrative_max_chars))

        raw_title = caption.group("title")
        title = compact_text(raw_title)
        identifier = table_id(title)
        table_occurrences[identifier] = table_occurrences.get(identifier, 0) + 1
        occurrence = table_occurrences[identifier]
        owner_clause = TABLE_CLAUSE.get(identifier)
        if not owner_clause:
            raise RuntimeError(f"Missing owner clause mapping for table {identifier}")
        between = source[caption.end() : table_match.start()].strip()
        categories = vehicle_categories(raw_title)
        items.append(
            {
                "kind": "table",
                "clause": owner_clause,
                "table_id": identifier,
                "part": occurrence,
                "title": title,
                "role": table_role(identifier),
                "vehicle_categories": categories,
                "content": between,
                "html": table_match.group(0),
            }
        )
        cursor = table_match.end()

    tail = source[cursor:]
    blocks, _, _ = split_narrative_blocks(tail, current_clause, current_appendix)
    for block in blocks:
        items.extend(split_large_narrative(block, narrative_max_chars))
    return items


def build_units(items: list[dict[str, Any]], narrative_unit_chars: int) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    narrative_buffer: list[str] = []
    narrative_chars = 0
    narrative_index = 0

    def add_unit(unit_id: str, kind: str, clause: str, content: str, **metadata: Any) -> None:
        file_source = SOURCE_NAME.replace(".md", f"__{unit_id}.md")
        units.append(
            {
                "unit_id": unit_id,
                "kind": kind,
                "source_id": SOURCE_ID,
                "source_file": SOURCE_NAME,
                "file_source": file_source,
                "clause": clause,
                "chars": len(content),
                "sha256": sha256_text(content),
                "content": content.rstrip() + "\n",
                **metadata,
            }
        )

    def flush_narrative() -> None:
        nonlocal narrative_buffer, narrative_chars, narrative_index
        if not narrative_buffer:
            return
        narrative_index += 1
        unit_id = f"narrative_{narrative_index:03d}"
        body = "\n\n".join(narrative_buffer).strip()
        content = marker("multiple", f"unit_id:{unit_id} kind:narrative") + "\n" + body
        add_unit(unit_id, "narrative", "multiple", content)
        narrative_buffer, narrative_chars = [], 0

    for item in items:
        if item["kind"] == "table":
            flush_narrative()
            identifier = item["table_id"]
            safe_table = identifier.replace(".", "_").lower()
            suffix = f"_part_{item['part']}" if item["part"] > 1 else ""
            unit_id = f"table_{safe_table}{suffix}"
            categories = ",".join(item["vehicle_categories"]) or "未指定"
            metadata_lines = [
                marker(
                    item["clause"],
                    f"unit_id:{unit_id} kind:table table:{identifier}",
                ),
                f"## {item['title']}",
                f"所属条款：{item['clause']}",
                f"表格角色：{item['role']}",
                f"车辆类别：{categories}",
            ]
            if item["content"]:
                metadata_lines.append(item["content"])
            metadata_lines.append(item["html"])
            content = "\n\n".join(metadata_lines)
            add_unit(
                unit_id,
                "table",
                item["clause"],
                content,
                table_id=identifier,
                table_part=item["part"],
                title=item["title"],
                role=item["role"],
                vehicle_categories=item["vehicle_categories"],
            )
            continue

        block = marker(item["clause"]) + "\n" + item["content"].strip()
        added = len(block) + (2 if narrative_buffer else 0)
        if narrative_buffer and narrative_chars + added > narrative_unit_chars:
            flush_narrative()
        narrative_buffer.append(block)
        narrative_chars += len(block) + (2 if len(narrative_buffer) > 1 else 0)
    flush_narrative()
    return units


def validate_units(units: list[dict[str, Any]], max_unit_chars: int) -> None:
    if len({unit["unit_id"] for unit in units}) != len(units):
        raise RuntimeError("Structural unit IDs are not unique")
    if len({unit["file_source"] for unit in units}) != len(units):
        raise RuntimeError("Structural unit file sources are not unique")
    table_units = [unit for unit in units if unit["kind"] == "table"]
    if len(table_units) != 23:
        raise RuntimeError(f"Expected 23 atomic table units, found {len(table_units)}")
    for unit in table_units:
        content = unit["content"]
        if content.lower().count("<table") != 1 or content.lower().count("</table>") != 1:
            raise RuntimeError(f"Table unit is not atomic: {unit['unit_id']}")
        if "<tr" not in content or "<td" not in content:
            raise RuntimeError(f"Table unit lacks rows or headers: {unit['unit_id']}")
    oversized = [(unit["unit_id"], unit["chars"]) for unit in units if unit["chars"] > max_unit_chars]
    if oversized:
        raise RuntimeError(f"Structural units exceed conservative character budget: {oversized}")
    expected = {"table_1": "5.2.1.1", "table_2": "5.2.1.2", "table_3": "5.2.1.1", "table_4": "5.2.1.2"}
    actual = {unit["unit_id"]: unit["clause"] for unit in table_units}
    for unit_id, clause in expected.items():
        if actual.get(unit_id) != clause:
            raise RuntimeError(f"Wrong owner clause for {unit_id}: {actual.get(unit_id)} != {clause}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--narrative-block-chars", type=int, default=2800)
    parser.add_argument("--narrative-unit-chars", type=int, default=4200)
    parser.add_argument("--max-unit-chars", type=int, default=9000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = load_env()
    bundle_setting = env.get("GB39901_STRUCTURAL_UNITS_FILE", "").strip()
    if not bundle_setting:
        raise RuntimeError("GB39901_STRUCTURAL_UNITS_FILE is not configured in the active profile")
    bundle_path = (ROOT / bundle_setting).resolve()
    bundle_path.relative_to(ROOT.resolve())
    if not SOURCE_PATH.is_file():
        raise RuntimeError(f"Missing OCR source: {SOURCE_PATH}")

    source = SOURCE_PATH.read_text(encoding="utf-8")
    items = structural_items(source, args.narrative_block_chars)
    units = build_units(items, args.narrative_unit_chars)
    validate_units(units, args.max_unit_chars)
    table_units = [unit for unit in units if unit["kind"] == "table"]
    report = {
        "workspace": safe_workspace(env),
        "source_file": str(SOURCE_PATH.relative_to(ROOT)),
        "source_sha256": sha256_text(source),
        "unit_count": len(units),
        "table_units": len(table_units),
        "narrative_units": len(units) - len(table_units),
        "max_unit_chars": max(unit["chars"] for unit in units),
        "total_unit_chars": sum(unit["chars"] for unit in units),
        "bundle_file": str(bundle_path.relative_to(ROOT)),
    }
    if args.check:
        print("v3-prepare CHECK " + json.dumps(report, ensure_ascii=False))
        return

    units_dir = bundle_path.parent / "units"
    units_dir.mkdir(parents=True, exist_ok=True)
    for unit in units:
        (units_dir / unit["file_source"]).write_text(unit["content"], encoding="utf-8")
    bundle = {
        "schema_version": 1,
        "strategy": "atomic_html_tables_and_structural_narrative_units",
        "source_id": SOURCE_ID,
        "source_file": SOURCE_NAME,
        "source_sha256": sha256_text(source),
        "units": units,
    }
    write_json_atomic(bundle_path, bundle)
    report_path = workspace_state_path(env, "prepared_document")
    write_json_atomic(report_path, report)
    print("v3-prepare OK " + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"v3-prepare FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
