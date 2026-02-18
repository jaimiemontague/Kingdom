"""Bounty pursuit behavior extracted from ``BasicAI``."""

from __future__ import annotations

import math
from typing import Any

from config import BOUNTY_BLACK_FOG_DISTANCE_PENALTY, TILE_SIZE
from game.entities.buildings.types import BuildingType
from game.entities.hero import HeroState
from game.sim.determinism import get_rng
from game.sim.hero_guardrails_tunables import BOUNTY_COMMIT_WINDOW_S
from game.sim.timebase import now_ms as sim_now_ms
from game.systems.navigation import best_adjacent_tile
from game.world import Visibility

from ai.behaviors.task_durations import roll_duration_seconds


def _resolve_bounty_from_target(target_dict: dict[str, Any], bounties: list[Any]) -> Any | None:
    """Find the bounty referenced by ``hero.target`` dict."""
    bid = target_dict.get("bounty_id")
    if bid is None:
        # Fallback: stored direct reference (best-effort)
        ref = target_dict.get("bounty_ref")
        if ref in bounties:
            return ref
        return None
    for bounty in bounties:
        if getattr(bounty, "bounty_id", None) == bid:
            return bounty
    return None


def maybe_take_bounty(ai: Any, hero: Any, game_state: dict) -> bool:
    """Pick and start pursuing a bounty if it makes sense."""
    bounties = game_state.get("bounties", [])
    if not bounties:
        return False

    # Avoid changing targets too often
    now_ms = sim_now_ms()

    # WK2 anti-oscillation: don't rapidly switch bounty objectives.
    if int(now_ms) < int(getattr(hero, "_bounty_commit_until_ms", 0) or 0):
        return False
    last_pick = int(getattr(hero, "_last_bounty_pick_ms", 0))
    if now_ms - last_pick < ai.bounty_pick_cooldown_ms:
        return False

    # Don't pursue bounties when hurt; survival + resting logic already handles healing.
    if hero.health_percent < 0.65:
        return False

    buildings = game_state.get("buildings", [])
    enemies = game_state.get("enemies", [])

    best = None
    best_score = -1e9
    for bounty in bounties:
        # Only consider bounties that are available (avoid dogpiling).
        if hasattr(bounty, "is_available_for") and not bounty.is_available_for(
            hero.name, now_ms, ai.bounty_assign_ttl_ms
        ):
            continue
        if hasattr(bounty, "is_valid") and not bounty.is_valid(buildings):
            continue

        world = game_state.get("world")
        score = score_bounty(ai, hero, bounty, buildings, enemies, world=world)
        if score > best_score:
            best_score = score
            best = bounty

    # Require some minimum attractiveness so heroes don't constantly wander to tiny bounties.
    if best is None or best_score < 0.15:
        hero._last_bounty_pick_ms = now_ms
        return False

    start_bounty_pursuit(ai, hero, best, game_state)
    hero._last_bounty_pick_ms = now_ms
    return True


