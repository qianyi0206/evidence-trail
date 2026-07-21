SHELL := /bin/sh

COMPOSE := docker compose --env-file .env -f compose.yaml
TOOLS := $(COMPOSE) run --rm --build tools
GB_PROFILE := .env.gb39901
GB_COMPOSE := docker compose --env-file .env --env-file $(GB_PROFILE) -f compose.yaml
GB_TOOLS := $(GB_COMPOSE) run --rm --build tools
V3_PROFILE := .env.gb39901_v3
V3_COMPOSE := docker compose --env-file .env --env-file $(V3_PROFILE) -f compose.yaml
V3_TOOLS := $(V3_COMPOSE) run --rm --build tools
V4_PROFILE := .env.gb39901_v4
V4_COMPOSE := docker compose --env-file .env --env-file $(V4_PROFILE) -f compose.yaml
V4_TOOLS := $(V4_COMPOSE) run --rm --build tools
BENCHMARK_PYTHON ?= python3

.PHONY: configure doctor up download prepare ingest test demo down reset-index \
	gb-doctor gb-prepare gb-up gb-ingest gb-postprocess gb-test gb-qa gb-demo gb-down \
	v3-doctor v3-prepare v3-up v3-ingest v3-postprocess v3-test v3-fact-qa v3-qa v3-demo v3-down \
	v4-doctor v4-prepare v4-up v4-ingest v4-postprocess v4-test v4-fact-qa v4-qa v4-demo v4-down \
	benchmark-build benchmark-validate benchmark-kg-offline benchmark-kg-live benchmark-run-a0 benchmark-run-v2 \
	benchmark-run-v3 benchmark-run-v4 benchmark-score-a0 benchmark-score-v2 benchmark-score-v3 \
	benchmark-score-v4 benchmark-test benchmark-report

configure:
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example; fill in model credentials before indexing."; fi

