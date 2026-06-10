"""
World and tile map system.
"""
from config import (
    TILE_SIZE, MAP_WIDTH, MAP_HEIGHT,
    COLOR_GRASS, COLOR_WATER, COLOR_PATH, COLOR_TREE,
)
from game.sim.determinism import get_rng
# WK86: one-shot world generation moved to game.worldgen (math, the `noise`
# Perlin import, and get_zone_blend now live there). The generate_* / flatten_*
# methods below are thin delegating wrappers.


class TileType:
    GRASS = 0
    WATER = 1
    PATH = 2
    TREE = 3


TILE_COLORS = {
    TileType.GRASS: COLOR_GRASS,
    TileType.WATER: COLOR_WATER,
    TileType.PATH: COLOR_PATH,
    TileType.TREE: COLOR_TREE,
}

# Tiles that block movement
BLOCKING_TILES = {TileType.WATER}


class Visibility:
    UNSEEN = 0
    SEEN = 1
    VISIBLE = 2


class World:
    """Manages the game world tile map."""
    
    def __init__(self):
        self.width = MAP_WIDTH
        self.height = MAP_HEIGHT
        self.tiles = [[TileType.GRASS for _ in range(self.width)] for _ in range(self.height)]
        # Deterministic world-gen stream (independent of other RNG usage).
        self.rng = get_rng("world_gen")
        # WK44 Stage 2: injected by SimEngine; called as tree_growth_lookup(tx,ty)->0..1
        self.tree_growth_lookup = None
        # Mythos S5 (tree-blocking-set-walkability): injected by SimEngine — the
        # live set of TREE tiles whose growth is >= 0.75 (the blocking threshold).
        # When present, is_walkable/is_buildable's TREE branch is ONE set lookup
        # instead of the 5-call tree_growth_lookup chain (A* calls is_walkable up
        # to 8x per expanded node). None => fall back to the original chain.
        self.blocked_tree_tiles = None
        self.generate_terrain()

        # WK53 Wave 2: heightmap for terrain elevation (generated after flat tiles).
        self.heightmap: list[list[float]] | None = None
        self.heightmap_grid_w: int = 0
        self.heightmap_grid_h: int = 0
        self.generate_heightmap()

        # Fog-of-war visibility grid (tile-based).
        # UNSEEN: never revealed; SEEN: explored but not currently visible; VISIBLE: in vision now.
        self.visibility = [[Visibility.UNSEEN for _ in range(self.width)] for _ in range(self.height)]
        self._currently_visible: list[tuple[int, int]] = []  # tiles marked VISIBLE this frame (demoted next update)
        self.fog_disabled = False

        # WK57 Wave 4: Per-underground-area visibility grids.
        # area_id -> 2D grid of Visibility values (UNSEEN/SEEN/VISIBLE)
        self.underground_visibility: dict[str, list[list[int]]] = {}
        # WK66 L10: terrain/fog DRAWING + the reusable fog Surfaces moved to
        # game.graphics.world_terrain_renderer.WorldTerrainRenderer (the sim no
        # longer imports pygame). All fog STATE below stays sim-owned.

    def generate_terrain(self):
        """Generate a simple procedural terrain.

        WK86: delegates to ``game.worldgen.generate_terrain`` (pure-move). Imported
        lazily to avoid a worldgen<->world import cycle.
        """
        from game.worldgen import generate_terrain as _gt
        return _gt(self)

    def generate_heightmap(self) -> None:
        """WK53 Wave 2: Generate a Perlin-noise heightmap at 2x sub-tile resolution.

        WK86: delegates to ``game.worldgen.generate_heightmap`` (pure-move).
        """
        from game.worldgen import generate_heightmap as _gh
        return _gh(self)

    def flatten_building_footprints(self, buildings):
        """Flatten terrain under all placed buildings/lairs.

        WK86: delegates to ``game.worldgen.flatten_building_footprints`` (pure-move).
        Called after buildings are placed during world generation.
        """
        from game.worldgen import flatten_building_footprints as _fbf
        return _fbf(self, buildings)

    def get_tile(self, x: int, y: int) -> int:
        """Get tile type at grid position."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.tiles[y][x]
        return TileType.WATER  # Out of bounds treated as water
    
    def set_tile(self, x: int, y: int, tile_type: int):
        """Set tile type at grid position."""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.tiles[y][x] = tile_type
    
    def is_walkable(self, x: int, y: int) -> bool:
        """Check if a tile can be walked on."""
        tile = self.get_tile(x, y)
        if tile in BLOCKING_TILES:
            return False
        if tile == TileType.TREE:
            # Mythos S5: precomputed blocking-tile set (growth >= 0.75) — exact
            # same semantics as the lookup chain below. A TREE tile missing from
            # the growth dict reads growth 1.0 (blocked) in the old chain; such
            # tiles only exist before SimEngine wires the set, when this attr is
            # still None and the fallback runs.
            bs = self.blocked_tree_tiles
            if bs is not None:
                return (x, y) not in bs
            g = 1.0
            fn = getattr(self, "tree_growth_lookup", None)
            if callable(fn):
                try:
                    g = float(fn(int(x), int(y)))
                except Exception:
                    g = 1.0
            # WK44: blocking threshold is growth >= 0.75
            return g < 0.75
        return True
    
    def is_buildable(self, x: int, y: int, width: int = 1, height: int = 1) -> bool:
        """Check if an area can have a building placed on it."""
        for dy in range(height):
            for dx in range(width):
                tile = self.get_tile(x + dx, y + dy)
                if tile in BLOCKING_TILES:
                    return False
                if tile == TileType.TREE:
                    # Mythos S5: same blocking-tile set fast path as is_walkable.
                    bs = self.blocked_tree_tiles
                    if bs is not None:
                        if (x + dx, y + dy) in bs:
                            return False
                        continue
                    g = 1.0
                    fn = getattr(self, "tree_growth_lookup", None)
                    if callable(fn):
                        try:
                            g = float(fn(int(x + dx), int(y + dy)))
                        except Exception:
                            g = 1.0
                    if g >= 0.75:
                        return False
        return True
    
    def world_to_grid(self, world_x: float, world_y: float) -> tuple:
        """Convert world coordinates to grid coordinates."""
        return int(world_x // TILE_SIZE), int(world_y // TILE_SIZE)
    
    def grid_to_world(self, grid_x: int, grid_y: int) -> tuple:
        """Convert grid coordinates to world coordinates (top-left of tile)."""
        return grid_x * TILE_SIZE, grid_y * TILE_SIZE

    def is_tile_visible_at(self, world_x: float, world_y: float) -> bool:
        """WK66: sim-owned read of the fog grid — is the tile under (world_x, world_y)
        currently VISIBLE? Out-of-bounds tiles read as visible (matches the
        renderer's pre-WK66 behavior of skipping the bounds-checked dimming).

        This lets ``build_snapshot`` populate ``BuildingDTO.tile_visible`` so the
        render boundary does not have to reach into ``world.visibility`` for it.
        The live grid is still exposed for richer gating (e.g. lair SEEN checks).
        """
        tx = int(world_x // TILE_SIZE)
        ty = int(world_y // TILE_SIZE)
        if 0 <= ty < self.height and 0 <= tx < self.width:
            return self.visibility[ty][tx] == Visibility.VISIBLE
        return True

    def _reveal_circle(self, grid_cx: int, grid_cy: int, radius_tiles: int, newly_revealed: set = None):
        """
        Mark tiles within a circle as VISIBLE.

        Args:
            grid_cx, grid_cy: Center grid coordinates
            radius_tiles: Vision radius in tiles
            newly_revealed: Optional set to populate with (grid_x, grid_y) tiles that transitioned UNSEEN -> VISIBLE
        """
        r = max(0, int(radius_tiles))
        vis = self.visibility
        cv = self._currently_visible
        VISIBLE = Visibility.VISIBLE
        UNSEEN = Visibility.UNSEEN
        w = self.width
        h = self.height

        if r <= 0:
            if 0 <= grid_cx < w and 0 <= grid_cy < h:
                if newly_revealed is not None and vis[grid_cy][grid_cx] == UNSEEN:
                    newly_revealed.add((grid_cx, grid_cy))
                vis[grid_cy][grid_cx] = VISIBLE
                cv.append((grid_cx, grid_cy))
            return

        y0 = max(0, grid_cy - r)
        y1 = min(h - 1, grid_cy + r)
        r2 = r * r
        track_new = newly_revealed is not None
        for y in range(y0, y1 + 1):
            dy = y - grid_cy
            dx_max = int((r2 - dy * dy) ** 0.5)
            x0 = max(0, grid_cx - dx_max)
            x1 = min(w - 1, grid_cx + dx_max)
            row = vis[y]
            for x in range(x0, x1 + 1):
                if track_new and row[x] == UNSEEN:
                    newly_revealed.add((x, y))
                row[x] = VISIBLE
                cv.append((x, y))

    def update_visibility(self, revealers: list[tuple[float, float, int]], return_new_reveals: bool = False):
        """
        Update the fog-of-war based on a set of revealers.

        `revealers`: list of (world_x, world_y, radius_tiles).
        `return_new_reveals`: If True, return set of (grid_x, grid_y) tiles that transitioned UNSEEN -> VISIBLE.

        Returns:
            If return_new_reveals=True: set of (grid_x, grid_y) tuples for newly revealed tiles.
            Otherwise: None
        """
        newly_revealed = set() if return_new_reveals else None

        vis = self.visibility
        VISIBLE = Visibility.VISIBLE
        SEEN = Visibility.SEEN
        w = self.width
        h = self.height

        if self.fog_disabled:
            for y in range(h):
                row = vis[y]
                for x in range(w):
                    if row[x] != VISIBLE:
                        if newly_revealed is not None and row[x] == Visibility.UNSEEN:
                            newly_revealed.add((x, y))
                        row[x] = VISIBLE
            self._currently_visible = []
            return newly_revealed if return_new_reveals else None

        # Demote last frame's visible tiles to SEEN (without scanning the whole map).
        for (x, y) in self._currently_visible:
            if 0 <= x < w and 0 <= y < h:
                if vis[y][x] == VISIBLE:
                    vis[y][x] = SEEN
        self._currently_visible = []

        for world_x, world_y, radius_tiles in revealers:
            gx, gy = self.world_to_grid(world_x, world_y)
            if return_new_reveals:
                self._reveal_circle(gx, gy, int(radius_tiles), newly_revealed=newly_revealed)
            else:
                self._reveal_circle(gx, gy, int(radius_tiles))

        return newly_revealed if return_new_reveals else None

    # ------------------------------------------------------------------
    # WK57 Wave 4: Underground fog of war
    # ------------------------------------------------------------------

    def init_underground_fog(self, area):
        """Create a fresh UNSEEN visibility grid for an underground area."""
        grid = [[Visibility.UNSEEN for _ in range(area.total_width)]
                for _ in range(area.total_height)]
        self.underground_visibility[area.area_id] = grid

    def reveal_underground_circle(self, area_id, local_x, local_z, radius):
        """Reveal underground fog in a circle around (local_x, local_z)."""
        grid = self.underground_visibility.get(area_id)
        if grid is None:
            return
        h = len(grid)
        w = len(grid[0]) if h > 0 else 0
        r2 = radius * radius
        for dz in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dz * dz <= r2:
                    gz = local_z + dz
                    gx = local_x + dx
                    if 0 <= gz < h and 0 <= gx < w:
                        grid[gz][gx] = Visibility.VISIBLE

