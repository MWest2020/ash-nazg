"""Extract user identity from AppAPI-proxied requests.

AppAPI sets the `AUTHORIZATION-APP-API` header on every request it
proxies to an ExApp; its value is `base64(user_id:app_secret)`. The
`user_id` is empty for anonymous (PUBLIC) routes, the Nextcloud user
id otherwise. Route access-levels (PUBLIC / USER / ADMIN) are enforced
by AppAPI BEFORE the request reaches us — so a request that arrives at
an `ADMIN`-declared route can be trusted to come from an admin. The
host should re-validate as defence in depth via OCS (TODO follow-up);
for the v1 demo we trust the route gating.
"""

from __future__ import annotations

import base64
import binascii
import logging
from dataclasses import dataclass
from typing import Final

from fastapi import Request

logger = logging.getLogger(__name__)

AUTH_HEADER: Final[str] = "AUTHORIZATION-APP-API"


@dataclass(frozen=True)
class RequestUser:
    user_id: str
    is_admin: bool


def extract_user(request: Request, *, admin_route: bool) -> RequestUser:
    """Extract the user identity that AppAPI passed in.

    `admin_route` tells us whether the AppAPI route the request landed
    on is declared ADMIN. If yes, we trust the gating and return
    is_admin=True; otherwise is_admin=False.

    Missing or malformed header → empty user, is_admin=False. Callers
    that require an authenticated user check `user_id != ""`.
    """
    header = request.headers.get(AUTH_HEADER, "")
    if not header:
        return RequestUser(user_id="", is_admin=False)
    try:
        decoded = base64.b64decode(header, validate=True).decode("utf-8", errors="strict")
    except (binascii.Error, UnicodeDecodeError):
        logger.warning("AUTHORIZATION-APP-API header is not valid base64; treating as anonymous")
        return RequestUser(user_id="", is_admin=False)
    if ":" not in decoded:
        return RequestUser(user_id="", is_admin=False)
    user_id, _secret = decoded.split(":", 1)
    return RequestUser(user_id=user_id, is_admin=admin_route and user_id != "")
