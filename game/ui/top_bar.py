"""Top-bar rendering for HUD statistics and quit action."""

from __future__ import annotations

import pygame

from config import COLOR_GOLD, COLOR_RED, COLOR_WHITE
from game.ui.widgets import Button, TextLabel


class TopBar:
    """Render top-bar metrics and quit button."""

    def __init__(
        self,
        theme,
        *,
        frame_outer: tuple[int, int, int],
        sep_color: tuple[int, int, int],
        button_tex_normal: str,
        button_tex_hover: str,
        button_tex_pressed: str,
        button_slice_border: int,
    ) -> None:
        self.theme = theme
        self._frame_outer = frame_outer
        self._sep_color = sep_color
        self._button_tex_normal = button_tex_normal
        self._button_tex_hover = button_tex_hover
        self._button_tex_pressed = button_tex_pressed
        self._button_slice_border = int(button_slice_border)
        self._quit_button = Button(
            rect=pygame.Rect(0, 0, 1, 1),
            text="Quit",
            font=self.theme.font_small,
        )
        self.quit_rect: pygame.Rect | None = None

    def _render_quit_button(self, surface: pygame.Surface, top_rect: pygame.Rect) -> pygame.Rect:
        label_surf = TextLabel.get_surface(self.theme.font_small, "Quit", (240, 240, 240))
        pad_x = 10
        pad_y = 6
        w = int(label_surf.get_width() + pad_x * 2)
        h = int(label_surf.get_height() + pad_y * 2)
        x = int(top_rect.right - w - int(self.theme.margin))
        y = int(top_rect.y + (top_rect.height - h) // 2)
        self._quit_button.rect = pygame.Rect(x, y, w, h)
        self._quit_button.text = "Quit"
        self._quit_button.render(
            surface,
            pygame.mouse.get_pos(),
            texture_normal=self._button_tex_normal,
            texture_hover=self._button_tex_hover,
            texture_pressed=self._button_tex_pressed,
            slice_border=self._button_slice_border,
            bg_normal=(55, 40, 40),
            bg_hover=(70, 45, 45),
            bg_pressed=(75, 55, 55),
            border_outer=(0x14, 0x14, 0x19),
            border_inner=(0x50, 0x50, 0x64),
            border_highlight=(0x6B, 0x6B, 0x84),
            text_shadow_color=(20, 20, 25),
        )
        return pygame.Rect(self._quit_button.rect)

    def render(self, surface: pygame.Surface, top_rect: pygame.Rect, game_state: dict) -> pygame.Rect:
        # Header strip for subtle depth.
        pygame.draw.rect(surface, (30, 30, 40), (top_rect.x, top_rect.y, top_rect.width, 6))

        gold = int(game_state.get("gold", 0) or 0)
        heroes = game_state.get("heroes", [])
        enemies = game_state.get("enemies", [])
        alive_heroes = sum(1 for hero in heroes if getattr(hero, "is_alive", True))
        alive_enemies = sum(1 for enemy in enemies if getattr(enemy, "is_alive", True))
        wave = int(game_state.get("wave", 1) or 1)

        items = [
            (f"Gold: {gold}", COLOR_GOLD),
            (f"Heroes: {alive_heroes}", (230, 230, 230)),
            (f"Enemies: {alive_enemies}", COLOR_RED),
            (f"Wave: {wave}", (230, 230, 230)),
        ]
        x = int(self.theme.margin)
        icon_size = 6
        icon_pad = 6
        item_gap = int(self.theme.gutter) * 2
        text_h = TextLabel.get_surface(self.theme.font_title, "Ag", COLOR_WHITE).get_height()
        y = int((top_rect.height - text_h) // 2)

        for idx, (label, icon_color) in enumerate(items):
            text_font = self.theme.font_title if idx == 0 else self.theme.font_body
            text_surf = TextLabel.get_surface(text_font, label, COLOR_GOLD if idx == 0 else COLOR_WHITE if idx != 2 else COLOR_RED)
            icon_y = int(y + (text_surf.get_height() - icon_size) // 2)
            pygame.draw.rect(surface, icon_color, (x, icon_y, icon_size, icon_size))
            text_x = int(x + icon_size + icon_pad)
            surface.blit(text_surf, (text_x, y + 1))
            x = int(text_x + text_surf.get_width() + item_gap)
            if idx < len(items) - 1:
                sep_x = int(x - (item_gap // 2))
                pygame.draw.line(surface, self._sep_color, (sep_x, top_rect.y + 10), (sep_x, top_rect.bottom - 10), 1)

        pygame.draw.line(surface, self._frame_outer, (top_rect.x, top_rect.bottom - 1), (top_rect.right, top_rect.bottom - 1), 1)
        self.quit_rect = self._render_quit_button(surface, top_rect)
        return pygame.Rect(self.quit_rect)
