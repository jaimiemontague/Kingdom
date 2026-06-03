"""Exploration and patrol behavior extracted from ``BasicAI``."""

from __future__ import annotations

import math
from typing import Any

from config import (
    RANGER_EXPLORE_BLACK_FOG_BIAS,
    RANGER_FRONTIER_COMMIT_MS,
    RANGER_FRONTIER_SCAN_RADIUS_TILES,
    RANGER_GLOBAL_FRONTIER_STRIDE_TILES,
    RANGER_REROAM_COMMIT_MS,
    TILE_SIZE,
)
from game.entities.buildings.types import BuildingType
from game.entities.hero import HeroState
from game.sim.hero_guardrails_tunables import TARGET_COMMIT_WINDOW_S
from game.sim.timebase import now_ms as sim_now_ms
from game.world import Visibility

from ai.behaviors.movement import route_to_building
from ai.behaviors.view_compat import as_ai_view

# WK84 Round D-4: patrol-zone assignment now lives in ``ai.behaviors.zones``
# (shared with movement/stuck_recovery via ``ai.exploration_behavior``). Re-import
# it here so explore()/handle_idle() and the ``ai.exploration_behavior.assign_patrol_zone``
# call-sites keep resolving against this module. zones.py imports no exploration
# symbol, so there is no import cycle.
from ai.behaviors.zones import assign_patrol_zone


def _is_live_enemy_target(target: Any) -> bool:
    """True only for living enemy entities (not buildings/lairs with ``is_alive``)."""
    if target is None or not hasattr(target, "is_alive"):
        return False
    if hasattr(target, "building_type"):
        return False
    return bool(getattr(target, "is_alive", False))


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


