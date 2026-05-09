# syntax=docker/dockerfile:1.7
#
# Ash Nazg DOSBox-X engine container — SCAFFOLD.
#
# This image installs DOSBox-X + KasmVNC + davfs2 + tini, but the
# entrypoint is intentionally a no-op stub. The real wiring lands in
# change `wire-dosbox-engine`, which replaces the entrypoint with the
# WebDAV mount + KasmVNC + dosbox-x launch sequence.
#
# Multi-arch: amd64 + arm64 via docker buildx (CI).

FROM debian:12-slim AS runtime

ARG TARGETARCH
# KASMVNC_VERSION must match an upstream GitHub release tag of
# https://github.com/kasmtech/KasmVNC. The .deb URL pattern below is
# sensitive to release naming changes — verify the asset names exist
# at /releases/download/v${KASMVNC_VERSION}/ before bumping.
#
# Verified 2026-05-08: v1.4.0 is the latest release and ships both
# kasmvncserver_bookworm_1.4.0_amd64.deb and ..._arm64.deb.
ARG KASMVNC_VERSION=1.4.0

ENV DEBIAN_FRONTEND=noninteractive

# --- Debian-packaged components ---------------------------------------------
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
# (assets confirmed 2026-05-08). A future release may change the
# asset filename. The wire-dosbox-engine change owns hardening this
# (sha256 pinning, signature verification, mirroring to a controlled
# artifact store).
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
        amd64) deb_arch=amd64 ;; \
        arm64) deb_arch=arm64 ;; \
        *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    url="https://github.com/kasmtech/KasmVNC/releases/download/v${KASMVNC_VERSION}/kasmvncserver_bookworm_${KASMVNC_VERSION}_${deb_arch}.deb"; \
    curl -fsSL "${url}" -o /tmp/kasmvnc.deb; \
    apt-get update; \
    apt-get install -y --no-install-recommends /tmp/kasmvnc.deb; \
    rm -f /tmp/kasmvnc.deb; \
    rm -rf /var/lib/apt/lists/*

# --- Non-root user ---------------------------------------------------------
# davfs2 needs supplementary group membership to mount as a regular user.
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --create-home --shell /bin/bash app \
    && usermod -aG davfs2 app

# --- Entrypoint ------------------------------------------------------------
COPY entrypoint.sh /usr/local/bin/ash-nazg-entrypoint
RUN chmod +x /usr/local/bin/ash-nazg-entrypoint

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
