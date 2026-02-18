"""
Input handling extracted from GameEngine.
"""
from typing import TYPE_CHECKING

import pygame

from config import ZOOM_STEP, COLOR_WHITE

if TYPE_CHECKING:
    from game.engine import GameEngine


class InputHandler:
    """Centralized input event routing for GameEngine."""

    def __init__(self, engine: "GameEngine"):
        self.engine = engine

    def process_events(self):
        """Process input events."""
        engine = self.engine

        # On some Windows/SDL builds, the first event poll immediately after a set_mode() can
        # intermittently crash inside SDL_PumpEvents (no Python exception). Avoid calling
        # any event APIs for a couple frames after a mode switch.
        skip_frames = int(getattr(engine, "_skip_event_processing_frames", 0) or 0)
        if skip_frames > 0:
            engine._skip_event_processing_frames = skip_frames - 1
            return

        events = pygame.event.get()

        for event in events:
            if event.type == pygame.QUIT:
                engine.running = False

            elif event.type == pygame.KEYDOWN:
                self.handle_keydown(event)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.handle_mousedown(event)

            elif event.type == pygame.MOUSEBUTTONUP:
                # Menu slider drag end
                if engine.pause_menu.visible and event.button == 1:
                    engine.pause_menu.handle_mouseup(event.pos)
                # End borderless drag
                if event.button == 1 and getattr(engine, "_borderless_drag_active", False):
                    engine._borderless_drag_active = False
                    engine._borderless_drag_start_pos = None
                    engine._borderless_drag_window_offset = None

            elif event.type == pygame.MOUSEMOTION:
                self.handle_mousemove(event)

            # Pygame 2 mouse wheel event
            elif hasattr(pygame, "MOUSEWHEEL") and event.type == pygame.MOUSEWHEEL:
                # Do not zoom while paused / menu open.
                if engine.paused or engine.pause_menu.visible:
                    continue
                # event.y: +1 scroll up, -1 scroll down
                if event.y > 0:
                    engine.zoom_by(ZOOM_STEP)
                elif event.y < 0:
                    engine.zoom_by(1.0 / ZOOM_STEP)

    def select_building_for_placement(self, building_type: str) -> bool:
        """
        Unified method for selecting a building for placement.
        Called by both hotkeys and panel clicks.
        Returns True if selection succeeded, False otherwise.
        """
        engine = self.engine

        # Check affordability
        if not engine.economy.can_afford_building(building_type):
            engine.hud.add_message("Not enough gold!", (255, 100, 100))
            return False

        # Check prerequisites
        from config import BUILDING_PREREQUISITES
        if building_type in BUILDING_PREREQUISITES:
            required = BUILDING_PREREQUISITES[building_type]
            has_prereq = False
            for building in engine.buildings:
                if building.building_type in required and getattr(building, "is_constructed", False):
                    has_prereq = True
                    break
            if not has_prereq:
                req_names = ", ".join(b.replace("_", " ").title() for b in required)
                engine.hud.add_message(f"Requires: {req_names}", (255, 200, 100))
                return False

        # Check constraints (mutually exclusive)
        from config import BUILDING_CONSTRAINTS
        if building_type in BUILDING_CONSTRAINTS:
            excluded = BUILDING_CONSTRAINTS[building_type]
            for building in engine.buildings:
                if building.building_type in excluded:
                    excl_name = building.building_type.replace("_", " ").title()
                    engine.hud.add_message(f"Cannot build: {excl_name} exists", (255, 200, 100))
                    return False

        # All checks passed - select building
        engine.building_menu.select_building(building_type)
        # Close panel if open
        if engine.building_list_panel.visible:
            engine.building_list_panel.close()
        return True

    def handle_keydown(self, event):
        """Handle keyboard input."""
        engine = self.engine

        # ESC menu takes priority
        if event.key == pygame.K_ESCAPE:
            if engine.pause_menu.visible:
                # Close menu (resume game)
                engine.pause_menu.close()
                engine.paused = False
            else:
                # Open menu (pause game)
                engine.pause_menu.open()
                engine.paused = True
                # Also close building panels when opening menu
                if engine.building_list_panel.visible:
                    engine.building_list_panel.close()
                    engine.building_menu.cancel_selection()
                if engine.building_menu.selected_building:
                    engine.building_menu.cancel_selection()
            return  # Consume ESC when menu is involved

        # Block world input when menu is open
        if engine.pause_menu.visible:
            return

        # Block world camera/zoom input while paused (even if menu not visible).
        if engine.paused:
            return

        elif event.key == pygame.K_TAB:
            # Toggle right-side panel
            if hasattr(engine.hud, "toggle_right_panel"):
                engine.hud.toggle_right_panel()
            return

        elif event.key == pygame.K_1:
            self.select_building_for_placement("warrior_guild")
        elif event.key == pygame.K_2:
            self.select_building_for_placement("marketplace")
        elif event.key == pygame.K_3:
            self.select_building_for_placement("ranger_guild")
        elif event.key == pygame.K_4:
            self.select_building_for_placement("rogue_guild")
        elif event.key == pygame.K_5:
            self.select_building_for_placement("wizard_guild")
        elif event.key == pygame.K_6:
            self.select_building_for_placement("blacksmith")
        elif event.key == pygame.K_7:
            self.select_building_for_placement("inn")
        elif event.key == pygame.K_8:
            self.select_building_for_placement("trading_post")
        elif event.key == pygame.K_t:
            self.select_building_for_placement("temple_agrela")
        elif event.key == pygame.K_g:
            self.select_building_for_placement("gnome_hovel")
        elif event.key == pygame.K_e:
            self.select_building_for_placement("elven_bungalow")
        elif event.key == pygame.K_v:
            self.select_building_for_placement("dwarven_settlement")
        elif event.key == pygame.K_u:
            self.select_building_for_placement("guardhouse")
        elif event.key == pygame.K_y:
            self.select_building_for_placement("ballista_tower")
        elif event.key == pygame.K_o:
            self.select_building_for_placement("wizard_tower")
        elif event.key == pygame.K_f:
            self.select_building_for_placement("fairgrounds")
        elif event.key == pygame.K_i:
            self.select_building_for_placement("library")
        elif event.key == pygame.K_r:
            self.select_building_for_placement("royal_gardens")

        elif event.key == pygame.K_h:
            # Hire a hero
            engine.try_hire_hero()

        elif event.key == pygame.K_SPACE:
            # Center view on castle and reset to starting zoom
            engine.center_on_castle(reset_zoom=True)

        elif event.key == pygame.K_F1:
            # Toggle debug panel
            engine.debug_panel.toggle()
        elif event.key == pygame.K_F2:
            # Toggle perf overlay
            engine.show_perf = not engine.show_perf
        elif event.key == pygame.K_F3:
            # Toggle HUD help/controls overlay
            if hasattr(engine.hud, "toggle_help"):
                engine.hud.toggle_help()

        elif event.key == pygame.K_F12:
            # Manual screenshot capture
            engine.capture_screenshot()

        elif event.key == pygame.K_b:
            # Place a bounty at mouse position
            engine.place_bounty()

        elif event.key == pygame.K_p:
            # Use potion for selected hero
            if engine.selected_hero and engine.selected_hero.is_alive:
                if engine.selected_hero.use_potion():
                    engine.hud.add_message(f"{engine.selected_hero.name} used a potion!", (100, 255, 100))

        # Zoom controls (+/- and keypad)
        elif event.key in (pygame.K_EQUALS, pygame.K_KP_PLUS):
            engine.zoom_by(ZOOM_STEP)
        elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            engine.zoom_by(1.0 / ZOOM_STEP)

    def handle_mousedown(self, event):
        """Handle mouse clicks."""
        engine = self.engine

        # Menu input handling (takes priority)
        if engine.pause_menu.visible:
            if event.button == 1:  # Left click
                action = engine.pause_menu.handle_click(event.pos)
                if action == "resume":
                    engine.pause_menu.close()
                    engine.paused = False
                elif action == "quit":
                    engine.running = False
                elif action and action.startswith("graphics_select_"):
                    # Graphics page selection (already handled in PauseMenu.handle_click)
                    pass
                elif action == "audio_slider_drag":
                    # Audio slider drag (already handled in PauseMenu.handle_mousemove)
                    pass
            return  # Consume all input when menu is open

        # While paused (without menu), do not allow world camera/zoom inputs.
        if engine.paused:
            return

        # Mouse wheel zoom (older pygame uses buttons 4/5)
        if event.button == 4:
            engine.zoom_by(ZOOM_STEP)
            return
        if event.button == 5:
            engine.zoom_by(1.0 / ZOOM_STEP)
            return

        if event.button == 1:  # Left click
            # UI clicks should consume input before world selection.
            try:
                gs = engine.get_game_state()
                if hasattr(engine.hud, "handle_click"):
                    action = engine.hud.handle_click(event.pos, gs)
                    if action == "quit":
                        engine.running = False
                        return
                    if action == "close_selection":
                        engine.selected_hero = None
                        engine.building_panel.deselect()
                        engine.selected_building = None
                        return
            except Exception:
                pass

            # Debug panel close/consume
            try:
                if getattr(engine.debug_panel, "visible", False) and hasattr(engine.debug_panel, "handle_click"):
                    if engine.debug_panel.handle_click(event.pos):
                        return
            except Exception:
                pass

            # Perf overlay close/consume
            try:
                if engine.show_perf and hasattr(engine, "_perf_close_rect") and engine._perf_close_rect and engine._perf_close_rect.collidepoint(event.pos):
                    engine.show_perf = False
                    return
            except Exception:
                pass

            # Check if clicking on building list panel first (if visible)
            if engine.building_list_panel.visible:
                result = engine.building_list_panel.handle_click(event.pos, engine.economy, engine.buildings)
                if result:  # Building type string
                    self.select_building_for_placement(result)
                    return
                # Click outside panel - close it
                engine.building_list_panel.close()
                return

            # Check if clicking on build catalog panel (castle-driven)
            if engine.build_catalog_panel.visible:
                building_type = engine.build_catalog_panel.handle_click(event.pos, engine.economy, engine.buildings)
                if building_type:
                    self.select_building_for_placement(building_type)
                    return
                # Click outside catalog - close it
                engine.build_catalog_panel.close()
                return

            # Check if clicking on building panel
            if engine.building_panel.visible:
                result = engine.building_panel.handle_click(event.pos, engine.economy, engine.get_game_state())
                if isinstance(result, dict) and result.get("type") == "open_build_catalog":
                    # Open build catalog from castle
                    engine.build_catalog_panel.open()
                    return
                elif isinstance(result, dict) and result.get("type") == "demolish_building":
                    # Handle player demolish action
                    building = result.get("building")
                    if building and building in engine.buildings and building.building_type != "castle":
                        # Set HP to 0 to trigger cleanup
                        building.hp = 0
                        # Immediate cleanup (instant UX) - suppress auto-demolish message
                        engine._cleanup_destroyed_buildings(emit_messages=False)
                        # Emit HUD message (player demolish: white)
                        building_name = building.building_type.replace("_", " ").title()
                        engine.hud.add_message(f"Demolished: {building_name}", COLOR_WHITE)
                        # Deselect building (panel will close)
                        engine.building_panel.deselect()
                        engine.selected_building = None
                    return
                elif result:  # Other panel clicks (True)
                    return

            if engine.building_menu.selected_building:
                # Try to place building
                pos = engine.building_menu.get_placement()
                if pos:
                    engine.place_building(pos[0], pos[1])
            else:
                # Try to select a hero first
                if engine.try_select_hero(event.pos):
                    engine.building_panel.deselect()
                    engine.selected_building = None
                # Then try to select a building
                elif engine.try_select_building(event.pos):
                    engine.selected_hero = None
                else:
                    # Clicked on empty space
                    engine.selected_hero = None
                    engine.building_panel.deselect()
                    engine.selected_building = None

        elif event.button == 3:  # Right click
            # Indirect-control game: no direct hero commands.
            pass

    def handle_mousemove(self, event):
        """Handle mouse movement."""
        engine = self.engine

        # Menu slider dragging
        if engine.pause_menu.visible:
            engine.pause_menu.handle_mousemove(event.pos)
            return  # Consume mouse movement when menu is open

        # Borderless drag live-drag handling
        if engine._borderless_drag_active and engine._borderless_drag_window_offset is not None:
            try:
                import pygame._sdl2
                sdl_window = pygame._sdl2.Window.from_display_module()
                if sdl_window:
                    # Calculate new window position based on mouse position
                    new_x = event.pos[0] + engine._borderless_drag_window_offset[0]
                    new_y = event.pos[1] + engine._borderless_drag_window_offset[1]
                    sdl_window.position = (new_x, new_y)
            except (ImportError, AttributeError):
                # pygame._sdl2 not available: already degraded
                pass
            except Exception:
                raise

        if engine.building_menu.selected_building:
            engine.building_menu.update_preview(
                event.pos,
                engine.world,
                engine.buildings,
                (engine.camera_x, engine.camera_y),
                zoom=engine.zoom,
            )

        # Update building list panel hover state
        if engine.building_list_panel.visible:
            engine.building_list_panel.update_hover(event.pos, engine.economy, engine.buildings)

        # Update building panel hover state
        engine.building_panel.update_hover(event.pos)

        # Update build catalog panel hover state
        if engine.build_catalog_panel.visible:
            engine.build_catalog_panel.update_hover(event.pos)
