"""
Main game engine - handles the game loop, input, and coordination.
"""
import time
import os
import pygame
from config import (
    WINDOW_WIDTH, WINDOW_HEIGHT, FPS, GAME_TITLE, TILE_SIZE,
    MAP_WIDTH, MAP_HEIGHT, COLOR_BLACK, COLOR_WHITE, COLOR_RED,
    CAMERA_SPEED_PX_PER_SEC, CAMERA_EDGE_MARGIN_PX,
    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP,
    MAX_ALIVE_ENEMIES,
    LAIR_BOUNTY_COST,
    BOUNTY_REWARD_LOW,
    BOUNTY_REWARD_MED,
    BOUNTY_REWARD_HIGH,
    EARLY_PACING_NUDGE_MODE,
    DETERMINISTIC_SIM,
    SIM_TICK_HZ,
    SIM_SEED,
    DEFAULT_BORDERLESS,
)
from game.graphics.vfx import VFXSystem
from game.audio.audio_system import AudioSystem
from game.world import World, Visibility
 
from game.entities import (
    Castle, WarriorGuild, RangerGuild, RogueGuild, WizardGuild, Marketplace,
    Blacksmith, Inn, TradingPost,
    TempleAgrela, TempleDauros, TempleFervus, TempleKrypta, TempleKrolm, TempleHelia, TempleLunord,
    GnomeHovel, ElvenBungalow, DwarvenSettlement,
    Guardhouse, BallistaTower, WizardTower,
    Fairgrounds, Library, RoyalGardens,
    Palace, Hero, Goblin, TaxCollector, Peasant, Guard
)
from game.systems import CombatSystem, EconomySystem, EnemySpawner, BountySystem, LairSystem, NeutralBuildingSystem
from game.systems.buffs import BuffSystem
from game.ui import HUD, BuildingMenu, DebugPanel, BuildingPanel
from game.ui.building_list_panel import BuildingListPanel
from game.ui.pause_menu import PauseMenu
from game.ui.build_catalog_panel import BuildCatalogPanel
from game.graphics.font_cache import get_font
from game.systems import perf_stats
from game.sim.determinism import set_sim_seed
from game.sim.timebase import set_sim_now_ms

