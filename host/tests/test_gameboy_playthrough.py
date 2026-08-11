"""Emulator + ROM playthrough seam — the "can we play Pokémon" harness.

This test is the drop-in point requested for the emulator flow. It is
**import-safe and skips cleanly today**, and goes live the moment two things
exist (see host/tests/fixtures/roms/README.md):

1. a ROM fixture at `host/tests/fixtures/roms/*.gb` / `*.gbc` (or `$ASH_NAZG_ROM`), and
2. a Game Boy emulator engine registered on the `ash_nazg.engines` entrypoint
   group whose `can_handle()` matches the ROM's detected type.

When both are present it drives the real dispatch pipeline (detect → select the
first enabled engine that handles the ROM → spawn via the StubSpawner) and
asserts a session starts — the host-side proof that a ROM reaches an emulator.
In-browser video is `streaming-proxy`, not this harness.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ash_nazg.detection import DETECTION_READ_BYTES, classify
from ash_nazg.dispatch import ActiveSessionTracker, Dispatcher, DispatchOk
from ash_nazg.engines.registry import discover_engines
from ash_nazg.io_adapters import InMemoryAuditLogger, InMemoryFileReader
from ash_nazg.spawners import StubSpawner

_ROMS_DIR = Path(__file__).parent / "fixtures" / "roms"


def _find_rom() -> Path | None:
    env = os.environ.get("ASH_NAZG_ROM")
    if env:
        p = Path(env)
        return p if p.is_file() else None
    for pattern in ("*.gb", "*.gbc"):
        hits = sorted(_ROMS_DIR.glob(pattern))
        if hits:
            return hits[0]
    return None


@pytest.mark.asyncio
async def test_rom_reaches_an_emulator_engine() -> None:
    rom = _find_rom()
    if rom is None:
        pytest.skip(
            "no ROM fixture — drop a legally-owned .gb/.gbc in "
            "host/tests/fixtures/roms/ or set $ASH_NAZG_ROM (see that dir's README)"
        )

    head = rom.read_bytes()[:DETECTION_READ_BYTES]
    detected = classify(head, extension=rom.suffix)

    registry = discover_engines()
    engine = next((e for e in registry.enabled() if e.can_handle(detected)), None)
    if engine is None:
        pytest.skip(
            f"ROM {rom.name} detected as {detected!r} but no enabled engine handles it "
            "— register a Game Boy emulator engine on the 'ash_nazg.engines' entrypoint "
            "(see fixtures/roms/README.md; wire-gameboy-engine follow-up)"
        )

    files_path = f"/roms/{rom.name}"
    dispatcher = Dispatcher(
        registry=registry,
        file_reader=InMemoryFileReader({files_path: head}),
        spawner=StubSpawner(host="127.0.0.1", port=16901),
        audit=InMemoryAuditLogger(),
        active_sessions=ActiveSessionTracker(),
    )
    result = await dispatcher.dispatch(files_path=files_path, user_id="tester", is_admin=True)

    assert isinstance(result, DispatchOk), f"dispatch failed for {rom.name}: {result}"
    assert result.session_id and result.host and result.port
