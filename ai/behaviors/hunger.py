"""Deterministic hero hunger / food-stand meal behavior (WK61-R10)."""

from __future__ import annotations

from typing import Any

from config import FOOD_MEAL_COST_GOLD
from game.entities.hero import HeroState

from ai.behaviors.movement import route_to_building
from ai.behaviors.view_compat import as_ai_view
from ai.contracts import HeroTask, TargetType, assign_hero_task

# Target types hunger may interrupt (discretionary movement only).
_INTERRUPTIBLE_TARGET_TYPES = frozenset({
    "patrol",
    "explore_frontier",
    "visit_poi",
    "get_drink",
    "shopping",
})

_CRITICAL_HP_FRACTION = 0.15


def _building_sort_key(building: Any) -> tuple:
    """Stable tie-break when two food stands are equidistant."""
    return (
        int(getattr(building, "grid_x", 0)),
        int(getattr(building, "grid_y", 0)),
        int(getattr(building, "placed_time_ms", 0) or 0),
    )


def find_nearest_food_stand(hero: Any, buildings: list[Any]) -> Any | None:
    """Return nearest constructed, live food stand (distance, then grid coords)."""
    candidates: list[tuple[float, tuple, Any]] = []
    for building in buildings:
        if getattr(building, "building_type", None) != "food_stand":
            continue
        if not getattr(building, "is_constructed", True):
            continue
        if int(getattr(building, "hp", 0) or 0) <= 0:
            continue
        dist = hero.distance_to(float(building.center_x), float(building.center_y))
        candidates.append((dist, _building_sort_key(building), building))

    if not candidates:
        return None
    candidates.sort(key=lambda row: (row[0], row[1]))
    return candidates[0][2]


def _log_no_food_stand_once(ai: Any, hero: Any) -> None:
    """Log missing food stand at most once per hero (WK61-R11)."""
    logged = getattr(ai, "_hunger_no_stand_logged_heroes", None)
    if logged is None:
        logged = set()
        ai._hunger_no_stand_logged_heroes = logged
    if hero.name in logged:
        return
    logged.add(hero.name)
    ai._debug_log(f"{hero.name} -> hunger urgent but no food stand available")


def should_seek_meal(hero: Any) -> bool:
    """True when hunger is urgent, hero can afford a meal, and HP is not critical."""
    if not getattr(hero, "hunger_urgent", False):
        return False
    if float(getattr(hero, "health_percent", 1.0)) <= _CRITICAL_HP_FRACTION:
        return False
    if int(getattr(hero, "gold", 0) or 0) < int(FOOD_MEAL_COST_GOLD):
        return False
    return True


def go_to_food_stand(ai: Any, hero: Any, food_stand: Any, view: Any) -> None:
    """Route hero toward the nearest reachable tile beside a food stand."""
    view = as_ai_view(view)
    buildings = view.buildings
    world = view.world

    route_to_building(hero, world, buildings, food_stand)

    hero.state = HeroState.MOVING
    # WK64 (audit item 15): author the task via the typed HeroTask API.
    # assign_hero_task serializes to the legacy dict shape
    # ({"type": "buy_meal", "food_stand": food_stand}) so hero.target stays a
    # dict and every existing reader (handle_meal_arrival, maybe_redirect_for_meal)
    # keeps working unchanged.
    task = HeroTask(
        type=TargetType.BUY_MEAL,
        target_ref=food_stand,
        payload={"food_stand": food_stand},
    )
    assign_hero_task(hero, task)
    ai.set_intent(hero, "shopping")
    ai.record_decision(
        hero,
        action="seek_meal",
        reason="hunger urgent",
        intent="shopping",
        source="system",
        inputs_summary={"food_stand": getattr(food_stand, "building_type", "food_stand")},
    )
    ai._debug_log(
        f"{hero.name} -> seeking meal at food stand ({food_stand.grid_x}, {food_stand.grid_y})",
        throttle_key=f"{hero.name}_seek_meal",
    )


def try_buy_meal(ai: Any, hero: Any, food_stand: Any) -> bool:
    """Attempt immediate meal purchase when in range."""
    if not hasattr(hero, "buy_meal_at_food_stand"):
        return False
    if hero.buy_meal_at_food_stand(food_stand):
        ai.record_decision(
            hero,
            action="buy_meal",
            reason="hunger urgent",
            intent="shopping",
            source="system",
            inputs_summary={"cost_gold": FOOD_MEAL_COST_GOLD},
        )
        ai._debug_log(f"{hero.name} -> bought meal at food stand")
        return True
    return False


