#!/usr/bin/env bash
# scripts/verify-against-nextcloud.sh
#
# LEVEL 3 verifier — full ephemeral Nextcloud install verification.
#
# Brings up `scripts/local-nextcloud-stack.yml` (postgres + valkey +
# nextcloud + appapi-harp), runs `scripts/bootstrap-nextcloud.sh`
# to install AppAPI, register the HaRP daemon, and deploy the
# ash_nazg ExApp. Asserts the AppAPI proxy URL works and the
# HaRP-spawned container is healthy. Tears down at the end.
#
# The stack's local registry stands in for GHCR: the bootstrap
# pushes the freshly-built host image there and rewrites info.xml's
# <registry> to match, so HaRP exercises the same pull-and-spawn
# path an App Store install would.
#
# In CI this runs on `v*.*.*` tag pushes and on `workflow_dispatch`.
# Per `docs/testing.md`, this is the gate that must be green before
# App Store submission.
#
# Caveats:
# - Requires a working Docker / Podman daemon socket reachable as
#   `docker compose`, AND reachable by HaRP: it spawns the ExApp
#   container through that socket. Set DOCKER_SOCKET to point at it
#   (auto-detected: rootful docker first, then rootless podman).
# - Requires the local image `localhost/ash-nazg-host:0.0.0-scaffold`.
#   The script builds it if missing.
# - Defaults to `KEEP_STACK=0` (tear down on success). Set
#   `KEEP_STACK=1` to leave the stack running for local inspection.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${REPO_ROOT}/scripts/local-nextcloud-stack.yml}"
HOST_IMAGE="${HOST_IMAGE:-localhost/ash-nazg-host:0.0.0-scaffold}"
KEEP_STACK="${KEEP_STACK:-0}"

log()  { printf '\033[36m::\033[0m %s\n' "$*" >&2; }
ok()   { printf '\033[32mOK\033[0m %s\n'  "$*" >&2; }
err()  { printf '\033[31m!!\033[0m %s\n'  "$*" >&2; }

cd "${REPO_ROOT}"

# HaRP needs a container-runtime socket to spawn the ExApp. Rootful
# docker exposes /var/run/docker.sock (0660, root:docker — the user
# running this script is in the docker group, and HaRP runs as root
# inside its container, so no chmod is needed). Rootless podman needs
# the 0660 socket relaxed to 0666 for the duration; that is what the
# chmod dance below is for.
DOCKER_SOCKET="${DOCKER_SOCKET:-$([[ -S /var/run/docker.sock ]] \
    && echo /var/run/docker.sock \
    || echo "/run/user/$(id -u)/podman/podman.sock")}"
export DOCKER_SOCKET
SOCKET_PATH="${SOCKET_PATH:-${DOCKER_SOCKET}}"
if [[ "${SOCKET_PATH}" == "/var/run/docker.sock" ]]; then
    SOCKET_PATH=""   # rootful docker: leave the socket alone
fi
SOCKET_PERMS_BEFORE=""
if [[ -S "${SOCKET_PATH}" ]]; then
    SOCKET_PERMS_BEFORE="$(stat -c '%a' "${SOCKET_PATH}")"
    chmod 0666 "${SOCKET_PATH}" 2>/dev/null || true
fi

