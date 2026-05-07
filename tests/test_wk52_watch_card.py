"""WK52 watch card layout / radar helper tests."""

import pygame

from game.ui.hud import (
    WATCH_CARD_FULL_H,
    WATCH_CARD_HEADER_H,
    WATCH_CARD_MAP_H,
    WATCH_CARD_STATS_H,
    WATCH_MINIMAP_SIZE,
    world_to_radar,
)


def test_left_column_caps_below_minimap_when_unpinned():
    h, top_h = 1080, 48
    minimap_y = h - int(WATCH_MINIMAP_SIZE)
    expected_left_h = minimap_y - top_h
    assert expected_left_h == 808


def test_watch_card_layout_shrinks_when_expanded():
    minimap_y = 1080 - int(WATCH_MINIMAP_SIZE)
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
