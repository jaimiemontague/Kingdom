"""Defense and retreat behavior extracted from ``BasicAI``."""

from __future__ import annotations

import os
from typing import Any

from config import TILE_SIZE
from game.entities.hero import HeroState
from game.sim.hero_guardrails_tunables import TARGET_COMMIT_WINDOW_S
from game.sim.timebase import now_ms as sim_now_ms

from ai.behaviors.view_compat import as_ai_view

# Mythos S5 (ai-threat-cache-staggered, memo half): hero-INDEPENDENT threat
# scans (castle/home-guild ``building_threatened``, the under-attack
# economic/neutral building prefilters) used to be recomputed for every hero
# every tick — 24x identical work at the gate scenario. They are memoized on the
# AiGameView, which SimEngine rebuilds fresh each tick (sim_engine.update ->
# build_ai_view), so the memo's lifetime is exactly one tick. Enemy/building
# threat state does not mutate during the AI pass (combat/damage runs later in
# the tick), so the memoized value == a fresh scan at every decision point —
# exact equivalence, WK67 digest byte-identical (pinned by
# tests/test_mythos_sim_tick.py). Views that cannot host the memo (the
# slots-based legacy-dict adapter used by observe_sync/direct-prompt) silently
# fall back to uncached scans. KINGDOM_AI_THREAT_MEMO=0 disables (A/B hatch).
_THREAT_MEMO_ENABLED = os.environ.get("KINGDOM_AI_THREAT_MEMO", "1") != "0"


def _view_tick_memo(view: Any) -> dict | None:
    """Per-tick memo dict hosted on the AI view, or None when not memoizable."""
    if not _THREAT_MEMO_ENABLED:
        return None
    memo = getattr(view, "_mythos_tick_memo", None)
    if memo is None:
        memo = {}
        try:
            # AiGameView is a frozen dataclass — bypass its setattr guard.
            object.__setattr__(view, "_mythos_tick_memo", memo)
        except (AttributeError, TypeError):
            return None  # slots-based adapter (legacy dict path): no caching
    return memo


def _commit_until_ms(now_ms: int) -> int:
    """Anti-oscillation target-commit deadline (sim-time ms) from ``now_ms``.

    Reproduces the inline expression copy-pasted across the engage sites:
    ``int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))``.
    """
    return int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))


def engage(
    hero: Any,
    enemy: Any,
    now_ms: int,
    *,
    set_fighting: bool = False,
    set_position: bool = True,
) -> None:
    """Commit ``hero`` to ``enemy`` as a combat target (WK74 dedup helper).

    Consolidates the "engage enemy" block duplicated ~8x in this module:
    set the target, refresh the anti-oscillation commit window, and -- depending
    on the call site -- either flip to ``FIGHTING`` (in attack range) or steer the
    hero toward the enemy's position (out of range). Callers that need a specific
    ``hero.state`` (e.g. ``MOVING``) still set it themselves after the call.
    """
    hero.target = enemy
    hero._target_commit_until_ms = _commit_until_ms(now_ms)
    if set_fighting:
        hero.state = HeroState.FIGHTING
    if set_position:
        hero.set_target_position(enemy.x, enemy.y)


def building_threatened(view: Any, building: Any, radius_tiles: int) -> bool:
    """True iff ``building`` faces an ACTUAL threat: recently damaged
    (``is_under_attack``, the 3 s window that exists to prevent permanent
    "defend forever") OR a live enemy within ``radius_tiles`` of its center.

    WK127-T1: the task router gates the home/castle defend hijack on this
    instead of ``is_damaged`` (any missing HP, forever) — a chipped building
    with stalled repairs and no enemies must NOT statue its heroes.
    Deterministic, read-only: no RNG, no state writes.
    """
    view = as_ai_view(view)
    memo = _view_tick_memo(view)
    if memo is not None:
        key = ("threatened", id(building), int(radius_tiles))
        hit = memo.get(key)
        if hit is None:
            hit = _building_threatened_scan(view, building, radius_tiles)
            memo[key] = hit
        return hit
    return _building_threatened_scan(view, building, radius_tiles)


def _building_threatened_scan(view: Any, building: Any, radius_tiles: int) -> bool:
    """The original uncached scan (see ``building_threatened``)."""
    if getattr(building, "is_under_attack", False):
        return True
    radius = TILE_SIZE * radius_tiles
    cx, cy = building.center_x, building.center_y
    for enemy in view.enemies:
        if getattr(enemy, "is_alive", False) and enemy.distance_to(cx, cy) < radius:
            return True
    return False


