"""
Building detail panel for showing building information when clicked.
"""
import pygame
from game.ui.widgets import NineSlice
from config import COLOR_UI_BG, COLOR_UI_BORDER, COLOR_WHITE, COLOR_GOLD, COLOR_GREEN, COLOR_RED


class BuildingPanel:
    """Panel that shows detailed building information when a building is selected."""
    
    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.visible = False
        self.selected_building = None

        # CC0 UI pack textures (WK7 R7)
        self._panel_tex_modal = "assets/ui/kingdomsim_ui_cc0/panels/panel_modal.png"
        self._panel_slice_border = 8
        
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

        # Buttons for library research
        self.library_research_rects = {}
        self.library_research_hovered = None
        
        # Button for upgrade (palace)
        self.upgrade_button_rect = None
        self.upgrade_button_hovered = False
        
        # Button for demolish
        self.demolish_button_rect = None
        self.demolish_button_hovered = False
        
        # WK7: Button for castle build catalog
        self.build_catalog_button_rect = None
        self.build_catalog_button_hovered = False
        
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
    
    def handle_click(self, mouse_pos: tuple, economy, game_state: dict) -> bool | dict:
        """Handle mouse click on the panel. Returns True if click was handled, or action dict for demolish."""
        if not self.visible or not self.selected_building:
            return False
        
        # Check if click is within panel
        if not (self.panel_x <= mouse_pos[0] <= self.panel_x + self.panel_width and
                self.panel_y <= mouse_pos[1] <= self.panel_y + self.panel_height):
            return False
        
        # Check demolish button (check first, before other buttons)
        if self.demolish_button_rect and self.demolish_button_rect.collidepoint(mouse_pos):
            building = self.selected_building
            # Disabled for castle (should not appear, but defensive check)
            if building.building_type == "castle":
                return True
            # Disabled for under-construction buildings
            if hasattr(building, "is_constructed") and not building.is_constructed:
                return True
            # Return demolish action dict for engine to consume
            return {"type": "demolish_building", "building": building}
        
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
        
        # WK7: Check build catalog button for castle
        if self.build_catalog_button_rect and self.selected_building.building_type == "castle":
            if self.build_catalog_button_rect.collidepoint(mouse_pos):
                return {"type": "open_build_catalog"}
        
        # Check upgrade button for palace
        if hasattr(self, "upgrade_button_rect") and self.upgrade_button_rect and self.selected_building.building_type == "palace":
            if self.upgrade_button_rect.collidepoint(mouse_pos):
                if self.selected_building.can_upgrade():
                    if self.selected_building.upgrade(economy):
                        return True

        # Check library research buttons
        if self.selected_building.building_type == "library" and self.library_research_rects:
            for research_name, rect in self.library_research_rects.items():
                if rect.collidepoint(mouse_pos):
                    # Cannot research while under construction
                    if hasattr(self.selected_building, "is_constructed") and not self.selected_building.is_constructed:
                        return True
                    self.selected_building.research(research_name, economy, game_state)
                    return True
        
        return True  # Click was in panel
    
    def update_hover(self, mouse_pos: tuple):
        """Update hover state for buttons."""
        if self.research_button_rect:
            self.research_button_hovered = self.research_button_rect.collidepoint(mouse_pos)

        if self.demolish_button_rect:
            self.demolish_button_hovered = self.demolish_button_rect.collidepoint(mouse_pos)
        else:
            self.demolish_button_hovered = False
        
        # WK7: Build catalog button hover
        if self.build_catalog_button_rect:
            self.build_catalog_button_hovered = self.build_catalog_button_rect.collidepoint(mouse_pos)
        else:
            self.build_catalog_button_hovered = False

        self.library_research_hovered = None
        if self.visible and self.selected_building and self.selected_building.building_type == "library":
            for research_name, rect in self.library_research_rects.items():
                if rect.collidepoint(mouse_pos):
                    self.library_research_hovered = research_name
                    break
    
    def render(self, surface: pygame.Surface, heroes: list, economy):
        """Render the building panel."""
        if not self.visible or not self.selected_building:
            return
        
        building = self.selected_building

        # Reset per-frame clickable regions to avoid stale rects
        self.library_research_rects = {}
        
        # Panel background (skinned)
        panel_surf = pygame.Surface((self.panel_width, self.panel_height), pygame.SRCALPHA)
        if not NineSlice.render(
            panel_surf,
            pygame.Rect(0, 0, self.panel_width, self.panel_height),
            self._panel_tex_modal,
            border=self._panel_slice_border,
        ):
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
        if building.building_type in ["warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild",
                                      "temple_agrela", "temple_dauros", "temple_fervus", "temple_krypta",
                                      "temple_krolm", "temple_helia", "temple_lunord",
                                      "gnome_hovel", "elven_bungalow", "dwarven_settlement"]:
            y = self.render_warrior_guild(panel_surf, building, heroes, y)
        elif building.building_type == "marketplace":
            y = self.render_marketplace(panel_surf, building, heroes, y, economy)
        elif building.building_type == "castle":
            y = self.render_castle(panel_surf, building, heroes, y)
        elif building.building_type == "palace":
            y = self.render_palace(panel_surf, building, heroes, y, economy)
        elif building.building_type == "blacksmith":
            y = self.render_blacksmith(panel_surf, building, y)
        elif building.building_type == "inn":
            y = self.render_inn(panel_surf, building, heroes, y)
        elif building.building_type == "trading_post":
            y = self.render_trading_post(panel_surf, building, y)
        elif building.building_type == "guardhouse":
            y = self.render_guardhouse(panel_surf, building, y)
        elif building.building_type == "ballista_tower":
            y = self.render_ballista_tower(panel_surf, building, y)
        elif building.building_type == "wizard_tower":
            y = self.render_wizard_tower(panel_surf, building, y)
        elif building.building_type == "fairgrounds":
            y = self.render_fairgrounds(panel_surf, building, y)
        elif building.building_type == "library":
            y = self.render_library(panel_surf, building, y, economy)
        elif building.building_type == "royal_gardens":
            y = self.render_royal_gardens(panel_surf, building, heroes, y)
        else:
            y = self.render_generic_building(panel_surf, building, y)
        
        # Render demolish button at bottom (after all building-specific content)
        y = self.render_demolish_button(panel_surf, building, y)
        
        surface.blit(panel_surf, (self.panel_x, self.panel_y))

    def render_generic_building(self, surface: pygame.Surface, building, y: int) -> int:
        """Fallback renderer for buildings without a dedicated panel."""
        hp_text = self.font_normal.render(f"HP: {int(getattr(building, 'hp', 0))}/{int(getattr(building, 'max_hp', 0))}", True, COLOR_WHITE)
        surface.blit(hp_text, (10, y))
        y += 22

        if hasattr(building, "stored_tax_gold"):
            tax_text = self.font_normal.render(f"Taxable Gold: ${int(getattr(building, 'stored_tax_gold', 0))}", True, COLOR_GOLD)
            surface.blit(tax_text, (10, y))
            y += 22

        if getattr(building, "is_neutral", False):
            tag = self.font_small.render("Neutral building (auto-spawned)", True, (160, 160, 160))
            surface.blit(tag, (10, y))
            y += 18

        if getattr(building, "is_under_attack", False):
            warn = self.font_small.render("Status: UNDER ATTACK", True, COLOR_RED)
            surface.blit(warn, (10, y))
            y += 18

        return y
    
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
            potion_price = getattr(building, "potion_price", 20)
            price_text = self.font_small.render(f"Heroes can buy potions for ${potion_price} each", True, (180, 180, 180))
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
            potion_price = getattr(building, "potion_price", 20)
            potion_text = self.font_small.render(f"• Healing Potion - ${potion_price}", True, COLOR_GREEN)
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
        
        # WK7: Build buildings button (draw in panel-local coords, store screen-space rect)
        button_w = self.panel_width - 20
        button_h = 32
        button_x = 10
        button_y = y
        local_rect = pygame.Rect(button_x, button_y, button_w, button_h)
        self.build_catalog_button_rect = pygame.Rect(
            self.panel_x + local_rect.x,
            self.panel_y + local_rect.y,
            local_rect.width,
            local_rect.height,
        )
        bg_color = (70, 100, 120) if self.build_catalog_button_hovered else (60, 80, 100)
        pygame.draw.rect(surface, bg_color, local_rect)
        pygame.draw.rect(surface, COLOR_UI_BORDER, local_rect, 2)
        button_text = self.font_normal.render("Build Buildings", True, COLOR_WHITE)
        text_x = local_rect.centerx - button_text.get_width() // 2
        text_y = local_rect.centery - button_text.get_height() // 2
        surface.blit(button_text, (text_x, text_y))
        y += button_h + 10
        
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
    
    def render_blacksmith(self, surface: pygame.Surface, building, y: int) -> int:
        """Render blacksmith details."""
        upgrades_text = self.font_normal.render(f"Upgrades Sold: {building.upgrades_sold}", True, COLOR_WHITE)
        surface.blit(upgrades_text, (10, y))
        y += 25
        
        info_text = self.font_small.render("Heroes can upgrade equipment here", True, (180, 180, 180))
        surface.blit(info_text, (10, y))
        y += 20
        return y
    
    def render_inn(self, surface: pygame.Surface, building, heroes: list, y: int) -> int:
        """Render inn details."""
        resting_count = len([h for h in heroes if h.is_alive and h.home_building == building])
        resting_text = self.font_normal.render(f"Heroes Resting: {resting_count}", True, COLOR_WHITE)
        surface.blit(resting_text, (10, y))
        y += 25
        
        info_text = self.font_small.render("Faster HP recovery than guilds", True, (180, 180, 180))
        surface.blit(info_text, (10, y))
        y += 20
        return y
    
    def render_trading_post(self, surface: pygame.Surface, building, y: int) -> int:
        """Render trading post details."""
        income_text = self.font_normal.render(f"Total Income: ${building.total_income_generated}", True, COLOR_GOLD)
        surface.blit(income_text, (10, y))
        y += 25
        
        info_text = self.font_small.render(f"Generates ${building.income_amount} every {building.income_interval:.0f}s", True, (180, 180, 180))
        surface.blit(info_text, (10, y))
        y += 20
        return y
    
    def render_guardhouse(self, surface: pygame.Surface, building, y: int) -> int:
        """Render guardhouse details."""
        guards_text = self.font_normal.render(f"Guards Spawned: {building.guards_spawned}", True, COLOR_WHITE)
        surface.blit(guards_text, (10, y))
        y += 25
        
        max_text = self.font_small.render(f"Max Guards: {building.max_guards}", True, (180, 180, 180))
        surface.blit(max_text, (10, y))
        y += 20
        return y
    
    def render_ballista_tower(self, surface: pygame.Surface, building, y: int) -> int:
        """Render ballista tower details."""
        range_text = self.font_normal.render(f"Range: {building.attack_range}px", True, COLOR_WHITE)
        surface.blit(range_text, (10, y))
        y += 25
        
        damage_text = self.font_small.render(f"Damage: {building.attack_damage}", True, (180, 180, 180))
        surface.blit(damage_text, (10, y))
        y += 20
        
        if building.target:
            target_text = self.font_small.render("Targeting enemy", True, COLOR_RED)
            surface.blit(target_text, (10, y))
            y += 20
        return y
    
    def render_wizard_tower(self, surface: pygame.Surface, building, y: int) -> int:
        """Render wizard tower details."""
        range_text = self.font_normal.render(f"Spell Range: {building.spell_range}px", True, COLOR_WHITE)
        surface.blit(range_text, (10, y))
        y += 25
        
        damage_text = self.font_small.render(f"Spell Damage: {building.spell_damage}", True, (180, 180, 180))
        surface.blit(damage_text, (10, y))
        y += 20
        
        cooldown_text = self.font_small.render(f"Cooldown: {building.spell_interval:.1f}s", True, (180, 180, 180))
        surface.blit(cooldown_text, (10, y))
        y += 20
        return y
    
    def render_fairgrounds(self, surface: pygame.Surface, building, y: int) -> int:
        """Render fairgrounds details."""
        tournaments_text = self.font_normal.render(f"Tournaments: {building.total_tournaments}", True, COLOR_WHITE)
        surface.blit(tournaments_text, (10, y))
        y += 25
        
        income_text = self.font_small.render(f"Income per tournament: ${building.tournament_income}", True, COLOR_GOLD)
        surface.blit(income_text, (10, y))
        y += 20
        
        info_text = self.font_small.render("Heroes nearby gain XP during tournaments", True, (180, 180, 180))
        surface.blit(info_text, (10, y))
        y += 20
        return y
    
    def render_library(self, surface: pygame.Surface, building, y: int, economy) -> int:
        """Render library details."""
        if hasattr(building, "is_constructed") and not building.is_constructed:
            uc = self.font_normal.render("Status: UNDER CONSTRUCTION", True, (200, 200, 100))
            surface.blit(uc, (10, y))
            y += 25
            note = self.font_small.render("Peasants must finish building it first.", True, (180, 180, 180))
            surface.blit(note, (10, y))
            y += 25
            return y

        researched_text = self.font_normal.render(f"Researched: {len(building.researched_items)}", True, COLOR_WHITE)
        surface.blit(researched_text, (10, y))
        y += 25
        
        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
        y += 10
        
        research_title = self.font_normal.render("Available Research:", True, COLOR_WHITE)
        surface.blit(research_title, (10, y))
        y += 22
        
        for item in building.available_research:
            name = item["name"]
            cost = item["cost"]

            if item["researched"]:
                item_text = self.font_small.render(f"✓ {name}", True, COLOR_GREEN)
                surface.blit(item_text, (15, y))
                y += 18
                continue

            # Clickable research row
            button_x = 10
            button_y = y
            button_width = self.panel_width - 20
            button_height = 24

            can_afford = economy.player_gold >= cost
            button_color = (60, 120, 60) if can_afford else (80, 80, 80)
            if self.library_research_hovered == name and can_afford:
                button_color = (80, 150, 80)

            pygame.draw.rect(surface, button_color, (button_x, button_y, button_width, button_height))
            pygame.draw.rect(surface, COLOR_WHITE, (button_x, button_y, button_width, button_height), 1)

            btn_text = f"Research: {name} (${cost})" if can_afford else f"Research: {name} (Need ${cost})"
            btn_render = self.font_small.render(btn_text, True, COLOR_WHITE)
            btn_rect = btn_render.get_rect(center=(button_x + button_width // 2, button_y + button_height // 2))
            surface.blit(btn_render, btn_rect)

            # Store clickable rect in screen coordinates
            self.library_research_rects[name] = pygame.Rect(
                self.panel_x + button_x,
                self.panel_y + button_y,
                button_width,
                button_height
            )

            y += button_height + 8
        return y
    
    def render_royal_gardens(self, surface: pygame.Surface, building, heroes: list, y: int) -> int:
        """Render royal gardens details."""
        buffed_heroes = building.get_heroes_in_range(heroes)
        buffed_text = self.font_normal.render(f"Heroes Buffed: {len(buffed_heroes)}", True, COLOR_WHITE)
        surface.blit(buffed_text, (10, y))
        y += 25
        
        buff_text = self.font_small.render(f"Attack Bonus: +{building.buff_attack_bonus}", True, COLOR_GREEN)
        surface.blit(buff_text, (10, y))
        y += 18
        
        defense_text = self.font_small.render(f"Defense Bonus: +{building.buff_defense_bonus}", True, COLOR_GREEN)
        surface.blit(defense_text, (10, y))
        y += 18
        
        range_text = self.font_small.render(f"Buff Range: {building.buff_range}px", True, (180, 180, 180))
        surface.blit(range_text, (10, y))
        y += 20
        return y
    
    def render_palace(self, surface: pygame.Surface, building, heroes: list, y: int, economy) -> int:
        """Render palace details with upgrade option."""
        # Level
        level_text = self.font_normal.render(f"Level: {building.level}/{building.max_level}", True, COLOR_WHITE)
        surface.blit(level_text, (10, y))
        y += 25
        
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
        
        # Capacity info
        capacity_text = self.font_small.render(
            f"Peasants: {building.max_peasants} | Tax Collectors: {building.max_tax_collectors} | Guards: {building.max_palace_guards}",
            True, (180, 180, 180)
        )
        surface.blit(capacity_text, (10, y))
        y += 20
        
        # Upgrade button
        if building.can_upgrade():
            pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
            y += 10
            
            upgrade_cost = building.get_upgrade_cost()
            button_width = 200
            button_height = 30
            button_x = 10
            button_y = y
            
            can_afford = economy.player_gold >= upgrade_cost
            button_color = (60, 120, 60) if can_afford else (80, 80, 80)
            
            pygame.draw.rect(surface, button_color, (button_x, button_y, button_width, button_height))
            pygame.draw.rect(surface, COLOR_WHITE, (button_x, button_y, button_width, button_height), 1)
            
            btn_text = f"Upgrade to Level {building.level + 1} (${upgrade_cost})" if can_afford else f"Upgrade (Need ${upgrade_cost})"
            btn_render = self.font_small.render(btn_text, True, COLOR_WHITE)
            btn_rect = btn_render.get_rect(center=(button_x + button_width // 2, button_y + button_height // 2))
            surface.blit(btn_render, btn_rect)
            
            # Store button rect for click detection
            self.upgrade_button_rect = pygame.Rect(
                self.panel_x + button_x,
                self.panel_y + button_y,
                button_width,
                button_height
            )
            y += 40
        else:
            self.upgrade_button_rect = None
        
        return y
    
    def render_demolish_button(self, surface: pygame.Surface, building, y: int) -> int:
        """Render demolish button at bottom of panel. Returns updated y position."""
        # Hide demolish button for castle
        if building.building_type == "castle":
            self.demolish_button_rect = None
            return y
        
        # Add separator line before demolish section
        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
        y += 10
        
        # Check if building is under construction (disabled state)
        is_under_construction = hasattr(building, "is_constructed") and not building.is_constructed
        
        # Button dimensions (consistent with existing buttons)
        button_width = 200
        button_height = 30
        button_x = 10
        button_y = y
        
        # Button colors based on state
        if is_under_construction:
            # Disabled state: gray
            button_color = (80, 80, 80)
            text_color = (120, 120, 120)
        elif self.demolish_button_hovered:
            # Hover state: lighter red
            button_color = (160, 60, 60)
            text_color = COLOR_WHITE
        else:
            # Default state: dark red
            button_color = (120, 40, 40)
            text_color = COLOR_WHITE
        
        # Draw button background
        pygame.draw.rect(surface, button_color, (button_x, button_y, button_width, button_height))
        # Draw button border (white, 1px)
        pygame.draw.rect(surface, COLOR_WHITE, (button_x, button_y, button_width, button_height), 1)
        
        # Button text
        btn_text = "Demolish"
        if is_under_construction:
            btn_text = "Demolish (Under Construction)"
        btn_render = self.font_small.render(btn_text, True, text_color)
        btn_rect = btn_render.get_rect(center=(button_x + button_width // 2, button_y + button_height // 2))
        surface.blit(btn_render, btn_rect)
        
        # Store button rect for click detection (in screen coordinates)
        self.demolish_button_rect = pygame.Rect(
            self.panel_x + button_x,
            self.panel_y + button_y,
            button_width,
            button_height
        )
        
        y += button_height + 10  # Add spacing after button
        
        return y

