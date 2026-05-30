"""
Input handling extracted from GameEngine.

WK63 Wave 2: InputHandler now types its command aliases as narrow Protocols
(CameraCommands, SelectionCommands, PlacementCommands, MenuCommands,
GameStateCommands) instead of the old monolithic GameCommands.
"""
from typing import TYPE_CHECKING

import pygame

from config import DEFAULT_SPEED_TIER, ZOOM_STEP, COLOR_WHITE
from game.content.buildings import BUILDING_DEFS
from game.sim.timebase import get_time_multiplier, set_time_multiplier
from game.ui.micro_view_manager import ViewMode
from game.ui.speed_control import SPEED_TIERS

# WK70 W2: reverse hotkey map {event_key: building_type} derived from the single-source
# BUILDING_DEFS, replacing the old hardcoded if/elif chain. Keys are lowercased to match the
# values pygame's key.name() delivers for letter keys (the pre-WK70 chain fired on lowercase
# 't'/'u' even though the catalog hotkey dict stores 'T'/'U'); digit hotkeys are unchanged.
# Byte-identical to the old chain's behavior (1-8 + t + u place the same buildings).
BUILD_HOTKEY_TO_TYPE = {
    d.hotkey.lower(): k
    for k, d in BUILDING_DEFS.items()
    if d.placeable and d.hotkey
}

if TYPE_CHECKING:
    from game.game_commands import (
        CameraCommands,
        SelectionCommands,
        PlacementCommands,
        MenuCommands,
        GameStateCommands,
    )


class InputHandler:
    """Centralized input event routing for the game via narrow command protocols (WK63)."""

    def __init__(self, commands) -> None:
        # commands implements all five protocols (EngineCommandHub)
        self.commands = commands
        self.camera: "CameraCommands" = commands
        self.selection: "SelectionCommands" = commands
        self.placement: "PlacementCommands" = commands
        self.menu: "MenuCommands" = commands
        self.state: "GameStateCommands" = commands

    def process_events(self):
        """Process input events."""
        c = self.commands

        # On some Windows/SDL builds, the first event poll immediately after a set_mode() can
        # intermittently crash inside SDL_PumpEvents (no Python exception). Avoid calling
        # any event APIs for a couple frames after a mode switch.
        skip_frames = int(getattr(c, "_skip_event_processing_frames", 0) or 0)
        if skip_frames > 0:
            c._skip_event_processing_frames = skip_frames - 1
            return

        events = c.input_manager.get_events()

        for event in events:
            # Note: Because the DevToolsPanel still expects Pygame events natively, we pass raw_event 
            # if we are still using Pygame under the hood, but this is a temporary bridge.
            if getattr(c, "dev_tools_panel", None) and c.dev_tools_panel.visible:
                if event.raw_event and c.dev_tools_panel.handle_event(event.raw_event):
                    continue

            if event.type == 'QUIT':
                c.running = False

            elif event.type == 'KEYDOWN':
                self.handle_keydown(event)

            elif event.type == 'VIDEORESIZE':
                c.apply_display_settings(c.display_mode, event.pos)

            elif event.type == 'MOUSEDOWN':
                self.handle_mousedown(event)

            elif event.type == 'MOUSEUP':
                # Menu slider drag end
                if c.pause_menu.visible and event.button == 1:
                    c.pause_menu.handle_mouseup(event.pos)
                if event.button == 1 and hasattr(c.hud, "handle_sidebar_split_pointer_up"):
                    if c.hud.handle_sidebar_split_pointer_up() is True:
                        bp = getattr(c, "building_panel", None)
                        fn = getattr(bp, "on_request_ursina_hud_upload", None) if bp else None
                        if callable(fn):
                            fn()
                # End borderless drag
                if event.button == 1 and getattr(c, "_borderless_drag_active", False):
                    c._borderless_drag_active = False
                    c._borderless_drag_start_pos = None
                    c._borderless_drag_window_offset = None

            elif event.type == 'MOUSEMOTION':
                self.handle_mousemove(event)

            elif event.type == 'WHEEL':
                # Pause menu: Controls page uses wheel to scroll the keybind list.
                if c.pause_menu.visible:
                    if getattr(c.pause_menu, "current_page", "") == "controls":
                        wy = int(event.wheel_y or 0)
                        if wy != 0:
                            c.pause_menu.handle_wheel(wy)
                    continue
                pos = None
                im = getattr(c, "input_manager", None)
                if im is not None:
                    gm = getattr(im, "get_mouse_pos", None)
                    if callable(gm):
                        try:
                            pos = gm()
                        except Exception:
                            pos = None
                if pos is None or len(pos) < 2:
                    pos = getattr(c, "_last_ui_cursor_pos", None)
                if pos is None or len(pos) < 2:
                    try:
                        pos = pygame.mouse.get_pos()
                    except Exception:
                        pos = (0, 0)
                if c.hud.handle_menu_scroll(tuple(pos), int(event.wheel_y or 0), c.get_game_state(), c.building_panel):
                    continue
                # Chat typing: do not zoom the world (same as blocking hotkeys in handle_keydown).
                _cp = getattr(c.hud, "_chat_panel", None)
                if _cp is not None and getattr(_cp, "is_active", lambda: False)():
                    continue
                # Do not zoom while paused without menu.
                if c.paused:
                    continue
                # event.wheel_y: +1 scroll up, -1 scroll down
                if event.wheel_y > 0:
                    c.zoom_by(ZOOM_STEP)
                elif event.wheel_y < 0:
                    c.zoom_by(1.0 / ZOOM_STEP)

    def select_building_for_placement(self, building_type: str) -> bool:
        from game.input import placement
        return placement.select_building_for_placement(self, building_type)

    def handle_keydown(self, event):
        from game.input import keyboard
        return keyboard.handle_keydown(self, event)

    def _clear_hero_selection(self):
        """Helper to clear hero selection and close chat/focus panels.

        NOTE: Does NOT clear selected_enemy — call sites that also need
        enemy cleared should do so explicitly (e.g. empty-space deselect).
        """
        chat_panel = getattr(self.commands.hud, "_chat_panel", None)
        if chat_panel is not None:
            chat_panel.end_conversation()
        micro_view = getattr(self.commands, "micro_view", None)
        if micro_view is not None:
            micro_view.exit_hero_focus()
        self.commands.selected_hero = None

    def handle_mousedown(self, event):
        from game.input import mouse
        return mouse.handle_mousedown(self, event)

    def handle_mousemove(self, event):
        from game.input import mouse
        return mouse.handle_mousemove(self, event)
