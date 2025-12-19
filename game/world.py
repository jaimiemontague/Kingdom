"""
World and tile map system.
"""
import pygame
import random
from config import (
    TILE_SIZE, MAP_WIDTH, MAP_HEIGHT,
    COLOR_GRASS, COLOR_WATER, COLOR_PATH, COLOR_TREE
)
from game.graphics.tile_sprites import TileSpriteLibrary


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


class World:
    """Manages the game world tile map."""
    
    def __init__(self):
        self.width = MAP_WIDTH
        self.height = MAP_HEIGHT
        self.tiles = [[TileType.GRASS for _ in range(self.width)] for _ in range(self.height)]
        self.generate_terrain()
        
    def generate_terrain(self):
        """Generate a simple procedural terrain."""
        # Add some water (a pond/lake)
        lake_x = random.randint(self.width // 4, self.width * 3 // 4)
        lake_y = random.randint(self.height // 4, self.height * 3 // 4)
        # Scale lake size with map size so large maps don't look empty.
        base = max(3, min(self.width, self.height) // 25)
        lake_radius = random.randint(base, base + 4)
        
        for y in range(self.height):
            for x in range(self.width):
                # Create lake
                dist = ((x - lake_x) ** 2 + (y - lake_y) ** 2) ** 0.5
                if dist < lake_radius:
                    self.tiles[y][x] = TileType.WATER
                # Add scattered trees
                elif random.random() < 0.06:
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

