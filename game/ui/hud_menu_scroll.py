"""Mouse-wheel menu-scroll routing, extracted from game.ui.hud (WK103).

Decide whether a pointer position is over a wheel-capturing menu (a visible
building panel with a selected building, or the left-column hero menu) and route
the wheel to the appropriate panel's apply_menu_scroll. All HUD state
(_last_left_rect, _hero_menu_chat_rect, _hero_menu_hero_rect, _hero_panel) lives on
the HUD instance and is reached here via the ``hud`` argument; HUD keeps 1-line
delegating wrappers (exact names: is_mouse_over_menu, scroll_active_menu,
handle_menu_scroll -- input_handler.py + ursina_app.py call handle_menu_scroll).
Acyclic: hud.py imports this module lazily inside the wrappers; this module imports
only pygame + HUD under TYPE_CHECKING.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import pygame
if TYPE_CHECKING:
    from game.ui.hud import HUD


def is_mouse_over_menu(
    hud,
    pos: tuple[int, int],
    game_state: dict,
    building_panel,
) -> bool:
    """True if ``pos`` (``engine.screen`` / virtual framebuffer pixels) is over a menu that captures wheel."""
    x, y = int(pos[0]), int(pos[1])
    lr = hud._last_left_rect
    if (
        building_panel is not None
        and getattr(building_panel, "visible", False)
        and getattr(building_panel, "selected_building", None) is not None
    ):
        bx = int(getattr(building_panel, "panel_x", 0))
        by = int(getattr(building_panel, "panel_y", 0))
        bw = int(getattr(building_panel, "panel_width", 0))
        bh = int(getattr(building_panel, "panel_height", 0))
        if bw > 0 and bh >= 0 and pygame.Rect(bx, by, bw, bh).collidepoint(x, y):
            return True
    if (
        lr is not None
        and lr.collidepoint(x, y)
        and game_state.get("selected_hero") is not None
        and game_state.get("selected_peasant") is None
        and game_state.get("selected_building") is None
    ):
        return True
    return False


def scroll_active_menu(
    hud,
    direction: int,
    pointer_pos: tuple[int, int],
    game_state: dict,
    building_panel,
) -> bool:
    """Scroll the menu under ``pointer_pos``.

    ``direction`` +1 moves content downward (wheel ``wheel_y=-1``); -1 moves content up.
    """
    wheel_y = -int(direction)
    if wheel_y == 0:
        return False
    return hud.handle_menu_scroll(pointer_pos, wheel_y, game_state, building_panel)


def handle_menu_scroll(
    hud,
    pos: tuple[int, int],
    wheel_y: int,
    game_state: dict,
    building_panel,
) -> bool:
    if wheel_y == 0:
        return False
    if not hud.is_mouse_over_menu(pos, game_state, building_panel):
        return False
    x, y = int(pos[0]), int(pos[1])
    lr = hud._last_left_rect
    if (
        building_panel is not None
        and getattr(building_panel, "visible", False)
        and getattr(building_panel, "selected_building", None) is not None
    ):
        bx = int(getattr(building_panel, "panel_x", 0))
        by = int(getattr(building_panel, "panel_y", 0))
        bw = int(getattr(building_panel, "panel_width", 0))
        bh = int(getattr(building_panel, "panel_height", 0))
        if bw > 0 and bh >= 0 and pygame.Rect(bx, by, bw, bh).collidepoint(x, y):
            if building_panel.apply_menu_scroll(int(wheel_y)):
                return True
            return True
    if (
        lr is not None
        and game_state.get("selected_hero") is not None
        and game_state.get("selected_peasant") is None
        and game_state.get("selected_building") is None
    ):
        hmcr = getattr(hud, "_hero_menu_chat_rect", None)
        if hmcr is not None and hmcr.collidepoint(x, y):
            return True
        hero_rect = getattr(hud, "_hero_menu_hero_rect", None) or lr
        if hero_rect.collidepoint(x, y):
            if hud._hero_panel.apply_menu_scroll(int(wheel_y)):
                return True
            return True
    return False
