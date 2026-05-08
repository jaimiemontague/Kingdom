"""WK52 R13: Centered modal listing heroes inside a selected building."""
from __future__ import annotations

from typing import Any, Optional

import pygame

# Match MemorialCard pause scrim readability.
OVERLAY_ALPHA = 180


def _building_interior_heading(building: Any) -> str:
    raw = str(getattr(building, "building_type", "") or "building")
    pretty = raw.replace("_", " ").strip().title() or "Building"
    return f"{pretty} — Interior"


class BuildingInteriorOverlay:
    """Fullscreen dim + centered card; dismiss via Close only."""

    CARD_W = 480
    CARD_H = 400

    def __init__(self) -> None:
        self.visible: bool = False
        self._building: Any = None
        self._close_rect: Optional[pygame.Rect] = None
        self._overlay: Optional[pygame.Surface] = None
        self._overlay_size: tuple[int, int] = (0, 0)

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

        hdr = pygame.Rect(cx, cy, self.CARD_W, 56)
        pygame.draw.rect(surface, (40, 32, 20), hdr, border_radius=8)
        pygame.draw.line(surface, (100, 90, 60), (cx, cy + 56), (cx + self.CARD_W, cy + 56))

        title = _building_interior_heading(self._building)
        font_title = pygame.font.SysFont("georgia,serif", 20, bold=True)
        font_sub = pygame.font.SysFont("georgia,serif", 14)
        font_body = pygame.font.SysFont("georgia,serif", 13)
        font_small = pygame.font.SysFont("arial,sans-serif", 12)

        title_surf = font_title.render(title, True, (240, 210, 120))
        surface.blit(title_surf, (cx + (self.CARD_W - title_surf.get_width()) // 2, cy + 10))

        occ_raw = list(getattr(self._building, "occupants", []) or [])
        inside = [h for h in occ_raw if int(getattr(h, "hp", 0) or 0) > 0]

        sub = (
            f"{len(inside)} hero{'s' if len(inside) != 1 else ''} inside"
            if inside
            else "Interior view"
        )
        sub_surf = font_sub.render(sub, True, (180, 170, 130))
        surface.blit(sub_surf, (cx + (self.CARD_W - sub_surf.get_width()) // 2, cy + 32))

        body_top = cy + 68
        body_bottom = cy + self.CARD_H - 72
        pygame.draw.line(surface, (80, 72, 48), (cx + 24, body_top - 6), (cx + self.CARD_W - 24, body_top - 6))

        y = body_top
        if not inside:
            hint = font_body.render("No heroes inside.", True, (170, 165, 155))
            surface.blit(hint, (cx + (self.CARD_W - hint.get_width()) // 2, body_top + 40))
        else:
            line_gap = 22
            max_lines = max(1, (body_bottom - body_top) // line_gap)
            for i, h in enumerate(inside[:max_lines]):
                nm = str(getattr(h, "name", "?"))
                hc = str(getattr(h, "hero_class", "?")).title()
                lv = int(getattr(h, "level", 1))
                hp = int(getattr(h, "hp", 0))
                mhp = max(1, int(getattr(h, "max_hp", 1)))
                row = f"{nm}  •  {hc}  •  Lv {lv}  •  HP {hp}/{mhp}"
                ls = font_body.render(row, True, (210, 205, 195))
                surface.blit(ls, (cx + 28, y))
                y += line_gap
            if len(inside) > max_lines:
                more = font_small.render(f"+ {len(inside) - max_lines} more…", True, (140, 135, 125))
                surface.blit(more, (cx + 28, min(y, body_bottom - 18)))

        btn_w, btn_h = 140, 36
        btn_x = cx + (self.CARD_W - btn_w) // 2
        btn_y = cy + self.CARD_H - btn_h - 20
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
