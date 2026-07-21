# Regulation Evidence Harness — Framework Architecture

控制层「该做什么 / 宏观规范 / 评测纪律」见同目录 [`PROTOCOL.md`](PROTOCOL.md)。  
本文侧重包结构与扩展挂钩；若与 PROTOCOL 冲突，以 **PROTOCOL 为北极星**，本文中贴题路由等视为现状或债。

## v0.1 release boundary

- **Active KB:** `gb39901` only (GB 39901-2025).
- English UNECE/Euro NCAP sources may exist under `corpus/` but are **not** active knowledge bases in this release.
- Multi-KB routing, real Librarian ingest, and graph merge are **hooks/docs only**.

## One-line split

| Layer | Responsibility |
|-------|----------------|
| **LightRAG** | Build & hold KG + vector indexes; expose `/query/data` |
| **Harness (this package)** | Intent, multi-step evidence gathering, precise lookup, guards, answers |
| **Librarian (stub)** | Future: onboard docs, bind schema profiles, ingest/merge plans |

```text
                    ┌─────────────────────────────┐
  user question ──► │  QA Harness (online)         │
                    │  intent → tools → compose    │
                    └──────────────┬──────────────┘
                                   │ tools
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
       vector/graph          clause/table          compose/finalize
       (LightRAG)            (EvidenceCatalog)     (LLM + guards)
              ▲
              │ ingest (offline)
  ┌───────────┴────────────┐
  │ Librarian (stub)        │  propose profile/L2, workspace, merge
  │ LightRAG workspaces     │
  └─────────────────────────┘
```

## Package map

```text
reg_harness/
  runtime.py           # build_stack() — wire everything
  loop.py              # agent action/observation loop
  intent.py            # lightweight vertical router
  kb.py                # KnowledgeBase + Registry (multi-KB hook)
  schema_profiles.py   # L0 / L1 / L2 dataclasses
  librarian.py         # offline ingest/merge interfaces (stub exec)
  knowledge/
    evidence_catalog.py
  tools/
    lightrag_retrieve.py
    precise_lookup.py
    evidence_check.py
    compose_answer.py
    finalize.py
    registry.py
  guards.py / slots.py / compact.py / llm.py / prompts.py
```

## Schema layering (framework, not full product)

| Layer | What | Demo status |
|-------|------|-------------|
| **L0** | Universal regulation types | `SchemaLayerL0` constants |
| **L1** | Domain profile (AEB) | `aeb_light_duty` + optional path to `config/gb_39901_2025_schema.yml` |
| **L2** | Per-document binding | `default_gb39901_binding()` |

**Rule:** new documents reuse L1; only L2 instance fields change. Do not invent a full ontology per PDF.

## KB policy (framework)

| Situation | Default recommendation |
|-----------|------------------------|
| Same standard, small patch | `incremental_append` (future) |
| New standard / experiment | `new_workspace` |
| Cross-doc QA | intent selects multiple KBs or federation; physical merge is explicit |

`StubLibrarian` only **proposes** plans; `run_ingest` / `run_merge` return `not_implemented`.

## Online vs offline

| Surface | When | Entry |
|---------|------|--------|
| QA | user asks | `build_stack().ask(...)` / `cli ask` |
| Intent only | debug | `cli intent` |
| Precise lookup | debug | `cli lookup` |
| Stack inspect | debug | `cli describe` |
| Onboard doc | ops | `cli librarian propose-ingest` |

## Intent contract

Always returns `kb: ["gb39901"]` in the current demo, plus `tools_prefer`, `need_graph/table/clause`.  
Multi-KB later = richer `resolve_intent` + `KnowledgeBaseRegistry` entries; loop stays the same.

## What is intentionally not in the online agent

- Designing new schemas mid-question
- Auto-merging graphs
- Full re-ingest of PDFs

Those belong to **Librarian / ops**, not the QA ReAct loop.
