"""AppAPI OCS client — registers ExApp UI integrations.

In AppAPI 5.x, ExApps register File Actions Menu entries (the right-click
menu items on Files) at runtime via the OCS endpoint
`POST /apps/app_api/api/v2/ui/files-actions-menu`. AppAPI persists
the registration and surfaces the menu item in NC's Files app. When a
user clicks it, AppAPI POSTs the file metadata to the ExApp's
`actionHandler` route; the ExApp responds with `{redirect_handler: ...}`
pointing to the page NC should navigate the user to (with `?fileIds=...`
appended).

Authentication: AppAPI accepts an `AUTHORIZATION-APP-API` header whose
value is `base64(user_id:app_secret)`. For system-context registration
the user_id is empty.

Reference:
- https://docs.nextcloud.com/server/latest/developer_manual/exapp_development/tech_details/api/fileactionsmenu.html
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass
from typing import Final

import httpx

from ash_nazg.appapi import AppApiConfig

logger = logging.getLogger(__name__)

FILE_ACTIONS_MENU_PATH: Final[str] = "/ocs/v2.php/apps/app_api/api/v2/ui/files-actions-menu"


@dataclass(frozen=True)
class FileActionsMenuEntry:
    """One right-click menu item to register with AppAPI."""

    name: str
    display_name: str
    action_handler: str  # path on the ExApp, e.g. "/files-action"
    mime: str = "file"  # comma-separated MIMEs; "file" matches all files
    icon: str | None = None
    permissions: int = 1  # READ
    order: int = 0


def _auth_header(user_id: str, secret: str) -> str:
    raw = f"{user_id}:{secret}".encode()
    return base64.b64encode(raw).decode("ascii")


class AppApiClient:
    """Thin HTTP client for AppAPI's OCS endpoints."""

    def __init__(
        self,
        config: AppApiConfig,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.config = config
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _ocs_headers(self, *, user_id: str = "") -> dict[str, str]:
        return {
            "EX-APP-ID": self.config.app_id,
            "EX-APP-VERSION": self.config.app_version,
            "AUTHORIZATION-APP-API": _auth_header(user_id, self.config.app_secret),
            "OCS-APIREQUEST": "true",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def register_file_action(
        self,
        entry: FileActionsMenuEntry,
        *,
        retries: int = 30,
        retry_delay_s: float = 10.0,
    ) -> None:
        """POST a file-actions-menu entry to AppAPI.

        AppAPI rejects OCS calls with 401 "AppAPI authentication failed"
        until the ExApp is `enabled` in `oc_ex_apps`. The bootstrap flow
        enables the ExApp AFTER `app:register --wait-finish` completes,
        and `--wait-finish` only returns after the container's first
        heartbeat — by which time uvicorn has already finished lifespan
        startup. So a freshly-spawned container ALWAYS fails the first
        register attempt with 401 and must retry.

        We retry up to `retries` times with `retry_delay_s` seconds
        between attempts (default: ~5 minutes total). AppAPI is
        idempotent on `name`, so retries are safe.

        Returns on 2xx; raises after exhausting retries.
        """
        url = f"{self.config.nc_url.rstrip('/')}{FILE_ACTIONS_MENU_PATH}"
        payload: dict[str, object] = {
            "name": entry.name,
            "displayName": entry.display_name,
            "actionHandler": entry.action_handler,
            "mime": entry.mime,
            "permissions": entry.permissions,
            "order": entry.order,
        }
        if entry.icon is not None:
            payload["icon"] = entry.icon

        last_error = ""
        for attempt in range(1, retries + 1):
            try:
                resp = await self._client.post(
                    url, headers=self._ocs_headers(), json=payload
                )
            except httpx.HTTPError as exc:
                last_error = f"transport error: {exc}"
                logger.info(
                    "FileActionsMenu register attempt %d/%d failed (%s) — retrying",
                    attempt,
                    retries,
                    last_error,
                )
            else:
                if resp.status_code < 400:
                    logger.info(
                        "registered FileActionsMenu entry name=%s actionHandler=%s "
                        "(attempt %d)",
                        entry.name,
                        entry.action_handler,
                        attempt,
                    )
                    return
                last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                # 401 specifically means "ExApp not yet enabled" — keep
                # retrying. Other 4xx are unlikely to recover, but we
                # retry anyway in case AppAPI is mid-restart.
                logger.info(
                    "FileActionsMenu register attempt %d/%d returned %s — retrying",
                    attempt,
                    retries,
                    last_error,
                )

            if attempt < retries:
                await asyncio.sleep(retry_delay_s)

        raise RuntimeError(
            f"AppAPI file-actions-menu register failed after {retries} attempts "
            f"(last: {last_error})"
        )
