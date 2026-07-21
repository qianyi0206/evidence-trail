from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from common import (
    MANIFEST_PATH,
    ROOT,
    STATE_DIR,
    active_documents,
    api_headers,
    ingest_path_for_record,
    lightrag_url,
    load_env,
    neo4j_query,
    safe_workspace,
    workspace_state_path,
    write_json_atomic,
)

DOMAIN_SCHEMA_PATH = ROOT / "config" / "domain_schema.yml"
GB_SCHEMA_PATH = ROOT / "config" / "gb_39901_2025_schema.yml"
QA_CASES_PATH = ROOT / "tests" / "qa_cases.yaml"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise RuntimeError("Missing corpus/manifest.json")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_structural_bundle(env: dict[str, str]) -> dict | None:
    setting = env.get("GB39901_STRUCTURAL_UNITS_FILE", "").strip()
    if not setting:
        return None
    path = (ROOT / setting).resolve()
    path.relative_to(ROOT.resolve())
    if not path.is_file():
        raise RuntimeError(f"Missing structural unit bundle: {path}")
    bundle = json.loads(path.read_text(encoding="utf-8"))
    units = bundle.get("units", [])
    if not units or len({unit.get("file_source") for unit in units}) != len(units):
        raise RuntimeError("Structural unit bundle is empty or has duplicate file sources")
    return bundle


def expected_document_names(env: dict[str, str], manifest: dict) -> set[str]:
    bundle = load_structural_bundle(env)
    if bundle:
        return {unit["file_source"] for unit in bundle["units"]}
    return {
        Path(item["prepared_file"]).name
        for item in active_documents(manifest)
    }


def offline_checks() -> dict:
    manifest = load_manifest()
    documents = manifest.get("documents", [])
    if not documents:
        raise RuntimeError("Corpus manifest contains no documents")
    if len({item["source_id"] for item in documents}) != len(documents):
        raise RuntimeError("Corpus source IDs are not unique")
    prepared_files = [item.get("prepared_file") for item in documents]
    if None in prepared_files or len(set(prepared_files)) != len(documents):
        raise RuntimeError("Prepared document paths are missing or not unique")
    prepared_hashes = [item.get("prepared_sha256") for item in documents]
    if None in prepared_hashes or len(set(prepared_hashes)) != len(documents):
        raise RuntimeError("Prepared document hashes are missing or not unique")

    enabled = active_documents(manifest)
    enabled_source_ids = {record["source_id"] for record in enabled}
    details = []
    raw_documents = 0
    for record in documents:
        prepared_path = ROOT / record["prepared_file"]
        if not prepared_path.is_file():
            raise RuntimeError(f"Missing prepared file for {record['source_id']}")
        if "local_file" in record:
            raw_documents += 1
            raw_path = ROOT / record["local_file"]
            if not raw_path.is_file():
                raise RuntimeError(f"Missing source file for {record['source_id']}")
            if sha256_file(raw_path) != record["sha256"]:
                raise RuntimeError(f"Raw checksum mismatch for {record['source_id']}")
        if sha256_file(prepared_path) != record["prepared_sha256"]:
            raise RuntimeError(f"Prepared checksum mismatch for {record['source_id']}")
        text = prepared_path.read_text(encoding="utf-8")
        markers = len(re.findall(r"<!-- source_id:[^ ]+ page:\d+ -->", text))
        page_count = record.get("page_count")
        if isinstance(page_count, int) and markers != page_count:
            raise RuntimeError(
                f"Page marker mismatch for {record['source_id']}: {markers} != {page_count}"
            )
        details.append(
            {
                "source_id": record["source_id"],
                "enabled": record.get("enabled", True),
                "pages": page_count,
                "page_traceability": record.get("page_traceability"),
                "text_chars": record["text_chars"],
            }
        )

    domain_schema = yaml.safe_load(DOMAIN_SCHEMA_PATH.read_text(encoding="utf-8"))
    entity_types = domain_schema.get("entity_types", [])
    if len(entity_types) < 10 or "TestScenario" not in entity_types or "Threshold" not in entity_types:
        raise RuntimeError("Domain schema is missing expected AEB entity types")
    gb_schema = yaml.safe_load(GB_SCHEMA_PATH.read_text(encoding="utf-8"))
    gb_types = gb_schema.get("entity_types", [])
    relation_types = gb_schema.get("relations_of_interest", [])
    relation_definitions = gb_schema.get("relation_definitions", {})
    if len(gb_types) != 34 or len(relation_types) != 42:
        raise RuntimeError("GB 39901 schema does not contain the expected 34 entities and 42 relations")
    if set(relation_types) != set(relation_definitions):
        raise RuntimeError("GB 39901 relation whitelist and definitions are inconsistent")

    qa = yaml.safe_load(QA_CASES_PATH.read_text(encoding="utf-8"))
    cases = qa.get("cases", [])
    if len(cases) != 8 or len({case["id"] for case in cases}) != 8:
        raise RuntimeError("Expected exactly 8 unique QA cases")
    inactive_expectations = {
        source_id
        for case in cases
        for source_id in case["expected_source_ids"]
        if source_id not in enabled_source_ids
    }
    if inactive_expectations:
        raise RuntimeError(
            f"QA cases reference disabled corpus sources: {sorted(inactive_expectations)}"
        )

    print(
        f"offline    OK ({raw_documents} downloaded PDFs, "
        f"{len(documents)} registered Markdown files, {len(enabled)} enabled, 8 QA cases)"
    )
    return {"documents": details, "entity_types": entity_types, "qa_cases": cases}


