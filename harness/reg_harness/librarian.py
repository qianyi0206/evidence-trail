from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from reg_harness.schema_profiles import DocumentBindingL2, SchemaProfileL1


@dataclass
class IngestPlan:
    """Plan produced before extracting a new document into a KB/workspace."""

    doc_id: str
    source_file: str
    schema_profile_id: str
    kb_id: str
    mode: str = "new_workspace"  # new_workspace | incremental_append
    workspace: str | None = None
    binding: DocumentBindingL2 | None = None
    notes: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_file": self.source_file,
            "schema_profile_id": self.schema_profile_id,
            "kb_id": self.kb_id,
            "mode": self.mode,
            "workspace": self.workspace,
            "binding": self.binding.to_dict() if self.binding else None,
            "notes": self.notes,
            "meta": self.meta,
        }


@dataclass
class MergePlan:
    """Explicit merge between knowledge partitions — never implicit."""

    source_kb_ids: list[str]
    target_kb_id: str
    strategy: str = "controlled_alias"  # controlled_alias | federation_only
    require_human_confirm: bool = True
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_kb_ids": self.source_kb_ids,
            "target_kb_id": self.target_kb_id,
            "strategy": self.strategy,
            "require_human_confirm": self.require_human_confirm,
            "notes": self.notes,
        }


class Librarian(ABC):
    """Offline / ops agent surface for onboarding documents.

    NOT part of the online QA loop. Call explicitly when adding corpora.
    """

    @abstractmethod
    def propose_ingest(
        self,
        source_file: str,
        *,
        preferred_profile: str | None = None,
        preferred_kb: str | None = None,
    ) -> IngestPlan:
        raise NotImplementedError

    @abstractmethod
    def run_ingest(self, plan: IngestPlan) -> dict[str, Any]:
        """Execute extraction into LightRAG workspace. Demo: not implemented."""
        raise NotImplementedError

    @abstractmethod
    def propose_merge(self, source_kb_ids: list[str], target_kb_id: str) -> MergePlan:
        raise NotImplementedError

    @abstractmethod
    def run_merge(self, plan: MergePlan) -> dict[str, Any]:
        raise NotImplementedError


class StubLibrarian(Librarian):
    """Scaffold librarian: proposes plans, refuses to execute heavy work."""

    def __init__(self, profiles: dict[str, SchemaProfileL1] | None = None):
        self.profiles = profiles or {}

    def propose_ingest(
        self,
        source_file: str,
        *,
        preferred_profile: str | None = None,
        preferred_kb: str | None = None,
    ) -> IngestPlan:
        profile = preferred_profile or "aeb_light_duty"
        kb = preferred_kb or "gb39901"
        doc_id = Path_stem(source_file)
        binding = DocumentBindingL2(
            doc_id=doc_id,
            source_file=source_file,
            schema_profile_id=profile,
            kb_id=kb,
        )
        return IngestPlan(
            doc_id=doc_id,
            source_file=source_file,
            schema_profile_id=profile,
            kb_id=kb,
            mode="new_workspace",
            workspace=f"{kb}_{doc_id}",
            binding=binding,
            notes=(
                "Stub only: review profile/L2 binding, then wire LightRAG ingest. "
                "Prefer new_workspace for new standards; incremental_append for same-standard patches."
            ),
            meta={"profiles_known": list(self.profiles)},
        )

    def run_ingest(self, plan: IngestPlan) -> dict[str, Any]:
        return {
            "status": "not_implemented",
            "message": "StubLibrarian.run_ingest is intentionally unimplemented in the demo framework.",
            "plan": plan.to_dict(),
        }

    def propose_merge(self, source_kb_ids: list[str], target_kb_id: str) -> MergePlan:
        return MergePlan(
            source_kb_ids=source_kb_ids,
            target_kb_id=target_kb_id,
            strategy="federation_only",
            require_human_confirm=True,
            notes="Default recommend query-time federation; physical merge only with alias rules + human confirm.",
        )

    def run_merge(self, plan: MergePlan) -> dict[str, Any]:
        return {
            "status": "not_implemented",
            "message": "StubLibrarian.run_merge is intentionally unimplemented.",
            "plan": plan.to_dict(),
        }


def Path_stem(source_file: str) -> str:
    name = source_file.replace("\\", "/").split("/")[-1]
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return name[:80] or "document"