class GameEngine:
    """Main game engine class."""
    
    def __init__(self, early_nudge_mode: str | None = None):
        pygame.init()
        pygame.font.init()

        # Determinism knobs (future multiplayer enablement).
        # Seed early so world gen + initial lairs are reproducible when enabled.
        set_sim_seed(SIM_SEED)
        self._sim_now_ms = 0

        # Early pacing guardrail (ContentScenarioDirector, wk1 broad sweep):
        # Within the first few minutes, surface a clear prompt and optionally place
        # a starter bounty using existing systems. Driven by sim-time (dt), not wall-clock.
        self._early_nudge_elapsed_s = 0.0
        self._early_nudge_tip_shown = False
        self._early_nudge_starter_bounty_done = False
        self._early_nudge_mode = (early_nudge_mode or EARLY_PACING_NUDGE_MODE or "auto").strip().lower()
        
        # -----------------------------
        # Display / window mode (WK7: runtime switching)
        # -----------------------------
        # WK7: User settings model (UI-only, non-sim)
        # Initialize with default (borderless if DEFAULT_BORDERLESS, else windowed)
        initial_mode = "borderless" if DEFAULT_BORDERLESS else "windowed"
        self.display_mode = initial_mode  # "fullscreen" | "borderless" | "windowed"
        # WK7 Mid-Sprint: make windowed obviously windowed by default
        self.window_size = (1280, 720)  # Saved size for windowed mode
        # Defer display mode changes to the main loop to avoid SDL re-entrancy during event handling
        # (fixes intermittent Windows crash inside pygame.event.get after mode switches).
        self._pending_display_settings: tuple[str, tuple[int, int] | None] | None = None
        
        # Borderless drag state (WK7)
        self._borderless_drag_active = False
        self._borderless_drag_start_pos = None
        self._borderless_drag_window_offset = None

        # Camera (initialize before display settings for clamp safety)
        self.camera_x = 0
        self.camera_y = 0
        self.zoom = 1.0
        self.default_zoom = 1.0
        
        # Apply initial display settings
        self.apply_display_settings(self.display_mode, self.window_size)
        self.clock = pygame.time.Clock()
        self.running = True
        self.paused = False

        # Screenshot tooling hook: when True, skip UI layers for clean world captures.
        # (Used by tools/capture_screenshots.py scenarios; normal gameplay leaves this False.)
        self.screenshot_hide_ui = False

        # Perf overlay
        self.show_perf = True
        self._perf_last_ms = 0
        self._perf_pf_calls = 0
        self._perf_pf_failures = 0
        self._perf_pf_total_ms = 0.0
        # Cached overlay panel (avoid per-frame Surface allocations)
        self._perf_overlay_next_update_ms = 0
        self._perf_overlay_panel = None
        self._perf_overlay_dirty = True
        self._perf_snapshot = {
            "fps": 0.0,
            "heroes": 0,
            "enemies": 0,
            "peasants": 0,
            "guards": 0,
        }
        # Loop timings (diagnostic only; EMA smoothing)
        self._perf_events_ms = 0.0
        self._perf_update_ms = 0.0
        self._perf_render_ms = 0.0
        
        # Initialize game world
        self.world = World()

        # Render surfaces (avoid per-frame allocations).
        self._view_surface = None
        self._view_surface_size = (0, 0)
        self._scaled_surface = pygame.Surface((self.window_width, self.window_height))
        self._pause_overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        self._pause_overlay.fill((0, 0, 0, 128))
        
        # Game objects
        self.buildings = []
        self.heroes = []
        self.enemies = []
        self.bounties = []
        self.peasants = []
        self.guards = []
        self.peasant_spawn_timer = 0.0
        
        # Systems
        self.combat_system = CombatSystem()
        self.economy = EconomySystem()
        self.spawner = EnemySpawner(self.world)
        self.lair_system = LairSystem(self.world)
        self.neutral_building_system = NeutralBuildingSystem(self.world)
        self.buff_system = BuffSystem()
        
        # WK7-BUG-001 FIX: Audio system MUST be initialized before PauseMenu
        # (PauseMenu constructor requires audio_system parameter)
        # Audio system (WK6: non-authoritative, event-driven sound effects and ambient music).
        # Expected interface:
        # - emit_from_events(events: list[dict]) -> None
        # - set_ambient(track_name: str, volume: float) -> None
        self.audio_system = AudioSystem(enabled=True)

        # UI (must be initialized after audio_system - see WK7-BUG-001)
        self.hud = HUD(self.window_width, self.window_height)
        self.building_menu = BuildingMenu()
        self.building_list_panel = BuildingListPanel(self.window_width, self.window_height)
        self.debug_panel = DebugPanel(self.window_width, self.window_height)
        self.building_panel = BuildingPanel(self.window_width, self.window_height)
        # WK7-BUG-001: PauseMenu requires audio_system, so it must be initialized after audio_system
        self.pause_menu = PauseMenu(self.window_width, self.window_height, engine=self, audio_system=self.audio_system)
        self.build_catalog_panel = BuildCatalogPanel(self.window_width, self.window_height)
        
        # Selection
        self.selected_building = None
        
        # Bounty system
        self.bounty_system = BountySystem()
        
        # Selection
        self.selected_hero = None
        
        # AI controller (will be set from main.py)
        self.ai_controller = None

        # VFX system (lightweight particles for hits/kills).
        # Expected interface:
        # - update(dt: float) -> None
        # - render(surface: pygame.Surface, camera_offset: tuple[int,int]) -> None
        # - emit_from_events(events: list[dict]) -> None
        self.vfx_system = VFXSystem()
        
        # Tax collector (created after castle is placed)
        self.tax_collector = None
        
        # Initialize starting buildings
        self.setup_initial_state()
        
        # WK6: Start ambient loop on game start (Build A: single neutral loop)
        if self.audio_system is not None:
            self.audio_system.set_ambient("ambient_loop", volume=0.4)

    def _update_fog_of_war(self):
        """Update fog-of-war visibility around the castle and living heroes."""
        # Tunables (tile radius). Kept local to avoid cross-agent config conflicts.
        CASTLE_VISION_TILES = 10
        HERO_VISION_TILES = 7

        castle = next((b for b in self.buildings if getattr(b, "building_type", None) == "castle"), None)
        revealers = []
        hero_revealers = []  # Track which revealers are heroes (for XP tracking)
        
        if castle is not None:
            revealers.append((castle.center_x, castle.center_y, CASTLE_VISION_TILES))

        for hero in self.heroes:
            if getattr(hero, "is_alive", True):
                revealers.append((hero.x, hero.y, HERO_VISION_TILES))
                hero_revealers.append((hero, hero.x, hero.y, HERO_VISION_TILES))

        if revealers:
            # WK6: Track newly revealed tiles for XP awards
            newly_revealed = self.world.update_visibility(revealers, return_new_reveals=True)
            
            # WK6: Award XP to Rangers for newly revealed tiles
            if newly_revealed:
                for hero, hx, hy, radius in hero_revealers:
                    if hero.hero_class == "ranger":
                        # Check which newly revealed tiles are within this hero's vision radius
                        hero_grid_x, hero_grid_y = self.world.world_to_grid(hx, hy)
                        radius_sq = radius * radius
                        
                        for grid_x, grid_y in newly_revealed:
                            # Check if this tile is within hero's vision circle
                            dx = grid_x - hero_grid_x
                            dy = grid_y - hero_grid_y
                            if (dx * dx + dy * dy) <= radius_sq:
                                # First-time reveal: award XP (idempotent via set check)
                                if (grid_x, grid_y) not in hero._revealed_tiles:
                                    hero._revealed_tiles.add((grid_x, grid_y))
                                    # Award small XP (1 per tile, Agent 06 can tune)
                                    hero.xp += 1
        
    def setup_initial_state(self):
        """Set up the initial game state."""
        # Place castle in center
        center_x = MAP_WIDTH // 2 - 1
        center_y = MAP_HEIGHT // 2 - 1
        
        castle = Castle(center_x, center_y)
        # Starting castle is fully built and targetable.
        if hasattr(castle, "is_constructed"):
            castle.is_constructed = True
        if hasattr(castle, "construction_started"):
            castle.construction_started = True
        self.buildings.append(castle)
        
        # Create tax collector at castle
        self.tax_collector = TaxCollector(castle)
        
        # Clear tiles under castle for path
        for dy in range(castle.size[1]):
            for dx in range(castle.size[0]):
                self.world.set_tile(center_x + dx, center_y + dy, 2)  # PATH
        
        # Center camera on castle
        self.center_on_castle(reset_zoom=True, castle=castle)

        # Spawn initial monster lairs (hostile world-structures).
        self.lair_system.spawn_initial_lairs(self.buildings, castle)
        self.clamp_camera()

        # Initialize fog-of-war reveal around the starting castle.
        self._update_fog_of_war()
        
    def handle_events(self):
        """Process input events."""
        # WK7 display-mode crash mitigation:
        # On some Windows/SDL builds, the first event poll immediately after a set_mode() can
        # intermittently crash inside SDL_PumpEvents (no Python exception). Avoid calling
        # any event APIs for a couple frames after a mode switch.
        skip_frames = int(getattr(self, "_skip_event_processing_frames", 0) or 0)
        if skip_frames > 0:
            self._skip_event_processing_frames = skip_frames - 1
            return

        events = pygame.event.get()

        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
                
            elif event.type == pygame.KEYDOWN:
                self.handle_keydown(event)
                
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.handle_mousedown(event)
            
            elif event.type == pygame.MOUSEBUTTONUP:
                # WK7: Menu slider drag end
                if self.pause_menu.visible and event.button == 1:
                    self.pause_menu.handle_mouseup(event.pos)
                # WK7: End borderless drag
                if event.button == 1 and getattr(self, "_borderless_drag_active", False):
                    self._borderless_drag_active = False
                    self._borderless_drag_start_pos = None
                    self._borderless_drag_window_offset = None
                
            elif event.type == pygame.MOUSEMOTION:
                self.handle_mousemove(event)

            # Pygame 2 mouse wheel event
            elif hasattr(pygame, "MOUSEWHEEL") and event.type == pygame.MOUSEWHEEL:
                # event.y: +1 scroll up, -1 scroll down
                if event.y > 0:
                    self.zoom_by(ZOOM_STEP)
                elif event.y < 0:
                    self.zoom_by(1.0 / ZOOM_STEP)

    def request_display_settings(self, display_mode: str, window_size: tuple[int, int] | None = None):
        """Queue a display mode change to be applied at a safe point (between frames)."""
        self._pending_display_settings = (str(display_mode), window_size)
    
    def select_building_for_placement(self, building_type: str) -> bool:
        """
        Unified method for selecting a building for placement.
        Called by both hotkeys and panel clicks.
        Returns True if selection succeeded, False otherwise.
        """
        # Check affordability
        if not self.economy.can_afford_building(building_type):
            self.hud.add_message("Not enough gold!", (255, 100, 100))
            return False
        
        # Check prerequisites
        from config import BUILDING_PREREQUISITES
        if building_type in BUILDING_PREREQUISITES:
            required = BUILDING_PREREQUISITES[building_type]
            has_prereq = False
            for building in self.buildings:
                if building.building_type in required and getattr(building, "is_constructed", False):
                    has_prereq = True
                    break
            if not has_prereq:
                req_names = ", ".join(b.replace("_", " ").title() for b in required)
                self.hud.add_message(f"Requires: {req_names}", (255, 200, 100))
                return False
        
        # Check constraints (mutually exclusive)
        from config import BUILDING_CONSTRAINTS
        if building_type in BUILDING_CONSTRAINTS:
            excluded = BUILDING_CONSTRAINTS[building_type]
            for building in self.buildings:
                if building.building_type in excluded:
                    excl_name = building.building_type.replace("_", " ").title()
                    self.hud.add_message(f"Cannot build: {excl_name} exists", (255, 200, 100))
                    return False
        
        # All checks passed - select building
        self.building_menu.select_building(building_type)
        # Close panel if open
        if self.building_list_panel.visible:
            self.building_list_panel.close()
        return True
    
    def handle_keydown(self, event):
        """Handle keyboard input."""
        # WK7: ESC menu takes priority
        if event.key == pygame.K_ESCAPE:
            if self.pause_menu.visible:
                # Close menu (resume game)
                self.pause_menu.close()
                self.paused = False
            else:
                # Open menu (pause game)
                self.pause_menu.open()
                self.paused = True
                # Also close building panels when opening menu
                if self.building_list_panel.visible:
                    self.building_list_panel.close()
                    self.building_menu.cancel_selection()
                if self.building_menu.selected_building:
                    self.building_menu.cancel_selection()
            return  # Consume ESC when menu is involved
        
        # Block world input when menu is open
        if self.pause_menu.visible:
            return
                
        elif event.key == pygame.K_TAB:
            # WK7 mid-sprint: Toggle right-side panel
            if hasattr(self.hud, "toggle_right_panel"):
                self.hud.toggle_right_panel()
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
            self.try_hire_hero()
            
        elif event.key == pygame.K_SPACE:
            # Center view on castle and reset to starting zoom
            self.center_on_castle(reset_zoom=True)
        
        elif event.key == pygame.K_F1:
            # Toggle debug panel
            self.debug_panel.toggle()
        elif event.key == pygame.K_F2:
            # Toggle perf overlay
            self.show_perf = not self.show_perf
        elif event.key == pygame.K_F3:
            # Toggle HUD help/controls overlay
            if hasattr(self.hud, "toggle_help"):
                self.hud.toggle_help()
        
        elif event.key == pygame.K_F12:
            # Manual screenshot capture
            self.capture_screenshot()
        
        elif event.key == pygame.K_b:
            # Place a bounty at mouse position
            self.place_bounty()
            
        elif event.key == pygame.K_p:
            # Use potion for selected hero
            if self.selected_hero and self.selected_hero.is_alive:
                if self.selected_hero.use_potion():
                    self.hud.add_message(f"{self.selected_hero.name} used a potion!", (100, 255, 100))

        # Zoom controls (+/- and keypad)
        elif event.key in (pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.zoom_by(ZOOM_STEP)
        elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.zoom_by(1.0 / ZOOM_STEP)
    
    def handle_mousedown(self, event):
        """Handle mouse clicks."""
        # WK7: Menu input handling (takes priority)
        if self.pause_menu.visible:
            if event.button == 1:  # Left click
                action = self.pause_menu.handle_click(event.pos)
                if action == "resume":
                    self.pause_menu.close()
                    self.paused = False
                elif action == "quit":
                    self.running = False
                elif action and action.startswith("graphics_select_"):
                    # Graphics page selection (already handled in PauseMenu.handle_click)
                    pass
                elif action == "audio_slider_drag":
                    # Audio slider drag (already handled in PauseMenu.handle_mousemove)
                    pass
            return  # Consume all input when menu is open
        
        # Mouse wheel zoom (older pygame uses buttons 4/5)
        if event.button == 4:
            self.zoom_by(ZOOM_STEP)
            return
        if event.button == 5:
            self.zoom_by(1.0 / ZOOM_STEP)
            return

        if event.button == 1:  # Left click
            # UI clicks should consume input before world selection.
            try:
                gs = self.get_game_state()
                if hasattr(self.hud, "handle_click"):
                    action = self.hud.handle_click(event.pos, gs)
                    if action == "quit":
                        self.running = False
                        return
                    if action == "close_selection":
                        self.selected_hero = None
                        self.building_panel.deselect()
                        self.selected_building = None
                        return
            except Exception:
                pass

            # Debug panel close/consume
            try:
                if getattr(self.debug_panel, "visible", False) and hasattr(self.debug_panel, "handle_click"):
                    if self.debug_panel.handle_click(event.pos):
                        return
            except Exception:
                pass

            # Perf overlay close/consume
            try:
                if self.show_perf and hasattr(self, "_perf_close_rect") and self._perf_close_rect and self._perf_close_rect.collidepoint(event.pos):
                    self.show_perf = False
                    return
            except Exception:
                pass

            # Check if clicking on building list panel first (if visible)
            if self.building_list_panel.visible:
                result = self.building_list_panel.handle_click(event.pos, self.economy, self.buildings)
                if result:  # Building type string
                    self.select_building_for_placement(result)
                    return
                # Click outside panel - close it
                self.building_list_panel.close()
                return
            
            # Check if clicking on build catalog panel (WK7: castle-driven)
            if self.build_catalog_panel.visible:
                building_type = self.build_catalog_panel.handle_click(event.pos, self.economy, self.buildings)
                if building_type:
                    self.select_building_for_placement(building_type)
                    return
                # Click outside catalog - close it
                self.build_catalog_panel.close()
                return
            
            # Check if clicking on building panel
            if self.building_panel.visible:
                result = self.building_panel.handle_click(event.pos, self.economy, self.get_game_state())
                if isinstance(result, dict) and result.get("type") == "open_build_catalog":
                    # WK7: Open build catalog from castle
                    self.build_catalog_panel.open()
                    return
                elif isinstance(result, dict) and result.get("type") == "demolish_building":
                    # Handle player demolish action
                    building = result.get("building")
                    if building and building in self.buildings and building.building_type != "castle":
                        # Set HP to 0 to trigger cleanup
                        building.hp = 0
                        # Immediate cleanup (instant UX) - suppress auto-demolish message
                        self._cleanup_destroyed_buildings(emit_messages=False)
                        # Emit HUD message (player demolish: white)
                        building_name = building.building_type.replace("_", " ").title()
                        self.hud.add_message(f"Demolished: {building_name}", COLOR_WHITE)
                        # Deselect building (panel will close)
                        self.building_panel.deselect()
                        self.selected_building = None
                    return
                elif result:  # Other panel clicks (True)
                    return
            
            if self.building_menu.selected_building:
                # Try to place building
                pos = self.building_menu.get_placement()
                if pos:
                    self.place_building(pos[0], pos[1])
            else:
                # Try to select a hero first
                if self.try_select_hero(event.pos):
                    self.building_panel.deselect()
                    self.selected_building = None
                # Then try to select a building
                elif self.try_select_building(event.pos):
                    self.selected_hero = None
                else:
                    # Clicked on empty space
                    self.selected_hero = None
                    self.building_panel.deselect()
                    self.selected_building = None
                
        elif event.button == 3:  # Right click
            # Indirect-control game: no direct hero commands.
            pass
    
    def handle_mousemove(self, event):
        """Handle mouse movement."""
        # WK7: Menu slider dragging
        if self.pause_menu.visible:
            self.pause_menu.handle_mousemove(event.pos)
            return  # Consume mouse movement when menu is open
        
        # WK7: Borderless drag live-drag handling
        if self._borderless_drag_active and self._borderless_drag_window_offset is not None:
            try:
                import pygame._sdl2
                sdl_window = pygame._sdl2.Window.from_display_module()
                if sdl_window:
                    # Calculate new window position based on mouse position
                    new_x = event.pos[0] + self._borderless_drag_window_offset[0]
                    new_y = event.pos[1] + self._borderless_drag_window_offset[1]
                    sdl_window.position = (new_x, new_y)
            except (ImportError, AttributeError) as e:
                # pygame._sdl2 not available: already degraded
                pass
            except Exception as e:
                raise
        
        if self.building_menu.selected_building:
            self.building_menu.update_preview(
                event.pos, 
                self.world, 
                self.buildings,
                (self.camera_x, self.camera_y),
                zoom=self.zoom
            )
        
        # Update building list panel hover state
        if self.building_list_panel.visible:
            self.building_list_panel.update_hover(event.pos, self.economy, self.buildings)
        
        # Update building panel hover state
        self.building_panel.update_hover(event.pos)
        
        # WK7: Update build catalog panel hover state
        if self.build_catalog_panel.visible:
            self.build_catalog_panel.update_hover(event.pos)
    
    def try_select_hero(self, screen_pos: tuple) -> bool:
        """Try to select a hero at the given screen position. Returns True if selected."""
        world_x, world_y = self.screen_to_world(screen_pos[0], screen_pos[1])
        
        for hero in self.heroes:
            if hero.is_alive and hero.distance_to(world_x, world_y) < hero.size:
                self.selected_hero = hero
                # Ensure the right panel becomes visible on selection (Tab panel UX).
                if hasattr(self, "hud"):
                    try:
                        self.hud.right_panel_visible = True
                    except Exception:
                        pass
                return True
        
        return False
    
    def try_select_building(self, screen_pos: tuple) -> bool:
        """Try to select a building at the given screen position. Returns True if selected."""
        world_x, world_y = self.screen_to_world(screen_pos[0], screen_pos[1])
        
        for building in self.buildings:
            rect = building.get_rect()
            if rect.collidepoint(world_x, world_y):
                self.selected_building = building
                self.building_panel.select_building(building, self.heroes)
                return True
        
        return False
    
    def try_hire_hero(self):
        """Try to hire a hero from the selected guild building."""
        guild = self.selected_building

        allowed = ["warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild"]
        if not guild or not hasattr(guild, "building_type") or guild.building_type not in allowed:
            self.hud.add_message("Select a constructed guild (Warrior/Ranger/Rogue/Wizard) to hire from!", (255, 100, 100))
            return

        # Guild must be constructed before it can be used.
        if hasattr(guild, "is_constructed") and not guild.is_constructed:
            self.hud.add_message("Guild is under construction!", (255, 100, 100))
            return
        
        if not self.economy.can_afford_hero():
            self.hud.add_message("Not enough gold to hire!", (255, 100, 100))
            return
        
        # Hire the hero
        self.economy.hire_hero()
        guild.hire_hero()
        
        # Spawn hero near guild
        class_by_guild = {
            "warrior_guild": "warrior",
            "ranger_guild": "ranger",
            "rogue_guild": "rogue",
            "wizard_guild": "wizard",
        }
        hero_class = class_by_guild.get(guild.building_type, "warrior")
        hero = Hero(
            guild.center_x + TILE_SIZE,
            guild.center_y,
            hero_class=hero_class
        )
        # Set the hero's home building to this guild
        hero.home_building = guild
        
        self.heroes.append(hero)
        self.hud.add_message(f"{hero.name} the {hero_class.title()} joins your kingdom!", (100, 255, 100))
    
    def place_building(self, grid_x: int, grid_y: int):
        """Place the selected building."""
        building_type = self.building_menu.selected_building
        
        if not self.economy.buy_building(building_type):
            self.hud.add_message("Not enough gold!", (255, 100, 100))
            return
        
        # Create the building
        building = None
        if building_type == "warrior_guild":
            building = WarriorGuild(grid_x, grid_y)
        elif building_type == "ranger_guild":
            building = RangerGuild(grid_x, grid_y)
        elif building_type == "rogue_guild":
            building = RogueGuild(grid_x, grid_y)
        elif building_type == "wizard_guild":
            building = WizardGuild(grid_x, grid_y)
        elif building_type == "marketplace":
            building = Marketplace(grid_x, grid_y)
        # Phase 1: Economic Buildings
        elif building_type == "blacksmith":
            building = Blacksmith(grid_x, grid_y)
        elif building_type == "inn":
            building = Inn(grid_x, grid_y)
        elif building_type == "trading_post":
            building = TradingPost(grid_x, grid_y)
        # Phase 2: Temples
        elif building_type == "temple_agrela":
            building = TempleAgrela(grid_x, grid_y)
        elif building_type == "temple_dauros":
            building = TempleDauros(grid_x, grid_y)
        elif building_type == "temple_fervus":
            building = TempleFervus(grid_x, grid_y)
        elif building_type == "temple_krypta":
            building = TempleKrypta(grid_x, grid_y)
        elif building_type == "temple_krolm":
            building = TempleKrolm(grid_x, grid_y)
        elif building_type == "temple_helia":
            building = TempleHelia(grid_x, grid_y)
        elif building_type == "temple_lunord":
            building = TempleLunord(grid_x, grid_y)
        # Phase 3: Non-Human Dwellings
        elif building_type == "gnome_hovel":
            building = GnomeHovel(grid_x, grid_y)
        elif building_type == "elven_bungalow":
            building = ElvenBungalow(grid_x, grid_y)
        elif building_type == "dwarven_settlement":
            building = DwarvenSettlement(grid_x, grid_y)
        # Phase 4: Defensive Structures
        elif building_type == "guardhouse":
            building = Guardhouse(grid_x, grid_y)
        elif building_type == "ballista_tower":
            building = BallistaTower(grid_x, grid_y)
        elif building_type == "wizard_tower":
            building = WizardTower(grid_x, grid_y)
        # Phase 5: Special Buildings
        elif building_type == "fairgrounds":
            building = Fairgrounds(grid_x, grid_y)
        elif building_type == "library":
            building = Library(grid_x, grid_y)
        elif building_type == "royal_gardens":
            building = RoyalGardens(grid_x, grid_y)
        # Phase 6: Palace
        elif building_type == "palace":
            building = Palace(grid_x, grid_y)
        
        if building is None:
            return

        # Newly placed buildings start unconstructed (1 HP, non-targetable) until a peasant begins building.
        if hasattr(building, "mark_unconstructed"):
            building.mark_unconstructed()
        
        self.buildings.append(building)
        self.building_menu.cancel_selection()
        self.hud.add_message(f"Placed: {building_type.replace('_', ' ').title()} (awaiting construction)", (100, 255, 100))
        
        # WK6 Mid-Sprint: Emit building_placed event for audio (with position for visibility gating)
        if self.audio_system is not None:
            try:
                # Calculate world position from grid
                world_x = float(grid_x * TILE_SIZE)
                world_y = float(grid_y * TILE_SIZE)
                # Update viewport context
                win_w = int(getattr(self, "window_width", self.screen.get_width()))
                win_h = int(getattr(self, "window_height", self.screen.get_height()))
                self.audio_system.set_listener_view(
                    self.camera_x, self.camera_y, self.zoom,
                    win_w, win_h, self.world
                )
                self.audio_system.emit_from_events([{
                    "type": "building_placed",
                    "x": world_x,
                    "y": world_y,
                }])
            except Exception:
                pass  # Audio should never crash simulation
    
    def place_bounty(self):
        """Place a bounty at the current mouse position."""
        mouse_pos = pygame.mouse.get_pos()
        world_x, world_y = self.screen_to_world(mouse_pos[0], mouse_pos[1])
        
        # Bounty reward tiers (player-paid; cost == reward).
        mods = pygame.key.get_mods()
        if mods & pygame.KMOD_CTRL:
            reward = int(BOUNTY_REWARD_HIGH)
        elif mods & pygame.KMOD_SHIFT:
            reward = int(BOUNTY_REWARD_MED)
        else:
            reward = int(BOUNTY_REWARD_LOW)
        
        if not self.economy.add_bounty(reward):
            self.hud.add_message("Not enough gold for bounty!", (255, 100, 100))
            return
        
        self.bounty_system.place_bounty(world_x, world_y, reward, "explore")
        self.hud.add_message(f"Bounty placed (${reward}). Heroes will respond.", (255, 215, 0))
        
        # WK6 Mid-Sprint: Emit bounty_placed event for audio (with position for visibility gating)
        if self.audio_system is not None:
            try:
                # Update viewport context
                win_w = int(getattr(self, "window_width", self.screen.get_width()))
                win_h = int(getattr(self, "window_height", self.screen.get_height()))
                self.audio_system.set_listener_view(
                    self.camera_x, self.camera_y, self.zoom,
                    win_w, win_h, self.world
                )
                self.audio_system.emit_from_events([{
                    "type": "bounty_placed",
                    "x": world_x,
                    "y": world_y,
                }])
            except Exception:
                pass  # Audio should never crash simulation

    def _nearest_lair_to(self, x: float, y: float):
        """Return nearest living lair to (x,y) or None."""
        lairs = getattr(self.lair_system, "lairs", []) or []
        best = None
        best_d2 = None
        for lair in lairs:
            if getattr(lair, "hp", 1) <= 0:
                continue
            lx = float(getattr(lair, "center_x", getattr(lair, "x", 0.0)))
            ly = float(getattr(lair, "center_y", getattr(lair, "y", 0.0)))
            dx = lx - float(x)
            dy = ly - float(y)
            d2 = dx * dx + dy * dy
            if best is None or (best_d2 is not None and d2 < best_d2):
                best = lair
                best_d2 = d2
        return best

    def _maybe_apply_early_pacing_nudge(self, dt: float, castle):
        """
        Deterministic-ish early-session pacing hook:
        - show a short HUD prompt early if the player hasn't placed a bounty
        - later, optionally place a starter 'attack_lair' bounty on the nearest lair
          (only if the player can afford it and hasn't placed any bounties yet)
        """
        if not castle:
            return

        mode = getattr(self, "_early_nudge_mode", "auto")
        if mode == "off":
            return
        if mode not in ("auto", "force"):
            mode = "auto"

        # Only relevant in the early game window.
        self._early_nudge_elapsed_s += float(dt)
        if self._early_nudge_elapsed_s > 180.0:
            return

        unclaimed = self.bounty_system.get_unclaimed_bounties()
        has_any_bounty = bool(unclaimed)

        tip_time_s = 0.0 if mode == "force" else 35.0
        starter_time_s = 0.0 if mode == "force" else 90.0

        # 1) Tip prompt: show once.
        if (not self._early_nudge_tip_shown) and (self._early_nudge_elapsed_s >= tip_time_s) and (not has_any_bounty):
            self._early_nudge_tip_shown = True
            self.hud.add_message("Tip: Press B to place a bounty and guide heroes.", (220, 220, 255))
            self.hud.add_message("Try targeting a lair for big stash payouts.", (220, 220, 255))

        # 2) Optional starter bounty: show player a clear lever if they haven't engaged.
        if self._early_nudge_starter_bounty_done:
            return
        if self._early_nudge_elapsed_s < starter_time_s:
            return
        if has_any_bounty:
            # Player already engaged with the bounty system; don't interfere.
            self._early_nudge_starter_bounty_done = True
            return

        lair = self._nearest_lair_to(float(castle.center_x), float(castle.center_y))
        if lair is None:
            self._early_nudge_starter_bounty_done = True
            return

        reward = int(LAIR_BOUNTY_COST) if LAIR_BOUNTY_COST else 75
        if not self.economy.add_bounty(reward):
            # Can't afford; keep it non-spammy and don't keep retrying.
            self._early_nudge_starter_bounty_done = True
            self.hud.add_message("Tip: Earn more gold to place bounties that guide heroes.", (220, 220, 255))
            return

        bx = float(getattr(lair, "center_x", getattr(lair, "x", 0.0)))
        by = float(getattr(lair, "center_y", getattr(lair, "y", 0.0)))
        self.bounty_system.place_bounty(bx, by, reward, "attack_lair", target=lair)
        self._early_nudge_starter_bounty_done = True
        self.hud.add_message(f"Starter bounty placed: Clear the lair (+${reward})", (255, 215, 0))
    
    def update(self, dt: float):
        """Update game state."""
        if DETERMINISTIC_SIM:
            # Drive gameplay timing off simulation time (not wall-clock).
            self._sim_now_ms += int(round(float(dt) * 1000.0))
            set_sim_now_ms(self._sim_now_ms)
        else:
            set_sim_now_ms(None)

        # Allow camera movement even while paused.
        self.update_camera(dt)
        if self.paused:
            return
        
        # Build game state for AI
        game_state = self.get_game_state()
        
        # Update AI for heroes
        if self.ai_controller:
            self.ai_controller.update(dt, self.heroes, game_state)
        
        # Update heroes
        for hero in self.heroes:
            hero.update(dt, game_state)

        # Fog-of-war reveal (castle + heroes).
        self._update_fog_of_war()

        # Apply/refresh buffs (auras) once per tick so ATK/DEF stays dynamic and stable.
        self.buff_system.update(self.heroes, self.buildings)

        # Spawn peasants from the castle (1 every 5s) until there are 2 alive.
        castle = game_state.get("castle")

        # Content pacing guardrail: nudge player toward a clear early decision.
        self._maybe_apply_early_pacing_nudge(dt, castle)

        self.peasant_spawn_timer += dt
        alive_peasants = [p for p in self.peasants if p.is_alive]
        if castle and len(alive_peasants) < 2 and self.peasant_spawn_timer >= 5.0:
            self.peasant_spawn_timer = 0.0
            self.peasants.append(Peasant(castle.center_x, castle.center_y))

        # Update peasants
        for peasant in self.peasants:
            peasant.update(dt, game_state)
        
        # Update enemies and collect ranged projectile events
        enemy_ranged_events = []
        for enemy in self.enemies:
            enemy.update(dt, self.heroes, self.peasants, self.buildings, guards=self.guards, world=self.world)
        
        # WK5: Collect ranged projectile events from enemies that just attacked
        # (do_attack() stores event in _last_ranged_event during update())
        for enemy in self.enemies:
            if hasattr(enemy, "_last_ranged_event") and enemy._last_ranged_event is not None:
                enemy_ranged_events.append(enemy._last_ranged_event)
                enemy._last_ranged_event = None  # Clear after collection

        # Update guards
        for guard in self.guards:
            guard.update(dt, self.enemies, world=self.world, buildings=self.buildings)
        
        # Spawn new enemies (with a safety cap to prevent runaway slowdown if enemies accumulate)
        alive_enemy_count = len([e for e in self.enemies if getattr(e, "is_alive", False)])
        remaining_slots = max(0, int(MAX_ALIVE_ENEMIES) - alive_enemy_count)
        if remaining_slots > 0:
            new_enemies = self.spawner.update(dt)
            if new_enemies:
                self.enemies.extend(new_enemies[:remaining_slots])

            # Spawn enemies from lairs (in addition to wave spawns)
            alive_enemy_count = len([e for e in self.enemies if getattr(e, "is_alive", False)])
            remaining_slots = max(0, int(MAX_ALIVE_ENEMIES) - alive_enemy_count)
            if remaining_slots > 0:
                lair_enemies = self.lair_system.update(dt, self.buildings)
                if lair_enemies:
                    self.enemies.extend(lair_enemies[:remaining_slots])
        
        # Process combat
        events = self.combat_system.process_combat(
            self.heroes, self.enemies, self.buildings
        )
        
        # WK5: Merge enemy ranged projectile events with combat events.
        # Building projectile events are collected later in the tick (after building updates)
        # and emitted to VFX separately to avoid ordering hazards.
        events.extend(enemy_ranged_events)

        # Feed combat/enemy events into optional VFX system (non-blocking, best-effort).
        if self.vfx_system is not None and hasattr(self.vfx_system, "emit_from_events"):
            try:
                self.vfx_system.emit_from_events(events)
            except Exception:
                # VFX should never crash the simulation.
                pass
        
        # WK6 Mid-Sprint: Feed combat/enemy events into AudioSystem (visibility-gated).
        if self.audio_system is not None:
            try:
                # Update viewport context for visibility gating
                win_w = int(getattr(self, "window_width", self.screen.get_width()))
                win_h = int(getattr(self, "window_height", self.screen.get_height()))
                self.audio_system.set_listener_view(
                    self.camera_x, self.camera_y, self.zoom,
                    win_w, win_h, self.world
                )
                self.audio_system.emit_from_events(events)
            except Exception:
                # Audio should never crash the simulation.
                pass
        
        # Handle combat events
        for event in events:
            if event["type"] == "enemy_killed":
                self.hud.add_message(
                    f"{event['hero']} slew a {event['enemy']}! (+{event['gold']}g, +{event['xp']}xp)",
                    (255, 215, 0)
                )
            elif event["type"] == "castle_destroyed":
                self.hud.add_message("GAME OVER - Castle Destroyed!", (255, 0, 0))
                self.paused = True
            elif event["type"] == "lair_cleared":
                lair_name = event.get("lair_type", "lair").replace("_", " ").title()
                gold = event.get("gold", 0)
                hero_name = event.get("hero", "A hero")
                self.hud.add_message(
                    f"{hero_name} cleared {lair_name}! (+{gold}g)",
                    (255, 215, 0),
                )
                lair_obj = event.get("lair_obj")

                # Completion-based lair bounty payout (do NOT allow proximity-claim).
                # If there is an active attack_lair bounty targeting this lair, pay it to the clearing hero now.
                bounty_claimed_events = []
                try:
                    hero_obj = next((h for h in self.heroes if getattr(h, "name", None) == hero_name), None)
                    if hero_obj is not None and lair_obj is not None:
                        for b in list(getattr(self.bounty_system, "bounties", []) or []):
                            if getattr(b, "claimed", False):
                                continue
                            if getattr(b, "bounty_type", None) != "attack_lair":
                                continue
                            if getattr(b, "target", None) is lair_obj:
                                if b.claim(hero_obj):
                                    # WK6 Mid-Sprint: Emit bounty_claimed event with position for visibility-gated audio
                                    bounty_claimed_events.append({
                                        "type": "bounty_claimed",
                                        "x": float(b.x),
                                        "y": float(b.y),
                                        "reward": b.reward,
                                        "hero": hero_name,
                                    })
                except Exception:
                    # Bounty payout should never crash the sim.
                    pass
                
                # WK6 Mid-Sprint: Route bounty_claimed events to AudioSystem (visibility-gated)
                if bounty_claimed_events and self.audio_system is not None:
                    try:
                        win_w = int(getattr(self, "window_width", self.screen.get_width()))
                        win_h = int(getattr(self, "window_height", self.screen.get_height()))
                        self.audio_system.set_listener_view(
                            self.camera_x, self.camera_y, self.zoom,
                            win_w, win_h, self.world
                        )
                        self.audio_system.emit_from_events(bounty_claimed_events)
                    except Exception:
                        # Audio should never crash the simulation
                        pass

                if lair_obj in self.buildings:
                    self.buildings.remove(lair_obj)
                if lair_obj in getattr(self.lair_system, "lairs", []):
                    self.lair_system.lairs.remove(lair_obj)
        
        # Clean up dead enemies
        self.enemies = [e for e in self.enemies if e.is_alive]

        # Clean up dead guards
        self.guards = [g for g in self.guards if getattr(g, "is_alive", False)]
        
        # Clean up destroyed buildings (WK5: auto-demolish at 0 HP + reference cleanup)
        self._cleanup_destroyed_buildings()
        
        # Process bounties
        claimed = self.bounty_system.check_claims(self.heroes)
        bounty_claimed_events = []
        for bounty, hero in claimed:
            self.hud.add_message(
                f"{hero.name} claimed bounty: +${bounty.reward}!",
                (255, 215, 0)
            )
            # WK6 Mid-Sprint: Emit bounty_claimed event with position for visibility-gated audio
            bounty_claimed_events.append({
                "type": "bounty_claimed",
                "x": float(bounty.x),
                "y": float(bounty.y),
                "reward": bounty.reward,
                "hero": hero.name,
            })
        
        # WK6 Mid-Sprint: Route bounty_claimed events to AudioSystem (visibility-gated)
        if bounty_claimed_events and self.audio_system is not None:
            try:
                win_w = int(getattr(self, "window_width", self.screen.get_width()))
                win_h = int(getattr(self, "window_height", self.screen.get_height()))
                self.audio_system.set_listener_view(
                    self.camera_x, self.camera_y, self.zoom,
                    win_w, win_h, self.world
                )
                self.audio_system.emit_from_events(bounty_claimed_events)
            except Exception:
                # Audio should never crash the simulation
                pass
        
        self.bounty_system.cleanup()

        # Neutral buildings: auto-spawn + passive tax
        self.neutral_building_system.update(dt, self.buildings, self.heroes, castle)
        
        # Update tax collector
        if self.tax_collector:
            self.tax_collector.update(dt, self.buildings, self.economy, world=self.world)
        
        # Update buildings that need periodic updates and collect ranged projectile events
        building_ranged_events = []
        for building in self.buildings:
            if building.building_type == "trading_post" and hasattr(building, "update"):
                building.update(dt, self.economy)
            elif building.building_type == "ballista_tower" and hasattr(building, "update"):
                building.update(dt, self.enemies)
            elif building.building_type == "wizard_tower" and hasattr(building, "update"):
                building.update(dt, self.enemies)
            elif building.building_type == "fairgrounds" and hasattr(building, "update"):
                building.update(dt, self.economy, self.heroes)
            elif building.building_type == "guardhouse" and hasattr(building, "update"):
                # Guard spawning handled here so guards become real entities.
                should_spawn = building.update(dt, [g for g in self.guards if g.home_building == building])
                if should_spawn:
                    # Spawn a guard near the guardhouse.
                    g = Guard(building.center_x + TILE_SIZE, building.center_y, home_building=building)
                    self.guards.append(g)
                    if hasattr(building, "guards_spawned"):
                        building.guards_spawned += 1

            # Palace guards (if palace building exists)
            elif building.building_type == "palace":
                max_guards = getattr(building, "max_palace_guards", 0)
                if max_guards > 0 and getattr(building, "is_constructed", True):
                    current = len([g for g in self.guards if g.home_building == building])
                    if current < max_guards:
                        g = Guard(building.center_x + TILE_SIZE, building.center_y, home_building=building)
                        self.guards.append(g)
        
        # WK5: Collect ranged projectile events from buildings that just attacked
        # (update() stores event in _last_ranged_event during building updates)
        for building in self.buildings:
            if hasattr(building, "_last_ranged_event") and building._last_ranged_event is not None:
                building_ranged_events.append(building._last_ranged_event)
                building._last_ranged_event = None  # Clear after collection

        # WK5: Feed building projectile events into VFX after building updates.
        if building_ranged_events and self.vfx_system is not None and hasattr(self.vfx_system, "emit_from_events"):
            try:
                self.vfx_system.emit_from_events(building_ranged_events)
            except Exception:
                pass
        
        # WK6 Mid-Sprint: Feed building projectile events into AudioSystem (visibility-gated).
        if building_ranged_events and self.audio_system is not None:
            try:
                # Update viewport context for visibility gating
                win_w = int(getattr(self, "window_width", self.screen.get_width()))
                win_h = int(getattr(self, "window_height", self.screen.get_height()))
                self.audio_system.set_listener_view(
                    self.camera_x, self.camera_y, self.zoom,
                    win_w, win_h, self.world
                )
                self.audio_system.emit_from_events(building_ranged_events)
            except Exception:
                pass
        
        # Update HUD
        self.hud.update()

        # Update VFX (after simulation state is updated).
        if self.vfx_system is not None and hasattr(self.vfx_system, "update"):
            try:
                self.vfx_system.update(dt)
            except Exception:
                pass
        
        # Camera already updated at top of update()
    
    def _cleanup_destroyed_buildings(self, emit_messages: bool = True):
        """
        WK5: Remove buildings at hp <= 0 (except castle) and clear all references.
        
        WK5 Build B: Also emits building_destroyed events for debris spawning.
        
        This method is idempotent (safe to call multiple times per tick).
        Called in update loop after combat/event handling, before building updates.
        Also called immediately for player demolish (instant UX).
        
        Args:
            emit_messages: If True, emit auto-demolish HUD messages. Set to False if caller
                          handles messages (e.g., player demolish).
        """
        # Collect destroyed buildings first (avoid modifying list during iteration)
        destroyed = [b for b in self.buildings if b.hp <= 0 and getattr(b, "building_type", None) != "castle"]
        
        if not destroyed:
            return
        
        # WK5 Build B: Collect building destruction events for debris spawning
        destruction_events = []
        
        for building in destroyed:
            # WK5 Build B: Capture building position/type for debris before removal
            building_x = getattr(building, "center_x", getattr(building, "x", 0.0))
            building_y = getattr(building, "center_y", getattr(building, "y", 0.0))
            building_type = getattr(building, "building_type", "unknown")
            
            # Emit auto-demolish message (red, warning) unless suppressed
            if emit_messages:
                building_name = building_type.replace("_", " ").title()
                self.hud.add_message(f"{building_name} destroyed", COLOR_RED)
            
            # 1. Remove from primary lists
            if building in self.buildings:
                self.buildings.remove(building)
            if getattr(building, "is_lair", False) and building in getattr(self.lair_system, "lairs", []):
                self.lair_system.lairs.remove(building)
            
            # 2. Clear selection
            if self.selected_building is building:
                self.selected_building = None
                self.building_panel.deselect()
            
            # 3. Clear entity target references
            for hero in self.heroes:
                if getattr(hero, "target", None) is building:
                    hero.target = None
                # Hero target dict with bounty_ref
                target = getattr(hero, "target", None)
                if isinstance(target, dict) and target.get("type") == "bounty":
                    bounty_ref = target.get("bounty_ref")
                    if bounty_ref and getattr(bounty_ref, "target", None) is building:
                        hero.target = None
            
            for enemy in self.enemies:
                if getattr(enemy, "target", None) is building:
                    enemy.target = None
            
            for peasant in self.peasants:
                if getattr(peasant, "target_building", None) is building:
                    peasant.target_building = None
            
            if self.tax_collector:
                if getattr(self.tax_collector, "target_guild", None) is building:
                    self.tax_collector.target_guild = None
            
            for guard in self.guards:
                if getattr(guard, "target", None) is building:
                    guard.target = None
            
            # 4. Clear home_building references
            for hero in self.heroes:
                if getattr(hero, "home_building", None) is building:
                    hero.home_building = None
            
            for guard in self.guards:
                if getattr(guard, "home_building", None) is building:
                    guard.home_building = None
            
            # 5. Clear bounty target references
            for bounty in getattr(self.bounty_system, "bounties", []):
                if getattr(bounty, "target", None) is building:
                    bounty.target = None
            
            # WK5 Build B: Emit building destruction event for debris spawning
            # WK5 Hotfix: Include footprint size for better debris visibility
            # (after all cleanup to avoid stale references)
            building_w = getattr(building, "width", 0) or (getattr(building, "size", (1, 1))[0] * TILE_SIZE)
            building_h = getattr(building, "height", 0) or (getattr(building, "size", (1, 1))[1] * TILE_SIZE)
            destruction_events.append({
                "type": "building_destroyed",
                "x": float(building_x),
                "y": float(building_y),
                "building_type": building_type,
                "w": int(building_w),  # Footprint width in pixels
                "h": int(building_h),  # Footprint height in pixels
            })
        
        # WK5 Build B: Feed building destruction events to VFX system for debris
        if destruction_events and self.vfx_system is not None and hasattr(self.vfx_system, "emit_from_events"):
            try:
                self.vfx_system.emit_from_events(destruction_events)
            except Exception:
                # VFX should never crash the simulation
                pass
        
        # WK6 Mid-Sprint: Feed building destruction events to AudioSystem (visibility-gated)
        if destruction_events and self.audio_system is not None:
            try:
                # Update viewport context for visibility gating
                win_w = int(getattr(self, "window_width", self.screen.get_width()))
                win_h = int(getattr(self, "window_height", self.screen.get_height()))
                self.audio_system.set_listener_view(
                    self.camera_x, self.camera_y, self.zoom,
                    win_w, win_h, self.world
                )
                self.audio_system.emit_from_events(destruction_events)
            except Exception:
                # Audio should never crash the simulation
                pass
    
    def apply_display_settings(self, display_mode: str, window_size: tuple[int, int] | None = None):
        """
        WK7: Apply display mode settings (fullscreen/borderless/windowed).
        
        Args:
            display_mode: "fullscreen" | "borderless" | "windowed"
            window_size: (width, height) tuple for windowed mode. If None, uses current window_size.
        
        This is UI-only and does not affect simulation determinism.
        """
        # Update state
        self.display_mode = str(display_mode)
        if window_size is not None:
            self.window_size = (int(window_size[0]), int(window_size[1]))

        # Skip event processing for a few frames after mode switches to avoid
        # rare SDL crash inside pygame.event.get() on Windows.
        try:
            self._skip_event_processing_frames = 10
        except Exception:
            pass
        
        # Check for headless/dummy driver (safe fallback)
        # NOTE: Even with SDL_VIDEODRIVER=dummy, pygame.display.set_mode can return a Surface.
        # We must still set window_width/window_height (and preferably screen) so the engine can boot.
        driver = str(os.environ.get("SDL_VIDEODRIVER", "")).lower()

        # Get display info (dummy driver may report 0; fall back to configured defaults)
        info = pygame.display.Info()
        disp_w = int(getattr(info, "current_w", WINDOW_WIDTH) or WINDOW_WIDTH)
        disp_h = int(getattr(info, "current_h", WINDOW_HEIGHT) or WINDOW_HEIGHT)
        # Use desktop sizes when possible (avoids fullscreen staying at old window size)
        try:
            desktop_sizes = pygame.display.get_desktop_sizes()
            if desktop_sizes:
                disp_w, disp_h = int(desktop_sizes[0][0]), int(desktop_sizes[0][1])
        except Exception:
            pass
        
        # Clear forced window position when leaving borderless
        if display_mode != "borderless":
            os.environ.pop("SDL_VIDEO_WINDOW_POS", None)
            os.environ.pop("SDL_VIDEO_CENTERED", None)

        # Determine size and flags based on mode
        flags = 0
        desired_w = self.window_size[0]
        desired_h = self.window_size[1]
        
        if driver == "dummy":
            # Headless mode: keep it simple and deterministic-safe.
            # We still create a display surface so downstream code can query sizes.
            flags = 0
            display_mode = "windowed"

        if display_mode == "fullscreen":
            flags |= pygame.FULLSCREEN
            desired_w = disp_w
            desired_h = disp_h
        elif display_mode == "borderless":
            flags |= pygame.NOFRAME
            # Borderless uses desktop resolution
            desired_w = disp_w
            desired_h = disp_h
            # Center on larger displays; pin to origin when matching display resolution
            if desired_w == disp_w and desired_h == disp_h:
                os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "0,0")
            else:
                os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
        elif display_mode == "windowed":
            flags |= pygame.RESIZABLE
            # Use saved window_size
            desired_w = max(1, min(desired_w, disp_w))
            desired_h = max(1, min(desired_h, disp_h))
            # Center once to avoid pinned top-left on mode switch
            os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
        else:
            # Unknown mode: default to windowed
            flags |= pygame.RESIZABLE
        

        # Apply display mode
        self.window_width = int(desired_w)
        self.window_height = int(desired_h)
        self.screen = pygame.display.set_mode((self.window_width, self.window_height), flags)
        # Ensure dimensions reflect the actual mode applied by SDL
        self.window_width = int(self.screen.get_width())
        self.window_height = int(self.screen.get_height())
        pygame.display.set_caption(GAME_TITLE)
        # WK7-CRASH-DEBUG: SDL2 window centering disabled to isolate crash cause.
        # The SDL_VIDEO_CENTERED env var (set above) should handle centering instead.
        # if display_mode == "windowed":
        #     try:
        #         from pygame import _sdl2 as sdl2
        #         sdl_window = sdl2.Window.from_display_module()
        #         if sdl_window:
        #             center_x = max(0, int((disp_w - self.window_width) // 2))
        #             center_y = max(0, int((disp_h - self.window_height) // 2))
        #             sdl_window.position = (center_x, center_y)
        #     except Exception:
        #         pass
        
        # Recreate cached surfaces sized to window
        self._scaled_surface = pygame.Surface((self.window_width, self.window_height))
        self._pause_overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        self._pause_overlay.fill((0, 0, 0, 128))
        # Reset view surface so it gets resized on demand
        self._view_surface = None
        self._view_surface_size = (0, 0)
        
        # Update HUD size
        if hasattr(self, "hud"):
            self.hud.screen_width = self.window_width
            self.hud.screen_height = self.window_height
            if hasattr(self.hud, "on_resize"):
                try:
                    self.hud.on_resize(self.window_width, self.window_height)
                except Exception:
                    pass
        # Resize modal panels if they expose on_resize (WK7 mid-sprint hitbox fix)
        if hasattr(self, "pause_menu") and hasattr(self.pause_menu, "on_resize"):
            try:
                self.pause_menu.on_resize(self.window_width, self.window_height)
            except Exception:
                pass
        if hasattr(self, "build_catalog_panel") and hasattr(self.build_catalog_panel, "on_resize"):
            try:
                self.build_catalog_panel.on_resize(self.window_width, self.window_height)
            except Exception:
                pass
        if hasattr(self, "building_list_panel") and hasattr(self.building_list_panel, "on_resize"):
            try:
                self.building_list_panel.on_resize(self.window_width, self.window_height)
            except Exception:
                pass
        # Clamp camera to new view bounds after mode change
        if hasattr(self, "clamp_camera"):
            try:
                self.clamp_camera()
            except Exception:
                pass

        # After a mode switch on some Windows/SDL builds, the *first* event poll can crash in SDL.
        # Best-effort mitigation: pump once + clear the queue now (outside the main event loop).
        # If this itself crashes, the last marker will be pre_event_pump, which is actionable.
        try:
            pygame.event.pump()
            pygame.event.clear()
        except Exception as e:
            pass
    
    def screen_to_world(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        """Convert screen-space pixels to world-space pixels, accounting for zoom."""
        z = self.zoom if self.zoom else 1.0
        return self.camera_x + (screen_x / z), self.camera_y + (screen_y / z)

    def clamp_camera(self):
        """Clamp camera to world bounds given current zoom."""
        win_w = int(getattr(self, "window_width", self.screen.get_width()))
        win_h = int(getattr(self, "window_height", self.screen.get_height()))
        view_w = max(1, int(win_w / (self.zoom if self.zoom else 1.0)))
        view_h = max(1, int(win_h / (self.zoom if self.zoom else 1.0)))
        world_w = MAP_WIDTH * TILE_SIZE
        world_h = MAP_HEIGHT * TILE_SIZE

        max_x = max(0, world_w - view_w)
        max_y = max(0, world_h - view_h)

        self.camera_x = max(0, min(max_x, self.camera_x))
        self.camera_y = max(0, min(max_y, self.camera_y))

    def center_on_castle(self, reset_zoom: bool = True, castle=None):
        """Center camera on the castle; optionally reset zoom to the starting zoom."""
        if reset_zoom:
            self.zoom = float(getattr(self, "default_zoom", 1.0))

        if castle is None:
            castle = next(
                (b for b in self.buildings if getattr(b, "building_type", None) == "castle" and getattr(b, "hp", 0) > 0),
                None,
            )
        if not castle:
            return

        win_w = int(getattr(self, "window_width", self.screen.get_width()))
        win_h = int(getattr(self, "window_height", self.screen.get_height()))
        self.camera_x = castle.center_x - win_w // 2
        self.camera_y = castle.center_y - win_h // 2
        self.clamp_camera()

    def capture_screenshot(self):
        """Capture a screenshot to docs/screenshots/manual/ with timestamp filename."""
        from datetime import datetime
        
        # Ensure the manual screenshots folder exists
        screenshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "screenshots", "manual")
        os.makedirs(screenshot_dir, exist_ok=True)
        
        # Generate timestamp-based filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Trim to milliseconds
        filename = f"screenshot_{timestamp}.png"
        filepath = os.path.join(screenshot_dir, filename)
        
        # Save the current screen
        try:
            pygame.image.save(self.screen, filepath)
            self.hud.add_message(f"Screenshot saved: {filename}", (100, 200, 255))
            print(f"[screenshot] Saved: {filepath}")
        except Exception as e:
            self.hud.add_message(f"Screenshot failed: {e}", (255, 100, 100))
            print(f"[screenshot] Failed: {e}")

    def set_zoom(self, new_zoom: float):
        """Set zoom with clamping."""
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, float(new_zoom)))
        self.clamp_camera()

    def zoom_by(self, factor: float):
        """Zoom in/out around the mouse cursor."""
        if factor is None:
            return
        factor = float(factor)
        if factor <= 0:
            return

        mouse_x, mouse_y = pygame.mouse.get_pos()
        before_x, before_y = self.screen_to_world(mouse_x, mouse_y)

        self.set_zoom(self.zoom * factor)

        # Keep the same world point under the cursor after zooming.
        after_zoom = self.zoom if self.zoom else 1.0
        self.camera_x = before_x - (mouse_x / after_zoom)
        self.camera_y = before_y - (mouse_y / after_zoom)
        self.clamp_camera()

    def update_camera(self, dt: float):
        """Update camera position based on WASD + mouse edge scrolling."""
        keys = pygame.key.get_pressed()
        speed = float(CAMERA_SPEED_PX_PER_SEC) * float(dt)

        dx = 0.0
        dy = 0.0

        # WASD pan (world-space pixels)
        if keys[pygame.K_a]:
            dx -= speed
        if keys[pygame.K_d]:
            dx += speed
        if keys[pygame.K_w]:
            dy -= speed
        if keys[pygame.K_s]:
            dy += speed

        # Mouse edge scroll (still in world-space pixels)
        mouse_x, mouse_y = pygame.mouse.get_pos()
        if mouse_x < CAMERA_EDGE_MARGIN_PX:
            dx -= speed
        elif mouse_x > int(getattr(self, "window_width", self.screen.get_width())) - CAMERA_EDGE_MARGIN_PX:
            dx += speed

        if mouse_y < CAMERA_EDGE_MARGIN_PX:
            dy -= speed
        elif mouse_y > int(getattr(self, "window_height", self.screen.get_height())) - CAMERA_EDGE_MARGIN_PX:
            dy += speed

        if dx or dy:
            self.camera_x += dx
            self.camera_y += dy
            self.clamp_camera()
    
    def get_game_state(self) -> dict:
        """Get current game state for AI and UI."""
        castle = next((b for b in self.buildings if b.building_type == "castle"), None)
        return {
            "screen_w": int(getattr(self, "window_width", self.screen.get_width())),
            "screen_h": int(getattr(self, "window_height", self.screen.get_height())),
            # WK7: Display mode state for ESC Graphics menu
            "display_mode": getattr(self, "display_mode", "windowed"),
            "window_size": getattr(self, "window_size", (WINDOW_WIDTH, WINDOW_HEIGHT)),
            "gold": self.economy.player_gold,
            "heroes": self.heroes,
            "peasants": self.peasants,
            "guards": self.guards,
            "enemies": self.enemies,
            "buildings": self.buildings,
            "bounties": self.bounty_system.get_unclaimed_bounties(),
            "bounty_system": self.bounty_system,
            "wave": self.spawner.wave_number,
            "selected_hero": self.selected_hero,
            "selected_building": getattr(self, "selected_building", None),
            "castle": castle,
            "economy": self.economy,
            "world": self.world,
            # UI helper: placement mode info for HUD
            "placing_building_type": getattr(self.building_menu, "selected_building", None),
            # UI helper: whether debug UI is currently visible (used to gate debug-only HUD indicators)
            "debug_ui": bool(getattr(self.debug_panel, "visible", False)),
        }
    
    def render(self):
        """Render the game."""
        # Clear screen
        self.screen.fill(COLOR_BLACK)

        # Pixel art: quantize camera to integer pixels to reduce shimmer.
        camera_offset = (int(self.camera_x), int(self.camera_y))

        # If not zoomed, render directly to the screen to avoid an expensive smoothscale.
        if abs((self.zoom if self.zoom else 1.0) - 1.0) < 1e-6:
            view_surface = self.screen
        else:
            # Render world + entities to a zoomed "camera view" surface, then scale to window.
            win_w = int(getattr(self, "window_width", self.screen.get_width()))
            win_h = int(getattr(self, "window_height", self.screen.get_height()))
            view_w = max(1, int(win_w / (self.zoom if self.zoom else 1.0)))
            view_h = max(1, int(win_h / (self.zoom if self.zoom else 1.0)))
            if self._view_surface is None or self._view_surface_size != (view_w, view_h):
                self._view_surface = pygame.Surface((view_w, view_h))
                self._view_surface_size = (view_w, view_h)
            view_surface = self._view_surface
            view_surface.fill(COLOR_BLACK)

        # Render world
        self.world.render(view_surface, camera_offset)

        # Render buildings
        for building in self.buildings:
            building.render(view_surface, camera_offset)

        # Render enemies
        for enemy in self.enemies:
            # Fog-of-war: enemies should only be visible when currently in vision (VISIBLE),
            # not in explored-but-dim (SEEN) tiles.
            gx, gy = self.world.world_to_grid(getattr(enemy, "x", 0.0), getattr(enemy, "y", 0.0))
            if 0 <= gx < self.world.width and 0 <= gy < self.world.height:
                if self.world.visibility[gy][gx] != Visibility.VISIBLE:
                    continue
            else:
                continue
            enemy.render(view_surface, camera_offset)

        # Render heroes
        for hero in self.heroes:
            hero.render(view_surface, camera_offset)

        # Render guards
        for guard in self.guards:
            guard.render(view_surface, camera_offset)

        # Render peasants
        for peasant in self.peasants:
            peasant.render(view_surface, camera_offset)

        # Render tax collector
        if self.tax_collector:
            self.tax_collector.render(view_surface, camera_offset)

        # Render building preview
        self.building_menu.render(view_surface, camera_offset)
        
        # Render building list panel (if visible)
        if self.building_list_panel.visible:
            selected_type = getattr(self.building_menu, "selected_building", None)
            self.building_list_panel.render(view_surface, self.economy, self.buildings, selected_type)

        # Render VFX overlay (world-space) if present.
        if self.vfx_system is not None and hasattr(self.vfx_system, "render"):
            try:
                self.vfx_system.render(view_surface, camera_offset)
            except Exception:
                pass

        # Fog-of-war overlay (covers world + entities/markers in unrevealed areas)
        # Draw AFTER world/entities/VFX so hidden areas remain hidden.
        if hasattr(self.world, "render_fog"):
            self.world.render_fog(view_surface, camera_offset)

        # Hotfix: Bounties must be visible even in black fog (UNSEEN). Render AFTER fog overlay so
        # the solid-black fog pass does not hide bounty flags.
        # Precompute lightweight UI metrics (responders/attractiveness) so bounty markers can display them.
        if hasattr(self.bounty_system, "update_ui_metrics"):
            try:
                self.bounty_system.update_ui_metrics(self.heroes, self.enemies, self.buildings)
            except Exception:
                pass
        self.bounty_system.render(view_surface, camera_offset)

        # Scale the world to the actual window (reusing a destination surface)
        if view_surface is not self.screen:
            # Pixel art: nearest-neighbor scaling (no blur).
            win_w = int(getattr(self, "window_width", self.screen.get_width()))
            win_h = int(getattr(self, "window_height", self.screen.get_height()))
            try:
                pygame.transform.scale(view_surface, (win_w, win_h), self._scaled_surface)
                self.screen.blit(self._scaled_surface, (0, 0))
            except Exception as e:
                raise
        
        # Render HUD
        if not bool(getattr(self, "screenshot_hide_ui", False)):
            self.hud.render(self.screen, self.get_game_state())
            
            # Render debug panel
            self.debug_panel.render(self.screen, self.get_game_state())
            
            # Render building panel
            self.building_panel.render(self.screen, self.heroes, self.economy)
            
            # WK7: Render build catalog panel (castle-driven)
            if self.build_catalog_panel.visible:
                self.build_catalog_panel.render(self.screen, self.economy, self.buildings)

            # WK7: Pause menu (rendered before pause overlay)
            if self.pause_menu.visible:
                self.pause_menu.render(self.screen)

            # Perf overlay (helps diagnose lag spikes)
            if self.show_perf:
                self.render_perf_overlay(self.screen)
            
            # Pause overlay (only show if paused but menu not visible)
            if self.paused and not self.pause_menu.visible:
                self.screen.blit(self._pause_overlay, (0, 0))
                
                font = pygame.font.Font(None, 72)
                text = font.render("PAUSED", True, (255, 255, 255))
                win_w = int(getattr(self, "window_width", self.screen.get_width()))
                win_h = int(getattr(self, "window_height", self.screen.get_height()))
                text_rect = text.get_rect(center=(win_w // 2, win_h // 2))
                self.screen.blit(text, text_rect)
        
        # NOTE (WK7): On some Windows setups, rapid mode switches can intermittently crash inside
        # SDL/driver during flip(). update() has proven more robust in practice.
        try:
            pygame.display.update()
        except Exception as e:
            raise


    def render_perf_overlay(self, surface: pygame.Surface):
        now_ms = pygame.time.get_ticks()
        if self._perf_last_ms == 0:
            self._perf_last_ms = now_ms

        # Update snapshot ~1x/sec (pathfinding stats) and ~4x/sec (counts + timings).
        if self._perf_overlay_next_update_ms == 0:
            self._perf_overlay_next_update_ms = now_ms

        if now_ms >= self._perf_overlay_next_update_ms:
            self._perf_overlay_next_update_ms = now_ms + 250
            self._perf_snapshot["fps"] = float(self.clock.get_fps())
            self._perf_snapshot["heroes"] = len([h for h in self.heroes if getattr(h, "is_alive", True)])
            self._perf_snapshot["enemies"] = len([e for e in self.enemies if getattr(e, "is_alive", False)])
            self._perf_snapshot["peasants"] = len([p for p in self.peasants if getattr(p, "is_alive", True)])
            self._perf_snapshot["guards"] = len([g for g in self.guards if getattr(g, "is_alive", False)])
            self._perf_overlay_dirty = True

        if now_ms - self._perf_last_ms >= 1000:
            self._perf_last_ms = now_ms
            self._perf_pf_calls = perf_stats.pathfinding.calls
            self._perf_pf_failures = perf_stats.pathfinding.failures
            self._perf_pf_total_ms = perf_stats.pathfinding.total_ms
            perf_stats.reset_pathfinding()
            self._perf_overlay_dirty = True

        # Rebuild panel only when sampled values change.
        if self._perf_overlay_panel is None or self._perf_overlay_dirty:
            self._perf_overlay_dirty = False

            fps = float(self._perf_snapshot.get("fps", 0.0))
            enemies_alive = int(self._perf_snapshot.get("enemies", 0))
            heroes_alive = int(self._perf_snapshot.get("heroes", 0))
            peasants_alive = int(self._perf_snapshot.get("peasants", 0))
            guards_alive = int(self._perf_snapshot.get("guards", 0))

            lines = [
                f"FPS: {fps:0.1f}",
                f"Entities: heroes={heroes_alive} peasants={peasants_alive} guards={guards_alive} enemies={enemies_alive} (cap={MAX_ALIVE_ENEMIES})",
                f"Loop ms (ema): events={self._perf_events_ms:0.2f} update={self._perf_update_ms:0.2f} render={self._perf_render_ms:0.2f}",
                f"PF calls/s: {self._perf_pf_calls}  fails/s: {self._perf_pf_failures}  ms/s: {self._perf_pf_total_ms:0.1f}",
            ]

            font = get_font(16)
            pad = 6
            w = 0
            h = 0
            rendered = []
            for line in lines:
                s = font.render(line, True, (255, 255, 255))
                rendered.append(s)
                w = max(w, s.get_width())
                h += s.get_height()

            panel = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 140))
            yy = pad
            for s in rendered:
                panel.blit(s, (pad, yy))
                yy += s.get_height()

            # Close button (X) drawn into cached panel
            x_surf = font.render("X", True, (255, 255, 255))
            size = 18
            close_local = pygame.Rect(panel.get_width() - size - 4, 4, size, size)
            pygame.draw.rect(panel, (45, 45, 55), close_local)
            pygame.draw.rect(panel, (120, 120, 150), close_local, 1)
            panel.blit(x_surf, (close_local.centerx - x_surf.get_width() // 2, close_local.centery - x_surf.get_height() // 2))
            self._perf_overlay_panel = panel

        # Reposition: bottom-left of the world area (avoid top bar, right panel, bottom bar)
        win_w = int(getattr(self, "window_width", surface.get_width()))
        win_h = int(getattr(self, "window_height", surface.get_height()))
        top_h = int(getattr(self.hud, "top_bar_height", 48))
        bottom_h = int(getattr(self.hud, "bottom_bar_height", 96))

        panel = self._perf_overlay_panel
        px = 10
        py = max(top_h + 10, win_h - bottom_h - panel.get_height() - 10)
        surface.blit(panel, (px, py))

        # Click target in screen coords (for close)
        size = 18
        self._perf_close_rect = pygame.Rect(px + panel.get_width() - size - 4, py + 4, size, size)
    
    def run(self):
        """Main game loop."""
        while self.running:
            # Apply any queued display settings change at a safe point (outside event polling).
            pending = getattr(self, "_pending_display_settings", None)
            if pending:
                try:
                    dm, ws = pending
                    self._pending_display_settings = None
                    self.apply_display_settings(dm, ws)
                except Exception:
                    # If anything goes wrong, clear the pending request and continue.
                    self._pending_display_settings = None


            if DETERMINISTIC_SIM:
                # Keep realtime pacing, but do not use wall-clock delta for simulation.
                tick_ms = self.clock.tick(FPS)
                dt = 1.0 / max(1, int(SIM_TICK_HZ))
            else:
                tick_ms = self.clock.tick(FPS)
                dt = tick_ms / 1000.0  # Delta time in seconds


            t0 = time.perf_counter()
            self.handle_events()
            t1 = time.perf_counter()


            self.update(dt)
            t2 = time.perf_counter()


            self.render()
            t3 = time.perf_counter()


            # Perf timings (EMA). Diagnostic only: must not affect simulation state.
            if self.show_perf:
                evt_ms = (t1 - t0) * 1000.0
                upd_ms = (t2 - t1) * 1000.0
                rnd_ms = (t3 - t2) * 1000.0

                alpha = 0.12
                self._perf_events_ms = evt_ms if self._perf_events_ms <= 0 else (self._perf_events_ms * (1 - alpha) + evt_ms * alpha)
                self._perf_update_ms = upd_ms if self._perf_update_ms <= 0 else (self._perf_update_ms * (1 - alpha) + upd_ms * alpha)
                self._perf_render_ms = rnd_ms if self._perf_render_ms <= 0 else (self._perf_render_ms * (1 - alpha) + rnd_ms * alpha)
        
        pygame.quit()

