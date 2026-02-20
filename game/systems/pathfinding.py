"""
Simple A* pathfinding implementation.
WK17: Bounded path cache to reduce allocation churn (memory leak mitigation).
"""
import heapq
from config import TILE_SIZE

# Bounded path cache: key (start, goal) -> path. FIFO eviction, max 256 entries.
_PATH_CACHE: dict[tuple[tuple[int, int], tuple[int, int]], list] = {}
_PATH_CACHE_MAX = 256


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
) -> list:
    """
    Find a path from start to goal using A*.
    
    Args:
        world: The World object with tile data
        start: (grid_x, grid_y) starting position
        goal: (grid_x, grid_y) target position
        buildings: Optional list of buildings to avoid
        
    Returns:
        List of (grid_x, grid_y) positions forming the path, or empty list if no path.
    """
    if start == goal:
        return [start]

    # Build set of blocked tiles from buildings (needed for cache validation and A*)
    blocked = set()
    if buildings:
        for building in buildings:
            for dx in range(building.size[0]):
                for dy in range(building.size[1]):
                    blocked.add((building.grid_x + dx, building.grid_y + dy))

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
            return list(cached)

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
            return []
        
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
            return path
        
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
    return []


def grid_to_world_path(grid_path: list) -> list:
    """Convert a grid path to world coordinates (center of each tile)."""
    world_path = []
    for gx, gy in grid_path:
        wx = gx * TILE_SIZE + TILE_SIZE // 2
        wy = gy * TILE_SIZE + TILE_SIZE // 2
        world_path.append((wx, wy))
    return world_path

