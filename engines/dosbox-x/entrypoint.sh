#!/usr/bin/env bash
#
# Ash Nazg DOSBox-X engine container — SCAFFOLD entrypoint.
#
# Intentional no-op. The wiring change `wire-dosbox-engine` replaces
# this with the real launch sequence:
#
#   1. mount /mnt/files via davfs2 using NEXTCLOUD_URL + APP_TOKEN;
#   2. spawn KasmVNC on port 6901;
#   3. exec dosbox-x with the file resolved under /mnt/files.

set -euo pipefail

echo "ash-nazg dosbox-x engine container — wiring TBD"
echo "Replace this entrypoint via change: wire-dosbox-engine"
exit 0
