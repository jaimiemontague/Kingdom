"""
Simple A* pathfinding implementation.
WK17: Bounded path cache to reduce allocation churn (memory leak mitigation).
WK59: Perf pass — cached blocked tiles, larger path cache, reduced expansions for long paths.
"""
import heapq
from config import TILE_SIZE

# Bounded path cache: key (start, goal) -> path. FIFO eviction.
_PATH_CACHE: dict[tuple[tuple[int, int], tuple[int, int]], list] = {}
_PATH_CACHE_MAX = 1024

# Cached blocked tiles set — rebuilt only when building count/hp changes.
_BLOCKED_CACHE: set[tuple[int, int]] = set()
_BLOCKED_CACHE_KEY: tuple = ()


def _rebuild_blocked_cache(buildings: list) -> set[tuple[int, int]]:
    """Rebuild the blocked tiles set from buildings and cache it."""
    global _BLOCKED_CACHE, _BLOCKED_CACHE_KEY
    if not buildings:
        _BLOCKED_CACHE = set()
        _BLOCKED_CACHE_KEY = ()
        return _BLOCKED_CACHE

    cache_key = (
        len(buildings),
        sum(1 for b in buildings if getattr(b, "is_constructed", True)),
    )
    if cache_key == _BLOCKED_CACHE_KEY and _BLOCKED_CACHE:
        return _BLOCKED_CACHE

    blocked: set[tuple[int, int]] = set()
    for building in buildings:
        size = getattr(building, "size", None)
        if not size:
            continue
        gx = getattr(building, "grid_x", None)
        gy = getattr(building, "grid_y", None)
        if gx is None or gy is None:
            continue
        for dx in range(size[0]):
            for dy in range(size[1]):
                blocked.add((gx + dx, gy + dy))
    _BLOCKED_CACHE = blocked
    _BLOCKED_CACHE_KEY = cache_key
    return blocked


def invalidate_blocked_cache() -> None:
    """Call when buildings are added/removed/destroyed to force cache rebuild."""
    global _BLOCKED_CACHE_KEY
    _BLOCKED_CACHE_KEY = ()


