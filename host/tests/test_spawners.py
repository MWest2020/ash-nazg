"""Tests for SessionSpawner implementations."""

from __future__ import annotations

import pytest

from ash_nazg.engines import FileMeta, SessionConfig
from ash_nazg.spawners import (
    StubSpawner,
    stub_spawner_from_env,
)


def _config() -> SessionConfig:
    return SessionConfig(
        image="ghcr.io/test/engine:0.1",
        cpu_limit=1.0,
        memory_limit_mb=1024,
        mount_path="/mnt/files",
        streaming_protocol="kasmvnc",
        streaming_port=6901,
        idle_timeout_seconds=900,
        entrypoint_args=["dosbox-x", "/mnt/files/Programs/keen1.exe"],
    )


def _meta() -> FileMeta:
    return FileMeta(
        path="/Programs/keen1.exe",
        size_bytes=212_000,
        extension="exe",
        magic_class="mz-dos",
    )


@pytest.mark.asyncio
async def test_stub_spawner_returns_fixed_endpoint() -> None:
    spawner = StubSpawner(host="127.0.0.1", port=16901)
    handle = await spawner.spawn(
        session_id="abc",
        config=_config(),
        file_meta=_meta(),
        user_id="alice",
    )
    assert handle.host == "127.0.0.1"
    assert handle.port == 16901
    assert handle.session_id == "abc"
    assert handle.container_id.startswith("stub-")


def test_stub_spawner_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASH_NAZG_DEMO_HOST", raising=False)
    monkeypatch.delenv("ASH_NAZG_DEMO_PORT", raising=False)
    spawner = stub_spawner_from_env()
    assert spawner.host == "127.0.0.1"
    assert spawner.port == 16901


def test_stub_spawner_from_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASH_NAZG_DEMO_HOST", "engine.svc")
    monkeypatch.setenv("ASH_NAZG_DEMO_PORT", "9999")
    spawner = stub_spawner_from_env()
    assert spawner.host == "engine.svc"
    assert spawner.port == 9999
