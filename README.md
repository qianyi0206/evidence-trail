# EvidenceTrail

**English** | [中文](README.zh-CN.md)

Graph-enhanced document evidence agent.

Built for closed-set, checkable knowledge (regulations, test procedures, manuals): answers must be grounded in indexed text; refuse when evidence is insufficient.

---

## 0. Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│                         EvidenceTrail                           │
│                                                                 │
│   PDF ──► OCR ──► Markdown ──► structural chunk / ingest         │
│            │                      │                             │
│            │ MinerU               ▼                             │
│            │              ┌──────────────┐  ┌────────────────┐  │
│            │              │ KG + vectors │◄─│ domain schema  │  │
│            │              │ LightRAG     │  │ relation rules │  │
│            │              └──────┬───────┘  └────────────────┘  │
│                                  │ retrieve                     │
│                                  ▼                              │
│                           ┌──────────────┐                      │
│                           │ Harness Agent│ plan→retrieve→       │
│                           │              │ reflect→gate         │
│                           └──────┬───────┘                      │
│                                  ▼                              │
│                           grounded answer / refuse              │
│                                  │                              │
│                                  ▼                              │
│                           ┌──────────────┐                      │
│                           │  Benchmark   │ offline eval         │
│                           └──────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
```

Architecture: [docs/architecture.svg](docs/architecture.svg)

CLI session (GIF):

![CLI](docs/demo/cli-pipeline-demo.gif)

```bash
cd harness
PYTHONPATH=. python3 -m reg_harness.cli --profile-env ../.env.gb39901_v4 chat
```

v4 knowledge graph (Neo4j workspace `aeb_gb39901_v4_relation_guard`):

| | |
|--|--|
| [Overview](docs/screenshots/neo4j-v4-overview.png) | Subgraph over clauses, requirements, thresholds, tests, … |
| [6.11 neighborhood](docs/screenshots/neo4j-v4-focus-6.11.png) | Local structure around false-response tests |

![v4 overview](docs/screenshots/neo4j-v4-overview.png)

![6.11 neighborhood](docs/screenshots/neo4j-v4-focus-6.11.png)

---

## 1. Problem

In intelligent driving Q&A, test specs, calibration, and diagnostics, questions often look like: speed thresholds under a scenario, false-trigger criteria, differences between test requirements. Answers usually already exist in standards or manuals—closed-set, verifiable facts. Relying only on model parameters risks fabricated clauses and wrong numbers.

Goal: answer strictly from the indexed corpus; refuse explicitly when evidence is missing.

---

## 2. Approach

### 2.1 RAG

Retrieve relevant passages, then generate from them.

```text
question ──► retrieve ──► generate
```

Typical pipelines are single-shot. On long documents and dense tables, one pass often misses context; bad chunking breaks numeric conditions; noisy context can still induce unsupported answers.

### 2.2 Agent control loop

A Harness agent turns single-shot RAG into multi-step evidence gathering:

```text
Classic RAG:   question ──► retrieve ──► answer

EvidenceTrail:
  question ──► Harness (plan → retrieve → reflect → decide) ──► grounded / refuse
                      │
                      └──► graph + vector backend
```

| | Classic RAG | EvidenceTrail |
|--|-------------|---------------|
| Flow | One retrieve + generate | Multi-step plan / retrieve / reflect |
| Querying | Often the full question once | Agent writes sub-queries and picks tools |
| Weak evidence | Often still answers | Keep gathering or refuse |
| Split | Retrieve + generate | Retrieval stack + control layer |

### 2.3 Knowledge graph, GraphRAG, LightRAG

A knowledge graph links requirements, tests, conditions, and thresholds. GraphRAG extends vector search with graph expansion, then returns to source text for generation.

```text
docs ──► chunk / extract ──► KG + vector index
                              │
                   query: expand on graph ──► source text ──► generate
