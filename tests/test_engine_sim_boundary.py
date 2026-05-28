"""
Baseline characterization tests for the engine/sim boundary.

Sprint: wk62_architecture_cleanup_baseline
Wave 0: Prove current engine/sim behavior BEFORE production code changes.

These tests document the actual behavior of:
- Sim time advancement (single vs double advance per update tick)
- Pause behavior (sim time should not advance when paused)
- Building destruction cleanup (rubble creation count, event emission count)

Tests that expose real current bugs are marked with pytest.xfail and document
the failure clearly so Wave 1 agents can fix the root cause.

DETERMINISTIC_SIM note: Tests 1-2 require deterministic sim time to be meaningful.
They use unittest.mock.patch to force DETERMINISTIC_SIM=True in both engine.py and
sim_engine.py so they run regardless of the env var setting.
"""

from __future__ import annotations

import pytest
import pygame
from unittest.mock import patch

from game.engine import GameEngine
from game.events import GameEventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_headless_engine_deterministic() -> GameEngine:
    """Create a headless GameEngine with deterministic sim time forced on.

    Patches DETERMINISTIC_SIM in both engine.py and sim_engine.py so that
    sim time is tracked via _sim_now_ms rather than wall-clock.
    """
    # The constant is already imported at module level in both engine.py
    # and sim_engine.py — we need to patch it in both places.
    with patch("game.engine.DETERMINISTIC_SIM", True), \
         patch("game.sim_engine.DETERMINISTIC_SIM", True):
        engine = GameEngine(headless=True)
    return engine


def _make_headless_engine() -> GameEngine:
    """Create a headless GameEngine suitable for boundary tests."""
    return GameEngine(headless=True)


def _castle(engine: GameEngine):
    return next(
        (b for b in engine.buildings if getattr(b, "building_type", None) == "castle"),
        None,
    )


def _place_test_building(engine: GameEngine):
    """Place a destructible building (warrior_guild) via the sim building factory.

    Returns the building instance. The building is placed at a fixed grid
    position near the castle so it does not overlap existing structures.
    """
    # Use a grid position far enough from castle (castle is at center ~123,123).
    gx, gy = 130, 130
    building = engine.sim.building_factory.create("warrior_guild", gx, gy)
    assert building is not None, "BuildingFactory failed to create warrior_guild"
    building.is_constructed = True
    building.construction_started = True
    building.hp = building.max_hp
    engine.sim.buildings.append(building)
    if hasattr(building, "set_event_bus"):
        building.set_event_bus(engine.sim.event_bus)
    return building


class _EventCollector:
    """Subscribe to EventBus and collect all events of a given type."""

    def __init__(self, event_bus, event_type: str):
        self.events: list[dict] = []
        self._event_type = event_type
        event_bus.subscribe(event_type, self._on_event)

    def _on_event(self, event: dict) -> None:
        self.events.append(event)

    @property
    def count(self) -> int:
        return len(self.events)


# ===========================================================================
# Test 1: Sim time advances exactly once per engine.update()
# ===========================================================================

def test_game_engine_update_advances_sim_time_once():
    """Verify that a single engine.update(dt=0.05) advances sim time by exactly 50ms.

    Expected: after == before + 50
    Actual (pre-fix): after == before + 100  (double advance)

    Root cause: _prepare_sim_and_camera() mutates _sim_now_ms (line 1228 of
    engine.py), then sim.update() also mutates _sim_now_ms (line 605 of
    sim_engine.py). Both add int(round(dt * 1000)).
    """
    engine = _make_headless_engine_deterministic()
    try:
        # Force deterministic mode for the update call via patches on the
        # already-imported module-level constants.
        with patch("game.engine.DETERMINISTIC_SIM", True), \
             patch("game.sim_engine.DETERMINISTIC_SIM", True):
            before = int(engine.sim._sim_now_ms)
            engine.update(0.05)
            after = int(engine.sim._sim_now_ms)
        delta = after - before
        assert delta == 50, (
            f"Sim time should advance by exactly 50ms for dt=0.05, "
            f"but advanced by {delta}ms (before={before}, after={after}). "
            f"This indicates sim time is being advanced {delta // 50} time(s)."
        )
    finally:
        pygame.quit()


# ===========================================================================
# Test 2: Paused does not advance sim time
# ===========================================================================

