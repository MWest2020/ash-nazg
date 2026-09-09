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

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

from ash_nazg.detection import DETECTION_READ_BYTES, UNKNOWN, classify
from ash_nazg.engines import FileMeta, SessionConfig
from ash_nazg.engines.registry import EngineRegistry

logger = logging.getLogger(__name__)


def _now() -> float:
    """Monotonic seconds — a wall clock that jumps must not end sessions."""
    return time.monotonic()

DEFAULT_MAX_FILE_BYTES: Final[int] = 100 * 1024 * 1024  # 100 MB per spec default
# Sandbox spec, "Engine session lifecycle bounded": maximum session
# duration, default 4 hours, and the idle window, default 15 minutes.
DEFAULT_MAX_SESSION_SECONDS: Final[float] = 4 * 60 * 60
DEFAULT_IDLE_SECONDS: Final[float] = 900


# --- Protocols injected by main.py ---------------------------------------


class FileReader(Protocol):
    """Reads the user's Files content via WebDAV (or a fake in tests)."""

    async def read_head(self, files_path: str, byte_count: int) -> bytes:
        """Return at most `byte_count` bytes from the start of `files_path`."""

    async def get_size(self, files_path: str) -> int:
        """Return the total file size in bytes."""

    async def download_to(self, files_path: str, destination: Path) -> None:
        """Write the whole file to `destination` (used to start a session)."""


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

    def owner_of(self, session_id: str) -> tuple[str, str] | None:
        """(user_id, files_path) for a session, or None if it is not held."""
        for (user_id, files_path), active in self._by_key.items():
            if active.session_id == session_id:
                return user_id, files_path
        return None


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
        max_session_seconds: float = DEFAULT_MAX_SESSION_SECONDS,
        idle_seconds: float = DEFAULT_IDLE_SECONDS,
        watch_interval_s: float = 15.0,
    ) -> None:
        self.registry = registry
        self.file_reader = file_reader
        self.spawner = spawner
        self.audit = audit
        self.active = active_sessions or ActiveSessionTracker()
        self.max_file_bytes = max_file_bytes
        self.max_session_seconds = max_session_seconds
        self.idle_seconds = idle_seconds
        self.watch_interval_s = watch_interval_s
        # Lifetime watchers, kept referenced so the loop cannot collect
        # them mid-flight, and the clock each one reads.
        self._expiries: set[asyncio.Task[None]] = set()
        self._last_activity: dict[str, float] = {}

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

        try:
            size_bytes = await self.file_reader.get_size(files_path)
        except Exception as exc:
            # A path that is not there is the user's mistake, not a
            # server fault: answering 500 with a WebDAV error would be
            # both wrong and unreadable.
            logger.info("could not read %s: %s", files_path, exc)
            await self._audit(
                "refused",
                user_id=user_id,
                files_path=files_path,
                reason="unreadable",
            )
            return DispatchError(
                status_code=404,
                code="file_not_found",
                message=f"Could not read {files_path} from your Files.",
            )
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
        self._schedule_expiry(handle.session_id, user_id, files_path)
        return DispatchOk(
            session_id=handle.session_id,
            host=handle.host,
            port=handle.port,
        )

    async def close(self, session_id: str, *, user_id: str) -> bool:
        """End a session and free its claim.

        Returns False when this user holds no such session — which is
        also the answer for someone else's session, so one user cannot
        probe for another's session ids.
        """
        owner = self.active.owner_of(session_id)
        if owner is None or owner[0] != user_id:
            return False
        terminate = getattr(self.spawner, "terminate", None)
        if callable(terminate):
            await terminate(session_id)
        self.active.release(*owner)
        self._last_activity.pop(session_id, None)
        await self._audit(
            "closed",
            user_id=user_id,
            files_path=owner[1],
            session_id=session_id,
        )
        return True

    def note_activity(self, session_id: str) -> None:
        """Called by the stream relay for every frame it carries.

        The relay is the only place that can see whether anyone is
        watching; the dispatcher must not guess at a signal it cannot
        observe.
        """
        if session_id in self._last_activity:
            self._last_activity[session_id] = _now()

    def _schedule_expiry(self, session_id: str, user_id: str, files_path: str) -> None:
        """Bound the session's lifetime: idle window and maximum duration.

        Both end the session the same way an explicit close does. That
        matters for the claim on (user, file): it is what makes a second
        Run return 409, so a session that ends without releasing it would
        lock the user out of that file for the life of the host.

        A session nobody has attached to yet counts as idle from the
        moment it started — which is correct: nothing is watching it.
        """
        started = _now()
        self._last_activity[session_id] = started

        async def _watch() -> None:
            while True:
                await asyncio.sleep(self.watch_interval_s)
                now = _now()
                last = self._last_activity.get(session_id, started)
                if now - started >= self.max_session_seconds:
                    reason = f"the {self.max_session_seconds:.0f}s maximum duration"
                elif now - last >= self.idle_seconds:
                    reason = f"{self.idle_seconds:.0f}s without traffic"
                else:
                    continue
                if await self.close(session_id, user_id=user_id):
                    logger.info("session %s closed: %s", session_id, reason)
                return

        task = asyncio.create_task(_watch())
        self._expiries.add(task)
        task.add_done_callback(self._expiries.discard)

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
