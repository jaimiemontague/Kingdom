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

from config import TILE_SIZE
from game.systems.pathfinding import find_path, grid_to_world_path
from game.systems import perf_stats


def _occupied_tiles(buildings: Iterable) -> set[tuple[int, int]]:
    blocked: set[tuple[int, int]] = set()
    for b in buildings or []:
        # Only treat constructed (or castle) buildings as solid for navigation.
        if getattr(b, "hp", 1) <= 0:
            continue
        if getattr(b, "building_type", "") != "castle" and getattr(b, "is_constructed", True) is False:
            continue
        gx = getattr(b, "grid_x", None)
        gy = getattr(b, "grid_y", None)
        size = getattr(b, "size", None)
        if gx is None or gy is None or not size:
            continue
        for dx in range(size[0]):
            for dy in range(size[1]):
                blocked.add((gx + dx, gy + dy))
    return blocked


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
    t0 = time.perf_counter()
    start = world.world_to_grid(start_x, start_y)
    goal = world.world_to_grid(goal_x, goal_y)
    # Cap expansions to keep worst-case pathfinding bounded on large maps.
    grid_path = find_path(world, start, goal, buildings=buildings, max_expansions=8000)
    dt_ms = (time.perf_counter() - t0) * 1000.0
    perf_stats.pathfinding.calls += 1
    perf_stats.pathfinding.total_ms += dt_ms
    if not grid_path:
        perf_stats.pathfinding.failures += 1
    return grid_to_world_path(grid_path)


def step_towards(x: float, y: float, tx: float, ty: float, speed: float, dt: float) -> tuple[float, float, bool]:
    """Move a point towards (tx, ty) at speed (tiles/sec style), returns (x, y, reached)."""
    dx = tx - x
    dy = ty - y
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 1e-6:
        return tx, ty, True
    move_dist = speed * dt * 60
    if move_dist >= dist:
        return tx, ty, True
    return x + (dx / dist) * move_dist, y + (dy / dist) * move_dist, False


def follow_path(entity, dt: float, arrive_radius: float = 4.0) -> bool:
    """
    Step an entity along its `path` list of world-space waypoints.
    Returns True if the entity reached the end of the path (or has no path).
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


