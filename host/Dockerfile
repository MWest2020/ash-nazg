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


# --- Stage 2b: frpc — the HaRP tunnel client -------------------------------
#
# A HaRP deploy daemon reaches an ExApp only through the FRP tunnel the
# ExApp itself opens (haproxy's `ex_apps` frontend has no route to a
# directly-bound container port). So the image ships `frpc`; `start.sh`
# launches it when HP_SHARED_KEY is present.
#
# Pinned + SHA256-verified per the HaRP integration guide.
FROM debian:bookworm-slim AS frpc-build
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
ARG FRP_VERSION=0.61.1
ARG FRP_AMD64_SHA256=bff260b68ca7b1461182a46c4f34e9709ba32764eed30a15dd94ac97f50a2c40
ARG FRP_ARM64_SHA256=af6366f2b43920ebfe6235dba6060770399ed1fb18601e5818552bd46a7621f8
RUN set -ex; \
    ARCH=$(uname -m); \
    if [ "$ARCH" = "aarch64" ]; then FRP_ARCH="arm64"; FRP_SHA256="${FRP_ARM64_SHA256}"; \
    else FRP_ARCH="amd64"; FRP_SHA256="${FRP_AMD64_SHA256}"; fi; \
    curl -fsSL "https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_${FRP_ARCH}.tar.gz" -o /tmp/frp.tar.gz; \
    [ "$(sha256sum /tmp/frp.tar.gz | cut -d' ' -f1)" = "$FRP_SHA256" ]; \
    tar -C /tmp -xzf /tmp/frp.tar.gz; \
    cp /tmp/frp_${FRP_VERSION}_linux_${FRP_ARCH}/frpc /usr/local/bin/frpc; \
    rm -rf /tmp/frp_${FRP_VERSION}_linux_${FRP_ARCH} /tmp/frp.tar.gz


# --- Stage 3: runtime ------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Non-root user. UID/GID are fixed so volume mounts stay predictable.
# curl is the HaRP-aware healthcheck's only way to probe a unix socket.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=python-build  /app/.venv               /app/.venv
COPY --from=python-build  /app/src                 /app/src
COPY --from=frontend-build /work/host/static       /app/static

# Translation files (info.xml's <translations-folder>/app/l10n).
COPY l10n/             /app/l10n/
# App metadata (info.xml — AppAPI may re-read it at registration).
COPY appinfo/info.xml  /app/appinfo/info.xml
COPY --from=frpc-build /usr/local/bin/frpc /usr/local/bin/frpc
COPY host/start.sh     /start.sh
RUN chmod +x /start.sh

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
# HaRP waits for this to report healthy before it registers the ExApp,
# and under HaRP there is no TCP port to probe — the app listens on the
# unix socket that frpc tunnels — so the check follows the same switch
# as start.sh.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD sh -c 'if [ -n "$HP_SHARED_KEY" ]; then \
        curl -fsS --unix-socket /tmp/exapp.sock http://localhost/health >/dev/null; \
    else \
        curl -fsS "http://127.0.0.1:${APP_PORT:-8080}/health" >/dev/null; \
    fi'

# How AppAPI/HaRP spawns this container as a docker-install ExApp:
# APP_PORT (e.g. 23000), APP_HOST=127.0.0.1, APP_SECRET, HP_SHARED_KEY
# and HP_FRP_ADDRESS/HP_FRP_PORT arrive as env vars. Under HaRP the
# daemon reaches the ExApp ONLY through the FRP tunnel, so uvicorn
# binds the unix socket start.sh tunnels (umask 0177 → 0600) instead of
# a TCP port. Without HP_SHARED_KEY (manual-install / docker-socket-
# proxy) start.sh is a pass-through and uvicorn binds TCP as before.
ENTRYPOINT ["/start.sh"]
CMD ["sh", "-c", "if [ -n \"$HP_SHARED_KEY\" ]; then umask 0177; exec uvicorn ash_nazg.main:app --uds /tmp/exapp.sock; else exec uvicorn ash_nazg.main:app --host 0.0.0.0 --port ${APP_PORT:-8080}; fi"]
