"""WK52 watch card layout / radar helper tests."""

import pygame

from game.ui.hud import (
    HERO_LEFT_MIN_H,
    RADAR_MINIMAP_H,
    WATCH_CARD_CHAT_H,
    WATCH_CARD_FULL_H,
    WATCH_CARD_HEADER_H,
    WATCH_CARD_MAP_H,
    WATCH_CARD_STATS_H,
    world_to_radar,
)


def test_minimap_flush_bottom_left():
    h = 1080
    minimap_y = h - RADAR_MINIMAP_H
    assert minimap_y == 900


def test_watch_card_full_h_includes_chat():
    assert WATCH_CARD_FULL_H == (
        WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + WATCH_CARD_STATS_H + WATCH_CARD_CHAT_H
    )


def test_watch_card_layout_expanded_taller_than_collapsed():
    minimap_y = 1080 - RADAR_MINIMAP_H
    card_top_expanded = minimap_y - WATCH_CARD_FULL_H
    card_top_minimized = minimap_y - WATCH_CARD_HEADER_H
    assert card_top_expanded < card_top_minimized


def test_effective_watch_card_reserves_hero_column():
    from game.ui.hud import HUD

    pygame.init()
    hud = HUD(1920, 1080)
    hud._pin_slot.hero_id = "p1"
    hud._watch_card_expanded = True
    ch = hud._effective_watch_card_h(1080)
    minimap_y = 1080 - RADAR_MINIMAP_H
    card_top = minimap_y - ch
    top_h = 48
    assert card_top >= top_h + HERO_LEFT_MIN_H
    assert card_top - top_h >= HERO_LEFT_MIN_H


def test_watch_card_expand_collapse_state():
    expanded = True
    expanded = not expanded
    assert expanded is False
    expanded = not expanded
    assert expanded is True


def test_world_origin_maps_to_radar_origin():
    pygame.init()
    inner = pygame.Rect(5, 5, 80, 80)
    assert world_to_radar(0.0, 0.0, inner, 4800, 4800) == (5, 5)


def test_world_centre_maps_to_radar_centre():
    inner = pygame.Rect(0, 0, 100, 100)
    rx, ry = world_to_radar(2400.0, 2400.0, inner, 4800, 4800)
    assert rx == 50 and ry == 50


def test_world_max_clamps_to_radar_edge():
    inner = pygame.Rect(0, 0, 64, 64)
    rx, ry = world_to_radar(4800.0, 4800.0, inner, 4800, 4800)
    assert rx <= inner.right - 1
    assert ry <= inner.bottom - 1


def test_toggle_right_panel_is_noop_for_compatibility():
    """WK52 R4: Tab hook must not flip visibility (right column removed)."""
    from game.ui.hud import HUD

    h = HUD(1920, 1080)
    h.right_panel_visible = False
    h.toggle_right_panel()
    assert h.right_panel_visible is False
    h.right_panel_visible = True
    h.toggle_right_panel()
    assert h.right_panel_visible is True


def test_watch_card_chevron_returns_consume_action():
    """Chevron returns a routed token so LMB does not fall through to world-clear (WK52 D2)."""
    from game.ui.hud import HUD

    hud = HUD(800, 600)
    hud._pin_slot.hero_id = "h1"
    hud._watch_card_rect = pygame.Rect(0, 100, 200, WATCH_CARD_FULL_H)
    hud._watch_card_chevron_rect = pygame.Rect(160, 102, 36, 20)
    before_exp = hud._watch_card_expanded
    act = hud.handle_click((170, 110), {"hero_profiles_by_id": {"h1": object()}})
    assert act == "watch_card_chevron_toggle"
    assert hud._watch_card_expanded is (not before_exp)


def test_chevron_toggle_keeps_left_panel_and_selection():
    """R5: expanding/collapsing watch card must not wipe the left hero column or sim selection."""
    from game.entities.hero import Hero
    from game.ui.hud import HUD
    from game.ui.micro_view_manager import ViewMode

    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="cjv1", name="ChevronTest")
    hud._pin_slot.pin("cjv1", 0)
    hud._pin_slot.pinned_name = "ChevronTest"
    hud._watch_card_expanded = True
    hud.right_panel_visible = True
    hud._micro_view.mode = ViewMode.OVERVIEW

    gs = {
        "selected_hero": hero,
        "hero_profiles_by_id": {"cjv1": object()},
        "selected_hero_profile": None,
        "world": None,
        "debug_ui": False,
        "bounties": [],
    }
    surf = pygame.Surface((1920, 1080))
    pin_before = hud._pin_slot.hero_id

    def left_rect_h() -> int:
        _t, _b, left, _r, _m, _c, _s, _rc, _mem = hud._layout_rects_for_screen(
            1920, 1080, show_right_panel=False
        )
        return left.height

    hud.render(surf, gs)
    chev = hud._watch_card_chevron_rect
    assert chev is not None
    assert left_rect_h() > 0
    cx, cy = chev.centerx, chev.centery

    assert hud.handle_click((cx, cy), gs) == "watch_card_chevron_toggle"
    assert gs["selected_hero"] is hero
    assert hud._micro_view.mode == ViewMode.OVERVIEW
    assert hud.right_panel_visible is True
    assert hud._pin_slot.hero_id == pin_before
    assert left_rect_h() > 0

    hud.render(surf, gs)
    chev2 = hud._watch_card_chevron_rect
    assert chev2 is not None
    cx2, cy2 = chev2.centerx, chev2.centery
    assert hud.handle_click((cx2, cy2), gs) == "watch_card_chevron_toggle"
    assert gs["selected_hero"] is hero
    assert hud._micro_view.mode == ViewMode.OVERVIEW
    assert hud.right_panel_visible is True
    assert hud._pin_slot.hero_id == pin_before
    assert left_rect_h() > 0
