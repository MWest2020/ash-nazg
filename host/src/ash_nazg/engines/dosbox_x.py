"""dosbox-x engine plugin.

Implements the Engine protocol for MS-DOS .exe / .com binaries (mz-dos)
and Windows 32/64-bit .exe binaries (pe32, pe32-plus). dosbox-x handles
both because its built-in win3.1/win95 layer covers PE binaries that the
user supplies along with their own Windows installation (per the
"bring your own software" guidance in `docs/bring-your-own-content.md`).

Pinned image tag matches the build the engine container CI workflow
publishes for this change. Never `:latest` — see `engines` spec
requirement "Engine images use pinned tags, never :latest".
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Final

from ash_nazg.engines import FileMeta, SessionConfig

ENGINE_ID: Final[str] = "dosbox-x"

# Pinned to the development tag for this change. The image-publish
# workflow (`build-engine-dosbox.yml`) emits this tag for every push
# to main. Bumped to a versioned tag (e.g. 0.1.0) at release time.
ENGINE_IMAGE: Final[str] = "ghcr.io/mwest2020/ash-nazg-dosbox-x:0.1.0-wire-dev"

MOUNT_PATH: Final[str] = "/mnt/files"
STREAMING_PORT: Final[int] = 6901
IDLE_TIMEOUT_SECONDS: Final[int] = 900
DEFAULT_CPU_LIMIT: Final[float] = 1.0
DEFAULT_MEMORY_LIMIT_MB: Final[int] = 1024

# Magic-byte families this engine accepts. Detection module produces
# these strings; see `detection/spec.md`.
SUPPORTED_MAGIC: Final[frozenset[str]] = frozenset({"pe32", "pe32-plus", "mz-dos"})


def _resolve_under_mount(files_path: str) -> PurePosixPath:
    """Translate a Files path into its location under /mnt/files."""
    return PurePosixPath(MOUNT_PATH) / files_path.lstrip("/")


class DosboxXEngine:
    """Engine plugin for DOSBox-X."""

    id: str = ENGINE_ID
    image: str = ENGINE_IMAGE

    def can_handle(self, file_meta: FileMeta) -> bool:
        return file_meta.magic_class in SUPPORTED_MAGIC

    def session_config(self, file_meta: FileMeta) -> SessionConfig:
        in_container = _resolve_under_mount(file_meta.path)
        # files-integration spec req "Working directory is the binary's
        # directory" — dosbox-x is started with the file path; the
        # engine container's entrypoint cd's to its parent before exec.
        return SessionConfig(
            image=ENGINE_IMAGE,
            cpu_limit=DEFAULT_CPU_LIMIT,
            memory_limit_mb=DEFAULT_MEMORY_LIMIT_MB,
            mount_path=MOUNT_PATH,
            streaming_protocol="kasmvnc",
            streaming_port=STREAMING_PORT,
            idle_timeout_seconds=IDLE_TIMEOUT_SECONDS,
            entrypoint_args=["dosbox-x", str(in_container)],
        )
