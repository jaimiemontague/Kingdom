"""
Debug panel for showing LLM decisions and game state.
"""
import pygame
from config import COLOR_UI_BG, COLOR_UI_BORDER, COLOR_WHITE, COLOR_GOLD, COLOR_GREEN


class DebugPanel:
    """Debug panel for development and LLM decision viewing."""
    
    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.visible = False
        
        # Panel dimensions
        self.panel_width = 350
        self.panel_height = 400
        self.panel_x = 10
        self.panel_y = 50
        
        # Fonts
        self.font_title = pygame.font.Font(None, 24)
        self.font_normal = pygame.font.Font(None, 18)
        self.font_small = pygame.font.Font(None, 14)
        
        # LLM decision log
        self.decision_log = []
        self.max_log_entries = 15
        
    def toggle(self):
        """Toggle panel visibility."""
        self.visible = not self.visible
    
    def log_decision(self, hero_name: str, decision: dict):
        """Log an LLM decision."""
        entry = {
            "hero": hero_name,
            "action": decision.get("action", "?"),
            "target": decision.get("target", ""),
            "reasoning": decision.get("reasoning", "")[:50],
            "time": pygame.time.get_ticks()
        }
        self.decision_log.append(entry)
        
        # Keep only recent entries
        if len(self.decision_log) > self.max_log_entries:
            self.decision_log.pop(0)
    
    def render(self, surface: pygame.Surface, game_state: dict):
        """Render the debug panel."""
        if not self.visible:
            return
        
        # Panel background
        panel_surf = pygame.Surface((self.panel_width, self.panel_height), pygame.SRCALPHA)
        panel_surf.fill((*COLOR_UI_BG, 230))
        pygame.draw.rect(panel_surf, COLOR_UI_BORDER, 
                        (0, 0, self.panel_width, self.panel_height), 2)
        
        y = 10
        
        # Title
        title = self.font_title.render("Debug Panel (F1 to toggle)", True, COLOR_WHITE)
        panel_surf.blit(title, (10, y))
        y += 30
        
        # Game stats
        pygame.draw.line(panel_surf, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
        y += 10
        
        stats_text = self.font_normal.render("Game Stats", True, COLOR_GOLD)
        panel_surf.blit(stats_text, (10, y))
        y += 20
        
        heroes = game_state.get("heroes", [])
        enemies = game_state.get("enemies", [])
        
        stats = [
            f"Heroes: {len([h for h in heroes if h.is_alive])}/{len(heroes)}",
            f"Enemies: {len([e for e in enemies if e.is_alive])}",
            f"Wave: {game_state.get('wave', 1)}",
            f"Gold: {game_state.get('gold', 0)}",
        ]
        
        for stat in stats:
            text = self.font_small.render(stat, True, COLOR_WHITE)
            panel_surf.blit(text, (20, y))
            y += 15
        
        y += 10
        
        # LLM Decision Log
        pygame.draw.line(panel_surf, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
        y += 10
        
        log_title = self.font_normal.render("LLM Decision Log", True, COLOR_GOLD)
        panel_surf.blit(log_title, (10, y))
        y += 20
        
        if not self.decision_log:
            text = self.font_small.render("No decisions yet...", True, (150, 150, 150))
            panel_surf.blit(text, (20, y))
        else:
            for entry in reversed(self.decision_log[-8:]):
                # Format: "HeroName: action -> target"
                action_text = f"{entry['hero']}: {entry['action']}"
                if entry['target']:
                    action_text += f" -> {entry['target']}"
                
                text = self.font_small.render(action_text, True, COLOR_GREEN)
                panel_surf.blit(text, (20, y))
                y += 12
                
                # Reasoning (truncated)
                if entry['reasoning']:
                    reason = self.font_small.render(f"  \"{entry['reasoning']}\"", True, (180, 180, 180))
                    panel_surf.blit(reason, (20, y))
                    y += 12
                
                y += 3
        
        # Hero details if selected
        selected = game_state.get("selected_hero")
        if selected and y < self.panel_height - 60:
            y += 10
            pygame.draw.line(panel_surf, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
            y += 10
            
            hero_title = self.font_normal.render(f"Selected: {selected.name}", True, COLOR_GOLD)
            panel_surf.blit(hero_title, (10, y))
            y += 20
            
            details = [
                f"State: {selected.state.name}",
                f"Personality: {selected.personality}",
                f"Potions: {getattr(selected, 'potions', 0)}",
                f"Last LLM: {selected.last_llm_action.get('action', 'None') if selected.last_llm_action else 'None'}",
            ]
            
            for detail in details:
                text = self.font_small.render(detail, True, COLOR_WHITE)
                panel_surf.blit(text, (20, y))
                y += 15
        
        surface.blit(panel_surf, (self.panel_x, self.panel_y))

