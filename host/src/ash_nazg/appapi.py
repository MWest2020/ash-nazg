"""AppAPI registration handshake — skeleton only.

The real `/exapp/v1/ex-app/register` call lands in a later change.
What lives here now is the canonical app-id, the declared scope set,
and the config object the handshake will read from environment
variables that AppAPI injects at deploy time.

Per design.md and the `nextcloud-distribution` capability spec, the
declared scopes are FILES + AUDIT_LOGS + NOTIFICATIONS. AI_PROVIDERS
is intentionally NOT requested — Ash Nazg is a runtime host, not an
AI provider.
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
    # Bind to all interfaces by design — the container is the network
    # boundary; AppAPI's reverse proxy is what's reachable externally.
    app_host: str = Field(default="0.0.0.0")  # noqa: S104
    app_port: int = Field(default=8080, gt=0, lt=65536)
    nc_url: str = Field(description="Reachable Nextcloud base URL from inside the container.")

    @classmethod
    def from_environment(cls) -> AppApiConfig:
        return cls(
            app_version=os.environ["APP_VERSION"],
            app_secret=os.environ["APP_SECRET"],
            app_host=os.environ.get("APP_HOST", "0.0.0.0"),  # noqa: S104
            app_port=int(os.environ.get("APP_PORT", "8080")),
            nc_url=os.environ["NEXTCLOUD_URL"],
        )


def register() -> None:
    """Perform the AppAPI registration handshake.

    Lands in change `wire-dosbox-engine`.
    """
    raise NotImplementedError("AppAPI registration lands in change wire-dosbox-engine")
