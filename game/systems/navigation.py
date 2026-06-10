"""
Navigation helpers for entity movement around blocking tiles + buildings.

The game uses a tile grid (see `game/world.py`) but entities move in world-space.
These helpers bridge the gap by computing A* paths that avoid building footprints,
then stepping entities along those waypoints.
"""

from __future__ import annotations

import math
import os
from typing import Iterable, Optional, Tuple, List
import time
import time as _time

from config import TILE_SIZE
from game.systems.pathfinding import find_path, grid_to_world_path, _rebuild_blocked_cache
from game.systems import perf_stats

# Mythos S5 (astar-burst-cap-tile-goals): chase goals key on the goal TILE so a
# target moving within one tile no longer invalidates the path every tick, and
# far-target replans commit longer. "0" restores pixel-keyed goals (A/B hatch).
_ASTAR_TILE_GOALS = os.environ.get("KINGDOM_ASTAR_TILE_GOALS", "1") != "0"
# Commit window for far chase targets (> _FAR_GOAL_TILES tiles away).
_FAR_GOAL_TILES = 6
_FAR_GOAL_COMMIT_MS = 1000


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


class PathfindingBudget:
    """Deterministic per-frame pathfinding budget.

    Budget is measured in A* node expansions, not wall-clock time.
    This ensures identical gameplay regardless of hardware speed.
    Wall-clock timing is still collected for perf metrics but does
    not gate whether a path request is served.

    Mythos S5 (astar-burst-cap-tile-goals): caps lowered 24->8 plans and
    24k->8k expansions per tick. The old budget legally allowed aligned replan
    bursts to pack 6-7.5ms of A* into ONE tick (the measured sim-side hitch
    signature); the deferred-return contract (compute_path_worldpoints -> None,
    callers keep their old path / direct-steer) amortizes the overflow across
    ticks. Env-overridable for A/B: KINGDOM_ASTAR_MAX_PLANS / _MAX_EXPANSIONS.
    """

    MAX_PLANS_PER_FRAME: int = _env_int("KINGDOM_ASTAR_MAX_PLANS", 8)           # was 24
    MAX_EXPANSIONS_PER_FRAME: int = _env_int("KINGDOM_ASTAR_MAX_EXPANSIONS", 8_000)  # was 24_000

    def __init__(self) -> None:
        self._frame_plans: int = 0
        self._frame_expansions: int = 0
        # Metrics only (not used for budget decisions):
        self._frame_ms_used: float = 0.0
        self._pending_queue: list = []  # [(entity_id, world, buildings, sx, sy, gx, gy)]

    def begin_frame(self) -> None:
        """Call at start of each simulation frame to reset budget."""
        self._frame_plans = 0
        self._frame_expansions = 0
        self._frame_ms_used = 0.0

    def budget_available(self) -> bool:
        """Check if there's budget remaining this frame."""
        return (
            self._frame_plans < self.MAX_PLANS_PER_FRAME
            and self._frame_expansions < self.MAX_EXPANSIONS_PER_FRAME
        )

    def record_plan(self, expansions: int, wall_ms: float = 0.0) -> None:
        """Record one completed path plan.

        Args:
            expansions: Number of A* nodes expanded (from find_path return).
            wall_ms: Wall-clock time for metrics only.
        """
        self._frame_plans += 1
        self._frame_expansions += expansions
        self._frame_ms_used += wall_ms

    def enqueue(self, entity_id, world, buildings, sx, sy, gx, gy):
        """Queue a replan request for next frame when budget is exhausted."""
        # Don't duplicate - replace existing entry for same entity
        for i, item in enumerate(self._pending_queue):
            if item[0] == entity_id:
                self._pending_queue[i] = (entity_id, world, buildings, sx, sy, gx, gy)
                return
        self._pending_queue.append((entity_id, world, buildings, sx, sy, gx, gy))

    def drain_pending(self) -> list:
        """Return and clear pending requests from last frame (to be processed this frame within budget)."""
        pending = self._pending_queue
        self._pending_queue = []
        return pending


# Global singleton
_pathfinding_budget = PathfindingBudget()


def get_pathfinding_budget() -> PathfindingBudget:
    return _pathfinding_budget


