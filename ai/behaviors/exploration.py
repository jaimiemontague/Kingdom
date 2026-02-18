"""Exploration and patrol behavior extracted from ``BasicAI``."""

from __future__ import annotations

import math
from typing import Any

from config import (
    RANGER_EXPLORE_BLACK_FOG_BIAS,
    RANGER_FRONTIER_COMMIT_MS,
    RANGER_FRONTIER_SCAN_RADIUS_TILES,
    TILE_SIZE,
)
from game.entities.buildings.types import BuildingType
from game.entities.hero import HeroState
from game.sim.hero_guardrails_tunables import TARGET_COMMIT_WINDOW_S
from game.sim.timebase import now_ms as sim_now_ms
from game.systems.navigation import best_adjacent_tile
from game.world import Visibility


def assign_patrol_zone(ai: Any, hero: Any, game_state: dict) -> tuple[float, float]:
    """Assign a unique patrol zone to a hero based on their index."""
    if hero.name in ai.hero_zones:
        return ai.hero_zones[hero.name]

    # Get castle position as reference.
    castle = game_state.get("castle")
    if castle:
        base_x, base_y = castle.center_x, castle.center_y
    else:
        from config import MAP_HEIGHT, MAP_WIDTH

        base_x = (MAP_WIDTH // 2) * TILE_SIZE
        base_y = (MAP_HEIGHT // 2) * TILE_SIZE

    # Assign zones in a circle around the castle.
    heroes = [h for h in game_state.get("heroes", []) if h.is_alive]
    try:
        idx = heroes.index(hero)
    except ValueError:
        idx = len(ai.hero_zones)

    num_heroes = max(len(heroes), 1)
    angle = (2 * math.pi * idx) / num_heroes + ai._ai_rng.uniform(-0.2, 0.2)
    radius = TILE_SIZE * ai._ai_rng.uniform(6, 10)  # Spread zones further out.

    zone_x = base_x + math.cos(angle) * radius
    zone_y = base_y + math.sin(angle) * radius

    ai.hero_zones[hero.name] = (zone_x, zone_y)
    ai._debug_log(
        f"{hero.name} assigned zone at ({zone_x:.0f}, {zone_y:.0f}), angle={math.degrees(angle):.0f}deg"
    )
    return (zone_x, zone_y)


def _find_black_fog_frontier_tiles(
    world: Any,
    hero: Any,
    max_candidates: int = 5,
    scan_radius: int | None = None,
    min_dist_tiles: float | None = None,
    max_dist_tiles: float | None = None,
) -> list[tuple[int, int, float]]:
    """
    Find UNSEEN tiles adjacent to SEEN/VISIBLE tiles (black-fog frontier).

    Returns ``(grid_x, grid_y, distance_tiles)`` tuples sorted by distance, then coords.
    """
    if not world or not hasattr(world, "visibility"):
        return []

    hero_gx = int(hero.x // TILE_SIZE)
    hero_gy = int(hero.y // TILE_SIZE)
    if scan_radius is None:
        scan_radius = RANGER_FRONTIER_SCAN_RADIUS_TILES

    candidates = []
    # Scan a square region around hero (bounded for perf).
    for dy in range(-scan_radius, scan_radius + 1):
        for dx in range(-scan_radius, scan_radius + 1):
            gx = hero_gx + dx
            gy = hero_gy + dy

            # Bounds check.
            if gx < 0 or gx >= world.width or gy < 0 or gy >= world.height:
                continue

            # Check if this tile is UNSEEN (black fog).
            if world.visibility[gy][gx] != Visibility.UNSEEN:
                continue

            # Check if it's adjacent to SEEN or VISIBLE (frontier).
            is_frontier = False
            for adj_dy in [-1, 0, 1]:
                for adj_dx in [-1, 0, 1]:
                    if adj_dx == 0 and adj_dy == 0:
                        continue
                    adj_gx = gx + adj_dx
                    adj_gy = gy + adj_dy
                    if 0 <= adj_gx < world.width and 0 <= adj_gy < world.height:
                        adj_vis = world.visibility[adj_gy][adj_gx]
                        if adj_vis == Visibility.SEEN or adj_vis == Visibility.VISIBLE:
                            is_frontier = True
                            break
                if is_frontier:
                    break

            if is_frontier:
                # Calculate distance (squared for comparison, avoid sqrt until needed).
                dist_sq = dx * dx + dy * dy
                dist_tiles = math.sqrt(dist_sq)
                if min_dist_tiles is not None and dist_tiles < float(min_dist_tiles):
                    continue
                if max_dist_tiles is not None and dist_tiles > float(max_dist_tiles):
                    continue
                candidates.append((gx, gy, dist_tiles))

    # Stable sort: by distance (closest first), then by grid coords (deterministic tie-break).
    candidates.sort(key=lambda c: (c[2], c[1], c[0]))

    # Return top N candidates.
    return candidates[:max_candidates]


def explore(ai: Any, hero: Any, game_state: dict) -> None:
    """Send hero to explore within their zone. Rangers prefer black-fog frontiers."""
    zone_x, zone_y = assign_patrol_zone(ai, hero, game_state)

    # WK6: Rangers have exploration bias toward black fog frontiers.
    if getattr(hero, "hero_class", None) == "ranger":
        world = game_state.get("world")
        if world:
            # Check commitment window (prevent rapid re-targeting).
            now_ms = sim_now_ms()
            frontier_commit_until = int(getattr(hero, "_frontier_commit_until_ms", 0) or 0)
            if now_ms < frontier_commit_until:
                # Still committed to current exploration target, continue.
                if hero.target_position:
                    return

            # Try to find frontier tiles.
            frontier_candidates = _find_black_fog_frontier_tiles(world, hero, max_candidates=5)

            if frontier_candidates and ai._ai_rng.random() < RANGER_EXPLORE_BLACK_FOG_BIAS:
                # Pick a frontier tile (weighted by distance: closer = higher weight).
                weights = [1.0 / (c[2] + 0.1) for c in frontier_candidates]
                total_weight = sum(weights)
                if total_weight > 0:
                    rand = ai._ai_rng.uniform(0, total_weight)
                    cumsum = 0.0
                    selected = None
                    for i, weight in enumerate(weights):
                        cumsum += weight
                        if rand <= cumsum:
                            selected = frontier_candidates[i]
                            break

                    if selected:
                        gx, gy, _ = selected
                        # Convert grid coords to world coords (center of tile).
                        target_x = gx * TILE_SIZE + TILE_SIZE / 2
                        target_y = gy * TILE_SIZE + TILE_SIZE / 2
                        hero.set_target_position(target_x, target_y)
                        hero.target = {"type": "explore_frontier"}
                        # Set commitment window.
                        hero._frontier_commit_until_ms = int(now_ms + RANGER_FRONTIER_COMMIT_MS)
                        ai._debug_log(f"{hero.name} -> exploring black fog frontier at ({gx}, {gy})")
                        return

    # Fallback: random wander (original behavior, or if no frontier found).
    angle = ai._ai_rng.uniform(0, 2 * math.pi)
    wander_dist = TILE_SIZE * ai._ai_rng.uniform(2, 5)
    target_x = zone_x + math.cos(angle) * wander_dist
    target_y = zone_y + math.sin(angle) * wander_dist
    hero.set_target_position(target_x, target_y)
    hero.target = {"type": "patrol"}


def handle_idle(ai: Any, hero: Any, game_state: dict) -> None:
    """Handle idle state - heroes patrol their assigned zone."""
    enemies = game_state.get("enemies", [])
    buildings = game_state.get("buildings", [])

    ai._debug_log(f"{hero.name} is IDLE at ({hero.x:.0f}, {hero.y:.0f})", throttle_key=f"{hero.name}_idle")

    # If we were pursuing a bounty but ended up idle, clear it (avoid dangling targets).
    if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "bounty":
        hero.target = None
        hero.target_position = None

    # Majesty-style indirect control: bounties should be a primary lever.
    if ai.bounty_behavior.maybe_take_bounty(ai, hero, game_state):
        return

    # Check if hero wants to go shopping (full health, has gold, needs potions).
    if hero.hp >= hero.max_hp:
        # V1.3 extension: check marketplace first, then blacksmith.
        marketplace = ai.shopping_behavior.find_marketplace_with_potions(buildings)
        if marketplace and hero.wants_to_shop(marketplace.can_sell_potions()):
            ai._debug_log(f"{hero.name} -> going shopping")
            world = game_state.get("world")
            if world:
                adj = best_adjacent_tile(world, buildings, marketplace, hero.x, hero.y)
                if adj:
                    hero.target_position = (
                        adj[0] * TILE_SIZE + TILE_SIZE / 2,
                        adj[1] * TILE_SIZE + TILE_SIZE / 2,
                    )
                else:
                    hero.target_position = (marketplace.center_x, marketplace.center_y)
            else:
                hero.target_position = (marketplace.center_x, marketplace.center_y)
            hero.state = HeroState.MOVING
            hero.target = {"type": "shopping", "marketplace": marketplace}
            return

        blacksmith = ai.shopping_behavior.find_blacksmith_with_upgrades(buildings, hero)
        if blacksmith and hero.gold >= 50:  # Assume upgrades cost at least 50 gold.
            ai._debug_log(f"{hero.name} -> going to Blacksmith for upgrades")
            world = game_state.get("world")
            if world:
                adj = best_adjacent_tile(world, buildings, blacksmith, hero.x, hero.y)
                if adj:
                    hero.target_position = (
                        adj[0] * TILE_SIZE + TILE_SIZE / 2,
                        adj[1] * TILE_SIZE + TILE_SIZE / 2,
                    )
                else:
                    hero.target_position = (blacksmith.center_x, blacksmith.center_y)
            else:
                hero.target_position = (blacksmith.center_x, blacksmith.center_y)
            hero.state = HeroState.MOVING
            hero.target = {"type": "shopping", "blacksmith": blacksmith}
            return

    # Heroes only know about enemies within 5 tiles of themselves (no map-wide awareness).
    awareness_radius = TILE_SIZE * 5

    enemies_nearby = []
    for enemy in enemies:
        if not enemy.is_alive:
            continue

        dist_to_hero = hero.distance_to(enemy.x, enemy.y)
        if dist_to_hero <= awareness_radius:
            enemies_nearby.append((enemy, dist_to_hero))

    # If there are enemies nearby, engage the closest one.
    if enemies_nearby:
        # WK2 anti-oscillation: respect commitment window unless current target is invalid.
        now_ms = int(sim_now_ms())
        if now_ms < int(getattr(hero, "_target_commit_until_ms", 0) or 0):
            cur = getattr(hero, "target", None)
            if cur is not None and hasattr(cur, "is_alive") and getattr(cur, "is_alive", False):
                return
        enemies_nearby.sort(key=lambda x: x[1])
        target_enemy, target_dist = enemies_nearby[0]
        ai._debug_log(f"{hero.name} -> sees enemy {target_dist:.0f}px away, engaging!")
        hero.target = target_enemy
        hero._target_commit_until_ms = int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))
        hero.set_target_position(target_enemy.x, target_enemy.y)
        hero.state = HeroState.MOVING
        return

    # WK11: Get a drink at Inn (IDLE, full health, 10+ gold, ~10–15% chance per idle cycle).
    if hero.hp >= hero.max_hp and hero.gold >= 10 and not enemies_nearby:
        inns = [
            b for b in buildings
            if getattr(b, "building_type", None) == BuildingType.INN and getattr(b, "is_constructed", True)
        ]
        if inns and ai._ai_rng.random() < 0.12:  # ~12% chance
            inn = min(inns, key=lambda b: hero.distance_to(b.center_x, b.center_y))
            world = game_state.get("world")
            if world:
                adj = best_adjacent_tile(world, buildings, inn, hero.x, hero.y)
                if adj:
                    hero.target_position = (
                        adj[0] * TILE_SIZE + TILE_SIZE / 2,
                        adj[1] * TILE_SIZE + TILE_SIZE / 2,
                    )
                else:
                    hero.target_position = (inn.center_x, inn.center_y)
            else:
                hero.target_position = (inn.center_x, inn.center_y)
            hero.state = HeroState.MOVING
            hero.target = {"type": "get_drink", "inn": inn}
            return

    # Get this hero's patrol zone.
    zone_x, zone_y = assign_patrol_zone(ai, hero, game_state)

    ai._debug_log(
        f"{hero.name} zone=({zone_x:.0f}, {zone_y:.0f}), hero at ({hero.x:.0f}, {hero.y:.0f})",
        throttle_key=f"{hero.name}_zone",
    )

    ai._debug_log(
        f"{hero.name} -> no enemies within {awareness_radius}px",
        throttle_key=f"{hero.name}_no_enemy",
    )

    # No enemies in zone - patrol within our zone.
    dist_to_zone = hero.distance_to(zone_x, zone_y)
    ai._debug_log(f"{hero.name} dist_to_zone={dist_to_zone:.0f}")

    if dist_to_zone > TILE_SIZE * 4:
        # Too far from zone, return to it.
        ai._debug_log(f"{hero.name} -> returning to zone")
        hero.target_position = (zone_x, zone_y)
        hero.state = HeroState.MOVING
        hero.target = {"type": "patrol"}
    else:
        # WK6: rangers use exploration module which has black-fog frontier bias.
        if getattr(hero, "hero_class", None) == "ranger":
            # Check commitment window (prevent rapid re-targeting).
            now_ms = sim_now_ms()
            frontier_commit_until = int(getattr(hero, "_frontier_commit_until_ms", 0) or 0)
            if now_ms >= frontier_commit_until or not hero.target_position:
                explore(ai, hero, game_state)
        else:
            # Non-rangers: random wander (original behavior).
            if ai._ai_rng.random() < 0.02:  # 2% chance per frame
                angle = ai._ai_rng.uniform(0, 2 * math.pi)
                wander_dist = TILE_SIZE * ai._ai_rng.uniform(1, 3)
                target_x = zone_x + math.cos(angle) * wander_dist
                target_y = zone_y + math.sin(angle) * wander_dist
                ai._debug_log(f"{hero.name} -> wandering to ({target_x:.0f}, {target_y:.0f})")
                hero.target_position = (target_x, target_y)
                hero.state = HeroState.MOVING
                hero.target = {"type": "patrol"}
