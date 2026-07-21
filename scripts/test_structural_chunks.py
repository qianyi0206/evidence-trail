#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

from common import ROOT, load_env


ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)


def clean_cell(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def table_rows(content: str) -> list[list[str]]:
    return [
        [clean_cell(cell) for cell in CELL_RE.findall(row)]
        for row in ROW_RE.findall(content)
    ]


def numeric_row(rows: list[list[str]], vehicle_speed: str) -> list[str]:
    matches = [row for row in rows[1:] if row and row[0] == vehicle_speed]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one row for vehicle speed {vehicle_speed}, found {matches}")
    return matches[0]


def main() -> None:
    env = load_env()
    setting = env.get("GB39901_STRUCTURAL_UNITS_FILE", "").strip()
    if not setting:
        raise RuntimeError("GB39901_STRUCTURAL_UNITS_FILE is not configured")
    bundle_path = (ROOT / setting).resolve()
    bundle_path.relative_to(ROOT.resolve())
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    units = bundle.get("units", [])
    tables = {unit["unit_id"]: unit for unit in units if unit.get("kind") == "table"}
    narratives = [unit for unit in units if unit.get("kind") == "narrative"]

    if len(units) != 46 or len(tables) != 23 or len(narratives) != 23:
        raise RuntimeError(
            f"Unexpected structural unit counts: total={len(units)} "
            f"tables={len(tables)} narrative={len(narratives)}"
        )
    if len({unit["file_source"] for unit in units}) != len(units):
        raise RuntimeError("Structural file sources are not unique")
    for unit in tables.values():
        lowered = unit["content"].lower()
        if lowered.count("<table") != 1 or lowered.count("</table>") != 1:
            raise RuntimeError(f"Table was split or combined: {unit['unit_id']}")
        if unit.get("chars", 0) > 9000:
            raise RuntimeError(f"Table exceeds the conservative one-chunk budget: {unit['unit_id']}")
    if any("<table" in unit["content"].lower() for unit in narratives):
        raise RuntimeError("Narrative unit unexpectedly contains an HTML table")

    expected_owner = {
        "table_1": "5.2.1.1",
        "table_2": "5.2.1.2",
        "table_3": "5.2.1.1",
        "table_4": "5.2.1.2",
    }
    for unit_id, clause in expected_owner.items():
        if tables[unit_id]["clause"] != clause:
            raise RuntimeError(f"Wrong clause owner for {unit_id}")

    rows_1 = table_rows(tables["table_1"]["content"])
    rows_2 = table_rows(tables["table_2"]["content"])
    rows_3 = table_rows(tables["table_3"]["content"])
    rows_4 = table_rows(tables["table_4"]["content"])
    expected_facts = {
        "table_1@60": (numeric_row(rows_1, "60"), ["60", "0", "35", "35"]),
        "table_1@80": (numeric_row(rows_1, "80"), ["80", "0", "50", "50"]),
        "table_2@40": (numeric_row(rows_2, "40"), ["40", "0", "0", "10"]),
        "table_2@60": (numeric_row(rows_2, "60"), ["60", "0", "35", "40"]),
        "table_3@80": (numeric_row(rows_3, "80"), ["80", "20", "35", "35"]),
        "table_4@60": (numeric_row(rows_4, "60"), ["60", "20", "0", "10"]),
    }
    mismatches = {
        key: {"actual": actual, "expected": expected}
        for key, (actual, expected) in expected_facts.items()
        if actual != expected
    }
    if mismatches:
        raise RuntimeError(f"Atomic table fact regression: {mismatches}")
    if any(row and row[0] == "80" for row in rows_2[1:] + rows_4[1:]):
        raise RuntimeError("N1 tables unexpectedly contain an 80 km/h vehicle-speed row")

    max_chars = max(unit["chars"] for unit in units)
    print(
        "structural OK "
        f"(46 units, 23 atomic tables, max={max_chars} chars, 6 numeric rows verified)"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"structural FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
