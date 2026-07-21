# Contributing

Thanks for interest in this demo. It is an **application layer** on top of [LightRAG](https://github.com/HKUDS/LightRAG), focused on GB 39901 AEBS regulation QA.

## Ground rules

1. **Do not commit secrets** — never add `.env` with real API keys. Use `.env.example` and non-secret overlays (`.env.gb39901*`).
2. **Do not commit Neo4j volumes** (`data/neo4j/`) or non-v4 workspaces. Final vector/KV snapshot is only `data/rag_storage/aeb_gb39901_v4_relation_guard/` (without LLM cache).
3. **Prefer small PRs** — harness behavior, scoring, docs, or ingest scripts separately when possible.
4. **Keep gold offline** — online agent path must not load benchmark gold unless `HARNESS_CATALOG_MODE=gold` is explicit.

## Dev setup

```bash
# Python 3.10+
pip install -r requirements.txt
cd harness && pip install -e . && cd ..

# Unit tests (no LLM / Docker required for most)
cd harness && python3 -m unittest discover -s tests -v
cd ../benchmark && PYTHONPATH=scripts python3 -m unittest tests.test_benchmark -v
```

Live stack: Docker Desktop, copy `.env.example` → `.env`, then `make v4-up` (see README).

## Code style

- Python: 4-space indent, type hints where practical, `logging` / existing patterns over ad-hoc prints in long-lived code.
- Agent control logic lives in `harness/reg_harness/`; LightRAG monkey-patches stay in `lightrag_custom/`.
- English for code comments; user-facing agent prompts may be Chinese (regulation domain).

## Before you open a PR

- [ ] `python3 -m unittest discover -s harness/tests` (or `cd harness && python3 -m unittest discover -s tests`)
- [ ] No new secrets or large binaries
- [ ] README / PROTOCOL updated if behavior or isolation rules change
- [ ] Clear description of *what* and *why*

## Reporting issues

Include: OS, Python version, whether Docker/LightRAG was up, profile (e.g. `.env.gb39901_v4`), and a minimal question or command that fails. Redact API keys.

## License

Contributions are accepted under the repository [MIT License](LICENSE). LightRAG remains under its own license — see [NOTICE.md](NOTICE.md).
