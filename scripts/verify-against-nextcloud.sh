#!/usr/bin/env bash
# scripts/verify-against-nextcloud.sh
#
# LEVEL 3 verifier — placeholder.
#
# When fully implemented, this script:
#   1. starts an ephemeral Nextcloud + AppAPI stack via docker compose
#      (Nextcloud >=30, HaRP deploy daemon, postgres, redis);
#   2. registers Ash Nazg as an ExApp via
#      `occ app_api:app:register ash_nazg ...`;
#   3. issues a curated set of curl checks against the host shim, the
#      admin settings endpoint, and the Files-app integration;
#   4. tears the stack down (always — even on failure).
#
# Implementation deferred to a follow-up change. Likely owner:
# `wire-dosbox-engine` once the dispatcher exists, or a dedicated
# `integration-testing-setup` change. See docs/testing.md for the
# verifier-layer rationale and the threshold at which this is
# required to pass.

set -euo pipefail

cat <<'EOF' >&2
─────────────────────────────────────────────────────────────────────
verify-against-nextcloud.sh — TODO: implement before App Store push.
─────────────────────────────────────────────────────────────────────
This is a level-3 verifier placeholder. Until it lands:

  Level 1 (per-commit):     pytest, eslint, vue-tsc, openspec validate
  Level 2 (per-PR):         scripts/verify-info-xml.sh — XSD + AppAPI
  Level 3 (per-tag/dispatch): THIS SCRIPT — ephemeral Nextcloud install

Tracked in docs/testing.md. Not yet a hard gate.
─────────────────────────────────────────────────────────────────────
EOF

# Exit 0 by design: the placeholder must NOT block PRs. The
# nextcloud-integration GitHub Actions workflow only runs on tags and
# manual dispatch, and at that point the maintainer is expected to
# have implemented the real flow.
exit 0