doctor: configure
	@command -v docker >/dev/null || { echo "Docker CLI is not installed."; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Docker daemon is unavailable. Start Docker Desktop first."; exit 1; }
	@$(COMPOSE) config --quiet
	@$(TOOLS) scripts/probe_models.py

up: configure
	@docker info >/dev/null 2>&1 || { echo "Docker daemon is unavailable. Start Docker Desktop first."; exit 1; }
	@$(COMPOSE) pull neo4j lightrag
	@$(COMPOSE) up -d neo4j lightrag
	@$(TOOLS) scripts/wait_services.py

download: configure
	@$(TOOLS) scripts/download_docs.py

prepare: configure
	@$(TOOLS) scripts/prepare_docs.py
	@$(TOOLS) scripts/test_demo.py --offline

ingest: doctor up
	@$(TOOLS) scripts/ingest.py

test: configure
	@$(TOOLS) scripts/test_demo.py --offline
	@$(TOOLS) scripts/test_demo.py --snapshot
	@$(COMPOSE) restart neo4j lightrag
	@$(TOOLS) scripts/wait_services.py
	@$(TOOLS) scripts/test_demo.py --compare-snapshot --qa

demo: doctor download prepare up ingest test

down: configure
	@$(COMPOSE) down

gb-doctor: configure
	@command -v docker >/dev/null || { echo "Docker CLI is not installed."; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Docker daemon is unavailable. Start Docker Desktop first."; exit 1; }
	@test -f $(GB_PROFILE) || { echo "Missing $(GB_PROFILE)."; exit 1; }
	@$(GB_COMPOSE) config --quiet
	@$(GB_TOOLS) scripts/prepare_gb39901.py --check
	@$(GB_TOOLS) scripts/probe_models.py

gb-prepare: configure
	@$(GB_TOOLS) scripts/prepare_gb39901.py

gb-up: configure
	@docker info >/dev/null 2>&1 || { echo "Docker daemon is unavailable. Start Docker Desktop first."; exit 1; }
	@$(GB_COMPOSE) up -d neo4j lightrag
	@$(GB_TOOLS) scripts/wait_services.py

gb-ingest: configure
	@$(GB_TOOLS) scripts/ingest.py

gb-postprocess: configure
	@$(GB_TOOLS) scripts/postprocess_graph.py --apply

gb-test: configure
	@$(GB_TOOLS) scripts/test_demo.py --offline
	@$(GB_TOOLS) scripts/test_demo.py --snapshot

gb-qa: configure
	@$(GB_TOOLS) scripts/test_demo.py --qa

gb-demo:
	@$(MAKE) gb-doctor
	@$(MAKE) gb-prepare
	@$(MAKE) gb-up
	@$(MAKE) gb-ingest
	@$(MAKE) gb-postprocess
	@$(MAKE) gb-test

gb-down: configure
	@$(GB_COMPOSE) down

v3-doctor: configure
	@command -v docker >/dev/null || { echo "Docker CLI is not installed."; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Docker daemon is unavailable. Start Docker Desktop first."; exit 1; }
	@test -f $(V3_PROFILE) || { echo "Missing $(V3_PROFILE)."; exit 1; }
	@$(V3_COMPOSE) config --quiet
	@$(V3_TOOLS) scripts/prepare_gb39901_v3.py --check
	@$(V3_TOOLS) scripts/probe_models.py

v3-prepare: configure
	@$(V3_TOOLS) scripts/prepare_gb39901_v3.py
	@$(V3_TOOLS) scripts/test_structural_chunks.py

v3-up: configure
	@docker info >/dev/null 2>&1 || { echo "Docker daemon is unavailable. Start Docker Desktop first."; exit 1; }
	@$(V3_COMPOSE) up -d neo4j lightrag
	@$(V3_TOOLS) scripts/wait_services.py

v3-ingest: configure
	@$(V3_TOOLS) scripts/ingest_structural.py

v3-postprocess: configure
	@$(V3_TOOLS) scripts/postprocess_graph.py --apply

v3-test: configure
	@$(V3_TOOLS) scripts/test_structural_chunks.py
	@$(V3_TOOLS) scripts/test_demo.py --snapshot

v3-fact-qa: configure
	@$(V3_TOOLS) scripts/test_fact_qa.py

v3-qa: configure
	@$(V3_TOOLS) scripts/test_demo.py --qa

v3-demo:
	@$(MAKE) v3-doctor
	@$(MAKE) v3-prepare
	@$(MAKE) v3-up
	@$(MAKE) v3-ingest
	@$(MAKE) v3-postprocess
	@$(MAKE) v3-test
	@$(MAKE) v3-fact-qa

v3-down: configure
	@$(V3_COMPOSE) down

v4-doctor: configure
	@command -v docker >/dev/null || { echo "Docker CLI is not installed."; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Docker daemon is unavailable. Start Docker Desktop first."; exit 1; }
	@test -f $(V4_PROFILE) || { echo "Missing $(V4_PROFILE)."; exit 1; }
	@$(V4_COMPOSE) config --quiet
	@$(V4_TOOLS) scripts/prepare_gb39901_v3.py --check
	@$(V4_TOOLS) scripts/test_schema_guard.py
	@$(V4_TOOLS) scripts/probe_models.py

v4-prepare: configure
	@$(V4_TOOLS) scripts/prepare_gb39901_v3.py
	@$(V4_TOOLS) scripts/test_structural_chunks.py
	@$(V4_TOOLS) scripts/test_schema_guard.py

v4-up: configure
	@docker info >/dev/null 2>&1 || { echo "Docker daemon is unavailable. Start Docker Desktop first."; exit 1; }
	@$(V4_COMPOSE) up -d neo4j lightrag
	@$(V4_TOOLS) scripts/wait_services.py

v4-ingest: configure
	@$(V4_TOOLS) scripts/ingest_structural.py

v4-postprocess: configure
	@$(V4_TOOLS) scripts/postprocess_graph.py --apply --repair-invalid --merge-explicit-aliases --strict

v4-test: configure
	@$(V4_TOOLS) scripts/test_schema_guard.py
	@$(V4_TOOLS) scripts/test_structural_chunks.py
	@$(V4_TOOLS) scripts/test_demo.py --snapshot

v4-fact-qa: configure
	@$(V4_TOOLS) scripts/test_fact_qa.py

v4-qa: configure
	@$(V4_TOOLS) scripts/test_demo.py --qa

v4-demo:
	@$(MAKE) v4-doctor
	@$(MAKE) v4-prepare
	@$(MAKE) v4-up
	@$(MAKE) v4-ingest
	@$(MAKE) v4-postprocess
	@$(MAKE) v4-test
	@$(MAKE) v4-fact-qa

v4-down: configure
	@$(V4_COMPOSE) down

benchmark-build:
	@$(BENCHMARK_PYTHON) benchmark/scripts/curate_benchmark.py --limit 60

benchmark-validate: benchmark-build
	@$(BENCHMARK_PYTHON) benchmark/scripts/validate_benchmark.py --write-review

benchmark-kg-offline: benchmark-build
	@$(BENCHMARK_PYTHON) benchmark/scripts/export_lightrag_kg.py --workspace aeb_demo --output benchmark/results/kg_a0.jsonl
	@$(BENCHMARK_PYTHON) benchmark/scripts/export_lightrag_kg.py --workspace aeb_gb39901_v2 --output benchmark/results/kg_v2.jsonl
	@$(BENCHMARK_PYTHON) benchmark/scripts/export_lightrag_kg.py --workspace aeb_gb39901_v3_table_chunks --output benchmark/results/kg_v3.jsonl
	@$(BENCHMARK_PYTHON) benchmark/scripts/export_lightrag_kg.py --workspace aeb_gb39901_v4_relation_guard --output benchmark/results/kg_v4.jsonl
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_kg.py --predicted benchmark/results/kg_a0.jsonl --output benchmark/results/kg_score_a0.json
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_kg.py --predicted benchmark/results/kg_v2.jsonl --output benchmark/results/kg_score_v2.json
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_kg.py --predicted benchmark/results/kg_v3.jsonl --output benchmark/results/kg_score_v3.json
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_kg.py --predicted benchmark/results/kg_v4.jsonl --output benchmark/results/kg_score_v4.json

benchmark-kg-live: benchmark-build
	@$(TOOLS) benchmark/scripts/export_lightrag_kg.py --live --output benchmark/results/kg_a0_live.jsonl
	@$(GB_TOOLS) benchmark/scripts/export_lightrag_kg.py --live --profile-env $(GB_PROFILE) --output benchmark/results/kg_v2_live.jsonl
	@$(V3_TOOLS) benchmark/scripts/export_lightrag_kg.py --live --profile-env $(V3_PROFILE) --output benchmark/results/kg_v3_live.jsonl
	@$(V4_TOOLS) benchmark/scripts/export_lightrag_kg.py --live --profile-env $(V4_PROFILE) --output benchmark/results/kg_v4_live.jsonl
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_kg.py --predicted benchmark/results/kg_a0_live.jsonl --output benchmark/results/kg_score_a0_live.json
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_kg.py --predicted benchmark/results/kg_v2_live.jsonl --output benchmark/results/kg_score_v2_live.json
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_kg.py --predicted benchmark/results/kg_v3_live.jsonl --output benchmark/results/kg_score_v3_live.json
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_kg.py --predicted benchmark/results/kg_v4_live.jsonl --output benchmark/results/kg_score_v4_live.json

benchmark-run-a0: up benchmark-validate
	@$(TOOLS) benchmark/scripts/run_graphrag_benchmark.py --profile-env "" --source-set gb --output benchmark/results/run_a0.jsonl --resume

benchmark-run-v2: gb-up benchmark-validate
	@$(GB_TOOLS) benchmark/scripts/run_graphrag_benchmark.py --profile-env $(GB_PROFILE) --source-set gb --output benchmark/results/run_v2.jsonl --resume

benchmark-run-v3: v3-up benchmark-validate
	@$(V3_TOOLS) benchmark/scripts/run_graphrag_benchmark.py --profile-env $(V3_PROFILE) --source-set gb --output benchmark/results/run_v3.jsonl --resume

benchmark-run-v4: v4-up benchmark-validate
	@$(V4_TOOLS) benchmark/scripts/run_graphrag_benchmark.py --profile-env $(V4_PROFILE) --source-set gb --output benchmark/results/run_v4.jsonl --resume

benchmark-score-a0:
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_retrieval.py --results benchmark/results/run_a0.jsonl --output benchmark/results/retrieval_score_a0.json
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_answers.py --results benchmark/results/run_a0.jsonl --output benchmark/results/answer_score_a0.json

benchmark-score-v2:
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_retrieval.py --results benchmark/results/run_v2.jsonl --output benchmark/results/retrieval_score_v2.json
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_answers.py --results benchmark/results/run_v2.jsonl --output benchmark/results/answer_score_v2.json

benchmark-score-v3:
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_retrieval.py --results benchmark/results/run_v3.jsonl --output benchmark/results/retrieval_score_v3.json
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_answers.py --results benchmark/results/run_v3.jsonl --output benchmark/results/answer_score_v3.json

benchmark-score-v4:
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_retrieval.py --results benchmark/results/run_v4.jsonl --output benchmark/results/retrieval_score_v4.json
	@$(BENCHMARK_PYTHON) benchmark/scripts/score_answers.py --results benchmark/results/run_v4.jsonl --output benchmark/results/answer_score_v4.json

benchmark-test: benchmark-validate
	@$(BENCHMARK_PYTHON) -m unittest discover -s benchmark/tests -v

benchmark-report:
	@$(BENCHMARK_PYTHON) benchmark/scripts/generate_report.py \
		--kg-score A0=benchmark/results/kg_score_a0_live.json \
		--kg-score A1-v2=benchmark/results/kg_score_v2_live.json \
		--kg-score A2-v3=benchmark/results/kg_score_v3_live.json \
		--kg-score A3-v4=benchmark/results/kg_score_v4_live.json \
		--pilot-comparison benchmark/results/pilot_6q_comparison.json \
		--output benchmark/results/benchmark_report.md

reset-index: configure
	@if [ "$(CONFIRM)" != "RESET_AEB_INDEX" ]; then echo "Refusing to delete data. Run: make reset-index CONFIRM=RESET_AEB_INDEX"; exit 1; fi
	@$(COMPOSE) down
	@rm -rf ./data/rag_storage ./data/inputs ./data/neo4j ./state/embedding_fingerprint.json ./state/ingest_report.json ./state/runtime_snapshot.json
	@mkdir -p ./data/rag_storage ./data/inputs ./data/neo4j ./state
	@echo "AEB index data was deleted; downloaded source documents were preserved."
