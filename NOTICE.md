# Third-party notices

## LightRAG

This project **does not vendor** the [LightRAG](https://github.com/HKUDS/LightRAG) source tree.

- **Role here:** graph + vector indexing and `/query` retrieval backend.
- **How we use it:** Docker image `ghcr.io/hkuds/lightrag` (pinned in `compose.yaml` / `.env.example`), plus optional local API at `http://127.0.0.1:9621`.
- **Our customisation (this repo):**
  - `lightrag_custom/` — prompt profiles and relation `schema_guard` (loaded via container `PYTHONPATH` / `sitecustomize`)
  - `scripts/` — prepare / ingest / probe helpers
  - `harness/` — multi-step regulation evidence **Agent** (tools, guards, sufficiency audit)
  - `benchmark/` — offline eval data and scorers

LightRAG remains under its own license and copyright (HKUDS and contributors).  
If you distribute a modified LightRAG binary or fork, follow **their** LICENSE, not only this repository’s MIT license.

## Regulation text

GB 39901 and related standards are **not** redistributed as official PDFs in this repository.  
Place OCR / prepared markdown under `corpus/` locally for educational use only.  
Do not treat demo answers as homologation advice; always verify against the official publication.
