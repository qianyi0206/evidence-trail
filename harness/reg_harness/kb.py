from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reg_harness.knowledge.evidence_catalog import EvidenceCatalog


@dataclass
class KnowledgeBase:
    """One queryable knowledge partition (framework hook for multi-KB later)."""

    id: str
    display_name: str = ""
    source_ids: list[str] = field(default_factory=list)
    # LightRAG workspace name when bound to a running server
    lightrag_workspace: str | None = None
    # Domain schema profile id (L1), e.g. aeb_light_duty
    schema_profile: str | None = None
    evidence_jsonl: Path | None = None
    catalog: EvidenceCatalog | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def ensure_catalog(self, default_kb: str | None = None) -> EvidenceCatalog:
        if self.catalog is not None:
            return self.catalog
        kb = default_kb or self.id
        if self.evidence_jsonl and self.evidence_jsonl.is_file():
            self.catalog = EvidenceCatalog.from_jsonl(self.evidence_jsonl, default_kb=kb)
        else:
            self.catalog = EvidenceCatalog([], default_kb=kb)
        return self.catalog


@dataclass
class KnowledgeBaseRegistry:
    """Registry of KBs. Demo ships with a single gb39901 entry."""

    kbs: dict[str, KnowledgeBase] = field(default_factory=dict)
    default_kb_id: str = "gb39901"

    def get(self, kb_id: str | None = None) -> KnowledgeBase:
        key = kb_id or self.default_kb_id
        if key not in self.kbs:
            raise KeyError(f"Unknown knowledge base: {key}. Known: {list(self.kbs)}")
        return self.kbs[key]

    def list_ids(self) -> list[str]:
        return sorted(self.kbs)

    def resolve_from_intent(self, intent_kb: list[str] | None) -> KnowledgeBase:
        if intent_kb:
            for kb_id in intent_kb:
                if kb_id in self.kbs:
                    return self.kbs[kb_id]
        return self.get(self.default_kb_id)

    @classmethod
    def default_gb39901(
        cls,
        aeb_root: Path,
        evidence_jsonl: Path | None = None,
        *,
        catalog_mode: str = "none",
    ) -> "KnowledgeBaseRegistry":
        """Build the demo KB registry.

        PROTOCOL: do not auto-bind benchmark gold evidence.jsonl for online mode.
        Pass evidence_jsonl only when catalog_mode is gold (or explicit path).
        """
        path: Path | None = None
        if catalog_mode == "gold" and evidence_jsonl is not None:
            path = evidence_jsonl if evidence_jsonl.is_file() else None
        elif catalog_mode == "gold" and evidence_jsonl is None:
            candidate = aeb_root / "benchmark" / "data" / "evidence.jsonl"
            path = candidate if candidate.is_file() else None
        elif evidence_jsonl is not None and evidence_jsonl.is_file():
            # Explicit non-default path (still only if caller intends a catalog file)
            path = evidence_jsonl if catalog_mode in {"gold", "index"} else None

        kb = KnowledgeBase(
            id="gb39901",
            display_name="GB 39901-2025 AEB",
            source_ids=["gb39901"],
            lightrag_workspace=None,  # filled from env at runtime if needed
            schema_profile="aeb_light_duty",
            evidence_jsonl=path,
            meta={
                "standard": "GB 39901-2025",
                "domain": "light_duty_aeb",
                "catalog_mode": catalog_mode,
            },
        )
        if path is not None:
            kb.ensure_catalog(default_kb="gb39901")
        else:
            kb.catalog = EvidenceCatalog([], default_kb="gb39901")
        return cls(kbs={"gb39901": kb}, default_kb_id="gb39901")
