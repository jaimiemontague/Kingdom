"""
Building placement menu and preview.
"""
import pygame
from config import (
    TILE_SIZE, BUILDING_SIZES, BUILDING_COLORS, BUILDING_COSTS,
    COLOR_WHITE, COLOR_RED, COLOR_GREEN
)


class BuildingMenu:
    """Handles building selection and placement preview."""
    
    def __init__(self):
        self.selected_building = None
        self.preview_valid = False
        self.preview_grid_pos = (0, 0)
        
    def select_building(self, building_type: str):
        """Select a building type for placement."""
        self.selected_building = building_type
        
    def cancel_selection(self):
        """Cancel building selection."""
        self.selected_building = None
        
    def update_preview(self, mouse_pos: tuple, world, buildings: list, camera_offset: tuple):
        """Update the preview position based on mouse."""
        if not self.selected_building:
            return
        
        cam_x, cam_y = camera_offset
        world_x = mouse_pos[0] + cam_x
        world_y = mouse_pos[1] + cam_y
        
        # Snap to grid
        grid_x = int(world_x // TILE_SIZE)
        grid_y = int(world_y // TILE_SIZE)
        
        self.preview_grid_pos = (grid_x, grid_y)
        
        # Check if placement is valid
        size = BUILDING_SIZES.get(self.selected_building, (1, 1))
        self.preview_valid = self.can_place(grid_x, grid_y, size, world, buildings)
        
    def can_place(self, grid_x: int, grid_y: int, size: tuple, world, buildings: list) -> bool:
        """Check if a building can be placed at the given position."""
        # Check world bounds and terrain
        if not world.is_buildable(grid_x, grid_y, size[0], size[1]):
            return False
        
        # Check overlap with existing buildings
        for building in buildings:
            for dx in range(size[0]):
                for dy in range(size[1]):
                    if building.occupies_tile(grid_x + dx, grid_y + dy):
                        return False
        
        return True
    
    def get_placement(self) -> tuple:
        """Get the current preview position for placement."""
        if self.selected_building and self.preview_valid:
            return self.preview_grid_pos
        return None
    
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        """Render the building preview."""
        if not self.selected_building:
            return
        
        size = BUILDING_SIZES.get(self.selected_building, (1, 1))
        color = BUILDING_COLORS.get(self.selected_building, (128, 128, 128))
        
        cam_x, cam_y = camera_offset
        grid_x, grid_y = self.preview_grid_pos
        screen_x = grid_x * TILE_SIZE - cam_x
        screen_y = grid_y * TILE_SIZE - cam_y
        
        width = size[0] * TILE_SIZE
        height = size[1] * TILE_SIZE
        
        # Create semi-transparent surface
        preview_surf = pygame.Surface((width, height), pygame.SRCALPHA)
        
        # Fill with building color (semi-transparent)
        if self.preview_valid:
            preview_color = (*color, 150)
            border_color = COLOR_GREEN
        else:
            preview_color = (*COLOR_RED[:3], 150)
            border_color = COLOR_RED
        
        pygame.draw.rect(preview_surf, preview_color, (0, 0, width, height))
        pygame.draw.rect(preview_surf, border_color, (0, 0, width, height), 2)
        
        surface.blit(preview_surf, (screen_x, screen_y))
        
        # Draw cost
        cost = BUILDING_COSTS.get(self.selected_building, 0)
        font = pygame.font.Font(None, 20)
        cost_text = font.render(f"${cost}", True, COLOR_WHITE)
        surface.blit(cost_text, (screen_x + 5, screen_y + height + 5))

