"""Concrete I/O adapters for FileReader and AuditLogger.

Both talk to Nextcloud via HTTP using the AppAPI-issued credentials.
`InMemoryFileReader` and `InMemoryAuditLogger` exist for tests and the
demo-mode bootstrap where no live NC is in front.

The WebDAV reader does only what the dispatcher needs: a range read of
the first ≤512 bytes (detection spec) and a HEAD for size. It does NOT
mount the user's Files inside the host shim — that's davfs2's job
inside the engine container.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


# --- In-memory (tests + demo bootstrap) ------------------------------------


class InMemoryFileReader:
    """FileReader backed by a dict — for demo bootstrap and unit tests.

    `head_by_path` maps a Files-relative path to the file's leading bytes.
    `size_by_path` maps the same path to the total size in bytes; falls
    back to `len(head)` when not declared.
    """

    def __init__(
        self,
        head_by_path: dict[str, bytes] | None = None,
        size_by_path: dict[str, int] | None = None,
    ) -> None:
        self._heads = dict(head_by_path or {})
        self._sizes = dict(size_by_path or {})

    def put(self, path: str, head: bytes, size: int | None = None) -> None:
        self._heads[path] = head
        if size is not None:
            self._sizes[path] = size

    async def read_head(self, files_path: str, byte_count: int) -> bytes:
        return self._heads.get(files_path, b"")[:byte_count]

    async def get_size(self, files_path: str) -> int:
        if files_path in self._sizes:
            return self._sizes[files_path]
        return len(self._heads.get(files_path, b""))


class InMemoryAuditLogger:
    """Audit logger that accumulates entries in memory — tests + demo."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def log(self, **fields: Any) -> None:
        self.entries.append(fields)


# --- WebDAV file reader ----------------------------------------------------


class WebDavFileReader:
    """FileReader against Nextcloud's WebDAV endpoint.

    Uses HTTP Range / HEAD against /remote.php/dav/files/<user>/<path>.
    Authentication is the AppAPI-issued per-user token; in v1 the host
    treats the user_id + token as basic-auth credentials (AppAPI 5.x
    docs).
    """

    def __init__(
        self,
        *,
        base_url: str,
        user_id: str,
        token: str,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.token = token
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _url_for(self, files_path: str) -> str:
        path = quote(files_path.lstrip("/"), safe="/")
        return f"{self.base_url}/remote.php/dav/files/{self.user_id}/{path}"

    async def read_head(self, files_path: str, byte_count: int) -> bytes:
        url = self._url_for(files_path)
        end = max(0, byte_count - 1)
        resp = await self._client.get(
            url,
            auth=(self.user_id, self.token),
            headers={"Range": f"bytes=0-{end}"},
        )
        # 206 Partial Content on success; some servers return 200 with
        # the whole body when Range is unsupported — both are usable.
        if resp.status_code not in (200, 206):
            raise RuntimeError(
                f"WebDAV range read failed for {files_path}: "
                f"{resp.status_code} {resp.text[:200]}"
            )
        return resp.content[:byte_count]

    async def get_size(self, files_path: str) -> int:
        url = self._url_for(files_path)
        resp = await self._client.head(
            url, auth=(self.user_id, self.token), follow_redirects=True
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"WebDAV HEAD failed for {files_path}: "
                f"{resp.status_code} {resp.text[:200]}"
            )
        cl = resp.headers.get("Content-Length")
        if cl is None:
            raise RuntimeError(
                f"WebDAV HEAD for {files_path} missing Content-Length"
            )
        return int(cl)


# --- OCS audit logger ------------------------------------------------------


class OcsAuditLogger:
    """Writes audit-log entries via Nextcloud's OCS audit-log API.

    Currently a thin wrapper: each call POSTs the supplied fields as a
    single audit entry. If the OCS call fails, the dispatcher's
    try/except absorbs the error and logs locally — audit failures
    must never break dispatch (sandbox-spec safety: dispatch always
    proceeds; observability is degraded but not absent).
    """

    OCS_PATH = "/ocs/v2.php/apps/admin_audit/api/v1/event"

    def __init__(
        self,
        *,
        base_url: str,
        user_id: str,
        token: str,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.token = token
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def log(self, **fields: Any) -> None:
        url = f"{self.base_url}{self.OCS_PATH}"
        payload = {
            "app": "ash_nazg",
            "event": fields.pop("outcome", "ash_nazg.execution"),
            "data": fields,
        }
        resp = await self._client.post(
            url,
            auth=(self.user_id, self.token),
            headers={"OCS-APIREQUEST": "true"},
            json=payload,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"OCS audit log POST failed: {resp.status_code} "
                f"{resp.text[:200]}"
            )
