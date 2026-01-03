"""
Building selection list panel for Build menu.
"""
import pygame
from game.ui.theme import UITheme
from game.ui.widgets import Panel
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


class BuildingListPanel:
    """Clickable panel listing all placeable buildings."""
    
    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.visible = False
        self.theme = UITheme()
        
        # Panel dimensions
        self.panel_width = 420
        self.max_height = 600
        self.panel_x = 50  # Center-left positioning
        self.panel_y = 150
        
        # Row dimensions
        self.row_height = 50
        self.row_padding = 8
        self.icon_size = 32
        
        # Fonts
        self.font_title = get_font(24)
        self.font_body = get_font(20)
        self.font_small = get_font(16)
        
        # Track hovered row
        self.hovered_row = None
        
        # Cached surfaces (per-frame caching)
        self._header_cache = None
        self._footer_cache = None
        self._row_caches = {}  # building_type -> (normal_surf, hover_surf, disabled_surf)
        
        # Get list of placeable buildings (exclude castle, palace, auto-spawn)
        self.placeable_buildings = [
            "warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild",
            "marketplace", "blacksmith", "inn", "trading_post",
            "temple_agrela", "gnome_hovel", "elven_bungalow", "dwarven_settlement",
            "guardhouse", "ballista_tower", "wizard_tower",
            "fairgrounds", "library", "royal_gardens"
        ]
    
    def toggle(self):
        """Toggle panel visibility."""
        self.visible = not self.visible
        if not self.visible:
            self.hovered_row = None
    
    def close(self):
        """Close the panel."""
        self.visible = False
        self.hovered_row = None
    
    def _get_building_availability(self, building_type: str, economy, buildings: list) -> tuple[bool, str]:
        """
        Check if a building is available.
        Returns (is_available, reason_string).
        """
        # Check affordability
        cost = BUILDING_COSTS.get(building_type, 0)
        if economy.player_gold < cost:
            return (False, "Cannot afford")
        
        # Check prerequisites
        if building_type in BUILDING_PREREQUISITES:
            required = BUILDING_PREREQUISITES[building_type]
            has_prereq = False
            for building in buildings:
                if building.building_type in required and getattr(building, "is_constructed", False):
                    has_prereq = True
                    break
            if not has_prereq:
                req_names = ", ".join(b.replace("_", " ").title() for b in required)
                return (False, f"Requires: {req_names}")
        
        # Check constraints (mutually exclusive)
        if building_type in BUILDING_CONSTRAINTS:
            excluded = BUILDING_CONSTRAINTS[building_type]
            for building in buildings:
                if building.building_type in excluded:
                    excl_name = building.building_type.replace("_", " ").title()
                    return (False, f"Cannot build: {excl_name} exists")
        
        return (True, "")
    
    def handle_click(self, mouse_pos: tuple[int, int], economy, buildings: list) -> str | None:
        """
        Handle mouse click on panel.
        Returns building_type if a row was clicked, None otherwise.
        """
        if not self.visible:
            return None
        
        # Check if click is within panel
        panel_rect = pygame.Rect(self.panel_x, self.panel_y, self.panel_width, self._get_panel_height())
        if not panel_rect.collidepoint(mouse_pos):
            return None
        
        # Check header/footer clicks (no-op, but consume click)
        header_height = 40
        footer_height = 30
        content_y = self.panel_y + header_height
        content_height = self._get_panel_height() - header_height - footer_height
        
        if mouse_pos[1] < content_y or mouse_pos[1] >= content_y + content_height:
            return None  # Clicked header or footer
        
        # Find clicked row
        rel_y = mouse_pos[1] - content_y
        row_index = int(rel_y // self.row_height)
        
        if 0 <= row_index < len(self.placeable_buildings):
            building_type = self.placeable_buildings[row_index]
            is_available, _ = self._get_building_availability(building_type, economy, buildings)
            if is_available:
                return building_type
        
        return None
    
    def update_hover(self, mouse_pos: tuple[int, int], economy, buildings: list):
        """Update hovered row state."""
        if not self.visible:
            self.hovered_row = None
            return
        
        panel_rect = pygame.Rect(self.panel_x, self.panel_y, self.panel_width, self._get_panel_height())
        if not panel_rect.collidepoint(mouse_pos):
            self.hovered_row = None
            return
        
        header_height = 40
        content_y = self.panel_y + header_height
        rel_y = mouse_pos[1] - content_y
        
        if rel_y < 0:
            self.hovered_row = None
            return
        
        row_index = int(rel_y // self.row_height)
        if 0 <= row_index < len(self.placeable_buildings):
            building_type = self.placeable_buildings[row_index]
            is_available, _ = self._get_building_availability(building_type, economy, buildings)
            if is_available:
                self.hovered_row = building_type
            else:
                self.hovered_row = None
        else:
            self.hovered_row = None
    
    def _get_panel_height(self) -> int:
        """Calculate panel height based on number of buildings."""
        header_height = 40
        footer_height = 30
        content_height = len(self.placeable_buildings) * self.row_height
        total = header_height + content_height + footer_height
        return min(total, self.max_height)
    
    def render(self, surface: pygame.Surface, economy, buildings: list, selected_building_type: str | None = None):
        """Render the building list panel."""
        if not self.visible:
            return
        
        panel_height = self._get_panel_height()
        panel_rect = pygame.Rect(self.panel_x, self.panel_y, self.panel_width, panel_height)
        
        # Render panel background using UITheme styling
        panel = Panel(
            rect=panel_rect,
            bg_rgb=COLOR_UI_BG,
            border_rgb=COLOR_UI_BORDER,
            alpha=235,
            border_w=2,
            inner_border_rgb=(0x50, 0x50, 0x64),
            inner_border_w=1,
            highlight_rgb=(0x6B, 0x6B, 0x84),
            highlight_w=1
        )
        panel.render(surface)
        
        # Render header
        header_y = self.panel_y + 10
        if self._header_cache is None:
            header_text = self.font_title.render("Select Building", True, COLOR_WHITE)
            self._header_cache = header_text
        surface.blit(self._header_cache, (self.panel_x + 15, header_y))
        
        # Render footer hint
        footer_y = self.panel_y + panel_height - 25
        if self._footer_cache is None:
            footer_text = self.font_small.render("ESC to close | Click building to place", True, (180, 180, 180))
            self._footer_cache = footer_text
        surface.blit(self._footer_cache, (self.panel_x + 15, footer_y))
        
        # Render building rows
        content_y = self.panel_y + 40
        scroll_y = 0  # TODO: Add scrolling if content exceeds max_height
        
        for i, building_type in enumerate(self.placeable_buildings):
            row_y = content_y + (i * self.row_height) + scroll_y
            
            # Skip if outside visible area
            if row_y + self.row_height < self.panel_y + 40 or row_y > self.panel_y + panel_height - 30:
                continue
            
            is_available, reason = self._get_building_availability(building_type, economy, buildings)
            is_hovered = (self.hovered_row == building_type)
            is_selected = (selected_building_type == building_type)
            
            self._render_building_row(
                surface, building_type, row_y, is_available, is_hovered, is_selected, reason
            )
    
    def _render_building_row(
        self, surface: pygame.Surface, building_type: str, y: int,
        is_available: bool, is_hovered: bool, is_selected: bool, reason: str
    ):
        """Render a single building row."""
        row_rect = pygame.Rect(self.panel_x + 2, y, self.panel_width - 4, self.row_height - 2)
        
        # Row background
        if is_selected:
            bg_color = (70, 70, 90)  # Selected highlight
        elif is_hovered and is_available:
            bg_color = (60, 60, 75)  # Hover
        else:
            bg_color = (45, 45, 60)  # Normal
        
        if not is_available:
            bg_color = (35, 35, 45)  # Disabled
        
        pygame.draw.rect(surface, bg_color, row_rect)
        
        # Icon/color swatch (left)
        icon_x = self.panel_x + 10
        icon_y = y + (self.row_height - self.icon_size) // 2
        icon_rect = pygame.Rect(icon_x, icon_y, self.icon_size, self.icon_size)
        color = BUILDING_COLORS.get(building_type, (128, 128, 128))
        pygame.draw.rect(surface, color, icon_rect)
        pygame.draw.rect(surface, COLOR_UI_BORDER, icon_rect, 1)
        
        # Building name + cost (center)
        name_x = icon_x + self.icon_size + 15
        name_y = y + 8
        
        building_name = building_type.replace("_", " ").title()
        cost = BUILDING_COSTS.get(building_type, 0)
        
        if is_available:
            name_color = COLOR_WHITE
            cost_color = COLOR_GREEN if cost > 0 else (180, 180, 180)
        else:
            name_color = (120, 120, 120)
            cost_color = COLOR_RED if cost > 0 else (100, 100, 100)
        
        name_surf = self.font_body.render(building_name, True, name_color)
        surface.blit(name_surf, (name_x, name_y))
        
        cost_text = f"${cost}" if cost > 0 else "Free"
        cost_surf = self.font_small.render(cost_text, True, cost_color)
        surface.blit(cost_surf, (name_x, name_y + name_surf.get_height() + 2))
        
        # Prerequisite/constraint hint (if unavailable)
        if not is_available and reason:
            hint_surf = self.font_small.render(reason, True, (150, 150, 150))
            surface.blit(hint_surf, (name_x, name_y + name_surf.get_height() + cost_surf.get_height() + 4))
        
        # Hotkey badge (right)
        hotkey = BUILDING_HOTKEYS.get(building_type, "")
        if hotkey:
            badge_x = self.panel_x + self.panel_width - 50
            badge_y = y + (self.row_height - 20) // 2
            badge_rect = pygame.Rect(badge_x, badge_y, 35, 20)
            
            badge_bg = (80, 80, 100) if is_available else (50, 50, 60)
            pygame.draw.rect(surface, badge_bg, badge_rect)
            pygame.draw.rect(surface, COLOR_UI_BORDER, badge_rect, 1)
            
            hotkey_surf = self.font_small.render(hotkey, True, (200, 200, 200) if is_available else (120, 120, 120))
            hotkey_w = hotkey_surf.get_width()
            hotkey_h = hotkey_surf.get_height()
            surface.blit(hotkey_surf, (badge_x + (35 - hotkey_w) // 2, badge_y + (20 - hotkey_h) // 2))

