# syntax=docker/dockerfile:1.7
#
# Ash Nazg host shim — multi-stage build.
#
# Build context is the repo root (so the frontend build stage can see
# `frontend/` alongside `host/`). Invoke with:
#
#   docker build -t ash-nazg-host -f host/Dockerfile .
#
# Three stages:
#   1. frontend-build — Node 22, runs `npm ci --ignore-scripts &&
#      npm run build`. Vite writes the bundle to `host/static/` per
#      `frontend/vite.config.ts`.
#   2. python-build   — Python 3.12, runs `uv sync --frozen --no-dev`.
#   3. runtime        — slim Python image, non-root user, uvicorn.
#
# Each stage starts fresh; layer caching keeps repeat builds quick
# when only one tier changes.

# --- Stage 1: frontend bundle ----------------------------------------------
FROM node:22-bookworm-slim AS frontend-build

WORKDIR /work/frontend

# Lockfile + manifest first so the npm install layer caches across
# source-only changes.
COPY frontend/package.json frontend/package-lock.json ./

# `--ignore-scripts` is project policy (supply-chain safety: postinstall
# scripts are the dominant attack vector). Re-enable only for specific
# packages with documented need.
RUN npm ci --ignore-scripts \
    && npm audit signatures

# Now the source tree.
COPY frontend/ ./

# Vite's outDir is `../host/static` → ends up at /work/host/static.
RUN npm run build


# --- Stage 2: python venv with uv ------------------------------------------
FROM python:3.12-slim-bookworm AS python-build

# `pip install uv` is the documented uv bootstrap path. Pinned for
# reproducibility.
ENV UV_VERSION=0.5.6
RUN pip install --no-cache-dir "uv==${UV_VERSION}"

WORKDIR /app

COPY host/pyproject.toml ./
COPY host/uv.lock ./
COPY host/src/ ./src/

RUN uv sync --frozen --no-dev


# --- Stage 3: runtime ------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Non-root user. UID/GID are fixed so volume mounts stay predictable.
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=python-build  /app/.venv               /app/.venv
COPY --from=python-build  /app/src                 /app/src
COPY --from=frontend-build /work/host/static       /app/static

# Translation files (info.xml's <translations-folder>/app/l10n).
COPY l10n/             /app/l10n/
# App metadata (info.xml — AppAPI may re-read it at registration).
COPY appinfo/info.xml  /app/appinfo/info.xml

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    APP_HOST=0.0.0.0 \
    APP_PORT=8080

USER app

EXPOSE 8080

# Liveness independent of AppAPI's /heartbeat handshake, so an
# orchestrator can probe the container even before AppAPI registration.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"APP_PORT\",\"8080\")}/health',timeout=3).status==200 else 1)"

# When AppAPI/HaRP spawns this container as a docker-install
# ExApp, APP_PORT comes in as an env var assigned by AppAPI (e.g.
# APP_PORT=23000). APP_HOST also comes in but with value 127.0.0.1
# — the "AppAPI expects an in-container frpc to reverse-tunnel"
# convention. We don't ship frpc inside the host image; instead we
# bind uvicorn on 0.0.0.0 so NC (and HaRP's HTTP proxy on 8780)
# can reach the container's port directly via its compose-network
# IP. The APP_HOST env from HaRP is ignored.
CMD ["sh", "-c", "exec uvicorn ash_nazg.main:app --host 0.0.0.0 --port ${APP_PORT:-8080}"]
