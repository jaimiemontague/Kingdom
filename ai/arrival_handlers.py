"""Arrival handler registry (WK64, audit item 17).

Extracted from ``bounty_pursuit.handle_moving``'s reached-destination dispatch.
Each handler runs when a hero reaches its task waypoint. Handlers return True
when they fully handle the arrival (the caller then ``return``s); they return
False to let the caller fall through to its default "arrived -> go IDLE" logic.

Dispatch is keyed by :class:`TargetType` via :data:`ARRIVAL_HANDLERS`. The
``bounty`` arrival stays in ``bounty_pursuit.py`` because it is interleaved with
en-route claim/abandon logic and is that module's actual job.

Import direction is ONE-WAY: ``bounty_pursuit`` imports from this module, never
the reverse. This module may import from ``ai.contracts`` and ``game.*`` only.

Determinism: dispatch is keyed by ``TargetType`` (a stable string enum); there
is no wall-clock or ``id()`` ordering. All randomness goes through
``get_rng("ai_basic")`` and all timestamps through ``sim_now_ms()`` exactly as
the pre-extraction code did.
"""

from __future__ import annotations

from typing import Any, Callable

from config import TILE_SIZE
from game.entities.hero import HeroState
from game.sim.determinism import get_rng
from game.sim.direct_prompt_targets import resolve_explore_direction_target
from game.sim.timebase import now_ms as sim_now_ms

from ai.behaviors.task_durations import roll_duration_seconds
from ai.behaviors.view_compat import as_ai_view, view_to_legacy_context
from ai.contracts import HeroTask, TargetType, coerce_task

# WK50 R18: sovereign explore legs chained from the initial compass commit
# (tiles per extension). Moved verbatim from bounty_pursuit.py with the
# direct-prompt arrival logic.
_DIRECT_PROMPT_EXPLORE_EXTENSION_TILES = 12
_DIRECT_PROMPT_EXPLORE_MAX_EXTENSIONS = 2


def _clear_direct_prompt_explore_meta(hero: Any) -> None:
    for attr in (
        "_dp_explore_bearing_ready",
        "_dp_explore_leg_vec",
        "_dp_explore_extensions",
    ):
        if hasattr(hero, attr):
            delattr(hero, attr)


def _compass_from_vec(dx: float, dy: float) -> str | None:
    if abs(dx) < 1e-3 and abs(dy) < 1e-3:
        return None
    if abs(dx) >= abs(dy):
        return "east" if dx > 0 else "west"
    return "south" if dy > 0 else "north"


def _pick_building_at_arrival(
    hero: Any,
    buildings: list[Any],
    dest_x: float,
    dest_y: float,
    *,
    reach_mult: float = 2.5,
) -> Any | None:
    """Prefer the building whose center best matches the sovereign waypoint among those in reach."""
    reach = TILE_SIZE * reach_mult
    best = None
    best_d = 1e18
    for building in buildings:
        if hero.distance_to(building.center_x, building.center_y) > reach:
            continue
        d = (building.center_x - dest_x) ** 2 + (building.center_y - dest_y) ** 2
        if d < best_d:
            best_d = d
            best = building
    return best


def _find_safety_building_for_arrival(hero: Any, buildings: list[Any]) -> Any | None:
    """Inn/castle/home within short range (same window as ``return_home`` direct prompt)."""
    rest_b = None
    if hero.home_building and hero.distance_to(
        hero.home_building.center_x, hero.home_building.center_y
    ) <= TILE_SIZE * 2:
        rest_b = hero.home_building
    if rest_b is None:
        for building in buildings:
            if getattr(building, "building_type", None) in ("castle", "inn"):
                if hero.distance_to(building.center_x, building.center_y) <= TILE_SIZE * 2:
                    rest_b = building
                    break
    return rest_b


