"""Authorisation on the session stream.

The bytes-forwarding itself is proven against a real KasmVNC by the
level-3 verifier; what unit tests can pin down is who is let through.
A session id must not be a capability, and "not yours" must be
indistinguishable from "does not exist" — otherwise the endpoint is an
oracle for guessing session ids.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from ash_nazg.dispatch import ActiveSessionTracker
from ash_nazg.main import app
from ash_nazg.request_context import AUTH_HEADER
from ash_nazg.stream_proxy import _request_headers, _target

SESSION = "11111111-2222-3333-4444-555555555555"


class _FakeSpawner:
    def __init__(
        self,
        *,
        port: int | None = 6901,
        secret: str | None = "s3cret",  # noqa: S107 — a test double, not a credential
    ) -> None:
        self._port = port
        self._secret = secret

    def port_for(self, session_id: str) -> int | None:
        return self._port if session_id == SESSION else None

    def credentials_for(self, session_id: str) -> tuple[str, str] | None:
        if session_id != SESSION or self._secret is None:
            return None
        return ("session", self._secret)


class _FakeDispatcher:
    def __init__(self, spawner: _FakeSpawner, owner: str = "alice") -> None:
        self.spawner = spawner
        self.active = ActiveSessionTracker()
        self.active.claim(owner, "/Programs/keen1.exe", SESSION)
        self.activity: list[str] = []

    def note_activity(self, session_id: str) -> None:
        self.activity.append(session_id)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _as(user_id: str) -> dict[str, str]:
    return {AUTH_HEADER: base64.b64encode(f"{user_id}:secret".encode()).decode()}


def test_target_resolves_for_the_owner(client: TestClient) -> None:
    client.app.state.dispatcher = _FakeDispatcher(_FakeSpawner())

    target = _target(client.app, SESSION, "alice")

    assert target is not None
    port, authorization = target
    assert port == 6901
    assert base64.b64decode(authorization.removeprefix("Basic ")).decode() == "session:s3cret"


def test_stream_of_another_users_session_is_404(client: TestClient) -> None:
    client.app.state.dispatcher = _FakeDispatcher(_FakeSpawner(), owner="alice")

    response = client.get(f"/sessions/{SESSION}/stream/vnc.html", headers=_as("bob"))

    assert response.status_code == 404
    assert response.json()["error"] == "unknown_session"


def test_stream_of_an_unknown_session_is_404(client: TestClient) -> None:
    """Same answer as someone else's session, deliberately."""
    client.app.state.dispatcher = _FakeDispatcher(_FakeSpawner())

    response = client.get("/sessions/does-not-exist/stream/vnc.html", headers=_as("alice"))

    assert response.status_code == 404
    assert response.json()["error"] == "unknown_session"


def test_stream_without_an_identity_is_404(client: TestClient) -> None:
    client.app.state.dispatcher = _FakeDispatcher(_FakeSpawner())

    response = client.get(f"/sessions/{SESSION}/stream/vnc.html")

    assert response.status_code == 404


def test_stream_of_a_gone_session_is_404(client: TestClient) -> None:
    """The claim can outlive the process for a moment; no port, no stream."""
    client.app.state.dispatcher = _FakeDispatcher(_FakeSpawner(port=None))

    response = client.get(f"/sessions/{SESSION}/stream/vnc.html", headers=_as("alice"))

    assert response.status_code == 404


def test_websocket_is_refused_before_the_upgrade(client: TestClient) -> None:
    client.app.state.dispatcher = _FakeDispatcher(_FakeSpawner(), owner="alice")

    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect(
            f"/sessions/{SESSION}/stream/websockify", headers=_as("bob")
        ):
            pass

    # 4404: the websocket's way of saying 404, so "not yours" and "does
    # not exist" stay indistinguishable here too.
    assert caught.value.code == 4404


def test_caller_credentials_never_reach_the_engine() -> None:
    """Header names arrive lower-cased. Adding "Authorization" without
    removing "authorization" sends both, and the VNC server reads the
    caller's Nextcloud credentials first — a 401 with no obvious cause."""
    incoming = {
        "authorization": "Basic bmV4dGNsb3VkOnBhc3N3b3Jk",
        "cookie": "nc_session_id=abc",
        "authorization-app-api": "YWxpY2U6c2VjcmV0",
        "accept": "text/html",
    }

    forwarded = _request_headers(incoming, "Basic c2Vzc2lvbjpzM2NyZXQ=")

    assert [k for k in forwarded if k.lower() == "authorization"] == ["Authorization"]
    assert forwarded["Authorization"] == "Basic c2Vzc2lvbjpzM2NyZXQ="
    assert "cookie" not in {k.lower() for k in forwarded}
    assert "authorization-app-api" not in {k.lower() for k in forwarded}
    assert forwarded["accept"] == "text/html"
