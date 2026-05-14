"""
World and tile map system.
"""
import pygame
import math
from config import (
    TILE_SIZE, MAP_WIDTH, MAP_HEIGHT,
    COLOR_GRASS, COLOR_WATER, COLOR_PATH, COLOR_TREE,
)
from game.graphics.tile_sprites import TileSpriteLibrary
from game.sim.determinism import get_rng
from game.world_zones import get_zone_blend

try:
    from noise import pnoise2 as _pnoise2
except ImportError:
    _pnoise2 = None


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
        self.generate_terrain()

        # WK53 Wave 2: heightmap for terrain elevation (generated after flat tiles).
        self.heightmap: list[list[float]] | None = None
        self.heightmap_grid_w: int = 0
        self.heightmap_grid_h: int = 0
        self.generate_heightmap()

        # Fog-of-war visibility grid (tile-based).
        # UNSEEN: never revealed; SEEN: explored but not currently visible; VISIBLE: in vision now.
        self.visibility = [[Visibility.UNSEEN for _ in range(self.width)] for _ in range(self.height)]
        self._currently_visible = set()  # set[(x, y)] currently marked as VISIBLE (so we can demote efficiently)

        # Reusable fog tile overlays (avoid per-tile Surface allocations).
        self._fog_tile_unseen = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        self._fog_tile_unseen.fill((0, 0, 0, 255))
        self._fog_tile_seen = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        self._fog_tile_seen.fill((0, 0, 0, 170))
        
    def generate_terrain(self):
        """Generate a simple procedural terrain."""
        # Add some water (a pond/lake)
        rng = getattr(self, "rng", get_rng("world_gen"))
        lake_x = rng.randint(self.width // 4, self.width * 3 // 4)
        lake_y = rng.randint(self.height // 4, self.height * 3 // 4)
        # Scale lake size with map size so large maps don't look empty.
        base = max(3, min(self.width, self.height) // 25)
        lake_radius = rng.randint(base, base + 4)
        
        for y in range(self.height):
            for x in range(self.width):
                # Create lake
                dist = ((x - lake_x) ** 2 + (y - lake_y) ** 2) ** 0.5
                if dist < lake_radius:
                    self.tiles[y][x] = TileType.WATER

        # WK44: clustered forests (not per-tile independent noise)
        # Deterministic blobs: pick a handful of centers then spray points with jitter.
        # Target: noticeably forested maps (avoid barren look) while leaving plenty of buildable space.
        area = int(self.width) * int(self.height)
        cluster_count = max(22, area // 900)
        castle_cx, castle_cy = self.width // 2, self.height // 2
        for _ in range(int(cluster_count)):
            cx = rng.randint(0, self.width - 1)
            cy = rng.randint(0, self.height - 1)
            if self.tiles[cy][cx] == TileType.WATER:
                continue
            radius = rng.randint(5, 12)
            # WK54: zone-influenced tree density
            zone, blend = get_zone_blend(cx, cy, castle_cx, castle_cy)
            tree_mult = 1.0
            if zone is not None:
                tree_mult = 1.0 + (zone.terrain_bias.get("tree_density", 1.0) - 1.0) * blend
            points = int(rng.randint(90, 220) * tree_mult)
            for _k in range(points):
                dx = rng.randint(-radius, radius)
                dy = rng.randint(-radius, radius)
                x = cx + dx
                y = cy + dy
                if not (0 <= x < self.width and 0 <= y < self.height):
                    continue
                if self.tiles[y][x] == TileType.WATER:
                    continue
                # Slight falloff to keep clusters organic.
                if (dx * dx + dy * dy) > (radius * radius):
                    continue
                if rng.random() < 0.92:
                    self.tiles[y][x] = TileType.TREE

        # Light background sprinkle to connect clusters (keeps edges from feeling empty).
        # WK54: zone-influenced sprinkle probability
        for y in range(self.height):
            for x in range(self.width):
                if self.tiles[y][x] != TileType.GRASS:
                    continue
                zone_s, blend_s = get_zone_blend(x, y, castle_cx, castle_cy)
                sprinkle_mult = 1.0
                if zone_s is not None:
                    sprinkle_mult = 1.0 + (zone_s.terrain_bias.get("tree_density", 1.0) - 1.0) * blend_s
                if rng.random() < 0.045 * sprinkle_mult:
                    self.tiles[y][x] = TileType.TREE
        
        # Create paths from edges to center
        center_x, center_y = self.width // 2, self.height // 2
        
        # Horizontal path
        for x in range(self.width):
            self.tiles[center_y][x] = TileType.PATH
            if center_y + 1 < self.height:
                self.tiles[center_y + 1][x] = TileType.PATH
        
        # Vertical path
        for y in range(self.height):
            self.tiles[y][center_x] = TileType.PATH
            if center_x + 1 < self.width:
                self.tiles[y][center_x + 1] = TileType.PATH

        # WK45: trim excess TREE tiles AFTER carving paths (paths erase lots of trees along the cross).
        # Target ~600 visible forest tiles at match start; sapling spawning uses a separate total cap.
        # WK54: scale tree cap proportionally with map area (750 for 150x150, ~2083 for 250x250).
        max_starting_trees = max(750, int(area * 750 / (150 * 150)))
        tree_tiles: list[tuple[int, int]] = []
        for ty in range(self.height):
            row = self.tiles[ty]
            for tx in range(self.width):
                if row[tx] == TileType.TREE:
                    tree_tiles.append((tx, ty))
        if len(tree_tiles) > max_starting_trees:
            rng.shuffle(tree_tiles)
            for tx, ty in tree_tiles[max_starting_trees:]:
                if self.tiles[ty][tx] == TileType.TREE:
                    self.tiles[ty][tx] = TileType.GRASS
    
    def generate_heightmap(self) -> None:
        """WK53 Wave 2: Generate a Perlin-noise heightmap at 2x sub-tile resolution.

        Fence-post pattern: for an NxM tile map the grid is (2*N+1) x (2*M+1).
        The castle starting area is flattened to a gentle plateau with cosine falloff.
        Water tiles are clamped to TERRAIN_WATER_LEVEL.
        """
        if _pnoise2 is None:
            # noise package unavailable — leave heightmap as None (flat terrain).
            return

        import config as cfg

        tw, th = int(self.width), int(self.height)
        gw = tw * 2 + 1
        gh = th * 2 + 1
        self.heightmap_grid_w = gw
        self.heightmap_grid_h = gh

        height_scale = float(getattr(cfg, "TERRAIN_HEIGHT_SCALE", 8.0))
        hill_freq = float(getattr(cfg, "TERRAIN_HILL_FREQUENCY", 0.04))
        mtn_freq = float(getattr(cfg, "TERRAIN_MOUNTAIN_FREQUENCY", 0.10))
        detail_freq = float(getattr(cfg, "TERRAIN_DETAIL_FREQUENCY", 0.25))
        water_level = float(getattr(cfg, "TERRAIN_WATER_LEVEL", 1.0))
        flat_radius = float(getattr(cfg, "TERRAIN_CASTLE_FLAT_RADIUS", 5))

        seed = int(getattr(cfg, "SIM_SEED", 1))

        # Castle center in grid coords (castle is placed at MAP_WIDTH//2-1, MAP_HEIGHT//2-1).
        castle_gx = tw // 2 - 1
        castle_gy = th // 2 - 1
        # In heightmap grid space (2x resolution):
        castle_hx = castle_gx * 2 + 1  # center of castle footprint (3x3) offset
        castle_hz = castle_gy * 2 + 1
        flat_radius_grid = flat_radius * 2.0  # convert tile-radius to grid-radius

        # WK53 R3: flatness exponent — pushes low-to-mid noise toward zero (flat ground)
        # while preserving peaks. Values > 1.0 create more flat terrain; 2.5 gives ~60-70%
        # flat map with distinct hill features rising where noise is strongest.
        flatness_exp = float(getattr(cfg, "TERRAIN_FLATNESS_EXPONENT", 2.5))

        # Generate raw Perlin noise heightmap
        hmap: list[list[float]] = []
        for gz in range(gh):
            row: list[float] = []
            for gx in range(gw):
                # Sample Perlin noise at three octaves
                x_sample = float(gx) / 2.0  # convert back to tile-space for frequency
                z_sample = float(gz) / 2.0
                n = 0.0
                n += 1.0 * _pnoise2(
                    x_sample * hill_freq, z_sample * hill_freq,
                    base=seed,
                )
                n += 0.4 * _pnoise2(
                    x_sample * mtn_freq, z_sample * mtn_freq,
                    base=seed + 1,
                )
                n += 0.15 * _pnoise2(
                    x_sample * detail_freq, z_sample * detail_freq,
                    base=seed + 2,
                )
                # pnoise2 returns roughly [-1, 1]; remap to [0, 1]
                raw_01 = (n + 1.0) * 0.5
                raw_01 = max(0.0, min(1.0, raw_01))
                # WK53 R3: Apply flatness bias — power curve compresses low values
                # toward zero (flat) while preserving peaks. This makes ~60-70% of
                # the map relatively flat with hills as distinct features.
                biased = pow(raw_01, flatness_exp)
                h = biased * height_scale
                h = max(0.0, min(height_scale, h))
                row.append(h)
            hmap.append(row)

        # WK54: Zone-influenced elevation biases (applied before castle flattening
        # so the flat plateau overrides any zone elevation changes).
        try:
            from game.graphics.terrain_height import apply_zone_elevation
            apply_zone_elevation(hmap, gw, gh, tw, th, castle_gx, castle_gy)
        except (ImportError, AttributeError):
            pass  # Zone elevation not yet available

        # Castle flattening: average height across footprint, then gentle cosine falloff
        # Sample average height across the castle's 3×3 footprint (6×6 grid cells)
        castle_footprint_samples = []
        for fz in range(castle_hz - 3, castle_hz + 4):
            for fx in range(castle_hx - 3, castle_hx + 4):
                if 0 <= fx < gw and 0 <= fz < gh:
                    castle_footprint_samples.append(hmap[fz][fx])
        castle_h = sum(castle_footprint_samples) / len(castle_footprint_samples) if castle_footprint_samples else hmap[castle_hz][castle_hx]

        for gz in range(gh):
            for gx in range(gw):
                dx = gx - castle_hx
                dz = gz - castle_hz
                dist = math.sqrt(dx * dx + dz * dz)
                if dist < flat_radius_grid:
                    t = dist / flat_radius_grid
                    blend = 0.5 * (1.0 + math.cos(t * math.pi))
                    hmap[gz][gx] = hmap[gz][gx] * (1.0 - blend) + castle_h * blend

        # Water tile clamping: clamp heightmap samples that fall on water tiles
        for gz in range(gh):
            tile_z = min(th - 1, gz // 2)
            for gx in range(gw):
                tile_x = min(tw - 1, gx // 2)
                if self.tiles[tile_z][tile_x] == TileType.WATER:
                    hmap[gz][gx] = water_level

        self.heightmap = hmap

    def flatten_building_footprints(self, buildings):
        """Flatten terrain under all placed buildings/lairs.

        Called after buildings are placed during world generation.
        buildings: iterable of objects with grid_x, grid_y, and size (w, h) attributes.
        """
        if self.heightmap is None:
            return
        try:
            from game.graphics.terrain_height import flatten_footprint
        except (ImportError, AttributeError):
            return  # flatten_footprint not yet available
        for b in buildings:
            w, h = getattr(b, 'size', (1, 1))
            if isinstance(w, (list, tuple)):
                w, h = w[0], w[1]
            flatten_footprint(
                self.heightmap, self.heightmap_grid_w, self.heightmap_grid_h,
                int(getattr(b, 'grid_x', 0)), int(getattr(b, 'grid_y', 0)),
                int(w), int(h),
            )

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
    
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        """Render the tile map."""
        cam_x, cam_y = camera_offset
        
        # Calculate visible tile range
        start_x = max(0, int(cam_x // TILE_SIZE))
        start_y = max(0, int(cam_y // TILE_SIZE))
        end_x = min(self.width, int((cam_x + surface.get_width()) // TILE_SIZE) + 1)
        end_y = min(self.height, int((cam_y + surface.get_height()) // TILE_SIZE) + 1)
        
        for y in range(start_y, end_y):
            for x in range(start_x, end_x):
                tile_type = self.tiles[y][x]

                screen_x = int(x * TILE_SIZE - cam_x)
                screen_y = int(y * TILE_SIZE - cam_y)

                # Pixel-art sprites (procedural fallback) for tiles.
                tile_img = TileSpriteLibrary.get(tile_type, x, y, size=TILE_SIZE)
                if tile_img is not None:
                    surface.blit(tile_img, (screen_x, screen_y))
                else:
                    # Safety fallback (shouldn't normally happen)
                    color = TILE_COLORS.get(tile_type, COLOR_GRASS)
                    pygame.draw.rect(surface, color, (screen_x, screen_y, TILE_SIZE, TILE_SIZE))

    def _reveal_circle(self, grid_cx: int, grid_cy: int, radius_tiles: int, newly_revealed: set = None):
        """
        Mark tiles within a circle as VISIBLE.
        
        Args:
            grid_cx, grid_cy: Center grid coordinates
            radius_tiles: Vision radius in tiles
            newly_revealed: Optional set to populate with (grid_x, grid_y) tiles that transitioned UNSEEN -> VISIBLE
        """
        r = max(0, int(radius_tiles))
        if r <= 0:
            if 0 <= grid_cx < self.width and 0 <= grid_cy < self.height:
                # WK6: Track UNSEEN -> VISIBLE transitions
                if newly_revealed is not None and self.visibility[grid_cy][grid_cx] == Visibility.UNSEEN:
                    newly_revealed.add((grid_cx, grid_cy))
                self.visibility[grid_cy][grid_cx] = Visibility.VISIBLE
                self._currently_visible.add((grid_cx, grid_cy))
            return

        y0 = max(0, grid_cy - r)
        y1 = min(self.height - 1, grid_cy + r)
        r2 = r * r
        for y in range(y0, y1 + 1):
            dy = y - grid_cy
            dx_max = int(math.sqrt(max(0, r2 - (dy * dy))))
            x0 = max(0, grid_cx - dx_max)
            x1 = min(self.width - 1, grid_cx + dx_max)
            row = self.visibility[y]
            for x in range(x0, x1 + 1):
                # WK6: Track UNSEEN -> VISIBLE transitions
                if newly_revealed is not None and row[x] == Visibility.UNSEEN:
                    newly_revealed.add((x, y))
                row[x] = Visibility.VISIBLE
                self._currently_visible.add((x, y))

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
        
        # Demote last frame's visible tiles to SEEN (without scanning the whole map).
        for (x, y) in self._currently_visible:
            if 0 <= x < self.width and 0 <= y < self.height:
                if self.visibility[y][x] == Visibility.VISIBLE:
                    self.visibility[y][x] = Visibility.SEEN
        self._currently_visible.clear()

        for world_x, world_y, radius_tiles in revealers:
            gx, gy = self.world_to_grid(world_x, world_y)
            if return_new_reveals:
                # Track which tiles transition UNSEEN -> VISIBLE
                self._reveal_circle(gx, gy, int(radius_tiles), newly_revealed=newly_revealed)
            else:
                self._reveal_circle(gx, gy, int(radius_tiles))
        
        return newly_revealed if return_new_reveals else None

    def render_fog(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        """Render fog-of-war overlay over the currently-visible screen region."""
        cam_x, cam_y = camera_offset

        start_x = max(0, int(cam_x // TILE_SIZE))
        start_y = max(0, int(cam_y // TILE_SIZE))
        end_x = min(self.width, int((cam_x + surface.get_width()) // TILE_SIZE) + 1)
        end_y = min(self.height, int((cam_y + surface.get_height()) // TILE_SIZE) + 1)

        for y in range(start_y, end_y):
            vis_row = self.visibility[y]
            for x in range(start_x, end_x):
                state = vis_row[x]
                if state == Visibility.VISIBLE:
                    continue

                screen_x = x * TILE_SIZE - cam_x
                screen_y = y * TILE_SIZE - cam_y

                if state == Visibility.UNSEEN:
                    surface.blit(self._fog_tile_unseen, (screen_x, screen_y))
                else:
                    surface.blit(self._fog_tile_seen, (screen_x, screen_y))

