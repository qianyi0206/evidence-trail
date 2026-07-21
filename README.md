# GB 39901 AEB Regulation GraphRAG Agent

Open-source **application layer** for light-duty vehicle **AEBS** regulation QA (primary KB: **GB 39901-2025**).

| This repo owns | Depends on (not vendored) |
|----------------|---------------------------|
| Multi-step **evidence Agent** (`harness/`) | [LightRAG](https://github.com/HKUDS/LightRAG) retrieval + graph build |
| Schema / prompt guards (`lightrag_custom/`) | Neo4j + your OpenAI-compatible LLM/embedding APIs |
| Prepare / ingest scripts, compose stack | Official regulation text (place under `corpus/` locally) |
| Offline benchmark data + scorers | — |

We **do not ship the LightRAG source tree**. Runtime uses the published Docker image (pinned **v1.4.16**). See [`NOTICE.md`](NOTICE.md).

**Release scope (v0.1):** GB 39901 graph ablations (A0–v4), pilot benchmark, evidence harness. Multi-document production routing and frozen 60-question formal eval are out of scope.

Chinese notes: [`DELIVERY.md`](DELIVERY.md) · status: [`PROJECT_STATUS.md`](PROJECT_STATUS.md) · agent: [`harness/`](harness/).

---

## What this project is

An educational GraphRAG + agent stack for **AEBS** regulation text:

1. **Build** a knowledge graph with LightRAG (Neo4j + local vectors), comparing A0→v4 strategies.  
2. **Query** via WebUI / API and via a multi-step **evidence harness** (not a single retrieve→concat→answer pipe).  
3. **Control quality**: numeric grounding, gold/online isolation, and a **post-retrieve sufficiency audit** that forces compose when the bag is already enough (stops retrieval spin).  
4. **Report** honest pilot findings: graph helps coverage; noise can hurt final answers — hence the agent, not mode-switching alone.

Internship / portfolio framing: this is an **applied agent + eval** project on top of an open-source RAG engine, not a re-implementation of LightRAG.

---

## Architecture (v0.1)

```text
GB 39901 OCR Markdown
  -> prepare / structural units (v3)
  -> LightRAG extract (workspace A0|v2|v3|v4)
  -> Neo4j + NanoVectorDB
        |
        +--> WebUI /query  (classic modes: naive|hybrid|mix)
        |
        +--> harness/ Agent loop
               intent -> tools (vector|graph|clause|table)
               -> slots/guards -> compose_answer
```

| Layer | Role |
|-------|------|
| LightRAG | Graph **build** + retrieval backend |
| `harness/` | Online **evidence agent** (routing, precise lookup, guards) |
| `benchmark/` | Candidate eval suite + **pilot results** (not frozen v1) |

Multi-KB / Librarian / merge APIs exist as **stubs and docs only** (`harness/ARCHITECTURE.md`).

---

## Corpus (what counts in v0.1)

| Source | Role in v0.1 |
|--------|----------------|
| **GB 39901-2025** (OCR Markdown) | **Only active KB** (`enabled: true`) |
| UN R152 Rev.2 | Registered, **`enabled: false`**, not used for main graph/QA conclusions |
| Euro NCAP AEB C2C v4.3.1 | Same |
| Euro NCAP Collision Avoidance v10.4.1 | Same |

English PDFs may remain under `corpus/` for local experiments; they are **not** part of the v0.1 delivery claim. Do not treat them as production knowledge bases in this release.

Documents are for local, non-commercial educational study. Keep publishers’ rights; do not use answers for homologation without checking the official text.

---

## Key results (already on disk)

| Result | Where |
|--------|--------|
| Pilot 6-question report | `benchmark/results/pilot_6q_report.md` |
| Aggregated report | `benchmark/results/benchmark_report.md` |
| Table fact QA 8/8 (v3/v4) | `results/fact_qa_*.json` |
| KG structure scores | `benchmark/results/kg_score_*` |

**Stable takeaways**

1. Table-aware chunking (v3) fixes many numeric table failures.  
2. Relation guards (v4) improve graph legality; QA does not automatically win.  
3. Graph modes often raise evidence coverage; high noise can cancel answer gains — hence the agent harness (precise lookup + gates), not mode-switching alone.

**Not claimed:** GraphRAG always beats vector RAG; 60-question frozen v1; multi-document production KB.

---

## Quick start

Clone **this** repository (application layer only). You need Docker for Neo4j + LightRAG image, and API keys for chat/embeddings.

### A. Offline checks (no LLM required)

```bash
# from repository root (this directory)
cd harness
python3 -m unittest discover -s tests -v
python3 -m reg_harness.cli describe
```

### B. Graph services (API keys required)

1. Start Docker Desktop.  
2. `cp .env.example .env` and edit **`.env`** (never commit it).  
3. Set Neo4j password, LLM and embedding endpoints.  
4. Prefer the v4 GB workspace overlay (non-secret):

```bash
make v4-up    # relation-guard workspace + LightRAG :9621
# or: make v3-up / make gb-up / make up
```

- WebUI: http://127.0.0.1:9621  
- Neo4j: http://127.0.0.1:7474  

Agent ask (LLM + running LightRAG):

```bash
cd harness
python3 -m reg_harness.cli --profile-env .env.gb39901_v4 \
  ask "GB 39901—2025 适用于哪两类汽车？" --max-steps 6
```

Harder example (multi-scenario + shared criterion):

```bash
python3 -m reg_harness.cli --profile-env .env.gb39901_v4 \
  ask "完整列出6.11规定的五类误响应场景，并说明所有场景共同的合格判据。" \
  --max-steps 10
```

### C. Full rebuild (heavy)

```bash
make doctor && make download && make prepare && make up && make ingest
# GB profiles: make gb-demo / v3-demo / v4-demo
```

Destructive reset only:

```bash
make reset-index CONFIRM=RESET_AEB_INDEX
```

---

## Workspaces (GB ablations, not multi-standard KBs)

| Tag | Workspace | Idea |
|-----|-----------|------|
| A0 | `aeb_demo` | Stock LightRAG baseline |
| v2 | `aeb_gb39901_v2` | Schema / prompt overlay |
| v3 | `aeb_gb39901_v3_table_chunks` | 46 structural units (tables atomic) |
| v4 | `aeb_gb39901_v4_relation_guard` | 42 relation endpoint contracts |

Details: later sections below and `PROJECT_STATUS.md`.

---

## Security & what is not in git

- Copy `.env.example` → `.env`; **never commit secrets**.  
- Ignored by default: `.env`, `data/` (indexes), `results/`, `state/`, bulky `corpus/*`, most `benchmark/results` run dumps.  
- Safe to share: source, `config/`, non-secret profiles (`.env.gb39901*`), `benchmark/data/` gold JSONL, small report markdowns.  
- Third-party: [`NOTICE.md`](NOTICE.md) · License: [`LICENSE`](LICENSE) (MIT for **this** repo only).

---

## Regulation Evidence Harness

See [`harness/README.md`](harness/README.md) and [`harness/ARCHITECTURE.md`](harness/ARCHITECTURE.md).

LightRAG builds and serves the graph; the harness is the online **evidence agent** (intent, tools, slots, compose, guards). Multi-document onboarding remains a **Librarian stub**.

---

## GB 39901-2025 schema-constrained workspace

The original `aeb_demo` workspace is retained as the automatic LightRAG
baseline. The dedicated profile uses `aeb_gb39901_v2` and overlays only
non-secret settings from `.env.gb39901`.

```bash
make gb-doctor       # validate schema profile and model endpoints
make gb-prepare      # add repeatable clause anchors to the OCR Markdown
make gb-up           # switch the running LightRAG service to the v2 workspace
make gb-ingest       # index only the GB 39901-2025 OCR document
make gb-postprocess  # annotate canonical names and typed relation metadata
make gb-test         # validate the graph and write a workspace-specific snapshot
make gb-qa           # run the eight grounded QA cases
```

`lightrag_custom/sitecustomize.py` patches only the extraction prompts at
container startup; upstream LightRAG source is unchanged. The postprocessor
does not auto-merge duplicate entities and does not invent edges for isolated
nodes. It writes candidates and validation failures to
`state/schema_report.aeb_gb39901_v2.json` for review.

The generated index-ready Markdown is derived from the user-provided OCR file.
It repeats `source_clause` anchors before blocks and table rows while uploading
under the original filename, so citations remain recognizable. The OCR source
itself is never modified.

## Table-aware v3 experiment

The v2 workspace is preserved as baseline B1. Its fixed token chunker can split
an HTML table between the caption/header and data rows; repeated row-level
source comments also make this more likely. The B2 profile
`aeb_gb39901_v3_table_chunks` changes only the ingestion granularity:

- all 23 OCR HTML tables become independent, atomic LightRAG documents;
- tables 1/3/5 are explicitly owned by M1 clause 5.2.1.1 and tables 2/4/6 by
  N1 clause 5.2.1.2;
- narrative text becomes 23 bounded structural units;
- the 46 units are submitted through `/documents/texts`, with a 6000-token
  chunk budget and zero overlap;
- ingestion fails unless every structural document produces exactly one
  LightRAG chunk;
- the v3 profile raises the embedding timeout to 120 seconds and waits for an
  active queue to finish before retrying failed units (up to three rounds);
- six source-table rows and eight model answers are checked as numeric
  regressions.

```bash
make v3-doctor
make v3-prepare
make v3-up
make v3-ingest
make v3-postprocess
make v3-test
make v3-fact-qa
```

## Relation-guarded v4 experiment

The v4 workspace `aeb_gb39901_v4_relation_guard` keeps the 46 structural units
from B2 and adds a strict GB 39901 relation contract at three points:

- the extraction prompt lists all 42 allowed relation endpoint contracts;
- `lightrag_custom/schema_guard.py` validates each extracted edge before both
  Neo4j and relation-vector writes;
- `scripts/postprocess_graph.py` revalidates the merged graph.

```bash
make v4-doctor
make v4-prepare
make v4-up
make v4-ingest
make v4-postprocess
make v4-test
make v4-fact-qa
```

Verified local comparison on 2026-07-18 (structure / table facts):

| Metric | B2 table-aware | v4 relation-guarded |
| --- | ---: | ---: |
| Processed structural documents | 46 | 46 |
| Type-invalid relations | 106 | 0 |
| Exact table facts with source citation | 8/8 | 8/8 |

## Data safety

- `.env`, downloaded documents, indexes, Neo4j data, state, and result files
  are ignored by Git (see `.gitignore`).
- API keys are never included in fingerprints or reports.
- The embedding model and dimension are immutable after first indexing.
- No normal command deletes data. Explicit destructive command:

  ```bash
  make reset-index CONFIRM=RESET_AEB_INDEX
  ```

## Baseline boundary

This is an automatic GraphRAG **baseline** plus an agent harness, **not** a
strict automotive ontology or a regulatory rule engine. Do not use answers for
homologation without checking the official standard text.

## Project status map

See [`PROJECT_STATUS.md`](PROJECT_STATUS.md) for the end-to-end map of A0–v4,
pilot evidence, and harness status.
