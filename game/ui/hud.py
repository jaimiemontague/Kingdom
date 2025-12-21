"""
Heads-up display for game information.
"""
import pygame
from game.sim.timebase import now_ms as sim_now_ms
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
        self.font_tiny = pygame.font.Font(None, 16)

        # Help/controls overlay (kept lightweight; toggled by engine)
        self.show_help = True
        
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

    def toggle_help(self):
        """Toggle help/controls visibility."""
        self.show_help = not self.show_help

    def _compute_hero_intent(self, hero) -> str:
        """
        Best-effort "intent" label derived from current state/target.
        This is intentionally UI-only (safe fallback until intent taxonomy is standardized).
        """
        # Bounty pursuit is encoded as hero.target dict {"type": "bounty", ...}
        try:
            if isinstance(getattr(hero, "target", None), dict) and hero.target.get("type") == "bounty":
                btype = hero.target.get("bounty_type", "bounty")
                if btype == "attack_lair":
                    return "Attacking lair (bounty)"
                if btype == "defend_building":
                    return "Defending building (bounty)"
                return "Pursuing bounty"
        except Exception:
            pass

        state = getattr(getattr(hero, "state", None), "name", "") or ""
        state = state.upper()
        if state == "FIGHTING":
            return "Engaging enemy"
        if state == "SHOPPING":
            return "Shopping"
        if state == "RETREATING":
            return "Returning to safety"
        if state == "RESTING":
            return "Resting"
        if state == "MOVING":
            return "Moving"
        if state == "IDLE":
            return "Idle"
        return state.title() if state else "Idle"

    def _format_last_decision(self, hero) -> tuple[str, tuple]:
        """Format last decision line + suggested color."""
        action = None
        target = ""
        reason = ""
        try:
            d = getattr(hero, "last_llm_action", None) or {}
            if isinstance(d, dict):
                action = d.get("action", None)
                target = d.get("target", "") if isinstance(d.get("target", ""), str) else ""
                reason = d.get("reasoning", "") if isinstance(d.get("reasoning", ""), str) else ""
        except Exception:
            action = None

        if not action:
            return "Last decision: (none yet)", (150, 150, 150)

        # Age (ms) is tracked on the hero; treat 0 as unknown.
        age_s = None
        try:
            t_ms = int(getattr(hero, "last_llm_decision_time", 0) or 0)
            if t_ms > 0:
                age_s = max(0.0, (float(sim_now_ms()) - float(t_ms)) / 1000.0)
        except Exception:
            age_s = None

        parts = [str(action)]
        if target:
            parts.append(f"→ {target}")
        if age_s is not None:
            parts.append(f"({age_s:.0f}s ago)")
        head = " ".join(parts)

        # Keep reasoning short and readable.
        reason = (reason or "").strip()
        if reason:
            reason = reason.replace("\n", " ")
            if len(reason) > 70:
                reason = reason[:67].rstrip() + "..."
            return f"Last decision: {head} — {reason}", COLOR_WHITE

        return f"Last decision: {head}", COLOR_WHITE
    
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
        # Context banner: placement mode
        placing = game_state.get("placing_building_type")
        if placing:
            placing_name = str(placing).replace("_", " ").title()
            banner = f"Placing: {placing_name}  (LMB: place, ESC: cancel)"
            text = self.font_medium.render(banner, True, COLOR_WHITE)
            surface.blit(text, (20, self.top_bar_height + 8))

        # Help/controls overlay (toggle via F3)
        if self.show_help:
            self._render_help(surface, origin=(self.screen_width - 310, 5))
        else:
            hint = self.font_small.render("F3: Help", True, (180, 180, 180))
            surface.blit(hint, (self.screen_width - hint.get_width() - 12, 12))
        
        # Render messages
        self.render_messages(surface)
        
        # Render selected hero info
        selected = game_state.get("selected_hero")
        if selected:
            self.render_hero_panel(surface, selected)

    def _render_help(self, surface: pygame.Surface, origin: tuple[int, int]):
        """Render a compact controls/help panel."""
        x0, y0 = origin
        pad = 10
        w = 300
        lines = [
            ("Controls (F3 to hide)", COLOR_GOLD),
            ("Build:", (200, 200, 200)),
            ("1 Warrior  2 Market  3 Ranger  4 Rogue  5 Wizard", COLOR_WHITE),
            ("6 Blacksmith  7 Inn  8 Trading Post", COLOR_WHITE),
            ("T Temple  G Gnome  E Elf  V Dwarf", COLOR_WHITE),
            ("U Guardhouse  Y Ballista  O Wizard Tower", COLOR_WHITE),
            ("F Fairgrounds  I Library  R Royal Gardens", COLOR_WHITE),
            ("Actions:", (200, 200, 200)),
            ("H Hire hero (select a built guild first)", COLOR_WHITE),
            ("B Place bounty ($50)   P Use potion (selected hero)", COLOR_WHITE),
            ("View:", (200, 200, 200)),
            ("Space center castle  ESC pause/cancel", COLOR_WHITE),
            ("WASD pan  Wheel or +/- zoom  F1 debug  F2 perf", COLOR_WHITE),
        ]

        # Background box sized by content
        h = pad * 2 + len(lines) * 16 + 6
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((*COLOR_UI_BG, 235))
        pygame.draw.rect(panel, COLOR_UI_BORDER, (0, 0, w, h), 2)

        y = pad
        for text, color in lines:
            t = self.font_tiny.render(text, True, color)
            panel.blit(t, (pad, y))
            y += 16

        surface.blit(panel, (x0, y0))
    
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
        intent = self._compute_hero_intent(hero)
        intent_text = self.font_small.render(f"Intent: {intent}", True, (200, 200, 200))
        surface.blit(intent_text, (panel_x + 10, y))
        y += 16

        state_text = self.font_small.render(f"State: {hero.state.name}", True, (170, 170, 170))
        surface.blit(state_text, (panel_x + 10, y))
        y += 16

        decision_line, decision_color = self._format_last_decision(hero)
        # Keep within panel width: simple truncation.
        max_chars = 48
        if len(decision_line) > max_chars:
            decision_line = decision_line[: max_chars - 3].rstrip() + "..."
        decision_text = self.font_tiny.render(decision_line, True, decision_color)
        surface.blit(decision_text, (panel_x + 10, y))