def _find_distant_frontier_tile(
    world: Any,
    hero: Any,
    rng: Any,
    *,
    stride: int = RANGER_GLOBAL_FRONTIER_STRIDE_TILES,
    max_candidates: int = 5,
) -> tuple[int, int] | None:
    """COARSE whole-map frontier scan for late-game ranger re-roam (WK124-T6).

    The local :func:`_find_black_fog_frontier_tiles` only scans a 10-tile bubble.
    Once the near-castle fog is fully revealed it returns ``[]`` and the ranger
    pins near base. This helper steps the WHOLE map by ``stride`` tiles looking
    for the nearest UNSEEN tile that is adjacent (within ``stride``) to a
    SEEN/VISIBLE tile — i.e. the edge of the explored region anywhere on the map.

    Returns the chosen ``(grid_x, grid_y)`` (with an RNG tie-break among the
    closest few candidates) or ``None`` when the reachable map appears fully
    revealed (no distant frontier found). Deterministic: uses only ``rng``
    (the AI RNG) — no ``random.*``/``time.*``.
    """
    if not world or not hasattr(world, "visibility"):
        return None

    stride = max(1, int(stride))
    width = int(world.width)
    height = int(world.height)
    visibility = world.visibility

    hero_gx = int(hero.x // TILE_SIZE)
    hero_gy = int(hero.y // TILE_SIZE)

    def _is_seen(gx: int, gy: int) -> bool:
        if gx < 0 or gx >= width or gy < 0 or gy >= height:
            return False
        v = visibility[gy][gx]
        return v == Visibility.SEEN or v == Visibility.VISIBLE

    candidates: list[tuple[int, int, int]] = []  # (dist_sq, gy, gx)
    # Coarse grid walk: step by ``stride`` so the whole 250x250 map is bounded.
    for gy in range(0, height, stride):
        for gx in range(0, width, stride):
            # Only UNSEEN sample points are frontier candidates.
            if visibility[gy][gx] != Visibility.UNSEEN:
                continue
            # Frontier = within ``stride`` of a SEEN/VISIBLE tile (4-neighbour
            # probe at the coarse step distance keeps this O(map/stride^2)).
            is_frontier = (
                _is_seen(gx - stride, gy)
                or _is_seen(gx + stride, gy)
                or _is_seen(gx, gy - stride)
                or _is_seen(gx, gy + stride)
            )
            if not is_frontier:
                continue
            dx = gx - hero_gx
            dy = gy - hero_gy
            dist_sq = dx * dx + dy * dy
            candidates.append((dist_sq, gy, gx))

    if not candidates:
        return None

    # Deterministic order: (dist_sq, gy, gx); RNG tie-break among the closest few.
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    pool = candidates[: max(1, int(max_candidates))]
    pick = pool[rng.randrange(len(pool))] if len(pool) > 1 else pool[0]
    _, gy, gx = pick
    return (gx, gy)


def _roam_toward_distant_objective(ai: Any, hero: Any, view: Any, now_ms: int) -> bool:
    """Productive roam when the whole reachable map is revealed (WK124-T6).

    No distant fog remains, so instead of oscillating near the castle the ranger
    heads toward the farthest known live lair (a meaningful destination far from
    base). Returns True and sets a patrol-style target on success; False when no
    such objective exists (caller then falls through to the existing wander).

    Deterministic: pure distance math, no RNG / wall-clock.
    """
    buildings = view.buildings or []

    best = None
    best_d2 = -1.0
    for building in buildings:
        if not getattr(building, "is_lair", False):
            continue
        if getattr(building, "hp", 0) <= 0:
            continue
        bx = float(getattr(building, "center_x", getattr(building, "x", 0.0)))
        by = float(getattr(building, "center_y", getattr(building, "y", 0.0)))
        dx = bx - float(hero.x)
        dy = by - float(hero.y)
        d2 = dx * dx + dy * dy
        # Farthest live lair (gives the longest productive travel); deterministic
        # tie-break on building position keeps the choice stable.
        key = (d2, bx, by)
        if best is None or key > best:
            best = key
            best_d2 = d2

    if best is None:
        return False

    # Don't churn if we're already essentially on top of it.
    if best_d2 <= (TILE_SIZE * 2) ** 2:
        return False

    _, goal_x, goal_y = best
    # Patrol-style roam target (a destination, NOT a combat lock): the ranger
    # travels toward the distant lair; normal combat/engage logic still applies
    # if it meets enemies en route.
    hero.set_target_position(goal_x, goal_y)
    hero.target = {"type": "explore_frontier"}
    hero._frontier_commit_until_ms = int(now_ms + RANGER_REROAM_COMMIT_MS)
    ai._debug_log(f"{hero.name} -> map revealed; roaming toward distant lair")
    return True


def explore(ai: Any, hero: Any, view: Any) -> None:
    """Send hero to explore within their zone. Rangers prefer black-fog frontiers."""
    view = as_ai_view(view)
    zone_x, zone_y = assign_patrol_zone(ai, hero, view)

    # WK6: Rangers have exploration bias toward black fog frontiers.
    if getattr(hero, "hero_class", None) == "ranger":
        world = view.world
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

            # WK124-T6: late-game re-roam. ONLY when the LOCAL frontier scan is
            # empty (the near-castle fog bubble is fully revealed) do a COARSE
            # whole-map scan for the nearest distant frontier and travel there.
            # DIGEST SAFETY: this fires only when ``frontier_candidates`` is empty,
            # which never happens in the 300-tick WK67 digest window, so the
            # digest stays byte-identical.
            if not frontier_candidates:
                distant = _find_distant_frontier_tile(world, hero, ai._ai_rng)
                if distant is not None:
                    gx, gy = distant
                    target_x = gx * TILE_SIZE + TILE_SIZE / 2
                    target_y = gy * TILE_SIZE + TILE_SIZE / 2
                    hero.set_target_position(target_x, target_y)
                    hero.target = {"type": "explore_frontier"}
                    # Longer commit so the ranger actually travels the distance
                    # instead of re-deciding every tick mid-journey.
                    hero._frontier_commit_until_ms = int(now_ms + RANGER_REROAM_COMMIT_MS)
                    ai._debug_log(
                        f"{hero.name} -> re-roaming to distant fog frontier at ({gx}, {gy})"
                    )
                    return
                # Whole reachable map appears revealed: productive roam toward a
                # known lair/distant waypoint rather than near-castle wander.
                if _roam_toward_distant_objective(ai, hero, view, now_ms):
                    return

    # Fallback: random wander (original behavior, or if no frontier found).
    angle = ai._ai_rng.uniform(0, 2 * math.pi)
    wander_dist = TILE_SIZE * ai._ai_rng.uniform(2, 5)
    target_x = zone_x + math.cos(angle) * wander_dist
    target_y = zone_y + math.sin(angle) * wander_dist
    hero.set_target_position(target_x, target_y)
    hero.target = {"type": "patrol"}


# ---------------------------------------------------------------------------
# WK85 Round D-5: ``handle_idle`` decomposed into ordered, named sub-steps.
#
# Each ``_idle_*(ai, hero, view) -> bool`` holds ONE of the original sequential
# decision branches VERBATIM and returns True iff the original ``handle_idle``
# would have returned/taken its action there (False = fall through to the next
# step). ``handle_idle`` is now a thin driver that runs them in the SAME order
# with the SAME short-circuit semantics. This is a behavior-preserving
# decomposition ONLY — same branches, same order, same effects. The WK67
# 300-tick AI-decision digest (``b73961…``) is the guard; it stays byte-identical.
#
# Shared-local note: the original computed ``view = as_ai_view(view)``,
# ``enemies``/``buildings`` and ``enemies_nearby`` once near the top and read them
# across branches. ``as_ai_view`` is idempotent (returns its arg if already an
# AiGameView), and the ``enemies_nearby`` scan is a pure, side-effect-free read
# (``is_alive``/``distance_to`` only), so each step recomputes exactly what it
# needs the same way the original did. None of the recomputations touch the RNG or
# sim-time stream, so the digest is preserved.
# ---------------------------------------------------------------------------


def _idle_clear_dangling_bounty(ai: Any, hero: Any, view: Any) -> bool:
    """Prelude: log IDLE + drop a stale ``bounty`` target. Always falls through."""
    ai._debug_log(f"{hero.name} is IDLE at ({hero.x:.0f}, {hero.y:.0f})", throttle_key=f"{hero.name}_idle")

    # If we were pursuing a bounty but ended up idle, clear it (avoid dangling targets).
    if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "bounty":
        hero.target = None
        hero.target_position = None
    return False


def _idle_take_bounty(ai: Any, hero: Any, view: Any) -> bool:
    """Majesty-style indirect control: bounties should be a primary lever."""
    if ai.bounty_behavior.maybe_take_bounty(ai, hero, view):
        return True
    return False


def _idle_seek_meal(ai: Any, hero: Any, view: Any) -> bool:
    """WK61-R10: hungry heroes seek food stands before discretionary explore/shopping."""
    hunger_behavior = getattr(ai, "hunger_behavior", None)
    if hunger_behavior is not None and hunger_behavior.maybe_seek_meal_idle(ai, hero, view):
        return True
    return False


def _idle_shopping(ai: Any, hero: Any, view: Any) -> bool:
    """Check if hero wants to go shopping (full health, has gold, needs potions)."""
    buildings = view.buildings
    if hero.hp >= hero.max_hp:
        # V1.3 extension: check marketplace first, then blacksmith.
        marketplace = ai.shopping_behavior.find_marketplace_with_potions(buildings)
        if marketplace and hero.wants_to_shop(marketplace.can_sell_potions()):
            ai._debug_log(f"{hero.name} -> going shopping")
            route_to_building(hero, view.world, buildings, marketplace)
            hero.state = HeroState.MOVING
            hero.target = {"type": "shopping", "marketplace": marketplace}
            return True

        if isinstance(hero, dict) or not hasattr(hero, "gold"):
            return True

        # WK15: Base shopping on available items
        blacksmith = ai.shopping_behavior.find_blacksmith(buildings, hero)
        if blacksmith and hero.gold >= 50:  # Assume upgrades cost at least 50 gold.
            ai._debug_log(f"{hero.name} -> going to Blacksmith for upgrades")
            route_to_building(hero, view.world, buildings, blacksmith)
            hero.state = HeroState.MOVING
            hero.target = {"type": "shopping", "blacksmith": blacksmith}
            return True
    return False


def _idle_engage_nearby_enemy(ai: Any, hero: Any, view: Any) -> bool:
    """Heroes only know about enemies within 5 tiles; if any, engage the closest."""
    enemies = view.enemies

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
            # WK61-R4-BUG-005: buildings now expose is_alive; only honor enemy commit windows.
            if _is_live_enemy_target(cur):
                return True
        enemies_nearby.sort(key=lambda x: x[1])
        target_enemy, target_dist = enemies_nearby[0]
        ai._debug_log(f"{hero.name} -> sees enemy {target_dist:.0f}px away, engaging!")
        hero.target = target_enemy
        hero._target_commit_until_ms = int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))
        hero.set_target_position(target_enemy.x, target_enemy.y)
        hero.state = HeroState.MOVING
        return True
    return False


