"""Contract test for the OCS audit logger.

An ExApp has no Nextcloud password: basic auth on an OCS endpoint
returns 401 "Unauthorised" (997). The live NC 32 / AppAPI 5 stack only
accepts the AUTHORIZATION-APP-API header, and only on AppAPI's own log
route — `apps/admin_audit/api/v1/event` does not exist (404). Both of
those were live-verified, so they are pinned here.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from ash_nazg.io_adapters import OcsAuditLogger


@pytest.mark.asyncio
async def test_log_posts_to_appapi_with_app_api_auth() -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ocs": {"meta": {"status": "ok"}}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    logger = OcsAuditLogger(
        base_url="http://nextcloud/",
        user_id="admin",
        token="s3cret",
        app_version="1.2.3",
        client=client,
    )

    await logger.log(outcome="ash_nazg.selftest", path="/keen1.exe")
    await client.aclose()

    assert seen["url"] == "http://nextcloud/ocs/v2.php/apps/app_api/api/v1/log"
    headers = seen["headers"]
    assert headers["ex-app-id"] == "ash_nazg"
    assert headers["ex-app-version"] == "1.2.3"
    # Empty user id = system context, secret in the AppAPI header.
    assert headers["authorization-app-api"] == base64.b64encode(
        b":s3cret"
    ).decode()
    assert "authorization" not in headers

    body = seen["body"]
    entry = json.loads(body["message"])
    assert entry["event"] == "ash_nazg.selftest"
    assert entry["data"] == {"path": "/keen1.exe"}


@pytest.mark.asyncio
async def test_log_raises_with_the_real_status_on_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorised")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    logger = OcsAuditLogger(
        base_url="http://nextcloud", user_id="admin", token="s3cret", client=client
    )

    with pytest.raises(RuntimeError, match="401"):
        await logger.log(outcome="ash_nazg.execution")
    await client.aclose()
