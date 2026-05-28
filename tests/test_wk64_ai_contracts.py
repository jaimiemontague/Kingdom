"""WK64 Phase B Wave 0 — AI arrival-behavior characterization tests.

Sprint: wk64_ai_contracts_and_system_runner
Round:  wk64_pb_w0_characterization
Owner:  Agent 11 (QA_TestEngineering_Lead)

Purpose
-------
Lock down the *observable* outcome of each hero "arrival" type, driving through
the real ``BasicAI`` / ``bounty_pursuit.handle_moving`` path. These pin the
arrival contract that Wave 2's ``ai/arrival_handlers.py`` extraction MUST
preserve. They are a faithful SNAPSHOT of current (post-Phase-A) behavior, so
they PASS against current code with no production changes.

Post-conditions are taken verbatim from ``ai/behaviors/bounty_pursuit.py``
``handle_moving`` (the reached-destination dispatch, ~lines 361-542) and
``ai/behaviors/hunger.py`` ``handle_meal_arrival`` (~lines 219-238):
  * visit_poi   -> hero.target is None, state IDLE                 (bp 473-477)
  * going_home  -> hero.target is None                            (bp 480-485)
  * shopping    -> hero.target None, state SHOPPING,
                   pending_task == "shopping", pending_task_building is shop
                                                                  (bp 488-505)
  * rest_inn    -> hero.target None, pending_task == "rest_inn"   (bp 508-518)
  * buy_meal    -> hero.target None, state IDLE                   (bp 521-524 ->
                                                                   hunger 229-238)
  * get_drink   -> hero.target None, state IDLE,
                   pending_task == "get_drink"                    (bp 527-538)

Honesty note (faithful-snapshot, NOT maximal coverage)
------------------------------------------------------
The default ``GameEngine(headless=True)`` world contains ZERO heroes and no
wired ``ai_controller``, and only a subset of buildings (castle, warrior_guild,
ranger_guild, marketplace, food_stand, guardhouse -- no inn, no blacksmith, no
home_building set on a hero).

The two behaviors Wave 2 actually converts to ``HeroTask`` -- buy_meal and
shopping -- have their required building (food_stand, marketplace) present in
the default world, so those tests CONSTRUCT a hero + ``BasicAI`` controller and
genuinely RUN the real arrival dispatch (no skip). This matches the
hero-construction pattern in ``tests/test_wk64_pathfinding_defer.py`` and
``tests/test_wk63_engine_boundary.py::_make_headless_engine_with_hero`` and
fabricates no buildings -- only entities the suite already creates elsewhere.

The remaining arrival tests (rest_inn, get_drink, going_home, visit_poi) depend
on buildings/home the default world does not provide; per the plan they
``pytest.skip`` rather than fabricating that state (the existing AI suite covers
them). ``test_contracts_module_round_trips_when_present`` skips until Wave 1
lands ``ai/contracts.py``.
"""

import pygame
import pytest

from game.engine import GameEngine
from game.entities.hero import HeroState


def _engine():
    return GameEngine(headless=True)


def _game_state(engine):
    """Build the full game_state dict bounty_pursuit.handle_moving expects."""
    return engine.sim.get_game_state(
        screen_w=1920, screen_h=1080, display_mode="windowed",
        window_size=(1920, 1080), placing_building_type=None, debug_ui=False,
        micro_view_mode=None, micro_view_building=None, micro_view_quest_hero=None,
        micro_view_quest_data=None, right_panel_rect=None, llm_available=False,
        ui_cursor_pos=None,
    )


