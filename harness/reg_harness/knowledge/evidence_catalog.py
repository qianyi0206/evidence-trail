from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from reg_harness.types import EvidenceItem  # noqa: F401 — used by EvidenceRecord.to_evidence_item


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).casefold()


def _normalize_clause_key(value: str) -> str:
    text = str(value or "").strip()
    text = text.replace("条款", "").replace("第", "").replace("条", "")
    text = text.replace("～", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", "", text)
    return text.casefold()


@dataclass
class EvidenceRecord:
    id: str
    source_id: str
    title: str
    source_excerpt: str
    source_file: str
    locator: dict[str, Any] = field(default_factory=dict)
    normalized_facts: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_evidence_item(self, *, source_tool: str) -> EvidenceItem:
        facts = ""
        if self.normalized_facts:
            facts = "\nnormalized_facts: " + json.dumps(
                self.normalized_facts, ensure_ascii=False, sort_keys=True
            )
        text = (
            f"evidence_id: {self.id}\n"
            f"title: {self.title}\n"
            f"locator: {json.dumps(self.locator, ensure_ascii=False, sort_keys=True)}"
            f"{facts}\n"
            f"source_excerpt:\n{self.source_excerpt}"
        )
        return EvidenceItem(
            kind="catalog",
            text=text,
            file_path=self.source_file,
            evidence_ids=[self.id],
            source_tool=source_tool,
            raw=self.raw,
        )


class EvidenceCatalog:
    """Gold-ish evidence store for precise clause/table lookup and ID enrichment."""

    def __init__(self, records: list[EvidenceRecord], *, default_kb: str = "gb39901"):
        self.default_kb = default_kb
        self.records = records
        self.by_id: dict[str, EvidenceRecord] = {item.id: item for item in records}
        self._by_clause: dict[str, list[EvidenceRecord]] = {}
        self._by_table: dict[str, list[EvidenceRecord]] = {}
        self._by_kb: dict[str, list[EvidenceRecord]] = {}
        for item in records:
            self._by_kb.setdefault(item.source_id, []).append(item)
            clause = item.locator.get("clause")
            if clause:
                key = _normalize_clause_key(str(clause))
                self._by_clause.setdefault(key, []).append(item)
            # also index from id suffixes: gb39901:clause:6.11
            if ":clause:" in item.id:
                key = _normalize_clause_key(item.id.split(":clause:", 1)[1])
                self._by_clause.setdefault(key, []).append(item)
            if ":appendix:" in item.id:
                key = _normalize_clause_key(item.id.split(":appendix:", 1)[1])
                self._by_clause.setdefault(key, []).append(item)
            table = item.locator.get("table")
            if table is not None:
                self._by_table.setdefault(str(table).casefold(), []).append(item)

    @classmethod
    def from_jsonl(cls, path: Path, *, default_kb: str = "gb39901") -> "EvidenceCatalog":
        if not path.is_file():
            return cls([], default_kb=default_kb)
        records: list[EvidenceRecord] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            records.append(
                EvidenceRecord(
                    id=str(raw["id"]),
                    source_id=str(raw.get("source_id") or default_kb),
                    title=str(raw.get("title") or ""),
                    source_excerpt=str(raw.get("source_excerpt") or ""),
                    source_file=str(raw.get("source_file") or ""),
                    locator=dict(raw.get("locator") or {}),
                    normalized_facts=dict(raw.get("normalized_facts") or {}),
                    raw=raw,
                )
            )
        return cls(records, default_kb=default_kb)

    @classmethod
    def from_aeb_root(cls, aeb_root: Path, *, default_kb: str = "gb39901") -> "EvidenceCatalog":
        """Load benchmark gold evidence.jsonl.

        PROTOCOL: this is an *eval/gold* source, not the default online catalog.
        Callers must only use this under catalog_mode=gold / explicit eval paths.
        """
        path = aeb_root / "benchmark" / "data" / "evidence.jsonl"
        return cls.from_jsonl(path, default_kb=default_kb)

    def filter_kb(self, kb: str | None = None) -> list[EvidenceRecord]:
        if not kb:
            return list(self.records)
        return list(self._by_kb.get(kb, []))

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        return self.by_id.get(evidence_id)

    def lookup_clause(
        self,
        clause: str,
        *,
        kb: str | None = None,
        exact_id_prefix: bool = True,
    ) -> list[EvidenceRecord]:
        key = _normalize_clause_key(clause)
        if not key:
            return []
        hits = list(self._by_clause.get(key, []))
        # Prefix match for hierarchical clauses: 6.11 matches 6.11 only exact key;
        # also try direct id forms.
        if not hits and exact_id_prefix:
            for item in self.records:
                for part in (item.locator.get("clause"),):
                    if not part:
                        continue
                    pk = _normalize_clause_key(str(part))
                    if pk == key or pk.startswith(key + ".") or key.startswith(pk + "."):
                        hits.append(item)
        # Prefer exact clause locator equality first
        exact = [
            item
            for item in hits
            if _normalize_clause_key(str(item.locator.get("clause") or "")) == key
            or item.id.endswith(f":clause:{clause}")
            or item.id.endswith(f":appendix:{clause}")
        ]
        ordered = exact or hits
        if kb:
            ordered = [item for item in ordered if item.source_id == kb]
        # de-dupe by id preserving order
        seen: set[str] = set()
        result: list[EvidenceRecord] = []
        for item in ordered:
            if item.id in seen:
                continue
            seen.add(item.id)
            result.append(item)
        return result

    def lookup_table(
        self,
        table: str | int,
        *,
        vehicle: str | None = None,
        ego_kmh: float | int | None = None,
        target_kmh: float | int | None = None,
        load_state: str | None = None,
        scenario: str | None = None,
        kb: str | None = None,
    ) -> list[EvidenceRecord]:
        table_key = str(table).casefold().replace("表", "")
        candidates = list(self._by_table.get(table_key, []))
        if kb:
            candidates = [item for item in candidates if item.source_id == kb]

        def same_number(actual: Any, expected: float | int) -> bool:
            try:
                return float(actual) == float(expected)
            except (TypeError, ValueError):
                return False

        def normalize_scenario(value: Any) -> str:
            normalized = str(value or "").strip().casefold()
            aliases = {
                "静止": "stationary",
                "静止目标": "stationary",
                "匀速": "moving",
                "移动": "moving",
                "移动目标": "moving",
                "制动": "braking",
                "制动目标": "braking",
            }
            return aliases.get(normalized, normalized)

        def matches_conditions(item: EvidenceRecord) -> bool:
            facts = item.normalized_facts or {}
            if vehicle and str(facts.get("vehicle", "")).upper() != str(vehicle).upper():
                return False
            if ego_kmh is not None and not same_number(facts.get("ego_kmh"), ego_kmh):
                return False
            if target_kmh is not None:
                target_values = (facts.get("target_kmh"), facts.get("target_start_kmh"))
                if not any(same_number(value, target_kmh) for value in target_values):
                    return False
            if scenario and normalize_scenario(facts.get("scenario")) != normalize_scenario(
                scenario
            ):
                return False
            return True

        candidates = [item for item in candidates if matches_conditions(item)]

        def score(item: EvidenceRecord) -> int:
            facts = item.normalized_facts or {}
            points = 0
            if vehicle:
                if str(facts.get("vehicle", "")).upper() == str(vehicle).upper():
                    points += 3
            if ego_kmh is not None:
                if facts.get("ego_kmh") == ego_kmh or facts.get("ego_kmh") == float(ego_kmh):
                    points += 3
                # row locator vehicle_speed=40
                row = str(item.locator.get("row") or "")
                if f"vehicle_speed={int(ego_kmh)}" in row or f"vehicle_speed={ego_kmh}" in row:
                    points += 2
            if target_kmh is not None:
                if facts.get("target_kmh") == target_kmh or facts.get("target_kmh") == float(
                    target_kmh
                ):
                    points += 2
            if scenario:
                if str(facts.get("scenario", "")).casefold() == str(scenario).casefold():
                    points += 2
            if load_state:
                load = str(load_state)
                if "最大设计" in load or load.casefold() in {"gross", "gvm", "max"}:
                    if "gross_kmh" in facts:
                        points += 1
                if "行车" in load or load.casefold() in {"kerb", "curb"}:
                    if "kerb_kmh" in facts:
                        points += 1
            # Prefer concrete rows over table summaries
            if item.locator.get("row"):
                points += 1
            return points

        if any(v is not None and v != "" for v in (vehicle, ego_kmh, target_kmh, load_state, scenario)):
            ranked = sorted(candidates, key=score, reverse=True)
            best = score(ranked[0]) if ranked else 0
            if best <= 0:
                return ranked[:5]
            return [item for item in ranked if score(item) >= max(1, best - 1)][:8]
        return candidates

    def match_ids_for_text(
        self,
        text: str,
        *,
        file_path: str = "",
        kb: str | None = None,
        limit: int = 5,
    ) -> list[str]:
        """Best-effort map free text / retrieval blurb onto catalog evidence ids."""
        if not text:
            return []
        norm_text = _norm(text)
        path = str(file_path or "").casefold()
        scored: list[tuple[int, str]] = []

        # Clause markers in text
        clause_hits = set(
            re.findall(
                r"(?:source_clause|来源条款)\s*[=:：]\s*([0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)",
                text,
                flags=re.IGNORECASE,
            )
        )
        clause_hits.update(re.findall(r"第\s*([0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)\s*条", text))
        clause_hits.update(re.findall(r"\[(\d+(?:\.\d+)+[A-Za-z]?)\]", text))

        for clause in clause_hits:
            for item in self.lookup_clause(clause, kb=kb):
                scored.append((6, item.id))

        # Table markers from path or text
        table_match = re.search(r"(?:__table_|table[_-]?)(a_)?(\d+)", path, re.IGNORECASE)
        if not table_match:
            table_match = re.search(r"表\s*([A-Za-z]?\d+)", text)
            table_key = table_match.group(1) if table_match else None
        else:
            table_key = ("a_" if table_match.group(1) else "") + table_match.group(2)
        if table_key:
            for item in self.lookup_table(table_key, kb=kb):
                excerpt = _norm(item.source_excerpt)
                points = 3
                if excerpt and excerpt[:80] in norm_text:
                    points += 4
                scored.append((points, item.id))

        # Excerpt containment for shorter gold snippets
        pool = self.filter_kb(kb) if kb else self.records
        for item in pool:
            excerpt = item.source_excerpt or ""
            if len(excerpt) < 40:
                continue
            excerpt_norm = _norm(excerpt)
            if len(excerpt_norm) >= 40 and excerpt_norm[:120] in norm_text:
                scored.append((5, item.id))
            elif len(excerpt_norm) >= 80 and excerpt_norm[:60] in norm_text:
                scored.append((4, item.id))
            elif item.title and _norm(item.title) in norm_text:
                scored.append((2, item.id))

        # Aggregate max score per id
        best: dict[str, int] = {}
        for points, evidence_id in scored:
            best[evidence_id] = max(best.get(evidence_id, 0), points)
        ranked = sorted(best.items(), key=lambda pair: (-pair[1], pair[0]))
        return [evidence_id for evidence_id, points in ranked[:limit] if points >= 2]


def merge_evidence_ids(existing: Iterable[str], new_ids: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in list(existing) + list(new_ids):
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result

