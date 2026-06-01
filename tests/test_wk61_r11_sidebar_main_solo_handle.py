"""WK61-R11 / WK115 BUG 1: unpinned hero/building solo left panel is content-sized.

Original contract (WK61-R11): the solo case always registered a ``main_solo`` resize
handle and the panel height equalled a fixed fraction of the available column.

New contract (WK115 BUG 1, Sovereign-reported): the solo hero/building card sizes to
its CONTENT and registers NO ``main_solo`` handle — there is no empty space below the
card to resize against, so the floating resize bar is removed. Overflow (rare) is
handled by mouse-wheel scroll, not a resize bar. The genuine two-panel dividers
(``main_bottom``/``watch_top``/``watch_bottom``) are unaffected.
"""

from __future__ import annotations

import pygame

from game.entities.hero import Hero
from game.ui.hud import (
    HERO_LEFT_MIN_H,
    HUD,
    LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO,
    RADAR_MINIMAP_H,
    WATCH_CARD_HEADER_H,
)


def _layout_at(hud: HUD, w: int, h: int, gs: dict):
    return hud._layout_rects_for_screen(w, h, show_right_panel=False, game_state=gs)


def test_no_main_solo_handle_when_hero_unpinned_and_content_fits():
    """WK115 BUG 1: solo card sized to content, NO floating resize handle."""
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="solo1", name="Solo")
    gs = {"selected_hero": hero, "selected_building": None}
    assert hud._pin_slot.hero_id is None

    top_h = 48
    available = 1080 - int(RADAR_MINIMAP_H) - top_h

    # Render once so the hero panel reports its natural content height.
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)

    # Then lay out: content is known, so the card sizes to it.
    _layout_at(hud, 1920, 1080, gs)

    assert hud._left_main_rect is not None
    assert hud._left_watch_rect is None
    # The floating solo resize bar must be gone.
    assert "main_solo" not in hud._left_split_handle_rects
    # Card sized to content: >= the minimum, <= the available column, and strictly
    # SHORTER than the old fixed-fraction height (the source of the blank panel).
    h = hud._left_main_rect.height
    assert h >= HERO_LEFT_MIN_H
    assert h <= available
    legacy_fraction_h = int(round(LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO * available))
    assert h < legacy_fraction_h, (
        f"solo card height {h} should be content-sized, not the legacy fraction "
        f"{legacy_fraction_h}"
    )
    # And it matches the panel's reported content height (clamped to the column).
    content_h = int(hud._hero_panel.last_content_height)
    assert content_h > 0
    assert h == max(HERO_LEFT_MIN_H, min(content_h, available))


def test_click_where_solo_handle_was_no_longer_returns_sidebar_split_drag():
    """Clicking below the (now content-sized) solo card must NOT start a split drag."""
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="solo3", name="ClickSolo")
    gs = {"selected_hero": hero, "hero_profiles_by_id": {}, "bounties": []}

    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)

    assert "main_solo" not in hud._left_split_handle_rects
    # Click just below the bottom of the content-sized card (where the floating bar
    # used to live). It must route normally — not as a sidebar split drag.
    main = hud._left_main_rect
    below = (main.centerx, main.bottom + 4)
    action = hud.handle_click(below, gs)
    assert action != "sidebar_split_drag"


def test_genuine_dividers_still_exist_in_watch_plus_main_case():
    """The real two-panel dividers must survive the solo-handle removal."""
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="split2", name="Split")
    hud._pin_slot.pin("split2", 0)
    hud._pin_slot.pinned_name = "Split"
    hud._watch_card_expanded = True
    hud._left_split_fracs = {"main": 0.5, "watch": 0.5}
    gs = {"selected_hero": hero, "selected_building": None}

    _layout_at(hud, 1920, 1080, gs)

    assert hud._left_main_rect is not None
    assert hud._left_watch_rect is not None
    assert "main_bottom" in hud._left_split_handle_rects
    assert "watch_top" in hud._left_split_handle_rects
    assert "watch_bottom" in hud._left_split_handle_rects
    assert hud._left_main_rect.height >= HERO_LEFT_MIN_H
    assert hud._left_watch_rect.height >= WATCH_CARD_HEADER_H


def test_watch_solo_case_has_watch_bottom_divider():
    """Pinned-only (no selection) watch-solo still registers watch_bottom (unchanged)."""
    pygame.init()
    hud = HUD(1920, 1080)
    hud._pin_slot.pin("wsolo", 0)
    hud._pin_slot.pinned_name = "WatchSolo"
    hud._watch_card_expanded = True
    gs = {"selected_hero": None, "selected_building": None}

    _layout_at(hud, 1920, 1080, gs)

    assert hud._left_main_rect is None
    assert hud._left_watch_rect is not None
    assert "watch_bottom" in hud._left_split_handle_rects
    assert "main_solo" not in hud._left_split_handle_rects
