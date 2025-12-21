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

        # Cache (avoid per-frame Surface allocations when visible)
        self._panel_cache = None  # pygame.Surface
        self._panel_dirty = True
        self._next_update_ms = 0
        self._close_rect = pygame.Rect(0, 0, 0, 0)  # in screen coords
        self._close_x_surf = self.font_small.render("X", True, COLOR_WHITE)
        
    def toggle(self):
        """Toggle panel visibility."""
        self.visible = not self.visible
        if self.visible:
            self._panel_dirty = True
    
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
        self._panel_dirty = True

    def handle_click(self, mouse_pos: tuple[int, int]) -> bool:
        """Handle clicks on the debug panel (close button + consume clicks inside panel)."""
        if not self.visible:
            return False
        x, y = int(mouse_pos[0]), int(mouse_pos[1])
        panel_rect = pygame.Rect(self.panel_x, self.panel_y, self.panel_width, self.panel_height)
        if not panel_rect.collidepoint((x, y)):
            return False
        # Close button
        if self._close_rect.collidepoint((x, y)):
            self.visible = False
            return True
        # Consume clicks inside debug UI to avoid selecting heroes/buildings behind it.
        return True
    
    def render(self, surface: pygame.Surface, game_state: dict):
        """Render the debug panel."""
        if not self.visible:
            return

        # Position: keep below top bar where possible (HUD owns exact layout).
        # Avoid hard dependency; just don't sit at y=0.
        self.panel_x = max(10, int(self.panel_x))
        self.panel_y = max(60, int(self.panel_y))

        now_ms = pygame.time.get_ticks()
        if self._next_update_ms == 0:
            self._next_update_ms = now_ms
        if now_ms >= self._next_update_ms:
            self._next_update_ms = now_ms + 250
            self._panel_dirty = True

        # Close button rect in screen coords (top-right inside panel)
        size = 18
        self._close_rect = pygame.Rect(self.panel_x + self.panel_width - size - 8, self.panel_y + 8, size, size)

        if self._panel_cache is None or self._panel_dirty:
            self._panel_dirty = False
            panel_surf = pygame.Surface((self.panel_width, self.panel_height), pygame.SRCALPHA)
            panel_surf.fill((*COLOR_UI_BG, 230))
            pygame.draw.rect(panel_surf, COLOR_UI_BORDER, (0, 0, self.panel_width, self.panel_height), 2)

            # Title + close hint (X)
            y = 10
            title = self.font_title.render("Debug Panel", True, COLOR_WHITE)
            panel_surf.blit(title, (10, y))

            # Close button (drawn into cached surface; hover handled by engine click)
            close_local = pygame.Rect(self.panel_width - size - 8, 8, size, size)
            pygame.draw.rect(panel_surf, (45, 45, 55), close_local)
            pygame.draw.rect(panel_surf, COLOR_UI_BORDER, close_local, 2)
            panel_surf.blit(self._close_x_surf, (close_local.centerx - self._close_x_surf.get_width() // 2, close_local.centery - self._close_x_surf.get_height() // 2))

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
                f"Heroes: {len([h for h in heroes if getattr(h, 'is_alive', True)])}/{len(heroes)}",
                f"Enemies: {len([e for e in enemies if getattr(e, 'is_alive', True)])}",
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
                    action_text = f"{entry['hero']}: {entry['action']}"
                    if entry['target']:
                        action_text += f" -> {entry['target']}"
                    text = self.font_small.render(action_text, True, COLOR_GREEN)
                    panel_surf.blit(text, (20, y))
                    y += 12
                    if entry['reasoning']:
                        reason = self.font_small.render(f"  \"{entry['reasoning']}\"", True, (180, 180, 180))
                        panel_surf.blit(reason, (20, y))
                        y += 12
                    y += 3

            self._panel_cache = panel_surf

        surface.blit(self._panel_cache, (self.panel_x, self.panel_y))

