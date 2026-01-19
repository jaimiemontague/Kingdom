"""
Castle-driven Build Catalog panel (WK7).

Centered modal catalog showing all placeable buildings with thumbnails, name, cost, hotkey.
Click-to-place functionality.
"""
from __future__ import annotations

import pygame
from game.ui.widgets import ModalPanel, NineSlice
from game.ui.theme import UITheme
from game.graphics.font_cache import get_font
from config import (
    BUILDING_COSTS, BUILDING_COLORS, BUILDING_SIZES,
    BUILDING_PREREQUISITES, BUILDING_CONSTRAINTS,
    COLOR_WHITE, COLOR_RED, COLOR_GREEN, COLOR_UI_BG, COLOR_UI_BORDER
)


# Hotkey mapping for building types
BUILDING_HOTKEYS = {
    "warrior_guild": "1",
    "marketplace": "2",
    "ranger_guild": "3",
    "rogue_guild": "4",
    "wizard_guild": "5",
    "blacksmith": "6",
    "inn": "7",
    "trading_post": "8",
    "temple_agrela": "T",
    "gnome_hovel": "G",
    "elven_bungalow": "E",
    "dwarven_settlement": "V",
    "guardhouse": "U",
    "ballista_tower": "Y",
    "wizard_tower": "O",
    "fairgrounds": "F",
    "library": "I",
    "royal_gardens": "R",
}


