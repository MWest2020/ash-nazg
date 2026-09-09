"""Tests for the AppAPI lifecycle endpoints.

`POST /init` and `PUT /enabled` are what AppAPI calls after HaRP has
spawned the container. Without the init report `app:register
--wait-finish` blocks forever, so these two are as load-bearing as
/heartbeat — and just as untestable from a unit test if we let them
talk to a real AppAPI. Both are driven here with the client patched.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ash_nazg import main
from ash_nazg.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_init_returns_empty_object_and_reports_progress(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    reported: list[int] = []

    async def fake_report() -> None:
        reported.append(100)

    monkeypatch.setattr(main, "_report_init_done", fake_report)

    resp = client.post("/init")

    assert resp.status_code == 200
    assert resp.json() == {}
    # The background task runs once the response is on the wire.
    assert reported == [100]


def test_enabled_true_registers_the_files_action(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def fake_register() -> None:
        calls.append("registered")

    monkeypatch.setattr(main, "_register_files_action_menu", fake_register)

    resp = client.put("/enabled", params={"enabled": 1})

    assert resp.status_code == 200
    # An empty error is AppAPI's "accepted".
    assert resp.json() == {"error": ""}
    assert calls == ["registered"]


def test_enabled_false_does_not_register(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def fake_register() -> None:
        calls.append("registered")

    monkeypatch.setattr(main, "_register_files_action_menu", fake_register)

    resp = client.put("/enabled", params={"enabled": 0})

    assert resp.status_code == 200
    assert resp.json() == {"error": ""}
    assert calls == []
