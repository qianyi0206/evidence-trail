from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from reg_harness.config import Settings, load_settings
from reg_harness.intent import IntentResult, resolve_intent
from reg_harness.kb import KnowledgeBase, KnowledgeBaseRegistry
from reg_harness.knowledge.evidence_catalog import EvidenceCatalog
from reg_harness.librarian import Librarian, StubLibrarian
from reg_harness.llm import ChatClient
from reg_harness.loop import RegulationHarness
from reg_harness.schema_profiles import (
    SchemaLayerL0,
    SchemaProfileL1,
    builtin_profiles,
    default_gb39901_binding,
)
from reg_harness.tools.registry import ToolRegistry, default_registry


@dataclass
class HarnessStack:
    """Fully wired framework stack for online QA (+ offline librarian stub)."""

    settings: Settings
    kb_registry: KnowledgeBaseRegistry
    profiles: dict[str, SchemaProfileL1]
    schema_l0: SchemaLayerL0
    librarian: Librarian
    chat: ChatClient
    registry: ToolRegistry
    harness: RegulationHarness
    active_kb_id: str = "gb39901"
    document_bindings: list[dict[str, Any]] = field(default_factory=list)

    def active_kb(self) -> KnowledgeBase:
        return self.kb_registry.get(self.active_kb_id)

    def catalog(self) -> EvidenceCatalog | None:
        return self.active_kb().catalog

    def describe(self) -> dict[str, Any]:
        cat = self.catalog()
        n_records = len(cat.records) if cat is not None else 0
        return {
            "active_kb": self.active_kb_id,
            "kbs": self.kb_registry.list_ids(),
            "profiles": list(self.profiles),
            "schema_l0_entities": self.schema_l0.entity_types,
            "tools": self.registry.names(),
            "document_bindings": self.document_bindings,
            "lightrag_url": self.settings.lightrag_url,
            "llm_model": self.settings.llm_model,
            "librarian": type(self.librarian).__name__,
            "pilot_heuristics": bool(getattr(self.settings, "pilot_heuristics", False)),
            "enable_precise_lookup": bool(
                getattr(self.settings, "enable_precise_lookup", False)
            ),
            "catalog_mode": getattr(self.settings, "catalog_mode", "none"),
            "catalog_records": n_records,
        }

    def resolve_intent(self, question: str, policy: str = "auto") -> IntentResult:
        return resolve_intent(
            question,
            policy,
            pilot_heuristics=bool(getattr(self.settings, "pilot_heuristics", False)),
        )

    def ask(
        self,
        question: str,
        *,
        policy: str = "auto",
        max_steps: int | None = None,
        bootstrap: bool = False,
        event_hook=None,
    ):
        return self.harness.run(
            question,
            policy=policy,
            max_steps=max_steps,
            bootstrap=bootstrap,
            event_hook=event_hook,
        )


def build_stack(
    settings: Settings | None = None,
    profile_env: str | None = None,
) -> HarnessStack:
    """Construct the full framework. Entry point for apps / CLI."""
    cfg = settings or load_settings(profile_env=profile_env)
    profiles = builtin_profiles(cfg.aeb_root)
    catalog_mode = getattr(cfg, "catalog_mode", "none") or "none"
    kb_registry = KnowledgeBaseRegistry.default_gb39901(
        cfg.aeb_root,
        evidence_jsonl=cfg.evidence_jsonl if catalog_mode == "gold" else None,
        catalog_mode=catalog_mode,
    )
    # Demo logical KB id; the running LightRAG process may use a different WORKSPACE env.
    if cfg.active_kb not in kb_registry.kbs:
        cfg.active_kb = kb_registry.default_kb_id
    kb = kb_registry.get(cfg.active_kb)
    kb.lightrag_workspace = cfg.active_kb

    chat = ChatClient(cfg)
    catalog = kb.ensure_catalog(default_kb=cfg.active_kb)
    registry = default_registry(cfg, chat=chat, catalog=catalog)
    harness = RegulationHarness(settings=cfg, registry=registry, chat=chat)
    librarian = StubLibrarian(profiles=profiles)
    binding = default_gb39901_binding()

    return HarnessStack(
        settings=cfg,
        kb_registry=kb_registry,
        profiles=profiles,
        schema_l0=SchemaLayerL0(),
        librarian=librarian,
        chat=chat,
        registry=registry,
        harness=harness,
        active_kb_id=cfg.active_kb,
        document_bindings=[binding.to_dict()],
    )
