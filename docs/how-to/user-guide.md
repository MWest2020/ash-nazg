---
status: draft
last_reviewed: 2026-07-13
---

# Ash Nazg user guide

> **Status: DRAFT.** This guide will be finalised in the batch
> covering the `wire-dosbox-engine` end-to-end demo. Steps below
> describe the *intended* flow per the design docs and specs;
> they will not actually work until that change lands.

## Who can use Ash Nazg

In v1: **admin users only**. Non-admin users will not see the
"Run with Ash Nazg" action on any file. This is enforced both in
the UI (the action's `enabled` predicate hides it) and at the
host shim's `/run` endpoint (the host re-validates admin status).

Future versions may relax this. The relaxation will be its own
OpenSpec change.

## Running a binary

1. **Upload the binary to your Nextcloud Files.** Any DOS or
   Windows 3.x executable up to 100 MB. Acceptable extensions in
   v1: `.exe`, `.com`, `.bat`. The host detects the format from
   the file's magic bytes regardless of extension.
2. **Right-click the file** in the Files app.
3. **Choose "Run with Ash Nazg".** The host spawns a fresh
   DOSBox-X engine container, mounts your Files directory at
   `/mnt/files` inside the engine, and starts the binary.
4. **Interact with the running session** in the iframe that
   appears. Output streams via KasmVNC; keyboard and mouse input
   pass through.
5. **Save inside the running app**, the way you would on a real
   machine. Anything written to a path under `/mnt/files` is
   stored back in your Nextcloud Files immediately. Anything
   written to `/tmp` or to memory disappears when the session
   ends.

## Sessions and lifetime

- A session lasts as long as you keep the iframe open and active.
- The default **idle timeout** is 15 minutes. After that, the host
  sends SIGTERM, waits 30 seconds, then SIGKILL. The admin can
  raise or lower this in the settings panel.
- A session that closes gracefully (you click Close, or the binary
  exits) is logged with `exit_status: graceful_close`. A timeout
  kills are logged with `exit_status: timeout`.

## What gets saved, what doesn't

| Path inside session  | Saved?    | Notes                                            |
|----------------------|-----------|--------------------------------------------------|
| `/mnt/files/...`     | yes       | Shows up in your Nextcloud Files immediately.    |
| `/tmp/...`           | no        | tmpfs, gone at session end.                      |
| Anywhere else        | no        | Root filesystem is read-only.                    |

If you're using DOSBox-X to install software into a virtual hard
disk image, save that image file under `/mnt/files`. You can then
upload that image again next session and skip reinstall.

## Bring your own content

Ash Nazg does not ship Windows, DOS, ROMs, BIOS files, or any
proprietary installation media. You upload your own from sources
you have a right to use. See
[`bring-your-own-content.md`](./bring-your-own-content.md).

## What DOSBox-X v1 can and cannot run

The v1 release ships exactly one engine: DOSBox-X. It is **not** a
general "run any Windows binary" environment. Honest scope keeps
expectations aligned.

### What it **can** run

- **MS-DOS / PC-DOS / FreeDOS programs.** All eras: DOS 3.x
  through 7.x. Anything that ran on a 386, 486, or original
  Pentium runs here.
- **DOS games.** Commander Keen, Doom, Wolfenstein 3D, Lemmings,
  Prince of Persia, Sim City Classic, Master of Orion, X-COM,
  Theme Hospital, etc. Bring your own copies.
- **Windows 3.x.** Windows 3.0, 3.1, 3.11 / Windows for
  Workgroups. The Program Manager, File Manager, Solitaire,
  Minesweeper, Write, Paint. Old business apps and CAD tools that
  shipped for Win 3.x.
- **Win16 binaries** — software that targeted the 16-bit Windows
  API and runs under Win 3.x. Often labelled "Windows 3.1" on the
  box.
- **Some early Win32s applications.** Win32s was a 32-bit
  extension layer for Windows 3.x. Coverage is partial; the
  DOSBox-X project tracks specific titles.

### What it **cannot** run

- **Windows 95, 98, ME.** These run *inside* DOSBox-X under
  certain configurations (it's an x86 PC emulator), but
  performance and reliability vary widely. Ash Nazg v1 does NOT
  ship a Win 95+ profile; treating it as supported would be
  dishonest.
- **Windows NT 4 / 2000 / XP / Vista / 7 / 8 / 10 / 11.** Out of
  scope. These need different engines (Wine for compatible Win32
  apps; full hypervisors for the OSes themselves). v2 may add a
  Wine engine for Win32 apps; that's a separate change, not a
  DOSBox-X capability.
- **Modern Win64 binaries.** Anything compiled in the last decade
  for x86_64 Windows. Out of scope for the same reason.
- **macOS, Linux, BSD binaries.** Detected and refused with
  `415 Unsupported Media Type` (per the `detection` capability
  spec). Future engines may handle these.
- **Java archives, WebAssembly modules.** Detected, refused, same
  reason.
- **DRM-protected commercial software** that depends on
  contemporary online activation. Even if the binary is Win 3.x
  in shape, a DRM check that needs a 2020s Microsoft activation
  server will not work.
- **3D-accelerated games.** No GPU passthrough in v1; software
  rendering only. Doom and Quake-era games are fine; anything
  expecting hardware acceleration will be slow or broken.
- **Audio.** No audio routing from the engine to the browser in
  v1. The KasmVNC stream is video-only.

### Heuristics

If you can answer "yes" to most of these, it'll probably run:

- Was the program released between roughly **1985 and 1998**?
- Did the box mention **DOS** or **Windows 3.x**?
- Is the executable **smaller than 100 MB**?
- Did the original ship on **floppies or a single CD**, with no
  online-only activation?

If those are mostly "no", v1 is the wrong tool.

### Future engines

Out of scope for v1, but designed for as drop-in additions:

| Engine | Targets | Status |
|---|---|---|
| Wine | Modern Win32 / Win64 apps | Designed for; not in v1 |
| RetroArch | Console emulation (NES, SNES, Genesis, …) | Designed for; not in v1 |
| JVM | Java applications and applets | Designed for; not in v1 |
| wasmtime | WebAssembly modules | Designed for; not in v1 |

Each is its own future OpenSpec change. None ship in v1.

## Other limitations in v1

The capability scope above (what DOSBox-X v1 can and cannot run)
is the main one. A few smaller v1 caveats not already covered
there:

- **One streaming protocol: KasmVNC.** No alternative chrome.
- **No clipboard sync** between the iframe and the surrounding
  Nextcloud UI.
- **No multi-tenant concurrent sessions** beyond admin-only
  single-session.
- **No file-watch / cron triggers** — every Run is user-initiated.

None of these is a bug; all are intentionally out of scope for v1
and tracked in subsequent OpenSpec changes.

## Troubleshooting (placeholder)

To be filled in once the wiring change is verified end-to-end.

## Reporting bugs

Bugs go to the GitHub issue tracker:
<https://github.com/MWest2020/ash-nazg/issues>. Security issues go
private — see [`SECURITY.md`](../SECURITY.md).
