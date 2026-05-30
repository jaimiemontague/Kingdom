"""Entity info-card renderers for the HUD right/left panels (WK95 slice of hud.py).

Extracted VERBATIM from game/ui/hud.py (WK95 Round B-12): the entity-summary
render cluster — ``peasant_action_label`` (short player-facing action label),
``render_peasant_summary`` (compact peasant info block, WK17), ``render_building_summary``
(selected-building status block) and ``render_hero_focus_profile`` (HERO_FOCUS top-half
condensed profile, WK49). These are LEAF renderers: they only read HUD theme/frame
state and call shared helpers that STAY on the HUD (``_draw_section_divider``,
``_right_panel_top_pad``) plus HUD-owned state (``_frame_inner``/``_frame_highlight``/
``_micro_view``/``_hero_panel``/``theme``), all reached here via the ``hud`` argument.
HUD keeps 1-line delegating wrappers (same names + signatures, including the
underscore-prefixed private names the render() call sites and the external
``game/ui/micro_view_manager.py`` hero-focus caller use) so the call sites are unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from config import COLOR_WHITE
from game.ui.widgets import HPBar, TextLabel

if TYPE_CHECKING:
    from game.ui.hud import HUD


def peasant_action_label(hud: "HUD", peasant) -> str:
    """Return a short player-facing label for the peasant's current action."""
    if not getattr(peasant, "is_alive", True):
        return "Dead"
    state = getattr(peasant, "state", None)
    state_name = getattr(state, "name", str(state) if state else "") or ""
    target = getattr(peasant, "target_building", None)
    btype = ""
    if target is not None:
        btype = str(getattr(target, "building_type", getattr(target, "__class__", "").__name__) or "").replace("_", " ").title()
    if state_name == "DEAD":
        return "Dead"
    if state_name == "IN_CASTLE":
        return "Resting in castle"
    if state_name == "WORKING":
        if target is None:
            return "Working"
        constructed = getattr(target, "is_constructed", True)
        if not constructed:
            return f"Building ({btype})" if btype else "Building"
        return f"Repairing ({btype})" if btype else "Repairing"
    if state_name == "MOVING":
        if target is not None:
            return f"Going to {btype}" if btype else "Walking"
        return "Walking"
    return "Working" if state_name else "Idle"


