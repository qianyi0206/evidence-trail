from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any


logger = logging.getLogger("lightrag")

# Kept in code so the LightRAG container can enforce the same contract before
# graph and vector writes without mounting or parsing external configuration.
RELATION_ENDPOINTS: dict[str, tuple[set[str], set[str]]] = {
    "CONTAINS": ({"Standard", "Clause", "DocumentationArtifact"}, {"Clause", "Requirement", "TestScenario", "DocumentationArtifact", "AcceptanceCriterion", "TypeEquivalenceCriterion", "ImplementationRule"}),
    "DEFINES": ({"Standard", "Clause"}, {"Term", "System", "SystemFunction", "SystemState", "TestScenario", "Metric", "Parameter", "TestTarget"}),
    "NORMATIVELY_REFERENCES": ({"Standard", "Clause", "Requirement", "TestTarget"}, {"Standard"}),
    "SUPERSEDES": ({"Standard"}, {"Standard"}),
    "PUBLISHED_BY": ({"Standard"}, {"Organization"}),
    "PROPOSED_BY": ({"Standard"}, {"Organization"}),
    "MANAGED_BY": ({"Standard"}, {"Organization"}),
    "APPLIES_TO": ({"Standard", "Clause", "Requirement", "TestScenario", "ImplementationRule", "Threshold", "AcceptanceCriterion"}, {"VehicleCategory", "System", "SystemFunction", "SimulationToolchain", "LoadState"}),
    "SPECIFIES": ({"Clause"}, {"Requirement", "TypeEquivalenceCriterion", "ImplementationRule", "Threshold", "TestScenario", "Condition", "VerificationActivity", "DocumentationArtifact", "AcceptanceCriterion", "TestTarget", "Hazard", "SafetyMeasure", "SystemComponent", "SimulationToolchain"}),
    "HAS_FUNCTION": ({"System"}, {"SystemFunction"}),
    "HAS_STATE": ({"System", "Requirement"}, {"SystemState"}),
    "HAS_COMPONENT": ({"System"}, {"SystemComponent"}),
    "HAS_SIGNAL": ({"SystemFunction", "SystemState", "FailureMode", "Requirement"}, {"Signal"}),
    "INTERRUPTED_BY": ({"SystemFunction"}, {"DriverAction"}),
    "TRANSITIONS_TO": ({"SystemState"}, {"SystemState"}),
    "VERIFIED_BY": ({"Requirement", "SafetyGoal", "SafetyMeasure", "CredibilityCriterion"}, {"TestScenario", "VerificationActivity"}),
    "USES_TARGET": ({"TestScenario"}, {"TestTarget"}),
    "HAS_LOAD_STATE": ({"Requirement", "TestScenario", "VerificationActivity", "Threshold", "AcceptanceCriterion", "ImplementationRule"}, {"LoadState"}),
    "HAS_CONDITION": ({"SystemFunction", "SystemState", "Requirement", "TestScenario", "ImplementationRule", "TypeEquivalenceCriterion", "SimulationToolchain", "VerificationActivity"}, {"Condition"}),
    "HAS_PARAMETER": ({"Condition", "TestScenario", "SimulationModel", "VerificationActivity", "TypeEquivalenceCriterion", "DocumentationArtifact"}, {"Parameter"}),
    "MEASURED_BY": ({"Requirement", "TestScenario", "AcceptanceCriterion", "Hazard", "CredibilityCriterion", "Threshold", "Condition"}, {"Metric"}),
    "HAS_THRESHOLD": ({"Requirement", "Metric", "AcceptanceCriterion", "CredibilityCriterion", "Condition", "TestScenario"}, {"Threshold"}),
    "HAS_ACCEPTANCE_CRITERION": ({"TestScenario", "VerificationActivity", "CredibilityCriterion", "Requirement"}, {"AcceptanceCriterion"}),
    "HAS_IMPLEMENTATION_RULE": ({"Standard", "Requirement", "TestScenario"}, {"ImplementationRule"}),
    "HAS_EQUIVALENCE_CRITERION": ({"Standard", "TypeEquivalenceCriterion"}, {"TypeEquivalenceCriterion", "Requirement"}),
    "REQUIRES_DOCUMENT": ({"Standard", "Clause", "Requirement", "SimulationToolchain", "ImplementationRule"}, {"DocumentationArtifact"}),
    "DOCUMENTS": ({"DocumentationArtifact"}, {"System", "SystemFunction", "SystemComponent", "FailureMode", "Hazard", "SafetyGoal", "SafetyMeasure", "VerificationActivity", "SimulationToolchain", "SimulationModel", "DocumentationArtifact", "AcceptanceCriterion", "SafetyAnalysis", "Requirement", "TypeEquivalenceCriterion"}),
    "HAS_FAILURE_MODE": ({"System", "SystemFunction", "SystemComponent"}, {"FailureMode"}),
    "CAUSES": ({"FailureMode", "SystemFunction"}, {"Hazard"}),
    "ASSIGNED_ASIL": ({"Hazard"}, {"ASILLevel"}),
    "HAS_SAFETY_GOAL": ({"Hazard"}, {"SafetyGoal"}),
    "IMPLEMENTED_BY": ({"SafetyGoal"}, {"SafetyMeasure"}),
    "MITIGATES": ({"SafetyMeasure"}, {"FailureMode", "Hazard"}),
    "ANALYZED_BY": ({"FailureMode", "Hazard", "SafetyAnalysis"}, {"SafetyAnalysis", "DocumentationArtifact"}),
    "INJECTS_FAULT": ({"VerificationActivity"}, {"FailureMode"}),
    "VALIDATES": ({"VerificationActivity"}, {"SystemFunction", "SafetyGoal", "SafetyMeasure", "SimulationToolchain", "SimulationModel"}),
    "PRODUCES": ({"TestScenario", "VerificationActivity", "SimulationToolchain", "Organization"}, {"DocumentationArtifact"}),
    "USES_TOOLCHAIN": ({"TestScenario", "VerificationActivity"}, {"SimulationToolchain"}),
    "COMPOSED_OF": ({"SimulationToolchain", "DocumentationArtifact"}, {"SimulationModel", "DocumentationArtifact"}),
    "HAS_VALIDITY_DOMAIN": ({"SimulationToolchain", "SimulationModel"}, {"ValidityDomain"}),
    "EVALUATED_BY": ({"SimulationToolchain", "SimulationModel"}, {"CredibilityCriterion", "VerificationActivity", "Requirement"}),
    "USES_KPI": ({"CredibilityCriterion", "VerificationActivity"}, {"Metric"}),
}

