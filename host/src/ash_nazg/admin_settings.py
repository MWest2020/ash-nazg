"""Admin settings page — FastAPI router.

Per task §11.1: serves the route declared in `appinfo/info.xml` for
the Nextcloud admin settings page. Renders a minimal HTML shell
that:

  1. injects the `AdminInitialState` via a Nextcloud-conventional
     hidden input (`initial-state-<app>-<key>`, base64-encoded JSON)
     so `@nextcloud/initial-state`'s `loadState()` can read it;
  2. renders the mount target div the Vue bundle expects
     (`#ash-nazg-admin-settings`);
  3. injects the hashed `<script>` tag from the vite-emitted
     `manifest.json` under `host/static/`.

If the frontend bundle has not been built yet, the page renders a
visible-but-non-fatal warning telling the developer to run
`npm run build`. This is intentional — the scaffold should never
500 just because someone hasn't run the frontend build.
"""

from __future__ import annotations

import base64
import html
from typing import Final

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ash_nazg.appapi import APP_ID
from ash_nazg.bundle import bundle_tags, load_manifest
from ash_nazg.initial_state import AdminInitialState, build_initial_state

# Vite uses the source-relative entry path as the manifest key.
ADMIN_ENTRY_KEY: Final[str] = "src/admin-settings-main.ts"

INITIAL_STATE_KEY: Final[str] = "config"

router = APIRouter(tags=["admin"])


def _initial_state_input(state: AdminInitialState) -> str:
    """Render the Nextcloud-conventional hidden input for loadState()."""
    payload = state.model_dump_json()
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    input_id = f"initial-state-{APP_ID}-{INITIAL_STATE_KEY}"
    return (
        f'<input type="hidden" '
        f'id="{html.escape(input_id, quote=True)}" '
        f'value="{html.escape(encoded, quote=True)}">'
    )


@router.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings_page() -> HTMLResponse:
    """Render the admin settings HTML shell."""
    state = build_initial_state()
    manifest = load_manifest()

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Ash Nazg — admin settings</title>
</head>
<body>
    {_initial_state_input(state)}
    <div id="ash-nazg-admin-settings"></div>
    {bundle_tags(manifest, ADMIN_ENTRY_KEY)}
</body>
</html>
"""
    return HTMLResponse(content=body)
