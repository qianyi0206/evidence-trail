# EvidenceTrail thin app layer on top of official LightRAG.
# - No API keys, Neo4j volumes, or rag_storage data baked in.
# - Only lightrag_custom hooks (prompt profile + schema_guard via sitecustomize).
#
# Build from repo root (demo/aeb):
#   docker build -f docker/lightrag/Dockerfile -t evidencetrail-lightrag:v1.4.16-app .
#
# Or: make lightrag-image

ARG BASE_IMAGE=ghcr.io/hkuds/lightrag:v1.4.16
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.title="EvidenceTrail LightRAG (app layer)" \
      org.opencontainers.image.description="Official LightRAG plus EvidenceTrail lightrag_custom hooks; no secrets or index data" \
      org.opencontainers.image.source="https://github.com" \
      org.opencontainers.image.licenses="MIT"

USER root

COPY lightrag_custom/ /app/custom/

# sitecustomize is only auto-imported from site-packages, not arbitrary PYTHONPATH.
RUN python - <<'PY'
from __future__ import annotations

import pathlib
import shutil
import site
import sys

src = pathlib.Path("/app/custom/sitecustomize.py")
if not src.is_file():
    raise SystemExit(f"missing {src}")

targets = []
try:
    targets.extend(pathlib.Path(p) for p in site.getsitepackages())
except Exception:
    pass
if hasattr(site, "getusersitepackages"):
    try:
        targets.append(pathlib.Path(site.getusersitepackages()))
    except Exception:
        pass
# Fallback common layout inside slim images
targets.append(pathlib.Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages")

copied = False
for dest_dir in targets:
    if dest_dir.is_dir():
        shutil.copy2(src, dest_dir / "sitecustomize.py")
        print(f"installed sitecustomize -> {dest_dir / 'sitecustomize.py'}")
        copied = True
        break
if not copied:
    raise SystemExit(f"no writable site-packages found; tried: {targets}")
PY

# Profile modules (gb39901_profile*) import as top-level from /app/custom.
ENV PYTHONPATH=/app/custom

# Base image user if present; ignore failure on distros without it.
RUN id app >/dev/null 2>&1 && chown -R app:app /app/custom || true