class BuildCatalogPanel:
    """Centered modal catalog for selecting buildings to place."""
    
    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.visible = False
        self.theme = UITheme()
        self._panel_tex_modal = "assets/ui/kingdomsim_ui_cc0/panels/panel_modal.png"
        self._button_tex_normal = "assets/ui/kingdomsim_ui_cc0/buttons/button_normal.png"
        self._button_tex_hover = "assets/ui/kingdomsim_ui_cc0/buttons/button_hover.png"
        self._button_slice_border = 6
        
        # Modal panel
        self.modal = ModalPanel(
            screen_width=screen_width,
            screen_height=screen_height,
            panel_width=560,
            panel_height=620,
            texture_path=self._panel_tex_modal,
            slice_border=8,
        )
        
        # Get list of placeable buildings (exclude castle, palace, auto-spawn)
        self.placeable_buildings = [
            "warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild",
            "marketplace", "blacksmith", "inn", "trading_post",
            "temple_agrela", "gnome_hovel", "elven_bungalow", "dwarven_settlement",
            "guardhouse", "ballista_tower", "wizard_tower",
            "fairgrounds", "library", "royal_gardens"
        ]
        
        # Grid layout
        self.cols = 3
        self.thumbnail_size = 48
        self.row_height = 72
        self.padding = 10
        
        # Track hovered building
        self.hovered_building = None
    
    def open(self):
        """Open the catalog."""
        self.visible = True
        self.hovered_building = None
    
    def close(self):
        """Close the catalog."""
        self.visible = False
        self.hovered_building = None

    def on_resize(self, screen_width: int, screen_height: int):
        """Update modal sizing after a window resize."""
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        self.modal.screen_width = self.screen_width
        self.modal.screen_height = self.screen_height
        # Clear cached backdrop so it matches new size
        self.modal._backdrop_cache = None
    
    def _get_building_availability(self, building_type: str, economy, buildings: list) -> tuple[bool, str]:
        """Check if building is available (affordable, prerequisites met, no conflicts)."""
        # Check affordability
        cost = BUILDING_COSTS.get(building_type, 0)
        if economy.player_gold < cost:
            return False, f"Need ${cost} (have ${economy.player_gold})"
        
        # Check prerequisites
        prereqs = BUILDING_PREREQUISITES.get(building_type, [])
        for prereq in prereqs:
            if not any(b.building_type == prereq for b in buildings):
                prereq_name = prereq.replace("_", " ").title()
                return False, f"Requires: {prereq_name}"
        
        # Check constraints (conflicts)
        constraints = BUILDING_CONSTRAINTS.get(building_type, [])
        for constraint in constraints:
            if any(b.building_type == constraint for b in buildings):
                constraint_name = constraint.replace("_", " ").title()
                return False, f"Cannot build: {constraint_name} exists"
        
        return True, ""
    
    def _get_building_rect(self, index: int) -> pygame.Rect:
        """Get rectangle for building at index in grid layout."""
        panel_rect = self.modal.get_panel_rect()
        col = index % self.cols
        row = index // self.cols
        
        x = panel_rect.x + self.padding + col * (panel_rect.width // self.cols)
        y = panel_rect.y + 52 + row * self.row_height
        
        return pygame.Rect(x, y, panel_rect.width // self.cols - self.padding * 2, self.row_height - self.padding)
    
    def handle_click(self, pos: tuple[int, int], economy, buildings: list) -> str | None:
        """
        Handle mouse click.
        Returns building_type string if clicked on available building, None otherwise.
        """
        if not self.visible:
            return None
        
        # Check close button (top-right)
        panel_rect = self.modal.get_panel_rect()
        close_rect = pygame.Rect(panel_rect.right - 30, panel_rect.y + 10, 20, 20)
        if close_rect.collidepoint(pos):
            self.close()
            return None
        
        # Check building grid
        for i, building_type in enumerate(self.placeable_buildings):
            rect = self._get_building_rect(i)
            if rect.collidepoint(pos):
                available, reason = self._get_building_availability(building_type, economy, buildings)
                if available:
                    self.close()
                    return building_type
        
        return None
    
    def update_hover(self, pos: tuple[int, int]):
        """Update hovered building."""
        if not self.visible:
            self.hovered_building = None
            return
        
        self.hovered_building = None
        for i, building_type in enumerate(self.placeable_buildings):
            rect = self._get_building_rect(i)
            if rect.collidepoint(pos):
                self.hovered_building = (i, building_type)
                break
    
    def render(self, surface: pygame.Surface, economy, buildings: list):
        """Render the catalog."""
        if not self.visible:
            return
        
        # Backdrop
        self.modal.render_backdrop(surface)
        
        # Panel
        self.modal.render_panel(surface)
        panel_rect = self.modal.get_panel_rect()
        
        # Title
        title = self.theme.font_title.render("Build Buildings", True, self.theme.text)
        title_x = panel_rect.centerx - title.get_width() // 2
        surface.blit(title, (title_x, panel_rect.y + 16))
        
        # Close button (X)
        close_rect = pygame.Rect(panel_rect.right - 30, panel_rect.y + 10, 20, 20)
        close_bg = (70, 70, 80) if close_rect.collidepoint(pygame.mouse.get_pos()) else (50, 50, 60)
        if not NineSlice.render(surface, close_rect, self._button_tex_hover if close_rect.collidepoint(pygame.mouse.get_pos()) else self._button_tex_normal, border=self._button_slice_border):
            pygame.draw.rect(surface, close_bg, close_rect)
            pygame.draw.rect(surface, self.theme.panel_border, close_rect, 1)
        close_x = self.theme.font_small.render("X", True, self.theme.text)
        surface.blit(close_x, (close_rect.centerx - close_x.get_width() // 2, close_rect.centery - close_x.get_height() // 2))
        
        # Building grid
        for i, building_type in enumerate(self.placeable_buildings):
            rect = self._get_building_rect(i)
            available, reason = self._get_building_availability(building_type, economy, buildings)
            is_hovered = (self.hovered_building and self.hovered_building[0] == i)
            
            # Row background
            bg_color = (60, 60, 70) if is_hovered else (45, 45, 55)
            if not available:
                bg_color = (40, 30, 30)  # Darker red tint for unavailable
            pygame.draw.rect(surface, bg_color, rect)
            pygame.draw.rect(surface, self.theme.panel_border, rect, 1)
            
            # Thumbnail (colored swatch for now; can be replaced with sprite later)
            thumb_x = rect.x + 8
            thumb_y = rect.y + (rect.height - self.thumbnail_size) // 2
            thumb_rect = pygame.Rect(thumb_x, thumb_y, self.thumbnail_size, self.thumbnail_size)
            building_color = BUILDING_COLORS.get(building_type, (100, 100, 100))
            if not available:
                building_color = tuple(c // 2 for c in building_color)  # Darken unavailable
            pygame.draw.rect(surface, building_color, thumb_rect)
            pygame.draw.rect(surface, (200, 200, 220), thumb_rect, 2)
            
            # Building name
            name = building_type.replace("_", " ").title()
            name_text = self.theme.font_body.render(name, True, self.theme.text if available else (150, 100, 100))
            surface.blit(name_text, (thumb_x + self.thumbnail_size + 12, rect.y + 8))
            
            # Cost and hotkey
            cost = BUILDING_COSTS.get(building_type, 0)
            hotkey = BUILDING_HOTKEYS.get(building_type, "")
            info_text = f"${cost}"
            if hotkey:
                info_text += f" • [{hotkey}]"
            cost_color = COLOR_GREEN if available else COLOR_RED
            info_surf = self.theme.font_small.render(info_text, True, cost_color)
            surface.blit(info_surf, (thumb_x + self.thumbnail_size + 12, rect.y + 28))
            
            # Availability reason (if unavailable)
            if not available and reason:
                reason_surf = self.theme.font_small.render(reason, True, (200, 150, 150))
                surface.blit(reason_surf, (thumb_x + self.thumbnail_size + 12, rect.y + 44))
