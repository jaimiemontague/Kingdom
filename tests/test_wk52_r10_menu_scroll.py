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
