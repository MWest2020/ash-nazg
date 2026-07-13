---
status: draft
last_reviewed: 2026-07-13
---

# Demo — what's runnable today

> **Use `127.0.0.1`, not `localhost`.** Many distros'
> `/etc/hosts` map `localhost` to both `127.0.0.1` and `::1`.
> Most browsers/curl try IPv6 first; the engine container's
> port publish is IPv4-only in some podman configs and the
> connection times out / TLS handshake fails. `127.0.0.1`
> always works.


This is the honest version of the demo. Three things you can
actually do; two things that work but need one more wiring step;
the rest is documented in tasks.md.

## The hardest part is already done

A DOSBox-X DOS prompt rendered in your browser. Real keyboard
input. ~1280×800 desktop area inside KasmVNC's noVNC-style
client. It's running in a Linux container; KasmVNC serves the
JS client, the X server runs Xvnc, DOSBox-X is an X client.
That's the "engine" tier of the architecture, in full.

## Run the standalone engine demo (no Nextcloud needed)

```bash
docker build -t ash-nazg-dosbox-x:demo \
    -f engines/dosbox-x/Dockerfile engines/dosbox-x/

docker run -d --name engine-demo \
    --security-opt label=disable \
    -p 16901:8444 \
    ash-nazg-dosbox-x:demo

# Wait 12 s
sleep 12

# Browser
xdg-open 'https://127.0.0.1:16901/vnc.html' 2>/dev/null \
    || echo 'Browse to https://127.0.0.1:16901/vnc.html'
```

- Accept the self-signed cert
- Login: **demo** / **ash_nazg**
- Click *Connect*. DOSBox-X DOS prompt appears.

To run a real DOS binary, mount it and set `FILE_PATH`:

```bash
docker run -d --name engine-demo \
    --security-opt label=disable \
    -p 16901:8444 \
    -v "$(pwd)/keen1.exe:/programs/keen1.exe:ro,z" \
    -e FILE_PATH=/programs/keen1.exe \
    ash-nazg-dosbox-x:demo
```

Stop: `docker rm -f engine-demo`.

## Run the full stack (Nextcloud + ExApp + engine)

```bash
# Workarounds for rootless podman; no-ops on Docker rootful
chmod 0666 /run/user/$(id -u)/podman/podman.sock
# (one-time per host) allow insecure local registry
mkdir -p ~/.config/containers
cat > ~/.config/containers/registries.conf <<'EOF'
[[registry]]
location = "127.0.0.1:5000"
insecure = true
EOF

docker compose -f scripts/local-nextcloud-stack.yml up -d
./scripts/bootstrap-nextcloud.sh    # registers ash_nazg as an ExApp
# enable (the occ enable hangs sometimes; fall back to direct DB)
docker exec scripts_nextcloud_1 php -r "
\$p = new PDO('pgsql:host=postgres;dbname=nextcloud','nextcloud','nextcloud-local-dev');
\$p->exec(\"UPDATE oc_ex_apps SET enabled = 1 WHERE appid = 'ash_nazg'\");
"
docker exec scripts_valkey_1 valkey-cli FLUSHDB
docker compose -f scripts/local-nextcloud-stack.yml restart nextcloud
```

What you can now visit:

| URL | What you see | Credentials |
|---|---|---|
| `http://localhost:8088` | Nextcloud login | admin / admin-local-dev |
| `http://localhost:8088/index.php/settings/apps` | Apps list — Ash Nazg shown as installed | admin |
| `https://127.0.0.1:16901/vnc.html` | DOSBox-X DOS prompt | demo / ash_nazg |

Tear down: `docker compose -f scripts/local-nextcloud-stack.yml down -v`.

## What works today, end-to-end

1. **NC 32 + AppAPI 5.x + HaRP** spins up reproducibly.
2. **ash_nazg ExApp** registers via `app_api:app:register` with
   our `info.xml`, gets pulled from the local registry, spawned
   by HaRP, attached to the compose network, and reports
   `enabled: True / status.error: ''`.
3. **`oc_ex_apps_routes`** populated with 6 PUBLIC/USER/ADMIN
   routes — the AppAPI route-allowlist mechanism works as
   designed.
4. **DOSBox-X engine container** runs (KasmVNC + Xvnc + dosbox-x);
   the noVNC web client serves on port 8444 inside / 16901
   outside.
5. **Browser sees DOSBox-X** at `https://127.0.0.1:16901/vnc.html`.

## What works "almost" — one wiring step short

1. **Right-click → Run with Ash Nazg in Files.** The
   `frontend/src/files-action.ts` bundle is built and would open
   `https://127.0.0.1:16901/vnc.html` in a new tab when its
   `exec` runs. But NC doesn't automatically load
   `host/static/js/files-action-*.js` into the Files-app HTML —
   that needs an entry in `info.xml` under
   `<external-app><scripts>` plus a corresponding row in
   `oc_ex_ui_files_actions`. **Not yet added.** The next step
   for the integrated demo is wiring AppAPI's script-injection
   mechanism (a few lines in `info.xml`).

2. **AppAPI proxy URL.** Visiting
   `http://localhost:8088/index.php/apps/app_api/proxy/ash_nazg/...`
   from `curl -u admin:...` still 404s. The path itself is
   plumbed (NC routes it to AppAPI's proxy controller); the
   issue is auth — Caddy may be stripping the `Authorization`
   header, or AppAPI's proxy might require a session cookie
   instead of basic auth. Browser-based access (with a real
   logged-in session) hasn't been tested yet. **Probably 30
   min of debugging away.**

## What's deferred to later changes

- **Per-Run engine spawn via HaRP** (current demo runs one
  always-on engine). The host shim's `/run` dispatcher that
  asks HaRP to spawn a fresh engine per session is wire-dosbox-
  engine §5.
- **WebDAV mount** of user Files inside the engine container.
  Currently `FILE_PATH` is a bind-mount or unset. The proper
  davfs2 mount lands in §7.
- **AppAPI websocket proxy** so the KasmVNC stream renders in
  an iframe inside NC's chrome (instead of a new browser tab).
  That's the `streaming-proxy` change — a separate proposal
  after `wire-dosbox-engine`.

## Security note

This demo runs KasmVNC with no VNC-protocol auth (`-SecurityTypes
None`) and a self-signed cert. The HTTP-layer login (demo/
ash_nazg) is the only gate. **Don't ship this configuration.**
Production replaces it with per-session tokens issued by the
host shim and routed through AppAPI's HaRP proxy.
