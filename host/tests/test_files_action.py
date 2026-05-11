"""Tests for the FileActionsMenu callback endpoints.

Covers:
- /files-action: AppAPI payload → dispatcher → redirect_handler shape
- /files-action: dispatch errors propagate to AppAPI as 4xx
- /session-redirect: HTML shell + JS bounce
- AppAPI client: registration POST shape + headers (mock httpx)
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from ash_nazg.appapi import AppApiConfig
from ash_nazg.appapi_client import (
    FILE_ACTIONS_MENU_PATH,
    AppApiClient,
    FileActionsMenuEntry,
)
from ash_nazg.dispatch import ActiveSessionTracker, Dispatcher
from ash_nazg.engines.dosbox_x import DosboxXEngine
from ash_nazg.engines.registry import EngineRegistry, RegisteredEngine
from ash_nazg.files_action import _files_path, _safe_redirect_url
from ash_nazg.io_adapters import InMemoryAuditLogger, InMemoryFileReader
from ash_nazg.main import app
from ash_nazg.spawners import StubSpawner

# --- Helpers --------------------------------------------------------------


def _mz_dos_head() -> bytes:
    return b"MZ" + b"\x00" * 60


@pytest.fixture
def client_with_dispatcher() -> Iterator[TestClient]:
    reader = InMemoryFileReader({"/Programs/keen1.exe": _mz_dos_head()})
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
    with TestClient(app) as c:
        app.state.dispatcher = dispatcher
        yield c


# --- /files-action --------------------------------------------------------


def test_files_path_joins_directory_and_name() -> None:
    assert _files_path("Programs", "keen1.exe") == "/Programs/keen1.exe"
    assert _files_path("/Programs/", "keen1.exe") == "/Programs/keen1.exe"
    assert _files_path("", "keen1.exe") == "/keen1.exe"
    assert _files_path("Folder/sub", "file.bin") == "/Folder/sub/file.bin"


def test_files_action_returns_redirect_handler(
    client_with_dispatcher: TestClient,
) -> None:
    resp = client_with_dispatcher.post(
        "/files-action",
        json={
            "fileId": 42,
            "name": "keen1.exe",
            "directory": "Programs",
            "userId": "alice",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "redirect_handler" in body
    assert body["redirect_handler"].startswith("/session-redirect?url=")
    assert "16901" in body["redirect_handler"]  # encoded engine URL contains port
    assert "session_id" in body


def test_files_action_unknown_file_returns_4xx(
    client_with_dispatcher: TestClient,
) -> None:
    """File not in the in-memory reader → empty head → unknown → 400."""
    resp = client_with_dispatcher.post(
        "/files-action",
        json={
            "fileId": 99,
            "name": "missing.exe",
            "directory": "",
            "userId": "alice",
        },
    )
    assert resp.status_code == 400


def test_files_action_dispatcher_not_ready_returns_503() -> None:
    # Manually clear dispatcher to simulate startup race
    with TestClient(app) as c:
        app.state.dispatcher = None
        resp = c.post(
            "/files-action",
            json={"fileId": 1, "name": "f.exe", "directory": "", "userId": "alice"},
        )
        assert resp.status_code == 503


# --- /session-redirect ----------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:16901/vnc.html",
        "http://engine.local/vnc.html",
    ],
)
def test_safe_redirect_url_accepts_http_schemes(url: str) -> None:
    assert _safe_redirect_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html;base64,PHN2Zz4=",
        "file:///etc/passwd",
        "",
        "no-scheme.com/path",
    ],
)
def test_safe_redirect_url_rejects_dangerous(url: str) -> None:
    assert _safe_redirect_url(url) is False


def test_session_redirect_renders_html_with_url_search(
    client_with_dispatcher: TestClient,
) -> None:
    resp = client_with_dispatcher.get(
        "/session-redirect?url=https%3A%2F%2F127.0.0.1%3A16901%2Fvnc.html"
    )
    assert resp.status_code == 200
    body = resp.text
    assert "<!DOCTYPE html>" in body
    assert "URLSearchParams" in body  # JS reads url from query string
    assert "Ash Nazg" in body


# --- AppApiClient --------------------------------------------------------


def _make_config() -> AppApiConfig:
    return AppApiConfig(
        app_id="ash_nazg",
        app_version="0.0.0",
        app_secret="testsecret",
        app_host="0.0.0.0",  # noqa: S104 — AppAPI 5.x ExApp listen address
        app_port=8080,
        nc_url="http://nextcloud.local",
        aa_version="5.0.0",
    )


@pytest.mark.asyncio
async def test_appapi_client_register_file_action_post_shape() -> None:
    captured: dict[str, Any] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = request.read().decode()
        return httpx.Response(200, json={"ocs": {"meta": {"status": "ok"}}})

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = AppApiClient(_make_config(), client=http)
        await client.register_file_action(
            FileActionsMenuEntry(
                name="ash_nazg.run",
                display_name="Run with Ash Nazg",
                action_handler="/files-action",
                mime="file",
                permissions=1,
                order=0,
            )
        )

    assert captured["url"].endswith(FILE_ACTIONS_MENU_PATH)
    assert "ex-app-id" in (k.lower() for k in captured["headers"])
    assert "authorization-app-api" in (k.lower() for k in captured["headers"])
    assert "ocs-apirequest" in (k.lower() for k in captured["headers"])
    import json as _json
    body = _json.loads(captured["json"])
    assert body["name"] == "ash_nazg.run"
    assert body["actionHandler"] == "/files-action"
    assert body["displayName"] == "Run with Ash Nazg"
    assert body["mime"] == "file"
    assert body["permissions"] == 1
    assert body["order"] == 0


@pytest.mark.asyncio
async def test_appapi_client_register_file_action_raises_on_4xx() -> None:
    def _handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = AppApiClient(_make_config(), client=http)
        with pytest.raises(RuntimeError, match="403"):
            await client.register_file_action(
                FileActionsMenuEntry(
                    name="x", display_name="x", action_handler="/x"
                )
            )
