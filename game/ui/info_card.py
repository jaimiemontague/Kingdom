"""WK52 R8: shared watch/building card chrome (rounded shell + header + chevron)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

import pygame


class InfoSectionProtocol(Protocol):
    """Renders one body band inside the card (below the header)."""

    section_id: str

    def height(self, body_h: int) -> int: ...

    def render(self, surface: pygame.Surface, body_rect: pygame.Rect, ctx: dict[str, Any]) -> None: ...


RenderBodyFn = Callable[[pygame.Surface, pygame.Rect, dict[str, Any]], None]


@dataclass
class FixedSection:
    section_id: str
    fixed_h: int
    render: RenderBodyFn

    def height(self, body_h: int) -> int:
        _ = body_h
        return self.fixed_h


@dataclass
class FlexSection:
    section_id: str
    render: RenderBodyFn

    def height(self, body_h: int) -> int:
        _ = body_h
        return 0


class InfoCard:
    """
    Shared chrome for WK52 left-column cards: rounded background, header strip, chevron.
    Call :meth:`draw_shell` first, then lay out body sections with :meth:`layout_body`.
    """

    CARD_BG = (18, 18, 28)
    CARD_EDGE = (70, 65, 90)
    HEADER_EDGE = (70, 65, 90)

    def __init__(self, header_bg: tuple[int, int, int] = (35, 30, 50)) -> None:
        self._header_bg = header_bg

    def draw_shell(
        self,
        surface: pygame.Surface,
        *,
        cx: int,
        cy: int,
        cw: int,
        ch: int,
        expanded: bool,
        header_h: int,
        name_surf: pygame.Surface,
        chevron_surf: pygame.Surface | None,
        header_close_x: bool = False,
    ) -> tuple[pygame.Rect, pygame.Rect, int | None]:
        """
        Paint card frame + header. Returns (card_rect, header_control_hit_rect, body_start_y).

        When ``expanded`` is False, ``body_start_y`` is ``None`` (header-only peek).
        If ``header_close_x``, draw the compact X control (WK52) instead of ``chevron_surf``.
        """
        card_rect = pygame.Rect(cx, cy, cw, ch)
        pygame.draw.rect(surface, self.CARD_BG, card_rect, border_radius=4)
        pygame.draw.rect(surface, self.CARD_EDGE, card_rect, width=1, border_radius=4)

        header_rect = pygame.Rect(cx, cy, cw, header_h)
        pygame.draw.rect(surface, self._header_bg, header_rect, border_radius=4)
        pygame.draw.line(
            surface,
            self.HEADER_EDGE,
            (cx, cy + header_h - 1),
            (cx + cw, cy + header_h - 1),
        )

        surface.blit(name_surf, (cx + 3, cy + (header_h - name_surf.get_height()) // 2))

        inset = 2
        close_s = 14
        if header_close_x:
            cr = pygame.Rect(cx + cw - close_s - inset, cy + (header_h - close_s) // 2, close_s, close_s)
            pygame.draw.rect(surface, (20, 20, 28), cr, border_radius=2)
            pygame.draw.rect(surface, (60, 60, 80), cr, width=1, border_radius=2)
            glyph = (190, 185, 210)
            pygame.draw.line(surface, glyph, (cr.left + 3, cr.top + 3), (cr.right - 4, cr.bottom - 4), 1)
            pygame.draw.line(surface, glyph, (cr.right - 4, cr.top + 3), (cr.left + 3, cr.bottom - 4), 1)
            control_hit = cr
        else:
            if chevron_surf is None:
                raise ValueError("chevron_surf required when header_close_x is False")
            cbx = cx + cw - chevron_surf.get_width() - 2
            cby = cy + (header_h - chevron_surf.get_height()) // 2
            surface.blit(chevron_surf, (cbx, cby))
            control_hit = pygame.Rect(
                int(cbx - 2),
                int(cby - 2),
                int(chevron_surf.get_width() + 5),
                int(chevron_surf.get_height() + 4),
            )

        if not expanded:
            return card_rect, control_hit, None
        return card_rect, control_hit, cy + header_h

    def layout_body(
        self,
        *,
        body_top: int,
        cx: int,
        cw: int,
        card_bottom: int,
        sections: list[FixedSection | FlexSection],
        surface: pygame.Surface,
        ctx: dict[str, Any],
    ) -> dict[str, pygame.Rect]:
        """Stack sections top-to-bottom inside the card body. Exactly one FlexSection allowed."""
        out: dict[str, pygame.Rect] = {}
        y = int(body_top)
        inner_w = max(0, cw - 4)
        x0 = cx + 2
        inner_bottom = int(card_bottom)

        flex_i: int | None = next(
            (i for i, s in enumerate(sections) if isinstance(s, FlexSection)), None
        )
        heights: list[int] = []
        for i, sec in enumerate(sections):
            if isinstance(sec, FlexSection):
                heights.append(0)
            else:
                heights.append(int(sec.height(0)))
        if flex_i is not None:
            used = sum(h for j, h in enumerate(heights) if j != flex_i)
            heights[flex_i] = max(0, inner_bottom - y - used)

        for sec, h in zip(sections, heights, strict=True):
            if h <= 0:
                continue
            rect = pygame.Rect(x0, y, inner_w, h)
            sec.render(surface, rect, ctx)
            out[sec.section_id] = rect
            y += h
        return out
