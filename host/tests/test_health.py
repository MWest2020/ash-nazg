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


def test_heartbeat_returns_status_ok_json() -> None:
    """AppAPI parses this body; a bare `ok` string reads as a failed
    heartbeat and the ExApp never finishes registering."""
    client = TestClient(app)
    response = client.get("/heartbeat")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_selftest_returns_canonical_shape() -> None:
    """Lock the self-test JSON shape (ids + order normative) so the schema
    stays stable for the frontend. Per `nextcloud-distribution` spec
    requirement *Self-check passes on healthy install*. Values are now real
    (wire-dosbox-engine); see test_selftest.py for the per-check verdicts.
    """
    client = TestClient(app)
    response = client.post("/selftest")

    assert response.status_code == 200
    body = response.json()

    assert body["overall"] in {"ok", "fail", "skipped"}
    assert isinstance(body["checks"], list)

    expected_ids = [
        "host-health",
        "engines-registered",
        "engine-runtime",
        "audit-log-write",
    ]
    actual_ids = [check["id"] for check in body["checks"]]
    assert actual_ids == expected_ids, (
        "self-test check IDs / order are normative — see "
        "nextcloud-distribution/spec.md"
    )

    for check in body["checks"]:
        assert check["status"] in {"ok", "fail", "skipped"}
        assert isinstance(check["message"], str)


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


def test_pages_reference_their_assets_relative_to_the_proxy_prefix() -> None:
    """The app is reached through a proxy prefix it cannot see. An
    absolute /static/... URL resolves against Nextcloud's root and 404s,
    which leaves the page rendered but the Vue app never mounted."""
    client = TestClient(app)

    for path in ("/admin/settings", "/sessions/abc-123"):
        body = client.get(path).text
        assert 'src="/static/' not in body, path
        assert 'href="/static/' not in body, path