_TYPE_CANONICAL = {
    value.casefold(): value
    for sources, targets in RELATION_ENDPOINTS.values()
    for value in sources | targets
}
_RELATION_RE = re.compile(r"relation_type\s*=\s*([A-Z_]+)", re.IGNORECASE)
_RELATION_SPLIT_RE = re.compile(r"(?:,|，|<SEP>|\s)+")
_ENTITY_TYPES_BY_CHUNK: dict[str, dict[str, str]] = defaultdict(dict)


def relation_contract_text() -> str:
    lines = []
    for relation, (sources, targets) in RELATION_ENDPOINTS.items():
        lines.append(
            f"- {relation}: {','.join(sorted(sources))} -> {','.join(sorted(targets))}"
        )
    return "\n".join(lines)


def _canonical_type(value: str | None) -> str | None:
    if not value:
        return None
    return _TYPE_CANONICAL.get(value.strip().casefold())


def _edge_relation_type(edge: dict[str, Any]) -> str | None:
    tokens = _RELATION_SPLIT_RE.split((edge.get("keywords") or "").upper())
    for token in tokens:
        if token in RELATION_ENDPOINTS:
            return token
    match = _RELATION_RE.search(edge.get("description") or "")
    if match:
        candidate = match.group(1).upper()
        if candidate in RELATION_ENDPOINTS:
            return candidate
    return None


