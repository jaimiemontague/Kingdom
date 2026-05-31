"""Left-column segment/split layout + sidebar-resize drag, extracted from game.ui.hud (WK99).

All layout/drag state lives on HUD, reached via the hud arg; acyclic -- imports only
leaf modules + TYPE_CHECKING HUD.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import pygame
from game.ui.hud_layout import (
    HERO_LEFT_MIN_H,
    LEFT_COL_W,
    LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO,
    LEFT_SPLIT_HANDLE_H,
    LEFT_SPLIT_HANDLE_HIT_H,
    RADAR_MINIMAP_H,
)
from game.ui.hud_watch_card import WATCH_CARD_HEADER_H
if TYPE_CHECKING:
    from game.ui.hud import HUD


def left_column_segments_open(hud, game_state: dict | None) -> tuple[bool, bool]:
    """Return (main_panel_open, watch_card_open) for left-column split layout."""
    gs = game_state or {}
    main_open = (
        gs.get("selected_hero") is not None
        or gs.get("selected_peasant") is not None
        or gs.get("selected_enemy") is not None
        or gs.get("selected_building") is not None
    )
    watch_open = hud._pin_slot.hero_id is not None
    return main_open, watch_open


def normalized_left_split_fracs(hud, main_open: bool, watch_open: bool) -> dict[str, float]:
    if main_open and not watch_open:
        solo = max(
            0.05,
            min(
                0.95,
                float(
                    hud._left_split_fracs.get("main_solo", LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO)
                ),
            ),
        )
        return {"main_solo": solo}
    keys: list[str] = []
    if main_open:
        keys.append("main")
    if watch_open:
        keys.append("watch")
    if not keys:
        return {}
    raw = {k: max(0.05, float(hud._left_split_fracs.get(k, 0.5))) for k in keys}
    total = sum(raw.values())
    return {k: raw[k] / total for k in keys}


def layout_left_column_segments(
    hud,
    top_h: int,
    minimap: pygame.Rect,
    game_state: dict | None,
) -> tuple[pygame.Rect, pygame.Rect | None, pygame.Rect | None]:
    """Allocate main + watch rects above the fixed minimap using session split fractions."""
    available = max(0, minimap.y - top_h)
    main_open, watch_open = hud._left_column_segments_open(game_state)
    hud._left_main_rect = None
    hud._left_watch_rect = None
    hud._left_split_handle_rects = {}

    if available <= 0 or (not main_open and not watch_open):
        left = pygame.Rect(0, top_h, LEFT_COL_W, available)
        hud._last_left_rect = left if main_open else None
        return left, None, None

    fracs = hud._normalized_left_split_fracs(main_open, watch_open)
    main_h = watch_h = 0

    if main_open and watch_open:
        main_h = max(HERO_LEFT_MIN_H, int(round(fracs["main"] * available)))
        watch_h = available - main_h
        if watch_h < WATCH_CARD_HEADER_H:
            watch_h = WATCH_CARD_HEADER_H
            main_h = max(HERO_LEFT_MIN_H, available - watch_h)
        if main_h < HERO_LEFT_MIN_H:
            main_h = HERO_LEFT_MIN_H
            watch_h = max(WATCH_CARD_HEADER_H, available - main_h)
    elif main_open:
        if hud._should_render_hero_menu_chat_popup(game_state or {}):
            main_h = available
        else:
            solo_frac = fracs.get("main_solo", LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO)
            main_h = max(HERO_LEFT_MIN_H, int(round(float(solo_frac) * available)))
            main_h = min(main_h, available)
    else:
        watch_h = available

    main_rect: pygame.Rect | None = None
    watch_rect: pygame.Rect | None = None
    y = top_h

    if main_open:
        main_rect = pygame.Rect(0, y, LEFT_COL_W, main_h)
        hud._left_main_rect = main_rect
        hud._last_left_rect = main_rect
        if watch_open:
            divider = pygame.Rect(0, y + main_h - LEFT_SPLIT_HANDLE_H, LEFT_COL_W, LEFT_SPLIT_HANDLE_H)
            hud._left_split_handle_rects["main_bottom"] = divider
            hud._left_split_handle_rects["watch_top"] = divider
        else:
            solo_handle = pygame.Rect(
                0,
                y + main_h - LEFT_SPLIT_HANDLE_HIT_H,
                LEFT_COL_W,
                LEFT_SPLIT_HANDLE_HIT_H,
            )
            hud._left_split_handle_rects["main_solo"] = solo_handle
        y += main_h

    if watch_open:
        watch_y = y if main_open else minimap.y - watch_h
        watch_rect = pygame.Rect(0, watch_y, LEFT_COL_W, watch_h)
        hud._left_watch_rect = watch_rect
        bottom_handle = pygame.Rect(
            0, watch_y + watch_h - LEFT_SPLIT_HANDLE_H, LEFT_COL_W, LEFT_SPLIT_HANDLE_H
        )
        hud._left_split_handle_rects["watch_bottom"] = bottom_handle
        if not main_open:
            hud._last_left_rect = watch_rect

    left = main_rect or watch_rect or pygame.Rect(0, top_h, LEFT_COL_W, available)
    return left, main_rect, watch_rect


def render_left_split_handles(hud, surface: pygame.Surface) -> None:
    """Draw thin resize bars on open left-column segment boundaries (WK61-R10)."""
    for key, rect in hud._left_split_handle_rects.items():
        if rect.width <= 0 or rect.height <= 0:
            continue
        hover = key == hud._left_split_drag_kind
        color = (120, 130, 160) if hover else (70, 78, 98)
        pygame.draw.rect(surface, color, rect)
        mid_y = rect.centery
        pygame.draw.line(
            surface,
            (150, 160, 190) if hover else (95, 105, 130),
            (rect.x + 8, mid_y),
            (rect.right - 8, mid_y),
            1,
        )


def handle_sidebar_split_pointer_down(hud, pos: tuple[int, int], game_state: dict) -> bool:
    """Begin dragging a left-column split handle; returns True if consumed."""
    if hud._left_split_drag_kind is not None:
        return True
    x, y = int(pos[0]), int(pos[1])
    for key, rect in hud._left_split_handle_rects.items():
        if rect.collidepoint(x, y):
            hud._left_split_drag_kind = key
            hud._left_split_drag_start_y = y
            hud._left_split_drag_main_h0 = int(hud._left_main_rect.height) if hud._left_main_rect else 0
            hud._left_split_drag_watch_h0 = int(hud._left_watch_rect.height) if hud._left_watch_rect else 0
            return True
    return False


def handle_sidebar_split_pointer_move(hud, pos: tuple[int, int], game_state: dict) -> bool:
    """Update split fractions while dragging; returns True if consumed."""
    if hud._left_split_drag_kind is None:
        return False
    top_h = int(getattr(hud.theme, "top_bar_h", 48))
    minimap_y = hud.screen_height - int(RADAR_MINIMAP_H)
    available = max(0, minimap_y - top_h)
    if available <= 0:
        return True
    dy = int(pos[1]) - hud._left_split_drag_start_y
    kind = hud._left_split_drag_kind
    if kind in ("main_bottom", "watch_top"):
        new_main_h = max(HERO_LEFT_MIN_H, min(available - WATCH_CARD_HEADER_H, hud._left_split_drag_main_h0 + dy))
        new_watch_h = available - new_main_h
    elif kind == "watch_bottom":
        new_watch_h = max(
            WATCH_CARD_HEADER_H,
            min(available - HERO_LEFT_MIN_H, hud._left_split_drag_watch_h0 + dy),
        )
        new_main_h = available - new_watch_h
    elif kind == "main_solo":
        new_main_h = max(
            HERO_LEFT_MIN_H,
            min(available, hud._left_split_drag_main_h0 + dy),
        )
        hud._left_split_fracs["main_solo"] = float(new_main_h) / float(available)
        return True
    else:
        return True
    if new_main_h > 0 and new_watch_h > 0:
        hud._left_split_fracs["main"] = float(new_main_h) / float(available)
        hud._left_split_fracs["watch"] = float(new_watch_h) / float(available)
    return True


def handle_sidebar_split_pointer_up(hud) -> bool:
    """End split-handle drag; returns True if a drag was active."""
    if hud._left_split_drag_kind is None:
        return False
    hud._left_split_drag_kind = None
    return True
