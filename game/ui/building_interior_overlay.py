"""Centered modal overlay showing a rich interior view of a building."""
from __future__ import annotations

from typing import Any, Optional

import pygame

from game.ui.interior_view_panel import InteriorViewPanel
from game.ui.theme import UITheme

OVERLAY_ALPHA = 180


def _building_interior_heading(building: Any) -> str:
    raw = str(getattr(building, "building_type", "") or "building")
    pretty = raw.replace("_", " ").strip().title() or "Building"
    return f"{pretty} — Interior"


class BuildingInteriorOverlay:
    """Fullscreen dim + centered card with graphical interior scene."""

    CARD_W = 780
    CARD_H = 720

    def __init__(self, theme: UITheme, **panel_kwargs: Any) -> None:
        self.visible: bool = False
        self._building: Any = None
        self._close_rect: Optional[pygame.Rect] = None
        self._overlay: Optional[pygame.Surface] = None
        self._overlay_size: tuple[int, int] = (0, 0)
        self._interior_panel = InteriorViewPanel(theme, **panel_kwargs)
        self._theme = theme

    def show(self, building: Any) -> None:
        self._building = building
        self.visible = True

    def hide(self) -> None:
        self.visible = False
        self._building = None
        self._close_rect = None

    def render(self, surface: pygame.Surface) -> None:
        if not self.visible or self._building is None:
            return

        sw, sh = surface.get_size()
        if self._overlay is None or self._overlay_size != (sw, sh):
            self._overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
            self._overlay.fill((0, 0, 0, OVERLAY_ALPHA))
            self._overlay_size = (sw, sh)
        surface.blit(self._overlay, (0, 0))

        cx = (sw - self.CARD_W) // 2
        cy = (sh - self.CARD_H) // 2
        card_rect = pygame.Rect(cx, cy, self.CARD_W, self.CARD_H)
        pygame.draw.rect(surface, (22, 20, 30), card_rect, border_radius=8)
        pygame.draw.rect(surface, (100, 90, 60), card_rect, width=2, border_radius=8)

        body_top = cy + 4
        btn_area_h = 56
        body_h = self.CARD_H - 4 - btn_area_h
        body_rect = pygame.Rect(cx + 4, body_top, self.CARD_W - 8, body_h)

        self._interior_panel.render(surface, body_rect, {}, self._building)

        font_sub = pygame.font.SysFont("georgia,serif", 14)
        btn_w, btn_h = 140, 36
        btn_x = cx + (self.CARD_W - btn_w) // 2
        btn_y = cy + self.CARD_H - btn_h - 14
        self._close_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        mp = pygame.mouse.get_pos()
        hover = self._close_rect.collidepoint(mp)
        btn_col = (90, 70, 40) if hover else (60, 50, 30)
        pygame.draw.rect(surface, btn_col, self._close_rect, border_radius=5)
        pygame.draw.rect(surface, (120, 100, 60), self._close_rect, width=1, border_radius=5)
        lbl = font_sub.render("Close", True, (230, 215, 160))
        surface.blit(
            lbl,
            (
                btn_x + (btn_w - lbl.get_width()) // 2,
                btn_y + (btn_h - lbl.get_height()) // 2,
            ),
        )

    def handle_click(self, pos: tuple[int, int]) -> bool:
        if not self.visible or self._building is None:
            return False
        if self._close_rect is not None and self._close_rect.collidepoint(pos):
            return True
        return False
