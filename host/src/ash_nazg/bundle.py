"""Vite bundle lookup shared by the pages the host renders.

Both the admin settings page and the session page inject the hashed
asset filenames vite writes into `host/static/manifest.json`. Neither
should 500 because the frontend has not been built — they render a
visible warning instead, which is what a developer needs to see.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Final

# vite-build output. main.py mounts /static at this path.
STATIC_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent / "static"
MANIFEST_PATH: Final[Path] = STATIC_ROOT / "manifest.json"


def _warning(message: str) -> str:
    return (
        '<div role="alert" '
        'style="padding:12px;border:1px solid #c33;background:#fee;'
        'color:#600;border-radius:4px;font-family:sans-serif;">'
        f"{message}"
        "</div>"
    )


def load_manifest() -> dict[str, dict[str, object]] | None:
    """Read vite's manifest.json. Returns None if not built yet."""
    if not MANIFEST_PATH.is_file():
        return None
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def relative_base(path: str) -> str:
    """How many levels up from `path` the app's own root is.

    The pages the app renders are reached through a proxy prefix it can
    neither see nor guess (`/index.php/apps/app_api/proxy/ash_nazg/…` in
    one case, `/exapps/ash_nazg/…` in another). An absolute `/static/…`
    URL therefore resolves against Nextcloud's root and 404s. A relative
    one resolves against whatever prefix the browser used.
    """
    segments = [s for s in path.split("/") if s]
    depth = len(segments) if path.endswith("/") else len(segments) - 1
    return "../" * max(depth, 0)


def bundle_tags(
    manifest: dict[str, dict[str, object]] | None,
    entry_key: str,
    base: str = "",
) -> str:
    """Render the <script> + <link rel=stylesheet> tags for one entry."""
    if manifest is None:
        return _warning(
            "Frontend bundle not built yet. "
            "Run <code>cd frontend &amp;&amp; npm ci --ignore-scripts &amp;&amp; "
            "npm run build</code> to populate <code>host/static/</code>."
        )

    entry = manifest.get(entry_key)
    if not isinstance(entry, dict):
        return _warning(
            "manifest.json missing entry for "
            f"<code>{html.escape(entry_key)}</code>."
        )

    js_file = entry.get("file")
    css_files = entry.get("css") or []

    parts: list[str] = []
    if isinstance(css_files, list):
        for css in css_files:
            if isinstance(css, str):
                parts.append(
                    f'<link rel="stylesheet" '
                    f'href="{base}static/{html.escape(css, quote=True)}">'
                )
    if isinstance(js_file, str):
        parts.append(
            f'<script type="module" '
            f'src="{base}static/{html.escape(js_file, quote=True)}"></script>'
        )
    return "\n        ".join(parts)
