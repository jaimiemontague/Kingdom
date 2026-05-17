"""
Navigation helpers for entity movement around blocking tiles + buildings.

The game uses a tile grid (see `game/world.py`) but entities move in world-space.
These helpers bridge the gap by computing A* paths that avoid building footprints,
then stepping entities along those waypoints.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional, Tuple, List
import time
import time as _time

from config import TILE_SIZE
from game.systems.pathfinding import find_path, grid_to_world_path, _rebuild_blocked_cache
from game.systems import perf_stats


class PathfindingBudget:
    """Global per-frame budget for A* pathfinding. Prevents frame stalls from simultaneous replans."""

    MAX_MS_PER_FRAME = 3.0

    def __init__(self):
        self._frame_start: float = 0.0
        self._frame_ms_used: float = 0.0
        self._pending_queue: list = []  # [(entity_id, world, buildings, sx, sy, gx, gy)]

    def begin_frame(self):
        """Call at start of each simulation frame to reset budget."""
        self._frame_start = _time.perf_counter()
        self._frame_ms_used = 0.0

    def budget_available(self) -> bool:
        """Check if there's budget remaining this frame."""
        return self._frame_ms_used < self.MAX_MS_PER_FRAME

    def record_time(self, ms: float):
        """Record time spent on a pathfinding call."""
        self._frame_ms_used += ms

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
) -> list[tuple[float, float]]:
    """Compute an A* path (as world-space waypoints) avoiding solid buildings."""
    budget = get_pathfinding_budget()

    # If budget exhausted, return empty (caller keeps existing path)
    if not budget.budget_available():
        return []

    t0 = time.perf_counter()
    start = world.world_to_grid(start_x, start_y)
    goal = world.world_to_grid(goal_x, goal_y)
    # Cap expansions to keep worst-case pathfinding bounded on large maps.
    grid_path = find_path(world, start, goal, buildings=buildings, max_expansions=8000)
    dt_ms = (time.perf_counter() - t0) * 1000.0

    budget.record_time(dt_ms)
    perf_stats.pathfinding.calls += 1
    perf_stats.pathfinding.total_ms += dt_ms
    if not grid_path:
        perf_stats.pathfinding.failures += 1
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