def defend_castle(ai: Any, hero: Any, view: Any, castle: Any) -> None:
    """Send hero to defend the castle when it is threatened (recently damaged
    or a live enemy nearby — see ``building_threatened``; WK127-T1 dropped the
    old chip-damage gate)."""
    view = as_ai_view(view)
    enemies = view.enemies

    # WK2 anti-oscillation: if currently committed to a valid combat target, don't thrash.
    now_ms = int(sim_now_ms())
    if now_ms < int(getattr(hero, "_target_commit_until_ms", 0) or 0):
        cur = getattr(hero, "target", None)
        if cur is not None and hasattr(cur, "is_alive") and getattr(cur, "is_alive", False):
            return

    target_enemy = None
    target_dist = float("inf")
    for enemy in enemies:
        if enemy.is_alive:
            dist_to_castle = enemy.distance_to(castle.center_x, castle.center_y)
            if dist_to_castle < target_dist:
                target_dist = dist_to_castle
                target_enemy = enemy

    if target_enemy:
        dist_to_hero = hero.distance_to(target_enemy.x, target_enemy.y)
        if dist_to_hero <= hero.attack_range:
            engage(hero, target_enemy, now_ms, set_fighting=True, set_position=False)
            return
        engage(hero, target_enemy, now_ms)
        hero.state = HeroState.MOVING
        return

    dist_to_castle = hero.distance_to(castle.center_x, castle.center_y)
    if dist_to_castle > TILE_SIZE * 3:
        hero.target = {"type": "defend_castle"}
        hero.set_target_position(castle.center_x + TILE_SIZE, castle.center_y)
        hero.state = HeroState.MOVING
    else:
        hero.state = HeroState.IDLE


def defend_home_building(ai: Any, hero: Any, view: Any) -> None:
    """Hero defends their threatened home building (recently damaged or a live
    enemy nearby — see ``building_threatened``; WK127-T1 dropped the old
    chip-damage gate)."""
    view = as_ai_view(view)
    enemies = view.enemies

    # WK2 anti-oscillation: if currently committed to a valid combat target, don't thrash.
    now_ms = int(sim_now_ms())
    if now_ms < int(getattr(hero, "_target_commit_until_ms", 0) or 0):
        cur = getattr(hero, "target", None)
        if cur is not None and hasattr(cur, "is_alive") and getattr(cur, "is_alive", False):
            return

    if not hero.home_building:
        return

    building = hero.home_building

    nearest_enemy = None
    nearest_dist = float("inf")

    for enemy in enemies:
        if enemy.is_alive:
            dist_to_building = enemy.distance_to(building.center_x, building.center_y)
            if dist_to_building < TILE_SIZE * 5:
                dist_to_hero = hero.distance_to(enemy.x, enemy.y)
                if dist_to_hero < nearest_dist:
                    nearest_dist = dist_to_hero
                    nearest_enemy = enemy

    if nearest_enemy:
        if nearest_dist <= hero.attack_range:
            engage(hero, nearest_enemy, now_ms, set_fighting=True, set_position=False)
        else:
            engage(hero, nearest_enemy, now_ms)
    else:
        dist_to_home = hero.distance_to(building.center_x, building.center_y)
        if dist_to_home > TILE_SIZE * 2:
            hero.set_target_position(building.center_x + TILE_SIZE, building.center_y)
        else:
            hero.state = HeroState.IDLE


# WK15: Economic building types warriors prioritize defending (neutral buildings that generate tax).
ECONOMIC_NEUTRAL_TYPES = ("farm", "food_stand")


def _attacked_economic_buildings(view: Any) -> list:
    """Hero-independent prefilter: under-attack economic buildings, in
    ``view.buildings`` order (memoized per tick — see ``_view_tick_memo``)."""
    memo = _view_tick_memo(view)
    if memo is not None:
        hit = memo.get("attacked_econ")
        if hit is not None:
            return hit
    out = []
    for building in view.buildings:
        bt = getattr(building, "building_type", None)
        if bt is not None and hasattr(bt, "value"):
            bt = bt.value
        if bt not in ECONOMIC_NEUTRAL_TYPES:
            continue
        if getattr(building, "hp", 0) <= 0:
            continue
        if not getattr(building, "is_under_attack", False):
            continue
        out.append(building)
    if memo is not None:
        memo["attacked_econ"] = out
    return out


def _attacked_neutral_buildings(view: Any) -> list:
    """Hero-independent prefilter: under-attack neutral buildings, in
    ``view.buildings`` order (memoized per tick — see ``_view_tick_memo``)."""
    memo = _view_tick_memo(view)
    if memo is not None:
        hit = memo.get("attacked_neutral")
        if hit is not None:
            return hit
    out = []
    for building in view.buildings:
        if not getattr(building, "is_neutral", False):
            continue
        if getattr(building, "hp", 0) <= 0:
            continue
        if not getattr(building, "is_under_attack", False):
            continue
        out.append(building)
    if memo is not None:
        memo["attacked_neutral"] = out
    return out


