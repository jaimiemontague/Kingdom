"""WK52 R10: left menus clip + wheel scroll wiring."""

import pygame

from game.ui.building_panel import BuildingPanel
from game.ui.hero_panel import HeroPanel
from game.ui.theme import UITheme


def test_hero_panel_apply_menu_scroll_noop_when_no_overflow():
    pygame.init()
    theme = UITheme()
    hp = HeroPanel(theme, frame_inner=(80, 80, 100), frame_highlight=(107, 107, 132))
    hp._menu_max_scroll = 0
    assert hp.apply_menu_scroll(1) is False


def test_hero_panel_apply_menu_scroll_clamps():
    pygame.init()
    theme = UITheme()
    hp = HeroPanel(theme, frame_inner=(80, 80, 100), frame_highlight=(107, 107, 132))
    hp.menu_scroll_px = 100
    hp._menu_max_scroll = 50
    assert hp.apply_menu_scroll(0) is False
    assert hp.apply_menu_scroll(10) is True
    assert 0 <= hp.menu_scroll_px <= 50


def test_building_panel_matches_left_col_width():
    pygame.init()
    bp = BuildingPanel(1920, 1080)
    from game.ui.hud import LEFT_COL_W

    assert bp.panel_width == LEFT_COL_W


def test_building_panel_scroll_resets_on_different_building():
    pygame.init()
    bp = BuildingPanel(800, 600)

    class _B:
        pass

    b1 = _B()
    b2 = _B()
    bp.select_building(b1, [])
    bp.menu_scroll_px = 40
    bp.select_building(b2, [])
    assert bp.menu_scroll_px == 0


def test_hud_handle_menu_scroll_requires_hit_inside_rect():
    from game.entities.hero import Hero
    from game.ui.hud import HUD

    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(1.0, 1.0, hero_class="warrior", hero_id="s1", name="ScrollHit")
    gs = {
        "selected_hero": hero,
        "selected_peasant": None,
        "selected_building": None,
        "hero_profiles_by_id": {"s1": object()},
    }
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    lr = hud._last_left_rect
    assert lr is not None
    hud._hero_panel._menu_max_scroll = 100
    assert hud.handle_menu_scroll((lr.centerx, lr.centery), 1, gs, None) is True
    assert hud.handle_menu_scroll((lr.right + 50, lr.centery), 1, gs, None) is False


def test_virtual_pointer_includes_left_when_building_selected():
    """Ursina: left column must count as HUD chrome when a building sheet is open (WK52 R12)."""
    from game.entities.hero import Hero
    from game.ui.hud import HUD

    pygame.init()
    surf = pygame.Surface((1920, 1080))
    hud = HUD(1920, 1080)
    hero = Hero(1.0, 1.0, hero_class="warrior", hero_id="s1", name="Brick")
    gs = {
        "selected_hero": None,
        "selected_peasant": None,
        "selected_building": object(),
        "hero_profiles_by_id": {},
    }
    hud.render(surf, gs)
    top, bottom, left, *_ = hud._compute_layout(surf, gs)
    assert left.collidepoint(left.x + 4, left.y + 4)
    inside = hud.virtual_pointer_in_hud_chrome((left.x + 4, left.y + 4), surf, gs)
    assert inside is True
    gs_out = dict(gs)
    gs_out["selected_building"] = None
    assert hud.virtual_pointer_in_hud_chrome((left.x + 4, left.y + 4), surf, gs_out) is False


def test_hud_is_mouse_over_menu_matches_rects():
    from game.entities.hero import Hero
    from game.ui.hud import HUD

    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(1.0, 1.0, hero_class="warrior", hero_id="s1", name="Gate")
    gs = {"selected_hero": hero, "selected_peasant": None, "selected_building": None, "hero_profiles_by_id": {"s1": object()}}
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    lr = hud._last_left_rect
    assert lr is not None
    assert hud.is_mouse_over_menu((lr.centerx, lr.centery), gs, None) is True
    assert hud.is_mouse_over_menu((lr.right + 80, lr.centery), gs, None) is False


def test_hud_scroll_active_menu_maps_direction_and_clamps():
    from game.entities.hero import Hero
    from game.ui.hud import HUD

    pygame.init()
    hud = HUD(1920, 1080)
    hero = Hero(1.0, 1.0, hero_class="warrior", hero_id="s1", name="Ramp")
    gs = {"selected_hero": hero, "selected_peasant": None, "selected_building": None, "hero_profiles_by_id": {"s1": object()}}
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    lr = hud._last_left_rect
    hud._hero_panel._menu_max_scroll = 48
    hud._hero_panel.menu_scroll_px = 0
    assert hud.scroll_active_menu(1, (lr.centerx, lr.centery), gs, None) is True
    assert hud._hero_panel.menu_scroll_px > 0
    for _ in range(20):
        hud.scroll_active_menu(-1, (lr.centerx, lr.centery), gs, None)
    assert hud._hero_panel.menu_scroll_px == 0


def test_wheel_zoom_skipped_when_mock_hud_reports_menu_hover():
    """Guards regressions: consume menu scroll before zoom_by (InputHandler wheel path)."""
    from unittest.mock import MagicMock

    from game.input_handler import InputHandler
    from game.input_manager import InputEvent

    cmds = MagicMock()
    cmds._skip_event_processing_frames = 0
    cmds.dev_tools_panel = None
    cmds.pause_menu.visible = False
    cmds.paused = False
    cmds.input_manager.get_mouse_pos = MagicMock(return_value=(123, 456))
    cmds.get_game_state.return_value = {}
    cmds.building_panel = None
    cmds.hud = MagicMock()
    cmds.hud.handle_menu_scroll = MagicMock(return_value=True)
    cp = MagicMock()
    cp.is_active = MagicMock(return_value=False)
    cmds.hud._chat_panel = cp
    cmds.input_manager.get_events = MagicMock(
        return_value=[InputEvent(type="WHEEL", wheel_y=1)]
    )
    cmds.zoom_by = MagicMock()

    ih = InputHandler(cmds)
    ih.process_events()
    cmds.hud.handle_menu_scroll.assert_called()
    assert cmds.hud.handle_menu_scroll.call_args[0][0] == (123, 456)
    cmds.zoom_by.assert_not_called()

    cmds.hud.handle_menu_scroll.reset_mock()
    cmds.hud.handle_menu_scroll.return_value = False
    cmds.input_manager.get_events = MagicMock(
        return_value=[InputEvent(type="WHEEL", wheel_y=-1)]
    )
    ih.process_events()
    cmds.zoom_by.assert_called()


def test_hud_handle_menu_scroll_building_panel_consume_without_content_scroll():
    """R11: Wheel over building menu must not fall through to zoom when there is no overflow."""
    from game.ui.hud import HUD
    from game.ui.building_panel import BuildingPanel

    pygame.init()
    hud = HUD(1920, 1080)
    gs = {"selected_hero": None, "selected_peasant": None, "selected_building": object(), "heroes": []}
    surf = pygame.Surface((1920, 1080))
    hud.render(surf, gs)
    lr = hud._last_left_rect
    assert lr is not None
    bp = BuildingPanel(1920, 1080)
    bp.visible = True
    bp.select_building(object(), [])
    bp.panel_x = lr.x
    bp.panel_y = lr.y
    bp.panel_width = lr.width
    bp.panel_height = min(240, lr.height)
    bp._menu_max_scroll = 0
    assert bp.apply_menu_scroll(1) is False
    mid = (lr.x + lr.width // 2, lr.y + min(80, lr.height // 2))
    assert hud.handle_menu_scroll(mid, 1, gs, bp) is True