def maybe_seek_meal_idle(ai: Any, hero: Any, view: Any) -> bool:
    """Idle hook: buy in range or path to the nearest food stand."""
    view = as_ai_view(view)
    if not should_seek_meal(hero):
        return False

    food_stand = find_nearest_food_stand(hero, view.buildings)
    if food_stand is None:
        _log_no_food_stand_once(ai, hero)
        return False

    if hero._is_at_food_stand(food_stand):
        if try_buy_meal(ai, hero, food_stand):
            hero.target = None
            hero.target_position = None
            hero.state = HeroState.IDLE
            return True
        return False

    go_to_food_stand(ai, hero, food_stand, view)
    return True


def maybe_redirect_for_meal(ai: Any, hero: Any, view: Any) -> bool:
    """Interrupt discretionary movement when hunger becomes urgent."""
    view = as_ai_view(view)
    if hero.state != HeroState.MOVING:
        return False
    if not should_seek_meal(hero):
        return False

    target = getattr(hero, "target", None)
    if isinstance(target, dict):
        target_type = target.get("type")
        if target_type == "buy_meal":
            return False
        if target_type not in _INTERRUPTIBLE_TARGET_TYPES:
            return False

    food_stand = find_nearest_food_stand(hero, view.buildings)
    if food_stand is None:
        _log_no_food_stand_once(ai, hero)
        return False

    go_to_food_stand(ai, hero, food_stand, view)
    return True


def maybe_interrupt_shopping_for_meal(ai: Any, hero: Any, view: Any) -> bool:
    """Leave marketplace shopping when hunger is urgent and hero can afford a meal."""
    view = as_ai_view(view)
    if hero.state != HeroState.SHOPPING:
        return False
    if not should_seek_meal(hero):
        return False

    if getattr(hero, "is_inside_building", False):
        hero.pop_out_of_building()
        setattr(hero, "pending_task", None)
        setattr(hero, "pending_task_building", None)

    food_stand = find_nearest_food_stand(hero, view.buildings)
    if food_stand is None:
        _log_no_food_stand_once(ai, hero)
        return False

    go_to_food_stand(ai, hero, food_stand, view)
    return True


def tick_meal_hunger(ai: Any, hero: Any, view: Any) -> bool:
    """Run hunger meal logic when HP is not critical. Returns True if hero was redirected."""
    view = as_ai_view(view)
    if float(getattr(hero, "health_percent", 1.0)) <= _CRITICAL_HP_FRACTION:
        return False

    st = hero.state
    if st == HeroState.IDLE:
        return maybe_seek_meal_idle(ai, hero, view)
    if st == HeroState.MOVING:
        return maybe_redirect_for_meal(ai, hero, view)
    if st == HeroState.SHOPPING:
        return maybe_interrupt_shopping_for_meal(ai, hero, view)
    return False


def maybe_apply_meal_before_llm_action(ai: Any, hero: Any, view: Any, action: str) -> bool:
    """If LLM/fallback chose explore or shop while hungry, redirect to food stand."""
    view = as_ai_view(view)
    if action not in ("explore", "buy_item", "seek_meal"):
        return False
    if action == "seek_meal":
        return tick_meal_hunger(ai, hero, view)
    if not should_seek_meal(hero):
        return False
    return tick_meal_hunger(ai, hero, view)


def handle_meal_arrival(ai: Any, hero: Any, view: Any) -> bool:
    """Called when hero reaches a buy_meal waypoint; purchase if possible."""
    view = as_ai_view(view)
    target = getattr(hero, "target", None)
    if not isinstance(target, dict) or target.get("type") != "buy_meal":
        return False

    food_stand = target.get("food_stand")
    if food_stand is None:
        food_stand = find_nearest_food_stand(hero, view.buildings)

    if food_stand is not None and try_buy_meal(ai, hero, food_stand):
        hero.target = None
        hero.target_position = None
        hero.state = HeroState.IDLE
        return True

    hero.target = None
    hero.target_position = None
    hero.state = HeroState.IDLE
    return True