def defend_economic_building_warrior(ai: Any, hero: Any, view: Any) -> bool:
    """
    Warriors prioritize moving to defend nearby economic buildings (farm, food_stand) under attack.
    Runs only for warrior class; no randomness (always respond if in range).
    """
    view = as_ai_view(view)
    buildings = view.buildings
    enemies = view.enemies

    if not getattr(hero, "hero_class", "") == "warrior":
        return False

    # Don't interrupt explicit activities.
    if hero.target and isinstance(hero.target, dict):
        if hero.target.get("type") in ["going_home", "shopping"]:
            return False

    now_ms = int(sim_now_ms())
    if now_ms < int(getattr(hero, "_target_commit_until_ms", 0) or 0):
        cur = getattr(hero, "target", None)
        if cur is not None and hasattr(cur, "is_alive") and getattr(cur, "is_alive", False):
            return False

    visibility_radius = TILE_SIZE * 8
    candidate = None
    candidate_dist = float("inf")
    # Mythos S5: the type/hp/under-attack filter is hero-independent — iterate
    # the per-tick prefiltered list (same buildings, same order) and keep only
    # the per-hero distance check here. Result is identical to the full loop.
    for building in _attacked_economic_buildings(view):
        dist = hero.distance_to(building.center_x, building.center_y)
        if dist <= visibility_radius and dist < candidate_dist:
            candidate = building
            candidate_dist = dist

    if not candidate:
        return False

    target_enemy = None
    target_dist = float("inf")
    for enemy in enemies:
        if not getattr(enemy, "is_alive", False):
            continue
        dist = enemy.distance_to(candidate.center_x, candidate.center_y)
        if dist < TILE_SIZE * 6 and dist < target_dist:
            target_enemy = enemy
            target_dist = dist

    if target_enemy:
        dist_to_hero = hero.distance_to(target_enemy.x, target_enemy.y)
        if dist_to_hero <= hero.attack_range:
            engage(hero, target_enemy, now_ms, set_fighting=True, set_position=False)
            return True
        engage(hero, target_enemy, now_ms)
        hero.state = HeroState.MOVING
        return True

    hero.target = {"type": "defend_neutral", "building": candidate}
    hero.set_target_position(candidate.center_x + TILE_SIZE, candidate.center_y)
    hero.state = HeroState.MOVING
    return True


def defend_neutral_building_if_visible(ai: Any, hero: Any, view: Any) -> bool:
    """
    If a neutral building is under attack within the hero's "visible" radius,
    the hero may choose to defend it depending on class.
    """
    view = as_ai_view(view)
    buildings = view.buildings
    enemies = view.enemies

    # Don't interrupt explicit activities like shopping/going_home.
    if hero.target and isinstance(hero.target, dict):
        if hero.target.get("type") in ["going_home", "shopping"]:
            return False

    # WK2 anti-oscillation: if currently committed to a valid combat target, don't thrash.
    now_ms = int(sim_now_ms())
    if now_ms < int(getattr(hero, "_target_commit_until_ms", 0) or 0):
        cur = getattr(hero, "target", None)
        if cur is not None and hasattr(cur, "is_alive") and getattr(cur, "is_alive", False):
            return False

    visibility_radius = TILE_SIZE * 6
    # Class-based willingness to respond.
    cls = getattr(hero, "hero_class", "warrior")
    willingness = {
        "warrior": 1.0,
        "ranger": 0.85,
        "wizard": 0.75,
        "rogue": 0.55,
    }.get(cls, 0.8)

    # Find closest attacked neutral building within visibility.
    # Mythos S5: the neutral/hp/under-attack filter is hero-independent —
    # iterate the per-tick prefiltered list (same buildings, same order) and
    # keep only the per-hero distance check here. Identical result; the RNG
    # willingness draw below still happens only when a candidate is found.
    candidate = None
    candidate_dist = float("inf")
    for building in _attacked_neutral_buildings(view):
        dist = hero.distance_to(building.center_x, building.center_y)
        if dist <= visibility_radius and dist < candidate_dist:
            candidate = building
            candidate_dist = dist

    if not candidate:
        return False

    # Stochastic willingness (keeps behavior varied and class-flavored).
    if ai._ai_rng.random() > float(willingness):
        return False

    # Find nearest enemy near that building.
    target_enemy = None
    target_dist = float("inf")
    for enemy in enemies:
        if not getattr(enemy, "is_alive", False):
            continue
        dist = enemy.distance_to(candidate.center_x, candidate.center_y)
        if dist < TILE_SIZE * 6 and dist < target_dist:
            target_enemy = enemy
            target_dist = dist

    if target_enemy:
        dist_to_hero = hero.distance_to(target_enemy.x, target_enemy.y)
        if dist_to_hero <= hero.attack_range:
            engage(hero, target_enemy, now_ms, set_fighting=True, set_position=False)
            return True
        engage(hero, target_enemy, now_ms)
        hero.state = HeroState.MOVING
        return True

    # If we can't find an enemy, move to the building to "investigate/defend".
    hero.target = {"type": "defend_neutral", "building": candidate}
    hero.set_target_position(candidate.center_x + TILE_SIZE, candidate.center_y)
    hero.state = HeroState.MOVING
    return True


def start_retreat(ai: Any, hero: Any, view: Any) -> None:
    """Start retreating to safety."""
    view = as_ai_view(view)
    hero.state = HeroState.RETREATING
    buildings = view.buildings

    for building in buildings:
        if building.building_type in ["castle", "marketplace"]:
            hero.target_position = (building.center_x, building.center_y)
            break
