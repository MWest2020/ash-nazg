#!/usr/bin/env bash
#
# Ash Nazg DOSBox-X engine container — entrypoint.
#
# Three operating modes, picked at runtime by env vars:
#
#   1. NEXTCLOUD_URL + APP_TOKEN + NC_USER_ID set
#      → davfs2 mount the user's Files at /mnt/files, then
#        exec dosbox-x FILE_PATH (which is expected to point
#        somewhere under /mnt/files, e.g. /mnt/files/Programs/keen1.exe).
#        Production path — the wire-dosbox-engine §7 spec.
#
#   2. FILE_PATH set, NEXTCLOUD_URL unset
#      → Skip the WebDAV mount. The orchestrator is expected to
#        have bind-mounted the binary at FILE_PATH. exec dosbox-x FILE_PATH.
#        Demo / integration-test path.
#
#   3. Neither set
#      → exec dosbox-x with no argument; user gets the bare DOS prompt.
#        Smoke-test path — verifies the engine itself boots.
#
# In all three cases the working directory before exec'ing dosbox-x is
# the directory containing FILE_PATH (per files-integration spec
# "Working directory is the binary's directory") so relative path
# reads inside the program land in the same Files folder.

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

# --- WebDAV mount (mode 1) ------------------------------------------------
#
# davfs2 needs:
#   1. Per-user secrets file at ~/.davfs2/secrets with mode 600.
#   2. /etc/davfs2/davfs2.conf permitting `use_locks 0` and the user_id
#      to mount without root (we're in the `davfs2` group).
#   3. mount.davfs to be SUID root (Ubuntu ships it this way).
#
# We construct the mount URL from NEXTCLOUD_URL + NC_USER_ID; the
# secrets line gives APP_TOKEN as the password. This token MUST be
# scoped to the user's Files only (per sandbox spec "Per-session
# token scoping"); the host shim issues it.
mount_webdav() {
    local nc_url="${NEXTCLOUD_URL%/}"
    local user="${NC_USER_ID}"
    local mount_url="${nc_url}/remote.php/dav/files/${user}/"

    mkdir -p "${HOME}/.davfs2"
    chmod 700 "${HOME}/.davfs2"
    # secrets format: <mount-url-or-mountpoint> <username> <password>
    # The username is the NC user; the password is the per-session token.
    printf '%s %s %s\n' "${mount_url}" "${user}" "${APP_TOKEN}" \
        > "${HOME}/.davfs2/secrets"
    chmod 600 "${HOME}/.davfs2/secrets"

    # davfs2 by default writes a cache under ~/.davfs2/cache and a
    # pidfile alongside; both live under HOME so we don't need extra
    # writable surfaces beyond /tmp + /mnt/files + HOME.
    echo "ash-nazg engine: mounting WebDAV ${mount_url} → /mnt/files"
    # `-o uid` makes the mount appear owned by the app user so
    # dosbox-x can read it without further chowns. `_netdev` defers
    # to davfs2's own retry; we add a simple loop below for resilience.
    local retries=5
    while (( retries > 0 )); do
        if mount -t davfs -o uid=1000,gid=1000,rw "${mount_url}" /mnt/files; then
            return 0
        fi
        retries=$((retries - 1))
        echo "ash-nazg engine: davfs2 mount failed, ${retries} retries left"
        sleep 2
    done
    echo "ash-nazg engine: davfs2 mount permanently failed; continuing without /mnt/files"
    return 1
}

if [ -n "${NEXTCLOUD_URL:-}" ] && [ -n "${NC_USER_ID:-}" ] && [ -n "${APP_TOKEN:-}" ]; then
    mount_webdav || true
fi

# --- xstartup: what gets exec'd inside the X session ----------------------
# DOSBox-X is the whole UI — when it exits the session ends.
cat > "${HOME}/.vnc/xstartup" <<'XSTARTUP'
#!/bin/sh
# Disable the screensaver and other X niceties; we only want dosbox.
xsetroot -solid black 2>/dev/null || true

# Working directory = parent of FILE_PATH if set (so the program's
# relative reads land in the right Files folder).
if [ -n "${FILE_PATH:-}" ] && [ -f "${FILE_PATH}" ]; then
    cd "$(dirname "${FILE_PATH}")"
    exec dosbox-x "${FILE_PATH}"
else
    # Smoke-test path. No file → bare DOS prompt.
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
