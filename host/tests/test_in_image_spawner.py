"""Tests for the in-image session spawner.

The real engine script starts KasmVNC and DOSBox-X, which no unit test
wants. These drive the spawner with a stand-in script that does the one
thing the spawner actually waits for — bind the websocket port it was
handed — so the readiness, failure and teardown paths are exercised for
real, without an emulator.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import pytest

from ash_nazg.engines import FileMeta, SessionConfig
from ash_nazg.io_adapters import InMemoryFileReader
from ash_nazg.spawners import InImageSpawner

BASE_PORT = 45000
MZ_HEAD = b"MZ\x90\x00" + b"\x00" * 60


def _config() -> SessionConfig:
    return SessionConfig(
        image="ghcr.io/mwest2020/ash-nazg-dosbox-x:0.0.0-scaffold",
        cpu_limit=1.0,
        memory_limit_mb=1024,
        mount_path="/mnt/files",
        streaming_protocol="kasmvnc",
        streaming_port=6901,
        idle_timeout_seconds=900,
        entrypoint_args=["dosbox-x", "/mnt/files/keen1.exe"],
    )


def _meta() -> FileMeta:
    return FileMeta(
        path="/Programs/keen1.exe",
        size_bytes=len(MZ_HEAD),
        extension="exe",
        magic_class="mz-dos",
    )


def _script(tmp_path: Path, body: str) -> str:
    path = tmp_path / "fake-engine"
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return str(path)


LISTENER = (
    'exec python3 -c "'
    "import os,socket,time;"
    "s=socket.socket();"
    "s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
    "s.bind((\\\"127.0.0.1\\\",int(os.environ[\\\"VNC_WEBSOCKET_PORT\\\"])));"
    "s.listen(1);"
    "time.sleep(300)"
    '"\n'
)


def _spawner(tmp_path: Path, script: str, **kwargs) -> InImageSpawner:
    reader = InMemoryFileReader({"/Programs/keen1.exe": MZ_HEAD})
    spawner = InImageSpawner(
        file_reader=reader,
        engine_script=script,
        sessions_root=tmp_path / "sessions",
        base_port=BASE_PORT,
        readiness_timeout_s=10.0,
        **kwargs,
    )

    # `kasmvncpasswd` lives in the runtime image, not on a test runner.
    # Everything about the secret except the tool call is still exercised.
    async def fake_password_file(path: Path, secret: str) -> None:
        path.write_text(f"session:{secret}\n")
        path.chmod(0o600)

    spawner._write_password_file = fake_password_file
    return spawner


@pytest.fixture
def strict_umask():
    """The umask the shim actually runs with under HaRP (its unix socket
    has to come out 0600). A session directory created under it would
    have no execute bit and be unusable, so the spawner must set modes
    explicitly."""
    previous = os.umask(0o177)
    yield
    os.umask(previous)


@pytest.mark.asyncio
async def test_spawn_returns_the_port_the_engine_listens_on(
    tmp_path: Path, strict_umask: None
) -> None:
    spawner = _spawner(tmp_path, _script(tmp_path, LISTENER))

    handle = await spawner.spawn(
        session_id="s-1", config=_config(), file_meta=_meta(), user_id="alice"
    )

    assert handle.port == BASE_PORT + 1
    assert handle.session_id == "s-1"
    assert handle.container_id.startswith("pid-")

    # The binary is downloaded into the session's own directory, not mounted.
    session_dir = tmp_path / "sessions" / "s-1"
    assert (session_dir / "keen1.exe").read_bytes() == MZ_HEAD
    assert session_dir.stat().st_mode & 0o777 == 0o700

    await spawner.terminate("s-1")
    assert not session_dir.exists()


@pytest.mark.asyncio
async def test_two_sessions_get_different_ports_and_displays(tmp_path: Path) -> None:
    spawner = _spawner(tmp_path, _script(tmp_path, LISTENER))

    first = await spawner.spawn(
        session_id="s-1", config=_config(), file_meta=_meta(), user_id="alice"
    )
    second = await spawner.spawn(
        session_id="s-2", config=_config(), file_meta=_meta(), user_id="bob"
    )

    assert first.port != second.port
    await spawner.terminate_all()


@pytest.mark.asyncio
async def test_engine_that_dies_reports_its_own_output(tmp_path: Path) -> None:
    spawner = _spawner(
        tmp_path, _script(tmp_path, 'echo "dosbox-x: no display\\n" >&2\nexit 3\n')
    )

    with pytest.raises(RuntimeError, match="exited with code 3"):
        await spawner.spawn(
            session_id="s-1", config=_config(), file_meta=_meta(), user_id="alice"
        )
    # A failed spawn frees its slot and leaves nothing behind.
    assert not (tmp_path / "sessions" / "s-1").exists()


@pytest.mark.asyncio
async def test_session_slots_are_capped(tmp_path: Path) -> None:
    spawner = _spawner(tmp_path, _script(tmp_path, LISTENER), max_sessions=1)
    await spawner.spawn(
        session_id="s-1", config=_config(), file_meta=_meta(), user_id="alice"
    )

    with pytest.raises(RuntimeError, match="session slots are in use"):
        await spawner.spawn(
            session_id="s-2", config=_config(), file_meta=_meta(), user_id="bob"
        )

    await spawner.terminate_all()


@pytest.mark.asyncio
async def test_preflight_names_what_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawner = _spawner(tmp_path, _script(tmp_path, LISTENER))
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    ok, message = await spawner.preflight()

    assert ok is False
    assert "dosbox-x" in message and "kasmvncserver" in message


@pytest.mark.asyncio
async def test_preflight_ok_when_everything_is_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawner = _spawner(tmp_path, _script(tmp_path, LISTENER))
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    ok, message = await spawner.preflight()

    assert ok is True
    assert "session slots free" in message


@pytest.mark.asyncio
async def test_session_environment_excludes_the_app_secret(tmp_path: Path) -> None:
    """Hygiene, not a boundary — but the shim's secret has no business
    being handed to an emulator process."""
    dump = 'env > "$XSTARTUP_PATH.env"\n' + LISTENER
    spawner = _spawner(tmp_path, _script(tmp_path, dump))
    os.environ["APP_SECRET"] = "super-secret-value"
    try:
        await spawner.spawn(
            session_id="s-1", config=_config(), file_meta=_meta(), user_id="alice"
        )
        env_dump = (tmp_path / "sessions" / "s-1" / "xstartup.env").read_text()
    finally:
        os.environ.pop("APP_SECRET", None)
        await spawner.terminate_all()

    assert "super-secret-value" not in env_dump
    assert "FILE_PATH=" in env_dump


@pytest.mark.asyncio
async def test_each_session_gets_its_own_credentials(tmp_path: Path) -> None:
    """A password baked into the image is the same on every install and
    survives redeployment; these are per session and die with it."""
    spawner = _spawner(tmp_path, _script(tmp_path, LISTENER))

    await spawner.spawn(
        session_id="s-1", config=_config(), file_meta=_meta(), user_id="alice"
    )
    await spawner.spawn(
        session_id="s-2", config=_config(), file_meta=_meta(), user_id="bob"
    )

    first = spawner.credentials_for("s-1")
    second = spawner.credentials_for("s-2")
    assert first is not None and second is not None
    assert first[1] != second[1]
    assert len(first[1]) >= 20

    password_file = tmp_path / "sessions" / "s-1" / "kasmpasswd"
    assert password_file.stat().st_mode & 0o777 == 0o600

    await spawner.terminate("s-1")
    # Gone with the session: no credential outlives what it protected.
    assert spawner.credentials_for("s-1") is None
    assert not password_file.exists()

    await spawner.terminate_all()


@pytest.mark.asyncio
async def test_port_and_credentials_are_unknown_for_unknown_sessions(
    tmp_path: Path,
) -> None:
    spawner = _spawner(tmp_path, _script(tmp_path, LISTENER))

    assert spawner.port_for("nooit-bestaan") is None
    assert spawner.credentials_for("nooit-bestaan") is None


@pytest.mark.asyncio
async def test_terminate_takes_the_whole_process_tree(tmp_path: Path) -> None:
    """`kasmvncserver` is a launcher: it starts Xvnc and returns, and Xvnc
    starts the emulator. Signalling only the child left both alive; the
    next session then found its port already open, attached to the
    previous session's server, and answered 401 with the wrong
    credentials. So termination has to take the group."""
    marker = tmp_path / "grandchild-alive"
    # The child spawns a grandchild that outlives it and keeps a file
    # locked open, then the child itself exits — exactly the shape that
    # used to survive.
    script = _script(
        tmp_path,
        f'python3 -c "'
        f"import os,socket,time,sys;"
        f"s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
        f"s.bind(('127.0.0.1',int(os.environ['VNC_WEBSOCKET_PORT'])));s.listen(1);"
        f"open('{marker}','w').write(str(os.getpid()));"
        f"time.sleep(300)"
        f'" &\nwait\n',
    )
    spawner = _spawner(tmp_path, script)

    await spawner.spawn(
        session_id="s-1", config=_config(), file_meta=_meta(), user_id="alice"
    )
    grandchild = int(marker.read_text())
    os.kill(grandchild, 0)  # raises if it is not running

    await spawner.terminate("s-1")

    # Give the signal a moment to land, then insist it is gone.
    for _ in range(20):
        try:
            os.kill(grandchild, 0)
        except OSError:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail("the grandchild survived terminate()")
