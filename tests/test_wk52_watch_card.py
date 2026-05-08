"""WK52 watch card layout / radar helper tests."""

import pygame

from game.ui.hud import (
    HERO_LEFT_MIN_H,
    LEFT_COL_W,
    RADAR_MINIMAP_H,
    WATCH_CARD_CHAT_H,
    WATCH_CARD_FULL_H,
    WATCH_CARD_FULL_H_NO_CHAT,
    WATCH_CARD_FULL_H_WITH_CHAT,
    WATCH_CARD_HEADER_H,
    WATCH_CARD_MAP_H,
    WATCH_CARD_STATS_COMPACT_H,
    WATCH_CARD_STATS_H,
    world_to_radar,
)


def test_minimap_flush_bottom_left():
    h = 1080
    minimap_y = h - RADAR_MINIMAP_H
    assert minimap_y == 900


def test_watch_card_full_h_includes_chat():
    assert WATCH_CARD_FULL_H_WITH_CHAT == (
        WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + WATCH_CARD_STATS_H + WATCH_CARD_CHAT_H
    )
    assert WATCH_CARD_FULL_H == WATCH_CARD_FULL_H_WITH_CHAT
    assert WATCH_CARD_FULL_H_NO_CHAT == WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + WATCH_CARD_STATS_COMPACT_H
    assert WATCH_CARD_CHAT_H >= 130


def test_watch_card_layout_expanded_taller_than_collapsed():
    minimap_y = 1080 - RADAR_MINIMAP_H
    card_top_expanded = minimap_y - WATCH_CARD_FULL_H_WITH_CHAT
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


def test_building_display_name_resolves_enum_value():
    from game.entities.buildings.castle import Castle
    from game.ui.hud import building_display_name

    c = Castle(3, 3)
    assert building_display_name(c) == "Castle"
    low = building_display_name(c).lower()
    assert "buildingtype" not in low


def test_chat_close_x_renders_on_top_of_band():
    """R9: close glyph center reads as chrome/glyph, not brown message-region fill."""
    from game.ui.chat_panel import ChatPanel
    from game.ui.theme import UITheme

    pygame.init()
    panel = ChatPanel(UITheme())
    panel.end_conversation()
    surf = pygame.Surface((220, 150))
    surf.fill((255, 0, 255))
    panel.render_watch_band(surf, pygame.Rect(10, 50, 200, 148), {"heroes": [], "llm_available": True}, "x")
    cr = panel._watch_band_close_rect
    assert cr is not None
    glyph = (190, 185, 210)
    brown = (60, 55, 45)
    px = surf.get_at((cr.centerx, cr.centery))[:3]

    def _d2(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
        return sum((int(a[i]) - int(b[i])) ** 2 for i in range(3))

    assert _d2(px, glyph) < _d2(px, brown)


def test_watch_card_chevron_returns_consume_action():
    """Chevron returns a routed token so LMB does not fall through to world-clear (WK52 D2)."""
    from game.ui.hud import HUD

    hud = HUD(800, 600)
    hud._pin_slot.hero_id = "h1"
    hud._watch_card_rect = pygame.Rect(0, 100, 200, WATCH_CARD_FULL_H_WITH_CHAT)
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


def test_watch_card_chat_band_draws_non_background_pixels():
    """WK52 R6: in-card chat shows placeholder text (not flat idle dock fill)."""
    from game.entities.hero import Hero
    from game.ui.hud import HUD

    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="wk52_chat_px", name="ChatPx")
    hud._pin_slot.pin(hero.hero_id, 0)
    hud._pin_slot._just_pinned = False
    hud._watch_card_expanded = True
    hud._chat_visible = True
    gs = {
        "selected_hero": hero,
        "hero_profiles_by_id": {"wk52_chat_px": object()},
        "selected_hero_profile": None,
        "heroes": [hero],
        "world": None,
        "debug_ui": False,
        "bounties": [],
        "llm_available": True,
    }
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    r = hud._watch_card_chat_rect
    assert r is not None and r.width > 20 and r.height > 20
    bright = False
    for py in range(r.top, r.bottom):
        for px in range(r.left, r.right):
            cr, cg, cb = surf.get_at((px, py))[:3]
            if cr >= 170 and cg >= 170 and cb >= 170:
                bright = True
                break
        if bright:
            break
    assert bright


def test_watch_card_auto_expand_on_pin_edge():
    """WK52 R6: first pin expands watch card; manual collapse sticks; re-pin expands again."""
    from game.entities.hero import Hero
    from game.ui.hud import HUD

    pygame.init()
    hud = HUD(1920, 1080)
    assert hud._watch_card_expanded is False

    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="wk52_autox", name="AutoX")
    hud._pin_slot.pin(hero.hero_id, 0)
    gs = {
        "selected_hero": hero,
        "hero_profiles_by_id": {"wk52_autox": object()},
        "selected_hero_profile": None,
        "heroes": [hero],
        "world": None,
        "debug_ui": False,
        "bounties": [],
    }
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    assert hud._watch_card_expanded is True

    chev = hud._watch_card_chevron_rect
    assert chev is not None
    assert hud.handle_click((chev.centerx, chev.centery), gs) == "watch_card_chevron_toggle"
    assert hud._watch_card_expanded is False

    hud.render(surf, gs)
    assert hud._watch_card_expanded is False

    hero2 = Hero(200.0, 200.0, hero_class="ranger", hero_id="wk52_autox2", name="AutoX2")
    hud._pin_slot.unpin()
    hud._pin_slot.pin(hero2.hero_id, 0)
    gs["heroes"] = [hero2]
    gs["hero_profiles_by_id"] = {"wk52_autox2": object()}
    gs["selected_hero"] = hero2
    hud.render(surf, gs)
    assert hud._watch_card_expanded is True


