"""FastAPI entrypoint for the Ash Nazg host container.

Wires up:
- engine registry (discovered from `ash_nazg.engines` entrypoints)
- dispatcher (with chosen FileReader / SessionSpawner / AuditLogger)
- routes: /health, /heartbeat, /run, /admin/settings, /selftest, /static

Dispatcher dependencies are selected by env at startup:

- `ASH_NAZG_MODE=demo` (default): in-memory file reader + audit logger,
  stub spawner pointed at the always-on engine demo container. The
  /run endpoint returns the demo URL the frontend should navigate to.
- `ASH_NAZG_MODE=nextcloud`: real WebDAV reader + OCS audit logger
  using AppAPI-injected creds, docker-subprocess spawner against the
  podman/docker socket bound into the host container.

This lets the trunk-based test suite + the visible demo run without a
live NC, while the level-3 verifier exercises the real path.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ash_nazg import __version__
from ash_nazg.admin_settings import router as admin_settings_router
from ash_nazg.appapi import APP_ID, AppApiConfig
from ash_nazg.appapi_client import AppApiClient, FileActionsMenuEntry
from ash_nazg.dispatch import (
    ActiveSessionTracker,
    AuditLogger,
    Dispatcher,
    DispatchError,
    DispatchOk,
    FileReader,
    SessionSpawner,
)
from ash_nazg.engines.registry import discover_engines
from ash_nazg.files_action import (
    files_action_menu_entry,
)
from ash_nazg.files_action import (
    router as files_action_router,
)
from ash_nazg.io_adapters import (
    InMemoryAuditLogger,
    InMemoryFileReader,
    OcsAuditLogger,
    WebDavFileReader,
)
from ash_nazg.request_context import extract_user
from ash_nazg.selftest import router as selftest_router
from ash_nazg.spawners import (
    DockerSubprocessSpawner,
    stub_spawner_from_env,
)

logger = logging.getLogger(__name__)

VERSION: Final[str] = __version__
STATIC_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent / "static"

MODE_DEMO: Final[str] = "demo"
MODE_NEXTCLOUD: Final[str] = "nextcloud"
DEFAULT_NETWORK_ENV: Final[str] = "ASH_NAZG_ENGINE_NETWORK"


def _make_dependencies() -> tuple[FileReader, SessionSpawner, AuditLogger]:
    """Pick FileReader/SessionSpawner/AuditLogger based on env."""
    mode = os.environ.get("ASH_NAZG_MODE", MODE_DEMO).lower()
    if mode == MODE_NEXTCLOUD:
        nc_url = os.environ["NEXTCLOUD_URL"]
        user_id = os.environ.get("EX_APP_USER", "admin")
        token = os.environ["APP_SECRET"]
        reader = WebDavFileReader(base_url=nc_url, user_id=user_id, token=token)
        audit = OcsAuditLogger(base_url=nc_url, user_id=user_id, token=token)
        network = os.environ.get(DEFAULT_NETWORK_ENV)
        spawner = DockerSubprocessSpawner(
            network=network,
            extra_env={"NEXTCLOUD_URL": nc_url, "APP_TOKEN": token},
        )
        logger.info("dispatcher mode=nextcloud network=%s", network)
        return reader, spawner, audit

    logger.info("dispatcher mode=demo (stub spawner + in-memory adapters)")
    return (
        InMemoryFileReader(),
        stub_spawner_from_env(),
        InMemoryAuditLogger(),
    )


async def _register_files_action_menu() -> None:
    """Register our right-click menu entry with AppAPI.

    In `ASH_NAZG_MODE=nextcloud` only — the demo bootstrap has no
    AppAPI to talk to. Failure logs and continues (the host stays up
    even if AppAPI is briefly unreachable; AppAPI re-polls heartbeats
    and we re-register on next start).
    """
    try:
        config = AppApiConfig.from_environment()
    except KeyError:
        logger.warning(
            "AppAPI config env vars missing — skipping FileActionsMenu register"
        )
        return
    entry_dict = files_action_menu_entry()
    entry = FileActionsMenuEntry(
        name=entry_dict["name"],
        display_name=entry_dict["displayName"],
        action_handler=entry_dict["actionHandler"],
        mime=entry_dict["mime"],
        permissions=entry_dict["permissions"],
        order=entry_dict["order"],
    )
    client = AppApiClient(config)
    try:
        await client.register_file_action(entry)
    except Exception:
        logger.exception("FileActionsMenu registration failed — continuing anyway")
    finally:
        await client.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build dispatcher dependencies once per process."""
    registry = discover_engines()
    reader, spawner, audit = _make_dependencies()
    app.state.registry = registry
    app.state.reader = reader
    app.state.dispatcher = Dispatcher(
        registry=registry,
        file_reader=reader,
        spawner=spawner,
        audit=audit,
        active_sessions=ActiveSessionTracker(),
    )
    logger.info(
        "ash-nazg host started — engines=%s",
        [r.engine.id for r in registry.all()],
    )

    if os.environ.get("ASH_NAZG_MODE", MODE_DEMO).lower() == MODE_NEXTCLOUD:
        await _register_files_action_menu()

    yield
    # Best-effort cleanup of HTTP adapters
    aclose = getattr(reader, "aclose", None)
    if callable(aclose):
        await aclose()
    aclose = getattr(audit, "aclose", None)
    if callable(aclose):
        await aclose()


app = FastAPI(
    title="Ash Nazg host",
    description="ExApp dispatcher for sandboxed legacy runtimes.",
    version=VERSION,
    lifespan=lifespan,
)

app.include_router(selftest_router)
app.include_router(admin_settings_router)
app.include_router(files_action_router)

# Serve the vite-built frontend bundle. The directory may not exist
# on a fresh checkout; only mount when present so the app still starts
# and the admin page can render its "not built yet" warning.
if STATIC_ROOT.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")


# --- Endpoints ---------------------------------------------------------------


@app.get("/health", tags=["liveness"])
async def health() -> dict[str, str]:
    return {"status": "ok", "app": APP_ID, "version": VERSION}


@app.get("/heartbeat", tags=["liveness"], response_class=PlainTextResponse)
async def heartbeat() -> str:
    return "ok"


class RunRequest(BaseModel):
    path: str = Field(
        description="Files-relative path of the binary to run (e.g. /Programs/keen1.exe)."
    )


class RunResponse(BaseModel):
    session_id: str
    host: str
    port: int


@app.post("/run", tags=["dispatch"])
async def run(req: RunRequest, request: Request) -> JSONResponse:
    # The `/run` info.xml route is declared ADMIN — AppAPI gates it.
    user = extract_user(request, admin_route=True)

    dispatcher: Dispatcher = request.app.state.dispatcher
    result = await dispatcher.dispatch(
        files_path=req.path,
        user_id=user.user_id,
        is_admin=user.is_admin,
    )
    if isinstance(result, DispatchOk):
        return JSONResponse(
            status_code=200,
            content=RunResponse(
                session_id=result.session_id, host=result.host, port=result.port
            ).model_dump(),
        )
    assert isinstance(result, DispatchError)
    return JSONResponse(
        status_code=result.status_code,
        content={"error": result.code, "message": result.message},
    )
