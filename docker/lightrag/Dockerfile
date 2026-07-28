# EvidenceTrail thin app layer on top of official LightRAG.
# - No API keys, Neo4j volumes, or rag_storage data baked in.
# - Only lightrag_custom hooks (prompt profile + schema_guard via sitecustomize).
#
# Build from repo root (demo/aeb):
#   docker build -f docker/lightrag/Dockerfile -t evidencetrail-lightrag:v1.4.16-app .
#
# Or: make lightrag-image

ARG BASE_IMAGE=ghcr.io/hkuds/lightrag:v1.4.16@sha256:67ccf8d9f74eb29da872bf8b3e6513605f5ac601fb0509c5b0ca16d98d2d307d
FROM ${BASE_IMAGE}

ARG APP_UID=1000
ARG APP_GID=1000

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
ENV PYTHONPATH=/app/custom \
    HOME=/tmp

# Do not retain the root build user at runtime. The Compose overlay may override
# this numeric identity with the host UID/GID for writable bind mounts.
RUN set -eu; \
    if ! getent group "${APP_GID}" >/dev/null 2>&1; then \
        groupadd --gid "${APP_GID}" app; \
    fi; \
    if ! getent passwd "${APP_UID}" >/dev/null 2>&1; then \
        useradd --uid "${APP_UID}" --gid "${APP_GID}" --home-dir /app \
            --shell /usr/sbin/nologin app; \
    fi; \
    mkdir -p /app/data/rag_storage /app/data/inputs; \
    chown -R "${APP_UID}:${APP_GID}" /app/custom /app/data

USER ${APP_UID}:${APP_GID}
