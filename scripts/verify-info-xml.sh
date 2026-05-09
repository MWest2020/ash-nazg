#!/usr/bin/env bash
# scripts/verify-info-xml.sh
#
# LEVEL 2 verifier — XSD + AppAPI-specific rules for appinfo/info.xml.
#
# Two phases:
#   1. canonical Nextcloud XSD validation
#      (https://apps.nextcloud.com/schema/apps/info.xsd)
#   2. AppAPI 5.x ExApp rule checks:
#        - <image-tag> present and not "latest"
#        - <image-tag> matches a permissive semver-ish pattern
#        - all required <external-app> subelements present
#        - every <scopes>/<value> entry is on the AppAPI scope allowlist
#
# Runnable locally and in CI. Exit codes:
#   0 — all checks passed
#   1 — XSD validation failed or environment problem
#   2 — AppAPI rule check failed
#
# Dependencies: bash 4+, curl, xmllint (libxml2-utils).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INFO_XML="${REPO_ROOT}/appinfo/info.xml"

XSD_URL="https://apps.nextcloud.com/schema/apps/info.xsd"
XSD_CACHE="${XSD_CACHE:-${REPO_ROOT}/.cache/info.xsd}"

# AppAPI scope allowlist. Keep sorted; bump when AppAPI documents new
# scopes upstream. The wiring change adds an automated drift check.
ALLOWED_SCOPES=(
    AI_PROVIDERS
    AUDIT_LOGS
    DAV
    FEDERATED_FILE_SHARING
    FILES
    FILES_SHARING
    FILES_VERSIONS
    NOTIFICATIONS
    OCM
    SETTINGS
    SHARING
    TALK
    TALK_BOT
    USER_INFO
    USER_STATUS
    WEATHER_STATUS
    WORKFLOW_ENGINE
)

# --- helpers ----------------------------------------------------------------
err()  { printf 'ERROR: %s\n' "$*" >&2; }
info() { printf 'INFO:  %s\n' "$*" >&2; }

xpath_string() {
    # Returns the string value of an XPath expression; empty on no match.
    xmllint --xpath "string($1)" "${INFO_XML}" 2>/dev/null || true
}

xpath_count() {
    xmllint --xpath "count($1)" "${INFO_XML}" 2>/dev/null || echo 0
}

# --- preflight --------------------------------------------------------------
if [[ ! -f "${INFO_XML}" ]]; then
    err "info.xml not found at ${INFO_XML}"
    exit 1
fi

if ! command -v xmllint >/dev/null 2>&1; then
    err "xmllint is not installed (apt: libxml2-utils)"
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    err "curl is not installed"
    exit 1
fi

info "info.xml = ${INFO_XML}"

# --- phase 1: XSD validation -----------------------------------------------
#
# Strip the AppAPI <external-app> extension element via Python stdlib
# (xml.etree — no regex on XML), then validate the remainder against
# the canonical Nextcloud XSD. This is the "maximally boring" choice:
#
#   * No grep heuristic over xmllint's error format. (The previous
#     implementation did that; it would have silently broken if
#     xmllint changed its message wording.)
#   * No self-maintained AppAPI XSD. AppAPI does not publish one;
#     fabricating one in-tree would create open-ended drift work.
#   * The <external-app> block is owned by Level-3 verification at
#     deploy time (verify-against-nextcloud.sh + the actual AppAPI
#     registration handshake).
#
# TODO (wire-dosbox-engine or integration-testing-setup): re-evaluate.
# If a stable, public AppAPI XSD becomes available upstream, validate
# the stripped block against it here. Until then, this layer
# deliberately does not pretend to cover the extension element.

mkdir -p "$(dirname "${XSD_CACHE}")"
if [[ ! -f "${XSD_CACHE}" ]]; then
    info "fetching XSD: ${XSD_URL}"
    if ! curl -fsSL "${XSD_URL}" -o "${XSD_CACHE}"; then
        err "failed to fetch ${XSD_URL}"
        exit 1
    fi
