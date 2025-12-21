"""
World and tile map system.
"""
import pygame
import math
from config import (
    TILE_SIZE, MAP_WIDTH, MAP_HEIGHT,
    COLOR_GRASS, COLOR_WATER, COLOR_PATH, COLOR_TREE
)
from game.graphics.tile_sprites import TileSpriteLibrary
from game.sim.determinism import get_rng


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
BLOCKING_TILES = {TileType.WATER, TileType.TREE}


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
        self.generate_terrain()

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
                # Add scattered trees
                elif rng.random() < 0.06:
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
        return tile not in BLOCKING_TILES
    
    def is_buildable(self, x: int, y: int, width: int = 1, height: int = 1) -> bool:
        """Check if an area can have a building placed on it."""
        for dy in range(height):
            for dx in range(width):
                tile = self.get_tile(x + dx, y + dy)
                if tile in BLOCKING_TILES:
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

    def _reveal_circle(self, grid_cx: int, grid_cy: int, radius_tiles: int):
        """Mark tiles within a circle as VISIBLE."""
        r = max(0, int(radius_tiles))
        if r <= 0:
            if 0 <= grid_cx < self.width and 0 <= grid_cy < self.height:
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
                row[x] = Visibility.VISIBLE
                self._currently_visible.add((x, y))

    def update_visibility(self, revealers: list[tuple[float, float, int]]):
        """
        Update the fog-of-war based on a set of revealers.

        `revealers`: list of (world_x, world_y, radius_tiles).
        """
        # Demote last frame's visible tiles to SEEN (without scanning the whole map).
        for (x, y) in self._currently_visible:
            if 0 <= x < self.width and 0 <= y < self.height:
                if self.visibility[y][x] == Visibility.VISIBLE:
                    self.visibility[y][x] = Visibility.SEEN
        self._currently_visible.clear()

        for world_x, world_y, radius_tiles in revealers:
            gx, gy = self.world_to_grid(world_x, world_y)
            self._reveal_circle(gx, gy, int(radius_tiles))

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

