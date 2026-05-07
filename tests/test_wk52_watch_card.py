"""WK52 watch card layout / radar helper tests."""

import pygame

from game.ui.hud import (
    CHAT_DOCK_H,
    RADAR_MINIMAP_H,
    WATCH_CARD_FULL_H,
    WATCH_CARD_HEADER_H,
    WATCH_CARD_MAP_H,
    WATCH_CARD_STATS_H,
    world_to_radar,
)


def test_left_column_caps_below_minimap_when_unpinned():
    h, top_h, bottom_h = 1080, 48, 96
    bottom_y = h - bottom_h
    minimap_y = bottom_y - RADAR_MINIMAP_H - CHAT_DOCK_H
    expected_left_h = minimap_y - top_h
    assert minimap_y == 664
    assert expected_left_h == 616


def test_chat_dock_between_minimap_and_bottom_bar():
    bottom_y = 1080 - 96
    minimap_y = bottom_y - RADAR_MINIMAP_H - CHAT_DOCK_H
    assert minimap_y + RADAR_MINIMAP_H + CHAT_DOCK_H == bottom_y


def test_watch_card_layout_shrinks_when_expanded():
    minimap_y = (1080 - 96) - RADAR_MINIMAP_H - CHAT_DOCK_H
    card_top_expanded = minimap_y - WATCH_CARD_FULL_H
    card_top_minimized = minimap_y - WATCH_CARD_HEADER_H
    assert card_top_expanded < card_top_minimized
    assert (card_top_minimized - card_top_expanded) == (WATCH_CARD_FULL_H - WATCH_CARD_HEADER_H)


def test_watch_card_full_h_constant_sum():
    assert WATCH_CARD_FULL_H == WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + WATCH_CARD_STATS_H


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
    """Chevron returns a routed token so LMB does not fall through to world-clear (WK52 D1)."""
    from game.ui.hud import HUD

    hud = HUD(800, 600)
    hud._pin_slot.hero_id = "h1"
    hud._watch_card_rect = pygame.Rect(0, 100, 200, WATCH_CARD_FULL_H)
    hud._watch_card_chevron_rect = pygame.Rect(160, 102, 36, 20)
    before_exp = hud._watch_card_expanded
    act = hud.handle_click((170, 110), {"hero_profiles_by_id": {"h1": object()}})
    assert act == "watch_card_chevron_toggle"
    assert hud._watch_card_expanded is (not before_exp)
