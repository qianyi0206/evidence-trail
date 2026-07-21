# Architecture

Portfolio-oriented overview of the **application layer** (this repo) vs **LightRAG** (dependency).

![System architecture](architecture.svg)

## Layers

```text
┌─────────────────────────────────────────────────────────────────┐
│  User / CLI / (optional) LightRAG WebUI                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┴───────────────────┐
         ▼                                       ▼
┌─────────────────────┐               ┌─────────────────────┐
│  reg_harness Agent  │               │  LightRAG API       │
│  (this repo)        │── /query* ──► │  Docker image       │
│  plan → tool → audit│               │  (not vendored)     │
│  → compose / gate   │               └──────────┬──────────┘
└─────────────────────┘                          │
                                                 ▼
                                    ┌────────────────────────┐
                                    │ Neo4j (graph) +        │
                                    │ NanoVector / JSON KV   │
                                    │ workspace: v4 only in  │
                                    │ git snapshot           │
                                    └────────────────────────┘
```

## Agent control loop

```text
question
  → decision LLM (JSON action)
  → tools: graph_search | vector_search | evidence_check | compose | finalize
  → post-retrieve sufficiency audit (code)
  → if sufficient / spin detected → force compose
  → numeric grounding guards on final JSON
```

| Component | Path | Responsibility |
|-----------|------|----------------|
| Loop + force compose | `harness/reg_harness/loop.py` | Orchestration |
| Sufficiency audit | `harness/reg_harness/sufficiency.py` | “Is the bag enough?” |
| Guards | `harness/reg_harness/guards.py` | Empty bag / ungrounded numbers |
| Schema guard | `lightrag_custom/schema_guard.py` | Relation endpoint filter at extract |
| Benchmark | `benchmark/` | Offline gold + scorers (not loaded online by default) |

## Data in git vs local

| Artifact | In git? |
|----------|---------|
| Prepared corpus + index units | Yes |
| v4 `rag_storage` (no LLM cache) | Yes |
| Neo4j volume | **No** — rebuild with Docker + ingest |
| `.env` secrets | **No** |

## Related docs

- [README.md](../README.md) — quick start  
- [harness/ARCHITECTURE.md](../harness/ARCHITECTURE.md) — package layout  
- [harness/PROTOCOL.md](../harness/PROTOCOL.md) — control-layer rules  
