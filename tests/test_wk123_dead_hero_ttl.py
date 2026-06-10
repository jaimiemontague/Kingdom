"""WK123 C2 regression: dead heroes/peasants are bounded without breaking the memorial.

The time-degradation amplifier C2 fixes: ``SimEngine.heroes`` / ``.peasants`` were
append-only, so the per-frame ``build_hero_profile_snapshot`` (sorts known_places +
profile_memory) and ``unit_dto_from`` work scaled with ALL-TIME hires rather than the
living set. These tests pin the three guarantees of the fix:

1. A dead unit's render DTO is no longer built (renderers already skip dead).
2. A freshly-dead hero keeps its profile for ``DEAD_HERO_RETENTION_MS`` (so the
   watch-card / recall / pin-liveness / memorial reads at hud.py:776/783 behave exactly
   as today within the window) and is then dropped, bounding per-frame profile cost.
3. ``self.heroes`` is culled past the retention window and ``self.peasants`` is culled as
   soon as a peasant dies — neither grows with all-time hires.

Time is controlled by monkeypatching ``game.sim.timebase.now_ms`` (the single clock both
the cleanup death-stamp and the get_game_state profile build read), because the default
config runs the non-deterministic clock that ``SimEngine.update`` resets to wall-time.
"""

from __future__ import annotations

import pytest

import game.sim.timebase as timebase
from config import TILE_SIZE
from game.engine import GameEngine
from game.entities.hero import Hero
from game.entities.peasant import Peasant
from game.sim_engine import DEAD_HERO_RETENTION_MS


@pytest.fixture
def fake_clock(monkeypatch):
    """A controllable sim clock; both C2 call sites read ``timebase.now_ms``."""
    state = {"t": 1_000}
    monkeypatch.setattr(timebase, "now_ms", lambda: state["t"])
    return state


def _spawn_hero(engine: GameEngine, hero_id: str) -> Hero:
    castle = next(b for b in engine.sim.buildings if getattr(b, "building_type", None) == "castle")
    h = Hero(float(castle.center_x) + TILE_SIZE, float(castle.center_y), hero_id=hero_id, name="Doomed")
    engine.sim.heroes.append(h)
    return h


def _has_hero_dto(engine: GameEngine, entity_id: str) -> bool:
    snap = engine.build_snapshot()
    return any(getattr(d, "entity_id", None) == entity_id for d in snap.hero_dtos)


def _profile_present(engine: GameEngine, hero_id: str) -> bool:
    return hero_id in engine.get_game_state()["hero_profiles_by_id"]


def test_dead_hero_dto_skipped_profile_retained_then_culled(fake_clock):
    engine = GameEngine(headless=True)
    h = _spawn_hero(engine, "wk123_dead")

    # Alive: both DTO and profile present.
    assert _has_hero_dto(engine, "wk123_dead")
    assert _profile_present(engine, "wk123_dead")

    # Kill, then tick once so the cleanup block stamps the death time.
    h.hp = 0
    assert not h.is_alive
    engine.update(0.016)
    assert getattr(h, "_dead_since_ms", None) == 1_000, "death must be stamped from timebase.now_ms"

    # Inside the retention window: DTO is skipped (perf win) but the profile is STILL
    # built so the memorial / pin-liveness / watch-card reads are unchanged from today.
    fake_clock["t"] = 1_000 + DEAD_HERO_RETENTION_MS - 5_000
    assert not _has_hero_dto(engine, "wk123_dead"), "dead hero DTO must not be built"
    assert _profile_present(engine, "wk123_dead"), "profile must persist within the retention window"
    assert h in engine.sim.heroes, "hero must be retained within the window"

    # Past the retention window: the heavy profile build stops immediately...
    fake_clock["t"] = 1_000 + DEAD_HERO_RETENTION_MS + 5_000
    assert not _profile_present(engine, "wk123_dead"), "profile build must stop past the window"

    # ...and the hero is reclaimed from self.heroes by the cleanup fallback (<= 60 ticks).
    for _ in range(61):
        engine.update(0.016)
    assert h not in engine.sim.heroes, "dead hero must be culled past the retention window"


def test_dead_peasant_culled_immediately(fake_clock):
    engine = GameEngine(headless=True)
    castle = next(b for b in engine.sim.buildings if getattr(b, "building_type", None) == "castle")
    p = Peasant(float(castle.center_x) + TILE_SIZE, float(castle.center_y))
    engine.sim.peasants.append(p)

    p.hp = 0
    assert not p.is_alive
    # The cleanup block runs on a death (events) or the 60-tick fallback.
    for _ in range(61):
        engine.update(0.016)
    assert p not in engine.sim.peasants, "dead peasants must be culled (no memorial / pin UX reads them)"


def test_dead_peasant_dto_skipped(fake_clock):
    engine = GameEngine(headless=True)
    castle = next(b for b in engine.sim.buildings if getattr(b, "building_type", None) == "castle")
    p = Peasant(float(castle.center_x) + TILE_SIZE, float(castle.center_y))
    engine.sim.peasants.append(p)

    snap = engine.build_snapshot()
    assert any(getattr(d, "is_alive", True) for d in snap.peasant_dtos)

    p.hp = 0
    snap2 = engine.build_snapshot()
    # The DTO for the now-dead peasant must not be built (the build_snapshot filter),
    # independent of the list cull which happens in the next cleanup pass.
    assert all(getattr(d, "is_alive", True) for d in snap2.peasant_dtos), \
        "dead peasant DTO must not be built"
