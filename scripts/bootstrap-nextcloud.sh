#!/usr/bin/env bash
# scripts/bootstrap-nextcloud.sh
#
# Drives the local Nextcloud stack from "containers up" to
# "Ash Nazg ExApp registered, deployed via HaRP, reachable through
# the AppAPI proxy".
#
# Run this AFTER:
#   docker compose -f scripts/local-nextcloud-stack.yml up -d
#
# Idempotent — re-running on an already-bootstrapped stack reports
# "already done" for each step.
#
# Architecture (wire-dosbox-engine §1):
# - Deploy daemon: HaRP (docker-install). AppAPI talks to HaRP on
#   port 8780; HaRP spawns the ExApp container via the Docker
#   socket, with APP_PORT, APP_SECRET, APP_VERSION, APP_ID,
#   NEXTCLOUD_URL injected.
# - The host shim is NOT pre-started by compose. AppAPI's
#   `app:register --wait-finish` triggers the spawn.
# - There is NO oc_ex_apps.port SQL workaround. HaRP allocates the
#   port and starts the container with APP_PORT set to that value.
#
# Caveats:
# - Local-dev only.
# - HP_SHARED_KEY in the compose file must match --harp_shared_key
#   in the daemon registration. Both default to the same value
#   (`ash-nazg-local-dev-key`).

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-scripts/local-nextcloud-stack.yml}"
NC_SVC="${NC_SVC:-nextcloud}"
APP_ID="ash_nazg"
APP_VERSION="0.0.0"
DAEMON_NAME="harp"
# Compose project name is the dirname of the compose file ("scripts").
# The network as the host's container runtime sees it is therefore
# `scripts_ash-nazg-net`, not the bare `ash-nazg-net` declared in the
# yaml. AppAPI's `--net` flag needs the runtime-visible name so HaRP
# can attach the spawned ExApp to the same network as Nextcloud.
NC_NET="${NC_NET:-scripts_ash-nazg-net}"

# Match the compose default; override via env if you customise it.
HARP_SHARED_KEY="${HP_SHARED_KEY:-ash-nazg-local-dev-key}"
HARP_HOST="appapi-harp:8780"
HARP_FRP_ADDRESS="appapi-harp:8782"

log()  { printf '\033[36m::\033[0m %s\n' "$*" >&2; }
ok()   { printf '\033[32mOK\033[0m %s\n'  "$*" >&2; }
warn() { printf '\033[33m??\033[0m %s\n'  "$*" >&2; }
err()  { printf '\033[31m!!\033[0m %s\n'  "$*" >&2; }

dc()  { docker compose -f "${COMPOSE_FILE}" "$@"; }
occ() { dc exec -T -u www-data "${NC_SVC}" php /var/www/html/occ "$@"; }

# --- preflight --------------------------------------------------------------
log "checking compose stack is up …"
if ! dc exec -T "${NC_SVC}" true >/dev/null 2>&1; then
    err "service '${NC_SVC}' is not running. Did you 'docker compose up -d'?"
    exit 1
fi

log "waiting for nextcloud /status.php to return 200 …"
deadline=$(( $(date +%s) + 240 ))
while :; do
    if dc exec -T "${NC_SVC}" curl -fsS http://127.0.0.1/status.php >/dev/null 2>&1; then
        ok "nextcloud is up"
        break
    fi
    if (( $(date +%s) > deadline )); then
        err "nextcloud did not become healthy within 240 s"
        dc logs --tail 50 "${NC_SVC}" >&2
        exit 1
    fi
    sleep 3
done

log "checking HaRP /info endpoint …"
if ! dc exec -T "${NC_SVC}" curl -fsS "http://appapi-harp:8780/info" >/dev/null 2>&1; then
    warn "HaRP /info not reachable from NC yet — registration may fail"
else
    ok "HaRP reachable from NC"
fi

# --- 1. install + enable app_api -------------------------------------------
log "ensuring AppAPI is installed and enabled …"
if occ app:list 2>/dev/null | grep -qE '^\s*-\s+app_api:'; then
    ok "app_api already enabled"
else
    occ app:install app_api || true
    occ app:enable  app_api
    ok "app_api enabled"
fi

# --- 2. register the HaRP docker-install daemon ----------------------------
log "ensuring deploy daemon '${DAEMON_NAME}' is registered …"
if occ app_api:daemon:list 2>/dev/null | grep -q "${DAEMON_NAME}"; then
    ok "deploy daemon '${DAEMON_NAME}' already registered"
