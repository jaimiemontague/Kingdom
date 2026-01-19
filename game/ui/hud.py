"""
Heads-up display for game information.
"""
import pygame
from game.sim.timebase import now_ms as sim_now_ms
from game.ui.theme import UITheme
from game.ui.widgets import Panel, Tooltip, IconButton, NineSlice, load_image_cached
from config import (
    COLOR_UI_BG, COLOR_UI_BORDER, COLOR_GOLD,
    COLOR_WHITE, COLOR_RED, COLOR_GREEN, BUILDING_COSTS, HERO_HIRE_COST
)


class HUD:
    """Displays game information to the player."""
    
    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        self.theme = UITheme()
        # Milestone 4 (UI skin, code-only): 2-layer frame + top-left lighting highlight.
        # Matches `docs/art/wk3_major_graphics_target.md` swatches:
        # - UI panel background: #282832 (40,40,50) == COLOR_UI_BG
        # - UI border: #505064 (80,80,100) == COLOR_UI_BORDER
        # - Outline (near-black): #141419
        self._frame_outer = (0x14, 0x14, 0x19)
        self._frame_inner = (0x50, 0x50, 0x64)
        # Subtle highlight for lit edges (top-left). Keep low-noise and non-white.
        self._frame_highlight = (0x6B, 0x6B, 0x84)

        # HUD dimensions (computed from actual screen size each frame; these are defaults)
        self.top_bar_height = int(getattr(self.theme, "top_bar_h", 48))
        self.bottom_bar_height = int(getattr(self.theme, "bottom_bar_h", 96))
        self.side_panel_width = 360  # computed per-frame; this is just an initial value
        
        # Fonts
        self.font_large = pygame.font.Font(None, 32)
        self.font_medium = pygame.font.Font(None, 24)
        self.font_small = pygame.font.Font(None, 18)
        self.font_tiny = pygame.font.Font(None, 16)

        # Help/controls overlay (kept lightweight; toggled by engine)
        # PM decision (wk1): default OFF + persistent hint when hidden.
        self.show_help = False
        self._help_panel_cache = None  # pygame.Surface built once (avoid per-frame allocations)
        self._help_hint_cache = self.font_small.render("F3: Help", True, (180, 180, 180))

        # WK7 mid-sprint: right panel toggle (Tab)
        self.right_panel_visible = False
        self._panel_hint_cache = self.font_small.render("Tab: Panel", True, (180, 180, 180))

        # Session start (sim-time) for one-time / early hints.
        self._session_start_ms = int(sim_now_ms())
        self._bounty_hint_cache = None

        # Cached hero panel lines (avoid per-frame allocations for slow-changing debug text)
        self._hero_line_cache = {}  # key -> pygame.Surface

        # Cached value text surfaces (avoid per-frame font.render churn)
        self._value_text_cache = {}  # key -> (last_value, surf)
        self._last_placing = None
        self._placing_surf = None

        # UI panels (cached surfaces)
        # CC0 UI pack textures (WK7_R6)
        self._panel_tex_top = "assets/ui/kingdomsim_ui_cc0/panels/panel_top.png"
        self._panel_tex_bottom = "assets/ui/kingdomsim_ui_cc0/panels/panel_bottom.png"
        self._panel_tex_right = "assets/ui/kingdomsim_ui_cc0/panels/panel_right.png"
        self._panel_tex_modal = "assets/ui/kingdomsim_ui_cc0/panels/panel_modal.png"
        self._button_tex_normal = "assets/ui/kingdomsim_ui_cc0/buttons/button_normal.png"
        self._button_tex_hover = "assets/ui/kingdomsim_ui_cc0/buttons/button_hover.png"
        self._button_tex_pressed = "assets/ui/kingdomsim_ui_cc0/buttons/button_pressed.png"
        self._panel_slice_border = 8
        self._button_slice_border = 6

        self._panel_top = Panel(
            pygame.Rect(0, 0, 1, 1),
            self.theme.panel_bg,
            self._frame_outer,
            alpha=int(self.theme.panel_alpha),
            border_w=2,
            inner_border_rgb=self._frame_inner,
            inner_border_w=1,
            highlight_rgb=self._frame_highlight,
            highlight_w=1,
            texture_path=self._panel_tex_top,
            slice_border=self._panel_slice_border,
        )
        self._panel_bottom = Panel(
            pygame.Rect(0, 0, 1, 1),
            self.theme.panel_bg,
            self._frame_outer,
            alpha=int(self.theme.panel_alpha),
            border_w=2,
            inner_border_rgb=self._frame_inner,
            inner_border_w=1,
            highlight_rgb=self._frame_highlight,
            highlight_w=1,
            texture_path=self._panel_tex_bottom,
            slice_border=self._panel_slice_border,
        )
        self._panel_right = Panel(
            pygame.Rect(0, 0, 1, 1),
            self.theme.panel_bg,
            self._frame_outer,
            alpha=int(self.theme.panel_alpha),
            border_w=2,
            inner_border_rgb=self._frame_inner,
            inner_border_w=1,
            highlight_rgb=self._frame_highlight,
            highlight_w=1,
            texture_path=self._panel_tex_right,
            slice_border=self._panel_slice_border,
        )
        self._panel_minimap = Panel(
            pygame.Rect(0, 0, 1, 1),
            self.theme.panel_bg,
            self._frame_outer,
            alpha=int(self.theme.panel_alpha),
            border_w=2,
            inner_border_rgb=self._frame_inner,
            inner_border_w=1,
            highlight_rgb=self._frame_highlight,
            highlight_w=1,
            texture_path=self._panel_tex_bottom,
            slice_border=self._panel_slice_border,
        )
        self._tooltip = Tooltip(COLOR_UI_BG, COLOR_UI_BORDER, alpha=240)
        self._buttons = []  # list[IconButton]
        # Command bar icons (cached)
        self._icon_build = load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_build.png", (16, 16))
        self._icon_hire = load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_hire.png", (16, 16))
        self._icon_bounty = load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_bounty.png", (16, 16))

        # Click targets (computed during render; read by engine input handler)
        self.quit_rect: pygame.Rect | None = None
        self.right_close_rect: pygame.Rect | None = None

        # Messages (top-left transient text)
        self.messages = []
        self.message_duration = 3000  # ms

    def _cached_line(self, key: tuple, text: str, color: tuple):
        """
        Cache a rendered text line by (key, text, color).
        This prevents per-frame Surface churn for debug-only indicators.
        """
        cache_key = (key, text, color)
        surf = self._hero_line_cache.get(cache_key)
        if surf is None:
            surf = self.font_tiny.render(text, True, color)
            # Simple bound to avoid unbounded growth in long sessions.
            if len(self._hero_line_cache) > 64:
                self._hero_line_cache.clear()
            self._hero_line_cache[cache_key] = surf
        return surf

    def _cached_value_text(self, key: str, value, text: str, font: pygame.font.Font, color: tuple):
        """Cache a rendered value text surface by key + last_value."""
        last = self._value_text_cache.get(key)
        if last is not None:
            last_value, surf = last
            if last_value == value and surf is not None:
                return surf
        surf = font.render(text, True, color)
        if len(self._value_text_cache) > 64:
            self._value_text_cache.clear()
        self._value_text_cache[key] = (value, surf)
        return surf

    def _compute_layout(self, surface: pygame.Surface):
        """Compute UI rects from the actual render surface size (no hardcoded 1920×1080)."""
        w, h = surface.get_width(), surface.get_height()
        self.screen_width = int(w)
        self.screen_height = int(h)

        top_h = int(getattr(self.theme, "top_bar_h", 48))
        bottom_h = int(getattr(self.theme, "bottom_bar_h", 96))
        margin = int(getattr(self.theme, "margin", 8))
        gutter = int(getattr(self.theme, "gutter", 8))

        right_w = int(max(getattr(self.theme, "right_panel_min_w", 320), min(getattr(self.theme, "right_panel_max_w", 420), int(w * 0.24))))
        right_w = int(max(280, min(right_w, w - 2 * margin)))  # clamp for small screens
        if not self.right_panel_visible:
            right_w = 0
        self.side_panel_width = right_w

        top = pygame.Rect(0, 0, w, top_h)
        bottom = pygame.Rect(0, h - bottom_h, w, bottom_h)
        right = pygame.Rect(w - right_w, top_h, right_w, max(0, h - top_h - bottom_h))

        # Minimap lives inside the bottom bar (bottom-left square).
        mm_size = max(64, bottom_h - 2 * margin)
        minimap = pygame.Rect(margin, bottom.y + margin, mm_size, mm_size)

        # Command bar area is the remaining bottom bar space excluding minimap and right panel.
        cmd_x = minimap.right + gutter
        cmd_w = max(0, (w - right_w) - cmd_x - gutter)
        cmd = pygame.Rect(cmd_x, bottom.y + margin, cmd_w, mm_size)

        return top, bottom, right, minimap, cmd
        
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
        # Nothing else to do; cached help panel surface is re-used.

    def toggle_right_panel(self):
        """Toggle the right-side panel visibility."""
        self.right_panel_visible = not self.right_panel_visible

    def on_resize(self, screen_width: int, screen_height: int):
        """Update cached screen dimensions after a resize."""
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)

    def _compute_hero_intent(self, hero) -> str:
        """
        Best-effort "intent" label derived from current state/target.
        This is intentionally UI-only (safe fallback until intent taxonomy is standardized).
        """
        # Preferred: hero intent snapshot contract (works in no-LLM + LLM).
        try:
            if hasattr(hero, "get_intent_snapshot"):
                snap = hero.get_intent_snapshot(now_ms=int(sim_now_ms()))
                if isinstance(snap, dict):
                    intent = str(snap.get("intent", "") or "")
                    if intent:
                        mapping = {
                            "idle": "Idle",
                            "pursuing_bounty": "Pursuing bounty",
                            "shopping": "Shopping",
                            "returning_to_safety": "Returning to safety",
                            "engaging_enemy": "Engaging enemy",
                            "defending_building": "Defending building",
                            "attacking_lair": "Attacking lair",
                        }
                        return mapping.get(intent, intent.replace("_", " ").title())
        except Exception:
            pass

        # Fallback: Bounty pursuit is encoded as hero.target dict {"type": "bounty", ...}
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
        age_s = None

        # Preferred: hero intent snapshot contract (works in no-LLM + LLM).
        try:
            if hasattr(hero, "get_intent_snapshot"):
                snap = hero.get_intent_snapshot(now_ms=int(sim_now_ms()))
                if isinstance(snap, dict):
                    last_decision = snap.get("last_decision", None)
                    if isinstance(last_decision, dict):
                        action = last_decision.get("action", None)
                        reason = last_decision.get("reason", "") if isinstance(last_decision.get("reason", ""), str) else ""
                        age_ms = last_decision.get("age_ms", None)
                        if age_ms is not None:
                            try:
                                age_s = max(0.0, float(age_ms) / 1000.0)
                            except Exception:
                                age_s = None
        except Exception:
            pass

        # Fallback: legacy LLM decision dict
        try:
            d = getattr(hero, "last_llm_action", None) or {}
            if isinstance(d, dict):
                action = action or d.get("action", None)
                target = d.get("target", "") if isinstance(d.get("target", ""), str) else ""
                reason = reason or (d.get("reasoning", "") if isinstance(d.get("reasoning", ""), str) else "")
        except Exception:
            action = action

        if not action:
            return "Last decision: (none yet)", (150, 150, 150)

        # Age: prefer contract age_ms; fallback to legacy last_llm_decision_time.
        if age_s is None:
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
        top, bottom, right, minimap, cmd = self._compute_layout(surface)

        # Panels (cached surfaces)
        self._panel_top.set_rect(top)
        self._panel_bottom.set_rect(bottom)
        self._panel_right.set_rect(right)
        self._panel_minimap.set_rect(minimap)
        self._panel_top.render(surface)
        self._panel_bottom.render(surface)
        if self.right_panel_visible:
            self._panel_right.render(surface)
        self._panel_minimap.render(surface)

        # Quit button (top-right; player-manageable UI)
        self._render_quit_button(surface, top_rect=top)
        
        # Top bar stats (cache text on value change)
        gold = int(game_state.get("gold", 0) or 0)
        heroes = game_state.get("heroes", [])
        enemies = game_state.get("enemies", [])
        alive_heroes = sum(1 for h in heroes if getattr(h, "is_alive", True))
        alive_enemies = sum(1 for e in enemies if getattr(e, "is_alive", True))
        wave = int(game_state.get("wave", 1) or 1)

        gold_surf = self._cached_value_text("top_gold", gold, f"Gold: {gold}", self.theme.font_title, COLOR_GOLD)
        heroes_surf = self._cached_value_text("top_heroes", alive_heroes, f"Heroes: {alive_heroes}", self.theme.font_body, COLOR_WHITE)
        enemies_surf = self._cached_value_text("top_enemies", alive_enemies, f"Enemies: {alive_enemies}", self.theme.font_body, COLOR_RED)
        wave_surf = self._cached_value_text("top_wave", wave, f"Wave: {wave}", self.theme.font_body, COLOR_WHITE)

        x = int(self.theme.margin)
        y = int((top.height - gold_surf.get_height()) // 2)
        surface.blit(gold_surf, (x, y))
        x += gold_surf.get_width() + int(self.theme.gutter) * 2
        surface.blit(heroes_surf, (x, y + 2))
        x += heroes_surf.get_width() + int(self.theme.gutter)
        surface.blit(enemies_surf, (x, y + 2))
        x += enemies_surf.get_width() + int(self.theme.gutter)
        surface.blit(wave_surf, (x, y + 2))
        
        # Context banner: placement mode (rendered near the bottom bar, above command buttons)
        placing = game_state.get("placing_building_type")
        if placing != self._last_placing:
            self._last_placing = placing
            if placing:
                placing_name = str(placing).replace("_", " ").title()
                banner = f"Placing: {placing_name} (LMB: place, ESC: cancel)"
                self._placing_surf = self.theme.font_body.render(banner, True, COLOR_WHITE)
            else:
                self._placing_surf = None
        if self._placing_surf is not None:
            surface.blit(self._placing_surf, (int(self.theme.margin), bottom.y - self._placing_surf.get_height() - 2))

        # Help/controls overlay (toggle via F3)
        if self.show_help:
            self._render_help(surface, origin=(self.screen_width - 310, 5))

        # Early, non-spammy bounty hint (addresses WK1-BUG-002 discoverability).
        # Show until the player places their first bounty, and only for the first ~90s.
        try:
            now_ms = int(sim_now_ms())
            elapsed_ms = now_ms - int(getattr(self, "_session_start_ms", now_ms))
            has_any_bounty = bool(game_state.get("bounties", []))
            if (not has_any_bounty) and elapsed_ms < 90000 and (not self.show_help):
                if self._bounty_hint_cache is None:
                    self._bounty_hint_cache = self.font_small.render(
                        "Tip: Press B to place a bounty at mouse (Shift/Ctrl: bigger).",
                        True,
                        (220, 220, 255),
                    )
                surface.blit(self._bounty_hint_cache, (20, self.top_bar_height + 28))
        except Exception:
            pass
        
        # Render messages
        self.render_messages(surface)
        
        # Bottom bar: command buttons (skeleton only; keyboard controls remain authoritative)
        self._render_command_bar(surface, game_state, cmd_rect=cmd)

        # Right panel: selected entity summary (hero preferred; else building; else placeholder)
        selected_hero = game_state.get("selected_hero")
        selected_building = game_state.get("selected_building")

        # Right panel close button (only when something is selected)
        self.right_close_rect = None
        if self.right_panel_visible:
            if selected_hero is not None or selected_building is not None:
                self._render_right_close_button(surface, right_rect=right)

            if selected_hero:
                self.render_hero_panel(surface, selected_hero, debug_ui=bool(game_state.get("debug_ui", False)), rect=right)
            elif selected_building is not None:
                self._render_building_summary(surface, selected_building, rect=right)
            else:
                empty = self._cached_value_text("right_none", 1, "Select a hero or building", self.theme.font_body, (180, 180, 180))
                pad = self._right_panel_top_pad(right)
                surface.blit(empty, (right.x + int(self.theme.margin), right.y + pad))

        # Minimap placeholder label (Build A skeleton; real minimap in later iteration)
        mm_label = self._cached_value_text("minimap_lbl", 1, "Minimap", self.theme.font_small, (200, 200, 200))
        surface.blit(mm_label, (minimap.x + 6, minimap.y + 6))

    def handle_click(self, mouse_pos: tuple[int, int], game_state: dict) -> str | None:
        """
        Handle HUD click targets only. Returns an action string if handled:
        - "quit"
        - "close_selection"
        - "build_menu_toggle"
        """
        x, y = int(mouse_pos[0]), int(mouse_pos[1])
        if self.quit_rect is not None and self.quit_rect.collidepoint((x, y)):
            return "quit"

        if self.right_close_rect is not None and self.right_close_rect.collidepoint((x, y)):
            # Close selected hero/building panel
            return "close_selection"
        
        # Check Build button click
        if self._buttons:
            build_button = self._buttons[0]  # First button is Build
            if build_button.hit_test((x, y)):
                return "build_menu_toggle"

        return None

    def _render_quit_button(self, surface: pygame.Surface, top_rect: pygame.Rect):
        """Render a clear Quit button in the top bar (cached label)."""
        label = self._cached_value_text("btn_quit_lbl", 1, "Quit", self.theme.font_small, (240, 240, 240))
        pad_x = 10
        pad_y = 6
        w = label.get_width() + pad_x * 2
        h = label.get_height() + pad_y * 2
        x = int(top_rect.right - w - int(self.theme.margin))
        y = int(top_rect.y + (top_rect.height - h) // 2)
        rect = pygame.Rect(x, y, w, h)
        self.quit_rect = rect

        mouse = pygame.mouse.get_pos()
        hover = rect.collidepoint(mouse)
        bg = (70, 45, 45) if hover else (55, 40, 40)
        self._draw_button_frame(surface, rect, bg_rgb=bg, hovered=hover)
        surface.blit(label, (rect.x + pad_x, rect.y + pad_y))

    def _render_right_close_button(self, surface: pygame.Surface, right_rect: pygame.Rect):
        """Render an X close button for the right info panel (selected entity panel)."""
        x_surf = self._cached_value_text("btn_close_x", 1, "X", self.theme.font_small, (240, 240, 240))
        size = max(18, x_surf.get_height() + 6)
        rect = pygame.Rect(int(right_rect.right - size - 6), int(right_rect.y + 6), int(size), int(size))
        self.right_close_rect = rect

        mouse = pygame.mouse.get_pos()
        hover = rect.collidepoint(mouse)
        bg = (60, 60, 70) if hover else (45, 45, 55)
        self._draw_button_frame(surface, rect, bg_rgb=bg, hovered=hover)
        surface.blit(x_surf, (rect.centerx - x_surf.get_width() // 2, rect.centery - x_surf.get_height() // 2))

    def _draw_button_frame(self, surface: pygame.Surface, rect: pygame.Rect, bg_rgb: tuple[int, int, int], hovered: bool = False):
        """Shared button frame styling (Quit / X / command buttons)."""
        tex = self._button_tex_hover if hovered else self._button_tex_normal
        if NineSlice.render(surface, rect, tex, border=self._button_slice_border):
            return
        pygame.draw.rect(surface, bg_rgb, rect)
        # Outer near-black outline
        pygame.draw.rect(surface, self._frame_outer, rect, 2)
        # Inner border + top-left highlight
        inner = rect.inflate(-4, -4)
        if inner.width > 0 and inner.height > 0:
            pygame.draw.rect(surface, self._frame_inner, inner, 1)
            pygame.draw.line(surface, self._frame_highlight, (inner.left + 1, inner.top + 1), (inner.right - 2, inner.top + 1), 1)
            pygame.draw.line(surface, self._frame_highlight, (inner.left + 1, inner.top + 1), (inner.left + 1, inner.bottom - 2), 1)

    def _render_command_bar(self, surface: pygame.Surface, game_state: dict, cmd_rect: pygame.Rect):
        """Render the bottom command bar skeleton (no click handling yet)."""
        if cmd_rect.width <= 0 or cmd_rect.height <= 0:
            return

        mouse = pygame.mouse.get_pos()
        gutter = int(self.theme.gutter)

        # Build A: 3 core actions only. Hotkeys remain in engine.
        if not self._buttons or getattr(self, "_buttons_last_size", None) != (cmd_rect.width, cmd_rect.height):
            self._buttons_last_size = (cmd_rect.width, cmd_rect.height)
            self._buttons = []
            bw = min(140, max(110, int(cmd_rect.width / 3) - gutter))
            bh = int(cmd_rect.height)
            x = int(cmd_rect.x)
            y = int(cmd_rect.y)
            self._buttons.append(
                IconButton(
                    rect=pygame.Rect(x, y, bw, bh),
                    title="Build",
                    hotkey="1-8/T/G/E/V/U/Y/O/F/I/R",
                    tooltip="Build\nHotkeys: 1-8, T,G,E,V,U,Y,O,F,I,R\nCost shown in top messages on fail.",
                )
            )
            x += bw + gutter
            self._buttons.append(
                IconButton(
                    rect=pygame.Rect(x, y, bw, bh),
                    title="Hire",
                    hotkey="H",
                    tooltip=f"Hire Hero\nHotkey: H\nCost: ${int(HERO_HIRE_COST)} (select a built guild first)",
                )
            )
            x += bw + gutter
            self._buttons.append(
                IconButton(
                    rect=pygame.Rect(x, y, bw, bh),
                    title="Bounty",
                    hotkey="B",
                    tooltip="Place Bounty\nHotkey: B\nPlace at mouse cursor\nShift/Ctrl: bigger (cost=reward)",
                )
            )

        hovered = None
        for btn in self._buttons:
            is_hover = btn.hit_test(mouse)
            if is_hover:
                hovered = btn
            # Button frame (textured nine-slice, cached)
            bg = (70, 80, 100) if is_hover else (45, 45, 60)
            self._draw_button_frame(surface, btn.rect, bg_rgb=bg, hovered=is_hover)

            # Label (cached by title)
            # WK7: Better button text spacing and positioning
            title_surf = self._cached_value_text(("btn_t", btn.title), 1, btn.title, self.theme.font_body, COLOR_WHITE if not is_hover else (240, 240, 255))
            hk_surf = self._cached_value_text(("btn_hk", btn.hotkey), 1, btn.hotkey, self.theme.font_small, (200, 200, 200) if is_hover else (180, 180, 180))
            icon = None
            if btn.title == "Build":
                icon = self._icon_build
            elif btn.title == "Hire":
                icon = self._icon_hire
            elif btn.title == "Bounty":
                icon = self._icon_bounty
            text_pad = 12
            icon_pad = 0
            if icon is not None:
                icon_x = btn.rect.x + text_pad
                icon_y = btn.rect.y + (btn.rect.height - icon.get_height()) // 2
                surface.blit(icon, (icon_x, icon_y))
                icon_pad = icon.get_width() + 6
            text_x = btn.rect.x + text_pad + icon_pad
            surface.blit(title_surf, (text_x, btn.rect.y + 10))
            surface.blit(hk_surf, (text_x, btn.rect.y + 10 + title_surf.get_height() + 4))

        # Tooltip (cached; built only when hovered text changes)
        if hovered is not None:
            self._tooltip.set_text(self.theme.font_small, hovered.tooltip, (230, 230, 230))
            self._tooltip.render(surface, mouse[0] + 12, mouse[1] + 12)
        else:
            self._tooltip.set_text(self.theme.font_small, "", (230, 230, 230))

    def _right_panel_top_pad(self, rect: pygame.Rect) -> int:
        pad = int(self.theme.margin)
        if self.right_close_rect is not None and self.right_close_rect.colliderect(rect):
            pad = max(pad, int(self.right_close_rect.height) + 10)
        return pad

    def _render_building_summary(self, surface: pygame.Surface, building, rect: pygame.Rect):
        """Minimal right-panel building summary for Build A."""
        # WK7: Better internal padding for readability
        x = rect.x + int(self.theme.margin)
        y = rect.y + self._right_panel_top_pad(rect)
        btype = str(getattr(building, "building_type", building.__class__.__name__) or "")
        title = self._cached_value_text(("bsel", btype), 1, btype.replace("_", " ").title(), self.theme.font_title, COLOR_WHITE)
        surface.blit(title, (x, y))
        y += title.get_height() + 10  # Increased from 6 for better spacing
        hp = int(getattr(building, "hp", 0) or 0)
        mhp = int(getattr(building, "max_hp", 0) or 0)
        hp_surf = self._cached_value_text(("bhp", id(building), hp, mhp), 1, f"HP: {hp}/{mhp}", self.theme.font_body, (200, 200, 200))
        surface.blit(hp_surf, (x, y))

    def _render_help(self, surface: pygame.Surface, origin: tuple[int, int]):
        """Render a compact controls/help panel."""
        x0, y0 = origin
        if self._help_panel_cache is None:
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
                ("B Bounty at mouse (cost=reward). Shift/Ctrl: bigger", COLOR_WHITE),
                ("P Use potion (selected hero)", COLOR_WHITE),
                ("View:", (200, 200, 200)),
                ("Space center castle  ESC pause/cancel", COLOR_WHITE),
                ("WASD pan  Wheel or +/- zoom  F1 debug  F2 perf", COLOR_WHITE),
            ]

            # Background box sized by content
            h = pad * 2 + len(lines) * 16 + 6
            panel = pygame.Surface((w, h), pygame.SRCALPHA)
            panel.fill((*COLOR_UI_BG, 235))
            # 2-layer frame + top-left highlight language (cached once)
            pygame.draw.rect(panel, self._frame_outer, (0, 0, w, h), 2)
            inner = pygame.Rect(2, 2, w - 4, h - 4)
            if inner.width > 0 and inner.height > 0:
                pygame.draw.rect(panel, self._frame_inner, inner, 1)
                pygame.draw.line(panel, self._frame_highlight, (inner.left + 1, inner.top + 1), (inner.right - 2, inner.top + 1), 1)
                pygame.draw.line(panel, self._frame_highlight, (inner.left + 1, inner.top + 1), (inner.left + 1, inner.bottom - 2), 1)

            y = pad
            for text, color in lines:
                t = self.font_tiny.render(text, True, color)
                panel.blit(t, (pad, y))
                y += 16

            self._help_panel_cache = panel

        surface.blit(self._help_panel_cache, (x0, y0))
    
    def render_messages(self, surface: pygame.Surface):
        """Render floating messages."""
        y_offset = self.top_bar_height + 10
        for msg in self.messages:
            text = self.font_small.render(msg["text"], True, msg["color"])
            surface.blit(text, (10, y_offset))
            y_offset += 18
    
    def render_hero_panel(self, surface: pygame.Surface, hero, debug_ui: bool = False, rect: pygame.Rect | None = None):
        """Render detailed info panel for selected hero."""
        if rect is None:
            panel_width = self.side_panel_width
            panel_height = 220
            panel_x = self.screen_width - panel_width - 10
            panel_y = self.top_bar_height + 10
            rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)
        else:
            panel_width = int(rect.width)
            panel_height = int(rect.height)
            panel_x = int(rect.x)
            panel_y = int(rect.y)
        
        # Panel background is already drawn by the right panel; do not redraw to avoid allocations.
        
        # Hero info (WK7: Use theme margin for consistent spacing)
        pad = int(self.theme.margin)
        if self.right_close_rect is not None and self.right_close_rect.colliderect(rect):
            pad = max(pad, int(self.right_close_rect.height) + 10)
        y = panel_y + pad
        
        # Name
        name_text = self.font_medium.render(hero.name, True, COLOR_WHITE)
        surface.blit(name_text, (panel_x + pad, y))
        y += name_text.get_height() + 8  # Better spacing
        
        # Class and level
        class_text = self.font_small.render(
            f"{hero.hero_class.title()} Lv.{hero.level}", True, COLOR_WHITE
        )
        surface.blit(class_text, (panel_x + pad, y))
        y += class_text.get_height() + 8  # Better spacing
        
        # HP bar
        hp_text = self.font_small.render(
            f"HP: {hero.hp}/{hero.max_hp}", True, COLOR_WHITE
        )
        surface.blit(hp_text, (panel_x + pad, y))
        y += hp_text.get_height() + 6
        
        bar_width = panel_width - (pad * 2)
        bar_height = 8
        pygame.draw.rect(surface, (60, 60, 60), (panel_x + pad, y, bar_width, bar_height))
        hp_pct = hero.hp / hero.max_hp
        hp_color = COLOR_GREEN if hp_pct > 0.5 else COLOR_RED
        pygame.draw.rect(surface, hp_color, (panel_x + pad, y, bar_width * hp_pct, bar_height))
        y += bar_height + 8  # Better spacing
        
        # Stats
        stats_text = self.font_small.render(
            f"ATK: {hero.attack}  DEF: {hero.defense}", True, COLOR_WHITE
        )
        surface.blit(stats_text, (panel_x + pad, y))
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
        
        # State / Intent / Decision
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
        y += 16

        # Inside-building visibility (PM: show if available; can be debug-only, but safe to show always when true)
        try:
            if bool(getattr(hero, "is_inside_building", False)):
                b = getattr(hero, "inside_building", None)
                bname = None
                if b is not None:
                    bname = getattr(b, "building_type", None) or b.__class__.__name__
                inside_line = f"Inside: {str(bname).replace('_',' ').title()}" if bname else "Inside: yes"
                inside_surf = self._cached_line(("inside", id(hero)), inside_line, (220, 220, 255))
                surface.blit(inside_surf, (panel_x + 10, y))
                y += 14
        except Exception:
            pass

        # Debug-only: stuck snapshot + attack gating surface
        if debug_ui:
            now_ms = int(sim_now_ms())

            # Stuck snapshot per locked contract: Hero.get_stuck_snapshot(now_ms=None)->dict
            try:
                if hasattr(hero, "get_stuck_snapshot"):
                    snap = hero.get_stuck_snapshot(now_ms=now_ms)
                else:
                    snap = None

                if isinstance(snap, dict) and bool(snap.get("stuck_active", False)):
                    reason = str(snap.get("stuck_reason", "") or "stuck").strip()
                    attempts = int(snap.get("unstuck_attempts", 0) or 0)
                    stuck_since = snap.get("stuck_since_ms", None)
                    stuck_s = None
                    if stuck_since is not None:
                        try:
                            stuck_s = max(0.0, (float(now_ms) - float(stuck_since)) / 1000.0)
                        except Exception:
                            stuck_s = None
                    if stuck_s is None:
                        stuck_line = f"STUCK: {reason} (attempts {attempts})"
                    else:
                        stuck_line = f"STUCK: {reason} ({stuck_s:.1f}s, attempts {attempts})"

                    stuck_surf = self._cached_line(("stuck", id(hero)), stuck_line, (255, 180, 100))
                    surface.blit(stuck_surf, (panel_x + 10, y))
                    y += 14
            except Exception:
                pass

            # Combat gating visibility: Hero.can_attack + optional attack_blocked_reason
            try:
                can_attack = getattr(hero, "can_attack", None)
                if isinstance(can_attack, bool) and not can_attack:
                    reason = str(getattr(hero, "attack_blocked_reason", "") or "").strip()
                    line = f"ATK BLOCKED: {reason}" if reason else "ATK BLOCKED"
                    atk_surf = self._cached_line(("atk_block", id(hero)), line[:48], (255, 160, 160))
                    surface.blit(atk_surf, (panel_x + 10, y))
                    y += 14
            except Exception:
                pass

