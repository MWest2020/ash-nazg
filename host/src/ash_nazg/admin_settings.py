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
import json
from pathlib import Path
from typing import Final

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ash_nazg.appapi import APP_ID
from ash_nazg.initial_state import AdminInitialState, build_initial_state

# vite-build output. main.py mounts /static at this path.
STATIC_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent / "static"
MANIFEST_PATH: Final[Path] = STATIC_ROOT / "manifest.json"

# Vite uses the source-relative entry path as the manifest key.
ADMIN_ENTRY_KEY: Final[str] = "src/admin-settings-main.ts"

INITIAL_STATE_KEY: Final[str] = "config"

router = APIRouter(tags=["admin"])


def _load_manifest() -> dict[str, dict[str, object]] | None:
    """Read vite's manifest.json. Returns None if not built yet."""
    if not MANIFEST_PATH.is_file():
        return None
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


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


def _bundle_tags(manifest: dict[str, dict[str, object]] | None) -> str:
    """Render the <script> + <link rel=stylesheet> tags for the bundle."""
    if manifest is None:
        return (
            '<div role="alert" '
            'style="padding:12px;border:1px solid #c33;background:#fee;'
            'color:#600;border-radius:4px;font-family:sans-serif;">'
            "Frontend bundle not built yet. "
            "Run <code>cd frontend &amp;&amp; npm ci --ignore-scripts &amp;&amp; "
            "npm run build</code> to populate <code>host/static/</code>."
            "</div>"
        )

    entry = manifest.get(ADMIN_ENTRY_KEY)
    if not isinstance(entry, dict):
        return (
            '<div role="alert" '
            'style="padding:12px;border:1px solid #c33;background:#fee;'
            'color:#600;border-radius:4px;font-family:sans-serif;">'
            f"manifest.json missing entry for "
            f"<code>{html.escape(ADMIN_ENTRY_KEY)}</code>."
            "</div>"
        )

    js_file = entry.get("file")
    css_files = entry.get("css") or []

    parts: list[str] = []
    if isinstance(css_files, list):
        for css in css_files:
            if isinstance(css, str):
                parts.append(
                    f'<link rel="stylesheet" '
                    f'href="/static/{html.escape(css, quote=True)}">'
                )
    if isinstance(js_file, str):
        parts.append(
            f'<script type="module" '
            f'src="/static/{html.escape(js_file, quote=True)}"></script>'
        )
    return "\n        ".join(parts)


@router.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings_page() -> HTMLResponse:
    """Render the admin settings HTML shell."""
    state = build_initial_state()
    manifest = _load_manifest()

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Ash Nazg — admin settings</title>
</head>
<body>
    {_initial_state_input(state)}
    <div id="ash-nazg-admin-settings"></div>
    {_bundle_tags(manifest)}
</body>
</html>
"""
    return HTMLResponse(content=body)
