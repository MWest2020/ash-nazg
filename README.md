# Ash Nazg

> One app to run them all — a universal application runtime for Nextcloud.

**Status:** alpha — scaffolding. Not for production. Not yet on the App Store.

Ash Nazg is a Nextcloud ExApp that lets users upload arbitrary binaries to
their Files and execute them inside sandboxed runtime engines, with output
streamed to the browser and writes flowing back into Files via WebDAV.

The MVP demo: upload `keen1.exe` and `windows311.img`, click Run, see
Commander Keen and Windows 3.11's Program Manager rendered inside your
Nextcloud — saving back to your own Files.

## Why

Today, running a custom program against your Nextcloud Files requires
building a full Nextcloud PHP app and publishing it to the App Store.
That bar is too high for someone with a single legacy program: a DOS-era
tool, an old Win 3.x utility, a game from 1992. Ash Nazg lowers the bar to
"upload a binary, click Run".

## What ships in v1

- One engine: **DOSBox-X** — handles Windows 3.x and DOS executables.
- One distribution channel: **Nextcloud App Store** via AppAPI ExApp.
- One streaming layer: **KasmVNC** in an iframe.
- One security model: **admin-only execution**, hard resource limits,
  audit log per run.

Future engines (Wine, RetroArch, JVM, wasmtime) are out of scope for v1
but explicitly designed for as drop-in additions.

## Repository layout

```
ash-nazg/
├── README.md                            ← this file
├── LICENSE                              ← AGPL-3.0
├── THIRD_PARTY_NOTICES.md               ← upstream license attributions
├── SECURITY.md                          ← vulnerability reporting policy
├── CONTRIBUTING.md                      ← OpenSpec workflow rules
├── .gitignore
├── .editorconfig
│
├── openspec/                            ← spec-driven development
│   ├── config.yaml                      ← project context for AI agents
│   ├── specs/                           ← living source-of-truth specs
│   │   └── .gitkeep                     ← (populated as changes archive)
│   └── changes/
│       └── init-mvp-runtime/            ← THIS change: greenfield scaffold
│           ├── proposal.md
│           ├── design.md
│           ├── tasks.md
│           └── specs/
│               ├── detection/spec.md
│               ├── engines/spec.md
│               ├── sandbox/spec.md
│               └── files-integration/spec.md
│
├── appinfo/
│   ├── info.xml                         ← Nextcloud app manifest
│   └── screenshots/                     ← (placeholders until v1 demo works)
│
├── host/                                ← the ExApp host container
│   ├── Dockerfile
│   ├── pyproject.toml                   ← uv-managed
│   ├── src/ash_nazg/
│   │   ├── main.py                      ← FastAPI entry
│   │   ├── appapi.py                    ← AppAPI registration
│   │   └── engines/__init__.py          ← Engine protocol
│   ├── static/                          ← frontend bundle output
│   └── tests/
│
├── engines/                             ← engine sidecars
│   └── dosbox-x/
│       ├── Dockerfile                   ← DOSBox-X + KasmVNC + davfs2
│       ├── entrypoint.sh                ← stub in this change
│       └── README.md                    ← engine contract docs
│
├── frontend/                            ← Vue 3 + TypeScript SPA
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── files-action.ts              ← right-click "Run with Ash Nazg"
│       └── IframeHost.vue               ← KasmVNC stream container
│
├── docs/
│   ├── installation.md                  ← admin install steps
│   ├── user-guide.md                    ← how to run a binary
│   ├── compatibility.md                 ← Nextcloud / AppAPI matrix
│   ├── security-model.md                ← sandbox + audit details
│   └── bring-your-own-content.md        ← legal boundary statement
│
└── .github/
    └── workflows/
        ├── build-host.yml               ← multi-arch GHCR push
        ├── build-engine-dosbox.yml
        ├── test.yml
        └── openspec-validate.yml
```

## How to develop on Ash Nazg

This repository uses **OpenSpec** (Fission-AI) for spec-driven development.
Every change starts with a proposal under `openspec/changes/`.

```bash
# Install OpenSpec CLI (one-time)
npm install -g @fission-ai/openspec@latest

# Initialize tooling for Claude Code (one-time per clone)
openspec init

# Validate the seed change
openspec validate init-mvp-runtime

# When ready to start a new feature
/opsx:propose <change-name>     # in Claude Code
```

After cloning, the next planned change is `wire-dosbox-engine` — connecting
the dispatcher to the DOSBox-X container so the demo flow actually works
end to end.

## Bring your own content

Ash Nazg ships zero proprietary binaries. To run Windows 3.11, you provide
your own legally-obtained installation floppies. To run a DOS game, you
provide your own copy. To run a legacy business application, you provide
your own license. See [`docs/bring-your-own-content.md`](docs/bring-your-own-content.md).

## License

AGPL-3.0-or-later. See [`LICENSE`](LICENSE).

## Disclaimer

The name "Ash Nazg" is a Black Speech reference from J.R.R. Tolkien's
legendarium, used nominatively as a fan-homage. This project is not
affiliated with or endorsed by the Tolkien Estate, Microsoft, id
Software, Apogee Software, or any console manufacturer. All trademarks
remain the property of their respective owners.
