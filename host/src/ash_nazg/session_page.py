"""Session page — the screen a Run navigates to.

Renders the shell for the `SessionStatus` bundle: the session id, and a
place for the stream once `streaming-proxy` routes KasmVNC through the
AppAPI proxy. Until then the page reports that the session is running
and offers to close it, which is honest about what exists.
"""

from __future__ import annotations

import html
from typing import Final

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ash_nazg.bundle import bundle_tags, load_manifest

SESSION_ENTRY_KEY: Final[str] = "src/session-status-main.ts"

router = APIRouter(tags=["dispatch"])


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
async def session_page(session_id: str) -> HTMLResponse:
    """Render the session HTML shell.

    The id is passed as a data attribute rather than interpolated into
    script: it arrives from the URL, so it is escaped and never reaches
    a JavaScript context.
    """
    manifest = load_manifest()
    safe_id = html.escape(session_id, quote=True)
    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Ash Nazg — session</title>
</head>
<body>
    <div id="ash-nazg-session" data-session-id="{safe_id}"></div>
    {bundle_tags(manifest, SESSION_ENTRY_KEY)}
</body>
</html>
"""
    return HTMLResponse(content=body)
