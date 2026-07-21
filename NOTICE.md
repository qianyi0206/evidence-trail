# Third-party notices

**EvidenceTrail** is an application-layer project (document evidence agent / Agentic RAG).  
It **does not vendor** the [LightRAG](https://github.com/HKUDS/LightRAG) source tree.

## LightRAG

- **Role here:** graph + vector indexing and `/query` retrieval backend.
- **How we use it:** Docker image `ghcr.io/hkuds/lightrag` (pinned in `compose.yaml` / `.env.example`), plus optional local API at `http://127.0.0.1:9621`.
- **Our customisation (this repo):**
  - `lightrag_custom/` — prompt profiles and relation `schema_guard` (loaded via container `PYTHONPATH` / `sitecustomize`)
  - optional thin image: `docker/lightrag/Dockerfile` builds `FROM` official LightRAG and only bakes those hooks (no secrets, no index data); see `docker/README.md`
  - `scripts/` — prepare / ingest / probe helpers
  - `harness/` — **EvidenceTrail** agent (`reg_harness`: tools, guards, sufficiency audit, traces)
  - `benchmark/` — offline eval data and scorers (case study: GB 39901 AEBS)

LightRAG remains under its own license and copyright (HKUDS and contributors).  
If you distribute a modified LightRAG binary or fork, follow **their** LICENSE, not only this repository’s MIT license.

## Regulation text

This repository may include **prepared / index-ready markdown** under `corpus/` for educational GraphRAG demos.  
It does **not** claim to be an official distribution of GB 39901 or other standards.  
Raw OCR/PDF dumps (`corpus/raw`) and Neo4j database volumes stay local and are gitignored.  
Do not treat demo answers as homologation advice; always verify against the official publication.