def _idle_get_drink(ai: Any, hero: Any, view: Any) -> bool:
    """WK11: Get a drink at Inn (IDLE, full health, 10+ gold, ~10–15% chance per idle cycle)."""
    buildings = view.buildings

    # No enemies are nearby here — the engage step already short-circuited if any
    # were (so ``enemies_nearby`` is empty); recompute the same pure scan to keep
    # the original ``not enemies_nearby`` predicate byte-identical.
    awareness_radius = TILE_SIZE * 5
    enemies_nearby = []
    for enemy in view.enemies:
        if not enemy.is_alive:
            continue
        dist_to_hero = hero.distance_to(enemy.x, enemy.y)
        if dist_to_hero <= awareness_radius:
            enemies_nearby.append((enemy, dist_to_hero))

    if hero.hp >= hero.max_hp and hero.gold >= 10 and not enemies_nearby:
        inns = [
            b for b in buildings
            if getattr(b, "building_type", None) == BuildingType.INN and getattr(b, "is_constructed", True)
        ]
        if inns and ai._ai_rng.random() < 0.12:  # ~12% chance
            inn = min(inns, key=lambda b: hero.distance_to(b.center_x, b.center_y))
            route_to_building(hero, view.world, buildings, inn)
            hero.state = HeroState.MOVING
            hero.target = {"type": "get_drink", "inn": inn}
            return True
    return False