def test_paused_does_not_advance_sim_time():
    """Verify that engine.update() does NOT advance sim time when paused.

    Expected: after == before (no change)
    Actual (pre-fix): after == before + 50  (one advance leaks through
    from _prepare_sim_and_camera before the pause early-return)

    Root cause: _prepare_sim_and_camera() runs the sim time increment
    unconditionally at lines 1228-1229 of engine.py BEFORE checking
    `self.paused` at line 1234 and returning False. The early return
    prevents SimEngine.update() from running, so only one of the two
    advances leaks — but it should be zero.
    """
    engine = _make_headless_engine_deterministic()
    try:
        with patch("game.engine.DETERMINISTIC_SIM", True), \
             patch("game.sim_engine.DETERMINISTIC_SIM", True):
            # Prime the engine with one normal tick so state is initialized.
            engine.update(0.05)
            before = int(engine.sim._sim_now_ms)

            # Pause and tick again.
            engine.paused = True
            engine.update(0.05)
            after = int(engine.sim._sim_now_ms)

        assert after == before, (
            f"Sim time should not advance when paused, but it moved from "
            f"{before}ms to {after}ms (delta={after - before}ms). "
            f"The leak comes from _prepare_sim_and_camera advancing "
            f"_sim_now_ms before checking the pause flag."
        )
    finally:
        pygame.quit()


# ===========================================================================
# Test 3: Destroying a building creates exactly one rubble record
# ===========================================================================

def test_destroying_building_creates_one_rubble():
    """Verify that destroying one building creates exactly one rubble record.

    Architecture note: Both SimEngine._cleanup_destroyed_buildings() (sim_engine.py
    line 749) and GameEngine._cleanup_destroyed_buildings() (engine.py line 1157,
    via CleanupManager) have code paths that create rubble. Currently, the sim-side
    cleanup runs first inside sim.update(), removes the building from the list, so
    CleanupManager finds nothing to clean — resulting in exactly 1 rubble record.

    This test guards the correct-count invariant. If cleanup ordering changes or
    a new cleanup path is added, this test will catch double-rubble regressions.
    """
    engine = _make_headless_engine()
    try:
        building = _place_test_building(engine)

        initial_rubble_count = len(engine.sim.rubble_records)

        # Kill the building.
        building.hp = 0

        # Run one full engine update tick so cleanup runs.
        engine.update(0.05)

        final_rubble_count = len(engine.sim.rubble_records)
        new_rubble = final_rubble_count - initial_rubble_count

        assert new_rubble == 1, (
            f"Destroying one building should create exactly 1 rubble record, "
            f"but created {new_rubble} (initial={initial_rubble_count}, "
            f"final={final_rubble_count}). "
            f"This indicates cleanup is running in multiple places."
        )
    finally:
        pygame.quit()


# ===========================================================================
# Test 4: Destroying a building emits exactly one destruction event
# ===========================================================================

def test_destroying_building_emits_one_event():
    """Verify that destroying one building emits exactly one BUILDING_DESTROYED event.

    The EventBus queues events and flushes them at the end of the frame via
    _flush_event_bus(). We subscribe before the destruction tick and count how
    many destruction events are delivered after one full engine.update() cycle.

    Architecture note: Both SimEngine._cleanup_destroyed_buildings() and
    GameEngine._cleanup_destroyed_buildings() (via CleanupManager) emit
    BUILDING_DESTROYED events. Currently the sim-side cleanup runs first
    and removes the building from the list, so CleanupManager's destroyed
    filter finds nothing and emits zero additional events. This test guards
    the single-event invariant against cleanup ordering regressions.
    """
    engine = _make_headless_engine()
    try:
        building = _place_test_building(engine)

        # Subscribe to building destroyed events.
        collector = _EventCollector(
            engine.sim.event_bus,
            GameEventType.BUILDING_DESTROYED.value,
        )

        # Flush any pre-existing events so they do not pollute our count.
        engine.sim.event_bus.flush()

        # Kill the building.
        building.hp = 0

        # Run one full engine update tick.
        engine.update(0.05)

        # _finalize_update calls _flush_event_bus for headless mode.
        # Also manually flush to ensure all queued events are delivered.
        engine.sim.event_bus.flush()

        assert collector.count == 1, (
            f"Destroying one building should emit exactly 1 BUILDING_DESTROYED "
            f"event, but emitted {collector.count}. "
            f"Collected events: {collector.events}"
        )
    finally:
        pygame.quit()