```

Backend: open-source [LightRAG](https://github.com/HKUDS/LightRAG). Domain entity types, relation legality, and table-aware chunking are applied on the application side. This repo does not fork LightRAG core.

### 2.4 PDF and OCR

Sources are often PDFs; OCR / layout parsing to Markdown comes before chunking and indexing. We use [MinerU](https://github.com/opendatalab/MinerU):

| Mode | Link |
|------|------|
| Online | [https://mineru.net/](https://mineru.net/) |
| Local | [https://github.com/opendatalab/MinerU](https://github.com/opendatalab/MinerU) |

```text
PDF ──► MinerU ──► Markdown ──► structural chunk / ingest
```

Sample corpus lives under `corpus/prepared/` and `corpus/index_ready/` (historical export names may include `PaddleOCR-VL`; new docs can use MinerU).

### 2.5 Indexing: defaults vs application-side work

LightRAG default: length-based chunks → broad entity types → graph + vectors. On regulatory text this often breaks tables, over-generalizes types, adds noisy edges, and severs numbers from conditions.

Application-side improvements (no core fork):

| Change | What | Why |
|--------|------|-----|
| Structural chunking | Keep tables whole; split narrative by clause/unit (`prepare_gb39901_v3.py`) | Align thresholds with conditions |
| Domain schema | Clause / test / threshold types and prompts (`config/gb_39901_2025_schema.yml`) | Extract domain objects |
| Relation guard | Allow-list; keep / reverse / drop; no invent (`schema_guard.py`) | Fewer illegal edges |
| Graph locate + full-text backfill | Expand graph hits via `source_id` to full text units | Answer from source text |

```text
PDF ──► OCR ──► structural chunk ──► schema extract ──► relation guard ──► graph + vectors
query: graph expand ──► source text ──► agent gather / gate
```

New domains mainly need a new schema and chunk policy; the control layer can stay. v4 graph screenshots are above.

### 2.6 Control layer and eval isolation

The control layer sets roles, tools, refusal rules, and step limits—not per-question answer keys. Changing corpora means new indexes/schemas, not new “quiz scripts.” See [harness/PROTOCOL.md](harness/PROTOCOL.md).

```text
online:  agent reads only index + source text ──► answer
offline: gold answers / evidence ──► score after the fact
```

| Item | Default |
|------|---------|
| Decision path | skill (`HARNESS_PILOT_HEURISTICS=0`) |
| Evidence catalog | `none` (no gold load) |
| Clause/table precise tools | off (`HARNESS_ENABLE_PRECISE_LOOKUP=0`) |

Reporting tiers: P0 bare retrieval baseline; **P1** protocol agent (primary results); P2 quiz-tuned / gold catalog (appendix only).

---

## 3. Benchmark

Under `benchmark/`. Two stages with different roles.

### 3.1 Stages

```text
Stage 1: small gold set → score_kg / retrieval / answers → iterate index or agent
Stage 2: larger set → RAGAS-style reference-free metrics (planned; not in repo yet)
```

| Stage | Data | Tools | Purpose |
|-------|------|-------|---------|
| 1 | Gold questions & evidence | Built-in layered scorers | Diagnose and freeze design |
| 2 | Large question set | [RAGAS](https://docs.ragas.io/)-style metrics | Regression / trends |

Stage 2 does not replace stage 1; keep gold spot-checks after scale-up. RAGAS-style scores measure faithfulness/relevance to retrieved context, not legal correctness. Scoring is always offline.

### 3.2 Retrieval modes

| Mode | Role |
|------|------|
| `closed_book` | No-retrieval floor |
| `naive` | Vector only |
| `hybrid` / `mix` | Graph-enhanced |
| `oracle` | Gold-evidence ceiling |

Claims of graph gains should report evidence recall, path completeness, and final answers together. High KG score ≠ high retrieval ≠ correct answer.

Current evidence is mainly a pilot set and layered scripts (`self_checked`), not a frozen formal v1. See [benchmark/README.md](benchmark/README.md) and [pilot_6q_report.md](benchmark/results/pilot_6q_report.md).

### 3.3 Data and scripts

| Path | Role |
|------|------|
| [benchmark/data/questions.jsonl](benchmark/data/questions.jsonl) | Questions and references |
| [benchmark/data/evidence.jsonl](benchmark/data/evidence.jsonl) | Gold evidence |
| [benchmark/scripts/score_kg.py](benchmark/scripts/score_kg.py) | Graph scores |
| [benchmark/scripts/score_retrieval.py](benchmark/scripts/score_retrieval.py) | Retrieval scores |
| [benchmark/scripts/score_answers.py](benchmark/scripts/score_answers.py) | Answer scores |
| [benchmark/scripts/run_harness_benchmark.py](benchmark/scripts/run_harness_benchmark.py) | Agent runs |
| [benchmark/scripts/run_graphrag_benchmark.py](benchmark/scripts/run_graphrag_benchmark.py) | Multi-mode pipeline |

### 3.4 Example question types

| Type | ID | Question (sample domain: GB 39901) |
|------|-----|-------------------------------------|
| Direct fact | `gb_direct_001` | Which two vehicle categories does GB 39901—2025 apply to? |
| Conditional table | `gb_table_001` | Max relative collision speed for M1 at 60 km/h, stationary target, GVW? |
| Multi-hop | `gb_multi_hop_001` | Vehicle-target CW tests, latest timing vs emergency braking, and exception? |
| Compare | `gb_compare_001` | M1 vs N1 min activation speed range for vehicle targets; same for VRU? |
| Synthesis | `gb_synthesis_001` / `gb_multi_hop_006` | Link of 5.4 to 6.11, scenario count, shared pass behavior |
| Unanswerable | `gb_unanswerable_001` | Can simulation fully replace the five 6.11 false-response tests? |

Unanswerable items check refusal. High recall does not guarantee safe refusal.

### 3.5 Pilot notes

Graph retrieval often raises evidence coverage and noise. Structural chunking and relation guards improve table stability and graph legality but do not automatically improve QA accuracy. Outcomes still depend on rerank, source-text priority, sufficiency stop rules, gates, and multi-step control. See [pilot_6q_report.md](benchmark/results/pilot_6q_report.md).

---

## 4. Runtime

The model chooses tools; code owns bag merge, budgets, sufficiency, and hard gates. Gold answers never enter the online path.

Graph search locates and expands; numbers and table rows must come from `kind=chunk` source text. Entities/relations are navigation only.

### 4.1 Control loop

| Tool | Default | Role |
|------|---------|------|
| `graph_search` | on, `mix` | Graph-enhanced retrieve |
| `vector_search` | on, `naive` | Vector only |
| `evidence_check` | on | Bag consistency |
| `compose_answer` | on | Answer from bag |
| `finalize` | on | Refuse / terminal |
| `clause_lookup` / `table_lookup` | off | Precise tools (opt-in) |

```text
question → plan → graph/vector retrieve → source_id chunk backfill
         → compact (dedupe / rerank / text-primary)
         → sufficiency / force-compose → compose → gates → answer
         if incomplete, new query and continue