def _idle_visit_poi(ai: Any, hero: Any, view: Any) -> bool:
    """WK55: Personality-driven POI visit (chance-gated to avoid constant POI chasing)."""
    from ai.behaviors.poi_awareness import maybe_visit_poi
    if ai._ai_rng.random() < 0.08:  # ~8% per idle tick
        if maybe_visit_poi(ai, hero, view):
            ai._debug_log(f"{hero.name} -> visiting personality-matched POI")
            return True
    return False


def _idle_patrol_zone(ai: Any, hero: Any, view: Any) -> bool:
    """Terminal fall-through: patrol within / return to the hero's zone.

    This is the last step and never short-circuits the driver (it always returns
    False); it mirrors the original function's final no-``return`` block.
    """
    awareness_radius = TILE_SIZE * 5

    # Get this hero's patrol zone.
    zone_x, zone_y = assign_patrol_zone(ai, hero, view)

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
        # WK61-R4-BUG-005: keep heroes active in-zone (v1.5.6-style patrol/explore cadence).
        now_ms = sim_now_ms()
        frontier_commit_until = int(getattr(hero, "_frontier_commit_until_ms", 0) or 0)
        if getattr(hero, "hero_class", None) == "ranger":
            if now_ms >= frontier_commit_until or not hero.target_position:
                explore(ai, hero, view)
        elif not hero.target_position:
            explore(ai, hero, view)
        elif ai._ai_rng.random() < 0.15:
            explore(ai, hero, view)
    return False


# Ordered idle decision pipeline — SAME order as the original sequential
# ``handle_idle`` body. ``handle_idle`` runs these in order and returns on the
# first one that returns True (the original early-return points). The final
# ``_idle_patrol_zone`` is the terminal fall-through and always returns False.
_IDLE_STEPS = (
    _idle_clear_dangling_bounty,
    _idle_take_bounty,
    _idle_seek_meal,
    _idle_shopping,
    _idle_engage_nearby_enemy,
    _idle_get_drink,
    _idle_visit_poi,
    _idle_patrol_zone,
)


def handle_idle(ai: Any, hero: Any, view: Any) -> None:
    """Handle idle state - heroes patrol their assigned zone.

    Thin ordered driver over the ``_idle_*`` step functions: each is tried in
    order and the first to return True short-circuits (the original early
    returns). Behavior is identical to the pre-WK85 single-body version.
    """
    view = as_ai_view(view)
    for step in _IDLE_STEPS:
        if step(ai, hero, view):
            return