def render_peasant_summary(hud: "HUD", surface: pygame.Surface, peasant, left_rect: pygame.Rect) -> None:
    """Render a compact peasant info block in the left panel (wk17)."""
    x = left_rect.x + int(hud.theme.margin)
    y = left_rect.y + int(hud.theme.margin)
    header_h = 26
    header_rect = pygame.Rect(left_rect.x + 4, y, left_rect.width - 8, header_h)
    pygame.draw.rect(surface, (35, 35, 45), header_rect)
    pygame.draw.rect(surface, hud._frame_inner, header_rect, 1)
    pygame.draw.line(
        surface,
        hud._frame_highlight,
        (header_rect.left + 1, header_rect.top + 1),
        (header_rect.right - 2, header_rect.top + 1),
        1,
    )
    TextLabel.render(
        surface,
        hud.theme.font_title,
        "Peasant",
        (x, header_rect.y + (header_rect.height - hud.theme.font_title.get_height()) // 2),
        COLOR_WHITE,
        shadow_color=(20, 20, 30),
    )
    y = header_rect.bottom + 8
    hud._draw_section_divider(surface, x, y, max(0, left_rect.width - int(hud.theme.margin) * 2))
    y += 8
    TextLabel.render(
        surface,
        hud.theme.font_small,
        "Action",
        (x, y),
        (180, 180, 200),
        shadow_color=(20, 20, 30),
    )
    y += hud.theme.font_small.get_height() + 4
    action = hud._peasant_action_label(peasant)
    TextLabel.render(
        surface,
        hud.theme.font_body,
        action,
        (x, y),
        (220, 220, 220),
        shadow_color=(20, 20, 30),
    )
    y += hud.theme.font_body.get_height() + 8
    hp = int(getattr(peasant, "hp", 0) or 0)
    max_hp = max(1, int(getattr(peasant, "max_hp", 1) or 1))
    HPBar.render(
        surface,
        pygame.Rect(x, y, max(0, left_rect.width - int(hud.theme.margin) * 2), 8),
        hp,
        max_hp,
        color_scheme={
            "bg": (60, 60, 60),
            "good": (80, 200, 100),
            "warn": (220, 180, 90),
            "bad": (220, 80, 80),
            "border": (20, 20, 25),
        },
    )

    # WK46 Stage 3: BuilderPeasant wood inventory (per-peasant, not a player resource).
    wood = getattr(peasant, "wood_inventory", None)
    req = getattr(peasant, "required_wood", None)
    if wood is not None or req is not None:
        y += 14
        TextLabel.render(
            surface,
            hud.theme.font_small,
            "Wood",
            (x, y),
            (180, 180, 200),
            shadow_color=(20, 20, 30),
        )
        y += hud.theme.font_small.get_height() + 4
        if wood is None:
            wood = 0
        if req is None:
            TextLabel.render(
                surface,
                hud.theme.font_body,
                f"{int(wood)}",
                (x, y),
                (220, 220, 220),
                shadow_color=(20, 20, 30),
            )
        else:
            TextLabel.render(
                surface,
                hud.theme.font_body,
                f"{int(wood)} / {int(req)}",
                (x, y),
                (220, 220, 220),
                shadow_color=(20, 20, 30),
            )


def render_building_summary(hud: "HUD", surface: pygame.Surface, building, rect: pygame.Rect) -> None:
    x = rect.x + int(hud.theme.margin)
    y = rect.y + hud._right_panel_top_pad(rect)
    btype = str(getattr(building, "building_type", building.__class__.__name__) or "")
    header_h = 28
    header_rect = pygame.Rect(rect.x + 6, rect.y + int(hud.theme.margin) - 4, rect.width - 12, header_h)
    pygame.draw.rect(surface, (35, 35, 45), header_rect)
    pygame.draw.rect(surface, hud._frame_inner, header_rect, 1)
    pygame.draw.line(
        surface,
        hud._frame_highlight,
        (header_rect.left + 1, header_rect.top + 1),
        (header_rect.right - 2, header_rect.top + 1),
        1,
    )
    title = btype.replace("_", " ").title()
    TextLabel.render(
        surface,
        hud.theme.font_title,
        title,
        (x, header_rect.y + (header_rect.height - hud.theme.font_title.get_height()) // 2),
        COLOR_WHITE,
        shadow_color=(20, 20, 30),
    )
    y = header_rect.bottom + 6
    hud._draw_section_divider(surface, x, y, int(rect.width - int(hud.theme.margin) * 2))
    y += 6
    TextLabel.render(
        surface,
        hud.theme.font_small,
        "Status",
        (x, y),
        (180, 180, 200),
        shadow_color=(20, 20, 30),
    )
    y += hud.theme.font_small.get_height() + 4
    hp = int(getattr(building, "hp", 0) or 0)
    max_hp = int(getattr(building, "max_hp", 0) or 0)
    TextLabel.render(
        surface,
        hud.theme.font_body,
        f"HP: {hp}/{max_hp}",
        (x, y),
        (220, 220, 220),
        shadow_color=(20, 20, 30),
    )
    y += hud.theme.font_body.get_height() + 6
    HPBar.render(
        surface,
        pygame.Rect(x, y, max(0, rect.width - int(hud.theme.margin) * 2), 8),
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


def render_hero_focus_profile(hud: "HUD", surface: pygame.Surface, rect: pygame.Rect, game_state: dict) -> None:
    """Top half of HERO_FOCUS mode: condensed profile/memory (WK49)."""
    hero = game_state.get("selected_hero")
    profile = game_state.get("selected_hero_profile")
    if hero is None:
        qh = getattr(hud._micro_view, "quest_hero", None)
        hero = qh
    if hero is None:
        return
    hud._hero_panel.render_focus_top(
        surface,
        rect,
        hero,
        hero_profile=profile,
    )