def heuristic(a: tuple, b: tuple) -> float:
    """Manhattan distance heuristic."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def get_neighbors(pos: tuple, world) -> list:
    """Get walkable neighboring tiles."""
    x, y = pos
    neighbors = []
    
    # 4-directional movement
    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        nx, ny = x + dx, y + dy
        if world.is_walkable(nx, ny):
            neighbors.append((nx, ny))
    
    # 8-directional (diagonal) movement
    for dx, dy in [(1, 1), (1, -1), (-1, 1), (-1, -1)]:
        nx, ny = x + dx, y + dy
        # Only allow diagonal if both adjacent tiles are walkable
        if (world.is_walkable(nx, ny) and 
            world.is_walkable(x + dx, y) and 
            world.is_walkable(x, y + dy)):
            neighbors.append((nx, ny))
    
    return neighbors


def find_path(
    world,
    start: tuple,
    goal: tuple,
    buildings: list = None,
    *,
    max_expansions: int = 8000,
) -> tuple[list, int]:
    """
    Find a path from start to goal using A*.

    Args:
        world: The World object with tile data
        start: (grid_x, grid_y) starting position
        goal: (grid_x, grid_y) target position
        buildings: Optional list of buildings to avoid

    Returns:
        (path, expansions_used) where path is a list of (grid_x, grid_y)
        positions forming the path (or [] if no path found), and
        expansions_used is the number of A* nodes expanded (for budget tracking).
    """
    if start == goal:
        return [start], 0

    # Use cached blocked tiles set (rebuilt only when buildings change).
    blocked = _rebuild_blocked_cache(buildings) if buildings else set()

    # Scale max_expansions by distance — short paths don't need 8000 nodes.
    dist = abs(start[0] - goal[0]) + abs(start[1] - goal[1])
    if max_expansions == 8000:
        max_expansions = min(8000, max(800, dist * 12))

    # Check if goal is walkable; adjust to nearest walkable if not
    if not world.is_walkable(goal[0], goal[1]):
        for radius in range(1, 5):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    test_pos = (goal[0] + dx, goal[1] + dy)
                    if world.is_walkable(test_pos[0], test_pos[1]):
                        goal = test_pos
                        break
                else:
                    continue
                break
            else:
                continue
            break

    cache_key = (start, goal)
    cached = _PATH_CACHE.get(cache_key)
    if cached is not None:
        # Validate cached path still valid (each cell walkable or goal; non-goal not blocked)
        valid = True
        for cell in cached:
            if cell == goal:
                continue
            if cell in blocked:
                valid = False
                break
            if not world.is_walkable(cell[0], cell[1]):
                valid = False
                break
        if valid:
            return list(cached), 0

    # A* algorithm
    open_set = []
    heapq.heappush(open_set, (0, start))
    came_from = {}
    g_score = {start: 0}
    f_score = {start: heuristic(start, goal)}
    open_set_hash = {start}

    expansions = 0
    while open_set:
        current = heapq.heappop(open_set)[1]
        open_set_hash.discard(current)
        expansions += 1
        if max_expansions is not None and expansions >= int(max_expansions):
            # Safety valve: avoid pathological searches on large maps (prevents multi-hundred-ms A*).
            return [], expansions

        if current == goal:
            # Reconstruct path
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            path.reverse()
            # WK17: Store in bounded cache (FIFO eviction)
            if len(_PATH_CACHE) >= _PATH_CACHE_MAX:
                first = next(iter(_PATH_CACHE))
                del _PATH_CACHE[first]
            _PATH_CACHE[cache_key] = path
            return path, expansions

        for neighbor in get_neighbors(current, world):
            # Skip if blocked by building (unless it's the goal)
            if neighbor in blocked and neighbor != goal:
                continue

            # Diagonal movement costs more
            if abs(neighbor[0] - current[0]) + abs(neighbor[1] - current[1]) == 2:
                move_cost = 1.414
            else:
                move_cost = 1

            tentative_g = g_score[current] + move_cost

            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score[neighbor] = tentative_g + heuristic(neighbor, goal)

                if neighbor not in open_set_hash:
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))
                    open_set_hash.add(neighbor)

    # No path found
    return [], expansions


def grid_to_world_path(grid_path: list) -> list:
    """Convert a grid path to world coordinates (center of each tile)."""
    world_path = []
    for gx, gy in grid_path:
        wx = gx * TILE_SIZE + TILE_SIZE // 2
        wy = gy * TILE_SIZE + TILE_SIZE // 2
        world_path.append((wx, wy))
    return world_path


# ---------------------------------------------------------------------------
# WK57 Wave 4: Layer-aware pathfinding wrapper
# ---------------------------------------------------------------------------

class LayerPathfinder:
    """Layer-aware pathfinding wrapper.

    Same-layer surface paths delegate to existing find_path().
    Cross-layer paths route through cave entrances.
    Underground paths use A* on the area's walkability grid.
    """

    def __init__(self, world, underground_areas: dict):
        self._world = world
        self._underground_areas = underground_areas
        self._cave_entrances: dict[tuple[int, int], str] = {}  # (grid_x, grid_y) -> area_id
        for area_id, area in underground_areas.items():
            self._cave_entrances[(area.entrance_grid_x, area.entrance_grid_y)] = area_id

    def find_layer_path(self, start_x, start_y, start_layer, goal_x, goal_y, goal_layer):
        """Find path between any two points, potentially across layers.

        Returns list of (x, y, layer) tuples, or empty list if no path.
        """
        if start_layer == goal_layer == 0:
            # Pure surface path -- delegate to existing pathfinder
            path, _expansions = find_path(self._world, (start_x, start_y), (goal_x, goal_y))
            return [(x, y, 0) for x, y in path] if path else []

        if start_layer == goal_layer == -1:
            # Pure underground path within same area
            return self._find_underground_path(start_x, start_y, goal_x, goal_y)

        if start_layer == 0 and goal_layer == -1:
            # Surface to underground: route to cave entrance, then descend
            area = self._find_area_for_underground_pos(goal_x, goal_y)
            if area is None:
                return []
            entrance = (area.entrance_grid_x, area.entrance_grid_y)

            # Surface path to entrance
            surface_path, _expansions = find_path(self._world, (start_x, start_y), (entrance[0], entrance[1]))
            if not surface_path:
                return []

            # Underground path from entrance to goal
            ug_path = self._find_underground_path(entrance[0], entrance[1], goal_x, goal_y)

            result = [(x, y, 0) for x, y in surface_path]
            result.extend(ug_path)
            return result

        if start_layer == -1 and goal_layer == 0:
            # Underground to surface: underground path to entrance, ascend, then surface
            area = self._find_area_for_underground_pos(start_x, start_y)
            if area is None:
                return []
            entrance = (area.entrance_grid_x, area.entrance_grid_y)

            ug_path = self._find_underground_path(start_x, start_y, entrance[0], entrance[1])

            surface_path, _expansions = find_path(self._world, (entrance[0], entrance[1]), (goal_x, goal_y))
            if not surface_path:
                return ug_path  # at least get to entrance

            result = list(ug_path)
            result.extend([(x, y, 0) for x, y in surface_path])
            return result

        return []

    def _find_underground_path(self, start_x, start_y, goal_x, goal_y):
        """A* pathfinding within an underground area using the walkability grid."""
        # Find which area these coords belong to
        area = self._find_area_for_underground_pos(start_x, start_y)
        if area is None:
            area = self._find_area_for_underground_pos(goal_x, goal_y)
        if area is None:
            return []

        # Convert world grid coords to underground local coords
        cx = area.total_width // 2

        def to_local(gx, gy):
            return (gx - area.entrance_grid_x + cx, gy - area.entrance_grid_y)

        def to_world(lx, lz):
            return (lx - cx + area.entrance_grid_x, lz + area.entrance_grid_y)

        sx, sz = to_local(start_x, start_y)
        gx_l, gz_l = to_local(goal_x, goal_y)

        # Clamp to grid bounds (entrance tile might be at edge)
        sx = max(0, min(area.total_width - 1, sx))
        sz = max(0, min(area.total_height - 1, sz))
        gx_l = max(0, min(area.total_width - 1, gx_l))
        gz_l = max(0, min(area.total_height - 1, gz_l))

        # Simple A* on the walkability grid (4-directional)
        def ug_heuristic(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        start_node = (sx, sz)
        goal_node = (gx_l, gz_l)

        open_set = [(ug_heuristic(start_node, goal_node), 0, start_node)]
        came_from: dict = {}
        g_score: dict = {start_node: 0}

        while open_set:
            _, _, current = heapq.heappop(open_set)

            if current == goal_node:
                # Reconstruct path
                path = []
                while current in came_from:
                    wx, wy = to_world(*current)
                    path.append((wx, wy, -1))
                    current = came_from[current]
                wx, wy = to_world(*current)
                path.append((wx, wy, -1))
                path.reverse()
                return path

            for dx, dz in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, nz = current[0] + dx, current[1] + dz
                if 0 <= nx < area.total_width and 0 <= nz < area.total_height:
                    if not area.walkability[nz][nx]:
                        continue
                    new_g = g_score[current] + 1
                    if (nx, nz) not in g_score or new_g < g_score[(nx, nz)]:
                        g_score[(nx, nz)] = new_g
                        f = new_g + ug_heuristic((nx, nz), goal_node)
                        heapq.heappush(open_set, (f, new_g, (nx, nz)))
                        came_from[(nx, nz)] = current

        return []  # no path found

    def _find_area_for_underground_pos(self, world_gx, world_gy):
        """Find which UndergroundArea contains the given world grid position."""
        for area in self._underground_areas.values():
            # Check if pos is within area bounds
            dx = world_gx - area.entrance_grid_x
            dy = world_gy - area.entrance_grid_y
            cx = area.total_width // 2
            lx = dx + cx
            lz = dy
            if 0 <= lx < area.total_width and 0 <= lz < area.total_height:
                if area.walkability[lz][lx]:
                    return area
        return None