def get_documents(client: httpx.Client, env: dict[str, str]) -> list[dict]:
    response = client.get(lightrag_url(env, "/documents"), headers=api_headers(env))
    response.raise_for_status()
    return [
        document
        for documents in response.json().get("statuses", {}).values()
        for document in documents
    ]


def check_duplicate_uploads(client: httpx.Client, env: dict[str, str], manifest: dict) -> None:
    bundle = load_structural_bundle(env)
    if bundle:
        unit = bundle["units"][0]
        response = client.post(
            lightrag_url(env, "/documents/text"),
            headers=api_headers(env),
            json={"text": unit["content"], "file_source": unit["file_source"]},
        )
        response.raise_for_status()
        status = response.json().get("status")
        if status != "duplicated":
            raise RuntimeError(
                f"Duplicate structural text was not rejected for {unit['file_source']}: {status}"
            )
        return
    for record in active_documents(manifest):
        path = ingest_path_for_record(env, record)
        upload_name = Path(record["prepared_file"]).name
        with path.open("rb") as handle:
            response = client.post(
                lightrag_url(env, "/documents/upload"),
                headers=api_headers(env),
                files={"file": (upload_name, handle, "text/markdown")},
            )
        response.raise_for_status()
        status = response.json().get("status")
        if status != "duplicated":
            raise RuntimeError(f"Duplicate upload was not rejected for {upload_name}: {status}")


def runtime_snapshot(env: dict[str, str], check_duplicates: bool = False) -> dict:
    workspace = safe_workspace(env)
    label = f"`{workspace}`"
    manifest = load_manifest()
    expected_names = expected_document_names(env, manifest)
    expected_count = len(expected_names)

    with httpx.Client(timeout=120) as client:
        health_response = client.get(lightrag_url(env, "/health"), headers=api_headers(env))
        health_response.raise_for_status()
        health = health_response.json()
        configuration = health.get("configuration", {})
        if health.get("status") != "healthy" or configuration.get("graph_storage") != "Neo4JStorage":
            raise RuntimeError(f"Unexpected LightRAG health/configuration: {health}")

        documents = get_documents(client, env)
        unexpected_documents = [
            item
            for item in documents
            if item.get("status") in {"pending", "processing", "processed"}
            and Path(item.get("file_path", "")).name not in expected_names
        ]
        if unexpected_documents:
            raise RuntimeError(
                f"Workspace contains non-enabled documents: {unexpected_documents}"
            )
        expected_documents = [
            item for item in documents if Path(item.get("file_path", "")).name in expected_names
        ]
        if len(expected_documents) != expected_count or any(
            item.get("status") != "processed" for item in expected_documents
        ):
            raise RuntimeError(
                f"Expected {expected_count} processed corpus documents, "
                f"found: {expected_documents}"
            )
        if load_structural_bundle(env):
            split_documents = {
                Path(item.get("file_path", "")).name: item.get("chunks_count")
                for item in expected_documents
                if item.get("chunks_count") != 1
            }
            if split_documents:
                raise RuntimeError(
                    f"Structural documents were split into multiple chunks: {split_documents}"
                )
        if check_duplicates:
            check_duplicate_uploads(client, env, manifest)

    nodes = neo4j_query(env, f"MATCH (n:{label}) RETURN count(n) AS nodes")[0][0]
    edges = neo4j_query(
        env, f"MATCH (a:{label})-[r]->(b:{label}) RETURN count(r) AS edges"
    )[0][0]
    type_rows = neo4j_query(
        env,
        f"MATCH (n:{label}) WHERE n.entity_type IS NOT NULL "
        "RETURN n.entity_type AS type, count(n) AS count ORDER BY count DESC",
    )
    typed_nodes = sum(row[1] for row in type_rows)
    if nodes <= 0 or edges <= 0:
        raise RuntimeError(f"Knowledge graph is empty: nodes={nodes}, edges={edges}")
    if typed_nodes <= 0 or len(type_rows) < 3:
        raise RuntimeError(f"Domain entity typing is insufficient: {type_rows}")

    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "processed_documents": len(expected_documents),
        "nodes": nodes,
        "edges": edges,
        "entity_types": {row[0]: row[1] for row in type_rows},
        "embedding_model": configuration.get("embedding_model"),
        "llm_model": configuration.get("llm_model"),
    }
    print(
        f"runtime    OK ({snapshot['processed_documents']} docs, {nodes} nodes, "
        f"{edges} edges, {len(type_rows)} entity types)"
    )
    return snapshot


