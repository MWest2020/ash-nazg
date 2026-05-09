#!/usr/bin/env bash
# scripts/bootstrap-nextcloud.sh
#
# Drives the local Nextcloud stack from "containers up" to
# "Ash Nazg ExApp registered, enabled, reachable from NC over the
# compose network".
#
# Run this AFTER:
#   docker compose -f scripts/local-nextcloud-stack.yml up -d
#
# Idempotent — re-running on an already-bootstrapped stack reports
# "already done" for each step.
#
# Caveats:
# - Local-dev only.
# - HaRP is NOT used; deploy daemon type is `manual_install`.
# - The AppAPI proxy at /index.php/apps/app_api/proxy/ash_nazg/...
#   will return 404 until the wiring change implements the AppAPI
#   registration handshake (which is what populates oc_ex_apps_routes).
#   Until then, verify by hitting the host shim directly from inside
#   the NC container — that's the cross-container reachability check.

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-scripts/local-nextcloud-stack.yml}"
NC_SVC="${NC_SVC:-nextcloud}"
APP_ID="ash_nazg"
APP_HOST_NAME="ash-nazg-host"
APP_PORT="8080"
DAEMON_NAME="manual"
NC_NET="ash-nazg-net"

log()  { printf '\033[36m::\033[0m %s\n' "$*" >&2; }
ok()   { printf '\033[32mOK\033[0m %s\n'  "$*" >&2; }
warn() { printf '\033[33m??\033[0m %s\n'  "$*" >&2; }
err()  { printf '\033[31m!!\033[0m %s\n'  "$*" >&2; }

dc()  { docker compose -f "${COMPOSE_FILE}" "$@"; }
occ() { dc exec -T -u www-data "${NC_SVC}" php /var/www/html/occ "$@"; }

# --- preflight --------------------------------------------------------------
log "checking compose stack is up …"
# podman-compose's `ps` flags differ from Docker-Compose v2; probe by
# executing `true` instead.
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

# --- 1. install + enable app_api -------------------------------------------
log "ensuring AppAPI is installed and enabled …"
if occ app:list 2>/dev/null | grep -qE '^\s*-\s+app_api:'; then
    ok "app_api already enabled"
else
    occ app:install app_api || true
    occ app:enable  app_api
    ok "app_api enabled"
fi

# --- 2. register the manual-install deploy daemon --------------------------
log "ensuring deploy daemon '${DAEMON_NAME}' is registered …"
if occ app_api:daemon:list 2>/dev/null | grep -q "\"name\": \"${DAEMON_NAME}\""; then
    ok "deploy daemon '${DAEMON_NAME}' already registered"
else
    # Args (per `app_api:daemon:register --help`):
    #   <name> <display> <accepts-deploy-id> <protocol> <host> <nextcloud_url>
    # `host` is where AppAPI sends proxy traffic. For manual-install
    # in our compose stack, that's the ash-nazg-host service's DNS name.
    occ app_api:daemon:register \
        "${DAEMON_NAME}" \
        "Local manual-install daemon" \
        manual-install \
        http \
        "${APP_HOST_NAME}" \
        "http://${NC_SVC}" \
        --net "${NC_NET}"
    ok "deploy daemon registered"
fi

# --- 3. register the Ash Nazg ExApp ---------------------------------------
log "registering ExApp '${APP_ID}' …"
if occ app_api:app:list 2>/dev/null | grep -q "${APP_ID} "; then
    ok "ExApp '${APP_ID}' already registered"
else
    # `--info-xml` wants a real file path inside the NC container,
    # not stdin. Copy first, then point at /tmp/info.xml.
    docker cp appinfo/info.xml "$(dc ps -q "${NC_SVC}")":/tmp/info.xml
    occ app_api:app:register "${APP_ID}" "${DAEMON_NAME}" \
        --info-xml=/tmp/info.xml
    ok "ExApp registered"
fi

# --- 4. correct the auto-assigned port ------------------------------------
# AppAPI's manual-install path auto-assigns a port (~23000) on
# register; for our scaffold the host shim listens on 8080 inside the
# compose network. Force it via direct DB update — there's no
# `app_api:app:update --port` command in 4.0.6. The wire-dosbox-engine
# change handles this properly through the registration handshake.
log "patching exapp port → 8080 (scaffold workaround for AppAPI 4.x manual-install) …"
dc exec -T "${NC_SVC}" php -r "
\$pdo = new PDO('pgsql:host=postgres;dbname=nextcloud', 'nextcloud', 'nextcloud-local-dev');
\$stmt = \$pdo->prepare('UPDATE oc_ex_apps SET port = 8080, enabled = 1 WHERE appid = ?');
\$stmt->execute(['${APP_ID}']);
echo 'rows updated: ', \$stmt->rowCount(), \"\\n\";
" || warn "DB patch returned non-zero (may already be at 8080)"

# --- 5. report ------------------------------------------------------------
echo
ok "bootstrap complete"
echo
log "level-3 reachability (NC → host shim, compose network):"
if dc exec -T "${NC_SVC}" curl -fsS "http://${APP_HOST_NAME}:${APP_PORT}/health" >/dev/null 2>&1; then
    ok "  GET http://${APP_HOST_NAME}:${APP_PORT}/health → 200 (host shim reachable from NC)"
else
    err "  GET http://${APP_HOST_NAME}:${APP_PORT}/health failed — host shim not reachable"
    exit 1
fi

cat <<EOF

─────────────────────────────────────────────────────────────────
What works (scaffold scope):
  - http://localhost:8088              (admin / admin-local-dev)
  - http://localhost:8088/index.php/settings/admin/${APP_ID}  (admin page)
  - dc exec ${NC_SVC} curl http://${APP_HOST_NAME}:8080/health
  - dc exec ${NC_SVC} curl http://${APP_HOST_NAME}:8080/admin/settings
  - dc exec ${NC_SVC} curl http://${APP_HOST_NAME}:8080/selftest

What deliberately returns 404 (scope of \`wire-dosbox-engine\`):
  - http://localhost:8088/index.php/apps/app_api/proxy/${APP_ID}/health
  AppAPI's proxy is gated by route registration, which happens
  during the AppAPI handshake — currently NotImplementedError.
─────────────────────────────────────────────────────────────────
EOF
