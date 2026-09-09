# syntax=docker/dockerfile:1.7
#
# Ash Nazg host shim — multi-stage build.
#
# Build context is the repo root (so the frontend build stage can see
# `frontend/` alongside `host/`). Invoke with:
#
#   docker build -t ash-nazg-host -f host/Dockerfile .
#
# Four stages:
#   1. frontend-build — Node 22, runs `npm ci --ignore-scripts &&
#      npm run build`. Vite writes the bundle to `host/static/` per
#      `frontend/vite.config.ts`.
#   2. python-build   — Ubuntu 24.04 + uv, runs `uv sync --frozen --no-dev`.
#   3. frpc-build     — fetches the pinned HaRP tunnel client.
#   4. runtime        — Ubuntu 24.04: the shim AND the engine.
#
# Why Ubuntu and not python:3.12-slim: since the engine-in-image
# decision the runtime carries dosbox-x and KasmVNC alongside uvicorn.
# `dosbox-x` is packaged in Ubuntu universe and not in Debian (which
# only has the older `dosbox`), and KasmVNC ships matching `noble`
# .debs. The venv is therefore built on the same base it runs on, so
# its interpreter path (/usr/bin/python3) resolves in both stages.
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
FROM ubuntu:24.04 AS python-build

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates python3.12 python3.12-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

# `pip install uv` is the documented uv bootstrap path. Pinned for
# reproducibility. --break-system-packages because this throwaway build
# stage IS the environment uv then manages (PEP 668 guards interactive
# systems, not a single-purpose image layer).
ENV UV_VERSION=0.5.6
RUN pip install --no-cache-dir --break-system-packages "uv==${UV_VERSION}"

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


# --- Stage 4: runtime — the shim and the engine -----------------------------
FROM ubuntu:24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive

# KASMVNC_VERSION must match an upstream GitHub release tag of
# https://github.com/kasmtech/KasmVNC. Verified 2026-05-09: v1.4.0 ships
# kasmvncserver_noble_1.4.0_{amd64,arm64}.deb.
ARG KASMVNC_VERSION=1.4.0
ARG TARGETARCH

# python3 (24.04 = 3.12) runs the shim — the venv's console scripts
# resolve /usr/bin/python3, so the bare `python3.12` package is not
# enough on its own; dosbox-x + KasmVNC run the sessions; curl is
# the HaRP-aware healthcheck's only way to probe a unix socket; tini reaps
# the session processes the shim spawns. No davfs2: an in-image session
# gets its binary as a plain download into a per-session directory, so
# there is no mount and no privilege to ask for.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        dosbox-x \
        openssl \
        python3 \
        tini \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
        amd64) deb_arch=amd64 ;; \
        arm64) deb_arch=arm64 ;; \
        *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    url="https://github.com/kasmtech/KasmVNC/releases/download/v${KASMVNC_VERSION}/kasmvncserver_noble_${KASMVNC_VERSION}_${deb_arch}.deb"; \
    curl -fsSL "${url}" -o /tmp/kasmvnc.deb; \
    apt-get update; \
    apt-get install -y --no-install-recommends /tmp/kasmvnc.deb; \
    rm -f /tmp/kasmvnc.deb; \
    rm -rf /var/lib/apt/lists/*

# KasmVNC loads the snakeoil cert at startup even with SSL disabled in
# the config. Generate a self-signed pair and make the key readable by
# the non-root user. DEMO-MODE only; production terminates TLS at the
# AppAPI proxy.
RUN openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
        -keyout /etc/ssl/private/ssl-cert-snakeoil.key \
        -out /etc/ssl/certs/ssl-cert-snakeoil.pem \
        -subj '/CN=ash-nazg-local-dev' \
    && chmod 755 /etc/ssl/private \
    && chmod 644 /etc/ssl/private/ssl-cert-snakeoil.key

# Non-root user. UID/GID are fixed so volume mounts stay predictable.
# Ubuntu 24.04 ships a default `ubuntu` user at 1000; remove it first.
# The engine needs a real home: KasmVNC keeps its per-display state there.
RUN userdel -r ubuntu 2>/dev/null || true \
    && groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --create-home --shell /bin/bash app

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
# The engine entrypoint is the same script the standalone engine image
# uses; the shim runs it per session with FILE_PATH, VNC_DISPLAY and
# VNC_WEBSOCKET_PORT set.
COPY engines/dosbox-x/entrypoint.sh /usr/local/bin/ash-nazg-engine
RUN chmod +x /start.sh /usr/local/bin/ash-nazg-engine

# The sentinel that skips KasmVNC's first-run desktop-environment
# question (it prompts interactively and deadlocks without a TTY).
#
# Deliberately NO password file here. Every session gets its own, written
# into its own directory at spawn time. A file baked in at build time
# would be the same secret on every install, would survive redeployment,
# and — worse — would silently accept connections when a session's own
# file failed to appear, turning a bug into a shared password.
USER app
RUN mkdir -p /home/app/.vnc /home/app/.local/share \
    && touch /home/app/.vnc/.de-was-selected
USER root

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    APP_HOST=0.0.0.0 \
    APP_PORT=8080

USER app

# 8080: the shim (AppAPI overrides it with APP_PORT).
# 6901+: one KasmVNC websocket per in-image session, handed out by the
# spawner. Only reachable through the AppAPI proxy in a real install.
EXPOSE 8080 6901-6910

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
# tini reaps the session processes the shim spawns; start.sh then
# brings up frpc (HaRP mode) and execs uvicorn.
ENTRYPOINT ["/usr/bin/tini", "--", "/start.sh"]
CMD ["sh", "-c", "if [ -n \"$HP_SHARED_KEY\" ]; then umask 0177; exec uvicorn ash_nazg.main:app --uds /tmp/exapp.sock; else exec uvicorn ash_nazg.main:app --host 0.0.0.0 --port ${APP_PORT:-8080}; fi"]
