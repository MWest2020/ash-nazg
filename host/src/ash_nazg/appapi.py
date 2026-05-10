"""AppAPI configuration — reads env vars that AppAPI/HaRP injects.

In AppAPI 5.x docker-install mode, HaRP spawns this container with
`APP_ID`, `APP_PORT`, `APP_SECRET`, `APP_VERSION`, `AA_VERSION`,
`NEXTCLOUD_URL` as env vars. The host shim accepts those values
(no port negotiation — AppAPI assigns).

Proxy routes are declared **statically** in `appinfo/info.xml`
under `<external-app><routes>` and registered by AppAPI at
`occ app_api:app:register` time. No runtime registration call is
needed — see the AppAPI 5.x source
(`apps/app_api/lib/Service/ExAppService.php::registerExApp`).

Authentication for AppAPI ↔ ExApp callbacks uses the simple
`AUTHORIZATION-APP-API: base64(user_id:app_secret)` header — no
HMAC, no canonical-string signing. Transport security comes from
the HaRP/TLS layer.
"""

from __future__ import annotations

import os
from typing import Final

from pydantic import BaseModel, Field

APP_ID: Final[str] = "ash_nazg"

REQUIRED_SCOPES: Final[tuple[str, ...]] = (
    "FILES",
    "AUDIT_LOGS",
    "NOTIFICATIONS",
)


class AppApiConfig(BaseModel):
    """Configuration AppAPI provides at container start."""

    app_id: str = Field(default=APP_ID)
    app_version: str
    app_secret: str
    app_host: str = Field(default="0.0.0.0")  # noqa: S104
    app_port: int = Field(default=8080, gt=0, lt=65536)
    nc_url: str
    aa_version: str = Field(default="")

    @classmethod
    def from_environment(cls) -> AppApiConfig:
        return cls(
            app_version=os.environ["APP_VERSION"],
            app_secret=os.environ["APP_SECRET"],
            app_host=os.environ.get("APP_HOST", "0.0.0.0"),  # noqa: S104
            app_port=int(os.environ.get("APP_PORT", "8080")),
            nc_url=os.environ["NEXTCLOUD_URL"],
            aa_version=os.environ.get("AA_VERSION", ""),
        )