```

### 4.2 Evidence bag

| kind | Role |
|------|------|
| `relationship` / `entity` | Navigation / support |
| `chunk` | Primary facts and numbers (incl. backfilled full text) |

Graph-only modes often return entities/relations with no text units; default `mix` plus `source_id` backfill. Code: `lightrag_retrieve.py`, `compact.py`, `types.evidence_text`, `compose_answer.py`.

### 4.3 Sufficiency and stop rules

Code audits the bag (`sufficiency.py`, `bag_gaps.py`): e.g. missing clause from the question, “see Table N” without table body. Sufficiency is an anti-spin heuristic, not semantic correctness.

| Condition (non-empty bag) | Action |
|---------------------------|--------|
| Stagnant ≥ 2 | Soft prompt to compose |
| Duplicate retrieve ≥ 2 or stagnant ≥ 3 | Force compose |
| Sufficient and still stagnant / zero added | Force compose |

Empty bags never force compose; max steps end in refuse or force compose if the bag is non-empty.

### 4.4 Hard gates

| Rule | Behavior |
|------|----------|
| Compose with empty bag | Reject |
| Answer numbers ≥ 5 | Must appear in bag text (incl. spaced thousands) |
| Ungrounded | May continue gather; no silent pass |
| `finalize` | Must not bypass compose for a “yes” answer |

### 4.5 Example: false-response thread

```text
question (5.4 ↔ 6.11, scenarios, shared pass behavior)
  → graph_search → backfill → sufficiency → compose → gates