else
    # Args (per `app_api:daemon:register --help` example):
    #   <name> <display> <accepts-deploy-id> <protocol> <host> <nextcloud_url>
    #   --net <net> --harp --harp_frp_address <addr> --harp_shared_key <key>
    occ app_api:daemon:register \
        "${DAEMON_NAME}" \
        "Local HaRP (docker-install)" \
        docker-install \
        http \
        "${HARP_HOST}" \
        "http://${NC_SVC}" \
        --net "${NC_NET}" \
        --harp \
        --harp_frp_address "${HARP_FRP_ADDRESS}" \
        --harp_shared_key "${HARP_SHARED_KEY}" \
        --set-default
    ok "HaRP daemon registered"
fi

# --- 3. register + deploy the Ash Nazg ExApp -------------------------------
log "registering ExApp '${APP_ID}' …"
if occ app_api:app:list 2>/dev/null | grep -q "${APP_ID} "; then
    ok "ExApp '${APP_ID}' already registered"
else
    # Push the local host image to the local registry so HaRP can
    # pull it through the AppAPI deploy flow. Skip if already tagged.
    if ! docker manifest inspect 127.0.0.1:5000/ash-nazg-host:${APP_VERSION}-scaffold >/dev/null 2>&1; then
        log "pushing host image to local registry …"
        docker tag localhost/ash-nazg-host:${APP_VERSION}-scaffold \
                   127.0.0.1:5000/ash-nazg-host:${APP_VERSION}-scaffold
        docker push --tls-verify=false \
                   127.0.0.1:5000/ash-nazg-host:${APP_VERSION}-scaffold
    fi

    # Patch info.xml in-flight so <registry> + <image> point at the
    # local registry rather than ghcr.io. Image ref from the host
    # daemon's POV is `127.0.0.1:5000/ash-nazg-host:...`. From inside
    # the compose net it's `registry:5000/...` — but HaRP forwards
    # the pull to the *host's* docker daemon via FRP, so 127.0.0.1
    # is the right address.
    sed -e 's|<registry>ghcr.io</registry>|<registry>127.0.0.1:5000</registry>|' \
        -e 's|<image>mwest2020/ash-nazg-host</image>|<image>ash-nazg-host</image>|' \
        appinfo/info.xml > /tmp/info.xml.local

    tar -cf - -C /tmp info.xml.local \
        | dc exec -T "${NC_SVC}" sh -c 'cd /tmp && tar -xf - && mv info.xml.local info.xml'
    # `--wait-finish` blocks until HaRP has actually spawned the
    # container and AppAPI's heartbeat check succeeds. Without it
    # the register returns immediately and the ExApp is only
    # half-initialised.
    occ app_api:app:register "${APP_ID}" "${DAEMON_NAME}" \
        --info-xml=/tmp/info.xml --wait-finish
    ok "ExApp registered + deployed"
fi

# --- 4. enable -------------------------------------------------------------
log "enabling '${APP_ID}' …"
occ app_api:app:enable "${APP_ID}" 2>&1 | tail -3 || warn "enable returned non-zero"

# --- 5. report -------------------------------------------------------------
echo
ok "bootstrap complete"
echo
log "checks (HaRP-spawned ExApp reachable via AppAPI proxy):"

# 5a. ExApp container exists and is running.
spawned="$(docker ps --filter "name=${APP_ID}" --format '{{.Names}} {{.Status}}' | head -1)"
if [[ -n "${spawned}" ]]; then
    ok "  ExApp container: ${spawned}"
else
    warn "  no ExApp container found — HaRP may not have spawned it"
fi

# 5b. AppAPI proxy URL — the assertion that retires the "404 by
# design" caveat. With routes registered via the handshake, the
# proxy returns the canonical /health body.
proxy_url="http://localhost:8088/index.php/apps/app_api/proxy/${APP_ID}/health"
status="$(curl -sS -o /dev/null -w '%{http_code}' -u admin:admin-local-dev "${proxy_url}" || true)"
if [[ "${status}" == "200" ]]; then
    ok "  AppAPI proxy /health → 200 (route registration WORKED)"
else
    warn "  AppAPI proxy /health → ${status} (route registration NOT yet wired — host shim still on scaffold register stub)"
fi

cat <<EOF

─────────────────────────────────────────────────────────────────
What works (wire-dosbox-engine §1 foundation):
  - http://localhost:8088              (admin / admin-local-dev)
  - http://localhost:8088/index.php/settings/admin/${APP_ID}
  - HaRP daemon: docker exec scripts_appapi-harp_1 wget -qO- http://localhost:8780/info
  - Spawned ExApp: docker ps | grep ${APP_ID}

What needs §6 (handshake) before it works:
  - http://localhost:8088/index.php/apps/app_api/proxy/${APP_ID}/health
  AppAPI's proxy is gated by route registration, which the host
  shim's appapi.register() owns. While that's still
  NotImplementedError this URL returns 404. Wiring §6 makes it 200.
─────────────────────────────────────────────────────────────────
EOF
