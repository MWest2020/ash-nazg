#!/usr/bin/env bash
#
# Ash Nazg DOSBox-X engine container — entrypoint.
#
# Starts KasmVNC on display :1 (port 6901) with DOSBox-X as the
# session command. For now there's NO WebDAV mount yet — the
# DOSBox-X prompt is what comes up. If a `FILE_PATH` env var is
# set and the file exists, DOSBox-X is launched with that file as
# its initial autoexec. Future iterations add the davfs2 mount
# under /mnt/files.

set -euo pipefail

: "${VNC_DISPLAY:=:1}"
: "${VNC_GEOMETRY:=1280x800}"
: "${VNC_DEPTH:=24}"
mkdir -p "${HOME}/.vnc"
chmod 700 "${HOME}/.vnc"

# Demo-mode KasmVNC config: no auth, accept connections on 0.0.0.0,
# enable the web client (vnc.html). The production wiring change
# will replace this with per-session credentials issued by the host
# shim and routed through AppAPI's HaRP proxy — but for the visible
# demo the simplest viable surface is "open port, no password".
cat > "${HOME}/.vnc/kasmvnc.yaml" <<'YAML'
network:
  protocol: http
  interface: 0.0.0.0
  ssl:
    require_ssl: false
desktop:
  resolution:
    width: 1280
    height: 800
  allow_resize: true
  pixel_depth: 24
YAML

# xstartup: what gets exec'd inside the X session. DOSBox-X is the
# whole UI — when it exits the session ends.
cat > "${HOME}/.vnc/xstartup" <<'XSTARTUP'
#!/bin/sh
# Disable the screensaver and other X niceties; we only want dosbox.
xsetroot -solid black 2>/dev/null || true

# If FILE_PATH is set and exists, hand it to dosbox-x. Otherwise
# launch the bare DOSBox-X prompt — useful for verifying the
# engine boots correctly.
if [ -n "${FILE_PATH:-}" ] && [ -f "${FILE_PATH}" ]; then
    exec dosbox-x "${FILE_PATH}"
else
    exec dosbox-x
fi
XSTARTUP
chmod 755 "${HOME}/.vnc/xstartup"

# Skip KasmVNC's interactive desktop-environment prompt — it looks
# for this sentinel file. Without it the first-run wizard runs
# `select-de.sh` interactively, which fails without a TTY.
touch "${HOME}/.vnc/.de-was-selected"

# Also create the user file the new-user prompt would create.
# Empty content + the sentinel below skips both prompts.
touch "${HOME}/.vnc/.kasmpasswd-was-selected" || true

echo "ash-nazg dosbox-x engine: starting KasmVNC on ${VNC_DISPLAY} (geometry ${VNC_GEOMETRY})"
echo "ash-nazg dosbox-x engine: FILE_PATH=${FILE_PATH:-<unset>}"

# Both interactive prompts are skipped at build time:
#   - DE-prompt: ~/.vnc/.de-was-selected sentinel
#   - User-prompt: ~/.kasmpasswd pre-created with a `demo` user
# `-SecurityTypes None` disables VNC auth — DEMO MODE only;
# production will replace this with per-session tokens through
# AppAPI/HaRP.
exec kasmvncserver "${VNC_DISPLAY}" \
    -geometry "${VNC_GEOMETRY}" \
    -depth "${VNC_DEPTH}" \
    -SecurityTypes None \
    -xstartup "${HOME}/.vnc/xstartup" \
    -fg