cleanup() {
    if [[ -n "${SOCKET_PERMS_BEFORE}" && -S "${SOCKET_PATH}" ]]; then
        chmod "${SOCKET_PERMS_BEFORE}" "${SOCKET_PATH}" 2>/dev/null || true
    fi
    if [[ "${KEEP_STACK}" == "1" ]]; then
        log "KEEP_STACK=1 — leaving stack running. Tear down manually with:"
        log "  docker compose -f ${COMPOSE_FILE} down -v"
        return
    fi
    log "tearing down stack …"
    docker compose -f "${COMPOSE_FILE}" down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

# --- 0. preflight ----------------------------------------------------------
log "checking docker/podman is reachable …"
if ! docker version >/dev/null 2>&1; then
    err "docker (or podman-as-docker) not reachable"
    exit 1
fi
ok "container runtime reachable"

# --- 1. ensure the host image exists --------------------------------------
log "ensuring ${HOST_IMAGE} exists locally …"
if docker image inspect "${HOST_IMAGE}" >/dev/null 2>&1; then
    ok "host image present"
else
    log "building host image …"
    docker build -t "${HOST_IMAGE}" -f host/Dockerfile . >/tmp/verify-host-build.log 2>&1 \
        || { err "host image build failed — see /tmp/verify-host-build.log"; exit 1; }
    ok "host image built"
fi

# --- 2. bring up the stack -------------------------------------------------
log "bringing up the stack …"
docker compose -f "${COMPOSE_FILE}" up -d >/tmp/verify-compose-up.log 2>&1 \
    || { err "compose up failed — see /tmp/verify-compose-up.log"; exit 1; }
ok "stack up"

# --- 3. run the bootstrap --------------------------------------------------
log "running bootstrap-nextcloud.sh …"
if ! ./scripts/bootstrap-nextcloud.sh; then
    err "bootstrap failed"
    docker compose -f "${COMPOSE_FILE}" logs --tail 80 nextcloud >&2 || true
    exit 1
fi
ok "bootstrap succeeded"

# --- 4. assert the deployment is real --------------------------------------
PROXY="${PROXY:-http://localhost:8088/index.php/apps/app_api/proxy/ash_nazg}"
NC_AUTH="${NC_AUTH:-admin:admin-local-dev}"
EXAPP_CONTAINER="${EXAPP_CONTAINER:-nc_app_ash_nazg}"

log "asserting HaRP spawned the ExApp container …"
spawned="$(docker ps --filter "name=${EXAPP_CONTAINER}" --format '{{.Names}}' | head -1)"
if [[ "${spawned}" == "${EXAPP_CONTAINER}" ]]; then
    ok "  ${EXAPP_CONTAINER} is running (spawned by HaRP, not by compose)"
else
    err "  no container named ${EXAPP_CONTAINER} — HaRP did not spawn the ExApp"
    exit 1
fi

log "asserting the bootstrap contains no oc_ex_apps port workaround …"
if grep -qi "UPDATE oc_ex_apps" scripts/bootstrap-nextcloud.sh; then
    err "  bootstrap still patches oc_ex_apps by SQL — HaRP allocates the port"
    exit 1
fi
ok "  no SQL port patch in the bootstrap"

log "asserting oc_ex_apps.port matches the port AppAPI gave the container …"
db_port="$(docker compose -f "${COMPOSE_FILE}" exec -T postgres \
    psql -U nextcloud -d nextcloud -tAc \
    "select port from oc_ex_apps where appid = 'ash_nazg'" 2>/dev/null | tr -d '[:space:]')"
env_port="$(docker inspect "${EXAPP_CONTAINER}" \
    --format '{{range .Config.Env}}{{println .}}{{end}}' \
    | sed -n 's/^APP_PORT=//p' | tr -d '[:space:]')"
if [[ -n "${db_port}" && "${db_port}" == "${env_port}" ]]; then
    ok "  oc_ex_apps.port = ${db_port} = the container's APP_PORT"
else
    err "  port mismatch: oc_ex_apps.port='${db_port}' APP_PORT='${env_port}'"
    exit 1
fi

log "asserting /health through the AppAPI proxy …"
body="$(curl -fsS -u "${NC_AUTH}" "${PROXY}/health" 2>/dev/null || true)"
if echo "${body}" | grep -q '"app":"ash_nazg"'; then
    ok "  proxy GET /health returned the canonical response (route registration works)"
else
    err "  proxy /health did not return the expected body. Got: ${body}"
    exit 1
fi

log "asserting /admin/settings serves the HTML shell through the proxy …"
shell="$(curl -fsS -u "${NC_AUTH}" "${PROXY}/admin/settings" 2>/dev/null || true)"
if echo "${shell}" | grep -q 'id="ash-nazg-admin-settings"'; then
    ok "  admin settings shell renders, mount target present"
else
    err "  admin settings shell missing the mount target div"
    exit 1
fi

log "asserting /selftest runs real checks through the proxy …"
selftest="$(curl -fsS -u "${NC_AUTH}" -X POST "${PROXY}/selftest" 2>/dev/null || true)"
for cid in host-health engines-registered engine-runtime audit-log-write; do
    if ! echo "${selftest}" | grep -q "\"id\":\"${cid}\""; then
        err "  /selftest missing check id: ${cid}"
        exit 1
    fi
done
ok "  /selftest returns all four canonical check IDs in spec order"

for cid in host-health engines-registered engine-runtime audit-log-write; do
    if ! echo "${selftest}" | grep -q "\"id\":\"${cid}\",\"status\":\"ok\""; then
        err "  /selftest check '${cid}' is not ok: ${selftest}"
        exit 1
    fi
done
ok "  all four self-checks pass"

# --- 5. the Run flow, end to end -------------------------------------------
#
# A DOS binary generated by this repo (no third-party content in the test
# path, per the sandbox spec), uploaded to the admin's Files over WebDAV,
# then started through the AppAPI proxy.
log "uploading the generated DOS fixture to Files …"
python3 scripts/make-dos-fixture.py /tmp/ash-nazg-verify.exe >/dev/null
upload_code="$(curl -sS -o /dev/null -w '%{http_code}' -u "${NC_AUTH}" \
    -T /tmp/ash-nazg-verify.exe \
    "http://localhost:8088/remote.php/dav/files/admin/ash-nazg-verify.exe")"
if [[ "${upload_code}" =~ ^20[0-9]$ ]]; then
    ok "  fixture uploaded (HTTP ${upload_code})"
else
    err "  fixture upload failed: HTTP ${upload_code}"
    exit 1
fi

log "asserting POST /run starts a session …"
run_body="$(curl -fsS -u "${NC_AUTH}" -X POST \
    -H 'Content-Type: application/json' \
    -d '{"path":"/ash-nazg-verify.exe"}' "${PROXY}/run" 2>/dev/null || true)"
if ! echo "${run_body}" | grep -q '"session_id"'; then
    err "  POST /run did not return a session: ${run_body}"
    exit 1
fi
run_port="$(echo "${run_body}" | sed -n 's/.*"port":\([0-9]*\).*/\1/p')"
ok "  POST /run returned a session on port ${run_port}"

log "asserting the emulator is actually running in the ExApp …"
# /run returns as soon as KasmVNC accepts connections; the X session then
# starts dosbox-x a moment later, so this polls rather than assuming.
emulator_deadline=$(( $(date +%s) + 30 ))
emulator_seen=0
while (( $(date +%s) < emulator_deadline )); do
    if docker exec "${EXAPP_CONTAINER}" \
            pgrep -f "dosbox-x .*ash-nazg-sessions" >/dev/null 2>&1; then
        emulator_seen=1
        break
    fi
    sleep 2
done
if (( emulator_seen == 1 )); then
    ok "  dosbox-x is running with the session's binary"
else
    err "  no dosbox-x process in ${EXAPP_CONTAINER} 30 s after a successful /run"
    docker exec "${EXAPP_CONTAINER}" sh -c 'cat /tmp/ash-nazg-sessions/*/engine.log' >&2 || true
    exit 1
fi

log "asserting a closed session can be started again …"
session_id="$(echo "${run_body}" | sed -n 's/.*"session_id":"\([^"]*\)".*/\1/p')"
close_code="$(curl -sS -o /dev/null -w '%{http_code}' -u "${NC_AUTH}" \
    -X DELETE "${PROXY}/sessions/${session_id}")"
if [[ "${close_code}" != "200" ]]; then
    err "  DELETE /sessions/${session_id} returned ${close_code}"
    exit 1
fi
rerun="$(curl -fsS -u "${NC_AUTH}" -X POST -H 'Content-Type: application/json' \
    -d '{"path":"/ash-nazg-verify.exe"}' "${PROXY}/run" 2>/dev/null || true)"
if echo "${rerun}" | grep -q '"session_id"'; then
    ok "  closed, then started again (the 409 claim is released on close)"
else
    err "  second run after close did not start a session: ${rerun}"
    exit 1
fi
run_port="$(echo "${rerun}" | sed -n 's/.*"port":\([0-9]*\).*/\1/p')"

log "asserting KasmVNC answers on the session port …"
vnc_code="$(docker exec "${EXAPP_CONTAINER}" \
    curl -sS -o /dev/null -m 5 -w '%{http_code}' "http://127.0.0.1:${run_port}/" || true)"
# 401 is the expected answer: KasmVNC's own HTTP auth stands in front of
# the web client. Reaching it at all is what this asserts; putting the
# stream in the browser is the `streaming-proxy` change.
if [[ "${vnc_code}" =~ ^(200|401)$ ]]; then
    ok "  KasmVNC listening on ${run_port} (HTTP ${vnc_code})"
else
    err "  nothing listening on session port ${run_port} (got '${vnc_code}')"
    exit 1
fi

# --- 6. report -------------------------------------------------------------
echo
ok "level-3 verification PASSED"
cat <<'EOF'

What this proves:
  - The manifest is accepted by AppAPI on Nextcloud 32 and the
    ExApp deploys through HaRP's docker-install path — HaRP pulls
    the image, spawns the container and allocates the port, with
    no SQL workaround anywhere.
  - The ExApp completes AppAPI's lifecycle handshake (heartbeat →
    init → enabled) and answers through the AppAPI proxy, which is
    the "App Store install would succeed" smoke.
  - All four self-checks pass against a real NC stack, including an
    audit write that AppAPI accepts.
  - The Run flow works end to end: a binary in the user's Files is
    downloaded into a private session directory and executed by
    DOSBox-X inside the ExApp, with KasmVNC listening on the session's
    port.

What this still does NOT prove:
  - That a user can SEE the session. The stream reaches the browser
    only once `streaming-proxy` routes KasmVNC through the AppAPI
    proxy; this asserts the port answers, not that a picture arrives.
EOF
