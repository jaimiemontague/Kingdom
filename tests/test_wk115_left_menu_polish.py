"""WK115 Round B: left-menu UI polish (Sovereign-reported 3 bugs).

BUG 1 — solo hero/building card sizes to its content; no floating ``main_solo`` resize
        handle below blank panel space.
BUG 2 — hero card body draws without a scroll clip when content fits
        (``_menu_max_scroll == 0``), avoiding partial-line clipping artifacts.
BUG 3 — pressing Chat on a pinned watch hero grows the watch card to fit the chatbox.
"""

from __future__ import annotations

import pygame

from game.entities.hero import Hero
from game.ui.hud import (
    HERO_LEFT_MIN_H,
    HUD,
    LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO,
    RADAR_MINIMAP_H,
)


def _layout_at(hud: HUD, w: int, h: int, gs: dict):
    return hud._layout_rects_for_screen(w, h, show_right_panel=False, game_state=gs)


def test_bug1_solo_hero_card_is_content_sized_no_handle():
    """BUG 1: unpinned hero on 1920x1080 — no main_solo handle; card sized to content."""
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="b1", name="Bug1")
    gs = {"selected_hero": hero, "selected_building": None}

    top_h = 48
    available = 1080 - int(RADAR_MINIMAP_H) - top_h

    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)

    assert "main_solo" not in hud._left_split_handle_rects
    h = hud._left_main_rect.height
    assert h >= HERO_LEFT_MIN_H
    # Content-sized: strictly shorter than the old 0.72*available fraction.
    assert h < int(round(LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO * available))


def test_bug1_solo_card_grows_during_render_pass():
    """BUG 1: HUD.render measures content up front so the card is content-sized in ONE
    frame (no first-frame flash / single-capture blank panel)."""
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="b1b", name="Bug1b")
    gs = {"selected_hero": hero, "selected_building": None}

    top_h = 48
    available = 1080 - int(RADAR_MINIMAP_H) - top_h

    # A single render() must already produce a content-sized main rect (the measure
    # pass populates last_content_height, then re-layout shrinks the panel).
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)

    assert hud._hero_panel.last_content_height > 0
    assert hud._left_main_rect is not None
    assert hud._left_main_rect.height < int(round(LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO * available))
    assert hud._left_main_rect.height >= HERO_LEFT_MIN_H


def test_bug2_hero_panel_no_clip_when_content_fits():
    """BUG 2: a normal hero on 1080 fits, so _menu_max_scroll == 0 (no clip path) and
    rendering does not raise; the card background does NOT extend far below content."""
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="b2", name="Bug2")
    gs = {"selected_hero": hero, "selected_building": None}

    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)  # must not raise

    # Content fits -> no scroll -> the BUG-2 clip path is skipped.
    assert hud._hero_panel._menu_max_scroll == 0

    # The card background must be content-sized: filled at the card rect, NOT far below.
    main = hud._left_main_rect
    assert main is not None
    # Sample a pixel inside the card body (just below the header) -> non-black fill.
    inside = surf.get_at((main.x + 6, main.y + 40))
    assert inside[0] + inside[1] + inside[2] > 30
    # Sample well below the card -> should be world/terrain, NOT the panel chrome
    # extending down. Just assert the panel did not run to mid-screen.
    far_below = main.bottom + 200
    assert far_below < (1080 - int(RADAR_MINIMAP_H)), "card should not fill the column"


def test_bug3_pinned_chat_grows_watch_card_to_fit_chatbox():
    """BUG 3: pinned hero + watch expanded + chat visible grows the watch segment to
    its chat-inclusive desired height, and the chat band has room for >= 1 line."""
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="b3", name="Bug3")
    hud._pin_slot.pin("b3", 0)
    hud._pin_slot.pinned_name = "Bug3"
    hud._watch_card_expanded = True
    hud._chat_visible = True
    # Small watch fraction: without the grow the band would be too short for the chatbox.
    hud._left_split_fracs = {"main": 0.7, "watch": 0.3}
    gs = {"selected_hero": hero, "selected_building": None}

    top_h = 48
    available = 1080 - int(RADAR_MINIMAP_H) - top_h

    _layout_at(hud, 1920, 1080, gs)

    want = int(hud._desired_watch_card_expanded_h())
    target = min(want, available - HERO_LEFT_MIN_H)
    assert hud._left_watch_rect is not None
    assert hud._left_watch_rect.height >= target, (
        f"watch height {hud._left_watch_rect.height} should grow to >= {target}"
    )

    # The chat band inside the grown card must be usable (room for at least one line).
    ch = hud._effective_watch_card_h(1080)
    _map_h, _stats_h, chat_h = hud._watch_card_body_split(ch)
    assert chat_h > 0
    assert chat_h >= hud.font_tiny.get_height(), "chat band too short for a message line"


def test_bug3_no_grow_when_chat_closed():
    """Sanity: with chat closed, the watch segment uses the plain fraction split (the
    grow branch must not fire)."""
    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="b3b", name="Bug3b")
    hud._pin_slot.pin("b3b", 0)
    hud._pin_slot.pinned_name = "Bug3b"
    hud._watch_card_expanded = True
    hud._chat_visible = False
    hud._left_split_fracs = {"main": 0.7, "watch": 0.3}
    gs = {"selected_hero": hero, "selected_building": None}

    top_h = 48
    available = 1080 - int(RADAR_MINIMAP_H) - top_h

    _layout_at(hud, 1920, 1080, gs)

    # Plain split: main ~= 0.7*available (no chat grow stealing space from main).
    assert hud._left_main_rect is not None
    assert hud._left_main_rect.height >= int(round(0.7 * available)) - 2
