"""Self-test endpoint — real per-check logic (wire-dosbox-engine).

Returns the canonical four-check document defined in
`nextcloud-distribution/spec.md` → *Self-check passes on healthy
install*. The JSON schema is unchanged from the `init-mvp-runtime`
scaffold (frontend binds against it); this change swaps each
`"skipped"` value for an actual probe:

- host-health         — dispatcher + engine registry are wired.
- engines-registered  — at least one engine is enabled.
- deploy-daemon-spawn — the session spawner passes its preflight
                        (docker/podman socket reachable, or stub ready).
- audit-log-write     — a probe entry writes to the audit log.

Each failing check carries an actual error message, never vague
text (acceptance criterion). `overall` is `ok` only when every
check is `ok`.
"""

from __future__ import annotations

import logging
from typing import Final, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

CheckStatus = Literal["ok", "fail", "skipped"]
OverallStatus = Literal["ok", "fail", "skipped"]

# Check IDs are normative — see the spec scenario "Self-check passes
# on healthy install". Order is preserved in responses for stable
# rendering on the frontend.
CHECK_IDS: Final[tuple[str, ...]] = (
    "host-health",
    "engines-registered",
    "deploy-daemon-spawn",
    "audit-log-write",
)


class CheckResult(BaseModel):
    id: str
    status: CheckStatus
    message: str = Field(default="", description="Human-readable detail.")


class SelfTestReport(BaseModel):
    checks: list[CheckResult]
    overall: OverallStatus


router = APIRouter(tags=["selftest"])


def _ok(cid: str, message: str) -> CheckResult:
    return CheckResult(id=cid, status="ok", message=message)


def _fail(cid: str, message: str) -> CheckResult:
    return CheckResult(id=cid, status="fail", message=message)


def _check_host_health(dispatcher: object) -> CheckResult:
    cid = "host-health"
    if dispatcher is None:
        return _fail(cid, "dispatcher not wired on app.state (lifespan did not run)")
    if getattr(dispatcher, "registry", None) is None:
        return _fail(cid, "dispatcher has no engine registry")
    return _ok(cid, "host up; dispatcher and registry wired")


def _check_engines_registered(dispatcher: object) -> CheckResult:
    cid = "engines-registered"
    registry = getattr(dispatcher, "registry", None)
    if registry is None:
        return _fail(cid, "no engine registry to query")
    enabled = registry.enabled()
    if not enabled:
        total = len(registry.all()) if hasattr(registry, "all") else 0
        return _fail(cid, f"no engines enabled ({total} discovered, 0 enabled)")
    ids = ", ".join(e.id for e in enabled)
    return _ok(cid, f"{len(enabled)} engine(s) enabled: {ids}")


async def _check_deploy_daemon_spawn(dispatcher: object) -> CheckResult:
    cid = "deploy-daemon-spawn"
    spawner = getattr(dispatcher, "spawner", None)
    if spawner is None:
        return _fail(cid, "no session spawner wired")
    preflight = getattr(spawner, "preflight", None)
    if preflight is None:
        # A spawner without a preflight probe can't be verified deeper;
        # report ok but name it so the gap is visible, never vague.
        return _ok(cid, f"spawner {type(spawner).__name__} wired (no preflight probe)")
    try:
        ready, detail = await preflight()
    except Exception as exc:
        return _fail(cid, f"spawner preflight raised: {exc!r}")
    return _ok(cid, detail) if ready else _fail(cid, detail)


async def _check_audit_log_write(dispatcher: object) -> CheckResult:
    cid = "audit-log-write"
    audit = getattr(dispatcher, "audit", None)
    if audit is None:
        return _fail(cid, "no audit logger wired")
    try:
        await audit.log(outcome="selftest", event="selftest-probe",
                        detail="self-test audit write probe")
    except Exception as exc:
        return _fail(cid, f"audit write failed: {exc!r}")
    return _ok(cid, "audit log accepted a probe entry")


@router.post("/selftest")
async def run_selftest(request: Request) -> SelfTestReport:
    """Run all self-test checks and return the aggregate report.

    Reads the wired dispatcher off `app.state`; every check degrades
    to `fail` with a concrete message rather than raising, so a broken
    install still returns a well-formed report the admin page can show.
    """
    dispatcher = getattr(request.app.state, "dispatcher", None)
    checks = [
        _check_host_health(dispatcher),
        _check_engines_registered(dispatcher),
        await _check_deploy_daemon_spawn(dispatcher),
        await _check_audit_log_write(dispatcher),
    ]
    overall: OverallStatus = "ok" if all(c.status == "ok" for c in checks) else "fail"
    return SelfTestReport(checks=checks, overall=overall)
