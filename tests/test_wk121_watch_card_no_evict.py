"""WK121 Round B: clicking the watch-card header must NOT maximize the card over /
evict the building/hero (main) menu.

Sovereign-reported (while testing WK115): "clicking the top bar of the hero card
maximizes it across the entire left sidebar, getting rid of any other menus
(building/hero) that were there."

Mechanism (diagnosed via headless before/after capture): in the
``main_open and watch_open`` split, the watch segment was sized by a saved fraction
(default 0.45, up to 0.68 in tested states) regardless of expand/collapse. A collapsed
card reserved a large empty box; expanding "filled" that pre-reserved segment, reading
as the card maximizing over the squeezed (or evicted) main menu.

Fix: the watch segment is bounded to the card's OWN content (header-only when collapsed,
its desired expanded height — incl. chat when open — when expanded). The main menu keeps
at least its natural content height (down to ``MAIN_MENU_MIN_PRESENT_H`` only when the
column is genuinely too short). The two panels visibly coexist; the header click is
non-destructive and a second click reliably restores the prior size.
"""

from __future__ import annotations

import pygame

from game.entities.hero import Hero
from game.ui.hud import HUD, HERO_LEFT_MIN_H, RADAR_MINIMAP_H, WATCH_CARD_HEADER_H
from game.ui.hud_layout import MAIN_MENU_MIN_PRESENT_H


def _layout_at(hud: HUD, w: int, h: int, gs: dict):
    return hud._layout_rects_for_screen(w, h, show_right_panel=False, game_state=gs)


def _pin_and_select(hud: HUD, hero: Hero, *, expanded: bool) -> dict:
    """Build the Sovereign's state: a hero SELECTED (main open) + a hero PINNED (watch)."""
    hud._pin_slot.pin(str(hero.hero_id), 0)
    hud._pin_slot.pinned_name = str(hero.name)
    hud._pin_slot._just_pinned = False
    hud._watch_card_expanded = expanded
    return {"selected_hero": hero, "selected_building": None}


def test_main_menu_not_evicted_when_watch_expanded():
    """With a main selection open + watch card expanded, the main menu keeps its
    content height (never squeezed to HERO_LEFT_MIN_H / hidden), and the watch card is
    bounded to its own content (never the full column)."""
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="evict1", name="Gareth")
    # A small main fraction + large watch fraction would, pre-fix, let the watch
    # card maximize over the main menu. Post-fix the saved fraction no longer drives
    # the split.
    hud._left_split_fracs = {"main": 0.32, "watch": 0.68}
    gs = _pin_and_select(hud, hero, expanded=True)

    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)  # populates the hero panel's content height
    _layout_at(hud, 1920, 1080, gs)

    available = 1080 - int(RADAR_MINIMAP_H) - 48

    assert hud._left_main_rect is not None, "main menu must NOT be hidden"
    # Main keeps a sane menu-present minimum (well above the absolute HERO_LEFT_MIN_H
    # clamp), so it is never reduced to a near-invisible strip.
    assert hud._left_main_rect.height >= MAIN_MENU_MIN_PRESENT_H, (
        f"main menu height {hud._left_main_rect.height} squeezed below "
        f"MAIN_MENU_MIN_PRESENT_H={MAIN_MENU_MIN_PRESENT_H}"
    )
    # The watch card never takes (near) the whole column while a main menu is present.
    assert hud._left_watch_rect is not None
    assert hud._left_watch_rect.height < available - HERO_LEFT_MIN_H, (
        "watch card must not consume the full sidebar"
    )
    # No overlap; flush-left stacking (main above watch).
    assert hud._left_main_rect.x == 0 and hud._left_watch_rect.x == 0
    assert hud._left_main_rect.bottom <= hud._left_watch_rect.top + 1


def test_collapsed_watch_is_header_peek_only():
    """A collapsed watch card occupies only its header (no giant empty reserved box),
    leaving the rest of the column to the main menu."""
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="evict2", name="Gareth")
    gs = _pin_and_select(hud, hero, expanded=False)

    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)

    assert hud._left_watch_rect is not None
    assert hud._left_watch_rect.height == WATCH_CARD_HEADER_H, (
        f"collapsed watch should be a {WATCH_CARD_HEADER_H}px header peek, "
        f"got {hud._left_watch_rect.height}"
    )
    assert hud._left_main_rect is not None
    assert hud._left_main_rect.height >= MAIN_MENU_MIN_PRESENT_H


def test_header_click_toggle_is_non_destructive_and_round_trips():
    """Driving the real chevron click headlessly: after the toggle the main menu is NOT
    hidden, and a second click restores the prior (collapsed) state. This is the §2a
    repro, hardened into a regression."""
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="evict3", name="Gareth")
    gs = _pin_and_select(hud, hero, expanded=False)

    surf = pygame.Surface((1920, 1080))
    # Render once so the chevron rect + main content height are populated.
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)

    main_before = hud._left_main_rect
    expanded_before = hud._watch_card_expanded
    assert main_before is not None
    chev = hud._watch_card_chevron_rect
    assert chev is not None, "watch-card header X control must be hittable"

    # Click 1: toggle to expanded.
    action = hud.handle_click(chev.center, gs)
    assert action == "watch_card_chevron_toggle"
    assert hud._watch_card_expanded is (not expanded_before)
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)

    # The main menu is NOT hidden and is not squeezed below its menu-present minimum.
    assert hud._left_main_rect is not None, "main menu must survive the header click"
    assert hud._left_main_rect.height >= MAIN_MENU_MIN_PRESENT_H

    # Click 2: the chevron must still be hittable at the (re-derived) expanded header
    # position, and a second click restores the prior collapsed state.
    chev2 = hud._watch_card_chevron_rect
    assert chev2 is not None
    action2 = hud.handle_click(chev2.center, gs)
    assert action2 == "watch_card_chevron_toggle"
    assert hud._watch_card_expanded is expanded_before, "second click must restore prior state"
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)
    # Back to a header-only peek; main menu still present.
    assert hud._left_watch_rect is not None
    assert hud._left_watch_rect.height == WATCH_CARD_HEADER_H
    assert hud._left_main_rect is not None
    assert hud._left_main_rect.height >= MAIN_MENU_MIN_PRESENT_H


def test_wk115_chat_grow_still_works():
    """Guard the WK115 BUG 3 fix: with chat visible the watch card still grows to its
    chat-inclusive desired height (the content-bound uses _desired_watch_card_expanded_h,
    which includes WATCH_CARD_CHAT_H when _chat_visible)."""
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="chat1", name="Gareth")
    gs = _pin_and_select(hud, hero, expanded=True)
    hud._chat_visible = True
    hud._left_split_fracs = {"main": 0.7, "watch": 0.3}

    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)

    available = 1080 - int(RADAR_MINIMAP_H) - 48
    want = int(hud._desired_watch_card_expanded_h())
    target = min(want, available - HERO_LEFT_MIN_H)
    assert hud._left_watch_rect is not None
    assert hud._left_watch_rect.height >= target, (
        f"watch height {hud._left_watch_rect.height} should grow to >= {target} for chat"
    )