def handle_direct_prompt_arrival(ai: Any, hero: Any, task: HeroTask, view: Any) -> bool:
    """Direct-prompt sovereign arrival dispatch (all sub_intents).

    Moved verbatim from bounty_pursuit.handle_moving lines 365-470. Reads the
    sub_intent and any other keys from ``hero.target`` (still a dict). Always
    returns True (it fully handles the arrival, including its own fall-through
    to IDLE for unknown sub-intents).

    WK67 Move 5: consumes the read-only :class:`AiGameView` (``view.buildings``/
    ``view.world``).
    """
    buildings = view.buildings
    sub = str(hero.target.get("sub_intent") or "")
    if sub == "return_home":
        rest_b = _find_safety_building_for_arrival(hero, buildings)
        if rest_b is not None:
            hero.transfer_taxes_to_home()
            hero.start_resting_at_building(rest_b)
        hero.target = None
        hero.target_position = None
        _clear_direct_prompt_explore_meta(hero)
        return True
    if sub == "buy_potions":
        shop = None
        for building in view.buildings:
            if building.building_type in ("marketplace", "blacksmith"):
                if hero.distance_to(building.center_x, building.center_y) < TILE_SIZE * 2:
                    shop = building
                    break
        if shop:
            rng = get_rng("ai_basic")
            duration_sec = roll_duration_seconds("buy_potion", rng)
            setattr(hero, "pending_task", "shopping")
            setattr(hero, "pending_task_building", shop)
            hero.enter_building_briefly(shop, duration_sec=float(duration_sec))
            hero.target = None
            hero.target_position = None
            hero.state = HeroState.SHOPPING
            _clear_direct_prompt_explore_meta(hero)
            return True
    if sub in ("rest_until_healed", "seek_healing", "retreat"):
        rest_b = _find_safety_building_for_arrival(hero, buildings)
        if rest_b is not None:
            if getattr(rest_b, "building_type", None) == "castle" or rest_b is getattr(
                hero, "home_building", None
            ):
                hero.transfer_taxes_to_home()
            hero.start_resting_at_building(rest_b)
        hero.target = None
        hero.target_position = None
        _clear_direct_prompt_explore_meta(hero)
        return True
    if sub == "go_to_known_place":
        tp = hero.target_position
        if tp:
            b = _pick_building_at_arrival(hero, buildings, float(tp[0]), float(tp[1]))
            if b is not None:
                bt = getattr(b, "building_type", None)
                rng = get_rng("ai_basic")
                if bt == "inn":
                    duration_sec = roll_duration_seconds("rest_inn", rng)
                    setattr(hero, "pending_task", "rest_inn")
                    setattr(hero, "pending_task_building", b)
                    hero.start_resting_at_building(b, duration_sec=float(duration_sec))
                elif bt == "castle":
                    hero.transfer_taxes_to_home()
                    hero.start_resting_at_building(b)
                elif bt in ("marketplace", "blacksmith"):
                    task_key = "buy_potion" if bt == "marketplace" else "shopping"
                    duration_sec = roll_duration_seconds(task_key, rng)
                    setattr(hero, "pending_task", "shopping")
                    setattr(hero, "pending_task_building", b)
                    hero.enter_building_briefly(b, duration_sec=float(duration_sec))
                    hero.state = HeroState.SHOPPING
                else:
                    duration_sec = roll_duration_seconds("shopping", rng)
                    hero.enter_building_briefly(b, duration_sec=float(duration_sec))
                    hero.state = HeroState.IDLE
        hero.target = None
        hero.target_position = None
        if hero.state == HeroState.MOVING:
            hero.state = HeroState.IDLE
        _clear_direct_prompt_explore_meta(hero)
        return True
    if sub == "explore_direction":
        cont = int(getattr(hero, "_dp_explore_extensions", 0))
        vec = getattr(hero, "_dp_explore_leg_vec", None)
        world = view.world
        if (
            cont < _DIRECT_PROMPT_EXPLORE_MAX_EXTENSIONS
            and vec is not None
            and world is not None
        ):
            dirn = _compass_from_vec(float(vec[0]), float(vec[1]))
            if dirn:
                # resolve_explore_direction_target (game/sim) reads the world from
                # its mapping arg; hand it the bridge dict carrying the WorldView.
                dest = resolve_explore_direction_target(
                    hero,
                    view_to_legacy_context(view),
                    dirn,
                    tiles_ahead=_DIRECT_PROMPT_EXPLORE_EXTENSION_TILES,
                )
                if dest is not None:
                    hero._dp_explore_extensions = cont + 1
                    hero.set_target_position(float(dest[0]), float(dest[1]))
                    hero.target["started_ms"] = int(sim_now_ms())
                    return True
        hero.target = None
        hero.target_position = None
        hero.state = HeroState.IDLE
        _clear_direct_prompt_explore_meta(hero)
        return True

    hero.target = None
    hero.target_position = None
    hero.state = HeroState.IDLE
    _clear_direct_prompt_explore_meta(hero)
    return True


def handle_visit_poi_arrival(ai: Any, hero: Any, task: HeroTask, view: Any) -> bool:
    """WK55: Arrived at POI -- hero naturally discovers/interacts via proximity system.

    Moved verbatim from bounty_pursuit.handle_moving lines 473-477.
    """
    hero.target = None
    hero.target_position = None
    hero.state = HeroState.IDLE
    return True


def handle_going_home_arrival(ai: Any, hero: Any, task: HeroTask, view: Any) -> bool:
    """Arrived home: transfer taxes, start resting, clear target.

    Moved verbatim from bounty_pursuit.handle_moving lines 480-485.
    """
    hero.transfer_taxes_to_home()
    hero.start_resting()
    hero.target = None
    hero.target_position = None
    return True


