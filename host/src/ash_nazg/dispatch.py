"""Dispatcher — selects an engine and spawns a session container.

Per `wire-dosbox-engine/specs/dispatch/spec.md`:
- Iterate registered ENABLED engines in registration order.
- Call `can_handle(file_meta)` on each; spawn using the first match.
- Return `{session_id, host, port}` on success.
- 415 for unhandled magic-byte family.
- 400 for unrecognised (unknown family + no engine claims it).
- 403 for non-admin (sandbox spec "Admin-only execution in v1").
- 413 for binaries larger than the configured limit.
- 409 if same user already has an active session for the same file.
- Every dispatch attempt writes an audit-log entry.

The dispatcher is decoupled from FastAPI and from the actual container
runtime by accepting protocols for file-reading, session-spawning, and
audit-logging. Tests pass fakes; production wires real WebDAV / docker /
AppAPI OCS implementations in `main.py`.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Final, Protocol

from ash_nazg.detection import DETECTION_READ_BYTES, UNKNOWN, classify
from ash_nazg.engines import FileMeta, SessionConfig
from ash_nazg.engines.registry import EngineRegistry

logger = logging.getLogger(__name__)

DEFAULT_MAX_FILE_BYTES: Final[int] = 100 * 1024 * 1024  # 100 MB per spec default


# --- Protocols injected by main.py ---------------------------------------


class FileReader(Protocol):
    """Reads the user's Files content via WebDAV (or a fake in tests)."""

    async def read_head(self, files_path: str, byte_count: int) -> bytes:
        """Return at most `byte_count` bytes from the start of `files_path`."""

    async def get_size(self, files_path: str) -> int:
        """Return the total file size in bytes."""


@dataclass(frozen=True)
class SessionHandle:
    """What a spawner returns after a successful container spawn."""

    session_id: str
    container_id: str
    host: str
    port: int


class SessionSpawner(Protocol):
    """Spawns an engine container for a session and returns its address."""

    async def spawn(
        self,
        *,
        session_id: str,
        config: SessionConfig,
        file_meta: FileMeta,
        user_id: str,
    ) -> SessionHandle:
        ...


class AuditLogger(Protocol):
    """Writes audit-log entries to Nextcloud's audit log (or a fake)."""

    async def log(self, **fields: Any) -> None:
        ...


# --- Result types ---------------------------------------------------------


@dataclass(frozen=True)
class DispatchOk:
    session_id: str
    host: str
    port: int


@dataclass(frozen=True)
class DispatchError:
    status_code: int
    code: str
    message: str


DispatchResult = DispatchOk | DispatchError


# --- Active sessions (concurrent access detection per spec) --------------


@dataclass
class _ActiveSession:
    user_id: str
    files_path: str
    session_id: str


class ActiveSessionTracker:
    """Tracks (user, file) → session for the 409 concurrent-access check.

    In-memory only in v1. Future: persist via AppAPI app_value so a host
    restart doesn't lose state.
    """

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], _ActiveSession] = {}

    def claim(self, user_id: str, files_path: str, session_id: str) -> bool:
        key = (user_id, files_path)
        if key in self._by_key:
            return False
        self._by_key[key] = _ActiveSession(user_id, files_path, session_id)
        return True

    def release(self, user_id: str, files_path: str) -> None:
        self._by_key.pop((user_id, files_path), None)


# --- Dispatcher -----------------------------------------------------------


