#!/usr/bin/env bash
#
# diagnose-proxy-auth.sh — pinpoint the AppAPI proxy URL 404.
#
# The wire-dosbox-engine work landed a Caddy reverse-proxy in front of
# Nextcloud that correctly forwards /exapps/* to HaRP. The remaining
# 404 on `/index.php/apps/app_api/proxy/ash_nazg/health` is downstream
# of Caddy — most likely an auth flavour mismatch.
#
# This script runs the same request with three auth approaches and
# reports which one (if any) reaches the ExApp. Run it after the
# full stack is up (`docker compose -f scripts/local-nextcloud-stack.yml up -d`
# and `./scripts/bootstrap-nextcloud.sh`).
#
# Usage:
#   ./scripts/diagnose-proxy-auth.sh [BASE_URL] [ADMIN_USER] [ADMIN_PASS]
# Defaults:
#   BASE_URL=http://localhost:8088, ADMIN_USER=admin, ADMIN_PASS=admin-local-dev

set -euo pipefail

BASE_URL="${1:-http://localhost:8088}"
ADMIN_USER="${2:-admin}"
ADMIN_PASS="${3:-admin-local-dev}"
APP_ID="ash_nazg"
PROXY_PATH="/index.php/apps/app_api/proxy/${APP_ID}/health"
OCS_PATH="/ocs/v2.php/cloud/users/${ADMIN_USER}"

PROXY_URL="${BASE_URL}${PROXY_PATH}"
OCS_URL="${BASE_URL}${OCS_PATH}"

echo "=== Target: ${PROXY_URL}"
echo

# --- Baseline 1: OCS endpoint with basic auth (sanity check) ---------------
echo "--- TEST 1/4: OCS endpoint with basic auth"
echo "    URL: ${OCS_URL}"
echo "    Auth: -u ${ADMIN_USER}:<pass>  + OCS-APIREQUEST: true"
status=$(curl -sk -o /tmp/diagnose-1.body -w '%{http_code}' \
    -u "${ADMIN_USER}:${ADMIN_PASS}" \
    -H "OCS-APIREQUEST: true" \
    "${OCS_URL}")
echo "    Result: HTTP ${status}"
echo "    Body (first 200 chars): $(head -c 200 /tmp/diagnose-1.body)"
echo

# --- Test 2: Proxy with basic auth + OCS-APIREQUEST -----------------------
echo "--- TEST 2/4: Proxy URL with basic auth"
echo "    Hypothesis: NC creates a transient session from basic auth"
status=$(curl -sk -o /tmp/diagnose-2.body -w '%{http_code}' \
    -u "${ADMIN_USER}:${ADMIN_PASS}" \
    -H "OCS-APIREQUEST: true" \
    "${PROXY_URL}")
echo "    Result: HTTP ${status}"
if echo "$(head -c 800 /tmp/diagnose-2.body)" | grep -q "body-login"; then
    echo "    >> Response is NC login page (basic auth didn't create session)"
fi
echo "    Body (first 200 chars): $(head -c 200 /tmp/diagnose-2.body)"
echo

# --- Test 3: Proxy with session cookie ------------------------------------
echo "--- TEST 3/4: Proxy URL with logged-in session cookie"
echo "    Step 1: log in to obtain cookie jar"
cookiejar="$(mktemp)"
# Get the login page to grab the requesttoken
login_html=$(curl -sk -c "${cookiejar}" -b "${cookiejar}" \
    "${BASE_URL}/index.php/login")
rt=$(echo "${login_html}" \
    | grep -oE 'data-requesttoken="[^"]+"' \
    | head -1 \
    | sed 's/data-requesttoken="\(.*\)"/\1/')
if [ -z "${rt:-}" ]; then
    echo "    !! Could not extract requesttoken from /index.php/login"
    echo "    !! (might mean Caddy isn't forwarding correctly — check Caddyfile)"
else
    echo "    requesttoken acquired: ${rt:0:20}..."
    curl -sk -c "${cookiejar}" -b "${cookiejar}" -o /dev/null \
        -d "user=${ADMIN_USER}" -d "password=${ADMIN_PASS}" -d "requesttoken=${rt}" \
        "${BASE_URL}/index.php/login"
    echo "    Step 2: hit proxy URL with session cookie"
    status=$(curl -sk -b "${cookiejar}" -o /tmp/diagnose-3.body -w '%{http_code}' \
        "${PROXY_URL}")
    echo "    Result: HTTP ${status}"
    echo "    Body (first 200 chars): $(head -c 200 /tmp/diagnose-3.body)"
fi
rm -f "${cookiejar}"
echo

# --- Test 4: Proxy with app-password basic auth ---------------------------
echo "--- TEST 4/4: Proxy URL with app-password (if available)"
echo "    Generate an app-password for ${ADMIN_USER} via web UI, then re-run with that"
echo "    as ADMIN_PASS to test. NC requires app-password (not user-password) for"
echo "    basic-auth access to non-OCS controller URLs on stricter setups."
echo
echo "=== Summary"
echo "The expected working path: TEST 3 (session cookie). Browser-based access from"
echo "an admin's logged-in NC session is the canonical channel for the AppAPI proxy."
echo "If TEST 3 also returns the login page, Caddy is likely consuming/dropping the"
echo "cookie — inspect with 'docker logs ash-nazg_caddy_1' after the request."
