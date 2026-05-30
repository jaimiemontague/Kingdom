"""Keyboard input — mechanical extraction of InputHandler.handle_keydown.

WK77 Round B-2e: ``handle_keydown`` moved verbatim from ``game/input_handler.py``
(WK69/WK75/WK76 pure-move pattern). Takes the live ``InputHandler`` as ``ih``; the
body is the original method body with ``self.`` rewritten to ``ih.``.
``game/input_handler.py`` keeps a 1-line delegating wrapper. Behavior is byte-identical.

The WK70 W2 build-hotkey reverse-map ``BUILD_HOTKEY_TO_TYPE`` lives on
``game/input_handler.py`` (single source) and is imported here for the hotkey branch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import DEFAULT_SPEED_TIER, ZOOM_STEP
from game.sim.timebase import get_time_multiplier, set_time_multiplier
from game.ui.micro_view_manager import ViewMode
from game.ui.speed_control import SPEED_TIERS

if TYPE_CHECKING:
    from game.input_handler import InputHandler


def handle_keydown(ih: "InputHandler", event):
    """Handle keyboard input."""
    # WK70 W2 reverse hotkey map lives on input_handler (single source); lazy-import to
    # avoid a top-level game.input_handler import (no cycle — the wrapper imports us lazily).
    from game.input_handler import BUILD_HOTKEY_TO_TYPE
    c = ih.commands

    # --- Universal command mode input (Enter to open, typed text captured) ---
    if getattr(c, '_command_mode', False):
        # Command mode active: consume all keystrokes for typing
        if event.key in ('enter', '13'):
            cmd = getattr(c, '_command_buffer', '')
            if cmd:
                c.process_command(cmd)
            c._command_mode = False
            c._command_buffer = ''
            return
        elif event.key == 'esc':
            c._command_mode = False
            c._command_buffer = ''
            return
        elif event.key in ('backspace', '8'):
            c._command_buffer = c._command_buffer[:-1]
            return
        else:
            # Try to extract the typed character from the raw pygame event
            raw = getattr(event, 'raw_event', None)
            ch = None
            if raw is not None:
                ch = getattr(raw, 'unicode', None)
            if ch and ch.isprintable():
                c._command_buffer += ch
            elif event.key and len(event.key) == 1 and event.key.isprintable():
                c._command_buffer += event.key
            return

    # ESC menu takes priority
    if event.key == 'esc':
        from game.ui.micro_view_manager import ViewMode
        micro_view = getattr(c, "micro_view", None)
        mode = getattr(micro_view, "mode", None) if micro_view else None

        # wk18: If in HERO_FOCUS, exit chat then hero focus (same order as _clear_hero_selection)
        if mode == ViewMode.HERO_FOCUS:
            chat_panel = getattr(c.hud, "_chat_panel", None)
            if chat_panel is not None and getattr(chat_panel, "is_active", lambda: False)():
                chat_panel.end_conversation()
            if micro_view:
                micro_view.exit_hero_focus()
            return

        # wk14: close chat first if active
        chat_panel = getattr(c.hud, "_chat_panel", None)
        if chat_panel is not None and getattr(chat_panel, "is_active", lambda: False)():
            chat_panel.end_conversation()
            return
        # wk13/wk14: exit interior or quest view (before opening pause menu)
        micro_view = getattr(c, "micro_view", None)
        mode = getattr(micro_view, "mode", None) if micro_view else None
        if micro_view is not None and mode == ViewMode.INTERIOR:
            if getattr(c, "audio_system", None) is not None:
                c.audio_system.stop_interior_ambient()
            micro_view.exit_interior()
            return
        if micro_view is not None and mode == ViewMode.QUEST:
            micro_view.exit_quest()
            return
        if c.pause_menu.visible:
            # Close menu (resume game)
            c.pause_menu.close()
            c.paused = False
        else:
            # Open menu (pause game)
            c.pause_menu.open()
            c.paused = True
            # Also close building panels when opening menu
            if c.building_list_panel.visible:
                c.building_list_panel.close()
                c.building_menu.cancel_selection()
            if c.building_menu.selected_building:
                c.building_menu.cancel_selection()
        return  # Consume ESC when menu is involved

    # wk14: when chat is active, consume ALL keystrokes (typing, Enter, etc.)
    # Must run before pause/menu checks so chat works even at low speed tiers.
    # Ursina queues InputEvent(KEYDOWN) without pygame raw_event — use generic key path.
    chat_panel = getattr(c.hud, "_chat_panel", None)
    if chat_panel is not None and getattr(chat_panel, "is_active", lambda: False)():
        result = None
        if event.raw_event:
            result = chat_panel.handle_keydown(event.raw_event)
        else:
            mods = (
                c.input_manager.get_key_mods()
                if getattr(c, "input_manager", None)
                else {}
            )
            result = chat_panel.handle_generic_keydown(event.key, mods)
        if result == "send_message":
            text = getattr(chat_panel, "get_pending_message", lambda: "")()
            if text and getattr(chat_panel, "hero_target", None) is not None:
                c.send_player_message(chat_panel.hero_target, text)
        elif result == "end_conversation":
            chat_panel.end_conversation()
        return

    # Block world input when menu is open
    if c.pause_menu.visible:
        return

    # Block world camera/zoom input while paused (even if menu not visible).
    if c.paused:
        return

    # Enter key opens universal command mode (when no chat panel is active)
    if event.key in ('enter', '13'):
        c._command_mode = True
        c._command_buffer = ''
        return

    if event.key == 'tab':
        # Toggle right-side panel
        if hasattr(c.hud, "toggle_right_panel"):
            c.hud.toggle_right_panel()
        return

    # WK70 W2: build hotkeys (1-8 + t + u) via the derived reverse-map (was an if/elif
    # chain). Keys are lowercased to match event.key; see BUILD_HOTKEY_TO_TYPE above.
    # WK34 REMOVED — will return in future sprint:
    # gnome_hovel (G), elven_bungalow (E), dwarven_settlement (V),
    # ballista_tower (Y), wizard_tower (O), fairgrounds (F), library (I), royal_gardens (R)
    elif event.key in BUILD_HOTKEY_TO_TYPE:
        ih.select_building_for_placement(BUILD_HOTKEY_TO_TYPE[event.key])

    elif event.key == 'h':
        # Hire a hero
        c.try_hire_hero()

    elif event.key == 'space':
        # Center view on castle and reset to starting zoom
        c.center_on_castle(reset_zoom=True)

    elif event.key == 'f1':
        # Toggle debug panel
        c.debug_panel.toggle()
    elif event.key == 'f2':
        # Toggle perf overlay
        c.show_perf = not c.show_perf
    elif event.key == 'f3':
        # Toggle HUD help/controls overlay
        if hasattr(c.hud, "toggle_help"):
            c.hud.toggle_help()
    elif event.key == 'f4':
        # WK18: Toggle Dev Tools overlay (AI/LLM log)
        if hasattr(c, "dev_tools_panel") and hasattr(c.dev_tools_panel, "toggle"):
            c.dev_tools_panel.toggle()

    elif event.key == 'f12':
        # Manual screenshot capture
        c.capture_screenshot()

    elif event.key == 'b':
        # Place a bounty at mouse position
        c.place_bounty()

    elif event.key == 'p':
        # Use potion for selected hero
        if c.selected_hero and getattr(c.selected_hero, "is_alive", False) and hasattr(c.selected_hero, "use_potion"):
            if c.selected_hero.use_potion():
                c.hud.add_message(f"{c.selected_hero.name} used a potion!", (100, 255, 100))

    # Zoom controls (+/- and keypad)
    elif event.key in ('=', '+'):
        c.zoom_by(ZOOM_STEP)
    elif event.key in ('-',):
        c.zoom_by(1.0 / ZOOM_STEP)

    # Speed controls (wk12 Chronos): [ slower, ] faster, ` pause toggle
    elif event.key == '`':
        current = get_time_multiplier()
        if current <= 0.0:
            before = getattr(c, "_speed_before_pause", DEFAULT_SPEED_TIER)
            set_time_multiplier(before)
        else:
            c._speed_before_pause = current
            set_time_multiplier(0.0)
    elif event.key == '[':
        current = get_time_multiplier()
        idx = next((i for i, m in enumerate(SPEED_TIERS) if abs(m - current) < 0.01), 0)
        idx = max(0, idx - 1)
        set_time_multiplier(SPEED_TIERS[idx])
    elif event.key == ']':
        current = get_time_multiplier()
        idx = next((i for i, m in enumerate(SPEED_TIERS) if abs(m - current) < 0.01), len(SPEED_TIERS) - 1)
        idx = min(len(SPEED_TIERS) - 1, idx + 1)
        set_time_multiplier(SPEED_TIERS[idx])
