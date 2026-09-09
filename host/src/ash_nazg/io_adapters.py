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

import base64
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

# AppAPI log levels mirror NC's: 0 debug, 1 info, 2 warning …
_LOG_LEVEL_INFO = 1

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

    async def download_to(self, files_path: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self._heads.get(files_path, b""))

    async def get_size(self, files_path: str) -> int:
        if files_path in self._sizes:
            return self._sizes[files_path]
        if files_path not in self._heads:
            # Same shape as the WebDAV reader on a missing path, so tests
            # exercise the dispatcher's not-found path rather than a
            # zero-byte file that exists nowhere.
            raise FileNotFoundError(files_path)
        return len(self._heads[files_path])


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
    Authenticates via the AppAPI-prescribed header set:

      EX-APP-ID:               <appid>
      EX-APP-VERSION:          <version>
      AUTHORIZATION-APP-API:   base64(<user_id>:<app_secret>)

    NC's AppAPI middleware (BasicAuthMiddleware / ExAppUsersMiddleware)
    recognises this and impersonates the user when authorising WebDAV
    access. Basic-auth with the APP_SECRET does not work for WebDAV —
    only OCS endpoints accept that form.
    """

    def __init__(
        self,
        *,
        base_url: str,
        user_id: str,
        token: str,
        app_id: str = "ash_nazg",
        app_version: str = "0.0.0",
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.token = token
        self.app_id = app_id
        self.app_version = app_version
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _url_for(self, files_path: str) -> str:
        path = quote(files_path.lstrip("/"), safe="/")
        return f"{self.base_url}/remote.php/dav/files/{self.user_id}/{path}"

    def _auth_headers(self) -> dict[str, str]:
        import base64
        raw = f"{self.user_id}:{self.token}".encode()
        return {
            "EX-APP-ID": self.app_id,
            "EX-APP-VERSION": self.app_version,
            "AUTHORIZATION-APP-API": base64.b64encode(raw).decode("ascii"),
        }

    async def read_head(self, files_path: str, byte_count: int) -> bytes:
        url = self._url_for(files_path)
        end = max(0, byte_count - 1)
        headers = {**self._auth_headers(), "Range": f"bytes=0-{end}"}
        resp = await self._client.get(url, headers=headers)
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
            url, headers=self._auth_headers(), follow_redirects=True
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

    async def download_to(self, files_path: str, destination: Path) -> None:
        """Stream the whole file to `destination`.

        The in-image engine gets its binary as a plain file in a private
        session directory rather than a WebDAV mount: no davfs2, no
        mount privileges, and a session sees exactly the one file it was
        asked to run instead of the user's entire Files tree.
        """
        url = self._url_for(files_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        async with self._client.stream(
            "GET", url, headers=self._auth_headers(), follow_redirects=True
        ) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread())[:200].decode(errors="replace")
                raise RuntimeError(
                    f"WebDAV download failed for {files_path}: "
                    f"{resp.status_code} {body}"
                )
            with destination.open("wb") as fh:
                async for chunk in resp.aiter_bytes():
                    fh.write(chunk)
        destination.chmod(0o600)


# --- OCS audit logger ------------------------------------------------------


class OcsAuditLogger:
    """Writes audit-log entries via AppAPI's ExApp log endpoint.

    Each call POSTs the supplied fields as a single entry. If the OCS
    call fails, the dispatcher's try/except absorbs the error and logs
    locally — audit failures must never break dispatch (sandbox-spec
    safety: dispatch always proceeds; observability is degraded but not
    absent).

    Auth is AppAPI's, not Nextcloud's: an ExApp has no NC password, so
    basic auth returns 401 "Unauthorised" (997) no matter what it
    sends. The AUTHORIZATION-APP-API header carries
    base64(user_id:APP_SECRET), with an empty user id for the system
    context — verified live against NC 32 / AppAPI 5.
    """

    OCS_PATH = "/ocs/v2.php/apps/app_api/api/v1/log"

    def __init__(
        self,
        *,
        base_url: str,
        user_id: str,
        token: str,
        app_version: str = "0.0.0",
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.token = token
        self.app_version = app_version
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def log(self, **fields: Any) -> None:
        url = f"{self.base_url}{self.OCS_PATH}"
        entry = {
            "app": "ash_nazg",
            "event": fields.pop("outcome", "ash_nazg.execution"),
            "data": fields,
        }
        # AppAPI's log endpoint takes a level + a flat message; the
        # audit fields ride along as JSON so nothing is lost.
        payload = {"level": _LOG_LEVEL_INFO, "message": json.dumps(entry)}
        resp = await self._client.post(
            url,
            headers={
                "EX-APP-ID": "ash_nazg",
                "EX-APP-VERSION": self.app_version,
                "AUTHORIZATION-APP-API": base64.b64encode(
                    f":{self.token}".encode()
                ).decode("ascii"),
                "OCS-APIREQUEST": "true",
            },
            json=payload,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"OCS audit log POST failed: {resp.status_code} "
                f"{resp.text[:200]}"
            )
