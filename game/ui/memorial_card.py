"""WK52: Full-screen Memorial Card overlay for fallen pinned heroes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pygame


@dataclass
class MemorialRecord:
    """Frozen snapshot captured the moment the pinned hero is detected as fallen."""

    hero_id: str
    name: str
    hero_class: str
    level: int
    enemies_defeated: int
    bounties_claimed: int
    gold_earned: int


def _generate_epitaph(r: MemorialRecord) -> str:
    """One sentence of flavour text based on the hero's career highlights."""
    if r.enemies_defeated >= 20:
        return (
            f"A fearless warrior who felled {r.enemies_defeated} foes "
            f"before the kingdom claimed their last breath."
        )
    if r.bounties_claimed >= 5:
        return (
            f"Faithful to every call, they honoured {r.bounties_claimed} "
            f"bounties before falling in service."
        )
    if r.gold_earned >= 500:
        return (
            f"They amassed {r.gold_earned} gold for the realm before "
            f"fortune finally ran dry."
        )
    if r.level >= 5:
        return (
            f"They rose to Level {r.level} — further than most dare to dream — "
            f"and paid the ultimate price."
        )
    return "Gone too soon. The kingdom will not forget."


class MemorialCard:
    """
    Full-screen pause overlay. Show with show(record). Dismiss with Farewell or overlay click.
    """

    CARD_W = 480
    CARD_H = 380
    OVERLAY_ALPHA = 180

    def __init__(self) -> None:
        self.visible: bool = False
        self._record: Optional[MemorialRecord] = None
        self._dismiss_rect: Optional[pygame.Rect] = None
        self._overlay: Optional[pygame.Surface] = None
        self._overlay_size: tuple[int, int] = (0, 0)

    def show(self, record: MemorialRecord) -> None:
        self._record = record
        self.visible = True

    def hide(self) -> None:
        self.visible = False
        self._record = None
        self._dismiss_rect = None

    def render(self, surface: pygame.Surface) -> bool:
        """Draw the overlay. Click handling is via handle_click."""
        if not self.visible or self._record is None:
            return False

        sw, sh = surface.get_size()

        if self._overlay is None or self._overlay_size != (sw, sh):
            self._overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
            self._overlay.fill((0, 0, 0, self.OVERLAY_ALPHA))
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

        r = self._record
        font_title = pygame.font.SysFont("georgia,serif", 22, bold=True)
        font_sub = pygame.font.SysFont("georgia,serif", 15)
        font_body = pygame.font.SysFont("georgia,serif", 14)
        font_small = pygame.font.SysFont("arial,sans-serif", 12)

        title_text = f"{r.name}  —  {r.hero_class.title()}"
        title_surf = font_title.render(title_text, True, (240, 210, 120))
        surface.blit(title_surf, (cx + (self.CARD_W - title_surf.get_width()) // 2, cy + 10))

        level_text = f"Level {r.level}"
        level_surf = font_sub.render(level_text, True, (180, 170, 130))
        surface.blit(level_surf, (cx + (self.CARD_W - level_surf.get_width()) // 2, cy + 34))

        sep_y = cy + 72
        pygame.draw.line(surface, (80, 72, 48), (cx + 40, sep_y), (cx + self.CARD_W - 40, sep_y))
        skull = font_sub.render("☠", True, (120, 110, 80))
        surface.blit(skull, (cx + (self.CARD_W - skull.get_width()) // 2, sep_y - 9))

        epitaph = _generate_epitaph(r)
        words = epitaph.split()
        lines: list[str] = []
        line = ""
        for word in words:
            test = (line + " " + word).strip()
            if len(test) > 52:
                lines.append(line)
                line = word
            else:
                line = test
        if line:
            lines.append(line)
        ey = sep_y + 20
        for ln in lines:
            ls = font_body.render(ln, True, (190, 180, 150))
            surface.blit(ls, (cx + (self.CARD_W - ls.get_width()) // 2, ey))
            ey += 20

        stats_y = cy + 200
        pygame.draw.line(surface, (60, 56, 40), (cx + 40, stats_y - 10), (cx + self.CARD_W - 40, stats_y - 10))
        stats = [
            ("Enemies Defeated", str(r.enemies_defeated)),
            ("Bounties Claimed", str(r.bounties_claimed)),
            ("Gold Earned", f"{r.gold_earned}g"),
        ]
        for i, (label, val) in enumerate(stats):
            lsurf = font_small.render(label, True, (150, 145, 120))
            vsurf = font_small.render(val, True, (220, 200, 120))
            row_y = stats_y + i * 26
            surface.blit(lsurf, (cx + 60, row_y))
            surface.blit(vsurf, (cx + self.CARD_W - 60 - vsurf.get_width(), row_y))

        hint = font_small.render("[Click to close]", True, (140, 135, 110))
        surface.blit(hint, (cx + (self.CARD_W - hint.get_width()) // 2, cy + self.CARD_H - 64))

        btn_w, btn_h = 140, 36
        btn_x = cx + (self.CARD_W - btn_w) // 2
        btn_y = cy + self.CARD_H - btn_h - 24
        self._dismiss_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        mp = pygame.mouse.get_pos()
        btn_hover = self._dismiss_rect.collidepoint(mp)
        btn_col = (90, 70, 40) if btn_hover else (60, 50, 30)
        pygame.draw.rect(surface, btn_col, self._dismiss_rect, border_radius=5)
        pygame.draw.rect(surface, (120, 100, 60), self._dismiss_rect, width=1, border_radius=5)
        btn_lbl = font_sub.render("Farewell", True, (230, 215, 160))
        surface.blit(
            btn_lbl,
            (
                btn_x + (btn_w - btn_lbl.get_width()) // 2,
                btn_y + (btn_h - btn_lbl.get_height()) // 2,
            ),
        )
        return False

    def handle_click(self, pos: tuple[int, int]) -> bool:
        """Returns True if Farewell (or card dismiss) was pressed."""
        if not self.visible or self._record is None:
            return False
        if self._dismiss_rect is not None and self._dismiss_rect.collidepoint(pos):
            return True
        return False
