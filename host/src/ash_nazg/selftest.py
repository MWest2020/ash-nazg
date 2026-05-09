"""Self-test endpoint — scaffold.

Per task §11.4: returns a JSON document with the four checks
defined in `nextcloud-distribution/spec.md` →
*Self-check passes on healthy install*. In this change every check
returns `status: "skipped"`; the `wire-dosbox-engine` change
replaces the per-check logic without changing the JSON schema.

Schema is fixed in this change so the frontend can bind against
it now and the wiring change only updates values, not shape.
"""

from __future__ import annotations

from typing import Final, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

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


def _skipped_report() -> SelfTestReport:
    """Build the canonical scaffold response."""
    return SelfTestReport(
        checks=[
            CheckResult(id=cid, status="skipped", message="not yet implemented")
            for cid in CHECK_IDS
        ],
        overall="skipped",
    )


@router.post("/selftest")
async def run_selftest() -> SelfTestReport:
    """Run all self-test checks and return the aggregate report.

    Currently a scaffold; every check returns `skipped`. The
    `wire-dosbox-engine` change replaces the per-check
    implementation but MUST keep the JSON shape unchanged.
    """
    return _skipped_report()
