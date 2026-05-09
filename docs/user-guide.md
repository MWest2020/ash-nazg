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

## Limitations in v1

- One engine: DOSBox-X. ELF binaries (Linux), Mach-O (macOS),
  WebAssembly, and Java archives are detected but rejected with
  `415 Unsupported Media Type`. Future engines will handle these.
- One streaming protocol: KasmVNC. No audio in v1.
- No GPU acceleration in v1. 3D-heavy programs will be slow or
  unrenderable.
- No clipboard sync between the iframe and the surrounding
  Nextcloud UI in v1.

These are tracked in subsequent OpenSpec changes; none of them is
a bug, all are intentionally out of scope for the scaffolding +
demo flow.

## Troubleshooting (placeholder)

To be filled in once the wiring change is verified end-to-end.

## Reporting bugs

Bugs go to the GitHub issue tracker:
<https://github.com/MWest2020/ash-nazg/issues>. Security issues go
private — see [`SECURITY.md`](../SECURITY.md).