def test_buy_meal_arrival_purchases_and_returns_idle():
    """Arriving at a buy_meal waypoint buys a meal and resets to IDLE.

    This pins the BUY_MEAL arrival contract that arrival_handlers.py must
    preserve after extraction.

    The default headless world has a ``food_stand`` but ZERO heroes and no
    wired ``ai_controller``, so we construct both -- the same pattern used by
    ``tests/test_wk64_pathfinding_defer.py`` and
    ``tests/test_wk63_engine_boundary.py::_make_headless_engine_with_hero``.
    We do NOT fabricate the food stand (it exists in the default world); we
    only skip as a last resort if that invariant ever changes. This drives the
    real ``BasicAI.handle_moving`` -> ``bounty_pursuit`` buy_meal branch ->
    ``hunger.handle_meal_arrival`` path, so it genuinely RUNS (not skips).
    """
    from ai.basic_ai import BasicAI
    from ai.behaviors.hunger import find_nearest_food_stand
    from game.entities.hero import Hero

    engine = _engine()
    try:
        ai = engine.sim.ai_controller or BasicAI()

        # Locate the food stand the default world spawns; only skip if the
        # world invariant ever changes (do NOT fabricate the building).
        stand = find_nearest_food_stand(
            Hero(0.0, 0.0, hero_class="warrior", hero_id="h_probe_meal"),
            engine.sim.buildings,
        )
        if stand is None:
            pytest.skip("default headless world unexpectedly has no food stand")

        # Construct + place a hero AT the food stand so target_position is reached.
        hero = Hero(
            float(stand.center_x), float(stand.center_y),
            hero_class="warrior", hero_id="h_test_buy_meal",
        )
        engine.sim.heroes.append(hero)
        hero.gold = 999
        hero.state = HeroState.MOVING
        hero.target = {"type": "buy_meal", "food_stand": stand}
        hero.target_position = (hero.x, hero.y)

        ai.handle_moving(hero, _game_state(engine))

        assert hero.target is None
        assert hero.state == HeroState.IDLE
    finally:
        pygame.quit()


def test_shopping_arrival_enters_shop_and_sets_pending_task():
    """Arriving at a shopping waypoint clears target, enters SHOPPING, and
    records the deferred pending_task + building (purchase happens on exit).

    bounty_pursuit.handle_moving lines 488-505.
    """
    from ai.basic_ai import BasicAI
    from game.entities.hero import Hero

    engine = _engine()
    try:
        ai = engine.sim.ai_controller or BasicAI()

        # Shopping reads target["marketplace"] or target["blacksmith"] for the
        # shop building. The default world has a marketplace; use it. Only skip
        # as a last resort if that world invariant ever changes (do NOT
        # fabricate the building).
        shop = next(
            (b for b in engine.sim.buildings
             if getattr(b, "building_type", None) == "marketplace"),
            None,
        )
        if shop is None:
            pytest.skip("default headless world unexpectedly has no marketplace")

        # Construct + place a hero AT the marketplace so target_position is reached.
        hero = Hero(
            float(shop.center_x), float(shop.center_y),
            hero_class="warrior", hero_id="h_test_shopping",
        )
        engine.sim.heroes.append(hero)
        hero.state = HeroState.MOVING
        hero.target = {"type": "shopping", "marketplace": shop, "blacksmith": None}
        hero.target_position = (hero.x, hero.y)

        ai.handle_moving(hero, _game_state(engine))

        assert hero.target is None
        assert hero.state == HeroState.SHOPPING
        assert getattr(hero, "pending_task", None) == "shopping"
        assert getattr(hero, "pending_task_building", None) is shop
    finally:
        pygame.quit()


def test_rest_inn_arrival_sets_pending_rest_inn():
    """Arriving at a rest_inn waypoint clears target and records the deferred
    rest_inn pending_task. Needs an inn -> skip if absent.

    bounty_pursuit.handle_moving lines 508-518.
    """
    engine = _engine()
    try:
        ai = engine.sim.ai_controller
        heroes = engine.sim.heroes
        if not heroes:
            pytest.skip("no heroes in headless engine")
        hero = heroes[0]

        inn = next(
            (b for b in engine.sim.buildings
             if getattr(b, "building_type", None) == "inn"),
            None,
        )
        if inn is None:
            pytest.skip("default headless world has no inn")

        hero.x, hero.y = float(inn.center_x), float(inn.center_y)
        hero.state = HeroState.MOVING
        hero.target = {"type": "rest_inn", "inn": inn}
        hero.target_position = (hero.x, hero.y)

        ai.handle_moving(hero, _game_state(engine))

        assert hero.target is None
        assert getattr(hero, "pending_task", None) == "rest_inn"
    finally:
        pygame.quit()


