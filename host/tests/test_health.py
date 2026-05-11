"""Smoke tests for the host scaffold endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ash_nazg.main import app


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "ash_nazg"


def test_heartbeat_returns_plain_ok() -> None:
    client = TestClient(app)
    response = client.get("/heartbeat")

    assert response.status_code == 200
    assert response.text == "ok"


def test_selftest_returns_canonical_skipped_shape() -> None:
    """Lock the self-test JSON shape so the wiring change can only
    swap values, never the schema. Per `nextcloud-distribution` spec
    requirement *Self-check passes on healthy install*.
    """
    client = TestClient(app)
    response = client.post("/selftest")

    assert response.status_code == 200
    body = response.json()

    assert body["overall"] == "skipped"
    assert isinstance(body["checks"], list)

    expected_ids = [
        "host-health",
        "engines-registered",
        "deploy-daemon-spawn",
        "audit-log-write",
    ]
    actual_ids = [check["id"] for check in body["checks"]]
    assert actual_ids == expected_ids, (
        "self-test check IDs / order are normative — see "
        "nextcloud-distribution/spec.md"
    )

    for check in body["checks"]:
        assert check["status"] == "skipped"
        assert check["message"] == "not yet implemented"


def test_admin_settings_renders_html_shell() -> None:
    """The shell must contain the initial-state input, the mount div,
    and either a bundle script tag or the 'not built yet' warning.
    """
    client = TestClient(app)
    response = client.get("/admin/settings")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

    body = response.text
    assert 'id="initial-state-ash_nazg-config"' in body
    assert 'id="ash-nazg-admin-settings"' in body
    # Either the bundle is loaded or the build-warning is shown.
    assert ("/static/js/admin-settings-" in body) or (
        "Frontend bundle not built yet" in body
    )
