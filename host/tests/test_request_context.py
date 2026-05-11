"""Tests for `ash_nazg.request_context`."""

from __future__ import annotations

import base64

import pytest
from fastapi import Request

from ash_nazg.request_context import AUTH_HEADER, extract_user


def _request(headers: dict[str, str]) -> Request:
    """Build a FastAPI Request with the given headers (no body)."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/run",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope=scope)


def _auth(user: str, secret: str = "s") -> str:  # noqa: S107 — test fixture, not a real secret
    return base64.b64encode(f"{user}:{secret}".encode()).decode()


def test_extract_user_admin_route_with_valid_header() -> None:
    req = _request({AUTH_HEADER: _auth("alice")})
    u = extract_user(req, admin_route=True)
    assert u.user_id == "alice"
    assert u.is_admin is True


def test_extract_user_non_admin_route_returns_is_admin_false() -> None:
    req = _request({AUTH_HEADER: _auth("alice")})
    u = extract_user(req, admin_route=False)
    assert u.user_id == "alice"
    assert u.is_admin is False


def test_extract_user_anonymous_empty_user_id() -> None:
    """user_id empty (PUBLIC route) → is_admin=False regardless of route."""
    req = _request({AUTH_HEADER: _auth("")})
    u = extract_user(req, admin_route=True)
    assert u.user_id == ""
    assert u.is_admin is False


def test_extract_user_missing_header() -> None:
    req = _request({})
    u = extract_user(req, admin_route=True)
    assert u.user_id == ""
    assert u.is_admin is False


def test_extract_user_malformed_base64() -> None:
    req = _request({AUTH_HEADER: "not-base64!!!"})
    u = extract_user(req, admin_route=True)
    assert u.user_id == ""
    assert u.is_admin is False


@pytest.mark.parametrize("payload", ["plain-no-colon", ""])
def test_extract_user_unexpected_payload(payload: str) -> None:
    req = _request({AUTH_HEADER: base64.b64encode(payload.encode()).decode()})
    u = extract_user(req, admin_route=True)
    assert u.user_id == ""
    assert u.is_admin is False