fi

if ! command -v python3 >/dev/null 2>&1; then
    err "python3 is not installed (needed to strip the AppAPI extension before XSD validation)"
    exit 1
fi

stripped="$(mktemp --suffix=.xml)"
trap 'rm -f "${stripped}"' EXIT

python3 - "${INFO_XML}" "${stripped}" <<'PY'
import sys
import xml.etree.ElementTree as ET

src, dst = sys.argv[1], sys.argv[2]
tree = ET.parse(src)
root = tree.getroot()
removed = 0
for ext in list(root.findall("external-app")):
    root.remove(ext)
    removed += 1
tree.write(dst, encoding="UTF-8", xml_declaration=True)
print(f"INFO:  stripped {removed} <external-app> block(s) before XSD validation", file=sys.stderr)
PY

if ! xmllint --noout --schema "${XSD_CACHE}" "${stripped}"; then
    err "info.xml failed XSD validation (canonical body, <external-app> already stripped)"
    err "the <external-app> extension is verified at Level-3 — see docs/testing.md"
    exit 1
fi
info "XSD validation passed (canonical body; <external-app> deferred to Level 3)"

# --- phase 2: AppAPI rules --------------------------------------------------
fail=0

# 2a. <image-tag> present and not "latest".
image_tag="$(xpath_string '/info/external-app/docker-install/image-tag')"
if [[ -z "${image_tag}" ]]; then
    err "missing <external-app>/<docker-install>/<image-tag>"
    fail=2
elif [[ "${image_tag}" == "latest" ]]; then
    err "<image-tag> is 'latest' — production builds MUST pin a version"
    fail=2
else
    info "image-tag pinned: ${image_tag}"
fi

# 2b. semver-ish pattern. Allows: 0.0.0, 1.2.3, 1.2.3-pre.1, 1.2.3+build.7,
# 1.2.3-scaffold, 1.2.3-dev. Rejects: foo, latest, 1, 1.2, etc.
if [[ -n "${image_tag}" ]] && [[ "${image_tag}" != "latest" ]]; then
    if ! [[ "${image_tag}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.+-]+)?$ ]]; then
        err "image-tag '${image_tag}' is not semver-ish (expected X.Y.Z[-prerelease][+build])"
        fail=2
    fi
fi

# 2c. required <external-app> subelements.
required_paths=(
    /info/external-app/docker-install/registry
    /info/external-app/docker-install/image
    /info/external-app/docker-install/image-tag
    /info/external-app/scopes
    /info/external-app/protocol
    /info/external-app/port
    /info/external-app/system
)
for p in "${required_paths[@]}"; do
    val="$(xpath_string "${p}")"
    if [[ -z "${val}" ]]; then
        err "missing required element: ${p}"
        fail=2
    fi
done

# 2d. each <scopes>/<value> on the allowlist.
n_scopes="$(xpath_count '/info/external-app/scopes/value')"
if [[ "${n_scopes}" == "0" ]]; then
    err "no <scopes>/<value> entries found"
    fail=2
fi

for ((i=1; i<=n_scopes; i++)); do
    scope="$(xpath_string "/info/external-app/scopes/value[${i}]")"
    found=false
    for allowed in "${ALLOWED_SCOPES[@]}"; do
        if [[ "${scope}" == "${allowed}" ]]; then
            found=true
            break
        fi
    done
    if ! ${found}; then
        err "scope '${scope}' is not on the AppAPI allowlist"
        err "  allowlist: ${ALLOWED_SCOPES[*]}"
        fail=2
    else
        info "scope OK: ${scope}"
    fi
done

if (( fail != 0 )); then
    err "verify-info-xml: AppAPI rule checks FAILED"
    exit "${fail}"
fi

info "verify-info-xml: all checks passed"
exit 0
