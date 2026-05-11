"""Tests for `ash_nazg.dispatch.Dispatcher`.

Covers the dispatch / detection / sandbox / files-integration spec
scenarios that constrain dispatcher behaviour:
- PE32 file dispatches to dosbox-x (happy path)
- ELF file refused with 415
- Unknown (not recognised) refused with 400
- Non-admin blocked with 403
- Oversize binary refused with 413
- Concurrent same-file same-user refused with 409
- Audit log entry per dispatch (success and failure)
- Spawn failure surfaced as 500 with audit entry
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from typing import Any

import pytest

from ash_nazg.dispatch import (
    ActiveSessionTracker,
    AuditLogger,
    Dispatcher,
    DispatchError,
    DispatchOk,
    FileReader,
    SessionHandle,
    SessionSpawner,
)
from ash_nazg.engines import FileMeta, SessionConfig
from ash_nazg.engines.dosbox_x import DosboxXEngine
from ash_nazg.engines.registry import EngineRegistry, RegisteredEngine


# --- Fakes ----------------------------------------------------------------


class _FakeReader(FileReader):
    def __init__(self, head: bytes, size: int | None = None) -> None:
        self._head = head
        self._size = size if size is not None else len(head)

    async def read_head(self, files_path: str, byte_count: int) -> bytes:
        return self._head[:byte_count]

    async def get_size(self, files_path: str) -> int:
        return self._size


class _FakeSpawner(SessionSpawner):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    async def spawn(
        self,
        *,
        session_id: str,
        config: SessionConfig,
        file_meta: FileMeta,
        user_id: str,
    ) -> SessionHandle:
        self.calls.append(
            {
                "session_id": session_id,
                "image": config.image,
                "files_path": file_meta.path,
                "user_id": user_id,
            }
        )
        if self.fail:
            raise RuntimeError("simulated container spawn failure")
        return SessionHandle(
            session_id=session_id,
            container_id="container-" + session_id[:8],
            host="engine.localhost",
            port=config.streaming_port,
        )


class _FakeAudit(AuditLogger):
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def log(self, **fields: Any) -> None:
        self.entries.append(fields)


# --- Fixtures -------------------------------------------------------------


def _dosbox_registry() -> EngineRegistry:
    return EngineRegistry([RegisteredEngine(engine=DosboxXEngine(), enabled=True)])


def _disabled_dosbox_registry() -> EngineRegistry:
    return EngineRegistry([RegisteredEngine(engine=DosboxXEngine(), enabled=False)])


def _make_mz_dos_head(extra_padding: int = 60) -> bytes:
    """Real-shape mz-dos head (no PE signature)."""
    head = bytearray(2 + extra_padding)
    head[0:2] = b"MZ"
    return bytes(head)


def _make_pe32_head() -> bytes:
    pe_offset = 0x80
    head = bytearray(512)
    head[0:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, pe_offset)
    head[pe_offset : pe_offset + 4] = b"PE\x00\x00"
    struct.pack_into("<H", head, pe_offset + 24, 0x010B)
    return bytes(head)


def _dispatcher(
    reader: _FakeReader,
    *,
    registry: EngineRegistry | None = None,
    spawner: _FakeSpawner | None = None,
    audit: _FakeAudit | None = None,
    max_file_bytes: int = 100 * 1024 * 1024,
) -> tuple[Dispatcher, _FakeSpawner, _FakeAudit]:
    spawner = spawner or _FakeSpawner()
    audit = audit or _FakeAudit()
    dispatcher = Dispatcher(
        registry=registry or _dosbox_registry(),
        file_reader=reader,
        spawner=spawner,
        audit=audit,
        active_sessions=ActiveSessionTracker(),
        max_file_bytes=max_file_bytes,
    )
    return dispatcher, spawner, audit


def _audit_outcomes(entries: Sequence[dict[str, Any]]) -> list[str]:
    return [e["outcome"] for e in entries]


# --- Happy path -----------------------------------------------------------


@pytest.mark.asyncio
async def test_pe32_dispatches_to_dosbox() -> None:
    reader = _FakeReader(_make_pe32_head())
    dispatcher, spawner, audit = _dispatcher(reader)
    result = await dispatcher.dispatch(
        files_path="/Programs/app.exe", user_id="alice", is_admin=True
    )
    assert isinstance(result, DispatchOk)
    assert result.port == 6901
    assert len(spawner.calls) == 1
    assert spawner.calls[0]["user_id"] == "alice"
    # one "dispatched" audit entry with the expected fields
    assert _audit_outcomes(audit.entries) == ["dispatched"]
    entry = audit.entries[0]
    assert entry["selected_engine"] == "dosbox-x"
    assert entry["detected_type"] == "pe32"
    assert entry["files_path"] == "/Programs/app.exe"
    assert "session_id" in entry
    assert "file_sha256" in entry


@pytest.mark.asyncio
async def test_mz_dos_dispatches_to_dosbox() -> None:
    """Keen-shaped binary (MZ without PE) → mz-dos → dosbox-x."""
    reader = _FakeReader(_make_mz_dos_head())
    dispatcher, spawner, _ = _dispatcher(reader)
    result = await dispatcher.dispatch(
        files_path="/Programs/keen1.exe", user_id="alice", is_admin=True
    )
    assert isinstance(result, DispatchOk)
    assert spawner.calls[0]["files_path"] == "/Programs/keen1.exe"


# --- Negative cases -------------------------------------------------------


@pytest.mark.asyncio
async def test_elf_refused_with_415() -> None:
    reader = _FakeReader(b"\x7fELF" + b"\x00" * 60)
    dispatcher, spawner, audit = _dispatcher(reader)
    result = await dispatcher.dispatch(
        files_path="/Programs/binary", user_id="alice", is_admin=True
    )
    assert isinstance(result, DispatchError)
    assert result.status_code == 415
    assert "elf" in result.message
    assert spawner.calls == []
    assert _audit_outcomes(audit.entries) == ["refused"]
    assert audit.entries[0]["detected_type"] == "elf"
    assert audit.entries[0]["reason"] == "no enabled engine handles this format"


@pytest.mark.asyncio
async def test_unrecognised_returns_400() -> None:
    reader = _FakeReader(b"#!/usr/bin/env python\n\nprint('hi')\n")
    dispatcher, spawner, audit = _dispatcher(reader)
    result = await dispatcher.dispatch(
        files_path="/data/script.py", user_id="alice", is_admin=True
    )
    assert isinstance(result, DispatchError)
    assert result.status_code == 400
    assert spawner.calls == []
    assert audit.entries[0]["reason"] == "not a recognized executable format"


@pytest.mark.asyncio
async def test_non_admin_blocked_with_403() -> None:
    reader = _FakeReader(_make_pe32_head())
    dispatcher, spawner, audit = _dispatcher(reader)
    result = await dispatcher.dispatch(
        files_path="/Programs/app.exe", user_id="bob", is_admin=False
    )
    assert isinstance(result, DispatchError)
    assert result.status_code == 403
    assert spawner.calls == []
    assert _audit_outcomes(audit.entries) == ["forbidden"]


@pytest.mark.asyncio
async def test_oversize_refused_with_413() -> None:
    reader = _FakeReader(_make_pe32_head(), size=200 * 1024 * 1024)
    dispatcher, spawner, audit = _dispatcher(reader, max_file_bytes=100 * 1024 * 1024)
    result = await dispatcher.dispatch(
        files_path="/Programs/big.exe", user_id="alice", is_admin=True
    )
    assert isinstance(result, DispatchError)
    assert result.status_code == 413
    assert spawner.calls == []
    assert audit.entries[0]["reason"] == "oversize"
    assert audit.entries[0]["file_size"] == 200 * 1024 * 1024


@pytest.mark.asyncio
async def test_disabled_engine_is_skipped() -> None:
    reader = _FakeReader(_make_pe32_head())
    dispatcher, spawner, audit = _dispatcher(
        reader, registry=_disabled_dosbox_registry()
    )
    result = await dispatcher.dispatch(
        files_path="/Programs/app.exe", user_id="alice", is_admin=True
    )
    assert isinstance(result, DispatchError)
    assert result.status_code == 415  # spec: 'no enabled engine handles this format'
    assert spawner.calls == []


@pytest.mark.asyncio
async def test_concurrent_same_user_same_file_409() -> None:
    reader = _FakeReader(_make_pe32_head())
    dispatcher, spawner, audit = _dispatcher(reader)
    first = await dispatcher.dispatch(
        files_path="/Programs/app.exe", user_id="alice", is_admin=True
    )
    assert isinstance(first, DispatchOk)
    second = await dispatcher.dispatch(
        files_path="/Programs/app.exe", user_id="alice", is_admin=True
    )
    assert isinstance(second, DispatchError)
    assert second.status_code == 409
    assert len(spawner.calls) == 1
    assert _audit_outcomes(audit.entries) == ["dispatched", "refused"]


@pytest.mark.asyncio
async def test_concurrent_different_users_allowed() -> None:
    reader = _FakeReader(_make_pe32_head())
    dispatcher, spawner, _ = _dispatcher(reader)
    a = await dispatcher.dispatch(
        files_path="/shared/app.exe", user_id="alice", is_admin=True
    )
    b = await dispatcher.dispatch(
        files_path="/shared/app.exe", user_id="bob", is_admin=True
    )
    assert isinstance(a, DispatchOk)
    assert isinstance(b, DispatchOk)
    assert len(spawner.calls) == 2


@pytest.mark.asyncio
async def test_spawn_failure_returns_500_and_releases_session() -> None:
    reader = _FakeReader(_make_pe32_head())
    spawner = _FakeSpawner(fail=True)
    dispatcher, _, audit = _dispatcher(reader, spawner=spawner)
    result = await dispatcher.dispatch(
        files_path="/Programs/app.exe", user_id="alice", is_admin=True
    )
    assert isinstance(result, DispatchError)
    assert result.status_code == 500
    assert "spawn" in result.message.lower()
    # active session must be released so the user can retry
    retry = await dispatcher.dispatch(
        files_path="/Programs/app.exe", user_id="alice", is_admin=True
    )
    # second call also fails the same way, but it's not 409
    assert isinstance(retry, DispatchError)
    assert retry.status_code == 500


@pytest.mark.asyncio
async def test_audit_writes_always_happen_even_when_audit_raises() -> None:
    """audit failures MUST NOT break dispatch."""

    class _BrokenAudit(AuditLogger):
        async def log(self, **fields: Any) -> None:
            raise RuntimeError("simulated OCS API down")

    reader = _FakeReader(_make_pe32_head())
    dispatcher, _, _ = _dispatcher(reader, audit=_BrokenAudit())
    result = await dispatcher.dispatch(
        files_path="/Programs/app.exe", user_id="alice", is_admin=True
    )
    assert isinstance(result, DispatchOk)
