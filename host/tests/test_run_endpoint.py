"""Integration tests for /run wired through the FastAPI app.

Drives the FastAPI TestClient with a Dispatcher built from the same
in-memory adapters production uses in `ASH_NAZG_MODE=demo`, with a
hand-loaded registry that contains the real dosbox-x engine. The
spawner is the StubSpawner so no docker socket is needed.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ash_nazg.dispatch import ActiveSessionTracker, Dispatcher
from ash_nazg.engines.dosbox_x import DosboxXEngine
from ash_nazg.engines.registry import EngineRegistry, RegisteredEngine
from ash_nazg.io_adapters import InMemoryAuditLogger, InMemoryFileReader
from ash_nazg.main import app
from ash_nazg.request_context import AUTH_HEADER
from ash_nazg.spawners import StubSpawner


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _admin_header(user_id: str = "alice") -> dict[str, str]:
    return {AUTH_HEADER: base64.b64encode(f"{user_id}:secret".encode()).decode()}


def _build_dispatcher(head: bytes) -> tuple[Dispatcher, InMemoryAuditLogger]:
    reader = InMemoryFileReader({"/Programs/keen1.exe": head})
    audit = InMemoryAuditLogger()
    dispatcher = Dispatcher(
        registry=EngineRegistry(
            [RegisteredEngine(engine=DosboxXEngine(), enabled=True)]
        ),
        file_reader=reader,
        spawner=StubSpawner(host="127.0.0.1", port=16901),
        audit=audit,
        active_sessions=ActiveSessionTracker(),
    )
    return dispatcher, audit


def _mz_dos_head() -> bytes:
    """MZ header without PE signature → mz-dos."""
    head = bytearray(2 + 60)
    head[0:2] = b"MZ"
    return bytes(head)


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["app"] == "ash_nazg"


def test_run_unknown_path_returns_400(client: TestClient) -> None:
    """No file in the reader → empty head → unknown → 400."""
    # Replace dispatcher on app state so the test controls inputs
    dispatcher, _ = _build_dispatcher(head=b"")
    app.state.dispatcher = dispatcher
    resp = client.post(
        "/run",
        headers=_admin_header(),
        json={"path": "/Programs/keen1.exe"},
    )
    assert resp.status_code == 400


def test_run_keen_path_returns_demo_endpoint(client: TestClient) -> None:
    dispatcher, audit = _build_dispatcher(head=_mz_dos_head())
    app.state.dispatcher = dispatcher
    resp = client.post(
        "/run",
        headers=_admin_header(),
        json={"path": "/Programs/keen1.exe"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["host"] == "127.0.0.1"
    assert body["port"] == 16901
    assert "session_id" in body
    assert len(audit.entries) == 1
    assert audit.entries[0]["outcome"] == "dispatched"
    assert audit.entries[0]["selected_engine"] == "dosbox-x"


def test_run_anonymous_blocked_with_403(client: TestClient) -> None:
    """Empty AUTHORIZATION-APP-API header → no user → 403."""
    dispatcher, _ = _build_dispatcher(head=_mz_dos_head())
    app.state.dispatcher = dispatcher
    resp = client.post("/run", json={"path": "/Programs/keen1.exe"})
    assert resp.status_code == 403


def test_run_missing_body_returns_422(client: TestClient) -> None:
    """FastAPI auto-422 for missing `path`."""
    dispatcher, _ = _build_dispatcher(head=_mz_dos_head())
    app.state.dispatcher = dispatcher
    resp = client.post("/run", headers=_admin_header(), json={})
    assert resp.status_code == 422
