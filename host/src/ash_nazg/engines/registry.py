"""Engine registry — discovers engines via the `ash_nazg.engines`
entrypoint group and tracks per-engine enabled state.

Per `engines` spec:
- Engines register via the `ash_nazg.engines` Python entrypoint group.
- Broken engines (fail to load, fail to instantiate, don't implement the
  protocol) MUST be logged and skipped without taking the host down.
- Newly-discovered engines default to DISABLED (spec scenario "Default
  state of newly discovered engine"). For the v1 release with one
  shipped engine, the bootstrap declares dosbox-x's initial state via
  the `ASH_NAZG_ENGINES_ENABLED` allowlist env var so the demo works
  out of the box.
- The registry preserves entrypoint-discovery order so dispatch picks
  the first registered enabled engine that handles the file (dispatch
  spec scenario "Dispatcher selects first registered enabled engine").
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from importlib.metadata import entry_points

from ash_nazg.engines import Engine

ENGINES_ENTRYPOINT_GROUP = "ash_nazg.engines"
ENGINES_ENABLED_ENV = "ASH_NAZG_ENGINES_ENABLED"

logger = logging.getLogger(__name__)


@dataclass
class RegisteredEngine:
    """An engine that loaded successfully + its current enabled state."""

    engine: Engine
    enabled: bool


class EngineRegistry:
    """Iterates loaded engines in registration order.

    Mutating set_enabled() does not persist across host restarts in v1;
    the admin settings page is the single source of truth and re-applies
    its state at startup via the env var. Future: back this with AppAPI
    config_keys for proper persistence (admin-settings-ui change).
    """

    def __init__(self, engines: Iterable[RegisteredEngine]) -> None:
        self._engines: list[RegisteredEngine] = list(engines)

    def __iter__(self) -> Iterator[RegisteredEngine]:
        return iter(self._engines)

    def __len__(self) -> int:
        return len(self._engines)

    def all(self) -> list[RegisteredEngine]:
        return list(self._engines)

    def enabled(self) -> list[Engine]:
        """Enabled engines in registration order. The dispatcher iterates
        this list and takes the first whose can_handle() returns True."""
        return [r.engine for r in self._engines if r.enabled]

    def by_id(self, engine_id: str) -> RegisteredEngine | None:
        for r in self._engines:
            if r.engine.id == engine_id:
                return r
        return None

    def set_enabled(self, engine_id: str, enabled: bool) -> bool:
        """Flip the enabled flag for an engine. Returns False if unknown."""
        target = self.by_id(engine_id)
        if target is None:
            return False
        target.enabled = enabled
        return True


def _enabled_allowlist() -> frozenset[str] | None:
    """Parse `ASH_NAZG_ENGINES_ENABLED` env var.

    Returns None when unset (caller treats as "no allowlist — all engines
    default enabled"). Returns a (possibly empty) frozenset of engine ids
    when set, even if empty, to encode "explicitly nothing enabled".
    """
    raw = os.environ.get(ENGINES_ENABLED_ENV)
    if raw is None:
        return None
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def _default_enabled_state(engine_id: str, allowlist: frozenset[str] | None) -> bool:
    """Decide whether an engine should be enabled at startup.

    `ASH_NAZG_ENGINES_ENABLED=dosbox-x,wine` → only those two enabled.
    `ASH_NAZG_ENGINES_ENABLED=` (empty)      → all engines disabled.
    `ASH_NAZG_ENGINES_ENABLED` unset         → all engines enabled.

    The "unset = all enabled" default exists so the v1 release works
    out of the box. Per spec, a newly-discovered engine after a host
    UPGRADE defaults disabled; that distinction is enforced by the
    bootstrap explicitly setting the allowlist after first install.
    """
    if allowlist is None:
        return True
    return engine_id in allowlist


def _load_engines(group: str) -> Iterable[Engine]:
    """Load all engines from the entrypoint group, skipping broken ones.

    Each entrypoint's target may be either the class itself or an already-
    instantiated singleton; both forms are accepted.
    """
    for ep in entry_points(group=group):
        try:
            target = ep.load()
        except Exception:
            logger.warning(
                "engine %r failed to load — skipping", ep.name, exc_info=True
            )
            continue

        try:
            engine = target() if isinstance(target, type) else target
        except Exception:
            logger.warning(
                "engine %r failed to instantiate — skipping", ep.name, exc_info=True
            )
            continue

        if not isinstance(engine, Engine):
            logger.warning(
                "engine %r does not implement the Engine protocol "
                "(missing can_handle or session_config) — skipping",
                ep.name,
            )
            continue

        yield engine


def discover_engines(group: str = ENGINES_ENTRYPOINT_GROUP) -> EngineRegistry:
    """Discover engines from the entrypoint group with their default state.

    Called once at host startup; result is cached on the FastAPI app
    state object so subsequent /run requests don't re-scan entrypoints.
    """
    allowlist = _enabled_allowlist()
    registered = [
        RegisteredEngine(
            engine=engine,
            enabled=_default_enabled_state(engine.id, allowlist),
        )
        for engine in _load_engines(group)
    ]
    return EngineRegistry(registered)
