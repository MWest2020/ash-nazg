"""FastAPI entrypoint for the Ash Nazg host container.

This module is a scaffold. It exposes only the endpoints AppAPI
requires for liveness (`/health`, `/heartbeat`) plus a `/run` stub
that returns 501. Dispatcher, audit logging and engine wiring land
in the `wire-dosbox-engine` change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from ash_nazg import __version__
from ash_nazg.admin_settings import router as admin_settings_router
from ash_nazg.appapi import APP_ID
from ash_nazg.selftest import router as selftest_router

VERSION: Final[str] = __version__
STATIC_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent / "static"

app = FastAPI(
    title="Ash Nazg host",
    description="ExApp dispatcher for sandboxed legacy runtimes.",
    version=VERSION,
)

app.include_router(selftest_router)
app.include_router(admin_settings_router)

# Serve the vite-built frontend bundle. The directory may not exist
# on a fresh checkout; mount with check_dir=False so the app still
# starts and the admin page can render its "not built yet" warning.
if STATIC_ROOT.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")


@app.get("/health", tags=["liveness"])
async def health() -> dict[str, str]:
    return {"status": "ok", "app": APP_ID, "version": VERSION}


@app.get("/heartbeat", tags=["liveness"], response_class=PlainTextResponse)
async def heartbeat() -> str:
    return "ok"


@app.post("/run", tags=["dispatch"])
async def run() -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "error": "not_implemented",
            "detail": "Dispatcher lands in change wire-dosbox-engine.",
        },
    )
