"""WK130: left sidebar + chat UX overhaul.

Covers the five contract areas of the WK130 sprint
(.cursor/plans/wk130_hero_world_roadmap.plan.md):

1. WIDTH PROPAGATION — sidebar / minimap / chat rects all derive from the single
   authoritative ``LEFT_COL_W`` (224 -> 246); no 224 assumption survives anywhere
   in the live geometry.
2. CHAT SIZES — ``HERO_MENU_CHAT_MIN_H`` 152 -> 190, ``HERO_MENU_CHAT_PREFERRED_H``
   220 -> 280, in-column cap 38% -> 45% (``HERO_MENU_CHAT_MAX_FRAC``),
   ``WATCH_CARD_CHAT_H`` 150 -> 190 with the derived ``WATCH_CARD_FULL_H_*`` sums
   staying internally consistent.
3. 8PX HIT BAND — split-handle pointer-down hit tests use the
   ``LEFT_SPLIT_HANDLE_HIT_H`` (8px) grab band everywhere (pointer_down,
   HUD.handle_click, virtual_pointer_in_hud_chrome), not the 4px visual bar.
4. GEOMETRY UNIFICATION — ``virtual_pointer_in_hud_chrome`` consumes the SAME
   left-column segment rects the render path computes (``_left_watch_rect`` /
   ``_left_main_rect`` via ``_layout_rects_for_screen``); no independently rebuilt
   minimap-anchored card rects (the pre-WK130 drift).
5. DRAG SWEEP INVARIANTS — at every drag position the stacked segments never
   overlap each other or the minimap, the main panel keeps ``HERO_LEFT_MIN_H``,
   and the WK121 "watch card never evicts the main menu" contract holds.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

import game.ui.hud_layout as hud_layout
import game.ui.hud_left_layout as hud_left_layout
import game.ui.hud_watch_card as hud_watch_card
from game.entities.hero import Hero
from game.ui.hud import HUD
from game.ui.hud_layout import (
    HERO_LEFT_MIN_H,
    HERO_MENU_CHAT_GAP,
    HERO_MENU_CHAT_MAX_FRAC,
    HERO_MENU_CHAT_MIN_H,
    HERO_MENU_CHAT_PREFERRED_H,
    HERO_MENU_HERO_MIN_H,
    LEFT_COL_W,
    LEFT_SPLIT_HANDLE_H,
    LEFT_SPLIT_HANDLE_HIT_H,
    RADAR_MINIMAP_H,
    RADAR_MINIMAP_W,
)
from game.ui.hud_watch_card import WATCH_CARD_HEADER_H


def _layout_at(hud: HUD, w: int, h: int, gs: dict):
    return hud._layout_rects_for_screen(w, h, show_right_panel=False, game_state=gs)


@pytest.fixture
def hud_1080() -> HUD:
    pygame.init()
    return HUD(1920, 1080)


def _pin_and_select(hud: HUD, hero: Hero, *, expanded: bool) -> dict:
    hud._pin_slot.pin(str(hero.hero_id), 0)
    hud._pin_slot.pinned_name = str(hero.name)
    hud._pin_slot._just_pinned = False
    hud._watch_card_expanded = expanded
    return {
        "selected_hero": hero,
        "selected_building": None,
        "heroes": [hero],
        "hero_profiles_by_id": {},
        "bounties": [],
    }


# ------------------------------------------------------------------
# (1) Width propagation: everything derives from LEFT_COL_W = 246.
# ------------------------------------------------------------------

def test_left_col_w_is_246_and_minimap_aliases_it() -> None:
    assert hud_layout.LEFT_COL_W == 246  # WK130: 224 -> 246 (+10%)
    assert hud_layout.RADAR_MINIMAP_W == hud_layout.LEFT_COL_W


def test_core_layout_rects_derive_from_left_col_w() -> None:
    layout = hud_layout.HUDLayoutManager().compute(1920, 1080)
    assert layout.left_panel.width == LEFT_COL_W
    assert layout.minimap.width == RADAR_MINIMAP_W == LEFT_COL_W
    assert layout.left_panel.x == 0 and layout.minimap.x == 0
    # Bottom-bar buttons start right of the (wider) minimap, no overlap.
    assert layout.recall_button.x >= layout.minimap.right


def test_segment_and_chat_rects_use_left_col_w(hud_1080: HUD) -> None:
    hud = hud_1080
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="w1", name="Width")
    gs = _pin_and_select(hud, hero, expanded=True)
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)

    assert hud._left_main_rect is not None and hud._left_main_rect.width == LEFT_COL_W
    assert hud._left_watch_rect is not None and hud._left_watch_rect.width == LEFT_COL_W
    for handle in hud._left_split_handle_rects.values():
        assert handle.width == LEFT_COL_W

    # In-column hero-menu chat rect insets from the SAME column width (x+4, w-8).
    split = hud._hero_menu_chat_split_rects(pygame.Rect(0, 48, LEFT_COL_W, 700))
    assert split is not None
    hero_rect, chat_rect = split
    assert hero_rect.width == LEFT_COL_W
    assert chat_rect.x == 4
    assert chat_rect.width == LEFT_COL_W - 8


# ------------------------------------------------------------------
# (2) Chat sizes: new minimum / preferred heights + 45% cap.
# ------------------------------------------------------------------

def test_new_chat_height_constants() -> None:
    assert HERO_MENU_CHAT_MIN_H == 190  # WK130: was 152
    assert HERO_MENU_CHAT_PREFERRED_H == 280  # WK130: was 220
    assert HERO_MENU_CHAT_MAX_FRAC == 0.45  # WK130: was inline 0.38
    assert hud_watch_card.WATCH_CARD_CHAT_H == 190  # WK130: was 150


def test_watch_card_derived_heights_stay_consistent() -> None:
    assert hud_watch_card.WATCH_CARD_FULL_H_WITH_CHAT == (
        hud_watch_card.WATCH_CARD_HEADER_H
        + hud_watch_card.WATCH_CARD_MAP_H
        + hud_watch_card.WATCH_CARD_STATS_H
        + hud_watch_card.WATCH_CARD_CHAT_H
    )
    assert hud_watch_card.WATCH_CARD_FULL_H_NO_CHAT == (
        hud_watch_card.WATCH_CARD_HEADER_H
        + hud_watch_card.WATCH_CARD_MAP_H
        + hud_watch_card.WATCH_CARD_STATS_COMPACT_H
    )
    assert hud_watch_card.WATCH_CARD_FULL_H == hud_watch_card.WATCH_CARD_FULL_H_WITH_CHAT


def test_hero_menu_chat_desired_h_uses_45_percent_cap(hud_1080: HUD) -> None:
    hud = hud_1080
    # Mid-range column: the 45% fraction (between MIN and PREFERRED) drives the height.
    left_h = 500
    frac_h = int(left_h * HERO_MENU_CHAT_MAX_FRAC)
    assert HERO_MENU_CHAT_MIN_H < frac_h < HERO_MENU_CHAT_PREFERRED_H
    assert hud._hero_menu_chat_desired_h(left_h) == frac_h
    # Tall column: capped at the (raised) preferred height.
    assert hud._hero_menu_chat_desired_h(2000) == HERO_MENU_CHAT_PREFERRED_H
    # Short column: never below the (raised) minimum.
    assert hud._hero_menu_chat_desired_h(320) >= HERO_MENU_CHAT_MIN_H


def test_chat_split_honours_new_minimums_at_1080(hud_1080: HUD) -> None:
    left = pygame.Rect(0, 48, LEFT_COL_W, 1080 - RADAR_MINIMAP_H - 48)
    split = hud_1080._hero_menu_chat_split_rects(left)
    assert split is not None
    hero_rect, chat_rect = split
    assert chat_rect.height >= HERO_MENU_CHAT_MIN_H
    assert hero_rect.height >= HERO_MENU_HERO_MIN_H
    assert hero_rect.bottom + HERO_MENU_CHAT_GAP <= chat_rect.top
    assert chat_rect.bottom <= left.bottom


# ------------------------------------------------------------------
# (3) 8px hit band: pointer-down + handle_click accept the grab band, not just
#     the 4px visual bar.
# ------------------------------------------------------------------

def test_split_handle_hit_rect_expands_visual_bar_to_hit_band() -> None:
    visual = pygame.Rect(0, 300, LEFT_COL_W, LEFT_SPLIT_HANDLE_H)
    hit = hud_left_layout.split_handle_hit_rect(visual)
    assert hit.height == LEFT_SPLIT_HANDLE_HIT_H
    assert hit.width == visual.width and hit.x == visual.x
    # The band is centered on the visual bar and fully contains it.
    assert hit.top <= visual.top and hit.bottom >= visual.bottom
    assert visual.centery == hit.centery


def test_pointer_down_accepts_band_above_visual_bar(hud_1080: HUD) -> None:
    hud = hud_1080
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="hb1", name="HitBand")
    gs = _pin_and_select(hud, hero, expanded=True)
    _layout_at(hud, 1920, 1080, gs)

    visual = hud._left_split_handle_rects["main_bottom"]
    assert visual.height == LEFT_SPLIT_HANDLE_H  # the rendered bar stays 4px
    band = hud_left_layout.split_handle_hit_rect(visual)

    # A point INSIDE the 8px band but OUTSIDE the 4px visual bar must start a drag.
    above = (visual.centerx, band.top)
    assert not visual.collidepoint(above)
    assert hud.handle_sidebar_split_pointer_down(above, gs) is True
    assert hud.handle_sidebar_split_pointer_up() is True

    # A point just outside the band must NOT start a drag.
    outside = (visual.centerx, band.top - 1)
    assert hud.handle_sidebar_split_pointer_down(outside, gs) is False
    # handle_click routes the band point as a sidebar split drag too.
    assert hud.handle_click(above, gs) == "sidebar_split_drag"
    hud.handle_sidebar_split_pointer_up()


# ------------------------------------------------------------------
# (4) Geometry unification: chrome hit tests reuse the layout rects the render
#     path computes (no independently rebuilt minimap-anchored card rects).
# ------------------------------------------------------------------

def test_virtual_pointer_matches_layout_rects(hud_1080: HUD) -> None:
    hud = hud_1080
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="g1", name="Geom")
    gs = _pin_and_select(hud, hero, expanded=False)  # collapsed: header peek under main
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)

    main = pygame.Rect(hud._left_main_rect)
    watch = pygame.Rect(hud._left_watch_rect)
    minimap_y = 1080 - RADAR_MINIMAP_H

    # The collapsed watch header sits directly under the main menu (render truth)...
    assert watch.top == main.bottom
    assert watch.height == WATCH_CARD_HEADER_H
    # ...and the hit test agrees with the SAME rects.
    assert hud.virtual_pointer_in_hud_chrome(main.center, surf, gs) is True
    assert hud.virtual_pointer_in_hud_chrome(watch.center, surf, gs) is True

    # The empty column gap between the watch card and the minimap is NOT chrome.
    # (Pre-WK130 the hit path rebuilt the card rect anchored to the minimap top and
    # claimed this area — the drift this sprint removes.)
    gap_probe = (watch.centerx, minimap_y - 10)
    assert watch.bottom < minimap_y - 20, "test premise: a real gap exists"
    assert hud.virtual_pointer_in_hud_chrome(gap_probe, surf, gs) is False

    # The layout state consumed by the hit test is the render-path state, unchanged.
    assert pygame.Rect(hud._left_main_rect) == main
    assert pygame.Rect(hud._left_watch_rect) == watch


def test_virtual_pointer_uses_grown_watch_rect_when_chat_open(hud_1080: HUD) -> None:
    hud = hud_1080
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="g2", name="GeomChat")
    gs = _pin_and_select(hud, hero, expanded=True)
    hud._chat_visible = True
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)

    watch = pygame.Rect(hud._left_watch_rect)
    # Every corner-adjacent probe of the watch segment (incl. the chat band at its
    # bottom) is chrome, straight from the shared layout rect.
    for probe in (
        watch.center,
        (watch.centerx, watch.top + 1),
        (watch.centerx, watch.bottom - 1),
    ):
        assert hud.virtual_pointer_in_hud_chrome(probe, surf, gs) is True


# ------------------------------------------------------------------
# (5) Drag sweep: no overlap, mins respected, WK121 no-evict preserved,
#     minimize/maximize round-trip leaves consistent state.
# ------------------------------------------------------------------

def _assert_column_invariants(hud: HUD, *, top_h: int = 48, screen_h: int = 1080) -> None:
    minimap_y = screen_h - RADAR_MINIMAP_H
    main = hud._left_main_rect
    watch = hud._left_watch_rect
    assert main is not None and watch is not None
    assert main.top == top_h
    assert main.height >= HERO_LEFT_MIN_H
    assert watch.height >= 0
    # Stacked, never overlapping each other or the minimap.
    assert main.bottom <= watch.top
    assert watch.bottom <= minimap_y
    assert main.x == 0 and watch.x == 0
    assert main.width == LEFT_COL_W and watch.width == LEFT_COL_W


@pytest.mark.parametrize("handle_key", ["main_bottom", "watch_bottom"])
def test_drag_sweep_produces_no_overlap_at_any_position(
    hud_1080: HUD, handle_key: str
) -> None:
    hud = hud_1080
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="d1", name="Drag")
    gs = _pin_and_select(hud, hero, expanded=True)
    hud._chat_visible = True
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)

    for dy in range(-900, 901, 60):  # deliberately way past the clamps both ways
        _layout_at(hud, 1920, 1080, gs)
        handle = hud._left_split_handle_rects.get(handle_key)
        assert handle is not None
        assert hud.handle_sidebar_split_pointer_down(handle.center, gs) is True
        hud.handle_sidebar_split_pointer_move((handle.centerx, handle.centery + dy), gs)
        assert hud.handle_sidebar_split_pointer_up() is True

        _layout_at(hud, 1920, 1080, gs)
        _assert_column_invariants(hud)


def test_wk121_no_evict_contract_survives_extreme_fracs(hud_1080: HUD) -> None:
    """Even with hostile saved fractions the watch card never evicts the main menu."""
    hud = hud_1080
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="d2", name="NoEvict")
    gs = _pin_and_select(hud, hero, expanded=True)
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    for fracs in ({"main": 0.05, "watch": 0.95}, {"main": 0.95, "watch": 0.05}):
        hud._left_split_fracs = dict(fracs)
        _layout_at(hud, 1920, 1080, gs)
        _assert_column_invariants(hud)
        assert hud._left_main_rect.height >= hud_layout.MAIN_MENU_MIN_PRESENT_H


def test_chevron_minimize_maximize_round_trip_consistent(hud_1080: HUD) -> None:
    hud = hud_1080
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="d3", name="Chevron")
    gs = _pin_and_select(hud, hero, expanded=True)
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)
    expanded_h = hud._left_watch_rect.height
    _assert_column_invariants(hud)

    # Minimize via the real chevron click.
    chev = hud._watch_card_chevron_rect
    assert chev is not None
    assert hud.handle_click(chev.center, gs) == "watch_card_chevron_toggle"
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)
    assert hud._watch_card_expanded is False
    assert hud._left_watch_rect.height == WATCH_CARD_HEADER_H
    _assert_column_invariants(hud)

    # Maximize again: the prior expanded height is restored exactly.
    chev2 = hud._watch_card_chevron_rect
    assert chev2 is not None
    assert hud.handle_click(chev2.center, gs) == "watch_card_chevron_toggle"
    hud.render(surf, gs)
    _layout_at(hud, 1920, 1080, gs)
    assert hud._watch_card_expanded is True
    assert hud._left_watch_rect.height == expanded_h
    _assert_column_invariants(hud)
    # No floating handles: every registered handle lies on a segment boundary.
    for key, rect in hud._left_split_handle_rects.items():
        if key in ("main_bottom", "watch_top"):
            assert rect.bottom == hud._left_main_rect.bottom
        elif key == "watch_bottom":
            assert rect.bottom == hud._left_watch_rect.bottom
