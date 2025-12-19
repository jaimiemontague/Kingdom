"""
Heads-up display for game information.
"""
import pygame
from config import (
    WINDOW_WIDTH, COLOR_UI_BG, COLOR_UI_BORDER, COLOR_GOLD, 
    COLOR_WHITE, COLOR_RED, COLOR_GREEN
)


class HUD:
    """Displays game information to the player."""
    
    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        # HUD dimensions
        self.top_bar_height = 40
        self.side_panel_width = 200
        
        # Fonts
        self.font_large = pygame.font.Font(None, 32)
        self.font_medium = pygame.font.Font(None, 24)
        self.font_small = pygame.font.Font(None, 18)
        
        # Messages
        self.messages = []
        self.message_duration = 3000  # ms
        
    def add_message(self, text: str, color: tuple = COLOR_WHITE):
        """Add a message to display."""
        self.messages.append({
            "text": text,
            "color": color,
            "time": pygame.time.get_ticks()
        })
        # Keep only last 5 messages
        if len(self.messages) > 5:
            self.messages.pop(0)
    
    def update(self):
        """Update HUD state."""
        current_time = pygame.time.get_ticks()
        # Remove old messages
        self.messages = [
            m for m in self.messages 
            if current_time - m["time"] < self.message_duration
        ]
    
    def render(self, surface: pygame.Surface, game_state: dict):
        """Render the HUD."""
        # Top bar background
        pygame.draw.rect(
            surface,
            COLOR_UI_BG,
            (0, 0, self.screen_width, self.top_bar_height)
        )
        pygame.draw.line(
            surface,
            COLOR_UI_BORDER,
            (0, self.top_bar_height),
            (self.screen_width, self.top_bar_height),
            2
        )
        
        # Gold display
        gold = game_state.get("gold", 0)
        gold_text = self.font_large.render(f"Gold: {gold}", True, COLOR_GOLD)
        surface.blit(gold_text, (20, 8))
        
        # Hero count
        heroes = game_state.get("heroes", [])
        alive_heroes = sum(1 for h in heroes if h.is_alive)
        hero_text = self.font_medium.render(
            f"Heroes: {alive_heroes}", True, COLOR_WHITE
        )
        surface.blit(hero_text, (200, 10))
        
        # Enemy count
        enemies = game_state.get("enemies", [])
        alive_enemies = sum(1 for e in enemies if e.is_alive)
        enemy_text = self.font_medium.render(
            f"Enemies: {alive_enemies}", True, COLOR_RED
        )
        surface.blit(enemy_text, (320, 10))
        
        # Wave number
        wave = game_state.get("wave", 1)
        wave_text = self.font_medium.render(
            f"Wave: {wave}", True, COLOR_WHITE
        )
        surface.blit(wave_text, (450, 10))
        
        # Instructions
        instructions = [
            "1: Warrior Guild ($150)",
            "2: Marketplace ($100)",
            "3: Ranger Guild ($175)",
            "4: Rogue Guild ($160)",
            "5: Wizard Guild ($220)",
            "6: Blacksmith ($200)",
            "7: Inn ($150)",
            "8: Trading Post ($250)",
            "T: Temple Agrela ($400)",
            "G: Gnome Hovel ($300)",
            "E: Elven Bungalow ($350)",
            "V: Dwarven Settlement ($300)",
            "U: Guardhouse ($200)",
            "Y: Ballista Tower ($300)",
            "O: Wizard Tower ($500)",
            "F: Fairgrounds ($400)",
            "I: Library ($350)",
            "R: Royal Gardens ($250)",
            "H: Hire Hero ($50)",
            "B: Place Bounty ($50)",
            "Space: Center on Castle",
            "Esc: Pause",
            "WASD: Scroll camera",
            "+/- or Wheel: Zoom",
            "F1: Debug Panel"
        ]
        for i, instr in enumerate(instructions):
            text = self.font_small.render(instr, True, COLOR_WHITE)
            surface.blit(text, (self.screen_width - 180, 5 + i * 15))
        
        # Render messages
        self.render_messages(surface)
        
        # Render selected hero info
        selected = game_state.get("selected_hero")
        if selected:
            self.render_hero_panel(surface, selected)
    
    def render_messages(self, surface: pygame.Surface):
        """Render floating messages."""
        y_offset = self.top_bar_height + 10
        for msg in self.messages:
            text = self.font_small.render(msg["text"], True, msg["color"])
            surface.blit(text, (10, y_offset))
            y_offset += 18
    
    def render_hero_panel(self, surface: pygame.Surface, hero):
        """Render detailed info panel for selected hero."""
        panel_width = self.side_panel_width
        panel_height = 200
        panel_x = self.screen_width - panel_width - 10
        panel_y = self.top_bar_height + 10
        
        # Panel background
        pygame.draw.rect(
            surface,
            COLOR_UI_BG,
            (panel_x, panel_y, panel_width, panel_height)
        )
        pygame.draw.rect(
            surface,
            COLOR_UI_BORDER,
            (panel_x, panel_y, panel_width, panel_height),
            2
        )
        
        # Hero info
        y = panel_y + 10
        
        # Name
        name_text = self.font_medium.render(hero.name, True, COLOR_WHITE)
        surface.blit(name_text, (panel_x + 10, y))
        y += 25
        
        # Class and level
        class_text = self.font_small.render(
            f"{hero.hero_class.title()} Lv.{hero.level}", True, COLOR_WHITE
        )
        surface.blit(class_text, (panel_x + 10, y))
        y += 20
        
        # HP bar
        hp_text = self.font_small.render(
            f"HP: {hero.hp}/{hero.max_hp}", True, COLOR_WHITE
        )
        surface.blit(hp_text, (panel_x + 10, y))
        y += 15
        
        bar_width = panel_width - 20
        bar_height = 8
        pygame.draw.rect(surface, (60, 60, 60), (panel_x + 10, y, bar_width, bar_height))
        hp_pct = hero.hp / hero.max_hp
        hp_color = COLOR_GREEN if hp_pct > 0.5 else COLOR_RED
        pygame.draw.rect(surface, hp_color, (panel_x + 10, y, bar_width * hp_pct, bar_height))
        y += 15
        
        # Stats
        stats_text = self.font_small.render(
            f"ATK: {hero.attack}  DEF: {hero.defense}", True, COLOR_WHITE
        )
        surface.blit(stats_text, (panel_x + 10, y))
        y += 20
        
        # Gold (spendable + taxed)
        gold_text = self.font_small.render(f"Gold: {hero.gold}", True, COLOR_GOLD)
        surface.blit(gold_text, (panel_x + 10, y))
        y += 15
        
        # Taxed gold
        tax_text = self.font_small.render(f"Taxed: {hero.taxed_gold}", True, (200, 150, 50))
        surface.blit(tax_text, (panel_x + 10, y))
        y += 20

        # Potions
        potions_text = self.font_small.render(f"Potions: {getattr(hero, 'potions', 0)}", True, COLOR_GREEN)
        surface.blit(potions_text, (panel_x + 10, y))
        y += 20
        
        # Equipment
        weapon = hero.weapon["name"] if hero.weapon else "Fists"
        armor = hero.armor["name"] if hero.armor else "None"
        equip_text = self.font_small.render(f"W: {weapon}", True, COLOR_WHITE)
        surface.blit(equip_text, (panel_x + 10, y))
        y += 15
        armor_text = self.font_small.render(f"A: {armor}", True, COLOR_WHITE)
        surface.blit(armor_text, (panel_x + 10, y))
        y += 20
        
        # State / Last LLM action
        state_text = self.font_small.render(f"State: {hero.state.name}", True, COLOR_WHITE)
        surface.blit(state_text, (panel_x + 10, y))

