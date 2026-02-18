"""Stuck detection and recovery extracted from ``BasicAI``."""

from __future__ import annotations

from typing import Any

from config import TILE_SIZE
from game.entities.hero import HeroState
from game.sim.hero_guardrails_tunables import (
    STUCK_DISPLACEMENT_TILES_THRESHOLD,
    STUCK_TIME_S,
    UNSTUCK_BACKOFF_S,
    UNSTUCK_MAX_ATTEMPTS_PER_TARGET,
)
from game.sim.timebase import now_ms as sim_now_ms


def _stuck_target_key(hero: Any) -> tuple[Any, ...]:
    target = getattr(hero, "target", None)
    if isinstance(target, dict) and target.get("type") == "bounty":
        return ("bounty", target.get("bounty_id"), target.get("bounty_type"))
    if isinstance(target, dict):
        return ("dict", target.get("type"))
    if target is None:
        return ("none",)
    return ("obj", target.__class__.__name__)


def _update_stuck_and_recover(ai: Any, hero: Any, game_state: dict) -> None:
    """
    Detect "intends to move but no progress" using sim-time and apply deterministic recovery steps.

    Locked thresholds (from PM hub wk2_r1):
    - displacement < STUCK_DISPLACEMENT_TILES_THRESHOLD tiles
    - time >= STUCK_TIME_S
    - max attempts per target = UNSTUCK_MAX_ATTEMPTS_PER_TARGET
    - backoff = UNSTUCK_BACKOFF_S
    """
    # Ignore while inside buildings; movement is intentionally paused.
    # Clear stuck state so we don't report "stuck" while a hero is intentionally hidden/paused.
    if bool(getattr(hero, "is_inside_building", False)):
        if bool(getattr(hero, "stuck_active", False)):
            hero.stuck_active = False
            hero.stuck_since_ms = None
            hero.stuck_reason = ""
        return

    state = getattr(hero, "state", None)
    if state not in (HeroState.MOVING, HeroState.RETREATING):
        # Not intending to move => not stuck.
        if bool(getattr(hero, "stuck_active", False)):
            hero.stuck_active = False
            hero.stuck_since_ms = None
            hero.stuck_reason = ""
        return
    if not getattr(hero, "target_position", None):
        return

    now_ms = int(sim_now_ms())

    # Initialize progress fields if missing.
    if not hasattr(hero, "last_progress_ms"):
        hero.last_progress_ms = now_ms
    if not hasattr(hero, "last_progress_pos"):
        hero.last_progress_pos = (float(getattr(hero, "x", 0.0)), float(getattr(hero, "y", 0.0)))

    last_px, last_py = getattr(hero, "last_progress_pos", (float(hero.x), float(hero.y)))
    dx = float(hero.x) - float(last_px)
    dy = float(hero.y) - float(last_py)
    dist_px = (dx * dx + dy * dy) ** 0.5

    displacement_thresh_px = float(TILE_SIZE) * float(STUCK_DISPLACEMENT_TILES_THRESHOLD)
    if dist_px >= displacement_thresh_px:
        hero.last_progress_ms = now_ms
        hero.last_progress_pos = (float(hero.x), float(hero.y))
        hero.stuck_active = False
        hero.stuck_since_ms = None
        hero.stuck_reason = ""
        hero._unstuck_attempts_for_target = 0
        hero._unstuck_target_key = None
        return

    if now_ms - int(getattr(hero, "last_progress_ms", now_ms)) < int(float(STUCK_TIME_S) * 1000.0):
        return

    # Mark stuck (contract fields).
    if not bool(getattr(hero, "stuck_active", False)):
        hero.stuck_active = True
        hero.stuck_since_ms = int(getattr(hero, "last_progress_ms", now_ms))
        hero.stuck_reason = "no_progress"

    # Backoff between attempts.
    last_attempt_ms = int(getattr(hero, "_last_unstuck_attempt_ms", 0) or 0)
    if now_ms - last_attempt_ms < int(float(UNSTUCK_BACKOFF_S) * 1000.0):
        return

    key = _stuck_target_key(hero)
    if getattr(hero, "_unstuck_target_key", None) != key:
        hero._unstuck_target_key = key
        hero._unstuck_attempts_for_target = 0

    attempt_idx = int(getattr(hero, "_unstuck_attempts_for_target", 0) or 0)
    if attempt_idx >= int(UNSTUCK_MAX_ATTEMPTS_PER_TARGET):
        # Fallback: drop target and return to idle patrol.
        hero.stuck_reason = "fallback_idle"
        hero.target = None
        hero.target_position = None
        hero.path = []
        hero._path_goal = None
        hero.state = HeroState.IDLE
        hero.stuck_active = False
        hero.stuck_since_ms = None
        return

    world = game_state.get("world")
    buildings = game_state.get("buildings", [])

    if attempt_idx == 0:
        # Step 1: force replanning.
        hero.stuck_reason = "repath"
        hero.path = []
        hero._path_goal = None
    elif attempt_idx == 1:
        # Step 2: nudge to an adjacent walkable tile (deterministic order).
        hero.stuck_reason = "nudge_adjacent"
        if world:
            gx, gy = world.world_to_grid(hero.x, hero.y)
            candidates = [(gx + 1, gy), (gx - 1, gy), (gx, gy + 1), (gx, gy - 1)]

            blocked = set()
            for building in buildings or []:
                if getattr(building, "hp", 1) <= 0:
                    continue
                if (
                    getattr(building, "building_type", "") != "castle"
                    and getattr(building, "is_constructed", True) is False
                ):
                    continue
                bgx = getattr(building, "grid_x", None)
                bgy = getattr(building, "grid_y", None)
                size = getattr(building, "size", None)
                if bgx is None or bgy is None or not size:
                    continue
                for dx0 in range(size[0]):
                    for dy0 in range(size[1]):
                        blocked.add((bgx + dx0, bgy + dy0))

            for cx, cy in candidates:
                if (cx, cy) in blocked:
                    continue
                if not world.is_walkable(cx, cy):
                    continue
                hero.target_position = (
                    cx * TILE_SIZE + TILE_SIZE / 2,
                    cy * TILE_SIZE + TILE_SIZE / 2,
                )
                hero.state = HeroState.MOVING
                break
    else:
        # Step 3: reset goal to an easy patrol objective.
        hero.stuck_reason = "reset_goal"
        hero.target = {"type": "patrol"}
        zone_x, zone_y = ai.exploration_behavior.assign_patrol_zone(ai, hero, game_state)
        hero.target_position = (zone_x, zone_y)
        hero.state = HeroState.MOVING

    hero._unstuck_attempts_for_target = attempt_idx + 1
    hero._last_unstuck_attempt_ms = now_ms
    hero.unstuck_attempts = int(getattr(hero, "unstuck_attempts", 0) or 0) + 1
