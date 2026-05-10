# syntax=docker/dockerfile:1.7
#
# Ash Nazg DOSBox-X engine container — SCAFFOLD.
#
# This image installs DOSBox-X + KasmVNC + davfs2 + tini, but the
# entrypoint is intentionally a no-op stub. The real wiring lands in
# change `wire-dosbox-engine`, which replaces the entrypoint with the
# WebDAV mount + KasmVNC + dosbox-x launch sequence.
#
# Base: ubuntu:24.04 (Noble). Rationale:
#   - `dosbox-x` is packaged in Ubuntu's `universe` repo (NOT in
#     Debian — only the older `dosbox` is in Debian repos). Building
#     dosbox-x from source would add ~200 MB of build-deps and a few
#     minutes per build; the Ubuntu package is the boring choice.
#   - KasmVNC ships matching `noble` .deb assets in v1.4.0+, so the
#     base-OS / KasmVNC pinning stay coherent.
#
# Multi-arch: amd64 + arm64 via docker buildx (CI).

FROM ubuntu:24.04 AS runtime

ARG TARGETARCH
# KASMVNC_VERSION must match an upstream GitHub release tag of
# https://github.com/kasmtech/KasmVNC. The .deb URL pattern below is
# sensitive to release naming changes — verify the asset names exist
# at /releases/download/v${KASMVNC_VERSION}/ before bumping.
#
# Verified 2026-05-09: v1.4.0 ships kasmvncserver_noble_1.4.0_{amd64,arm64}.deb.
ARG KASMVNC_VERSION=1.4.0

ENV DEBIAN_FRONTEND=noninteractive

# --- Ubuntu-packaged components ---------------------------------------------
# Ubuntu 24.04 has main + universe enabled by default in the standard
# image, so no source-list editing is needed. `dosbox-x` lives in
# `universe/otherosfs`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        davfs2 \
        dosbox-x \
        tini \
    && rm -rf /var/lib/apt/lists/*

# --- KasmVNC --------------------------------------------------------------
# Not in Debian repos; install the pinned .deb from upstream GitHub
# releases.
#
# SCAFFOLD CAVEAT: the URL pattern is verified against KasmVNC 1.4.0
# (assets confirmed 2026-05-09). A future release may change the
# asset filename. The wire-dosbox-engine change owns hardening this
# (sha256 pinning, signature verification, mirroring to a controlled
# artifact store).
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

# --- Non-root user ---------------------------------------------------------
# Ubuntu 24.04 ships a default `ubuntu` user at uid/gid 1000; remove
# it so we can keep the engine container's user-id aligned with the
# host container's `app:1000` for review-friendliness. davfs2 needs
# supplementary group membership to mount as a regular user.
RUN userdel -r ubuntu 2>/dev/null || true \
    && groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --create-home --shell /bin/bash app \
    && usermod -aG davfs2 app

# --- Entrypoint ------------------------------------------------------------
COPY entrypoint.sh /usr/local/bin/ash-nazg-entrypoint
RUN chmod +x /usr/local/bin/ash-nazg-entrypoint

# Pre-create a KasmVNC password file at the path the default
# kasmvnc.yaml expects (~/.kasmpasswd). Without this the
# kasmvncserver first-run wizard prompts interactively for user
# creation, which deadlocks under docker run.
USER app
RUN mkdir -p /home/app/.vnc /home/app/.local/share \
    && printf 'ash_nazg\nash_nazg\n\n' \
        | kasmvncpasswd -u demo -wo /home/app/.kasmpasswd \
    && touch /home/app/.vnc/.de-was-selected
USER root

# KasmVNC requires a TLS key/cert even when SSL is disabled in the
# config (it tries to load the snakeoil cert at startup). Generate
# a self-signed pair, then make /etc/ssl/private readable so the
# non-root `app` user can load the key. DEMO-MODE only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
        -keyout /etc/ssl/private/ssl-cert-snakeoil.key \
        -out /etc/ssl/certs/ssl-cert-snakeoil.pem \
        -subj '/CN=ash-nazg-local-dev' \
    && chmod 755 /etc/ssl/private \
    && chmod 644 /etc/ssl/private/ssl-cert-snakeoil.key \
    && rm -rf /var/lib/apt/lists/*

# Mount point the host expects (per engines spec; see SessionConfig.mount_path).
RUN mkdir -p /mnt/files && chown app:app /mnt/files

# KasmVNC websocket. Host maps this in SessionConfig.streaming_port.
EXPOSE 6901

USER app
WORKDIR /home/app

# tini reaps zombies; the host kills the container with SIGTERM on
# idle/timeout per design.md.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/ash-nazg-entrypoint"]
