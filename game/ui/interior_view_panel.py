"""
Interior view panel for building micro-view (wk13 Living Interiors).

Renders inside the right panel when MicroViewManager is in INTERIOR mode:
layered background, furniture, NPC, hero occupants, and UI overlay with Exit button.
"""

from __future__ import annotations

from typing import Any

import pygame

from game.graphics.hero_sprites import HeroSpriteLibrary
from game.graphics.interior_sprites import (
    FurnitureAnchor,
    HeroSlot,
    InteriorSpriteLibrary,
)
from game.ui.theme import UITheme
from game.ui.widgets import Button, NineSlice, TextLabel


def _npc_position(bt: str, w: int, h: int) -> tuple[int, int]:
    """Return (x, y) for NPC sprite relative to panel (0,0)."""
    wall_h = h // 3
    if bt == "inn":
        return (w // 2 - 16, wall_h + 5)
    if bt == "marketplace":
        return (w // 2 - 16, wall_h + 25)
    if bt == "warrior_guild":
        return (w - 55, wall_h + 20)
    return (w // 2 - 16, wall_h + 10)


def _building_type_key(building: Any) -> str:
    """Normalize building type to string for sprite library."""
    raw = getattr(building, "building_type", "building")
    val = getattr(raw, "value", raw)
    return str(val).lower() if val else "building"


def _hero_idle_surface(hero_class: str, size: int = 64) -> pygame.Surface | None:
    """Cached first idle frame for hero class at given size."""
    key = (str(hero_class or "warrior").lower(), size)
    if key not in _hero_idle_surface._cache:
        try:
            clips = HeroSpriteLibrary.clips_for(hero_class or "warrior", size=size)
            idle = clips.get("idle")
            if idle and idle.frames:
                _hero_idle_surface._cache[key] = idle.frames[0]
            else:
                _hero_idle_surface._cache[key] = None
        except Exception:
            _hero_idle_surface._cache[key] = None
    return _hero_idle_surface._cache[key]


_hero_idle_surface._cache: dict[tuple[str, int], pygame.Surface | None] = {}


class InteriorViewPanel:
    """
    Right-panel interior scene: background, furniture, NPC, hero occupants,
    building name header, Exit button, hover/click regions.
    """

    def __init__(
        self,
        theme: UITheme,
        *,
        frame_outer: tuple[int, int, int] = (0x14, 0x14, 0x19),
        frame_highlight: tuple[int, int, int] = (0x6B, 0x6B, 0x84),
        button_tex_normal: str | None = None,
        button_tex_hover: str | None = None,
        button_tex_pressed: str | None = None,
        slice_border: int = 6,
    ) -> None:
        self.theme = theme
        self._frame_outer = frame_outer
        self._frame_highlight = frame_highlight
        self._button_tex_normal = button_tex_normal
        self._button_tex_hover = button_tex_hover
        self._button_tex_pressed = button_tex_pressed
        self._slice_border = int(slice_border)
        self._exit_button = Button(
            rect=pygame.Rect(0, 0, 1, 1),
            text="Exit",
            font=theme.font_small,
            enabled=True,
        )
        self._exit_rect: pygame.Rect | None = None
        self._hovered_hero_index: int | None = None
        self._hovered_npc: bool = False
        self._tooltip_name: str | None = None
        self._hero_click_rects: list[tuple[pygame.Rect, Any]] = []

    def render(
        self,
        surface: pygame.Surface,
        right_rect: pygame.Rect,
        game_state: dict[str, Any],
        building: Any,
    ) -> None:
        w = max(1, right_rect.width)
        h = max(1, right_rect.height)
        rx, ry = right_rect.x, right_rect.y
        bt = _building_type_key(building)

        # Layer 1 — Background
        bg = InteriorSpriteLibrary.get_background(bt, w, h)
        surface.blit(bg, (rx, ry))

        # Layer 2 — Furniture
        furniture = InteriorSpriteLibrary.get_furniture_layout(bt, w, h)
        for anchor in furniture:
            surface.blit(anchor.surface, (rx + anchor.x, ry + anchor.y))

        # Layer 3 — NPC
        npc_surf = InteriorSpriteLibrary.get_npc_sprite(bt)
        npc_x, npc_y = rx, ry
        if npc_surf:
            px, py = _npc_position(bt, w, h)
            npc_x = rx + px
            npc_y = ry + py
            surface.blit(npc_surf, (npc_x, npc_y))

        # Layer 4 — Hero occupants (from building.occupants)
        slots = InteriorSpriteLibrary.get_hero_slots(bt, w, h)
        occupants = getattr(building, "occupants", [])[: len(slots)]
        mouse_pos = pygame.mouse.get_pos()
        self._hovered_hero_index = None
        self._tooltip_name = None
        self._hero_click_rects = []

        for idx, slot in enumerate(slots):
            if idx >= len(occupants):
                continue
            hero = occupants[idx]
            hero_class = getattr(hero, "hero_class", "warrior")
            surf = _hero_idle_surface(hero_class, 64)
            if surf:
                sx = rx + slot.x
                sy = ry + slot.y
                surface.blit(surf, (sx, sy))
                slot_rect = pygame.Rect(sx, sy, surf.get_width(), surf.get_height())
                self._hero_click_rects.append((slot_rect, hero))
                if slot_rect.collidepoint(mouse_pos):
                    self._hovered_hero_index = idx
                    self._tooltip_name = getattr(hero, "name", "Hero")
                    pygame.draw.rect(surface, self._frame_highlight, slot_rect.inflate(2, 2), 2)

        # NPC hover (simple rect around NPC area)
        self._hovered_npc = False
        if npc_surf:
            npc_rect = pygame.Rect(npc_x, npc_y, npc_surf.get_width(), npc_surf.get_height())
            self._hovered_npc = npc_rect.collidepoint(mouse_pos)
            if self._hovered_npc:
                pygame.draw.rect(surface, self._frame_highlight, npc_rect.inflate(2, 2), 2)

        # Layer 5 — UI overlay: header + Exit button
        pad = int(getattr(self.theme, "margin", 8))
        header_h = 28
        name = bt.replace("_", " ").title()
        header_rect = pygame.Rect(rx + 6, ry + pad, w - 12, header_h)
        pygame.draw.rect(surface, (35, 35, 45), header_rect)
        pygame.draw.rect(surface, self._frame_outer, header_rect, 1)
        TextLabel.render(
            surface,
            self.theme.font_body,
            name,
            (rx + pad + 4, ry + pad + (header_h - self.theme.font_body.get_height()) // 2),
            (220, 220, 220),
        )
        # wk14: Building-under-attack warning banner (Agent 14)
        if getattr(building, "is_under_attack", False):
            warn_h = 22
            warn_rect = pygame.Rect(rx + 6, ry + pad + header_h + 4, w - 12, warn_h)
            pygame.draw.rect(surface, (120, 40, 40), warn_rect)
            pygame.draw.rect(surface, (180, 60, 60), warn_rect, 1)
            TextLabel.render(
                surface,
                self.theme.font_small,
                "Building under attack!",
                (rx + pad + 4, ry + pad + header_h + 4 + (warn_h - self.theme.font_small.get_height()) // 2),
                (255, 200, 200),
            )

        # Exit button (top-right)
        exit_w = 56
        exit_h = 26
        self._exit_rect = pygame.Rect(rx + w - exit_w - pad, ry + pad, exit_w, exit_h)
        self._exit_button.rect = self._exit_rect
        self._exit_button.render(
            surface,
            mouse_pos,
            texture_normal=self._button_tex_normal,
            texture_hover=self._button_tex_hover,
            texture_pressed=self._button_tex_pressed,
            slice_border=self._slice_border,
            bg_normal=(45, 45, 55),
            bg_hover=(60, 60, 70),
            bg_pressed=(70, 70, 85),
            border_outer=self._frame_outer,
            text_color=(240, 240, 240),
        )

        # Tooltip for hovered hero or NPC
        if self._tooltip_name:
            tip = self.theme.font_small.render(self._tooltip_name, True, (255, 255, 255))
            tip_bg = (40, 40, 50, 230)
            tx = mouse_pos[0] + 12
            ty = mouse_pos[1] + 12
            tw, th = tip.get_width() + 8, tip.get_height() + 4
            tool_rect = pygame.Rect(tx, ty, tw, th)
            tool_surf = pygame.Surface((tw, th), pygame.SRCALPHA)
            tool_surf.fill(tip_bg)
            pygame.draw.rect(tool_surf, (80, 80, 100), tool_surf.get_rect(), 1)
            tool_surf.blit(tip, (4, 2))
            surface.blit(tool_surf, (tx, ty))
        elif self._hovered_npc:
            npc_tip = "Buy a Drink" if bt == "inn" else ("Trade" if bt == "marketplace" else "Train")
            stub = self.theme.font_small.render(f"{npc_tip} (Coming Soon)", True, (160, 160, 160))
            tx = mouse_pos[0] + 12
            ty = mouse_pos[1] + 12
            surface.blit(stub, (tx, ty))

    def handle_click(self, mouse_pos: tuple[int, int], right_rect: pygame.Rect) -> str | dict | None:
        """Handle click: Exit returns 'exit_interior'; hero click returns start_conversation dict."""
        x, y = int(mouse_pos[0]), int(mouse_pos[1])
        if not right_rect.collidepoint(x, y):
            return None
        if self._exit_rect and self._exit_rect.collidepoint(x, y):
            return "exit_interior"
        for slot_rect, hero in self._hero_click_rects:
            if slot_rect.collidepoint(x, y):
                return {"type": "start_conversation", "hero": hero}
        return None