def test_get_drink_arrival_sets_pending_get_drink_and_idle():
    """Arriving at a get_drink waypoint clears target, returns IDLE, and records
    the deferred get_drink pending_task. Needs an inn -> skip if absent.

    bounty_pursuit.handle_moving lines 527-538.
    """
    engine = _engine()
    try:
        ai = engine.sim.ai_controller
        heroes = engine.sim.heroes
        if not heroes:
            pytest.skip("no heroes in headless engine")
        hero = heroes[0]

        inn = next(
            (b for b in engine.sim.buildings
             if getattr(b, "building_type", None) == "inn"),
            None,
        )
        if inn is None:
            pytest.skip("default headless world has no inn")

        hero.x, hero.y = float(inn.center_x), float(inn.center_y)
        hero.state = HeroState.MOVING
        hero.target = {"type": "get_drink", "inn": inn}
        hero.target_position = (hero.x, hero.y)

        ai.handle_moving(hero, _game_state(engine))

        assert hero.target is None
        assert hero.state == HeroState.IDLE
        assert getattr(hero, "pending_task", None) == "get_drink"
    finally:
        pygame.quit()


def test_going_home_arrival_clears_target():
    """Arriving at a going_home waypoint transfers taxes, starts resting, and
    clears the target.

    bounty_pursuit.handle_moving lines 480-485. Needs hero.home_building to make
    the arrival meaningful -> skip if absent.
    """
    engine = _engine()
    try:
        ai = engine.sim.ai_controller
        heroes = engine.sim.heroes
        if not heroes:
            pytest.skip("no heroes in headless engine")
        hero = heroes[0]

        if getattr(hero, "home_building", None) is None:
            pytest.skip("hero has no home_building in default headless world")

        home = hero.home_building
        hero.x, hero.y = float(home.center_x), float(home.center_y)
        hero.state = HeroState.MOVING
        hero.target = {"type": "going_home"}
        hero.target_position = (hero.x, hero.y)

        ai.handle_moving(hero, _game_state(engine))

        assert hero.target is None
    finally:
        pygame.quit()


def test_visit_poi_arrival_clears_target_and_idles():
    """Arriving at a visit_poi waypoint clears the target and returns IDLE
    (interaction is handled by the proximity system, not here).

    bounty_pursuit.handle_moving lines 473-477.
    """
    engine = _engine()
    try:
        ai = engine.sim.ai_controller
        heroes = engine.sim.heroes
        if not heroes:
            pytest.skip("no heroes in headless engine")
        hero = heroes[0]

        # A visit_poi arrival does not require a specific building object; the
        # target_position alone marks "arrived". Use the hero's own position.
        hero.state = HeroState.MOVING
        hero.target = {"type": "visit_poi"}
        hero.target_position = (hero.x, hero.y)

        ai.handle_moving(hero, _game_state(engine))

        assert hero.target is None
        assert hero.state == HeroState.IDLE
    finally:
        pygame.quit()


def test_contracts_module_round_trips_when_present():
    """After Wave 1, HeroTask.to_dict/from_dict must round-trip the legacy shape.

    Skips cleanly until ai/contracts.py lands so this file passes on current code.
    """
    pytest.importorskip("ai.contracts")
    from ai.contracts import HeroTask, TargetType, coerce_task

    d = {"type": "shopping", "item": "potion", "marketplace": None,
         "blacksmith": None, "shop_building": None}
    task = HeroTask.from_dict(d)
    assert task is not None
    assert task.type == TargetType.SHOPPING
    # Round-trip preserves every legacy key the arrival handler reads.
    back = task.to_dict()
    assert back["type"] == "shopping"
    for k in ("item", "marketplace", "blacksmith", "shop_building"):
        assert k in back
    # A live entity target is NOT a task.
    assert coerce_task(object()) is None
    assert coerce_task(None) is None
