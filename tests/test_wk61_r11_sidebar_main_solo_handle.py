"""WK61-R11: unpinned hero/enemy/building panel solo split handle (BUG-005)."""

from __future__ import annotations

import pygame

from game.entities.hero import Hero
from game.ui.hud import (
    HERO_LEFT_MIN_H,
    HUD,
    LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO,
    LEFT_SPLIT_HANDLE_HIT_H,
    RADAR_MINIMAP_H,
)


def _layout_at(hud: HUD, w: int, h: int, gs: dict):
    return hud._layout_rects_for_screen(w, h, show_right_panel=False, game_state=gs)


def test_main_solo_handle_when_hero_unpinned():
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="solo1", name="Solo")
    gs = {"selected_hero": hero, "selected_building": None}
    assert hud._pin_slot.hero_id is None

    top_h = 48
    available = 1080 - int(RADAR_MINIMAP_H) - top_h
    hud._left_split_fracs = {"main_solo": 0.55}
    _layout_at(hud, 1920, 1080, gs)

    assert hud._left_main_rect is not None
    assert hud._left_watch_rect is None
    assert "main_solo" in hud._left_split_handle_rects
    handle = hud._left_split_handle_rects["main_solo"]
    assert handle.height == LEFT_SPLIT_HANDLE_HIT_H
    assert hud._left_main_rect.height == max(HERO_LEFT_MIN_H, int(round(0.55 * available)))


def test_drag_main_solo_updates_fraction():
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="solo2", name="DragSolo")
    gs = {"selected_hero": hero}
    hud._left_split_fracs = {"main_solo": LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO}

    _layout_at(hud, 1920, 1080, gs)
    handle = hud._left_split_handle_rects["main_solo"]
    start_h = hud._left_main_rect.height

    assert hud.handle_sidebar_split_pointer_down(handle.center, gs) is True
    assert hud.handle_sidebar_split_pointer_move((handle.centerx, handle.centery + 50), gs) is True
    assert hud.handle_sidebar_split_pointer_up() is True

    _layout_at(hud, 1920, 1080, gs)
    assert hud._left_main_rect.height > start_h
    assert hud._left_split_fracs["main_solo"] > LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO


def test_handle_click_returns_sidebar_split_drag_on_main_solo():
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="solo3", name="ClickSolo")
    gs = {"selected_hero": hero, "hero_profiles_by_id": {}, "bounties": []}

    _layout_at(hud, 1920, 1080, gs)
    handle = hud._left_split_handle_rects["main_solo"]
    action = hud.handle_click(handle.center, gs)
    assert action == "sidebar_split_drag"


def test_main_solo_handle_renders_visible_pixels():
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="solo4", name="VisSolo")
    gs = {"selected_hero": hero, "hero_profiles_by_id": {}, "bounties": []}
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    handle = hud._left_split_handle_rects.get("main_solo")
    assert handle is not None
    sample = surf.get_at(handle.center)
    assert sample[0] + sample[1] + sample[2] > 30
