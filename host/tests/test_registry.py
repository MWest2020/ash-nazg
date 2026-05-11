"""Tests for the engine registry.

Covers the spec scenarios:
- "Engine registration discovered at startup" — loading from entrypoints
- "Engine missing required methods refused" — broken engines skipped
- "Disabled engine ignored" — set_enabled flips visibility
- "Default state of newly discovered engine" — env-var allowlist
- Registration order preserved (dispatch picks first registered match)
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from ash_nazg.engines import FileMeta, SessionConfig
from ash_nazg.engines.registry import (
    ENGINES_ENABLED_ENV,
    EngineRegistry,
    RegisteredEngine,
    discover_engines,
)


class _GoodEngine:
    id = "good"
    image = "ghcr.io/test/good:0.1"

    def can_handle(self, file_meta: FileMeta) -> bool:
        return True

    def session_config(self, file_meta: FileMeta) -> SessionConfig:
        return SessionConfig(
            image=self.image,
            cpu_limit=1.0,
            memory_limit_mb=512,
            mount_path="/mnt/files",
            streaming_protocol="kasmvnc",
            streaming_port=6901,
            idle_timeout_seconds=300,
            entrypoint_args=[],
        )


class _OtherGoodEngine(_GoodEngine):
    id = "other"
    image = "ghcr.io/test/other:0.1"


class _BrokenEngineNoMethods:
    """Doesn't implement the Engine protocol."""

    id = "broken-no-methods"
    image = "ghcr.io/test/broken:0.1"


class _RaisesOnInstantiate:
    def __init__(self) -> None:
        raise RuntimeError("simulated plugin init failure")


def _make_ep(name: str, target: Any) -> SimpleNamespace:
    """Fake importlib.metadata EntryPoint with a `.load()` method."""

    def _load() -> Any:
        return target

    return SimpleNamespace(name=name, load=_load)


def _patch_entrypoints(eps: Iterable[SimpleNamespace]) -> Any:
    """Patch importlib.metadata.entry_points used by the registry."""
    return patch(
        "ash_nazg.engines.registry.entry_points",
        return_value=list(eps),
    )


# --- discover_engines ------------------------------------------------------


def test_discover_engines_loads_protocol_implementers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENGINES_ENABLED_ENV, raising=False)
    eps = [_make_ep("good", _GoodEngine)]
    with _patch_entrypoints(eps):
        registry = discover_engines()
    assert len(registry) == 1
    assert registry.by_id("good") is not None
    assert registry.enabled()[0].id == "good"


def test_discover_engines_preserves_registration_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENGINES_ENABLED_ENV, raising=False)
    eps = [_make_ep("good", _GoodEngine), _make_ep("other", _OtherGoodEngine)]
    with _patch_entrypoints(eps):
        registry = discover_engines()
    assert [r.engine.id for r in registry.all()] == ["good", "other"]


def test_discover_engines_skips_load_failures(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENGINES_ENABLED_ENV, raising=False)

    def _raises() -> Any:
        raise ImportError("simulated module load failure")

    eps = [
        SimpleNamespace(name="broken-load", load=_raises),
        _make_ep("good", _GoodEngine),
    ]
    caplog.set_level(logging.WARNING, logger="ash_nazg.engines.registry")
    with _patch_entrypoints(eps):
        registry = discover_engines()
    assert len(registry) == 1
    assert registry.by_id("good") is not None
    assert any("broken-load" in rec.message for rec in caplog.records)


def test_discover_engines_skips_instantiation_failures(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENGINES_ENABLED_ENV, raising=False)
    eps = [
        _make_ep("broken-init", _RaisesOnInstantiate),
        _make_ep("good", _GoodEngine),
    ]
    caplog.set_level(logging.WARNING, logger="ash_nazg.engines.registry")
    with _patch_entrypoints(eps):
        registry = discover_engines()
    assert len(registry) == 1
    assert registry.by_id("good") is not None
    assert any("broken-init" in rec.message for rec in caplog.records)


def test_discover_engines_skips_non_protocol(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENGINES_ENABLED_ENV, raising=False)
    eps = [
        _make_ep("broken-no-methods", _BrokenEngineNoMethods),
        _make_ep("good", _GoodEngine),
    ]
    caplog.set_level(logging.WARNING, logger="ash_nazg.engines.registry")
    with _patch_entrypoints(eps):
        registry = discover_engines()
    assert len(registry) == 1
    assert registry.by_id("good") is not None
    assert any("broken-no-methods" in rec.message for rec in caplog.records)


# --- Env-var allowlist (default enabled state) -----------------------------


def test_env_unset_enables_all_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENGINES_ENABLED_ENV, raising=False)
    eps = [_make_ep("good", _GoodEngine), _make_ep("other", _OtherGoodEngine)]
    with _patch_entrypoints(eps):
        registry = discover_engines()
    assert {e.id for e in registry.enabled()} == {"good", "other"}


def test_env_allowlist_restricts_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENGINES_ENABLED_ENV, "good")
    eps = [_make_ep("good", _GoodEngine), _make_ep("other", _OtherGoodEngine)]
    with _patch_entrypoints(eps):
        registry = discover_engines()
    enabled_ids = {e.id for e in registry.enabled()}
    assert enabled_ids == {"good"}
    # the disabled engine still appears in all() — the admin UI lists it
    assert {r.engine.id for r in registry.all()} == {"good", "other"}


def test_env_empty_allowlist_disables_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENGINES_ENABLED_ENV, "")
    eps = [_make_ep("good", _GoodEngine), _make_ep("other", _OtherGoodEngine)]
    with _patch_entrypoints(eps):
        registry = discover_engines()
    assert registry.enabled() == []


# --- set_enabled -----------------------------------------------------------


def test_set_enabled_flips_state() -> None:
    registry = EngineRegistry(
        [RegisteredEngine(engine=_GoodEngine(), enabled=True)]
    )
    assert registry.set_enabled("good", False) is True
    assert registry.enabled() == []
    assert registry.set_enabled("good", True) is True
    assert {e.id for e in registry.enabled()} == {"good"}


def test_set_enabled_unknown_returns_false() -> None:
    registry = EngineRegistry(
        [RegisteredEngine(engine=_GoodEngine(), enabled=True)]
    )
    assert registry.set_enabled("nope", False) is False
