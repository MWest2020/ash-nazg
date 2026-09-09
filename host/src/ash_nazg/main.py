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

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse
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
from ash_nazg.session_page import router as session_page_router
from ash_nazg.spawners import (
    InImageSpawner,
    stub_spawner_from_env,
)
from ash_nazg.stream_proxy import router as stream_proxy_router

# uvicorn configures its own loggers and leaves the root logger alone, so
# without this the app's own log lines never appear anywhere — which turns
# every production question into a rebuild. Level via env so an admin can
# turn it down without a new image.
logging.basicConfig(
    level=os.environ.get("ASH_NAZG_LOG_LEVEL", "INFO").upper(),
    format="%(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

VERSION: Final[str] = __version__
STATIC_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent / "static"

MODE_DEMO: Final[str] = "demo"
MODE_NEXTCLOUD: Final[str] = "nextcloud"


def _resolved_mode() -> str:
    """Pick the dispatcher's operating mode from env.

    Order:
    - ASH_NAZG_MODE set explicitly → use it verbatim.
    - Else, if AppAPI env vars present (HaRP-spawned containers)
      → nextcloud.
    - Else → demo.
    """
    explicit = os.environ.get("ASH_NAZG_MODE")
    if explicit:
        return explicit.lower()
    if "APP_SECRET" in os.environ and "NEXTCLOUD_URL" in os.environ:
        return MODE_NEXTCLOUD
    return MODE_DEMO


def _make_dependencies() -> tuple[FileReader, SessionSpawner, AuditLogger]:
    """Pick FileReader/SessionSpawner/AuditLogger based on env."""
    mode = _resolved_mode()
    if mode == MODE_NEXTCLOUD:
        nc_url = os.environ["NEXTCLOUD_URL"]
        user_id = os.environ.get("EX_APP_USER", "admin")
        token = os.environ["APP_SECRET"]
        reader = WebDavFileReader(base_url=nc_url, user_id=user_id, token=token)
        audit = OcsAuditLogger(
            base_url=nc_url,
            user_id=user_id,
            token=token,
            app_version=os.environ.get("APP_VERSION", VERSION),
        )
        # Sessions run inside this container: an ExApp cannot spawn a
        # sibling container (no docker CLI, no socket, no HaRP spawn API
        # for ExApps). See wire-dosbox-engine, "Open ontwerpbesluit".
        spawner = InImageSpawner(file_reader=reader)
        logger.info("dispatcher mode=nextcloud spawner=in-image")
        return reader, spawner, audit

    logger.info("dispatcher mode=demo (stub spawner + in-memory adapters)")
    return (
        InMemoryFileReader(),
        stub_spawner_from_env(),
        InMemoryAuditLogger(),
    )


async def _register_files_action_menu(
    *, retries: int = 3, retry_delay_s: float = 2.0
) -> None:
    """Register our right-click menu entry with AppAPI.

    In `ASH_NAZG_MODE=nextcloud` only — the demo bootstrap has no
    AppAPI to talk to. Called from the `PUT /enabled` handler, because
    AppAPI answers OCS calls from an ExApp with 401 until that ExApp is
    enabled — so a few short retries are enough, where a startup-time
    register needed minutes of them. Failure logs and continues (the
    host stays up; AppAPI calls `/enabled` again on the next enable).
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
        await client.register_file_action(
            entry, retries=retries, retry_delay_s=retry_delay_s
        )
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

    # The FileActionsMenu entry is registered from `PUT /enabled`, not
    # here: AppAPI rejects OCS calls from an ExApp that is not yet
    # enabled, and at lifespan time it never is.

    yield

    # Sessions are children of this process: leaving them behind on
    # shutdown would orphan an emulator per Run (sandbox spec, "Engine
    # session lifecycle bounded" — host shutdown terminates sessions).
    terminate_all = getattr(spawner, "terminate_all", None)
    if callable(terminate_all):
        await terminate_all()

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
app.include_router(session_page_router)
app.include_router(stream_proxy_router)

# Serve the vite-built frontend bundle. The directory may not exist
# on a fresh checkout; only mount when present so the app still starts
# and the admin page can render its "not built yet" warning.
if STATIC_ROOT.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")


# --- Endpoints ---------------------------------------------------------------


@app.get("/health", tags=["liveness"])
async def health() -> dict[str, str]:
    return {"status": "ok", "app": APP_ID, "version": VERSION}


@app.get("/heartbeat", tags=["liveness"])
async def heartbeat() -> dict[str, str]:
    """AppAPI's liveness probe.

    The body matters, not just the status: AppAPI reads `status` and
    logs "Failed heartbeat … status=200" for anything else, so a
    plain-text `ok` leaves the ExApp stuck in registration forever.
    """
    return {"status": "ok"}


async def _report_init_done() -> None:
    """Tell AppAPI the ExApp finished initialising."""
    try:
        config = AppApiConfig.from_environment()
    except KeyError:
        logger.warning("AppAPI config env vars missing — skipping init-status report")
        return
    client = AppApiClient(config)
    try:
        await client.set_init_status(100)
    except Exception:
        logger.exception("init-status report failed")
    finally:
        await client.aclose()


@app.post("/init", tags=["appapi"])
async def appapi_init(background: BackgroundTasks) -> dict[str, str]:
    """AppAPI's post-deploy init step.

    There is nothing to download — the engine images are pulled per
    session — so we report 100 % straight away, in the background so
    this handler can answer immediately. Until that report lands,
    `app:register --wait-finish` blocks.
    """
    background.add_task(_report_init_done)
    return {}


@app.put("/enabled", tags=["appapi"])
async def appapi_enabled(enabled: int = 0) -> dict[str, str]:
    """AppAPI enable/disable hook.

    An empty `error` means "accepted". Enabling is also the first
    moment AppAPI accepts OCS calls from us, so the Files right-click
    entry is registered here.
    """
    if enabled:
        await _register_files_action_menu()
    return {"error": ""}


class RunRequest(BaseModel):
    path: str = Field(
        description="Files-relative path of the binary to run (e.g. /Programs/keen1.exe)."
    )


class RunResponse(BaseModel):
    session_id: str
    host: str
    port: int


@app.delete("/sessions/{session_id}", tags=["dispatch"])
async def close_session(session_id: str, request: Request) -> JSONResponse:
    """End a session the caller started.

    The claim that makes a second Run of the same file return 409 lives
    until this is called (or the session hits its maximum duration), so
    closing is what lets a user run the same binary again.
    """
    user = extract_user(request, admin_route=True)
    dispatcher: Dispatcher = request.app.state.dispatcher
    if await dispatcher.close(session_id, user_id=user.user_id):
        return JSONResponse(status_code=200, content={"session_id": session_id,
                                                      "status": "closed"})
    return JSONResponse(
        status_code=404,
        content={"error": "unknown_session",
                 "message": "no such session for this user"},
    )


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
