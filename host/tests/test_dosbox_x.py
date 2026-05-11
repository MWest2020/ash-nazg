"""Tests for the dosbox-x engine plugin.

Covers `engines` spec scenarios:
- "dosbox-x advertises supported formats" — can_handle by magic
- "dosbox-x produces a valid session config" — canonical SessionConfig values
"""

from __future__ import annotations

import pytest

from ash_nazg.engines import FileMeta
from ash_nazg.engines.dosbox_x import (
    DEFAULT_CPU_LIMIT,
    DEFAULT_MEMORY_LIMIT_MB,
    ENGINE_ID,
    ENGINE_IMAGE,
    IDLE_TIMEOUT_SECONDS,
    MOUNT_PATH,
    STREAMING_PORT,
    DosboxXEngine,
)


def _meta(magic: str, path: str = "/Programs/keen1.exe") -> FileMeta:
    return FileMeta(path=path, size_bytes=212_000, extension="exe", magic_class=magic)


@pytest.fixture
def engine() -> DosboxXEngine:
    return DosboxXEngine()


# --- can_handle ------------------------------------------------------------


@pytest.mark.parametrize("magic", ["pe32", "pe32-plus", "mz-dos"])
def test_can_handle_supported(engine: DosboxXEngine, magic: str) -> None:
    assert engine.can_handle(_meta(magic)) is True


@pytest.mark.parametrize("magic", ["elf", "wasm", "jar", "mach-o", "unknown"])
def test_can_handle_unsupported(engine: DosboxXEngine, magic: str) -> None:
    assert engine.can_handle(_meta(magic)) is False


# --- session_config --------------------------------------------------------


def test_session_config_values_match_spec(engine: DosboxXEngine) -> None:
    cfg = engine.session_config(_meta("mz-dos"))
    assert cfg.image == ENGINE_IMAGE
    assert cfg.cpu_limit == DEFAULT_CPU_LIMIT == 1.0
    assert cfg.memory_limit_mb == DEFAULT_MEMORY_LIMIT_MB == 1024
    assert cfg.mount_path == MOUNT_PATH == "/mnt/files"
    assert cfg.streaming_protocol == "kasmvnc"
    assert cfg.streaming_port == STREAMING_PORT == 6901
    assert cfg.idle_timeout_seconds == IDLE_TIMEOUT_SECONDS == 900


def test_session_config_resolves_path_under_mount(engine: DosboxXEngine) -> None:
    cfg = engine.session_config(_meta("mz-dos", path="/Programs/keen1.exe"))
    assert cfg.entrypoint_args == ["dosbox-x", "/mnt/files/Programs/keen1.exe"]


def test_session_config_strips_leading_slash(engine: DosboxXEngine) -> None:
    cfg = engine.session_config(_meta("mz-dos", path="/keen1.exe"))
    assert cfg.entrypoint_args[1] == "/mnt/files/keen1.exe"


def test_image_is_pinned_not_latest(engine: DosboxXEngine) -> None:
    """engines spec req "Engine images use pinned tags, never :latest"."""
    assert ":" in ENGINE_IMAGE
    tag = ENGINE_IMAGE.rsplit(":", 1)[1]
    assert tag != "latest"
    assert tag != ""


def test_engine_id_matches_constant(engine: DosboxXEngine) -> None:
    assert engine.id == ENGINE_ID == "dosbox-x"
