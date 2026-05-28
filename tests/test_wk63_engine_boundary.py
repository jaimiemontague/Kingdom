"""
Baseline characterization tests for engine boundary cleanup.

Sprint: wk63_engine_boundary_cleanup
Wave 0: Prove current engine/sim behavior BEFORE production code changes.

These tests document the actual behavior of:
- Pathfinding budget enforcement and per-frame reset
- Selection mutual exclusivity (manual clearing pattern)
- GameCommands Protocol member completeness
- Hero stable ID (hero_id) existence
- Building lack of stable entity_id (gap to be filled by Wave 1)

Tests are written against the CURRENT API so Wave 1/2 agents have a
regression net. When production code changes land, update assertions
accordingly.
"""

from __future__ import annotations

import inspect

import pytest
import pygame

from game.engine import GameEngine
from game.entities.hero import Hero
from game.systems.navigation import (
    PathfindingBudget,
    get_pathfinding_budget,
    compute_path_worldpoints,
)
from game.game_commands import (
    CameraCommands,
    SelectionCommands,
    PlacementCommands,
    MenuCommands,
    GameStateCommands,
    GameCommands,
    EngineCommandHub,
    EngineBackedGameCommands,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_headless_engine() -> GameEngine:
    """Create a headless GameEngine suitable for boundary tests."""
    return GameEngine(headless=True)


def _make_headless_engine_with_hero() -> tuple[GameEngine, Hero]:
    """Create a headless GameEngine and add one hero to it.

    Headless engines start with no heroes, so we manually create one
    and append it to sim.heroes, matching the pattern used by other
    tests in the suite.
    """
    engine = GameEngine(headless=True)
    # Place hero near center of the map
    hero = Hero(400.0, 400.0, hero_class="warrior", hero_id="h_test_001")
    engine.sim.heroes.append(hero)
    return engine, hero


# ---------------------------------------------------------------------------
# Test 1: Pathfinding budget exhaustion returns empty path
# ---------------------------------------------------------------------------

def test_pathfinding_budget_exhaustion_defers():
    """When budget is exhausted, compute_path_worldpoints now DEFERS (returns None)
    so callers keep their existing path; WK64 Phase A corrected the prior
    `[]`-on-exhaustion behavior that wiped paths.
    """
    engine = _make_headless_engine()
    try:
        budget = get_pathfinding_budget()
        budget.begin_frame()

        # Exhaust the budget by pushing _frame_expansions above MAX_EXPANSIONS_PER_FRAME
        budget._frame_expansions = budget.MAX_EXPANSIONS_PER_FRAME + 1

        result = compute_path_worldpoints(
            engine.sim.world,
            engine.sim.buildings,
            100.0, 100.0,   # start
            500.0, 500.0,   # goal
        )
        assert result is None, f"Expected None (deferred) when budget exhausted, got {result}"
    finally:
        pygame.quit()


# ---------------------------------------------------------------------------
# Test 2: Pathfinding budget resets each frame
# ---------------------------------------------------------------------------

def test_pathfinding_budget_resets_each_frame():
    """begin_frame() resets the per-frame budget counters.

    Wave 1B counters: _frame_plans (int), _frame_expansions (int),
    _frame_ms_used (float, metrics only).
    The _pending_queue is NOT reset by begin_frame() (it uses
    drain_pending() separately).
    """
    budget = get_pathfinding_budget()

    # Pollute the counters
    budget._frame_ms_used = 999.0
    budget._frame_plans = 999
    budget._frame_expansions = 999

    budget.begin_frame()

    assert budget._frame_ms_used == 0.0, (
        f"_frame_ms_used should be 0.0 after begin_frame(), got {budget._frame_ms_used}"
    )
    assert budget._frame_plans == 0, (
        f"_frame_plans should be 0 after begin_frame(), got {budget._frame_plans}"
    )
    assert budget._frame_expansions == 0, (
        f"_frame_expansions should be 0 after begin_frame(), got {budget._frame_expansions}"
    )


# ---------------------------------------------------------------------------
# Test 3: Selection is mutually exclusive (manual pattern)
# ---------------------------------------------------------------------------

def test_selection_is_mutually_exclusive():
    """Selection is managed by SelectionState (WK63).

    SelectionState enforces mutual exclusivity: hero+building can coexist
    (HUD shows building in right panel and hero in left), but selecting
    an enemy clears hero and peasant, etc.
    """
    engine, hero = _make_headless_engine_with_hero()
    try:
        engine.selected_hero = hero
        assert engine.selected_hero is hero

        # Selecting a building does NOT clear hero (hero+building coexist)
        buildings = [
            b for b in engine.sim.buildings
            if getattr(b, "building_type", "") != "castle"
        ]
        if buildings:
            b = buildings[0]
            engine.selected_building = b
            assert engine.selected_hero is hero, (
                "select_building should NOT clear hero "
                "(hero+building coexist in SelectionState)"
            )
            assert engine.selected_building is b

        # Engine exposes all four selected_* properties
        assert hasattr(engine, "selected_hero")
        assert hasattr(engine, "selected_building")
        assert hasattr(engine, "selected_peasant")
        assert hasattr(engine, "selected_enemy")

        # Verify try_select_* methods exist
        assert callable(getattr(engine, "try_select_hero", None))
        assert callable(getattr(engine, "try_select_building", None))
        assert callable(getattr(engine, "try_select_peasant", None))
        assert callable(getattr(engine, "try_select_enemy", None))
    finally:
        pygame.quit()


# ---------------------------------------------------------------------------
# Test 4: GameCommands Protocol has all expected members
# ---------------------------------------------------------------------------

def test_game_commands_has_all_expected_members():
    """The 5 narrow Protocol interfaces cover all members InputHandler needs.

    WK63 Wave 2 split the monolithic GameCommands into CameraCommands,
    SelectionCommands, PlacementCommands, MenuCommands, GameStateCommands.
    """
    def _members(cls):
        return {
            name
            for name, _ in inspect.getmembers(cls)
            if not name.startswith("__")
        }

    # CameraCommands
    cam = _members(CameraCommands)
    for req in ("camera_x", "camera_y", "zoom", "zoom_by", "center_on_castle"):
        assert req in cam, f"CameraCommands missing {req}"

    # SelectionCommands
    sel = _members(SelectionCommands)
    for req in (
        "selected_hero", "selected_building", "selected_peasant", "selected_enemy",
        "try_select_hero", "try_select_building", "try_select_peasant",
        "try_select_enemy", "try_select_hero_at_world",
        "try_select_tax_collector", "try_select_guard",
    ):
        assert req in sel, f"SelectionCommands missing {req}"

    # PlacementCommands
    plc = _members(PlacementCommands)
    for req in ("economy", "buildings", "world", "building_menu",
                "building_list_panel", "build_catalog_panel", "building_panel",
                "place_building"):
        assert req in plc, f"PlacementCommands missing {req}"

    # MenuCommands
    mnu = _members(MenuCommands)
    for req in ("hud", "pause_menu", "debug_panel", "dev_tools_panel",
                "micro_view", "audio_system", "input_manager",
                "show_perf", "apply_hud_pin_action", "capture_screenshot",
                "send_player_message"):
        assert req in mnu, f"MenuCommands missing {req}"

    # GameStateCommands
    gsc = _members(GameStateCommands)
    for req in ("running", "paused", "display_mode", "window_size",
                "get_game_state", "apply_display_settings",
                "request_display_settings", "try_hire_hero",
                "place_bounty", "process_command"):
        assert req in gsc, f"GameStateCommands missing {req}"

    # Backward compat aliases exist
    assert GameCommands is GameStateCommands
    assert EngineBackedGameCommands is EngineCommandHub


# ---------------------------------------------------------------------------
# Test 5: Hero has stable ID
# ---------------------------------------------------------------------------

def test_hero_has_stable_id():
    """Heroes have a hero_id string attribute.

    The hero_id is assigned at construction time via _allocate_fallback_hero_id()
    or an explicit kwarg.  It follows the pattern "hNNNNNNNN" (e.g. "h00000001").
    Wave 1A will use hero_id as the entity ID for SelectionState lookups.
    """
    # Test with explicit hero_id kwarg
    hero_explicit = Hero(100.0, 100.0, hero_class="warrior", hero_id="h_test_explicit")
    assert hasattr(hero_explicit, "hero_id"), "Hero missing hero_id"
    assert isinstance(hero_explicit.hero_id, str), (
        f"hero_id should be str, got {type(hero_explicit.hero_id)}"
    )
    assert hero_explicit.hero_id == "h_test_explicit"

    # Test with fallback auto-allocated hero_id
    hero_auto = Hero(200.0, 200.0, hero_class="ranger")
    assert hasattr(hero_auto, "hero_id"), "Hero missing hero_id"
    assert isinstance(hero_auto.hero_id, str), (
        f"hero_id should be str, got {type(hero_auto.hero_id)}"
    )
    assert len(hero_auto.hero_id) > 0, "hero_id should not be empty"
    # Auto-allocated IDs follow the pattern "hNNNNNNNN"
    assert hero_auto.hero_id.startswith("h"), (
        f"Auto-allocated hero_id should start with 'h', got {hero_auto.hero_id!r}"
    )

    # Verify two heroes get distinct IDs
    hero_auto2 = Hero(300.0, 300.0, hero_class="rogue")
    assert hero_auto.hero_id != hero_auto2.hero_id, (
        "Two auto-allocated heroes should have distinct hero_id values"
    )


# ---------------------------------------------------------------------------
# Test 6: Buildings lack stable entity_id (documents the gap)
# ---------------------------------------------------------------------------

def test_buildings_have_stable_id():
    """Buildings have entity_id -- Wave 1A added stable string IDs.

    entity_id is a non-empty string starting with 'b', assigned at
    construction time via _allocate_building_id().
    """
    from game.entities.buildings.base import Building

    # Test with a direct Building instance (no engine needed)
    b = Building(grid_x=5, grid_y=5, building_type="marketplace")
    assert hasattr(b, "entity_id"), "Building missing entity_id"
    assert isinstance(b.entity_id, str), (
        f"entity_id should be str, got {type(b.entity_id)}"
    )
    assert b.entity_id.startswith("b"), (
        f"Building entity_id should start with 'b', got {b.entity_id!r}"
    )
    assert len(b.entity_id) > 0, "entity_id should not be empty"

    # Two buildings get distinct IDs
    b2 = Building(grid_x=6, grid_y=6, building_type="warrior_guild")
    assert b.entity_id != b2.entity_id, (
        "Two buildings should have distinct entity_id values"
    )

    # Also check against headless engine buildings (castle + starting buildings)
    engine = _make_headless_engine()
    try:
        assert len(engine.sim.buildings) > 0, (
            "Expected at least one building in headless engine"
        )
        seen_ids = set()
        for eb in engine.sim.buildings:
            assert hasattr(eb, "entity_id"), f"Engine building missing entity_id"
            assert isinstance(eb.entity_id, str), (
                f"entity_id should be str, got {type(eb.entity_id)}"
            )
            assert eb.entity_id not in seen_ids, (
                f"Duplicate entity_id {eb.entity_id!r} across engine buildings"
            )
            seen_ids.add(eb.entity_id)
    finally:
        pygame.quit()


# ---------------------------------------------------------------------------
# Test 7: SelectionState stores IDs not objects
# ---------------------------------------------------------------------------

def test_selection_state_stores_ids_not_objects():
    """SelectionState stores string IDs, not entity references."""
    from game.presentation.selection_state import SelectionState

    sel = SelectionState()
    sel.select_hero("h00000001")
    assert sel.selected_hero_id == "h00000001"
    assert isinstance(sel.selected_hero_id, str)

    sel.select_building("b00000001")
    assert sel.selected_building_id == "b00000001"
    assert sel.selected_enemy_id is None  # cleared by select_building

    sel.on_entity_destroyed("b00000001")
    assert sel.selected_building_id is None  # cleared
