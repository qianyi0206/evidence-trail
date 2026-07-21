#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from common import ROOT, api_headers, lightrag_url, load_env, safe_workspace, write_json_atomic


CASES_PATH = ROOT / "tests" / "fact_qa_cases_v3.yaml"


def parse_json_answer(answer: str) -> dict:
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", answer.strip(), flags=re.IGNORECASE)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*?\}", stripped)
        if not match:
            raise RuntimeError(f"Answer does not contain a JSON object: {answer}")
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict) or "value" not in payload:
        raise RuntimeError(f"Answer JSON lacks value: {payload}")
    return payload


def referenced_names(references: list[dict]) -> set[str]:
    return {Path(item.get("file_path", "")).name for item in references}


def main() -> None:
    env = load_env()
    workspace = safe_workspace(env)
    data = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    if len(cases) != 8 or len({case["id"] for case in cases}) != 8:
        raise RuntimeError("Expected exactly 8 unique fact QA cases")

    prompt = (
        "只根据检索到的 GB 39901-2025 表格回答，不得使用模型常识补全。"
        "区分试验车辆速度、目标速度、行车质量和最大设计总质量。"
        "只输出一个 JSON 对象，格式严格为 "
        '{"value": 数值, "unit": "km/h", "evidence": "表号和条件"}。'
    )
    results: list[dict] = []
    failures: list[str] = []
    with httpx.Client(timeout=300) as client:
        for case in cases:
            response = client.post(
                lightrag_url(env, "/query"),
                headers=api_headers(env),
                json={
                    "query": case["question"],
                    "mode": "mix",
                    "response_type": "Single Paragraph",
                    "include_references": True,
                    "include_chunk_content": True,
                    "enable_rerank": False,
                    "user_prompt": prompt,
                },
            )
            response.raise_for_status()
            payload = response.json()
            answer = payload.get("response", "").strip()
            references = payload.get("references") or []
            names = referenced_names(references)
            parse_error = None
            parsed: dict = {}
            try:
                parsed = parse_json_answer(answer)
                actual = float(parsed["value"])
            except Exception as error:
                actual = math.nan
                parse_error = str(error)
            expected = float(case["expected_value"])
            value_ok = math.isfinite(actual) and math.isclose(actual, expected, abs_tol=1e-9)
            source_ok = case["expected_file_source"] in names
            passed = value_ok and source_ok
            if not passed:
                failures.append(case["id"])
            results.append(
                {
                    "case_id": case["id"],
                    "passed": passed,
                    "expected_value": expected,
                    "actual_value": actual if math.isfinite(actual) else None,
                    "expected_source": case["expected_file_source"],
                    "referenced_sources": sorted(names),
                    "value_ok": value_ok,
                    "source_ok": source_ok,
                    "parse_error": parse_error,
                    "answer": answer,
                    "references": references,
                }
            )
            marker = "PASS" if passed else "FAIL"
            actual_text = str(actual) if math.isfinite(actual) else "unparsed"
            print(
                f"fact-qa    {marker} {case['id']} "
                f"expected={expected:g} actual={actual_text} source={source_ok}"
            )

    completed_at = datetime.now(timezone.utc)
    report = {
        "completed_at": completed_at.isoformat(),
        "workspace": workspace,
        "passed": len(cases) - len(failures),
        "total": len(cases),
        "failures": failures,
        "results": results,
    }
    output_path = ROOT / "results" / (
        f"fact_qa_{workspace}_{completed_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    write_json_atomic(output_path, report)
    if failures:
        raise RuntimeError(
            f"Fact-level QA passed {len(cases) - len(failures)}/{len(cases)}; "
            f"failed={failures}; report={output_path}"
        )
    print(f"fact-qa    OK (8/8 exact values with table-unit citations); report={output_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"fact-qa    FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
