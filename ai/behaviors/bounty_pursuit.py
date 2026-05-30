"""Bounty pursuit behavior extracted from ``BasicAI``."""

from __future__ import annotations

import math
from typing import Any

from config import BOUNTY_BLACK_FOG_DISTANCE_PENALTY, TILE_SIZE
from game.entities.hero import HeroState
from game.sim.direct_prompt_commit import DIRECT_PROMPT_TARGET_TYPE
from game.sim.hero_guardrails_tunables import BOUNTY_COMMIT_WINDOW_S
from game.sim.timebase import now_ms as sim_now_ms
from game.systems.navigation import best_adjacent_tile
from game.world import Visibility

from ai.behaviors.view_compat import as_ai_view

# WK64 (audit item 17): the reached-destination arrival dispatch (and its private
# helpers _clear_direct_prompt_explore_meta / _compass_from_vec /
# _pick_building_at_arrival / _find_safety_building_for_arrival, plus the
# explore-extension constants) moved to ai/arrival_handlers.py. Import direction
# is one-way: this module imports dispatch_arrival from there, never the reverse.


def _seed_direct_prompt_explore_bearing(hero: Any) -> None:
    target = getattr(hero, "target", None)
    if not isinstance(target, dict) or target.get("type") != DIRECT_PROMPT_TARGET_TYPE:
        return
    if str(target.get("sub_intent") or "") != "explore_direction":
        return
    tp = getattr(hero, "target_position", None)
    if not tp or getattr(hero, "_dp_explore_bearing_ready", False):
        return
    dx = float(tp[0]) - float(hero.x)
    dy = float(tp[1]) - float(hero.y)
    if dx * dx + dy * dy > (TILE_SIZE * 0.2) ** 2:
        hero._dp_explore_leg_vec = (dx, dy)
        hero._dp_explore_bearing_ready = True


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


def maybe_take_bounty(ai: Any, hero: Any, view: Any) -> bool:
    """Pick and start pursuing a bounty if it makes sense."""
    view = as_ai_view(view)
    bounties = view.bounties
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

    buildings = view.buildings
    enemies = view.enemies

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

        world = view.world
        score = score_bounty(ai, hero, bounty, buildings, enemies, world=world)
        if score > best_score:
            best_score = score
            best = bounty

    # Require some minimum attractiveness so heroes don't constantly wander to tiny bounties.
    if best is None or best_score < 0.15:
        hero._last_bounty_pick_ms = now_ms
        return False

    start_bounty_pursuit(ai, hero, best, view)
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


def start_bounty_pursuit(ai: Any, hero: Any, bounty: Any, view: Any) -> None:
    """Set hero to pursue the bounty."""
    view = as_ai_view(view)
    buildings = view.buildings
    world = view.world

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


def handle_moving(ai, hero, view):
    # WK83 Round D-3: the global MOVING-state dispatcher moved VERBATIM to
    # ai/behaviors/movement.py (it routes bounty/arrival/chase/fight, not just
    # bounty code). This 1-line shim keeps basic_ai's
    # self.bounty_behavior.handle_moving(self, hero, view) caller unchanged.
    # Import is lazy to avoid a module-load cycle (movement.handle_moving lazily
    # imports this module's bounty helpers in turn).
    from ai.behaviors import movement

    return movement.handle_moving(ai, hero, view)
