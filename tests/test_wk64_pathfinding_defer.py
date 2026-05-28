import pygame
import pytest

from game.engine import GameEngine


def test_exhausted_budget_returns_none_not_empty():
    """Budget exhaustion must be DISTINGUISHABLE from 'no path found'.

    Pre-fix: returns [] (ambiguous). Post-fix: returns None (deferred).
    """
    from game.systems.navigation import compute_path_worldpoints, get_pathfinding_budget
    engine = GameEngine(headless=True)
    try:
        budget = get_pathfinding_budget()
        budget.begin_frame()
        # Force exhaustion.
        budget._frame_plans = budget.MAX_PLANS_PER_FRAME
        result = compute_path_worldpoints(
            engine.sim.world, engine.sim.buildings, 100.0, 100.0, 500.0, 500.0
        )
        assert result is None, (
            "exhausted budget must return None (deferred), not [] (no-path). "
            f"got {result!r}"
        )
    finally:
        pygame.quit()


def test_available_budget_returns_list():
    """With budget available, the function returns a list (a path, or [] if truly no path)."""
    from game.systems.navigation import compute_path_worldpoints, get_pathfinding_budget
    engine = GameEngine(headless=True)
    try:
        budget = get_pathfinding_budget()
        budget.begin_frame()  # fresh budget
        result = compute_path_worldpoints(
            engine.sim.world, engine.sim.buildings, 100.0, 100.0, 200.0, 200.0
        )
        assert isinstance(result, list), f"expected list with budget available, got {result!r}"
    finally:
        pygame.quit()


def test_hero_keeps_existing_path_when_budget_deferred():
    """A hero with a valid path must NOT lose it when the budget is exhausted.

    Setup note (Step A1): a default headless ``GameEngine`` spawns NO heroes,
    so we construct one and append it to ``sim.heroes`` -- the same pattern the
    existing suite uses (see ``tests/test_wk63_engine_boundary.py``
    ``_make_headless_engine_with_hero``). We also have to drive the hero into the
    REAL replan branch of ``Hero.update()`` (game/entities/hero.py ~line 945):

      * The goal must be within A* range (``dist <= TILE_SIZE*20``) AND not in
        black fog, otherwise ``update()`` takes the direct-steering early return
        at ~line 918 and never touches the budget. We use a 320px (10-tile) goal
        and reveal a corridor so the goal tile is VISIBLE, not UNSEEN.
      * The per-replan rate limit (PATH_REPLAN_MIN_INTERVAL_MS) would suppress the
        replan because the headless sim clock starts at 0; we set
        ``_path_last_replan_ms`` far in the past so the rate limit passes and the
        replan is genuinely attempted (then deferred by the exhausted budget).

    The final assertion (``hero.path`` stays non-empty) is unchanged: it is the
    behavioral heart of the fix.
    """
    from game.entities.hero import Hero, HeroState, TILE_SIZE
    from game.systems.navigation import get_pathfinding_budget
    from game.world import Visibility
    engine = GameEngine(headless=True)
    try:
        # Headless engines start with no heroes; construct + append one.
        hero = Hero(400.0, 400.0, hero_class="warrior", hero_id="h_defer_001")
        engine.sim.heroes.append(hero)

        world = engine.sim.world
        # Reveal a corridor around hero->goal so the goal tile is NOT black fog
        # (black-fog goals trigger direct-steering and skip the budget branch).
        hero_gx, hero_gy = world.world_to_grid(hero.x, hero.y)
        for tx in range(hero_gx - 2, hero_gx + 16):
            for ty in range(hero_gy - 2, hero_gy + 3):
                if 0 <= tx < world.width and 0 <= ty < world.height:
                    world.visibility[ty][tx] = Visibility.VISIBLE

        sentinel_path = [(hero.x + 160.0, hero.y), (hero.x + 320.0, hero.y)]
        hero.path = list(sentinel_path)
        hero.state = HeroState.MOVING
        # A goal whose tile differs from the current path goal -> triggers a replan
        # attempt. 320px = 10 tiles, inside the TILE_SIZE*20 A* threshold.
        hero.target_position = (hero.x + 320.0, hero.y)
        hero._path_goal = None  # force goal_changed -> need_replan True
        # Defeat the per-replan rate limit (sim clock is ~0 in headless).
        hero._path_last_replan_ms = -100000

        # Exhaust the budget so the replan attempt is deferred.
        budget = get_pathfinding_budget()
        budget.begin_frame()
        budget._frame_plans = budget.MAX_PLANS_PER_FRAME

        gs = engine.sim.get_game_state(
            screen_w=1920, screen_h=1080, display_mode="windowed", window_size=(1920, 1080),
            placing_building_type=None, debug_ui=False, micro_view_mode=None,
            micro_view_building=None, micro_view_quest_hero=None, micro_view_quest_data=None,
            right_panel_rect=None, llm_available=False, ui_cursor_pos=None,
        )
        hero.update(1.0 / 30.0, gs)

        # The hero may have consumed the first waypoint by moving, but it must still
        # have a non-empty path (it was NOT wiped to [] by the deferred replan).
        assert hero.path, "deferred budget wiped the hero's existing path (regression)"
    finally:
        pygame.quit()
