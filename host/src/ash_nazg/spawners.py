"""SessionSpawner implementations.

Two implementations:

- `StubSpawner` — returns a fixed (host, port) without actually spawning
  a container. Used in the integrated demo flow where one always-on
  engine container (started outside Ash Nazg) handles every Run
  request. Trunk-friendly: lets the /run endpoint return a URL the
  frontend can navigate to without first having to wire the docker
  socket. Marked clearly as a demo-mode shortcut.

- `DockerSubprocessSpawner` — spawns a fresh engine container per
  session via `docker run`. Wires the spawned container onto the
  compose network and writes the AppAPI-issued per-session token in.
  Production-shaped but still constrained to the local docker /
  podman socket; the AppAPI-bridged spawner replaces it once
  upstream AppAPI exposes a per-session spawn endpoint.

Both implement the `SessionSpawner` Protocol from `dispatch.py`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from typing import Final

from ash_nazg.dispatch import SessionHandle
from ash_nazg.engines import FileMeta, SessionConfig

logger = logging.getLogger(__name__)

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


# --- Docker subprocess -------------------------------------------------------


_DEFAULT_DOCKER_BIN: Final[str] = "docker"


class DockerSubprocessSpawner:
    """Spawns engine containers by shelling out to `docker run`.

    Resource limits, read-only root, tmpfs for /tmp, network attach, and
    env-var injection are encoded as run flags per the sandbox spec.
    The container is detached; the spawner reads the container id from
    stdout and resolves the host:port the engine listens on.

    The `network` param is the docker network the engine container must
    join so the Nextcloud container can reach it. In demo mode this is
    the compose network created by `scripts/local-nextcloud-stack.yml`;
    in production it's the AppAPI proxy network.
    """

    def __init__(
        self,
        *,
        docker_bin: str = _DEFAULT_DOCKER_BIN,
        network: str | None = None,
        extra_env: dict[str, str] | None = None,
        container_label_app: str = "ash-nazg",
    ) -> None:
        self.docker_bin = docker_bin
        self.network = network
        self.extra_env = extra_env or {}
        self.container_label_app = container_label_app

    async def spawn(
        self,
        *,
        session_id: str,
        config: SessionConfig,
        file_meta: FileMeta,
        user_id: str,
    ) -> SessionHandle:
        argv = self._build_argv(
            session_id=session_id,
            config=config,
            file_meta=file_meta,
            user_id=user_id,
        )
        logger.debug("spawn argv: %s", shlex.join(argv))
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"docker run failed (exit {proc.returncode}): "
                f"{stderr.decode(errors='replace').strip()}"
            )
        container_id = stdout.decode().strip()
        if not container_id:
            raise RuntimeError("docker run returned empty container id")

        # Engine reachable via container DNS name on the shared network.
        # KasmVNC listens on streaming_port inside the container.
        return SessionHandle(
            session_id=session_id,
            container_id=container_id,
            host=container_id[:12],  # short id == DNS name on podman bridge
            port=config.streaming_port,
        )

    def _build_argv(
        self,
        *,
        session_id: str,
        config: SessionConfig,
        file_meta: FileMeta,
        user_id: str,
    ) -> list[str]:
        memory = f"{config.memory_limit_mb}m"
        cpus = str(config.cpu_limit)
        container_name = f"ash-nazg-{session_id[:12]}"

        argv: list[str] = [
            self.docker_bin,
            "run",
            "-d",
            "--rm",
            "--name",
            container_name,
            "--label",
            f"app={self.container_label_app}",
            "--label",
            f"session_id={session_id}",
            "--label",
            f"user_id={user_id}",
            "--cpus",
            cpus,
            "--memory",
            memory,
            "--memory-swap",
            memory,  # sandbox spec: no swap allowance
            "--read-only",
            "--tmpfs",
            "/tmp:rw,size=256m",  # noqa: S108 — docker tmpfs spec, not a host path
            "--security-opt",
            "label=disable",  # SELinux interop for bind mounts
        ]

        if self.network:
            argv.extend(["--network", self.network])

        # Per-session env: file path inside the engine, plus the AppAPI
        # token davfs2 will use. The engine entrypoint reads FILE_PATH;
        # NEXTCLOUD_URL + APP_TOKEN are mount-time inputs.
        if len(config.entrypoint_args) >= 2:
            inside_path = config.entrypoint_args[1]
        else:
            inside_path = file_meta.path
        argv.extend(["-e", f"FILE_PATH={inside_path}"])
        argv.extend(["-e", f"NC_USER_ID={user_id}"])
        for key, value in self.extra_env.items():
            argv.extend(["-e", f"{key}={value}"])

        argv.append(config.image)
        return argv


def stub_spawner_from_env() -> StubSpawner:
    """Build a StubSpawner from `ASH_NAZG_DEMO_HOST` / `ASH_NAZG_DEMO_PORT`.

    Defaults match the visible-demo flow documented in `docs/demo.md`:
    host 127.0.0.1, port 16901 (KasmVNC web client).
    """
    host = os.environ.get("ASH_NAZG_DEMO_HOST", "127.0.0.1")
    port = int(os.environ.get("ASH_NAZG_DEMO_PORT", "16901"))
    return StubSpawner(host=host, port=port)
