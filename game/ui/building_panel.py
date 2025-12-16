"""
Building detail panel for showing building information when clicked.
"""
import pygame
from config import COLOR_UI_BG, COLOR_UI_BORDER, COLOR_WHITE, COLOR_GOLD, COLOR_GREEN, COLOR_RED


class BuildingPanel:
    """Panel that shows detailed building information when a building is selected."""
    
    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.visible = False
        self.selected_building = None
        
        # Panel dimensions
        self.panel_width = 300
        self.panel_height = 400
        self.panel_x = 10
        self.panel_y = 50
        
        # Fonts
        self.font_title = pygame.font.Font(None, 28)
        self.font_normal = pygame.font.Font(None, 20)
        self.font_small = pygame.font.Font(None, 16)
        
        # Button for research (marketplace)
        self.research_button_rect = None
        self.research_button_hovered = False
        
        # Hero portrait colors (simple colored circles as placeholders)
        self.portrait_colors = [
            (70, 130, 180),   # Steel blue
            (178, 34, 34),    # Firebrick
            (46, 139, 87),    # Sea green
            (218, 165, 32),   # Goldenrod
            (147, 112, 219),  # Medium purple
            (205, 92, 92),    # Indian red
            (60, 179, 113),   # Medium sea green
            (255, 140, 0),    # Dark orange
        ]
    
    def select_building(self, building, heroes: list):
        """Select a building to show details for."""
        self.selected_building = building
        self.visible = True
    
    def deselect(self):
        """Deselect the current building."""
        self.selected_building = None
        self.visible = False
    
    def get_heroes_for_building(self, building, all_heroes: list) -> dict:
        """Get heroes associated with this building."""
        result = {
            "total": 0,
            "resting": [],
            "fighting": [],
            "idle": [],
            "moving": [],
            "other": []
        }
        
        for hero in all_heroes:
            if not hero.is_alive:
                continue
            if hero.home_building == building:
                result["total"] += 1
                
                state_name = hero.state.name.lower()
                if state_name == "resting":
                    result["resting"].append(hero)
                elif state_name == "fighting":
                    result["fighting"].append(hero)
                elif state_name == "idle":
                    result["idle"].append(hero)
                elif state_name == "moving":
                    result["moving"].append(hero)
                else:
                    result["other"].append(hero)
        
        return result
    
    def handle_click(self, mouse_pos: tuple, economy, game_state: dict) -> bool:
        """Handle mouse click on the panel. Returns True if click was handled."""
        if not self.visible or not self.selected_building:
            return False
        
        # Check if click is within panel
        if not (self.panel_x <= mouse_pos[0] <= self.panel_x + self.panel_width and
                self.panel_y <= mouse_pos[1] <= self.panel_y + self.panel_height):
            return False
        
        # Check research button for marketplace
        if self.research_button_rect and self.selected_building.building_type == "marketplace":
            if self.research_button_rect.collidepoint(mouse_pos):
                # Cannot research while under construction
                if hasattr(self.selected_building, "is_constructed") and not self.selected_building.is_constructed:
                    return True
                # Try to research potions
                if not self.selected_building.potions_researched:
                    if economy.player_gold >= 100:
                        economy.player_gold -= 100
                        self.selected_building.potions_researched = True
                        return True
        
        return True  # Click was in panel
    
    def update_hover(self, mouse_pos: tuple):
        """Update hover state for buttons."""
        if self.research_button_rect:
            self.research_button_hovered = self.research_button_rect.collidepoint(mouse_pos)
    
    def render(self, surface: pygame.Surface, heroes: list, economy):
        """Render the building panel."""
        if not self.visible or not self.selected_building:
            return
        
        building = self.selected_building
        
        # Panel background
        panel_surf = pygame.Surface((self.panel_width, self.panel_height), pygame.SRCALPHA)
        panel_surf.fill((*COLOR_UI_BG, 240))
        pygame.draw.rect(panel_surf, COLOR_UI_BORDER, 
                        (0, 0, self.panel_width, self.panel_height), 2)
        
        y = 10
        
        # Building name
        building_name = building.building_type.replace("_", " ").title()
        title = self.font_title.render(building_name, True, COLOR_WHITE)
        panel_surf.blit(title, (10, y))
        y += 35
        
        # Separator
        pygame.draw.line(panel_surf, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
        y += 10
        
        # Building-specific info
        if building.building_type in ["warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild"]:
            y = self.render_warrior_guild(panel_surf, building, heroes, y)
        elif building.building_type == "marketplace":
            y = self.render_marketplace(panel_surf, building, heroes, y, economy)
        elif building.building_type == "castle":
            y = self.render_castle(panel_surf, building, heroes, y)
        
        surface.blit(panel_surf, (self.panel_x, self.panel_y))
    
    def render_warrior_guild(self, surface: pygame.Surface, building, heroes: list, y: int) -> int:
        """Render warrior guild details."""
        hero_info = self.get_heroes_for_building(building, heroes)
        
        # Tax gold
        tax_text = self.font_normal.render(f"Taxable Gold: ${building.stored_tax_gold}", True, COLOR_GOLD)
        surface.blit(tax_text, (10, y))
        y += 25
        
        # Total heroes
        total_text = self.font_normal.render(f"Total Heroes: {hero_info['total']}", True, COLOR_WHITE)
        surface.blit(total_text, (10, y))
        y += 25
        
        # Status counts
        status_text = self.font_small.render(
            f"Fighting: {len(hero_info['fighting'])} | Resting: {len(hero_info['resting'])} | Idle: {len(hero_info['idle'])}",
            True, (180, 180, 180)
        )
        surface.blit(status_text, (10, y))
        y += 20
        
        # Separator
        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
        y += 10
        
        # Resting heroes section
        resting_title = self.font_normal.render("Heroes Resting:", True, COLOR_WHITE)
        surface.blit(resting_title, (10, y))
        y += 22
        
        if hero_info['resting']:
            for i, hero in enumerate(hero_info['resting'][:5]):  # Max 5 shown
                y = self.render_hero_row(surface, hero, y, i)
        else:
            no_rest = self.font_small.render("No heroes resting", True, (120, 120, 120))
            surface.blit(no_rest, (20, y))
            y += 18
        
        y += 10
        
        # All heroes section
        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
        y += 10
        
        all_title = self.font_normal.render("All Guild Heroes:", True, COLOR_WHITE)
        surface.blit(all_title, (10, y))
        y += 22
        
        all_heroes = (hero_info['fighting'] + hero_info['idle'] + 
                     hero_info['moving'] + hero_info['resting'] + hero_info['other'])
        
        for i, hero in enumerate(all_heroes[:6]):  # Max 6 shown
            y = self.render_hero_row(surface, hero, y, i)
        
        if len(all_heroes) > 6:
            more_text = self.font_small.render(f"... and {len(all_heroes) - 6} more", True, (120, 120, 120))
            surface.blit(more_text, (20, y))
            y += 18
        
        return y
    
    def render_marketplace(self, surface: pygame.Surface, building, heroes: list, y: int, economy) -> int:
        """Render marketplace details."""
        if hasattr(building, "is_constructed") and not building.is_constructed:
            uc = self.font_normal.render("Status: UNDER CONSTRUCTION", True, (200, 200, 100))
            surface.blit(uc, (10, y))
            y += 25
            note = self.font_small.render("Peasants must finish building it first.", True, (180, 180, 180))
            surface.blit(note, (10, y))
            y += 25
            # Disable research while unconstructed
            self.research_button_rect = None
            return y

        # Research status
        if hasattr(building, 'potions_researched') and building.potions_researched:
            research_text = self.font_normal.render("Healing Potions: RESEARCHED", True, COLOR_GREEN)
            surface.blit(research_text, (10, y))
            y += 25
            
            # Show potion price
            price_text = self.font_small.render("Heroes can buy potions for $20 each", True, (180, 180, 180))
            surface.blit(price_text, (10, y))
            y += 20
        else:
            research_text = self.font_normal.render("Healing Potions: Not Researched", True, (180, 180, 180))
            surface.blit(research_text, (10, y))
            y += 25
            
            # Research button
            button_width = 200
            button_height = 30
            button_x = 10
            button_y = y
            
            can_afford = economy.player_gold >= 100
            button_color = (60, 120, 60) if can_afford else (80, 80, 80)
            if self.research_button_hovered and can_afford:
                button_color = (80, 150, 80)
            
            pygame.draw.rect(surface, button_color, (button_x, button_y, button_width, button_height))
            pygame.draw.rect(surface, COLOR_WHITE, (button_x, button_y, button_width, button_height), 1)
            
            btn_text = "Research Potions ($100)" if can_afford else "Research Potions (Need $100)"
            btn_render = self.font_small.render(btn_text, True, COLOR_WHITE)
            btn_rect = btn_render.get_rect(center=(button_x + button_width // 2, button_y + button_height // 2))
            surface.blit(btn_render, btn_rect)
            
            # Store button rect for click detection (in screen coordinates)
            self.research_button_rect = pygame.Rect(
                self.panel_x + button_x, 
                self.panel_y + button_y, 
                button_width, 
                button_height
            )
            
            y += 40
        
        y += 10
        
        # Separator
        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
        y += 10
        
        # Available items
        items_title = self.font_normal.render("Items for Sale:", True, COLOR_WHITE)
        surface.blit(items_title, (10, y))
        y += 22
        
        for item in building.get_available_items():
            item_text = self.font_small.render(f"• {item['name']} - ${item['price']}", True, (180, 180, 180))
            surface.blit(item_text, (15, y))
            y += 16
        
        # Show potions if researched
        if hasattr(building, 'potions_researched') and building.potions_researched:
            potion_text = self.font_small.render("• Healing Potion - $20", True, COLOR_GREEN)
            surface.blit(potion_text, (15, y))
            y += 16
        
        return y
    
    def render_castle(self, surface: pygame.Surface, building, heroes: list, y: int) -> int:
        """Render castle details."""
        # HP
        hp_text = self.font_normal.render(f"HP: {building.hp}/{building.max_hp}", True, COLOR_WHITE)
        surface.blit(hp_text, (10, y))
        y += 25
        
        # HP bar
        bar_width = self.panel_width - 20
        bar_height = 12
        pygame.draw.rect(surface, (60, 60, 60), (10, y, bar_width, bar_height))
        hp_pct = building.hp / building.max_hp
        hp_color = COLOR_GREEN if hp_pct > 0.5 else COLOR_RED
        pygame.draw.rect(surface, hp_color, (10, y, bar_width * hp_pct, bar_height))
        y += 20
        
        # Total heroes in kingdom
        alive_heroes = [h for h in heroes if h.is_alive]
        total_text = self.font_normal.render(f"Kingdom Heroes: {len(alive_heroes)}", True, COLOR_WHITE)
        surface.blit(total_text, (10, y))
        y += 25
        
        return y
    
    def render_hero_row(self, surface: pygame.Surface, hero, y: int, index: int) -> int:
        """Render a single hero row with portrait, name, HP, and status."""
        # Portrait (colored circle)
        portrait_color = self.portrait_colors[index % len(self.portrait_colors)]
        portrait_x = 20
        portrait_radius = 12
        pygame.draw.circle(surface, portrait_color, (portrait_x, y + 10), portrait_radius)
        pygame.draw.circle(surface, COLOR_WHITE, (portrait_x, y + 10), portrait_radius, 1)
        
        # Name and status
        status_color = self.get_status_color(hero.state.name)
        name_text = self.font_small.render(f"{hero.name}", True, COLOR_WHITE)
        surface.blit(name_text, (40, y))
        
        status_text = self.font_small.render(f"[{hero.state.name}]", True, status_color)
        surface.blit(status_text, (40 + name_text.get_width() + 5, y))
        
        # HP bar
        hp_bar_x = 40
        hp_bar_y = y + 14
        hp_bar_width = 80
        hp_bar_height = 6
        
        pygame.draw.rect(surface, (60, 60, 60), (hp_bar_x, hp_bar_y, hp_bar_width, hp_bar_height))
        hp_pct = hero.hp / hero.max_hp
        hp_color = COLOR_GREEN if hp_pct > 0.5 else COLOR_RED
        pygame.draw.rect(surface, hp_color, (hp_bar_x, hp_bar_y, hp_bar_width * hp_pct, hp_bar_height))
        
        # HP text
        hp_text = self.font_small.render(f"{hero.hp}/{hero.max_hp}", True, (150, 150, 150))
        surface.blit(hp_text, (hp_bar_x + hp_bar_width + 5, y + 7))
        
        # Potions (always show count; emoji can render inconsistently on some systems)
        pot_color = (100, 200, 100) if hero.potions > 0 else (130, 130, 130)
        pot_text = self.font_small.render(f"Potions: {hero.potions}", True, pot_color)
        surface.blit(pot_text, (180, y + 7))
        
        return y + 28
    
    def get_status_color(self, status: str) -> tuple:
        """Get color for a hero status."""
        status_colors = {
            "FIGHTING": (220, 60, 60),
            "RESTING": (100, 150, 255),
            "IDLE": (150, 150, 150),
            "MOVING": (200, 200, 100),
            "RETREATING": (255, 165, 0),
            "SHOPPING": (218, 165, 32),
        }
        return status_colors.get(status.upper(), (150, 150, 150))

