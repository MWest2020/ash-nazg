"""Initial-state defaults for the admin settings page.

Per task §11.2: this module builds the JSON config blob that the
frontend's `@nextcloud/initial-state` reads on page mount. In this
scaffolding change the values are hardcoded; later changes wire it
to persistent storage backed by the AppAPI volume.

Structured as a Pydantic model — never a loose dict — so the
schema is self-documenting and exportable to JSON Schema for
TypeScript typings in the frontend without re-typing fields by
hand.

Defaults track the `engines` capability spec dosbox-x SessionConfig
so the admin UI's initial render matches the engine's actual
defaults.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, Field

DOSBOX_X_DEFAULT_MEMORY_MB: Final[int] = 1024
DOSBOX_X_DEFAULT_IDLE_TIMEOUT_S: Final[int] = 900


class EngineDefaults(BaseModel):
    """Per-engine default values surfaced in the admin UI."""

    enabled: bool = Field(default=False, description="New engines are admin-opt-in.")
    memory_limit_mb: int = Field(gt=0)
    idle_timeout_seconds: int = Field(gt=0)


class AdminInitialState(BaseModel):
    """Shape consumed by `@nextcloud/initial-state` on the admin page.

    The frontend imports this schema's JSON-Schema export to build
    its TypeScript types — keep field names stable.
    """

    app_id: str = Field(default="ash_nazg")
    app_version: str = Field(default="0.0.0")
    engines: dict[str, EngineDefaults]
    audit_event_prefix: str = Field(
        default="ash_nazg",
        description="Audit-log event names are prefixed with this string.",
    )
    selftest_endpoint: str = Field(
        default="/selftest",
        description="Path the 'Test installation' button POSTs to.",
    )


def build_initial_state() -> AdminInitialState:
    """Return the hardcoded scaffold-defaults blob.

    The wiring change replaces the body with a read from persistent
    storage; the return type stays the same so the frontend never
    has to branch on schema versions.
    """
    return AdminInitialState(
        engines={
            "dosbox-x": EngineDefaults(
                enabled=False,
                memory_limit_mb=DOSBOX_X_DEFAULT_MEMORY_MB,
                idle_timeout_seconds=DOSBOX_X_DEFAULT_IDLE_TIMEOUT_S,
            ),
        },
    )
