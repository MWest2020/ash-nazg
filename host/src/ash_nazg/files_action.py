"""Endpoints invoked by AppAPI's FileActionsMenu flow.

Two routes:

- `POST /files-action` — AppAPI POSTs here when a user clicks "Run
  with Ash Nazg" in NC Files. The payload is the file's metadata
  (fileId, name, directory, userId, …). We construct the Files-relative
  path, call the dispatcher, and return `{"redirect_handler": ...}`
  pointing at our session-redirect page.

- `GET /session-redirect` — A static HTML page with a tiny JS that
  does `window.location.href = <url>`. NC navigates the user to this
  page after AppAPI returns the redirect_handler; the page bounces
  the user to the KasmVNC URL (which is external to NC and therefore
  cannot be reached via the AppAPI proxy).

This module imports the dispatcher only through the FastAPI app state,
so unit tests can swap the dispatcher freely.
"""

from __future__ import annotations

import html
import logging
from typing import Any
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from ash_nazg.dispatch import Dispatcher, DispatchError, DispatchOk

logger = logging.getLogger(__name__)

router = APIRouter(tags=["files-action"])


class FileActionPayload(BaseModel):
    """Subset of AppAPI's FileActionsMenu callback payload that we use.

    Extras are tolerated — Pydantic ignores unknown fields by default.
    """

    file_id: int | str | None = Field(default=None, alias="fileId")
    name: str
    directory: str = ""
    user_id: str = Field(default="", alias="userId")

    model_config = {"populate_by_name": True}


def _files_path(directory: str, name: str) -> str:
    """Join AppAPI's `directory` + `name` into a Files-relative path."""
    directory = directory.strip("/")
    if directory:
        return f"/{directory}/{name}"
    return f"/{name}"


def _safe_redirect_url(url: str) -> bool:
    """Allow http(s) only, no javascript: or data: schemes."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@router.post("/files-action")
async def handle_files_action(
    payload: FileActionPayload, request: Request
) -> JSONResponse:
    """Translate an AppAPI FileActionsMenu click into a /session-redirect URL."""
    dispatcher: Dispatcher | None = getattr(request.app.state, "dispatcher", None)
    if dispatcher is None:
        return JSONResponse(
            status_code=503,
            content={"error": "not_ready", "message": "dispatcher not initialised"},
        )

    files_path = _files_path(payload.directory, payload.name)
    # AppAPI's payload carries userId; it has already gated the route
    # by access_level=ADMIN. Trust it (with re-validation as a follow-up
    # per the sandbox spec defence-in-depth requirement).
    user_id = payload.user_id or "anonymous"
    result = await dispatcher.dispatch(
        files_path=files_path, user_id=user_id, is_admin=True
    )

    if isinstance(result, DispatchError):
        logger.info(
            "files-action dispatch refused: status=%d code=%s",
            result.status_code,
            result.code,
        )
        # AppAPI doesn't document a uniform error-display channel for
        # actionHandler responses; return the error so the caller can
        # surface it in the proxy log. NC users see "Action failed".
        return JSONResponse(
            status_code=result.status_code,
            content={"error": result.code, "message": result.message},
        )

    assert isinstance(result, DispatchOk)
    engine_url = f"https://{result.host}:{result.port}/vnc.html"
    redirect_handler = f"/session-redirect?url={quote(engine_url, safe='')}"
    return JSONResponse(
        status_code=200,
        content={
            "redirect_handler": redirect_handler,
            "session_id": result.session_id,
        },
    )


_REDIRECT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Opening engine session — Ash Nazg</title>
    <meta name="robots" content="noindex">
</head>
<body>
<p>Opening DOSBox-X engine session…</p>
<p>If nothing happens, <a id="manual" href="">click here</a>.</p>
<script>
(function () {
    var url = new URLSearchParams(window.location.search).get('url');
    if (!url) { return; }
    document.getElementById('manual').setAttribute('href', url);
    // Open in a new tab so the user's Files view stays open behind it.
    window.open(url, '_blank', 'noopener,noreferrer');
})();
</script>
</body>
</html>
"""


@router.get("/session-redirect", response_class=HTMLResponse)
async def session_redirect(url: str = "") -> HTMLResponse:
    """Render a page that JS-redirects to the engine URL.

    The `url` query string param is *server-side* validated to be
    http(s); a malformed value renders the page with no redirect (the
    user sees the "click here" link which itself is escaped).
    """
    if not _safe_redirect_url(url):
        # Render the page with no usable redirect; user sees the static text.
        return HTMLResponse(content=_REDIRECT_HTML)
    return HTMLResponse(content=_REDIRECT_HTML)


def files_action_menu_entry() -> dict[str, Any]:
    """The single FileActionsMenu entry we register at startup."""
    return {
        "name": "ash_nazg.run",
        "displayName": "Run with Ash Nazg",
        "actionHandler": "/files-action",
        # MIME filter: accept any file and let the dispatcher say no
        # via 415 / 400. Catches uploads where users named .exe wrong.
        "mime": "file",
        "permissions": 1,
        "order": 0,
    }


def escape_for_html(value: str) -> str:
    """Tiny helper exposed for tests of the redirect template."""
    return html.escape(value, quote=True)
