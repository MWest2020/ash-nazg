"""The session stream: HTTP and websocket, relayed to the session's VNC server.

Why the shim relays at all: AppAPI allocates one port per ExApp, and the
sessions listen on ports of their own behind it. Nothing else can bridge
the two.

Why the browser must use `/exapps/<appid>/…` for this and not the
`app_api/proxy` URL the rest of the app uses: measured on NC 32.0.14 —
the proxy is a PHP controller and cannot return `101 Switching
Protocols`. The upgrade reaches the ExApp, which accepts it, but the
handshake never completes at the client. The `/exapps` path is routed
straight to HaRP by the web server in front of Nextcloud and carries the
upgrade end to end, with HaRP still enforcing the route's declared
access level. See the change's `design.md`.

Scope, per the "boring valkuil" this change inherited: forward bytes.
No VNC client, no RFB, no reimplementation of anything KasmVNC already
does.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Final
from urllib.parse import urlencode

import httpx
import websockets
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from websockets.exceptions import WebSocketException

from ash_nazg.request_context import AUTH_HEADER, extract_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dispatch"])

# Headers that describe one hop, not the payload; forwarding them breaks
# the next hop's framing.
_HOP_BY_HOP: Final[frozenset[str]] = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host",
    "content-length",
})

# Closing code for "this is not your session, or it does not exist". The
# websocket equivalent of the 404 the HTTP route answers: one code for
# both cases, so the endpoint is not an oracle for session ids.
_WS_NOT_FOUND: Final[int] = 4404


def _target(app, session_id: str, user_id: str) -> tuple[int, str] | None:
    """(port, basic-auth header) for a session this user owns, else None."""
    dispatcher = getattr(app.state, "dispatcher", None)
    if dispatcher is None or not user_id:
        return None
    owner = dispatcher.active.owner_of(session_id)
    if owner is None or owner[0] != user_id:
        return None
    spawner = dispatcher.spawner
    port = getattr(spawner, "port_for", lambda _s: None)(session_id)
    credentials = getattr(spawner, "credentials_for", lambda _s: None)(session_id)
    if port is None or credentials is None:
        return None
    raw = f"{credentials[0]}:{credentials[1]}".encode()
    return port, "Basic " + base64.b64encode(raw).decode("ascii")


# Request headers that must not travel on: the caller's Nextcloud
# credentials and cookies have no business at the VNC server, and its own
# Authorization is added below. Header names arrive lower-cased, so
# leaving these in would send *two* Authorization headers — the VNC
# server reads the first, sees Nextcloud's, and answers 401. That cost an
# afternoon once; hence this comment.
_STRIP_ON_REQUEST: Final[frozenset[str]] = frozenset({
    "authorization", "cookie", "authorization-app-api", "ex-app-id",
    "ex-app-version",
})


def _forwardable(headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}


def _request_headers(headers, authorization: str) -> dict[str, str]:
    return {
        k: v for k, v in headers.items()
        if k.lower() not in _HOP_BY_HOP and k.lower() not in _STRIP_ON_REQUEST
    } | {"Authorization": authorization}


@router.get("/sessions/{session_id}/stream/{path:path}")
async def stream_http(session_id: str, path: str, request: Request) -> Response:
    """Relay one HTTP request to the session's VNC server.

    This serves KasmVNC's own web client and its assets. The session's
    credentials are added here, so they never travel through a URL that
    a browser history or a proxy log could keep.
    """
    user = extract_user(request, admin_route=True)
    target = _target(request.app, session_id, user.user_id)
    if target is None:
        logger.info(
            "stream: refused request for session %s (caller=%r, auth header %s)",
            session_id,
            user.user_id,
            "present" if request.headers.get(AUTH_HEADER) else "absent",
        )
        return Response(status_code=404, content='{"error":"unknown_session"}',
                        media_type="application/json")
    port, authorization = target

    query = urlencode(list(request.query_params.multi_items()))
    url = f"http://127.0.0.1:{port}/{path}" + (f"?{query}" if query else "")
    headers = _request_headers(request.headers, authorization)

    client = httpx.AsyncClient(timeout=30.0)
    try:
        upstream = await client.send(
            client.build_request("GET", url, headers=headers), stream=True
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        logger.info("stream: upstream unreachable for %s: %s", session_id, exc)
        return Response(status_code=502, content='{"error":"engine_unreachable"}',
                        media_type="application/json")

    _touch(request.app, session_id)

    async def body():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        headers=_forwardable(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


@router.websocket("/sessions/{session_id}/stream/{path:path}")
async def stream_ws(websocket: WebSocket, session_id: str, path: str) -> None:
    """Relay the session's websocket, both directions, until either end stops."""
    user = extract_user(websocket, admin_route=True)
    target = _target(websocket.app, session_id, user.user_id)
    if target is None:
        # Refuse before the upgrade completes: a relay that authorises
        # afterwards has already handed out the socket. Log enough to tell
        # "wrong user" from "no identity at all" — the second means the
        # proxy in front did not pass the header, which looks identical
        # from the browser and is a very different problem.
        logger.info(
            "stream: refused websocket for session %s (caller=%r, auth header %s)",
            session_id,
            user.user_id,
            "present" if websocket.headers.get(AUTH_HEADER) else "absent",
        )
        await websocket.close(code=_WS_NOT_FOUND)
        return
    port, authorization = target

    query = urlencode(list(websocket.query_params.multi_items()))
    url = f"ws://127.0.0.1:{port}/{path}" + (f"?{query}" if query else "")
    subprotocols = websocket.scope.get("subprotocols") or []

    try:
        upstream = await websockets.connect(
            url,
            additional_headers={
                "Authorization": authorization,
                # KasmVNC answers an upgrade without an Origin header with
                # 404 — not 400, not 403, a plain "no such path", which
                # sends you hunting for the wrong websocket path for an
                # afternoon. It does not check the value, so this is the
                # engine's own origin: nothing about Nextcloud needs to
                # travel to the engine.
                "Origin": f"http://127.0.0.1:{port}",
            },
            subprotocols=subprotocols or None,
            open_timeout=15,
            max_size=None,
        )
    except (OSError, WebSocketException) as exc:
        logger.info("stream: websocket to session %s failed: %s", session_id, exc)
        await websocket.close(code=1011)
        return

    await websocket.accept(subprotocol=upstream.subprotocol)
    logger.info("stream: session %s attached (port %d)", session_id, port)
    try:
        await _pump(websocket, upstream, websocket.app, session_id)
    finally:
        await upstream.close()


async def _pump(client: WebSocket, upstream, app, session_id: str) -> None:
    """Shuttle frames until one side stops, then stop the other."""

    async def to_upstream() -> None:
        while True:
            message = await client.receive()
            if message["type"] == "websocket.disconnect":
                return
            _touch(app, session_id)
            if (data := message.get("bytes")) is not None:
                await upstream.send(data)
            elif (text := message.get("text")) is not None:
                await upstream.send(text)

    async def to_client() -> None:
        async for frame in upstream:
            _touch(app, session_id)
            if isinstance(frame, bytes):
                await client.send_bytes(frame)
            else:
                await client.send_text(frame)

    tasks = [asyncio.create_task(to_upstream()), asyncio.create_task(to_client())]
    try:
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
    except (WebSocketDisconnect, WebSocketException, RuntimeError) as exc:
        logger.info("stream: session %s detached: %s", session_id, exc)


def _touch(app, session_id: str) -> None:
    """Report activity, which is what keeps the idle clock from firing."""
    dispatcher = getattr(app.state, "dispatcher", None)
    if dispatcher is not None:
        dispatcher.note_activity(session_id)
