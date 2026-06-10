"""Mouse input — mechanical extraction of InputHandler.handle_mousedown / handle_mousemove.

WK77 Round B-2e: ``handle_mousedown`` and ``handle_mousemove`` moved verbatim from
``game/input_handler.py`` (WK69/WK75/WK76 pure-move pattern). Each takes the live
``InputHandler`` as ``ih``; the body is the original method body with ``self.``
rewritten to ``ih.`` (``self.commands`` -> ``ih.commands``,
``self._clear_hero_selection()`` -> ``ih._clear_hero_selection()``,
``self.select_building_for_placement`` -> ``ih.select_building_for_placement``).
``game/input_handler.py`` keeps 1-line delegating wrappers. Behavior is byte-identical.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from config import ZOOM_STEP
from game.ui.micro_view_manager import ViewMode

if TYPE_CHECKING:
    from game.input_handler import InputHandler


def handle_mousedown(ih: "InputHandler", event):
    """Handle mouse clicks."""
    c = ih.commands

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

    # While paused (without menu), allow only modal overlays (memorial / building interior) LMB,
    # plus LMB that lands inside a visible building panel so its buttons (Enter/Demolish/Hire/
    # research/etc.) still work when paused for a non-modal reason (e.g. speed-control pause).
    # WK68 H1: world-selection clicks stay blocked — the building panel consumes (returns True
    # for) any click inside its bounds before world pick is reached, so only panel-area clicks
    # pass through here.
    if c.paused and not c.pause_menu.visible:
        mc = getattr(c.hud, "memorial_card", None)
        bio = getattr(c.hud, "building_interior_overlay", None)
        mem_vis = mc is not None and getattr(mc, "visible", False)
        bio_vis = bio is not None and getattr(bio, "visible", False)
        bp = getattr(c, "building_panel", None)
        panel_hit = False
        if event.button == 1 and bp is not None and getattr(bp, "visible", False):
            panel_rect = pygame.Rect(
                int(getattr(bp, "panel_x", 0)),
                int(getattr(bp, "panel_y", 0)),
                int(getattr(bp, "panel_width", 0)),
                int(getattr(bp, "panel_height", 0)),
            )
            panel_hit = panel_rect.collidepoint(event.pos)
        if event.button != 1 or not (mem_vis or bio_vis or panel_hit):
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
            if hasattr(c.hud, "handle_sidebar_split_pointer_down"):
                down_fn = c.hud.handle_sidebar_split_pointer_down
                if down_fn(event.pos, gs) is True:
                    return
            if hasattr(c.hud, "handle_click"):
                action = c.hud.handle_click(event.pos, gs)
                if action == "quit":
                    c.running = False
                    return
                if action == "close_selection":
                    ih._clear_hero_selection()
                    c.building_panel.deselect()
                    c.selected_building = None
                    c.selected_peasant = None
                    c.selected_enemy = None
                    return
                if action in ("pin_hero", "unpin_hero", "recall_pinned_hero"):
                    if hasattr(c, "apply_hud_pin_action"):
                        c.apply_hud_pin_action(action)
                    return
                if action in (
                    "open_memorial",
                    "close_memorial_unpause",
                    "expand_watch_card",
                    "open_building_interior",
                    "close_building_interior_unpause",
                    "confirm_demolish",
                ):
                    if hasattr(c, "apply_hud_pin_action"):
                        c.apply_hud_pin_action(action)
                    return
                if action == "watch_card_chevron_toggle":
                    return
                if action == "sidebar_split_drag":
                    return
                if action in ("chat_band_close", "chat_band_open"):
                    return
                # WK135: inventory window — modal click consumed / open request.
                if action == "inventory_click":
                    return
                if isinstance(action, dict) and action.get("type") == "open_inventory":
                    hero = action.get("hero")
                    inv = getattr(c.hud, "inventory_panel", None)
                    if inv is not None and hero is not None:
                        inv.open(hero)
                    return
                if isinstance(action, dict) and action.get("type") == "select_hero_at_world":
                    c.try_select_hero_at_world(float(action.get("wx", 0.0)), float(action.get("wy", 0.0)))
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
                        c.building_panel.deselect()
                        c.selected_building = None
                        # WK61-R4-BUG-007: Chat opens conversation only — never pin.
                        # If this hero is already pinned, expand the watch-card chat band.
                        hid = str(getattr(hero, "hero_id", "") or "").strip()
                        pin_slot = getattr(c.hud, "_pin_slot", None)
                        if hid and pin_slot is not None and pin_slot.hero_id == hid:
                            c.hud._watch_card_expanded = True
                            c.hud._chat_visible = True
                    chat_panel = getattr(c.hud, "_chat_panel", None)
                    if chat_panel is not None and hero is not None:
                        chat_panel.start_conversation(hero)
                    return
                if isinstance(action, dict) and action.get("type") == "select_hero":
                    hero = action.get("hero")
                    if hero is not None:
                        c.selected_hero = hero
                        c.selected_building = None
                    return
                if action == "end_conversation":
                    ih._clear_hero_selection()
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

        try:
            mc = getattr(c.hud, "memorial_card", None)
            bio = getattr(c.hud, "building_interior_overlay", None)
            if mc is not None and getattr(mc, "visible", False):
                return
            if bio is not None and getattr(bio, "visible", False):
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
                ih.select_building_for_placement(result)
                return
            # Click outside panel - close it
            c.building_list_panel.close()
            return

        # Check if clicking on build catalog panel (castle-driven)
        if c.build_catalog_panel.visible:
            building_type = c.build_catalog_panel.handle_click(event.pos, c.economy, c.buildings)
            if building_type:
                ih.select_building_for_placement(building_type)
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
                building = result.get("building")
                if building and building in c.buildings and building.building_type != "castle":
                    dco = getattr(c.hud, "demolish_confirm_overlay", None)
                    if dco is not None:
                        dco.show(building)
                return
            elif isinstance(result, dict) and result.get("type") == "enter_building":
                building = result.get("building")
                bio = getattr(c.hud, "building_interior_overlay", None)
                if bio is not None and building is not None:
                    bio.show(building)
                    if hasattr(c, "apply_hud_pin_action"):
                        c.apply_hud_pin_action("open_building_interior")
                return
            elif isinstance(result, dict) and result.get("type") == "hire_hero":
                building = result.get("building")
                if building is not None:
                    c.selected_building = building  # target THIS guild
                c.try_hire_hero()
                return
            elif result:  # Other panel clicks (True)
                return

        if c.building_menu.selected_building:
            # Try to place building
            pos = c.building_menu.get_placement()
            if pos:
                c.place_building(pos[0], pos[1])
        elif getattr(c.hud, "_left_split_drag_kind", None) is not None:
            # WK61-R11 BUG-005: block world pick/placement while sidebar split drag is active.
            return
        else:
            # WK61-R4-BUG-002: Ursina screen-space pick before floor-ray distance checks.
            if getattr(c, "_ursina_viewer", False) and c.try_ursina_select_unit_at_screen(event.pos):
                c.building_panel.deselect()
                c.selected_building = None
            elif c.try_select_hero(event.pos):
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
                ih._clear_hero_selection()
            elif c.try_select_enemy(event.pos):
                ih._clear_hero_selection()
                c.building_panel.deselect()
            elif c.try_select_building(event.pos):
                ih._clear_hero_selection()
                c.selected_peasant = None
            else:
                # Clicked on empty space
                ih._clear_hero_selection()
                c.building_panel.deselect()
                c.selected_building = None
                c.selected_peasant = None
                c.selected_enemy = None

    elif event.button == 3:  # Right click
        # Indirect-control game: no direct hero commands.
        pass


def handle_mousemove(ih: "InputHandler", event):
    """Handle mouse movement."""
    c = ih.commands
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
        wptr = getattr(c, "_ursina_pointer_world_sim", None)
        if wptr is not None:
            c.building_menu.update_preview_world_pixels(
                wptr[0], wptr[1], c.world, c.buildings
            )
        else:
            c.building_menu.update_preview(
                event.pos,
                c.world,
                c.buildings,
                (c.camera_x, c.camera_y),
                zoom=c.zoom,
            )

    move_fn = getattr(c.hud, "handle_sidebar_split_pointer_move", None)
    if callable(move_fn):
        gs = c.get_game_state()
        if move_fn(event.pos, gs) is True:
            bp = getattr(c, "building_panel", None)
            fn = getattr(bp, "on_request_ursina_hud_upload", None) if bp else None
            if callable(fn):
                fn()

    # Update building list panel hover state
    if c.building_list_panel.visible:
        c.building_list_panel.update_hover(event.pos, c.economy, c.buildings)

    # Update building panel hover state
    c.building_panel.update_hover(event.pos)

    # Update build catalog panel hover state
    if c.build_catalog_panel.visible:
        c.build_catalog_panel.update_hover(event.pos)
