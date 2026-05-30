"""Shared hero movement-routing helpers extracted from ``BasicAI`` behaviors.

WK74 Round C-2b: the "route hero to a building" block (best_adjacent_tile ->
set target_position to the adjacent-tile center, else the building center) was
copy-pasted across exploration/shopping/hunger/basic_ai. ``route_to_building``
is the single canonical implementation (verbatim from the marketplace block in
``exploration.handle_idle``); every byte-identical site calls it instead.

WK83 Round D-3: the global MOVING-state dispatcher ``handle_moving`` (the
per-frame router that drives bounty claim/abandon, arrival dispatch, chase
zone-limiting, and enter-FIGHTING) moved here VERBATIM from
``ai/behaviors/bounty_pursuit.py``. It is not bounty code -- it is the
MOVING-state behavior that the 300-tick AI-decision digest hashes.
``bounty_pursuit.handle_moving`` is now a 1-line delegating shim so
``basic_ai``'s ``self.bounty_behavior.handle_moving(self, hero, view)`` caller is
unchanged. The two bounty_pursuit helpers it calls
(``_seed_direct_prompt_explore_bearing`` / ``_resolve_bounty_from_target``) are
imported LAZILY inside the function (``from ai.behaviors import bounty_pursuit``)
to avoid a module-load cycle (the shim imports movement lazily too).
"""

from __future__ import annotations

import math
from typing import Any

from config import TILE_SIZE
from game.entities.hero import HeroState
from game.sim.timebase import now_ms as sim_now_ms
from game.systems.navigation import best_adjacent_tile

from ai.behaviors.view_compat import as_ai_view


def route_to_building(hero: Any, world: Any, buildings: Any, building: Any) -> None:
    """Point ``hero.target_position`` at the best reachable tile beside ``building``.

    Reproduces the canonical "route hero to a building" block byte-for-byte:
    prefer the center of the nearest reachable adjacent tile, falling back to the
    building center when no adjacent tile is available (or ``world`` is missing).
    Does NOT set ``hero.state`` or ``hero.target`` -- callers keep that.
    """
    if world:
        adj = best_adjacent_tile(world, buildings, building, hero.x, hero.y)
        if adj:
            hero.target_position = (
                adj[0] * TILE_SIZE + TILE_SIZE / 2,
                adj[1] * TILE_SIZE + TILE_SIZE / 2,
            )
        else:
            hero.target_position = (building.center_x, building.center_y)
    else:
        hero.target_position = (building.center_x, building.center_y)


def handle_moving(ai: Any, hero: Any, view: Any) -> None:
    """Handle moving-state behaviors including bounty claim/abandon and arrivals."""
    # WK83 Round D-3: lazy import to avoid a module-load cycle. ``bounty_pursuit``
    # keeps the bounty scoring/pursuit helpers this dispatcher calls; its
    # ``handle_moving`` shim imports this module lazily in turn.
    from ai.behaviors import bounty_pursuit

    view = as_ai_view(view)
    buildings = view.buildings
    bounty_pursuit._seed_direct_prompt_explore_bearing(hero)

    # Bounty pursuit: claim/abandon logic while walking.
    if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "bounty":
        bounty = bounty_pursuit._resolve_bounty_from_target(hero.target, view.bounties)
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
                    world = view.world
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
        if dist <= TILE_SIZE * 1.5:
            # WK64 (audit item 17): the reached-destination arrival dispatch was
            # extracted to ai/arrival_handlers.py (a TargetType-keyed registry).
            # dispatch_arrival consumes hero.target via coerce_task; it returns
            # True when a handler fully handled the arrival, and False for
            # bounty/live-entity/None targets so we fall through to the default
            # "arrived -> go IDLE" branch below (identical to pre-extraction).
            from ai.arrival_handlers import dispatch_arrival

            if dispatch_arrival(ai, hero, view):
                return
            # Default: arrived with no special handler -> go idle.
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
            "direct_prompt",
            "bounty",
            "visit_poi",  # WK55: personality-driven POI visit
            "buy_meal",  # WK61-R10: hunger meal at food stand
        ]:
            return

    # If chasing an enemy, check if we've gone too far from our zone (8 tiles max).
    # WK61-FIX: exclude lair/building targets — only zone-limit enemy chases.
    # Buildings now have is_alive (WK61-BUG-003), so hasattr alone is too broad.
    if hero.target and hasattr(hero.target, "is_alive") and not getattr(hero.target, "is_lair", False) and not hasattr(hero.target, "building_type"):
        zone_x, zone_y = ai.exploration_behavior.assign_patrol_zone(ai, hero, view)
        dist_to_zone = math.sqrt((hero.x - zone_x) ** 2 + (hero.y - zone_y) ** 2)
        max_chase_dist = TILE_SIZE * 8

        if dist_to_zone > max_chase_dist:
            ai._debug_log(f"{hero.name} -> too far from zone ({dist_to_zone:.0f}px), giving up chase")
            hero.target = None
            hero.target_position = None
            hero.state = HeroState.IDLE
            return

    # If we have an enemy target, check if we're in range to fight.
    # WK61-FIX: also enter FIGHTING for lair targets (is_lair) so heroes attack lairs.
    if hero.target and hasattr(hero.target, "is_alive") and hero.target.is_alive and (not hasattr(hero.target, "building_type") or getattr(hero.target, "is_lair", False)):
        dist = hero.distance_to(hero.target.x, hero.target.y)
        if dist <= hero.attack_range:
            hero.state = HeroState.FIGHTING
            return