def _set_relation_type(edge: dict[str, Any], relation_type: str) -> dict[str, Any]:
    updated = dict(edge)
    updated["keywords"] = relation_type
    description = updated.get("description") or ""
    if _RELATION_RE.search(description):
        description = _RELATION_RE.sub(
            f"relation_type={relation_type}", description, count=1
        )
    else:
        description = f"relation_type={relation_type}；{description}"
    updated["description"] = description
    return updated


def filter_extraction_result(
    maybe_nodes: dict[str, list[dict[str, Any]]],
    maybe_edges: dict[tuple[str, str], list[dict[str, Any]]],
    chunk_key: str,
) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], dict[str, int]]:
    # Build types from this call only — never invent relations from endpoint
    # cardinality, and never reuse a process-global type map across documents.
    chunk_types: dict[str, str] = {}
    for name, entities in maybe_nodes.items():
        if entities:
            canonical = _canonical_type(entities[0].get("entity_type"))
            if canonical:
                chunk_types[name] = canonical
    # Optional debug snapshot (not used for later chunks).
    _ENTITY_TYPES_BY_CHUNK[chunk_key] = dict(chunk_types)

    filtered: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    stats = {
        "kept": 0,
        "repaired": 0,
        "reversed": 0,
        "repaired_reversed": 0,
        "dropped": 0,
    }
    for edge_list in maybe_edges.values():
        for edge in edge_list:
            source = edge.get("src_id", "")
            target = edge.get("tgt_id", "")
            source_type = chunk_types.get(source)
            target_type = chunk_types.get(target)
            if not source_type or not target_type:
                stats["dropped"] += 1
                continue

            mapped = _edge_relation_type(edge)
            if not mapped:
                # No declared relation type → drop (do not invent from type pair).
                stats["dropped"] += 1
                continue

            allowed_sources, allowed_targets = RELATION_ENDPOINTS[mapped]
            if source_type in allowed_sources and target_type in allowed_targets:
                filtered[(source, target)].append(_set_relation_type(edge, mapped))
                stats["kept"] += 1
                continue
            if target_type in allowed_sources and source_type in allowed_targets:
                reversed_edge = _set_relation_type(edge, mapped)
                reversed_edge["src_id"] = target
                reversed_edge["tgt_id"] = source
                filtered[(target, source)].append(reversed_edge)
                stats["reversed"] += 1
                continue

            # Declared relation does not match either orientation → drop.
            stats["dropped"] += 1
    return dict(filtered), stats


def install_schema_guard() -> None:
    import lightrag.operate as operate

    original = operate._process_extraction_result
    if getattr(original, "_gb39901_schema_guard", False):
        return

    async def guarded_process_extraction_result(*args: Any, **kwargs: Any):
        maybe_nodes, maybe_edges = await original(*args, **kwargs)
        chunk_key = kwargs.get("chunk_key") or (args[1] if len(args) > 1 else "unknown")
        filtered_edges, stats = filter_extraction_result(
            maybe_nodes, maybe_edges, str(chunk_key)
        )
        if maybe_edges:
            logger.info(
                "GB39901 schema guard %s: kept=%d reversed=%d dropped=%d",
                chunk_key,
                stats["kept"],
                stats["reversed"],
                stats["dropped"],
            )
            if stats["dropped"]:
                # Sample endpoints of dropped edges for debugging (no full text dump).
                dropped_sample: list[str] = []
                kept_keys = set(filtered_edges)
                for key, edge_list in maybe_edges.items():
                    if key in kept_keys:
                        continue
                    for edge in edge_list[:2]:
                        dropped_sample.append(
                            f"{edge.get('src_id')}->{edge.get('tgt_id')}:"
                            f"{(edge.get('keywords') or '')[:40]}"
                        )
                        if len(dropped_sample) >= 5:
                            break
                    if len(dropped_sample) >= 5:
                        break
                if dropped_sample:
                    logger.info(
                        "GB39901 schema guard %s dropped sample: %s",
                        chunk_key,
                        "; ".join(dropped_sample),
                    )
        return maybe_nodes, filtered_edges

    guarded_process_extraction_result._gb39901_schema_guard = True
    operate._process_extraction_result = guarded_process_extraction_result


def reset_type_cache() -> None:
    _ENTITY_TYPES_BY_CHUNK.clear()