```

Full trace: `--dump-trace path.json`.

---

## 5. Repository layout

```text
harness/           # Agent
lightrag_custom/   # extraction prompts, relation guard
config/            # domain schema
scripts/           # prepare / ingest / postprocess
benchmark/         # evaluation
corpus/            # sample corpus
data/rag_storage/  # v4 vector/KV snapshot (no LLM cache)
docs/              # architecture, screenshots, CLI GIF
docker/            # optional thin image
compose.yaml
Makefile
```

| In git | Not in git |
|--------|------------|
| App code, schema, prepared corpus, v4 snapshot, benchmark data & reports | LightRAG sources, Neo4j volumes, `.env`, raw PDFs, non-v4 workspaces, LLM cache |

See [NOTICE.md](NOTICE.md), [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 6. Run

### 6.1 Topology

```text
Docker: Neo4j :7474/:7687 · LightRAG :9621 (mounts rag_storage, lightrag_custom)
Python: reg_harness ──HTTP──► LightRAG
```

| Mode | Command |
|------|---------|
| Default | `make v4-up` (official LightRAG image) |
| Thin app image | `make lightrag-image` && `make v4-up-app` |

Details: [docker/README.md](docker/README.md). Neo4j Browser: `http://127.0.0.1:7474`.

### 6.2 Config

Needs: Docker, Python 3.10+, chat + embedding APIs.

```bash
git clone https://github.com/qianyi0206/evidence-trail.git
cd evidence-trail

pip install -r requirements.txt
cd harness && pip install -e . && cd ..

cp .env.example .env
# set NEO4J_PASSWORD, LLM_*, EMBEDDING_*; optional RERANK_*
```

Secret-free overlay: `.env.gb39901_v4`.

### 6.3 Steps

```text
1. cd harness && python3 -m unittest discover -s tests -v
2. (optional) MinerU PDF → Markdown → corpus/prepared/
3. make v4-up
4. if graph empty: make v4-prepare && make v4-ingest …
5. cd harness && PYTHONPATH=. python3 -m reg_harness.cli \
     --profile-env ../.env.gb39901_v4 chat
6. (optional) benchmark/scripts/ …
```

One-shot ask (default: live process log; planning may stream model tokens; `--no-live` disables):

```bash
cd harness
PYTHONPATH=. python3 -m reg_harness.cli --profile-env ../.env.gb39901_v4 \
  ask "What is the link between the no false-response requirement and section 6.11 tests? How many 6.11 sub-scenarios are there, and what is the shared pass behavior?" \
  --max-steps 8

PYTHONPATH=. python3 -m reg_harness.cli --profile-env ../.env.gb39901_v4 \
  ask "Which two vehicle categories does GB 39901—2025 apply to?" --max-steps 6
```

```python
from reg_harness import build_stack

stack = build_stack(profile_env=".env.gb39901_v4")
state = stack.ask("Which two vehicle categories does GB 39901 apply to?", max_steps=6)
print(state.final_answer)
```

When using the shipped vector snapshot, embedding model and dimension must match ingest (`state/embedding_fingerprint*.json`).

---

## 7. Scope

- Engineering demo, not a production knowledge platform or type-approval tool.
- Gates reduce unsupported generation; they do not guarantee zero error.
- No frozen formal overall accuracy; see [pilot_6q_report.md](benchmark/results/pilot_6q_report.md).
- Sample corpus is for study only: [NOTICE.md](NOTICE.md).
- [CONTRIBUTING.md](CONTRIBUTING.md) · [MIT](LICENSE) · [harness/PROTOCOL.md](harness/PROTOCOL.md)