def _occupied_tiles(buildings: Iterable) -> set[tuple[int, int]]:
    return _rebuild_blocked_cache(list(buildings) if buildings else [])


def best_adjacent_tile(world, buildings: list, building, from_x: float, from_y: float) -> Optional[tuple[int, int]]:
    """
    Pick a walkable, unoccupied tile adjacent to a building footprint.
    Prefer the tile closest to the requester (from_x/from_y).
    """
    gx = getattr(building, "grid_x", None)
    gy = getattr(building, "grid_y", None)
    size = getattr(building, "size", None)
    if gx is None or gy is None or not size:
        return None

    blocked = _occupied_tiles(buildings)
    candidates: list[tuple[int, int]] = []

    # Ring around footprint (4-neighborhood around perimeter)
    for x in range(gx - 1, gx + size[0] + 1):
        candidates.append((x, gy - 1))
        candidates.append((x, gy + size[1]))
    for y in range(gy, gy + size[1]):
        candidates.append((gx - 1, y))
        candidates.append((gx + size[0], y))

    # Filter to walkable + not occupied
    filtered: list[tuple[int, int]] = []
    for cx, cy in candidates:
        if (cx, cy) in blocked:
            continue
        if not world.is_walkable(cx, cy):
            continue
        filtered.append((cx, cy))

    if not filtered:
        return None

    # Choose closest to requester in world-space
    def dist2(tile: tuple[int, int]) -> float:
        wx = tile[0] * TILE_SIZE + TILE_SIZE / 2
        wy = tile[1] * TILE_SIZE + TILE_SIZE / 2
        dx = wx - from_x
        dy = wy - from_y
        return dx * dx + dy * dy

    filtered.sort(key=dist2)
    return filtered[0]


def compute_path_worldpoints(
    world,
    buildings: list,
    start_x: float,
    start_y: float,
    goal_x: float,
    goal_y: float,
) -> list[tuple[float, float]] | None:
    """Compute an A* path (world-space waypoints) avoiding solid buildings.

    Returns:
        list: the path, or [] when there is genuinely no path to the goal.
        None: DEFERRED -- the per-frame budget is exhausted. The caller MUST
              keep its existing ``path`` and retry next frame. Do NOT treat
              None as failure and do NOT assign it to ``entity.path``.
    """
    budget = get_pathfinding_budget()

    # Budget exhausted -> defer (do NOT return [], which callers would assign,
    # wiping a still-valid path and looking like 'no path found').
    if not budget.budget_available():
        return None

    start = world.world_to_grid(start_x, start_y)
    goal = world.world_to_grid(goal_x, goal_y)

    # Wall-clock timing for metrics only (does NOT gate budget)
    t0 = time.perf_counter()
    grid_path, expansions = find_path(world, start, goal, buildings=buildings, max_expansions=8000)
    t1 = time.perf_counter()
    wall_ms = (t1 - t0) * 1000.0

    # Record using deterministic expansion count
    budget.record_plan(expansions, wall_ms)

    # Update perf stats (observability)
    perf_stats.pathfinding.calls += 1
    perf_stats.pathfinding.total_ms += wall_ms
    perf_stats.pathfinding.total_expansions += expansions
    if not grid_path:
        perf_stats.pathfinding.failures += 1
        return []

    return grid_to_world_path(grid_path)


def step_towards(x: float, y: float, tx: float, ty: float, speed: float, dt: float) -> tuple[float, float, bool]:
    """Move a point towards (tx, ty) at speed (px/sec), returns (x, y, reached)."""
    dx = tx - x
    dy = ty - y
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 1e-6:
        return tx, ty, True
    move_dist = speed * dt
    if move_dist >= dist:
        return tx, ty, True
    return x + (dx / dist) * move_dist, y + (dy / dist) * move_dist, False