def score_bounty(
    ai: Any,
    hero: Any,
    bounty: Any,
    buildings: list[Any],
    enemies: list[Any],
    world: Any = None,
) -> float:
    """Heuristic bounty scoring: reward vs distance vs risk, with class biases + noise."""
    try:
        goal_x, goal_y = (
            bounty.get_goal_position(buildings)
            if hasattr(bounty, "get_goal_position")
            else (bounty.x, bounty.y)
        )
        dist_tiles = max(0.1, float(hero.distance_to(goal_x, goal_y)) / float(TILE_SIZE))
    except Exception:
        dist_tiles = 10.0

    # WK6: Check if bounty is in black fog and apply distance penalty (uncertainty), but never exclude.
    is_black_fog = False
    if world and hasattr(world, "visibility"):
        try:
            # Get bounty grid coordinates
            bounty_gx = int(goal_x // TILE_SIZE)
            bounty_gy = int(goal_y // TILE_SIZE)
            if 0 <= bounty_gx < world.width and 0 <= bounty_gy < world.height:
                bounty_vis = world.visibility[bounty_gy][bounty_gx]
                is_black_fog = bounty_vis == Visibility.UNSEEN
        except Exception:
            # If we can't determine, assume not black fog (no penalty).
            pass

    reward = float(getattr(bounty, "reward", 0))
    risk = float(bounty.estimate_risk(enemies)) if hasattr(bounty, "estimate_risk") else 0.0

    # Class bias tuning (prototype).
    cls = getattr(hero, "hero_class", "warrior")
    reward_w = 1.0
    dist_w = 1.0
    risk_w = 1.0
    type_bonus = 0.0

    if cls == "rogue":
        reward_w = 1.45
        dist_w = 0.85
        risk_w = 1.05
    elif cls == "wizard":
        reward_w = 1.15
        dist_w = 1.05
        risk_w = 1.15
    elif cls == "ranger":
        reward_w = 1.05
        dist_w = 0.95
        risk_w = 1.0
    else:  # warrior and others
        reward_w = 1.0
        dist_w = 1.0
        risk_w = 1.0

    btype = getattr(bounty, "bounty_type", "explore")
    if cls == "rogue" and btype == "explore":
        type_bonus += 1.0
    if cls == "wizard" and btype == "defend_building":
        type_bonus += 0.4

    # WK6: Apply black fog distance penalty (uncertainty multiplier).
    effective_dist_tiles = dist_tiles * (
        BOUNTY_BLACK_FOG_DISTANCE_PENALTY if is_black_fog else 1.0
    )

    # Reward grows sublinearly; distance is a smooth penalty; risk subtracts.
    base = (reward_w * math.sqrt(max(0.0, reward)) + type_bonus) / (
        1.0 + dist_w * (effective_dist_tiles**1.1)
    )
    base -= risk_w * 0.35 * risk

    # Add a small per-hero randomness to reduce synchronized picks.
    base += ai._ai_rng.uniform(-0.15, 0.15)
    return base


def start_bounty_pursuit(ai: Any, hero: Any, bounty: Any, game_state: dict) -> None:
    """Set hero to pursue the bounty."""
    buildings = game_state.get("buildings", [])
    world = game_state.get("world")

    # Assign the bounty so others generally avoid it for a short while.
    if hasattr(bounty, "assign"):
        bounty.assign(hero.name)

    goal_x, goal_y = (float(getattr(bounty, "x", hero.x)), float(getattr(bounty, "y", hero.y)))
    if hasattr(bounty, "get_goal_position"):
        goal_x, goal_y = bounty.get_goal_position(buildings)

    # If the bounty targets a building, go to an adjacent tile so heroes don't try to stand inside it.
    target_building = None
    if getattr(bounty, "bounty_type", "") in ("attack_lair", "defend_building"):
        target_building = getattr(bounty, "target", None)

    if world and target_building is not None:
        adj = best_adjacent_tile(world, buildings, target_building, hero.x, hero.y)
        if adj:
            goal_x = adj[0] * TILE_SIZE + TILE_SIZE / 2
            goal_y = adj[1] * TILE_SIZE + TILE_SIZE / 2

    hero.target_position = (goal_x, goal_y)
    hero.target = {
        "type": "bounty",
        "bounty_id": getattr(bounty, "bounty_id", None),
        "bounty_type": getattr(bounty, "bounty_type", "explore"),
        # Keep a direct reference as fallback for headless tests.
        "bounty_ref": bounty,
        "started_ms": sim_now_ms(),
    }
    hero._bounty_commit_until_ms = int(sim_now_ms() + int(float(BOUNTY_COMMIT_WINDOW_S) * 1000.0))
    hero.state = HeroState.MOVING


def handle_moving(ai: Any, hero: Any, game_state: dict) -> None:
    """Handle moving-state behaviors including bounty claim/abandon and arrivals."""
    buildings = game_state.get("buildings", [])

    # Bounty pursuit: claim/abandon logic while walking.
    if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "bounty":
        bounty = _resolve_bounty_from_target(hero.target, game_state.get("bounties", []))
        if bounty is None:
            # Bounty vanished (claimed/cleaned up).
            hero.target = None
            hero.target_position = None
            hero.state = HeroState.IDLE
            return

        # Abandon invalid or already-claimed bounties.
        if getattr(bounty, "claimed", False) or (hasattr(bounty, "is_valid") and not bounty.is_valid(buildings)):
            if hasattr(bounty, "unassign") and getattr(bounty, "assigned_to", None) == hero.name:
                bounty.unassign()
            hero.target = None
            hero.target_position = None
            hero.state = HeroState.IDLE
            return

        # Timeout to avoid permanent lock.
        now_ms = sim_now_ms()
        started_ms = int(hero.target.get("started_ms", now_ms))
        if now_ms - started_ms > ai.bounty_max_pursue_ms:
            if hasattr(bounty, "unassign") and getattr(bounty, "assigned_to", None) == hero.name:
                bounty.unassign()
            hero.target = None
            hero.target_position = None
            hero.state = HeroState.IDLE
            return

        # Claim if we're close enough (works both in-game and in headless observer).
        goal_x, goal_y = (float(getattr(bounty, "x", hero.x)), float(getattr(bounty, "y", hero.y)))
        if hasattr(bounty, "get_goal_position"):
            goal_x, goal_y = bounty.get_goal_position(buildings)
        if hero.distance_to(goal_x, goal_y) <= float(ai.bounty_claim_radius_px):
            btype = str(getattr(bounty, "bounty_type", "explore") or "explore")

            # Typed bounties are not proximity-claimed.
            # For attack_lair: reaching the bounty transitions the hero to actually attack the lair.
            if btype == "attack_lair":
                lair = getattr(bounty, "target", None)
                if getattr(lair, "is_lair", False) and getattr(lair, "hp", 0) > 0:
                    hero.target = lair
                    world = game_state.get("world")
                    if world:
                        adj = best_adjacent_tile(world, buildings, lair, hero.x, hero.y)
                        if adj:
                            hero.target_position = (
                                adj[0] * TILE_SIZE + TILE_SIZE / 2,
                                adj[1] * TILE_SIZE + TILE_SIZE / 2,
                            )
                        else:
                            hero.target_position = (
                                float(getattr(lair, "center_x", goal_x)),
                                float(getattr(lair, "center_y", goal_y)),
                            )
                    else:
                        hero.target_position = (
                            float(getattr(lair, "center_x", goal_x)),
                            float(getattr(lair, "center_y", goal_y)),
                        )
                    hero.state = HeroState.MOVING
                    # Best-effort breadcrumb for debugging/UX (no hard dependency).
                    setattr(hero, "_active_attack_lair_bounty_id", getattr(bounty, "bounty_id", None))
                    return

            if btype == "explore":
                if hasattr(bounty, "claim"):
                    bounty.claim(hero)
                hero.target = None
                hero.target_position = None
                hero.state = HeroState.IDLE
                return
            # Other typed bounties: don't auto-claim here; let their systems resolve completion.

    # Check if reached destination.
    if hero.target_position:
        dist = hero.distance_to(hero.target_position[0], hero.target_position[1])
        if dist < TILE_SIZE // 2:
            # Check if we were going home.
            if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "going_home":
                hero.transfer_taxes_to_home()
                hero.start_resting()
                hero.target = None
                hero.target_position = None
                return

            # Check if we were going shopping (WK11: deferred — purchase on exit).
            if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "shopping":
                shop_building = hero.target.get("marketplace") or hero.target.get("blacksmith")
                if shop_building:
                    rng = get_rng("ai_basic")
                    duration_sec = roll_duration_seconds("shopping", rng)
                    setattr(hero, "pending_task", "shopping")
                    setattr(hero, "pending_task_building", shop_building)
                    hero.enter_building_briefly(shop_building, duration_sec=float(duration_sec))
                hero.target = None
                hero.target_position = None
                hero.state = HeroState.SHOPPING
                return

            # Rest at Inn (WK11): enter and heal inside; finalize on exit.
            if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "rest_inn":
                inn = hero.target.get("inn")
                if inn:
                    rng = get_rng("ai_basic")
                    duration_sec = roll_duration_seconds("rest_inn", rng)
                    setattr(hero, "pending_task", "rest_inn")
                    setattr(hero, "pending_task_building", inn)
                    hero.enter_building_briefly(inn, duration_sec=float(duration_sec))
                hero.target = None
                hero.target_position = None
                hero.state = HeroState.IDLE
                return

            # Get a drink at Inn (WK11): enter, pay on exit.
            if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "get_drink":
                inn = hero.target.get("inn")
                if inn:
                    rng = get_rng("ai_basic")
                    duration_sec = roll_duration_seconds("get_drink", rng)
                    setattr(hero, "pending_task", "get_drink")
                    setattr(hero, "pending_task_building", inn)
                    hero.enter_building_briefly(inn, duration_sec=float(duration_sec))
                hero.target = None
                hero.target_position = None
                hero.state = HeroState.IDLE
                return

            hero.target_position = None
            hero.state = HeroState.IDLE
            return

    # Only auto-engage if we're moving toward an enemy target (not patrolling/shopping/etc).
    if hero.target and isinstance(hero.target, dict):
        target_type = hero.target.get("type")
        # Don't interrupt these activities.
        if target_type in [
            "going_home",
            "shopping",
            "rest_inn",
            "get_drink",
            "patrol",
            "guard_home",
            "patrol_castle",
            "defend_castle",
        ]:
            return

    # If chasing an enemy, check if we've gone too far from our zone (8 tiles max).
    if hero.target and hasattr(hero.target, "is_alive"):
        zone_x, zone_y = ai.exploration_behavior.assign_patrol_zone(ai, hero, game_state)
        dist_to_zone = math.sqrt((hero.x - zone_x) ** 2 + (hero.y - zone_y) ** 2)
        max_chase_dist = TILE_SIZE * 8

        if dist_to_zone > max_chase_dist:
            ai._debug_log(f"{hero.name} -> too far from zone ({dist_to_zone:.0f}px), giving up chase")
            hero.target = None
            hero.target_position = None
            hero.state = HeroState.IDLE
            return

    # If we have an enemy target, check if we're in range to fight.
    if hero.target and hasattr(hero.target, "is_alive") and hero.target.is_alive:
        dist = hero.distance_to(hero.target.x, hero.target.y)
        if dist <= hero.attack_range:
            hero.state = HeroState.FIGHTING
            return