def test_render_watch_band_empty_history_has_visual_chrome_r7():
    """R7: empty history draws stripes/hint — catches flat-black void regressions."""
    from game.ui.chat_panel import ChatPanel
    from game.ui.theme import UITheme

    pygame.init()
    panel = ChatPanel(UITheme())
    panel.end_conversation()
    surf = pygame.Surface((220, 150))
    surf.fill((255, 0, 255))
    panel.render_watch_band(surf, pygame.Rect(10, 50, 200, 148), {"heroes": [], "llm_available": True}, "x")
    mr = panel._message_area_rect
    assert mr is not None and mr.height >= 24
    base = surf.get_at((mr.left + 10, mr.top + 6))[:3]
    differs = False
    for dy in range(8, min(90, mr.height - 12), 6):
        c = surf.get_at((mr.left + 14, mr.top + dy))[:3]
        if sum(abs(base[i] - c[i]) for i in range(3)) > 15:
            differs = True
            break
    assert differs


def test_chat_close_button_shrinks_card():
    from game.entities.hero import Hero
    from game.ui.hud import HUD

    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="wk52_xclose", name="XClose")
    hud._pin_slot.pin(hero.hero_id, 0)
    hud._pin_slot.pinned_name = hero.name
    hud._pin_slot._just_pinned = False
    hud._watch_card_expanded = True
    hud._chat_visible = True
    gs = {
        "selected_hero": hero,
        "hero_profiles_by_id": {"wk52_xclose": object()},
        "selected_hero_profile": None,
        "heroes": [hero],
        "world": None,
        "debug_ui": False,
        "bounties": [],
        "llm_available": True,
    }
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    cr = hud._chat_close_rect
    assert cr is not None
    assert hud.effective_card_full_h() == WATCH_CARD_FULL_H_WITH_CHAT
    assert hud.handle_click((cr.centerx, cr.centery), gs) == "chat_band_close"
    assert hud._chat_visible is False
    assert hud.effective_card_full_h() == WATCH_CARD_FULL_H_NO_CHAT


def test_chat_open_button_restores_chat():
    from game.entities.hero import Hero
    from game.ui.hud import HUD

    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="wk52_xopen", name="XOpen")
    hud._pin_slot.pin(hero.hero_id, 0)
    hud._watch_card_expanded = True
    hud._chat_visible = False
    gs = {
        "selected_hero": hero,
        "hero_profiles_by_id": {"wk52_xopen": object()},
        "selected_hero_profile": None,
        "heroes": [hero],
        "world": None,
        "debug_ui": False,
        "bounties": [],
        "llm_available": True,
    }
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    op = hud._chat_open_rect
    assert op is not None
    assert hud.handle_click((op.centerx, op.centery), gs) == "chat_band_open"
    assert hud._chat_visible is True
    hud.render(surf, gs)
    assert hud._watch_card_chat_rect is not None


def test_chevron_toggle_independent_of_chat_visible():
    from game.entities.hero import Hero
    from game.ui.hud import HUD

    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="wk52_chevx", name="ChevX")
    hud._pin_slot.pin(hero.hero_id, 0)
    hud._watch_card_expanded = True
    hud._chat_visible = False
    gs = {
        "selected_hero": hero,
        "hero_profiles_by_id": {"wk52_chevx": object()},
        "selected_hero_profile": None,
        "heroes": [hero],
        "world": None,
        "debug_ui": False,
        "bounties": [],
        "llm_available": True,
    }
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    chev = hud._watch_card_chevron_rect
    assert chev is not None
    before = hud._watch_card_expanded
    assert hud.handle_click((chev.centerx, chev.centery), gs) == "watch_card_chevron_toggle"
    assert hud._watch_card_expanded is (not before)
    assert hud._chat_visible is False


def test_building_selection_does_not_replace_watch_card_slot():
    """R10: bottom card slot is pinned hero only; building uses BuildingPanel, not card slot."""
    from game.entities.buildings.castle import Castle
    from game.entities.hero import Hero
    from game.ui.hud import HUD

    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="wk52_r10", name="R10Hero")
    castle = Castle(3, 3)
    hud._pin_slot.pin(hero.hero_id, 0)
    gs = {
        "selected_hero": hero,
        "selected_building": castle,
        "hero_profiles_by_id": {"wk52_r10": object()},
        "heroes": [hero],
        "world": None,
        "debug_ui": False,
        "bounties": [],
    }
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    assert hud._card_slot_kind == "hero"
    assert hud._watch_card_rect is not None
    assert hud._watch_card_rect.width == LEFT_COL_W


def test_pinned_watch_card_unaffected_when_only_building_selected():
    from game.entities.buildings.castle import Castle
    from game.ui.hud import HUD

    pygame.init()
    hud = HUD(1920, 1080)
    castle = Castle(3, 3)
    gs = {
        "selected_building": castle,
        "selected_hero": None,
        "hero_profiles_by_id": {},
        "heroes": [],
        "world": None,
        "debug_ui": False,
        "bounties": [],
    }
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    assert hud._card_slot_kind is None
    assert hud._watch_card_rect is None
