"""SessionSpawner implementations.

Two implementations:

- `StubSpawner` — returns a fixed (host, port) without actually spawning
  a container. Used in the integrated demo flow where one always-on
  engine container (started outside Ash Nazg) handles every Run
  request. Trunk-friendly: lets the /run endpoint return a URL the
  frontend can navigate to without first having to wire the docker
  socket. Marked clearly as a demo-mode shortcut.

- `InImageSpawner` — runs the engine as a child process of this
  container, one process tree per session. An earlier
  `DockerSubprocessSpawner` shelled out to `docker run`; it is gone,
  because an ExApp container has no docker CLI, no socket, and HaRP
  offers ExApps no spawn API. See wire-dosbox-engine's "Open
  ontwerpbesluit" for the routes back to container-level isolation.

Both implement the `SessionSpawner` Protocol from `dispatch.py`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import shutil
import signal
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ash_nazg.dispatch import SessionHandle
from ash_nazg.engines import FileMeta, SessionConfig

logger = logging.getLogger(__name__)

# The account name inside the session's own KasmVNC password file.
VNC_USER: Final[str] = "session"

# --- Stub --------------------------------------------------------------------


class StubSpawner:
    """Returns a fixed engine endpoint regardless of session.

    Used in the demo where a single pre-started engine container handles
    every Run request. The host returns the demo URL so the frontend can
    navigate to it. NEVER use this in a multi-user deployment.
    """

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    async def spawn(
        self,
        *,
        session_id: str,
        config: SessionConfig,
        file_meta: FileMeta,
        user_id: str,
    ) -> SessionHandle:
        logger.info(
            "stub-spawner: returning demo URL host=%s port=%d for session=%s "
            "(would have launched %s with file=%s)",
            self.host,
            self.port,
            session_id,
            config.image,
            file_meta.path,
        )
        return SessionHandle(
            session_id=session_id,
            container_id=f"stub-{session_id[:8]}",
            host=self.host,
            port=self.port,
        )

    async def preflight(self) -> tuple[bool, str]:
        """The stub has no backend to reach; it is always ready."""
        return True, f"stub spawner ready → {self.host}:{self.port} (demo mode)"


def stub_spawner_from_env() -> StubSpawner:
    """Build a StubSpawner from `ASH_NAZG_DEMO_HOST` / `ASH_NAZG_DEMO_PORT`.

    Defaults match the visible-demo flow documented in `docs/demo.md`:
    host 127.0.0.1, port 16901 (KasmVNC web client).
    """
    host = os.environ.get("ASH_NAZG_DEMO_HOST", "127.0.0.1")
    port = int(os.environ.get("ASH_NAZG_DEMO_PORT", "16901"))
    return StubSpawner(host=host, port=port)


# --- In-image sessions -------------------------------------------------------


@dataclass
class _RunningSession:
    """One engine process tree started by `InImageSpawner`."""

    session_id: str
    process: asyncio.subprocess.Process
    display: int
    port: int
    directory: Path
    secret: str


class InImageSpawner:
    """Runs the engine inside this container, as a child process.

    The decision behind this (wire-dosbox-engine, "Open ontwerpbesluit"):
    an ExApp container cannot spawn a sibling container. It has no docker
    CLI, no socket, and HaRP exposes no spawn API to ExApps. So the
    emulator ships in the same image as the shim and a session is a
    process tree, not a container.

    What that costs, stated plainly because the sandbox spec used to
    promise otherwise: there are no cgroup limits on a session, the
    root filesystem is not read-only, and a session runs under the same
    uid as the shim — so the emulator process can read the shim's
    environment, including APP_SECRET. The isolation that remains is
    DOSBox-X itself: the untrusted binary is a DOS program inside an
    emulator, never native code on this host. Per-engine ExApps are the
    route back to container-level isolation.

    What is enforced here: one process tree per session (never reused),
    a private directory per session, a cap on concurrent sessions, a
    lower scheduling priority than the shim, and termination on max
    duration and on host shutdown.
    """

    def __init__(
        self,
        *,
        file_reader: Any,
        engine_script: str = "/usr/local/bin/ash-nazg-engine",
        sessions_root: Path = Path("/tmp/ash-nazg-sessions"),  # noqa: S108
        base_port: int = 6900,
        first_display: int = 10,
        max_sessions: int = 8,
        readiness_timeout_s: float = 30.0,
        max_duration_s: float = 4 * 60 * 60,
        nice_increment: int = 10,
    ) -> None:
        self.file_reader = file_reader
        self.engine_script = engine_script
        self.sessions_root = sessions_root
        self.base_port = base_port
        self.first_display = first_display
        self.max_sessions = max_sessions
        self.readiness_timeout_s = readiness_timeout_s
        self.max_duration_s = max_duration_s
        self.nice_increment = nice_increment
        self._sessions: dict[str, _RunningSession] = {}
        self._slots: set[int] = set()

    # --- lifecycle ---------------------------------------------------------

    async def preflight(self) -> tuple[bool, str]:
        """Check the engine can actually be started, without starting it."""
        missing = [
            name for name in ("dosbox-x", "kasmvncserver")
            if shutil.which(name) is None
        ]
        if missing:
            return False, f"engine binaries missing from the image: {', '.join(missing)}"
        if not os.access(self.engine_script, os.X_OK):
            return False, f"engine entrypoint {self.engine_script} is not executable"
        free = self.max_sessions - len(self._slots)
        return True, (
            f"in-image engine ready (dosbox-x + kasmvncserver present, "
            f"{free}/{self.max_sessions} session slots free)"
        )

    async def spawn(
        self,
        *,
        session_id: str,
        config: SessionConfig,
        file_meta: FileMeta,
        user_id: str,
    ) -> SessionHandle:
        slot = self._claim_slot()
        # Modes are set explicitly, never left to the umask: under HaRP
        # the shim runs with umask 0177 (so its unix socket comes out
        # 0600), and a directory created under that umask has no execute
        # bit — nothing can be written inside it, not even by its owner.
        directory = self.sessions_root / session_id
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        self.sessions_root.chmod(0o700)
        directory.mkdir(exist_ok=True)
        directory.chmod(0o700)

        # The binary is downloaded, not mounted: no davfs2, no privileges,
        # and the session cannot reach the rest of the user's Files.
        local_path = directory / Path(file_meta.path).name
        await self.file_reader.download_to(file_meta.path, local_path)

        display = self.first_display + slot
        port = self.base_port + slot
        # A killed Xvnc leaves its display lock behind, and the next
        # server on that display exits 29 without explaining itself. The
        # slot is ours, so anything still lying around for it is stale.
        self._clear_display_locks(display)
        # Credentials belong to this session, not to the image: a baked-in
        # password is identical on every install and survives redeployment.
        # It lives in the session directory and dies with it.
        secret = secrets.token_urlsafe(24)
        password_file = directory / "kasmpasswd"
        await self._write_password_file(password_file, secret)
        env = self._session_env(
            display=display,
            port=port,
            local_path=local_path,
            directory=directory,
            password_file=password_file,
        )
        log_path = directory / "engine.log"
        with log_path.open("wb") as log:
            process = await asyncio.create_subprocess_exec(
                self.engine_script,
                stdout=log,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
                env=env,
                cwd=str(directory),
                preexec_fn=self._lower_priority,
                # Own process group. `kasmvncserver` is a launcher: it
                # starts Xvnc and returns, and Xvnc starts the emulator.
                # Signalling only the child left both of those running —
                # the next session then found "its" port already open,
                # attached to the previous session's server, and answered
                # 401 because the credentials no longer matched.
                start_new_session=True,
            )
        session = _RunningSession(
            session_id=session_id,
            process=process,
            display=display,
            port=port,
            directory=directory,
            secret=secret,
        )
        self._sessions[session_id] = session

        try:
            await self._await_port(port, process, log_path)
        except Exception:
            await self.terminate(session_id)
            raise

        logger.info(
            "in-image session %s started: pid=%d display=:%d port=%d file=%s",
            session_id, process.pid, display, port, file_meta.path,
        )
        return SessionHandle(
            session_id=session_id,
            container_id=f"pid-{process.pid}",
            host=socket.gethostname(),
            port=port,
        )

    def port_for(self, session_id: str) -> int | None:
        """The port this session's VNC server listens on, or None."""
        session = self._sessions.get(session_id)
        return session.port if session else None

    def credentials_for(self, session_id: str) -> tuple[str, str] | None:
        """(user, secret) for this session's VNC server, or None."""
        session = self._sessions.get(session_id)
        return (VNC_USER, session.secret) if session else None

    async def terminate(self, session_id: str) -> None:
        """SIGTERM, then SIGKILL after the grace period (sandbox spec)."""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        self._slots.discard(session.display - self.first_display)
        if session.process.returncode is None:
            # Ask KasmVNC to stop first: it tears its display down and
            # removes the lock file. The group sweep below is for
            # whatever ignores that.
            await self._kill_display(session.display)
            self._signal_group(session, signal.SIGTERM)
            try:
                await asyncio.wait_for(session.process.wait(), timeout=_GRACE_SECONDS)
            except TimeoutError:
                logger.warning("session %s ignored SIGTERM; killing", session_id)
                self._signal_group(session, signal.SIGKILL)
                await session.process.wait()
        # The group outlives the leader: Xvnc and the emulator are its
        # children, not the launcher's. Sweep whatever is left.
        self._signal_group(session, signal.SIGKILL)
        shutil.rmtree(session.directory, ignore_errors=True)
        logger.info("in-image session %s terminated", session_id)

    async def terminate_all(self) -> None:
        for session_id in list(self._sessions):
            await self.terminate(session_id)

    # --- internals ---------------------------------------------------------

    async def _kill_display(self, display: int) -> None:
        """`kasmvncserver -kill :N` — the graceful stop, lock file included."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "kasmvncserver", "-kill", f":{display}",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=10)
        except (OSError, TimeoutError) as exc:
            logger.info("kasmvncserver -kill :%d did not complete: %s", display, exc)

    def _clear_display_locks(self, display: int) -> None:
        for path in (Path(f"/tmp/.X{display}-lock"),  # noqa: S108 — X11's own paths
                     Path(f"/tmp/.X11-unix/X{display}")):  # noqa: S108
            try:
                path.unlink()
                logger.info("removed stale %s from a previous session", path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                logger.warning("could not remove %s: %s", path, exc)

    def _signal_group(self, session: _RunningSession, sig: int) -> None:
        """Signal the whole session process group; missing is fine."""
        try:
            os.killpg(session.process.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    def _claim_slot(self) -> int:
        for slot in range(1, self.max_sessions + 1):
            if slot not in self._slots:
                self._slots.add(slot)
                return slot
        raise RuntimeError(
            f"all {self.max_sessions} session slots are in use; "
            "close a session before starting another"
        )

    async def _write_password_file(self, path: Path, secret: str) -> None:
        """Ask kasmvncpasswd to write the session's password file."""
        proc = await asyncio.create_subprocess_exec(
            "kasmvncpasswd", "-u", VNC_USER, "-wo", str(path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        # The tool asks for the password twice, then for a read-only one
        # (empty = none).
        _, stderr = await proc.communicate(f"{secret}\n{secret}\n\n".encode())
        if proc.returncode != 0:
            raise RuntimeError(
                "kasmvncpasswd failed "
                f"(exit {proc.returncode}): {stderr.decode(errors='replace').strip()}"
            )
        path.chmod(0o600)

    def _session_env(
        self,
        *,
        display: int,
        port: int,
        local_path: Path,
        directory: Path,
        password_file: Path,
    ) -> dict[str, str]:
        # A deliberately small environment: the shim's own variables
        # (APP_SECRET above all) have no business in an engine session.
        # This is hygiene, not a boundary — same uid, same /proc.
        return {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/home/app"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "FILE_PATH": str(local_path),
            "VNC_DISPLAY": f":{display}",
            "VNC_WEBSOCKET_PORT": str(port),
            "XSTARTUP_PATH": str(directory / "xstartup"),
            "VNC_PASSWORD_FILE": str(password_file),
        }

    def _lower_priority(self) -> None:
        """Runs in the child between fork and exec."""
        os.nice(self.nice_increment)

    async def _await_port(
        self, port: int, process: asyncio.subprocess.Process, log_path: Path
    ) -> None:
        """Wait until KasmVNC accepts connections, or explain why it never did."""
        deadline = asyncio.get_running_loop().time() + self.readiness_timeout_s
        while asyncio.get_running_loop().time() < deadline:
            if process.returncode is not None:
                raise RuntimeError(
                    f"engine exited with code {process.returncode} before "
                    f"listening on port {port}: {_tail(log_path)}"
                )
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", port)
            except OSError:
                await asyncio.sleep(0.5)
                continue
            writer.close()
            await writer.wait_closed()
            return
        raise RuntimeError(
            f"engine did not listen on port {port} within "
            f"{self.readiness_timeout_s:.0f}s: {_tail(log_path)}"
        )


_GRACE_SECONDS: Final[float] = 30.0


def _tail(path: Path, limit: int = 400) -> str:
    try:
        return path.read_text(errors="replace")[-limit:].strip() or "(engine log empty)"
    except OSError:
        return "(no engine log)"