class Dispatcher:
    def __init__(
        self,
        *,
        registry: EngineRegistry,
        file_reader: FileReader,
        spawner: SessionSpawner,
        audit: AuditLogger,
        active_sessions: ActiveSessionTracker | None = None,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    ) -> None:
        self.registry = registry
        self.file_reader = file_reader
        self.spawner = spawner
        self.audit = audit
        self.active = active_sessions or ActiveSessionTracker()
        self.max_file_bytes = max_file_bytes

    async def dispatch(
        self,
        *,
        files_path: str,
        user_id: str,
        is_admin: bool,
    ) -> DispatchResult:
        # sandbox spec: non-admin blocked, still audited.
        if not is_admin:
            await self._audit("forbidden", user_id=user_id, files_path=files_path,
                              reason="not admin")
            return DispatchError(
                status_code=403,
                code="forbidden",
                message="Only Nextcloud admins may run binaries via Ash Nazg.",
            )

        size_bytes = await self.file_reader.get_size(files_path)
        if size_bytes > self.max_file_bytes:
            await self._audit(
                "refused",
                user_id=user_id,
                files_path=files_path,
                reason="oversize",
                file_size=size_bytes,
            )
            return DispatchError(
                status_code=413,
                code="oversize",
                message=(
                    f"Binary exceeds size limit "
                    f"({self.max_file_bytes // (1024 * 1024)} MB) — "
                    "adjust in admin settings if intentional."
                ),
            )

        head = await self.file_reader.read_head(files_path, DETECTION_READ_BYTES)
        extension = files_path.rsplit(".", 1)[-1].lower() if "." in files_path else ""
        magic = classify(head, extension=extension)
        file_sha256 = hashlib.sha256(head).hexdigest()  # only the head — for audit traceability

        meta = FileMeta(
            path=files_path,
            size_bytes=size_bytes,
            extension=extension,
            magic_class=magic,
        )

        if magic == UNKNOWN:
            await self._audit(
                "refused",
                user_id=user_id,
                files_path=files_path,
                detected_type=magic,
                reason="not a recognized executable format",
                file_sha256=file_sha256,
            )
            return DispatchError(
                status_code=400,
                code="unrecognized",
                message="not a recognized executable format",
            )

        engine = self._select_engine(meta)
        if engine is None:
            await self._audit(
                "refused",
                user_id=user_id,
                files_path=files_path,
                detected_type=magic,
                reason="no enabled engine handles this format",
                file_sha256=file_sha256,
            )
            return DispatchError(
                status_code=415,
                code="unsupported_media_type",
                message=f"no enabled engine handles {magic}",
            )

        # Concurrent access detection: spec scenario "Double-click while
        # running" → 409. Claim BEFORE spawning so a parallel request
        # doesn't double-spawn.
        session_id = str(uuid.uuid4())
        if not self.active.claim(user_id, files_path, session_id):
            await self._audit(
                "refused",
                user_id=user_id,
                files_path=files_path,
                detected_type=magic,
                selected_engine=engine.id,
                reason="already running for this user",
                file_sha256=file_sha256,
            )
            return DispatchError(
                status_code=409,
                code="already_running",
                message=(
                    "this file is already running — close the existing "
                    "session first"
                ),
            )

        try:
            config = engine.session_config(meta)
            handle = await self.spawner.spawn(
                session_id=session_id,
                config=config,
                file_meta=meta,
                user_id=user_id,
            )
        except Exception as exc:
            self.active.release(user_id, files_path)
            logger.exception("engine spawn failed")
            await self._audit(
                "error",
                user_id=user_id,
                files_path=files_path,
                detected_type=magic,
                selected_engine=engine.id,
                engine_image=engine.image,
                reason=f"spawn failed: {exc.__class__.__name__}: {exc}",
                file_sha256=file_sha256,
            )
            return DispatchError(
                status_code=500,
                code="spawn_failed",
                message=f"engine container failed to start: {exc}",
            )

        await self._audit(
            "dispatched",
            user_id=user_id,
            files_path=files_path,
            detected_type=magic,
            selected_engine=engine.id,
            engine_image=engine.image,
            session_id=handle.session_id,
            container_id=handle.container_id,
            file_sha256=file_sha256,
        )
        return DispatchOk(
            session_id=handle.session_id,
            host=handle.host,
            port=handle.port,
        )

    def _select_engine(self, meta: FileMeta) -> Any:  # returns Engine | None
        for engine in self.registry.enabled():
            if engine.can_handle(meta):
                return engine
        return None

    async def _audit(self, outcome: str, **fields: Any) -> None:
        try:
            await self.audit.log(outcome=outcome, **fields)
        except Exception:
            # Audit failures must NOT break dispatch — observability is
            # degraded, not absent. Log locally and continue.
            logger.exception("audit log write failed for outcome=%s", outcome)