def follow_path(entity, dt: float, arrive_radius: float = 10.0) -> bool:
    """
    Step an entity along its `path` list of world-space waypoints.
    Returns True if the entity reached the end of the path (or has no path).
    arrive_radius: consider waypoint reached when within this many px (reduces overshoot jitter).
    """
    path: List[Tuple[float, float]] = getattr(entity, "path", None) or []
    if not path:
        return True

    tx, ty = path[0]
    speed = getattr(entity, "speed", 1.5)
    x, y, reached = step_towards(getattr(entity, "x"), getattr(entity, "y"), tx, ty, speed, dt)
    entity.x = x
    entity.y = y

    if reached or (abs(entity.x - tx) + abs(entity.y - ty)) <= arrive_radius:
        # Consume waypoint
        path.pop(0)
        entity.path = path

    return not bool(entity.path)


def advance_along_path_to(
    entity,
    world,
    buildings,
    goal_x: float,
    goal_y: float,
    dt: float,
    now_ms_val: int,
) -> None:
    """Replan-and-follow a path toward (goal_x, goal_y), with a direct-steer fallback.

    WK72 W2: behavior-preserving extraction of the path-follow block copy-pasted in
    ``Enemy.update`` and ``SkeletonArcher.update``. The logic is reproduced byte-for-byte
    from those sites; ``now_ms_val`` is the caller's already-computed ``now_ms()`` reading.

    Commitment: when chasing moving targets, stick to current path to avoid jitter.
    Replan only if no path, or (goal changed AND commitment window expired), and only
    once the replan throttle (``_next_replan_ms``) has elapsed. A ``None`` from
    ``compute_path_worldpoints`` means the per-frame budget is exhausted (deferred):
    keep the existing path and retry next frame. Falls back to ``move_towards`` (direct
    steering) when there is no usable path so the entity never freezes.

    NOTE: ``game/entities/guard.py`` deliberately does NOT use this helper -- its block
    omits the ``_next_replan_ms`` throttle and follows the path unconditionally (no
    direct-steer fallback). Unifying it would change guard behavior, so it is left inline.
    """
    if not hasattr(entity, "path"):
        entity.path = []
        entity._path_goal = None
    if _ASTAR_TILE_GOALS:
        # Mythos S5: key the goal on its TILE (the same quantization Hero.update
        # already uses, hero.py:501) so a chase target moving within one tile
        # never invalidates the committed path. Pixel-keyed goals made every
        # chasing enemy replan each 500ms commit expiry (~4.3 plans/tick at the
        # swarm, aligning into 6-7.5ms single-tick A* bursts).
        goal_key = world.world_to_grid(goal_x, goal_y)
    else:
        goal_key = (int(goal_x), int(goal_y))
    path_commit = int(getattr(entity, "_path_commit_until_ms", 0) or 0)
    has_path = bool(getattr(entity, "path", None))
    # Commitment: when chasing moving targets, stick to current path to avoid jitter.
    # Replan only if no path, or (goal changed AND commitment window expired).
    want_replan = (
        (not has_path) or (getattr(entity, "_path_goal", None) != goal_key and now_ms_val >= path_commit)
    ) and now_ms_val >= int(getattr(entity, "_next_replan_ms", 0) or 0)
    if want_replan:
        _new_path = compute_path_worldpoints(world, buildings, entity.x, entity.y, goal_x, goal_y)
        if _new_path is not None:
            entity.path = _new_path
            entity._path_goal = goal_key
            commit_ms = getattr(entity, "_path_commit_duration_ms", 500)
            if _ASTAR_TILE_GOALS:
                # Far targets (> ~6 tiles) commit longer — precision cornering
                # is irrelevant until the chaser closes in, and the longer
                # window halves steady-state replan demand at the swarm.
                _dx = float(goal_x) - float(entity.x)
                _dy = float(goal_y) - float(entity.y)
                if (_dx * _dx + _dy * _dy) > float(TILE_SIZE * _FAR_GOAL_TILES) ** 2:
                    commit_ms = max(int(commit_ms), _FAR_GOAL_COMMIT_MS)
            entity._path_commit_until_ms = now_ms_val + commit_ms
            if not entity.path:
                entity._next_replan_ms = now_ms_val + 800
            else:
                entity._next_replan_ms = now_ms_val + 150
        # else: deferred -- keep existing path, retry next frame

    if entity.path:
        follow_path(entity, dt)
    else:
        # Fallback: still move roughly toward the goal so enemies don't freeze.
        entity.move_towards(goal_x, goal_y, dt)


