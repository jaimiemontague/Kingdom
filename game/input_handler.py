"""
Input handling extracted from GameEngine.
"""
from typing import TYPE_CHECKING

import pygame

from config import DEFAULT_SPEED_TIER, ZOOM_STEP, COLOR_WHITE
from game.sim.timebase import get_time_multiplier, set_time_multiplier
from game.ui.micro_view_manager import ViewMode
from game.ui.speed_control import SPEED_TIERS

if TYPE_CHECKING:
    from game.game_commands import GameCommands


class InputHandler:
    """Centralized input event routing for the game via a GameCommands surface (WK38)."""

    def __init__(self, commands: "GameCommands"):
        self.commands = commands

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
        """
        Unified method for selecting a building for placement.
        Called by both hotkeys and panel clicks.
        Returns True if selection succeeded, False otherwise.
        """
        c = self.commands

        # Check affordability
        if not c.economy.can_afford_building(building_type):
            c.hud.add_message("Not enough gold!", (255, 100, 100))
            return False

        # Check prerequisites. Empty list = no prerequisite (e.g. temple).
        from config import BUILDING_PREREQUISITES
        if building_type in BUILDING_PREREQUISITES:
            required = BUILDING_PREREQUISITES[building_type]
            if required:
                has_prereq = False
                for building in c.buildings:
                    if building.building_type in required and getattr(building, "is_constructed", False):
                        has_prereq = True
                        break
                if not has_prereq:
                    req_names = ", ".join(b.replace("_", " ").title() for b in required)
                    c.hud.add_message(f"Requires: {req_names}", (255, 200, 100))
                    return False

        # Check constraints (mutually exclusive)
        from config import BUILDING_CONSTRAINTS
        if building_type in BUILDING_CONSTRAINTS:
            excluded = BUILDING_CONSTRAINTS[building_type]
            for building in c.buildings:
                if building.building_type in excluded:
                    excl_name = building.building_type.replace("_", " ").title()
                    c.hud.add_message(f"Cannot build: {excl_name} exists", (255, 200, 100))
                    return False

        # All checks passed - select building
        c.building_menu.select_building(building_type)
        # Close panel if open
        if c.building_list_panel.visible:
            c.building_list_panel.close()
        return True

    def handle_keydown(self, event):
        """Handle keyboard input."""
        c = self.commands

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

        if event.key == 'tab':
            # Toggle right-side panel
            if hasattr(c.hud, "toggle_right_panel"):
                c.hud.toggle_right_panel()
            return

        elif event.key == '1':
            self.select_building_for_placement("warrior_guild")
        elif event.key == '2':
            self.select_building_for_placement("marketplace")
        elif event.key == '3':
            self.select_building_for_placement("ranger_guild")
        elif event.key == '4':
            self.select_building_for_placement("rogue_guild")
        elif event.key == '5':
            self.select_building_for_placement("wizard_guild")
        elif event.key == '6':
            self.select_building_for_placement("blacksmith")
        elif event.key == '7':
            self.select_building_for_placement("inn")
        elif event.key == '8':
            self.select_building_for_placement("trading_post")
        elif event.key == 't':
            self.select_building_for_placement("temple")
        # WK34 REMOVED — will return in future sprint:
        # gnome_hovel (G), elven_bungalow (E), dwarven_settlement (V),
        # ballista_tower (Y), wizard_tower (O), fairgrounds (F), library (I), royal_gardens (R)
        elif event.key == 'u':
            self.select_building_for_placement("guardhouse")

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

    def _clear_hero_selection(self):
        """Helper to clear hero selection and close chat/focus panels."""
        chat_panel = getattr(self.commands.hud, "_chat_panel", None)
        if chat_panel is not None:
            chat_panel.end_conversation()
        micro_view = getattr(self.commands, "micro_view", None)
        if micro_view is not None:
            micro_view.exit_hero_focus()
        self.commands.selected_hero = None

    def handle_mousedown(self, event):
        """Handle mouse clicks."""
        c = self.commands

        # Menu input handling (takes priority)
        if c.pause_menu.visible:
            if event.button == 1:  # Left click
                action = c.pause_menu.handle_click(event.pos)
                if action == "resume":
                    c.pause_menu.close()
                    c.paused = False
                elif action == "quit":
                    c.running = False
                elif action and action.startswith("graphics_select_"):
                    # Graphics page selection (already handled in PauseMenu.handle_click)
                    pass
                elif action == "audio_slider_drag":
                    # Audio slider drag (already handled in PauseMenu.handle_mousemove)
                    pass
            return  # Consume all input when menu is open

        # While paused (without menu), do not allow world camera/zoom inputs.
        if c.paused:
            return

        _cp = getattr(c.hud, "_chat_panel", None)
        _chat_on = _cp is not None and getattr(_cp, "is_active", lambda: False)()

        # Mouse wheel zoom (older pygame uses buttons 4/5)
        if event.button == 4:
            if not _chat_on:
                c.zoom_by(ZOOM_STEP)
            return
        if event.button == 5:
            if not _chat_on:
                c.zoom_by(1.0 / ZOOM_STEP)
            return

        if event.button == 1:  # Left click
            # UI clicks should consume input before world selection.
            action = None
            try:
                gs = c.get_game_state()
                if hasattr(c.hud, "handle_click"):
                    action = c.hud.handle_click(event.pos, gs)
                    if action == "quit":
                        c.running = False
                        return
                    if action == "close_selection":
                        self._clear_hero_selection()
                        c.building_panel.deselect()
                        c.selected_building = None
                        c.selected_peasant = None
                        return
                    if action == "exit_interior":
                        if getattr(c, "micro_view", None) is not None:
                            if getattr(c, "audio_system", None) is not None:
                                c.audio_system.stop_interior_ambient()
                            c.micro_view.exit_interior()
                        return
                    if action == "exit_quest":
                        if getattr(c, "micro_view", None) is not None:
                            c.micro_view.exit_quest()
                        return
                    if isinstance(action, dict) and action.get("type") == "start_conversation":
                        hero = action.get("hero")
                        if hero is not None:
                            c.selected_hero = hero
                            c.selected_building = None
                            if hasattr(c.hud, "_micro_view"):
                                c.hud._micro_view.enter_hero_focus(hero)
                        chat_panel = getattr(c.hud, "_chat_panel", None)
                        if chat_panel is not None:
                            chat_panel.start_conversation(action["hero"])
                        return
                    if isinstance(action, dict) and action.get("type") == "select_hero":
                        hero = action.get("hero")
                        if hero is not None:
                            c.selected_hero = hero
                            c.selected_building = None
                            if hasattr(c.hud, "_micro_view"):
                                c.hud._micro_view.enter_hero_focus(hero)
                        return
                    if action == "end_conversation":
                        self._clear_hero_selection()
                        return
                    if action == "build_menu_toggle":
                        # Open Build Catalog (centered grid) — same UI as castle "Build Buildings"
                        if c.build_catalog_panel.visible:
                            c.build_catalog_panel.close()
                        else:
                            c.build_catalog_panel.open()
                        return
                    if action == "hire_hero":
                        c.try_hire_hero()
                        return
                    if action == "place_bounty":
                        c.place_bounty()
                        return
            except Exception:
                pass

            # WK7 (partial): drag-to-windowed — top-bar click drops to windowed without touching SDL2.
            # (Live window-drag via pygame._sdl2 after switch caused immediate crashes on Windows.)
            try:
                display_mode = str(getattr(c, "display_mode", "windowed") or "windowed").strip().lower()
                if (not action) and display_mode in ("borderless", "fullscreen"):
                    x, y = int(event.pos[0]), int(event.pos[1])
                    if y <= 40:
                        quit_rect = getattr(c.hud, "quit_rect", None)
                        if not (quit_rect and quit_rect.collidepoint((x, y))):
                            c.request_display_settings("windowed", getattr(c, "window_size", None))
                            return
            except Exception:
                pass

            # Debug panel close/consume
            try:
                if getattr(c.debug_panel, "visible", False) and hasattr(c.debug_panel, "handle_click"):
                    if c.debug_panel.handle_click(event.pos):
                        return
            except Exception:
                pass

            # Perf overlay close/consume
            try:
                if c.show_perf and hasattr(c, "_perf_close_rect") and c._perf_close_rect and c._perf_close_rect.collidepoint(event.pos):
                    c.show_perf = False
                    return
            except Exception:
                pass

            # Check if clicking on building list panel first (if visible)
            if c.building_list_panel.visible:
                result = c.building_list_panel.handle_click(event.pos, c.economy, c.buildings)
                if result:  # Building type string
                    self.select_building_for_placement(result)
                    return
                # Click outside panel - close it
                c.building_list_panel.close()
                return

            # Check if clicking on build catalog panel (castle-driven)
            if c.build_catalog_panel.visible:
                building_type = c.build_catalog_panel.handle_click(event.pos, c.economy, c.buildings)
                if building_type:
                    self.select_building_for_placement(building_type)
                    return
                # Click outside catalog - close it
                c.build_catalog_panel.close()
                return

            # wk13/wk14: left-click on world map while in interior or quest view → exit that view, then continue
            gs = c.get_game_state()
            micro_view = getattr(c, "micro_view", None)
            right_panel_rect = gs.get("right_panel_rect")
            mode = getattr(micro_view, "mode", None) if micro_view else None
            if (
                micro_view is not None
                and right_panel_rect is not None
                and not right_panel_rect.collidepoint(event.pos)
            ):
                if mode == ViewMode.INTERIOR:
                    if getattr(c, "audio_system", None) is not None:
                        c.audio_system.stop_interior_ambient()
                    micro_view.exit_interior()
                elif mode == ViewMode.QUEST:
                    micro_view.exit_quest()
                # Ensure chat is exited if we close the interior/quest view by clicking out
                chat_panel = getattr(c.hud, "_chat_panel", None)
                if chat_panel is not None:
                    chat_panel.end_conversation()

            # Check if clicking on building panel
            if c.building_panel.visible:
                result = c.building_panel.handle_click(event.pos, c.economy, c.get_game_state())
                if isinstance(result, dict) and result.get("type") == "open_build_catalog":
                    # Open build catalog from castle
                    c.build_catalog_panel.open()
                    return
                elif isinstance(result, dict) and result.get("type") == "demolish_building":
                    # Handle player demolish action
                    building = result.get("building")
                    if building and building in c.buildings and building.building_type != "castle":
                        # Set HP to 0 to trigger cleanup
                        building.hp = 0
                        # Immediate cleanup (instant UX) - suppress auto-demolish message
                        c._cleanup_destroyed_buildings(emit_messages=False)
                        # Emit HUD message (player demolish: white)
                        building_name = building.building_type.replace("_", " ").title()
                        c.hud.add_message(f"Demolished: {building_name}", COLOR_WHITE)
                        # Deselect building (panel will close)
                        c.building_panel.deselect()
                        c.selected_building = None
                    return
                elif isinstance(result, dict) and result.get("type") == "enter_building":
                    # wk13 Living Interiors: transition right panel to interior view
                    building = result.get("building")
                    if building and getattr(c, "micro_view", None) is not None:
                        c.micro_view.enter_interior(building)
                        if getattr(c, "audio_system", None) is not None:
                            c.audio_system.start_interior_ambient(
                                getattr(building, "building_type", "") or ""
                            )
                        c.hud.right_panel_visible = True
                        c.building_panel.deselect()
                        c.selected_building = None
                    return
                elif result:  # Other panel clicks (True)
                    return

            if c.building_menu.selected_building:
                # Try to place building
                pos = c.building_menu.get_placement()
                if pos:
                    c.place_building(pos[0], pos[1])
            else:
                # Try to select hero, then tax collector, then guard, then building
                if c.try_select_hero(event.pos):
                    c.building_panel.deselect()
                    c.selected_building = None
                    c.selected_peasant = None
                elif c.try_select_tax_collector(event.pos):
                    c.building_panel.deselect()
                    c.selected_building = None
                    c.selected_peasant = None
                elif c.try_select_guard(event.pos):
                    c.building_panel.deselect()
                    c.selected_building = None
                    c.selected_peasant = None
                elif c.try_select_peasant(event.pos):
                    self._clear_hero_selection()
                elif c.try_select_building(event.pos):
                    self._clear_hero_selection()
                    c.selected_peasant = None
                else:
                    # Clicked on empty space
                    self._clear_hero_selection()
                    c.building_panel.deselect()
                    c.selected_building = None
                    c.selected_peasant = None

        elif event.button == 3:  # Right click
            # Indirect-control game: no direct hero commands.
            pass

    def handle_mousemove(self, event):
        """Handle mouse movement."""
        c = self.commands
        try:
            c._last_ui_cursor_pos = (int(event.pos[0]), int(event.pos[1]))
        except Exception:
            pass

        # Menu slider dragging (only while LMB held — matches pygame.buttons / Ursina mouse.left)
        if c.pause_menu.visible:
            lmb_held = True
            if getattr(event, "buttons", None) is not None:
                lmb_held = bool(event.buttons[0])
            elif getattr(event, "raw_event", None) is not None:
                re = event.raw_event
                if hasattr(re, "buttons") and re.buttons is not None:
                    lmb_held = bool(re.buttons[0])
            else:
                try:
                    import pygame

                    lmb_held = bool(pygame.mouse.get_pressed()[0])
                except Exception:
                    lmb_held = True
            c.pause_menu.handle_mousemove(event.pos, lmb_held=lmb_held)
            return  # Consume mouse movement when menu is open

        # Borderless drag live-drag handling (only when already in windowed and past mode-switch cooldown)
        if getattr(c, "_borderless_drag_active", False) and c._borderless_drag_window_offset is not None:
            skip_frames = int(getattr(c, "_skip_event_processing_frames", 0) or 0)
            if skip_frames > 0:
                # Do not touch SDL2 window during cooldown after set_mode(); can crash on Windows.
                pass
            elif str(getattr(c, "display_mode", "windowed")).strip().lower() == "windowed":
                try:
                    import pygame._sdl2
                    sdl_window = pygame._sdl2.Window.from_display_module()
                    if sdl_window:
                        new_x = event.pos[0] + c._borderless_drag_window_offset[0]
                        new_y = event.pos[1] + c._borderless_drag_window_offset[1]
                        sdl_window.position = (new_x, new_y)
                except (ImportError, AttributeError):
                    pass
                except Exception:
                    # Avoid repeated crashes: clear drag state on any error
                    c._borderless_drag_active = False
                    c._borderless_drag_start_pos = None
                    c._borderless_drag_window_offset = None

        if c.building_menu.selected_building:
            c.building_menu.update_preview(
                event.pos,
                c.world,
                c.buildings,
                (c.camera_x, c.camera_y),
                zoom=c.zoom,
            )

        # Update building list panel hover state
        if c.building_list_panel.visible:
            c.building_list_panel.update_hover(event.pos, c.economy, c.buildings)

        # Update building panel hover state
        c.building_panel.update_hover(event.pos)

        # Update build catalog panel hover state
        if c.build_catalog_panel.visible:
            c.build_catalog_panel.update_hover(event.pos)
