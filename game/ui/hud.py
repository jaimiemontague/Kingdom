"""Heads-up display for game information."""

from __future__ import annotations

import pygame

from config import COLOR_GOLD, COLOR_UI_BG, COLOR_UI_BORDER, COLOR_WHITE
from game.sim.timebase import now_ms as sim_now_ms
from game.ui.command_bar import CommandBar
from game.ui.hero_panel import HeroPanel
from game.ui.interior_view_panel import InteriorViewPanel
from game.ui.micro_view_manager import MicroViewManager
from game.ui.speed_control import SpeedControlBar
from game.ui.theme import UITheme
from game.ui.top_bar import TopBar
from game.ui.widgets import Button, HPBar, NineSlice, Panel, TextLabel


class HUD:
    """Displays game information to the player."""

    def __init__(self, screen_width: int, screen_height: int) -> None:
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        self.theme = UITheme()

        self._frame_outer = (0x14, 0x14, 0x19)
        self._frame_inner = (0x50, 0x50, 0x64)
        self._frame_highlight = (0x6B, 0x6B, 0x84)

        self.top_bar_height = int(getattr(self.theme, "top_bar_h", 48))
        self.bottom_bar_height = int(getattr(self.theme, "bottom_bar_h", 96))
        self.side_panel_width = 360

        self.font_large = pygame.font.Font(None, 32)
        self.font_medium = pygame.font.Font(None, 24)
        self.font_small = pygame.font.Font(None, 18)
        self.font_tiny = pygame.font.Font(None, 16)

        self.show_help = False
        self._help_panel_cache: pygame.Surface | None = None
        self._help_hint_cache = self.font_small.render("F3: Help", True, (180, 180, 180))
        self.right_panel_visible = False
        self._panel_hint_cache = self.font_small.render("Tab: Panel", True, (180, 180, 180))

        self._session_start_ms = int(sim_now_ms())
        self._bounty_hint_cache: pygame.Surface | None = None
        self._last_placing = None
        self._placing_banner_cache: pygame.Surface | None = None

        self._panel_tex_top = "assets/ui/kingdomsim_ui_cc0/panels/panel_top.png"
        self._panel_tex_bottom = "assets/ui/kingdomsim_ui_cc0/panels/panel_bottom.png"
        self._panel_tex_right = "assets/ui/kingdomsim_ui_cc0/panels/panel_right.png"
        self._button_tex_normal = "assets/ui/kingdomsim_ui_cc0/buttons/button_normal.png"
        self._button_tex_hover = "assets/ui/kingdomsim_ui_cc0/buttons/button_hover.png"
        self._button_tex_pressed = "assets/ui/kingdomsim_ui_cc0/buttons/button_pressed.png"
        self._panel_slice_border = 8
        self._button_slice_border = 6
        self._topbar_sep_color = (70, 70, 90)

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

        self._top_bar = TopBar(
            self.theme,
            frame_outer=self._frame_outer,
            sep_color=self._topbar_sep_color,
            button_tex_normal=self._button_tex_normal,
            button_tex_hover=self._button_tex_hover,
            button_tex_pressed=self._button_tex_pressed,
            button_slice_border=self._button_slice_border,
        )
        self._command_bar = CommandBar(
            self.theme,
            frame_inner=self._frame_inner,
            frame_outer=self._frame_outer,
            frame_highlight=self._frame_highlight,
            button_tex_normal=self._button_tex_normal,
            button_tex_hover=self._button_tex_hover,
            button_tex_pressed=self._button_tex_pressed,
            button_slice_border=self._button_slice_border,
        )
        self._speed_bar = SpeedControlBar(
            self.theme,
            frame_outer=self._frame_outer,
            frame_inner=self._frame_inner,
            frame_highlight=self._frame_highlight,
        )
        self._hero_panel = HeroPanel(
            self.theme,
            frame_inner=self._frame_inner,
            frame_highlight=self._frame_highlight,
        )
        self._interior_panel = InteriorViewPanel(
            self.theme,
            frame_outer=self._frame_outer,
            frame_highlight=self._frame_highlight,
            button_tex_normal=self._button_tex_normal,
            button_tex_hover=self._button_tex_hover,
            button_tex_pressed=self._button_tex_pressed,
            slice_border=self._button_slice_border,
        )
        self._right_close_button = Button(
            rect=pygame.Rect(0, 0, 1, 1),
            text="X",
            font=self.theme.font_small,
            enabled=True,
        )

        self.quit_rect: pygame.Rect | None = None
        self.right_close_rect: pygame.Rect | None = None
        self._right_rect: pygame.Rect | None = None
        self._micro_view = MicroViewManager()
        self._speed_rect: pygame.Rect | None = None
        self.messages: list[dict] = []
        self.message_duration = 3000

    def _compute_layout(self, surface: pygame.Surface) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect]:
        """Compute UI rects from current surface size. Returns top, bottom, right, minimap, command, speed_rect."""
        w, h = surface.get_width(), surface.get_height()
        self.screen_width = int(w)
        self.screen_height = int(h)

        top_h = int(getattr(self.theme, "top_bar_h", 48))
        bottom_h = int(getattr(self.theme, "bottom_bar_h", 96))
        margin = int(getattr(self.theme, "margin", 8))
        gutter = int(getattr(self.theme, "gutter", 8))

        right_w = int(
            max(
                getattr(self.theme, "right_panel_min_w", 320),
                min(getattr(self.theme, "right_panel_max_w", 420), int(w * 0.24)),
            )
        )
        right_w = int(max(280, min(right_w, w - 2 * margin)))
        if not self.right_panel_visible:
            right_w = 0
        self.side_panel_width = right_w

        top = pygame.Rect(0, 0, w, top_h)
        bottom = pygame.Rect(0, h - bottom_h, w, bottom_h)
        right = pygame.Rect(w - right_w, top_h, right_w, max(0, h - top_h - bottom_h))

        # Speed bar: bottom-right, left of right panel (wk12 Chronos)
        speed_bar_w = 200
        speed_bar_h = 50
        speed_rect = pygame.Rect(
            (w - right_w) - speed_bar_w - margin,
            bottom.y + margin,
            speed_bar_w,
            min(speed_bar_h, bottom_h - 2 * margin),
        )

        minimap_size = max(64, bottom_h - 2 * margin)
        minimap = pygame.Rect(margin, bottom.y + margin, minimap_size, minimap_size)
        cmd_x = minimap.right + gutter
        cmd_w = max(0, speed_rect.left - cmd_x - gutter)
        command = pygame.Rect(cmd_x, bottom.y + margin, cmd_w, minimap_size)
        return top, bottom, right, minimap, command, speed_rect

    def _build_placing_banner(self, text_surf: pygame.Surface) -> pygame.Surface:
        pad_x = 14
        pad_y = 8
        width = text_surf.get_width() + pad_x * 2
        height = text_surf.get_height() + pad_y * 2
        banner = pygame.Surface((width, height), pygame.SRCALPHA)
        rect = pygame.Rect(0, 0, width, height)
        if not NineSlice.render(banner, rect, self._button_tex_hover, border=self._button_slice_border):
            banner.fill((40, 40, 55, 220))
            pygame.draw.rect(banner, self._frame_outer, rect, 2)
            inner = rect.inflate(-4, -4)
            if inner.width > 0 and inner.height > 0:
                pygame.draw.rect(banner, self._frame_inner, inner, 1)
        pygame.draw.line(banner, COLOR_GOLD, (4, 4), (width - 5, 4), 2)
        banner.blit(text_surf, (pad_x, pad_y))
        return banner

    def _draw_section_divider(self, surface: pygame.Surface, x: int, y: int, width: int) -> None:
        if width <= 0:
            return
        pygame.draw.line(surface, self._frame_inner, (x, y), (x + width, y), 1)
        pygame.draw.line(surface, self._frame_highlight, (x, y + 1), (x + width, y + 1), 1)

    def _render_right_panel_overview(
        self, surface: pygame.Surface, right: pygame.Rect, game_state: dict
    ) -> None:
        """Render OVERVIEW mode content: hero panel, building summary, or empty hint (wk13 delegate from MicroViewManager)."""
        selected_hero = game_state.get("selected_hero")
        selected_building = game_state.get("selected_building")
        self.right_close_rect = None
        if selected_hero is not None or selected_building is not None:
            self._render_right_close_button(surface, right)
        if selected_hero is not None:
            self._hero_panel.render(
                surface,
                selected_hero,
                right,
                right_close_rect=self.right_close_rect,
                debug_ui=bool(game_state.get("debug_ui", False)),
            )
        elif selected_building is not None:
            self._render_building_summary(surface, selected_building, right)
        else:
            pad = self._right_panel_top_pad(right)
            TextLabel.render(
                surface,
                self.theme.font_body,
                "Select a hero or building",
                (right.x + int(self.theme.margin), right.y + pad),
                (180, 180, 180),
            )

    def _right_panel_top_pad(self, rect: pygame.Rect) -> int:
        pad = int(self.theme.margin)
        if self.right_close_rect is not None and self.right_close_rect.colliderect(rect):
            pad = max(pad, int(self.right_close_rect.height) + int(self.theme.gutter))
        return pad

    def _render_right_close_button(self, surface: pygame.Surface, right_rect: pygame.Rect) -> None:
        x_surf = TextLabel.get_surface(self.theme.font_small, "X", (240, 240, 240))
        size = max(18, x_surf.get_height() + 6)
        self._right_close_button.rect = pygame.Rect(
            int(right_rect.right - size - 6),
            int(right_rect.y + 6),
            int(size),
            int(size),
        )
        self._right_close_button.text = "X"
        self._right_close_button.render(
            surface,
            pygame.mouse.get_pos(),
            texture_normal=self._button_tex_normal,
            texture_hover=self._button_tex_hover,
            texture_pressed=self._button_tex_pressed,
            slice_border=self._button_slice_border,
            bg_normal=(45, 45, 55),
            bg_hover=(60, 60, 70),
            bg_pressed=(70, 70, 85),
            border_outer=self._frame_outer,
            border_inner=self._frame_inner,
            border_highlight=self._frame_highlight,
            text_color=(240, 240, 240),
            text_shadow_color=(20, 20, 30),
        )
        self.right_close_rect = pygame.Rect(self._right_close_button.rect)

    def _render_building_summary(self, surface: pygame.Surface, building, rect: pygame.Rect) -> None:
        x = rect.x + int(self.theme.margin)
        y = rect.y + self._right_panel_top_pad(rect)
        btype = str(getattr(building, "building_type", building.__class__.__name__) or "")
        header_h = 28
        header_rect = pygame.Rect(rect.x + 6, rect.y + int(self.theme.margin) - 4, rect.width - 12, header_h)
        pygame.draw.rect(surface, (35, 35, 45), header_rect)
        pygame.draw.rect(surface, self._frame_inner, header_rect, 1)
        pygame.draw.line(
            surface,
            self._frame_highlight,
            (header_rect.left + 1, header_rect.top + 1),
            (header_rect.right - 2, header_rect.top + 1),
            1,
        )
        title = btype.replace("_", " ").title()
        TextLabel.render(
            surface,
            self.theme.font_title,
            title,
            (x, header_rect.y + (header_rect.height - self.theme.font_title.get_height()) // 2),
            COLOR_WHITE,
            shadow_color=(20, 20, 30),
        )
        y = header_rect.bottom + 6
        self._draw_section_divider(surface, x, y, int(rect.width - int(self.theme.margin) * 2))
        y += 6
        TextLabel.render(
            surface,
            self.theme.font_small,
            "Status",
            (x, y),
            (180, 180, 200),
            shadow_color=(20, 20, 30),
        )
        y += self.theme.font_small.get_height() + 4
        hp = int(getattr(building, "hp", 0) or 0)
        max_hp = int(getattr(building, "max_hp", 0) or 0)
        TextLabel.render(
            surface,
            self.theme.font_body,
            f"HP: {hp}/{max_hp}",
            (x, y),
            (220, 220, 220),
            shadow_color=(20, 20, 30),
        )
        y += self.theme.font_body.get_height() + 6
        HPBar.render(
            surface,
            pygame.Rect(x, y, max(0, rect.width - int(self.theme.margin) * 2), 8),
            hp,
            max(1, max_hp),
            color_scheme={
                "bg": (60, 60, 60),
                "good": (80, 200, 100),
                "warn": (220, 180, 90),
                "bad": (220, 80, 80),
                "border": (20, 20, 25),
            },
        )

    def _render_help(self, surface: pygame.Surface, origin: tuple[int, int]) -> None:
        x0, y0 = origin
        if self._help_panel_cache is None:
            pad = 10
            width = 300
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
            height = pad * 2 + len(lines) * 16 + 6
            panel = pygame.Surface((width, height), pygame.SRCALPHA)
            panel.fill((*COLOR_UI_BG, 235))
            pygame.draw.rect(panel, self._frame_outer, (0, 0, width, height), 2)
            inner = pygame.Rect(2, 2, width - 4, height - 4)
            if inner.width > 0 and inner.height > 0:
                pygame.draw.rect(panel, self._frame_inner, inner, 1)
                pygame.draw.line(
                    panel,
                    self._frame_highlight,
                    (inner.left + 1, inner.top + 1),
                    (inner.right - 2, inner.top + 1),
                    1,
                )
                pygame.draw.line(
                    panel,
                    self._frame_highlight,
                    (inner.left + 1, inner.top + 1),
                    (inner.left + 1, inner.bottom - 2),
                    1,
                )
            y = pad
            for text, color in lines:
                line = self.font_tiny.render(text, True, color)
                panel.blit(line, (pad, y))
                y += 16
            self._help_panel_cache = panel
        surface.blit(self._help_panel_cache, (x0, y0))

    def add_message(self, text: str, color: tuple[int, int, int] = COLOR_WHITE) -> None:
        self.messages.append({"text": text, "color": color, "time": pygame.time.get_ticks()})
        if len(self.messages) > 5:
            self.messages.pop(0)

    def update(self) -> None:
        current_time = pygame.time.get_ticks()
        self.messages = [msg for msg in self.messages if current_time - msg["time"] < self.message_duration]

    def toggle_help(self) -> None:
        self.show_help = not self.show_help

    def toggle_right_panel(self) -> None:
        self.right_panel_visible = not self.right_panel_visible

    def on_resize(self, screen_width: int, screen_height: int) -> None:
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)

    def render_messages(self, surface: pygame.Surface) -> None:
        y_offset = self.top_bar_height + 10
        for msg in self.messages:
            text = self.font_small.render(msg["text"], True, msg["color"])
            surface.blit(text, (10, y_offset))
            y_offset += 18

    def render(self, surface: pygame.Surface, game_state: dict) -> None:
        top, bottom, right, minimap, cmd, speed_rect = self._compute_layout(surface)

        self._panel_top.set_rect(top)
        self._panel_bottom.set_rect(bottom)
        self._panel_right.set_rect(right)
        self._panel_minimap.set_rect(minimap)
        self._panel_top.render(surface)
        self._panel_bottom.render(surface)
        if self.right_panel_visible:
            self._panel_right.render(surface)
        self._panel_minimap.render(surface)

        if minimap.width > 0 and minimap.height > 0:
            inner = minimap.inflate(-6, -6)
            if inner.width > 0 and inner.height > 0:
                pygame.draw.rect(surface, self._frame_inner, inner, 1)
                pygame.draw.line(
                    surface,
                    self._frame_highlight,
                    (inner.left + 1, inner.top + 1),
                    (inner.right - 2, inner.top + 1),
                    1,
                )
                pygame.draw.line(
                    surface,
                    self._frame_highlight,
                    (inner.left + 1, inner.top + 1),
                    (inner.left + 1, inner.bottom - 2),
                    1,
                )
            sep_x = minimap.right + int(self.theme.gutter // 2)
            pygame.draw.line(surface, self._frame_outer, (sep_x, bottom.y + 8), (sep_x, bottom.bottom - 8), 2)

        self.quit_rect = self._top_bar.render(surface, top, game_state)

        placing = game_state.get("placing_building_type")
        if placing != self._last_placing:
            self._last_placing = placing
            if placing:
                placing_name = str(placing).replace("_", " ").title()
                banner_text = f"Placing: {placing_name} (LMB: place, ESC: cancel)"
                text_surf = self.theme.font_body.render(banner_text, True, COLOR_WHITE)
                self._placing_banner_cache = self._build_placing_banner(text_surf)
            else:
                self._placing_banner_cache = None
        if self._placing_banner_cache is not None:
            bx = int(cmd.x + (cmd.width - self._placing_banner_cache.get_width()) // 2) if cmd.width > 0 else int(self.theme.margin)
            by = int(bottom.y - self._placing_banner_cache.get_height() - 6)
            surface.blit(self._placing_banner_cache, (bx, by))

        if self.show_help:
            self._render_help(surface, origin=(self.screen_width - 310, 5))

        try:
            now_ms = int(sim_now_ms())
            elapsed_ms = now_ms - int(self._session_start_ms)
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

        self.render_messages(surface)
        self._command_bar.render(surface, cmd)
        self._speed_bar.render(surface, speed_rect, pygame.mouse.get_pos())
        self._speed_rect = speed_rect

        selected_hero = game_state.get("selected_hero")
        selected_building = game_state.get("selected_building")
        self.right_close_rect = None
        if self.right_panel_visible:
            self._right_rect = right
            interior_panel = getattr(self, "_interior_panel", None)
            exit_msg = self._micro_view.render(
                surface, right, game_state, self, interior_panel
            )
            if exit_msg:
                self.add_message(exit_msg, (255, 180, 100))
        else:
            self._right_rect = None

        TextLabel.render(surface, self.theme.font_small, "Minimap", (minimap.x + 6, minimap.y + 6), (200, 200, 200))

    def handle_click(self, mouse_pos: tuple[int, int], game_state: dict) -> str | None:
        x = int(mouse_pos[0])
        y = int(mouse_pos[1])
        if self.quit_rect is not None and self.quit_rect.collidepoint((x, y)):
            return "quit"
        if self.right_close_rect is not None and self.right_close_rect.collidepoint((x, y)):
            return "close_selection"
        if self._right_rect is not None and self._right_rect.collidepoint((x, y)):
            interior_panel = getattr(self, "_interior_panel", None)
            action = self._micro_view.handle_click((x, y), self._right_rect, interior_panel)
            if action == "exit_interior":
                return "exit_interior"
        action = self._command_bar.handle_click((x, y))
        if action:
            return action
        if getattr(self, "_speed_rect", None) is not None and self._speed_bar.handle_click((x, y)):
            return None
        return None

