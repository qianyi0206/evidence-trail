from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SchemaLayerL0:
    """Universal regulation skeleton shared across standards."""

    entity_types: list[str] = field(
        default_factory=lambda: [
            "Standard",
            "Clause",
            "Requirement",
            "TestScenario",
            "Metric",
            "Threshold",
            "Condition",
            "Parameter",
            "DocumentationArtifact",
            "Organization",
        ]
    )
    relation_types: list[str] = field(
        default_factory=lambda: [
            "CONTAINS",
            "DEFINES",
            "SPECIFIES",
            "VERIFIED_BY",
            "HAS_THRESHOLD",
            "HAS_CONDITION",
            "APPLIES_TO",
        ]
    )


@dataclass
class SchemaProfileL1:
    """Domain profile reused by many documents (e.g. light-duty AEB)."""

    id: str
    title: str
    domain: str
    extra_entity_types: list[str] = field(default_factory=list)
    extra_relation_types: list[str] = field(default_factory=list)
    notes: str = ""
    # Optional path to richer YAML (gb_39901_2025_schema.yml etc.)
    config_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "domain": self.domain,
            "extra_entity_types": self.extra_entity_types,
            "extra_relation_types": self.extra_relation_types,
            "notes": self.notes,
            "config_path": self.config_path,
        }


@dataclass
class DocumentBindingL2:
    """Per-document instance config — not a brand-new ontology."""

    doc_id: str
    source_file: str
    schema_profile_id: str
    kb_id: str = "gb39901"
    enabled_sections: list[str] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    table_maps: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_file": self.source_file,
            "schema_profile_id": self.schema_profile_id,
            "kb_id": self.kb_id,
            "enabled_sections": self.enabled_sections,
            "aliases": self.aliases,
            "table_maps": self.table_maps,
            "meta": self.meta,
        }


def builtin_profiles(aeb_root: Path | None = None) -> dict[str, SchemaProfileL1]:
    """Demo profiles. Future: load from config/schema_profiles/*.yml."""
    config_path = None
    if aeb_root is not None:
        candidate = aeb_root / "config" / "gb_39901_2025_schema.yml"
        if candidate.is_file():
            config_path = str(candidate.relative_to(aeb_root))
    aeb = SchemaProfileL1(
        id="aeb_light_duty",
        title="轻型汽车 AEB / 主动安全",
        domain="light_duty_vehicle_aeb",
        extra_entity_types=[
            "System",
            "SystemFunction",
            "SystemState",
            "TestTarget",
            "LoadState",
            "AcceptanceCriterion",
            "FailureMode",
            "Hazard",
        ],
        extra_relation_types=[
            "HAS_FUNCTION",
            "HAS_STATE",
            "USES_TARGET",
            "HAS_LOAD_STATE",
            "HAS_ACCEPTANCE_CRITERION",
        ],
        notes="Shared by GB 39901 and similar AEB regs; document diffs go to L2.",
        config_path=config_path,
    )
    return {aeb.id: aeb}


def default_gb39901_binding() -> DocumentBindingL2:
    return DocumentBindingL2(
        doc_id="gb_39901_2025",
        source_file="GB+39901-2025.pdf_by_PaddleOCR-VL-1.6.md",
        schema_profile_id="aeb_light_duty",
        kb_id="gb39901",
        enabled_sections=["1", "3", "4", "5", "6", "7", "8", "9", "附录A", "附录B"],
        aliases={"AEBS": "自动紧急制动系统", "AEB系统": "自动紧急制动系统"},
        meta={"standard_id": "GB 39901-2025"},
    )
