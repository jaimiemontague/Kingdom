"""Centered confirmation dialog before demolishing a building."""
from __future__ import annotations

from typing import Any, Optional

import pygame

OVERLAY_ALPHA = 180


class DemolishConfirmOverlay:
    """Fullscreen dim + centered 'Are you sure?' card for demolish actions."""

    CARD_W = 380
    CARD_H = 180

    def __init__(self) -> None:
        self.visible: bool = False
        self._building: Any = None
        self._confirm_rect: Optional[pygame.Rect] = None
        self._cancel_rect: Optional[pygame.Rect] = None
        self._overlay: Optional[pygame.Surface] = None
        self._overlay_size: tuple[int, int] = (0, 0)

    def show(self, building: Any) -> None:
        self._building = building
        self.visible = True

    def hide(self) -> None:
        self.visible = False
        self._building = None
        self._confirm_rect = None
        self._cancel_rect = None

    @property
    def building(self) -> Any:
        return self._building

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
        pygame.draw.rect(surface, (30, 25, 22), card_rect, border_radius=8)
        pygame.draw.rect(surface, (140, 60, 50), card_rect, width=2, border_radius=8)

        font_title = pygame.font.SysFont("georgia,serif", 20, bold=True)
        font_body = pygame.font.SysFont("georgia,serif", 14)
        font_btn = pygame.font.SysFont("georgia,serif", 14)

        raw = str(getattr(self._building, "building_type", "") or "building")
        name = raw.replace("_", " ").strip().title() or "Building"

        title_surf = font_title.render("Demolish Building?", True, (240, 180, 160))
        surface.blit(title_surf, (cx + (self.CARD_W - title_surf.get_width()) // 2, cy + 20))

        msg = f'Are you sure you want to demolish the {name}?'
        msg_surf = font_body.render(msg, True, (210, 200, 190))
        surface.blit(msg_surf, (cx + (self.CARD_W - msg_surf.get_width()) // 2, cy + 58))

        warn_surf = font_body.render("This cannot be undone.", True, (180, 120, 110))
        surface.blit(warn_surf, (cx + (self.CARD_W - warn_surf.get_width()) // 2, cy + 80))

        mp = pygame.mouse.get_pos()
        btn_w, btn_h = 120, 36
        gap = 24
        total_w = btn_w * 2 + gap
        btn_y = cy + self.CARD_H - btn_h - 22

        cancel_x = cx + (self.CARD_W - total_w) // 2
        self._cancel_rect = pygame.Rect(cancel_x, btn_y, btn_w, btn_h)
        cancel_hover = self._cancel_rect.collidepoint(mp)
        cancel_col = (80, 70, 55) if cancel_hover else (60, 50, 38)
        pygame.draw.rect(surface, cancel_col, self._cancel_rect, border_radius=5)
        pygame.draw.rect(surface, (120, 100, 60), self._cancel_rect, width=1, border_radius=5)
        cancel_lbl = font_btn.render("Cancel", True, (230, 215, 160))
        surface.blit(cancel_lbl, (
            cancel_x + (btn_w - cancel_lbl.get_width()) // 2,
            btn_y + (btn_h - cancel_lbl.get_height()) // 2,
        ))

        confirm_x = cancel_x + btn_w + gap
        self._confirm_rect = pygame.Rect(confirm_x, btn_y, btn_w, btn_h)
        confirm_hover = self._confirm_rect.collidepoint(mp)
        confirm_col = (160, 55, 45) if confirm_hover else (130, 45, 35)
        pygame.draw.rect(surface, confirm_col, self._confirm_rect, border_radius=5)
        pygame.draw.rect(surface, (200, 80, 60), self._confirm_rect, width=1, border_radius=5)
        confirm_lbl = font_btn.render("Demolish", True, (255, 220, 210))
        surface.blit(confirm_lbl, (
            confirm_x + (btn_w - confirm_lbl.get_width()) // 2,
            btn_y + (btn_h - confirm_lbl.get_height()) // 2,
        ))

    def handle_click(self, pos: tuple[int, int]) -> str | None:
        """Returns 'confirm', 'cancel', or None (swallow click)."""
        if not self.visible or self._building is None:
            return None
        if self._confirm_rect is not None and self._confirm_rect.collidepoint(pos):
            return "confirm"
        if self._cancel_rect is not None and self._cancel_rect.collidepoint(pos):
            return "cancel"
        return None
