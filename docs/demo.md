# Demo — DOSBox-X running in a browser

> **Status: standalone visual demo.** Proves the engine container
> works end-to-end. Full Nextcloud-integrated flow (right-click a
> file in Files → see DOSBox-X) is still in progress; this is the
> "see DOSBox-X in a browser tab" milestone.

## What you'll see

1. A DOSBox-X DOS prompt rendered in your browser
2. Real keyboard input — type `dir`, run programs
3. ~1280×800 desktop area inside the noVNC-style client

## Run it

```bash
# Build the engine image (~5 min; downloads KasmVNC, dosbox-x)
docker build -t ash-nazg-dosbox-x:demo \
    -f engines/dosbox-x/Dockerfile engines/dosbox-x/

# Run with the KasmVNC web-client port exposed
docker run -d --name ash-nazg-engine-demo \
    --security-opt label=disable \
    -p 16901:8444 \
    ash-nazg-dosbox-x:demo

# Wait ~12 s for KasmVNC to bind
sleep 12

# Open the browser
xdg-open 'https://localhost:16901/vnc.html' 2>/dev/null \
    || echo 'Browse to https://localhost:16901/vnc.html'
```

The browser will warn about the self-signed certificate — accept
it (local dev only). On the KasmVNC login page:

- **Username:** `demo`
- **Password:** `ash_nazg`

Click *Connect*. After a couple of seconds the DOSBox-X welcome
screen + DOS prompt appears.

## Stop

```bash
docker rm -f ash-nazg-engine-demo
```

## What you're seeing under the hood

```
[browser] ──HTTPS:16901──▶ [engine container]
                              ├─ KasmVNC (port 8444 internal)
                              │     └─ serves vnc.html, noVNC client, websocket
                              └─ Xvnc :1 ──▶ xstartup ──▶ dosbox-x
```

- **KasmVNC** is the VNC server with a built-in noVNC web client.
  No browser plugin needed — the JS in vnc.html does the work.
- **Xvnc** is the X server KasmVNC drives. DOSBox-X runs as an X
  client inside it.
- **DOSBox-X** is invoked from `~/.vnc/xstartup`. If `FILE_PATH`
  is set as an env var on `docker run` (and the path exists in the
  container), DOSBox-X runs that file. Otherwise the bare DOS
  prompt appears.

## Running a real program

To run an actual DOS executable, mount it into the container and
point DOSBox-X at it:

```bash
# Get a homebrew DOS program (FreeDOS, OpenWatcom, abandonware
# you have rights to, etc.). For this example pretend you have
# keen1.exe in your current directory.

docker run -d --name ash-nazg-engine-demo \
    --security-opt label=disable \
    -p 16901:8444 \
    -v "$(pwd)/keen1.exe:/programs/keen1.exe:ro,z" \
    -e FILE_PATH=/programs/keen1.exe \
    ash-nazg-dosbox-x:demo
```

DOSBox-X loads the binary and (depending on the binary) runs it
straight away.

## Why this isn't yet the full demo

The fully-wired flow has more pieces:

1. **Upload to Nextcloud Files** — works (NC is up at
   localhost:8088 in the full stack).
2. **Right-click → Run with Ash Nazg** — file action is
   registered but its `exec` toasts "not yet wired".
3. **Host dispatcher** — `/run` endpoint that magic-byte-detects
   the binary and asks HaRP to spawn an engine container with
   `FILE_PATH` set. **Not yet implemented** (§5 of
   wire-dosbox-engine).
4. **Browser shows the running session** — currently you'd need
   to browse to the spawned container's host-exposed port. The
   AppAPI websocket proxy (so the iframe inside NC's UI shows
   the stream) is a future change (`streaming-proxy`).

What this demo proves:

- The engine container (item 4-ish) works in isolation.
- KasmVNC + DOSBox-X + the entrypoint pipeline are real.
- The image you'd publish to GHCR for the App Store is the same
  image driving this demo.

Closing the remaining gaps is wire-dosbox-engine §3 / §5 / §8
work.

## Security note

This demo runs KasmVNC with auth disabled (`-SecurityTypes None`
plus a permissive yaml) and a self-signed cert at
`/etc/ssl/private/ssl-cert-snakeoil.key`. **Don't ship this
configuration.** Production replaces the demo password with
per-session tokens issued by the host shim and routed through
AppAPI's HaRP proxy.
