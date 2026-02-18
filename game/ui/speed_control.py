"""
Speed control bar widget (wk12 Chronos).

5-tier player-facing speed: Pause, Super Slow, Slow, Normal, Fast.
Renders in bottom-right of HUD; forwards clicks to timebase.set_time_multiplier().
"""

from __future__ import annotations

import pygame

from config import (
    SPEED_FAST,
    SPEED_NORMAL,
    SPEED_PAUSE,
    SPEED_SLOW,
    SPEED_SUPER_SLOW,
    SPEED_TIER_NAMES,
)
from game.sim.timebase import get_time_multiplier, set_time_multiplier
from game.ui.theme import UITheme


# Ordered list for [ / ] hotkey stepping (slower / faster)
SPEED_TIERS = [SPEED_PAUSE, SPEED_SUPER_SLOW, SPEED_SLOW, SPEED_NORMAL, SPEED_FAST]

# Button symbols (5 buttons)
SPEED_SYMBOLS = ("||", ">", ">>", ">>>", ">>>>")


class SpeedControlBar:
    """Horizontal bar of 5 speed-tier buttons. Highlights active tier; click sets multiplier."""

    def __init__(
        self,
        theme: UITheme,
        *,
        frame_outer: tuple[int, int, int] = (0x14, 0x14, 0x19),
        frame_inner: tuple[int, int, int] = (0x50, 0x50, 0x64),
        frame_highlight: tuple[int, int, int] = (0x6B, 0x6B, 0x84),
        accent: tuple[int, int, int] | None = None,
        button_tex_normal: str | None = None,
        button_tex_hover: str | None = None,
        button_tex_pressed: str | None = None,
        slice_border: int = 6,
    ) -> None:
        self.theme = theme
        self._frame_outer = frame_outer
        self._frame_inner = frame_inner
        self._frame_highlight = frame_highlight
        self._accent = accent or getattr(theme, "accent", (0xCC, 0xAA, 0x44))
        self._button_tex_normal = button_tex_normal
        self._button_tex_hover = button_tex_hover
        self._button_tex_pressed = button_tex_pressed
        self._slice_border = int(slice_border)
        self._rect = pygame.Rect(0, 0, 200, 50)
        # Cached label surfaces for tier names (keyed by multiplier)
        self._label_cache: dict[float, pygame.Surface] = {}
        # Cached symbol surfaces (keyed by (symbol, color)) — avoid per-frame allocations
        self._symbol_cache: dict[tuple[str, tuple[int, int, int]], pygame.Surface] = {}

    def _get_symbol_surface(self, symbol: str, color: tuple[int, int, int]) -> pygame.Surface:
        key = (symbol, color)
        if key not in self._symbol_cache:
            self._symbol_cache[key] = self.theme.font_small.render(symbol, True, color)
        return self._symbol_cache[key]

    def _get_label_surface(self, multiplier: float) -> pygame.Surface:
        name = SPEED_TIER_NAMES.get(multiplier, "?")
        if multiplier not in self._label_cache:
            self._label_cache[multiplier] = self.theme.font_small.render(
                name, True, (220, 220, 220)
            )
        return self._label_cache[multiplier]

    def set_rect(self, rect: pygame.Rect) -> None:
        self._rect = pygame.Rect(rect)

    def render(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        mouse_pos: tuple[int, int] | None = None,
    ) -> None:
        self._rect = pygame.Rect(rect)
        w, h = rect.width, rect.height
        if w <= 0 or h <= 0:
            return

        # Reserve bottom 14px for tier name; buttons above
        label_h = 14
        btn_h = max(1, h - label_h)
        n = len(SPEED_TIERS)
        btn_w = max(1, (w - (n - 1) * 2) // n)  # 2px gap between
        current = get_time_multiplier()

        # Find which tier is active (tolerance for float)
        active_idx = 0
        for i, m in enumerate(SPEED_TIERS):
            if abs(m - current) < 0.01:
                active_idx = i
                break

        x = rect.x
        for i in range(n):
            btn_rect = pygame.Rect(x, rect.y, btn_w, btn_h)
            m = SPEED_TIERS[i]
            is_active = i == active_idx
            hovered = (
                mouse_pos is not None
                and btn_rect.collidepoint(mouse_pos[0], mouse_pos[1])
            )

            # Background: accent if active, else normal/hover
            if is_active:
                bg = self._accent
            elif hovered:
                bg = (self._frame_highlight[0], self._frame_highlight[1], self._frame_highlight[2])
            else:
                bg = (50, 50, 60)
            pygame.draw.rect(surface, bg, btn_rect)
            pygame.draw.rect(surface, self._frame_outer, btn_rect, 1)
            inner = btn_rect.inflate(-2, -2)
            if inner.width > 0 and inner.height > 0:
                pygame.draw.rect(surface, self._frame_inner, inner, 1)

            # Symbol (cached by symbol + color)
            sym = SPEED_SYMBOLS[i]
            text_color = (30, 30, 30) if is_active else (240, 240, 240)
            sym_surf = self._get_symbol_surface(sym, text_color)
            sx = btn_rect.centerx - sym_surf.get_width() // 2
            sy = btn_rect.y + (btn_rect.height - sym_surf.get_height()) // 2
            surface.blit(sym_surf, (sx, sy))

            x += btn_w + 2

        # Tier name label in reserved bottom strip
        label_surf = self._get_label_surface(SPEED_TIERS[active_idx])
        label_x = rect.x + (rect.width - label_surf.get_width()) // 2
        label_y = rect.y + btn_h + (label_h - label_surf.get_height()) // 2
        if label_y >= rect.y and label_y + label_surf.get_height() <= rect.bottom:
            surface.blit(label_surf, (label_x, label_y))

    def handle_click(self, pos: tuple[int, int]) -> bool:
        """Handle click: set time multiplier to clicked tier. Returns True if consumed."""
        x, y = int(pos[0]), int(pos[1])
        if not self._rect.collidepoint(x, y):
            return False
        # Only button area (exclude label strip) for hit-test
        label_h = 14
        btn_h = max(1, self._rect.height - label_h)
        if y >= self._rect.y + btn_h:
            return False
        w = self._rect.width
        n = len(SPEED_TIERS)
        btn_w = max(1, (w - (n - 1) * 2) // n)
        local_x = x - self._rect.x
        idx = local_x // (btn_w + 2)
        idx = max(0, min(idx, n - 1))
        set_time_multiplier(SPEED_TIERS[idx])
        return True
