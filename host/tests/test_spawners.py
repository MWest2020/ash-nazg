"""Tests for SessionSpawner implementations."""

from __future__ import annotations

import pytest

from ash_nazg.engines import FileMeta, SessionConfig
from ash_nazg.spawners import (
    DockerSubprocessSpawner,
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


def test_docker_subprocess_argv_has_required_flags() -> None:
    spawner = DockerSubprocessSpawner(network="ash-nazg-net")
    argv = spawner._build_argv(
        session_id="abc12345-uuid",
        config=_config(),
        file_meta=_meta(),
        user_id="alice",
    )
    assert argv[0] == "docker"
    assert argv[1] == "run"
    # sandbox spec resource limits
    assert "--cpus" in argv and "1.0" in argv
    assert "--memory" in argv and "1024m" in argv
    assert "--memory-swap" in argv and argv.count("1024m") == 2
    # read-only root + tmpfs for /tmp
    assert "--read-only" in argv
    assert any(a.startswith("/tmp:rw,size=") for a in argv)  # noqa: S108 — docker tmpfs spec
    # network attach
    assert "ash-nazg-net" in argv
    # per-session env
    assert any(a.startswith("FILE_PATH=") and "keen1.exe" in a for a in argv)
    assert any(a == "NC_USER_ID=alice" for a in argv)
    # session label for cleanup
    assert any(a.startswith("session_id=") for a in argv)
    # image is the last positional arg
    assert argv[-1] == "ghcr.io/test/engine:0.1"


def test_docker_subprocess_no_network_arg_when_unset() -> None:
    spawner = DockerSubprocessSpawner(network=None)
    argv = spawner._build_argv(
        session_id="abc",
        config=_config(),
        file_meta=_meta(),
        user_id="alice",
    )
    assert "--network" not in argv


def test_docker_subprocess_extra_env_passed_through() -> None:
    spawner = DockerSubprocessSpawner(
        extra_env={"NEXTCLOUD_URL": "http://nextcloud", "APP_TOKEN": "secret"}
    )
    argv = spawner._build_argv(
        session_id="abc",
        config=_config(),
        file_meta=_meta(),
        user_id="alice",
    )
    assert "NEXTCLOUD_URL=http://nextcloud" in argv
    assert "APP_TOKEN=secret" in argv
