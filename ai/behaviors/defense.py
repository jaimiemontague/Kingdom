"""Defense and retreat behavior extracted from ``BasicAI``."""

from __future__ import annotations

from typing import Any

from config import TILE_SIZE
from game.entities.hero import HeroState
from game.sim.hero_guardrails_tunables import TARGET_COMMIT_WINDOW_S
from game.sim.timebase import now_ms as sim_now_ms


def defend_castle(ai: Any, hero: Any, game_state: dict, castle: Any) -> None:
    """Send hero to defend the castle when it's damaged."""
    enemies = game_state.get("enemies", [])

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
            hero.target = target_enemy
            hero._target_commit_until_ms = int(
                now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0)
            )
            hero.state = HeroState.FIGHTING
            return
        hero.target = target_enemy
        hero._target_commit_until_ms = int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))
        hero.set_target_position(target_enemy.x, target_enemy.y)
        hero.state = HeroState.MOVING
        return

    dist_to_castle = hero.distance_to(castle.center_x, castle.center_y)
    if dist_to_castle > TILE_SIZE * 3:
        hero.target = {"type": "defend_castle"}
        hero.set_target_position(castle.center_x + TILE_SIZE, castle.center_y)
        hero.state = HeroState.MOVING
    else:
        hero.state = HeroState.IDLE


def defend_home_building(ai: Any, hero: Any, game_state: dict) -> None:
    """Hero defends their damaged home building."""
    enemies = game_state.get("enemies", [])

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
            hero.target = nearest_enemy
            hero._target_commit_until_ms = int(
                now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0)
            )
            hero.state = HeroState.FIGHTING
        else:
            hero.target = nearest_enemy
            hero._target_commit_until_ms = int(
                now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0)
            )
            hero.set_target_position(nearest_enemy.x, nearest_enemy.y)
    else:
        dist_to_home = hero.distance_to(building.center_x, building.center_y)
        if dist_to_home > TILE_SIZE * 2:
            hero.set_target_position(building.center_x + TILE_SIZE, building.center_y)
        else:
            hero.state = HeroState.IDLE


def defend_neutral_building_if_visible(ai: Any, hero: Any, game_state: dict) -> bool:
    """
    If a neutral building is under attack within the hero's "visible" radius,
    the hero may choose to defend it depending on class.
    """
    buildings = game_state.get("buildings", [])
    enemies = game_state.get("enemies", [])

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
    candidate = None
    candidate_dist = float("inf")
    for building in buildings:
        if not getattr(building, "is_neutral", False):
            continue
        if getattr(building, "hp", 0) <= 0:
            continue
        if not getattr(building, "is_under_attack", False):
            continue
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
            hero.target = target_enemy
            hero._target_commit_until_ms = int(
                now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0)
            )
            hero.state = HeroState.FIGHTING
            return True
        hero.target = target_enemy
        hero._target_commit_until_ms = int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))
        hero.set_target_position(target_enemy.x, target_enemy.y)
        hero.state = HeroState.MOVING
        return True

    # If we can't find an enemy, move to the building to "investigate/defend".
    hero.target = {"type": "defend_neutral", "building": candidate}
    hero.set_target_position(candidate.center_x + TILE_SIZE, candidate.center_y)
    hero.state = HeroState.MOVING
    return True


def start_retreat(ai: Any, hero: Any, game_state: dict) -> None:
    """Start retreating to safety."""
    hero.state = HeroState.RETREATING
    buildings = game_state.get("buildings", [])

    for building in buildings:
        if building.building_type in ["castle", "marketplace"]:
            hero.target_position = (building.center_x, building.center_y)
            break
