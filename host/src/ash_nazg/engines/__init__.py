"""Engine plugin protocol for Ash Nazg.

Per design.md and the `engines` capability spec, every engine
implements the `Engine` Protocol below. Engines register themselves
at host startup via the `ash_nazg.engines` Python entrypoint group;
the host iterates over that group and adds discovered engines to the
dispatch registry.

This module ONLY defines the protocol and the data shapes. No
concrete engine implementations live here. The dosbox-x engine is
wired in change `wire-dosbox-engine`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class FileMeta(BaseModel):
    """Metadata about a Files entry being considered for dispatch."""

    path: str = Field(description="Path within the user's Files root.")
    size_bytes: int = Field(ge=0)
    extension: str = Field(default="", description="Lowercased extension, no leading dot.")
    magic_class: str = Field(
        description=(
            "Detected magic-byte family: pe32, pe32-plus, mz-dos, elf, "
            "wasm, jar, mach-o, or unknown."
        )
    )


class SessionConfig(BaseModel):
    """Container spawn configuration returned by an Engine for a given file.

    Field set is normative — see the `engines` spec, requirement
    "The repository SHALL ship one engine implementation: dosbox-x".
    """

    image: str = Field(
        description="Fully qualified OCI reference. MUST NOT use the :latest tag."
    )
    cpu_limit: float = Field(gt=0)
    memory_limit_mb: int = Field(gt=0)
    mount_path: str = Field(description="WebDAV mount path inside the engine container.")
    streaming_protocol: str = Field(description='e.g. "kasmvnc"')
    streaming_port: int = Field(gt=0, lt=65536)
    idle_timeout_seconds: int = Field(gt=0)
    entrypoint_args: list[str] = Field(default_factory=list)


@runtime_checkable
class Engine(Protocol):
    """Plugin protocol every Ash Nazg engine implements."""

    id: str
    image: str

    def can_handle(self, file_meta: FileMeta) -> bool:
        """Return True if this engine should handle the given file.

        Multiple engines may match. The dispatcher takes the first
        registered match; admins can reorder via the settings UI.
        """
        ...

    def session_config(self, file_meta: FileMeta) -> SessionConfig:
        """Return the container spawn configuration for `file_meta`.

        Called only after `can_handle()` returns True.
        """
        ...
