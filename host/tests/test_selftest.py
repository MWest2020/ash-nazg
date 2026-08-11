"""Self-test endpoint tests (wire-dosbox-engine).

The four canonical checks return real verdicts against a dispatcher wired
on app.state — a healthy install is all-ok; a broken one fails the
specific check with a concrete message (never vague), and the JSON shape
is unchanged from the scaffold.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ash_nazg.dispatch import ActiveSessionTracker, Dispatcher, SessionHandle
from ash_nazg.engines.dosbox_x import DosboxXEngine
from ash_nazg.engines.registry import EngineRegistry, RegisteredEngine
from ash_nazg.io_adapters import InMemoryAuditLogger, InMemoryFileReader
from ash_nazg.main import app
from ash_nazg.selftest import CHECK_IDS
from ash_nazg.spawners import StubSpawner


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _dispatcher(*, engine_enabled: bool = True, audit=None, spawner=None) -> Dispatcher:
    return Dispatcher(
        registry=EngineRegistry(
            [RegisteredEngine(engine=DosboxXEngine(), enabled=engine_enabled)]
        ),
        file_reader=InMemoryFileReader({}),
        spawner=spawner or StubSpawner(host="127.0.0.1", port=16901),
        audit=audit or InMemoryAuditLogger(),
        active_sessions=ActiveSessionTracker(),
    )


def _by_id(body: dict) -> dict[str, dict]:
    return {c["id"]: c for c in body["checks"]}


def test_selftest_schema_is_stable(client: TestClient) -> None:
    app.state.dispatcher = _dispatcher()
    body = client.post("/selftest").json()
    assert [c["id"] for c in body["checks"]] == list(CHECK_IDS)
    assert set(body) == {"checks", "overall"}
    for c in body["checks"]:
        assert set(c) == {"id", "status", "message"}


def test_selftest_healthy_install_all_ok(client: TestClient) -> None:
    app.state.dispatcher = _dispatcher()
    body = client.post("/selftest").json()
    assert body["overall"] == "ok"
    checks = _by_id(body)
    assert all(c["status"] == "ok" for c in checks.values())
    assert "dosbox-x" in checks["engines-registered"]["message"]
    assert "audit log accepted" in checks["audit-log-write"]["message"]


def test_selftest_no_enabled_engines_fails_with_reason(client: TestClient) -> None:
    app.state.dispatcher = _dispatcher(engine_enabled=False)
    body = client.post("/selftest").json()
    assert body["overall"] == "fail"
    check = _by_id(body)["engines-registered"]
    assert check["status"] == "fail"
    assert "0 enabled" in check["message"]  # concrete, not vague


def test_selftest_audit_failure_is_reported(client: TestClient) -> None:
    class BrokenAudit:
        async def log(self, **fields: object) -> None:
            raise RuntimeError("audit backend down")

    app.state.dispatcher = _dispatcher(audit=BrokenAudit())
    body = client.post("/selftest").json()
    assert body["overall"] == "fail"
    check = _by_id(body)["audit-log-write"]
    assert check["status"] == "fail"
    assert "audit backend down" in check["message"]


def test_selftest_spawner_preflight_failure_is_reported(client: TestClient) -> None:
    class DownSpawner:
        async def preflight(self) -> tuple[bool, str]:
            return False, "docker daemon unreachable (exit 1): permission denied"

        async def spawn(self, **kwargs: object) -> SessionHandle:  # pragma: no cover
            raise AssertionError("spawn must not be called by selftest")

    app.state.dispatcher = _dispatcher(spawner=DownSpawner())
    body = client.post("/selftest").json()
    assert body["overall"] == "fail"
    check = _by_id(body)["deploy-daemon-spawn"]
    assert check["status"] == "fail"
    assert "permission denied" in check["message"]


def test_selftest_stub_spawner_preflight_ok(client: TestClient) -> None:
    app.state.dispatcher = _dispatcher()
    body = client.post("/selftest").json()
    check = _by_id(body)["deploy-daemon-spawn"]
    assert check["status"] == "ok"
    assert "stub spawner ready" in check["message"]
