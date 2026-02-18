"""Post-shopping journey behavior extracted from ``BasicAI``."""

from __future__ import annotations

from typing import Any

from config import TILE_SIZE
from game.sim.timebase import now_ms as sim_now_ms
from game.systems.navigation import best_adjacent_tile


def _maybe_start_journey(
    ai: Any,
    hero: Any,
    game_state: dict,
    purchased_types: set[str] | None,
) -> bool:
    """Start a post-shopping journey if conditions are met."""
    if not purchased_types:
        return False
    if hero.hp < hero.max_hp:
        return False
    last_purchase_ms = getattr(hero, "last_purchase_ms", None)
    if last_purchase_ms is None:
        return False
    now_ms = int(sim_now_ms())
    if (now_ms - int(last_purchase_ms)) > int(ai.journey_trigger_window_ms):
        return False
    cooldown_until = int(getattr(hero, "_journey_cooldown_until_ms", 0) or 0)
    if now_ms < cooldown_until:
        return False

    hero_class = str(getattr(hero, "hero_class", "warrior") or "warrior")
    chance = 0.75
    if hero_class == "rogue":
        chance = 0.7
    elif hero_class == "warrior":
        chance = 0.8
    elif hero_class == "ranger":
        chance = 0.85
    if ai._ai_rng.random() > float(chance):
        return False

    started = False
    if hero_class == "warrior":
        # Prefer fighting: attack lair more often, else explore deeper fog.
        if ai._ai_rng.random() < 0.65:
            started = _start_journey_attack_lair(ai, hero, game_state)
        if not started:
            started = _start_journey_explore(
                ai,
                hero,
                game_state,
                min_tiles=10,
                max_tiles=30,
                prefer_far=True,
                scan_radius=30,
            )
    elif hero_class == "ranger":
        # Prefer exploration: farther fog target, fallback to lair if none found.
        started = _start_journey_explore(
            ai,
            hero,
            game_state,
            min_tiles=6,
            max_tiles=None,
            prefer_far=True,
            scan_radius=40,
        )
        if not started and ai._ai_rng.random() < 0.25:
            started = _start_journey_attack_lair(ai, hero, game_state)
    else:
        # Rogue: short, cautious fog step.
        started = _start_journey_explore(
            ai,
            hero,
            game_state,
            min_tiles=2,
            max_tiles=6,
            prefer_far=False,
            scan_radius=6,
        )

    if started:
        hero._journey_cooldown_until_ms = int(now_ms + int(ai.journey_cooldown_ms))
    return started


def _start_journey_explore(
    ai: Any,
    hero: Any,
    game_state: dict,
    *,
    min_tiles: float | None,
    max_tiles: float | None,
    prefer_far: bool,
    scan_radius: int,
) -> bool:
    world = game_state.get("world")
    if not world:
        return False
    candidates = ai.exploration_behavior._find_black_fog_frontier_tiles(
        world,
        hero,
        max_candidates=8,
        scan_radius=int(scan_radius),
        min_dist_tiles=min_tiles,
        max_dist_tiles=max_tiles,
    )
    if not candidates:
        return False

    # Weighted pick: farther for warriors/rangers, closer for rogues.
    weights = []
    for _, _, dist in candidates:
        if prefer_far:
            weights.append(max(0.1, float(dist)))
        else:
            weights.append(1.0 / (float(dist) + 0.1))
    total_weight = float(sum(weights))
    if total_weight <= 0:
        return False
    rand = ai._ai_rng.uniform(0, total_weight)
    cumsum = 0.0
    selected = None
    for i, weight in enumerate(weights):
        cumsum += weight
        if rand <= cumsum:
            selected = candidates[i]
            break
    if not selected:
        selected = candidates[0]
    gx, gy, _ = selected
    target_x = gx * TILE_SIZE + TILE_SIZE / 2
    target_y = gy * TILE_SIZE + TILE_SIZE / 2
    hero.set_target_position(target_x, target_y)
    hero.target = {"type": "journey_explore", "goal": "black_fog", "grid": (gx, gy)}
    ai.set_intent(hero, "idle")
    ai.record_decision(
        hero,
        action="journey_explore",
        reason="Post-shopping journey: explore fog",
        intent=getattr(hero, "intent", "idle") or "idle",
        inputs_summary={"trigger": "post_shopping", "goal": "black_fog"},
        source="system",
    )
    return True


def _start_journey_attack_lair(ai: Any, hero: Any, game_state: dict) -> bool:
    buildings = game_state.get("buildings", [])
    world = game_state.get("world")
    if not buildings:
        return False
    best = None
    best_d2 = None
    for building in buildings:
        if not getattr(building, "is_lair", False):
            continue
        if getattr(building, "hp", 0) <= 0:
            continue
        dx = float(getattr(building, "center_x", getattr(building, "x", 0.0))) - float(hero.x)
        dy = float(getattr(building, "center_y", getattr(building, "y", 0.0))) - float(hero.y)
        d2 = dx * dx + dy * dy
        if best is None or (best_d2 is not None and d2 < best_d2):
            best = building
            best_d2 = d2
    if best is None:
        return False

    goal_x = float(getattr(best, "center_x", getattr(best, "x", hero.x)))
    goal_y = float(getattr(best, "center_y", getattr(best, "y", hero.y)))
    if world:
        adj = best_adjacent_tile(world, buildings, best, hero.x, hero.y)
        if adj:
            goal_x = adj[0] * TILE_SIZE + TILE_SIZE / 2
            goal_y = adj[1] * TILE_SIZE + TILE_SIZE / 2
    hero.set_target_position(goal_x, goal_y)
    hero.target = best
    ai.set_intent(hero, "attacking_lair")
    ai.record_decision(
        hero,
        action="journey_attack_lair",
        reason="Post-shopping journey: attack lair",
        intent=getattr(hero, "intent", "idle") or "idle",
        inputs_summary={"trigger": "post_shopping", "goal": "attack_lair"},
        source="system",
    )
    return True
