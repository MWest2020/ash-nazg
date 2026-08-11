# ROM fixtures (emulator playthrough seam)

This directory is the drop-in point for the **emulator + ROM playthrough
test** (`host/tests/test_gameboy_playthrough.py`) — the "can we actually
play Pokémon" harness.

It is **empty by design**: game ROMs are copyrighted, so none is committed.
The playthrough test *skips* until a ROM is present, then runs for real.

## How to enable the playthrough test

1. Drop a **legally-owned** Game Boy / Game Boy Color ROM here, e.g.
   `host/tests/fixtures/roms/pokemon.gb` (`.gb` or `.gbc`), **or** point the
   `ASH_NAZG_ROM` env var at a ROM path.
2. Register a Game Boy emulator engine on the `ash_nazg.engines` entrypoint
   group (a `gameboy` `Engine` whose `can_handle()` matches the ROM's detected
   type and whose `session_config()` names the emulator container image). This
   is the `wire-gameboy-engine` follow-up — the dosbox-x engine
   (`ash_nazg/engines/dosbox_x.py`) is the template.
3. Run `uv run pytest tests/test_gameboy_playthrough.py`.

With both in place the test drives the real dispatch pipeline (detect → select
engine → spawn via the StubSpawner) and asserts a session starts for the ROM —
the host-side proof that a ROM reaches an emulator. In-browser video needs the
`streaming-proxy` change (KasmVNC iframe) on top; that is not part of this
harness.

Everything under this directory except this README and `.gitkeep` is
git-ignored so a local ROM never gets committed.
