"""WK61-R10: resizable left-sidebar split layout + economic panel taxable gold."""

from __future__ import annotations

import pygame

from config import COLOR_GOLD
from game.entities.hero import Hero
from game.ui.building_panel import BuildingPanel
from game.ui.hud import (
    HERO_LEFT_MIN_H,
    HUD,
    LEFT_COL_W,
    LEFT_SPLIT_HANDLE_H,
    RADAR_MINIMAP_H,
    WATCH_CARD_HEADER_H,
)


def _layout_at(hud: HUD, w: int, h: int, gs: dict):
    return hud._layout_rects_for_screen(w, h, show_right_panel=False, game_state=gs)


def test_left_split_fracs_allocate_main_and_watch():
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="split1", name="Split")
    hud._pin_slot.pin("split1", 0)
    hud._pin_slot.pinned_name = "Split"
    hud._watch_card_expanded = True
    hud._left_split_fracs = {"main": 0.4, "watch": 0.6}
    gs = {"selected_hero": hero, "selected_building": None}

    top_h = 48
    available = 1080 - int(RADAR_MINIMAP_H) - top_h
    _layout_at(hud, 1920, 1080, gs)

    assert hud._left_main_rect is not None
    assert hud._left_watch_rect is not None
    assert hud._left_main_rect.height + hud._left_watch_rect.height == available
    assert hud._left_main_rect.height >= HERO_LEFT_MIN_H
    assert hud._left_watch_rect.height >= WATCH_CARD_HEADER_H
    assert "main_bottom" in hud._left_split_handle_rects
    assert hud._left_split_handle_rects["main_bottom"].height == LEFT_SPLIT_HANDLE_H


def test_drag_main_bottom_updates_fractions():
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="drag1", name="Drag")
    hud._pin_slot.pin("drag1", 0)
    hud._left_split_fracs = {"main": 0.5, "watch": 0.5}
    gs = {"selected_hero": hero}

    _layout_at(hud, 1920, 1080, gs)
    handle = hud._left_split_handle_rects["main_bottom"]
    start_main_h = hud._left_main_rect.height

    assert hud.handle_sidebar_split_pointer_down(handle.center, gs) is True
    assert hud.handle_sidebar_split_pointer_move((handle.centerx, handle.centery + 40), gs) is True
    assert hud.handle_sidebar_split_pointer_up() is True

    _layout_at(hud, 1920, 1080, gs)
    assert hud._left_main_rect.height > start_main_h
    assert hud._left_split_fracs["main"] > 0.5


def test_marketplace_taxable_gold_renders_gold_when_stash_positive():
    """Economic panel must not show stale grey $0 when stored_tax_gold > 0."""
    pygame.init()
    from game.entities.buildings.economic import Marketplace

    class _Economy:
        player_gold = 9999

    panel = BuildingPanel(1920, 1080)
    mp = Marketplace(10, 10)
    mp.stored_tax_gold = 42
    mp.is_constructed = True
    mp.potions_researched = True
    panel.select_building(mp, [])
    surf = pygame.Surface((LEFT_COL_W, 600))
    left = pygame.Rect(0, 48, LEFT_COL_W, 500)
    panel.render(surf, [], _Economy(), left_rect=left)

    goldish = False
    for y in range(left.y, min(surf.get_height(), left.bottom)):
        for x in range(left.x + 8, min(left.right - 8, surf.get_width())):
            r, g, b, a = surf.get_at((x, y))
            if a < 8:
                continue
            if r >= COLOR_GOLD[0] - 20 and g >= COLOR_GOLD[1] - 30 and b <= COLOR_GOLD[2] + 40:
                goldish = True
                break
        if goldish:
            break
    assert goldish, "Expected gold-colored taxable gold text for stored_tax_gold=42"


def test_sidebar_split_handles_draw_visible_pixels():
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="vis1", name="Vis")
    hud._pin_slot.pin("vis1", 0)
    hud._watch_card_expanded = True
    gs = {"selected_hero": hero, "hero_profiles_by_id": {"vis1": object()}, "bounties": []}
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    handle = hud._left_split_handle_rects.get("main_bottom")
    assert handle is not None
    sample = surf.get_at(handle.center)
    assert sample[0] + sample[1] + sample[2] > 30