def compare_snapshot(current: dict, snapshot_path: Path) -> None:
    if not snapshot_path.exists():
        raise RuntimeError(f"Missing {snapshot_path}")
    previous = json.loads(snapshot_path.read_text(encoding="utf-8"))
    fields = ("processed_documents", "nodes", "edges")
    changed = {field: (previous.get(field), current.get(field)) for field in fields if previous.get(field) != current.get(field)}
    if changed:
        raise RuntimeError(f"Persistence check failed after restart: {changed}")
    print("persist    OK (document, node and edge counts survived restart)")


def reference_source_ids(
    references: list[dict], manifest: dict, structural_bundle: dict | None = None
) -> set[str]:
    name_to_id = {
        Path(record["prepared_file"]).name: record["source_id"]
        for record in manifest["documents"]
    }
    if structural_bundle:
        name_to_id.update(
            {
                Path(unit["file_source"]).name: unit["source_id"]
                for unit in structural_bundle["units"]
            }
        )
    matched: set[str] = set()
    for reference in references:
        name = Path(reference.get("file_path", "")).name
        if name in name_to_id:
            matched.add(name_to_id[name])
    return matched


def run_qa(env: dict[str, str], qa_cases: list[dict]) -> dict:
    manifest = load_manifest()
    structural_bundle = load_structural_bundle(env)
    results = []
    failures = []
    prompt = (
        "请只根据检索到的法规和测试协议上下文回答。使用中文，保留英文缩写；"
        "每个关键结论尽量标注[来源文件名 | source page N]。证据不足时明确说明，不要使用外部常识补全。"
    )
    with httpx.Client(timeout=300) as client:
        for case in qa_cases:
            for mode in ("naive", "mix"):
                response = client.post(
                    lightrag_url(env, "/query"),
                    headers=api_headers(env),
                    json={
                        "query": case["question"],
                        "mode": mode,
                        "response_type": "Multiple Paragraphs",
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
                matched_sources = reference_source_ids(
                    references, manifest, structural_bundle
                )
                expected = set(case["expected_source_ids"])
                if case.get("source_match", "all") == "all":
                    source_ok = expected.issubset(matched_sources)
                else:
                    source_ok = bool(expected & matched_sources)
                has_page_marker = any(
                    "<!-- source_id:" in chunk and " page:" in chunk
                    for reference in references
                    for chunk in reference.get("content", [])
                )
                passed = bool(answer) and bool(references) and source_ok
                result = {
                    "case_id": case["id"],
                    "question": case["question"],
                    "mode": mode,
                    "passed": passed,
                    "expected_sources": sorted(expected),
                    "matched_sources": sorted(matched_sources),
                    "has_page_marker_in_context": has_page_marker,
                    "answer": answer,
                    "references": references,
                }
                results.append(result)
                marker = "PASS" if passed else "MISS"
                print(f"qa         {marker} {mode:5s} {case['id']} sources={sorted(matched_sources)}")
                if mode == "mix" and not passed:
                    failures.append(case["id"])

    output = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "mix_failures": failures,
    }
    results_dir = ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    output_path = results_dir / (
        "qa_results_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
    )
    write_json_atomic(output_path, output)
    if failures:
        raise RuntimeError(f"GraphRAG mix-mode grounding failed for cases: {failures}")
    print(f"qa         OK (8 questions x 2 modes); report={output_path}")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--compare-snapshot", action="store_true")
    parser.add_argument("--qa", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = load_env()
    checked = offline_checks()
    if args.offline and not (args.snapshot or args.compare_snapshot or args.qa):
        return

    snapshot_path = workspace_state_path(env, "runtime_snapshot")
    current = runtime_snapshot(env, check_duplicates=args.snapshot)
    if args.snapshot:
        write_json_atomic(snapshot_path, current)
        print(f"snapshot   written {snapshot_path}")
    if args.compare_snapshot:
        compare_snapshot(current, snapshot_path)
    if args.qa:
        run_qa(env, checked["qa_cases"])


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"test       FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
