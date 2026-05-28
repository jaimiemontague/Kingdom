"""
Deterministic pathfinding budget tests.

Sprint: wk63_engine_boundary_cleanup
Wave 1B: Verify that pathfinding budget gates on deterministic expansion
counts (not wall-clock time), resets each frame, and that find_path
returns (path, expansions) tuples.
"""

from __future__ import annotations

import pygame
import pytest


def test_budget_gates_on_expansion_count_not_time():
    """Budget exhaustion depends on expansion count, not wall-clock time."""
    from game.systems.navigation import PathfindingBudget

    budget = PathfindingBudget()
    budget.begin_frame()

    # Record plans with high wall-clock time but low expansions
    budget.record_plan(expansions=100, wall_ms=999.0)
    assert budget.budget_available(), (
        "Budget should still be available: only 100 expansions used, "
        "even though wall_ms is 999"
    )

    # Now exhaust the expansion budget
    budget.record_plan(expansions=PathfindingBudget.MAX_EXPANSIONS_PER_FRAME, wall_ms=0.1)
    assert not budget.budget_available(), (
        "Budget should be exhausted after MAX_EXPANSIONS_PER_FRAME expansions"
    )


def test_budget_gates_on_plan_count():
    """Budget also limits number of plans per frame."""
    from game.systems.navigation import PathfindingBudget

    budget = PathfindingBudget()
    budget.begin_frame()

    for i in range(PathfindingBudget.MAX_PLANS_PER_FRAME):
        assert budget.budget_available(), f"Budget should be available at plan {i}"
        budget.record_plan(expansions=1, wall_ms=0.01)

    assert not budget.budget_available(), (
        "Budget should be exhausted after MAX_PLANS_PER_FRAME plans"
    )


def test_budget_resets_each_frame():
    """begin_frame() resets all counters."""
    from game.systems.navigation import PathfindingBudget

    budget = PathfindingBudget()
    budget.begin_frame()
    budget.record_plan(expansions=99999, wall_ms=99999.0)
    assert not budget.budget_available()

    budget.begin_frame()
    assert budget.budget_available()
    assert budget._frame_plans == 0
    assert budget._frame_expansions == 0
    assert budget._frame_ms_used == 0.0


def test_find_path_returns_expansion_count():
    """find_path() returns (path, expansions) tuple."""
    from game.systems.pathfinding import find_path
    from game.engine import GameEngine

    engine = GameEngine(headless=True)
    try:
        world = engine.sim.world
        result = find_path(world, (10, 10), (15, 15), engine.sim.buildings)
        assert isinstance(result, tuple), f"find_path should return tuple, got {type(result)}"
        assert len(result) == 2, f"find_path should return (path, expansions), got len={len(result)}"
        path, expansions = result
        assert isinstance(path, list)
        assert isinstance(expansions, int)
        assert expansions >= 0
    finally:
        pygame.quit()