def handle_shopping_arrival(ai: Any, hero: Any, task: HeroTask, view: Any) -> bool:
    """Arrived shopping (WK11: deferred -- purchase on exit).

    Moved verbatim from bounty_pursuit.handle_moving lines 488-505. Reads the
    same legacy keys via ``task.payload`` (equal to the old dict keys).
    """
    shop_building = task.payload.get("marketplace") or task.payload.get("blacksmith")
    if shop_building:
        rng = get_rng("ai_basic")
        # WK24: marketplace (potion) trips use shorter buy_potion band; blacksmith uses generic shopping.
        task_key = (
            "buy_potion"
            if task.payload.get("marketplace") is not None
            else "shopping"
        )
        duration_sec = roll_duration_seconds(task_key, rng)
        setattr(hero, "pending_task", "shopping")
        setattr(hero, "pending_task_building", shop_building)
        hero.enter_building_briefly(shop_building, duration_sec=float(duration_sec))
    hero.target = None
    hero.target_position = None
    hero.state = HeroState.SHOPPING
    return True


def handle_rest_inn_arrival(ai: Any, hero: Any, task: HeroTask, view: Any) -> bool:
    """Rest at Inn (WK11): enter and heal inside; finalize on exit.

    Moved verbatim from bounty_pursuit.handle_moving lines 508-518.
    """
    inn = task.payload.get("inn")
    if inn:
        rng = get_rng("ai_basic")
        duration_sec = roll_duration_seconds("rest_inn", rng)
        setattr(hero, "pending_task", "rest_inn")
        setattr(hero, "pending_task_building", inn)
        hero.start_resting_at_building(inn, duration_sec=float(duration_sec))
    hero.target = None
    hero.target_position = None
    return True


def handle_buy_meal_arrival(ai: Any, hero: Any, task: HeroTask, view: Any) -> bool:
    """WK61-R10: buy meal at food stand when arrival waypoint reached.

    Delegates to the hunger behavior, exactly as the old code did
    (bounty_pursuit.handle_moving lines 521-524). Returns the hunger behavior's
    result so the caller falls through to the default IDLE when it returns False
    (matching the pre-extraction fall-through).
    """
    hunger_behavior = getattr(ai, "hunger_behavior", None)
    if hunger_behavior is not None and hunger_behavior.handle_meal_arrival(ai, hero, view):
        return True
    return False


def handle_get_drink_arrival(ai: Any, hero: Any, task: HeroTask, view: Any) -> bool:
    """Get a drink at Inn (WK11): enter, pay on exit.

    Moved verbatim from bounty_pursuit.handle_moving lines 527-538.
    """
    inn = task.payload.get("inn")
    if inn:
        rng = get_rng("ai_basic")
        duration_sec = roll_duration_seconds("get_drink", rng)
        setattr(hero, "pending_task", "get_drink")
        setattr(hero, "pending_task_building", inn)
        hero.enter_building_briefly(inn, duration_sec=float(duration_sec))
    hero.target = None
    hero.target_position = None
    hero.state = HeroState.IDLE
    return True


ARRIVAL_HANDLERS: dict[TargetType, Callable[[Any, Any, HeroTask, Any], bool]] = {
    TargetType.DIRECT_PROMPT: handle_direct_prompt_arrival,
    TargetType.VISIT_POI: handle_visit_poi_arrival,
    TargetType.GOING_HOME: handle_going_home_arrival,
    TargetType.SHOPPING: handle_shopping_arrival,
    TargetType.REST_INN: handle_rest_inn_arrival,
    TargetType.BUY_MEAL: handle_buy_meal_arrival,
    TargetType.GET_DRINK: handle_get_drink_arrival,
}


def dispatch_arrival(ai: Any, hero: Any, view: Any) -> bool:
    """Look up and run the arrival handler for the hero's current task.

    Returns True if a handler ran and handled it (caller should ``return``).
    Returns False if there is no task, no matching handler, or the target is a
    live entity (combat) -- in which case the caller falls through to its default
    "arrived, go IDLE" logic. This preserves the pre-extraction behavior where a
    ``bounty`` dict (no arrival handler) and live-entity targets fell through to
    the default IDLE branch.

    WK67 Move 5: ``view`` is the read-only :class:`AiGameView`.
    """
    view = as_ai_view(view)
    task = coerce_task(getattr(hero, "target", None))
    if task is None:
        return False
    handler = ARRIVAL_HANDLERS.get(task.type)
    if handler is None:
        return False
    return handler(ai, hero, task, view)
