"""
Main game engine - handles the game loop, input, and coordination.
"""
import time
import os
import pygame
from config import (
    WINDOW_WIDTH, WINDOW_HEIGHT, FPS, TILE_SIZE,
    MAP_WIDTH, MAP_HEIGHT, COLOR_BLACK,
    CAMERA_SPEED_PX_PER_SEC, CAMERA_EDGE_MARGIN_PX,
    ZOOM_MIN, ZOOM_MAX,
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
    DEFAULT_SPEED_TIER,
    CONVERSATION_COOLDOWN_MS,
    CONVERSATION_HISTORY_LIMIT,
)
from game.graphics.vfx import VFXSystem
from game.audio.audio_system import AudioSystem
from game.world import World, Visibility

from game.entities import Castle, Hero, TaxCollector, Peasant, Guard
from game.systems import CombatSystem, EconomySystem, EnemySpawner, BountySystem, LairSystem, NeutralBuildingSystem
from game.systems.buffs import BuffSystem
from game.ui import HUD, BuildingMenu, DebugPanel, BuildingPanel, DevToolsPanel
from game.ui.building_list_panel import BuildingListPanel
from game.ui.pause_menu import PauseMenu
from game.ui.build_catalog_panel import BuildCatalogPanel
from game.input_handler import InputHandler
from game.display_manager import DisplayManager
from game.building_factory import BuildingFactory
from game.cleanup_manager import CleanupManager
from game.events import EventBus, GameEventType
from game.systems.protocol import SystemContext
from game.types import BountyType, HeroClass
from game.graphics.font_cache import get_font
from game.graphics.render_context import set_render_zoom
from game.graphics.renderers import RendererRegistry
from game.systems import perf_stats
from game.sim.determinism import set_sim_seed
from game.sim.timebase import set_sim_now_ms, get_time_multiplier, set_time_multiplier
from ai.context_builder import ContextBuilder

from game.input_manager import InputManager

class GameEngine:
    """Main game engine class."""
    
    def __init__(self, early_nudge_mode: str | None = None, input_manager: InputManager | None = None, headless: bool = False, headless_ui: bool = False):
        self.headless = headless
        self.headless_ui = headless_ui
        pygame.init()
        pygame.font.init()
        
        self.input_manager = input_manager

        # Determinism knobs (future multiplayer enablement).
        # Seed early so world gen + initial lairs are reproducible when enabled.
        set_sim_seed(SIM_SEED)
        self._sim_now_ms = 0
        # wk12 Chronos: 5-tier speed control; default NORMAL (0.5x). Camera dt kept separate in run().
        set_time_multiplier(DEFAULT_SPEED_TIER)
        self._camera_dt = 0.0

        # Early pacing guardrail (ContentScenarioDirector, wk1 broad sweep):
        # Within the first few minutes, surface a clear prompt and optionally place
        # a starter bounty using existing systems. Driven by sim-time (dt), not wall-clock.
        self._early_nudge_elapsed_s = 0.0
        self._early_nudge_tip_shown = False
        self._early_nudge_starter_bounty_done = False
        self._early_nudge_mode = (early_nudge_mode or EARLY_PACING_NUDGE_MODE or "auto").strip().lower()
        
        # Camera state (always needed for simulation coordinate queries)
        self.camera_x = 0
        self.camera_y = 0
        self.zoom = 1.0
        self.default_zoom = 1.0
        self.clock = pygame.time.Clock()
        self.running = True
        self.paused = False

        # Perf counters (diagnostic, always safe to init)
        self.show_perf = False
        self._perf_last_ms = 0
        self._perf_pf_calls = 0
        self._perf_pf_failures = 0
        self._perf_pf_total_ms = 0.0
        self._perf_overlay_next_update_ms = 0
        self._perf_overlay_panel = None
        self._perf_overlay_dirty = True
        self._perf_snapshot = {"fps": 0.0, "heroes": 0, "enemies": 0, "peasants": 0, "guards": 0}
        self._perf_events_ms = 0.0
        self._perf_update_ms = 0.0
        self._perf_render_ms = 0.0

        # Initialize game world (pure simulation, no Pygame dependency)
        self.world = World()
        self.event_bus = EventBus()
        self.renderer_registry = None if headless and not headless_ui else RendererRegistry()
        self._renderer_prune_accum_s = 0.0

        if not headless and not headless_ui:
            # -----------------------------
            # Display / window mode (WK7: runtime switching)
            # -----------------------------
            initial_mode = "borderless" if DEFAULT_BORDERLESS else "windowed"
            self.display_mode = initial_mode
            self.window_size = (1280, 720)
            self._pending_display_settings: tuple[str, tuple[int, int] | None] | None = None
            self._borderless_drag_active = False
            self._borderless_drag_start_pos = None
            self._borderless_drag_window_offset = None
            self.display_manager = DisplayManager(self)
            self.apply_display_settings(self.display_mode, self.window_size)
            self.screenshot_hide_ui = False
            self.show_perf = True
            # Render surfaces
            self._view_surface = None
            self._view_surface_size = (0, 0)
            self._scaled_surface = pygame.Surface((self.window_width, self.window_height))
            self._pause_overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
            self._pause_overlay.fill((0, 0, 0, 128))
            self._pause_font = None
            self._last_ui_cursor_pos = (0, 0)
        elif headless_ui:
            # Virtual screen for Ursina overlay; match UrsinaApp default (windowed, bordered)
            self.display_mode = "windowed"
            self.window_size = (1920, 1080)
            self._pending_display_settings = None
            self._borderless_drag_active = False
            self._borderless_drag_start_pos = None
            self._borderless_drag_window_offset = None
            self.display_manager = None
            self.screenshot_hide_ui = False
            self.show_perf = True
            self.window_width = 1920
            self.window_height = 1080
            self._view_surface = None
            self._view_surface_size = (0, 0)
            
            # Use SRCALPHA so the background is transparent and Ursina shows through
            self.screen = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
            self._scaled_surface = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
            self._pause_overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
            self._pause_overlay.fill((0, 0, 0, 128))
            self._pause_font = None
            self._last_ui_cursor_pos = (0, 0)
        else:
            # Headless stubs so attribute access doesn't crash
            self.display_mode = "headless"
            self.window_size = (1, 1)
            self._pending_display_settings = None
            self._borderless_drag_active = False
            self._borderless_drag_start_pos = None
            self._borderless_drag_window_offset = None
            self.display_manager = None
            self.screenshot_hide_ui = True
            self.window_width = 1
            self.window_height = 1
            self._view_surface = None
            self._view_surface_size = (0, 0)
            self._scaled_surface = None
            self._pause_overlay = None
            self._pause_font = None
            self.screen = None
        
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
        self.building_factory = BuildingFactory()
        
        # Selection (always needed for simulation queries)
        self.selected_building = None
        self.selected_peasant = None
        self.selected_hero = None
        
        # Bounty system
        self.bounty_system = BountySystem()
        
        # AI controller (will be set from main.py)
        self.ai_controller = None
        
        # Tax collector (created after castle is placed)
        self.tax_collector = None

        if not headless or headless_ui:
            # Audio, UI, VFX — only needed for Pygame rendering
            self.audio_system = AudioSystem(enabled=True)
            self.hud = HUD(self.window_width, self.window_height)
            self.micro_view = self.hud._micro_view
            self._last_conversation_request_ms = -CONVERSATION_COOLDOWN_MS
            self._previous_micro_view_mode = None
            self._last_interior_rumble_sim_ms: float | None = None
            self.building_menu = BuildingMenu()
            self.building_list_panel = BuildingListPanel(self.window_width, self.window_height)
            self.debug_panel = DebugPanel(self.window_width, self.window_height)
            self.dev_tools_panel = DevToolsPanel(self.event_bus, self.window_width, self.window_height)
            self.building_panel = BuildingPanel(self.window_width, self.window_height)
            self.building_panel.engine = self
            self.pause_menu = PauseMenu(self.window_width, self.window_height, engine=self, audio_system=self.audio_system)
            self.build_catalog_panel = BuildCatalogPanel(self.window_width, self.window_height)
            self.input_handler = InputHandler(self)
            self.cleanup_manager = CleanupManager(self)
            self.vfx_system = VFXSystem()
            self.event_bus.subscribe("*", self.audio_system.on_event)
            self.event_bus.subscribe("*", self.vfx_system.on_event)
        else:
            # Headless stubs: _NullStub silently absorbs any .method() or .attr access
            class _NullStub:
                """Swallows all attribute access and method calls."""
                def __getattr__(self, name):
                    return _NullStub()
                def __call__(self, *a, **kw):
                    return _NullStub()
                def __bool__(self):
                    return False
                def __iter__(self):
                    return iter([])
            _s = _NullStub()
            self.audio_system = None  # Keep None so event_bus doesn't subscribe
            self.hud = _s
            self.micro_view = _s
            self._last_conversation_request_ms = 0
            self._previous_micro_view_mode = None
            self._last_interior_rumble_sim_ms = None
            self.building_menu = _s
            self.building_list_panel = _s
            self.debug_panel = _s
            self.dev_tools_panel = _s
            self.building_panel = _s
            self.pause_menu = _s
            self.build_catalog_panel = _s
            self.input_handler = None
            self.cleanup_manager = CleanupManager(self)
            self.vfx_system = None

        # Initialize starting buildings (pure simulation)
        self.setup_initial_state()
        
        # Start ambient loop on game start (audio only if present)
        if self.audio_system is not None:
            self.audio_system.set_ambient("ambient_loop", volume=0.4)

    def _update_fog_of_war(self):
        """Update fog-of-war visibility around the castle, living heroes, neutral buildings, and guards.

        WK22 Agent-10 perf fix: cache the tile-grid positions of every revealer and
        skip the expensive ``world.update_visibility`` call when no vision source has
        moved by at least one full tile since the last rebuild.  This eliminates the
        dominant per-frame cost (previously ~55% of total frame time).
        """
        # Tunables (tile radius). Kept local to avoid cross-agent config conflicts.
        # WK17: per docs/vision_rules_fog_of_war.md (Agent 05 spec).
        CASTLE_VISION_TILES = 10
        HERO_VISION_TILES = 7
        GUARD_VISION_TILES = 6
        NEUTRAL_VISION = {"house": 3, "farm": 5, "food_stand": 3}

        castle = next((b for b in self.buildings if getattr(b, "building_type", None) == "castle"), None)
        revealers = []
        hero_revealers = []  # Track which revealers are heroes (for XP tracking)
        
        if castle is not None:
            revealers.append((castle.center_x, castle.center_y, CASTLE_VISION_TILES))

        for hero in self.heroes:
            if getattr(hero, "is_alive", True):
                revealers.append((hero.x, hero.y, HERO_VISION_TILES))
                hero_revealers.append((hero, hero.x, hero.y, HERO_VISION_TILES))

        # WK17: Neutral buildings (house, farm, food_stand) as vision sources.
        for building in self.buildings:
            btype = getattr(building, "building_type", None)
            if btype not in NEUTRAL_VISION:
                continue
            if getattr(building, "is_constructed", True) is not True:
                continue
            if getattr(building, "hp", 1) <= 0:
                continue
            radius = NEUTRAL_VISION[btype]
            revealers.append((building.center_x, building.center_y, radius))

        # WK17: Living guards as vision sources.
        for guard in self.guards:
            if not getattr(guard, "is_alive", True):
                continue
            revealers.append((guard.x, guard.y, GUARD_VISION_TILES))

        if not revealers:
            return

        # ---- Dirty check: skip update if no revealer moved a full tile ----
        # Build a canonical snapshot of (grid_x, grid_y, radius) for comparison.
        # Sort so list order (heroes vs buildings iteration) cannot spuriously skip updates.
        w2g = self.world.world_to_grid
        grid_snapshot = tuple(
            sorted((w2g(wx, wy)[0], w2g(wx, wy)[1], r) for wx, wy, r in revealers)
        )
        prev = getattr(self, "_fog_revealers_snapshot", None)
        if prev is not None and prev == grid_snapshot:
            # Nothing changed on the tile grid — skip the expensive rebuild.
            return
        self._fog_revealers_snapshot = grid_snapshot
        # Increment fog revision so the Ursina renderer knows the grid has changed.
        self._fog_revision = getattr(self, "_fog_revision", 0) + 1

        # ---- Perform the full visibility update ----
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
        if hasattr(castle, "set_event_bus"):
            castle.set_event_bus(self.event_bus)

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
        if not self.input_manager:
            return
        if self.input_handler is None:
            return
        self.input_handler.process_events()

    def request_display_settings(self, display_mode: str, window_size: tuple[int, int] | None = None):
        """Queue a display mode change to be applied at a safe point (between frames)."""
        self._pending_display_settings = (str(display_mode), window_size)
    
    def select_building_for_placement(self, building_type: str) -> bool:
        """Select a building type for placement if checks pass."""
        return self.input_handler.select_building_for_placement(building_type)
    
    def handle_keydown(self, event):
        """Handle keyboard input."""
        self.input_handler.handle_keydown(event)
    
    def handle_mousedown(self, event):
        """Handle mouse clicks."""
        self.input_handler.handle_mousedown(event)
    
    def handle_mousemove(self, event):
        """Handle mouse movement."""
        self.input_handler.handle_mousemove(event)
    
    def try_select_hero(self, screen_pos: tuple) -> bool:
        """Try to select a hero at the given screen position. Returns True if selected."""
        world_x, world_y = self.screen_to_world(screen_pos[0], screen_pos[1])
        
        for hero in self.heroes:
            if hero.is_alive and hero.distance_to(world_x, world_y) < hero.size:
                self.selected_hero = hero
                self.selected_peasant = None
                # Ensure the right panel becomes visible on selection (Tab panel UX).
                if hasattr(self, "hud"):
                    try:
                        self.hud.right_panel_visible = True
                        if hasattr(self.hud, "_micro_view"):
                            self.hud._micro_view.enter_hero_focus(hero)
                    except Exception:
                        pass
                return True
        
        return False

    def try_select_tax_collector(self, screen_pos: tuple) -> bool:
        """Try to select the tax collector at the given screen position. Returns True if selected. (wk16)"""
        if self.tax_collector is None:
            return False
        world_x, world_y = self.screen_to_world(screen_pos[0], screen_pos[1])
        tc = self.tax_collector
        if tc.distance_to(world_x, world_y) < tc.size:
            self.selected_hero = tc  # unified selection state for left panel
            self.selected_building = None
            self.selected_peasant = None
            if hasattr(self, "hud"):
                try:
                    self.hud.right_panel_visible = True
                except Exception:
                    pass
            return True
        return False

    def try_select_guard(self, screen_pos: tuple) -> bool:
        """Try to select a guard at the given screen position. Returns True if selected."""
        world_x, world_y = self.screen_to_world(screen_pos[0], screen_pos[1])
        for guard in self.guards:
            if getattr(guard, "is_alive", True) and guard.distance_to(world_x, world_y) < guard.size:
                self.selected_hero = guard
                self.selected_building = None
                self.selected_peasant = None
                if hasattr(self, "hud"):
                    try:
                        self.hud.right_panel_visible = True
                    except Exception:
                        pass
                return True
        return False

    def try_select_peasant(self, screen_pos: tuple) -> bool:
        """Try to select a peasant at the given screen position. Returns True if selected."""
        world_x, world_y = self.screen_to_world(screen_pos[0], screen_pos[1])
        for peasant in self.peasants:
            if getattr(peasant, "is_alive", True) and peasant.distance_to(world_x, world_y) < peasant.size:
                self.selected_peasant = peasant
                self.selected_hero = None
                self.selected_building = None
                if hasattr(self, "building_panel"):
                    try:
                        self.building_panel.deselect()
                    except Exception:
                        pass
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
                self.selected_peasant = None
                self.building_panel.select_building(building, self.heroes)
                return True
        
        return False
    
    def try_hire_hero(self):
        """Try to hire a hero from the selected guild building or auto-locate one."""
        allowed = frozenset({"warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild"})

        def _is_hirable_guild(b) -> bool:
            bt = getattr(b, "building_type", "")
            if bt not in allowed:
                return False
            # Match building_panel / navigation: missing is_constructed → treat as built (see Building base).
            return getattr(b, "is_constructed", True) is True

        guild = None
        sel = self.selected_building
        if sel is not None and _is_hirable_guild(sel):
            guild = sel

        if guild is None:
            for b in self.buildings:
                if _is_hirable_guild(b):
                    guild = b
                    break

        if guild is None:
            self.hud.add_message("Requires a constructed guild (Warrior/Ranger/Rogue/Wizard)!", (255, 100, 100))
            return

        if not self.economy.can_afford_hero():
            self.hud.add_message("Not enough gold to hire!", (255, 100, 100))
            return
        
        # Hire the hero
        self.economy.hire_hero()
        guild.hire_hero()
        
        # Spawn hero near guild
        class_by_guild = {
            "warrior_guild": HeroClass.WARRIOR.value,
            "ranger_guild": HeroClass.RANGER.value,
            "rogue_guild": HeroClass.ROGUE.value,
            "wizard_guild": HeroClass.WIZARD.value,
        }
        hero_class = class_by_guild.get(guild.building_type, HeroClass.WARRIOR.value)
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
        building = self.building_factory.create(building_type, grid_x, grid_y)
        
        if building is None:
            return

        # Newly placed buildings start unconstructed (1 HP, non-targetable) until a peasant begins building.
        if hasattr(building, "mark_unconstructed"):
            building.mark_unconstructed()
        
        self.buildings.append(building)
        if hasattr(building, "set_event_bus"):
            building.set_event_bus(self.event_bus)
        self.building_menu.cancel_selection()
        self.hud.add_message(f"Placed: {building_type.replace('_', ' ').title()} (awaiting construction)", (100, 255, 100))
        
        # Queue building placement event for EventBus subscribers (Audio/VFX).
        self.event_bus.emit({
            "type": GameEventType.BUILDING_PLACED.value,
            "x": float(grid_x * TILE_SIZE),
            "y": float(grid_y * TILE_SIZE),
        })
    
    def place_bounty(self):
        """Place a bounty at the current mouse position."""
        mouse_pos = self.input_manager.get_mouse_pos() if getattr(self, "input_manager", None) else pygame.mouse.get_pos()
        world_x, world_y = self.screen_to_world(mouse_pos[0], mouse_pos[1])
        
        # Bounty reward tiers (player-paid; cost == reward).
        mods = self.input_manager.get_key_mods() if getattr(self, "input_manager", None) else {'shift': False, 'ctrl': False, 'alt': False}
        if not getattr(self, "input_manager", None): # Fallback
            pg_mods = pygame.key.get_mods()
            mods = {'ctrl': bool(pg_mods & pygame.KMOD_CTRL), 'shift': bool(pg_mods & pygame.KMOD_SHIFT)}
            
        if mods.get('ctrl'):
            reward = int(BOUNTY_REWARD_HIGH)
        elif mods.get('shift'):
            reward = int(BOUNTY_REWARD_MED)
        else:
            reward = int(BOUNTY_REWARD_LOW)
        
        if not self.economy.add_bounty(reward):
            self.hud.add_message("Not enough gold for bounty!", (255, 100, 100))
            return
        
        self.bounty_system.place_bounty(world_x, world_y, reward, BountyType.EXPLORE.value)
        self.hud.add_message(f"Bounty placed (${reward}). Heroes will respond.", (255, 215, 0))
        
        # Queue bounty placement event for EventBus subscribers (Audio/VFX).
        self.event_bus.emit({
            "type": GameEventType.BOUNTY_PLACED.value,
            "x": float(world_x),
            "y": float(world_y),
        })

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
        self.bounty_system.place_bounty(bx, by, reward, BountyType.ATTACK_LAIR.value, target=lair)
        self._early_nudge_starter_bounty_done = True
        self.hud.add_message(f"Starter bounty placed: Clear the lair (+${reward})", (255, 215, 0))
    
    def update(self, dt: float):
        """Update game state."""
        if not self._prepare_sim_and_camera(dt):
            self._flush_event_bus()
            return

        game_state = self.get_game_state()

        # wk12 Chronos: ensure all buildings have event_bus for hero_entered/exited_building events
        for building in self.buildings:
            if getattr(building, "_event_bus", None) is None and hasattr(building, "set_event_bus"):
                building.set_event_bus(self.event_bus)

        system_ctx = self._build_system_context()
        self._update_ai_and_heroes(dt, game_state)
        castle = self._update_world_systems(system_ctx, dt, game_state)
        self._update_peasants(dt, game_state, castle)
        enemy_ranged_events = self._update_enemies(dt)
        self._update_guards(dt)
        self._spawn_enemies(dt)
        self._apply_entity_separation(dt)
        events = self._process_combat(system_ctx, dt, enemy_ranged_events)
        self._route_combat_events(events)
        self._cleanup_after_combat()
        self._process_bounties()
        self._update_neutral_systems(dt, castle)
        self._update_buildings(dt)
        self._update_render_animations(dt)
        self._finalize_update(dt)
        self._poll_conversation_response()

    def send_player_message(self, hero, text: str):
        """Send a player message to a hero in conversation (wk14). Queues LLM request and sets chat panel waiting."""
        chat_panel = getattr(self.hud, "_chat_panel", None)
        if not chat_panel:
            return
        llm = getattr(self.ai_controller, "llm_brain", None)
        if not llm:
            return
        now_ms = pygame.time.get_ticks()
        if now_ms - self._last_conversation_request_ms < CONVERSATION_COOLDOWN_MS:
            return
        self._last_conversation_request_ms = now_ms
        history = (getattr(chat_panel, "conversation_history", []) or [])[-CONVERSATION_HISTORY_LIMIT:]
        game_state = self.get_game_state()
        context = ContextBuilder.build_hero_context(hero, game_state)
        llm.request_conversation(hero.name, context, history, text)
        chat_panel.waiting_for_response = True

    def _poll_conversation_response(self):
        """When chat is active, poll LLM for conversation response and push to chat panel (wk14)."""
        chat_panel = getattr(self.hud, "_chat_panel", None)
        llm = getattr(self.ai_controller, "llm_brain", None)
        if not chat_panel or not llm:
            return
        if not getattr(chat_panel, "is_active", lambda: False)():
            return
        hero_target = getattr(chat_panel, "hero_target", None)
        if not hero_target:
            return
        response_dict = llm.get_conversation_response(hero_target.name)
        if response_dict is not None:
            spoken = response_dict.get("spoken_response", response_dict.get("text", "I'm thinking..."))
            chat_panel.receive_response(spoken)
            
            tool_action = response_dict.get("tool_action")
            if tool_action:
                from ai.behaviors.llm_bridge import apply_llm_decision
                game_state = self.get_game_state()
                # apply_llm_decision expects 'action', so map tool_action to it
                response_dict["action"] = tool_action 
                apply_llm_decision(
                    self.ai_controller,
                    hero_target,
                    response_dict,
                    game_state,
                    source="chat"
                )

    def _prepare_sim_and_camera(self, dt: float) -> bool:
        """Apply deterministic timing and update camera when world input is allowed."""
        if DETERMINISTIC_SIM:
            # Drive gameplay timing off simulation time (not wall-clock).
            self._sim_now_ms += int(round(float(dt) * 1000.0))
            set_sim_now_ms(self._sim_now_ms)
        else:
            set_sim_now_ms(None)

        # wk12 Chronos: speed-tier pause (multiplier 0) or menu pause → no sim (return False). Camera still pans when paused (not when menu open).
        if get_time_multiplier() == 0.0 or self.paused:
            if not getattr(self.pause_menu, "visible", False):
                camera_dt = getattr(self, "_camera_dt", dt)
                self.update_camera(camera_dt)
            return False
        # V1.3-EXT-BUG-001: Do not move camera/zoom while menu open.
        if getattr(self.pause_menu, "visible", False):
            return False
        # Camera uses wall-clock dt for responsiveness; sim uses scaled dt (already passed in as dt).
        camera_dt = getattr(self, "_camera_dt", dt)
        self.update_camera(camera_dt)
        return True

    def _build_system_context(self) -> SystemContext:
        """Construct a shared context object for protocol-based systems."""
        return SystemContext(
            heroes=self.heroes,
            enemies=self.enemies,
            buildings=self.buildings,
            world=self.world,
            economy=self.economy,
            event_bus=self.event_bus,
        )

    def _update_ai_and_heroes(self, dt: float, game_state: dict):
        """Run AI controller and hero updates."""
        if self.ai_controller:
            self.ai_controller.update(dt, self.heroes, game_state)

        # WK18: Drain LLM move_to requests into physical state so hero executes immediately.
        from game.entities.hero import HeroState
        for hero in self.heroes:
            if getattr(hero, "llm_move_request", None) is not None:
                wx, wy = hero.llm_move_request
                hero.set_target_position(wx, wy)
                hero.llm_move_request = None

        for hero in self.heroes:
            hero.update(dt, game_state)

    def _apply_entity_separation(self, dt: float) -> None:
        """WK18 / WK22-Agent10: Soft collision / flocking separation for all mobile entities.

        Optimised from O(N²) brute-force to grid-based O(N) by binning
        entities into cells whose side equals ``min_dist_px``.  Each entity
        only inspects its own cell + the 8 adjacent cells, keeping the inner
        loop bounded by a small constant.
        """
        import math
        # Tunables: min distance (px), nudge strength (px/s when overlapping).
        min_dist_px = 16.0
        strength_per_sec = 250.0
        max_step = 120.0 * dt  # cap displacement per frame
        cell = min_dist_px  # grid cell size

        alive = []
        for lst in (self.heroes, self.enemies, self.peasants, self.guards):
            alive.extend(e for e in lst if getattr(e, "is_alive", True))
        if self.tax_collector and getattr(self.tax_collector, "is_alive", True):
            alive.append(self.tax_collector)

        if len(alive) < 2:
            return

        # Build spatial grid: cell key -> list of entity indices.
        grid: dict[tuple[int, int], list[int]] = {}
        for idx, ent in enumerate(alive):
            if getattr(ent, "is_inside_building", False):
                continue
            cx = int(ent.x // cell)
            cy = int(ent.y // cell)
            key = (cx, cy)
            bucket = grid.get(key)
            if bucket is None:
                grid[key] = [idx]
            else:
                bucket.append(idx)

        # For each entity, only check neighbours in the same + adjacent cells.
        for key, indices in grid.items():
            kx, ky = key
            # Gather candidate indices from the 3×3 neighbourhood.
            neighbours: list[int] = []
            for ox in range(kx - 1, kx + 2):
                for oy in range(ky - 1, ky + 2):
                    nb = grid.get((ox, oy))
                    if nb is not None:
                        neighbours.extend(nb)

            for i in indices:
                ent = alive[i]
                dx_sum, dy_sum = 0.0, 0.0
                ex, ey = ent.x, ent.y
                for j in neighbours:
                    if j == i:
                        continue
                    other = alive[j]
                    dx = ex - other.x
                    dy = ey - other.y
                    d2 = dx * dx + dy * dy
                    if d2 < min_dist_px * min_dist_px and d2 > 1e-12:
                        dist = math.sqrt(d2)
                        push = (min_dist_px - dist) * strength_per_sec * dt / dist
                        dx_sum += dx * push
                        dy_sum += dy * push
                if dx_sum != 0 or dy_sum != 0:
                    step = math.sqrt(dx_sum * dx_sum + dy_sum * dy_sum)
                    if step > max_step:
                        scale = max_step / step
                        dx_sum *= scale
                        dy_sum *= scale
                    ent.x += dx_sum
                    ent.y += dy_sum

    def _update_world_systems(self, system_ctx: SystemContext, dt: float, game_state: dict):
        """Update fog, buffs, and early pacing logic."""
        # Fog-of-war reveal (castle + heroes).
        self._update_fog_of_war()

        # Apply/refresh buffs (auras) once per tick so ATK/DEF stays dynamic and stable.
        self.buff_system.update(system_ctx, dt)

        castle = game_state.get("castle")

        # Content pacing guardrail: nudge player toward a clear early decision.
        self._maybe_apply_early_pacing_nudge(dt, castle)
        return castle

    def _update_peasants(self, dt: float, game_state: dict, castle):
        """Spawn and update peasant workers."""
        # Spawn peasants from the castle (1 every 5s) until there are 2 alive.
        self.peasant_spawn_timer += dt
        alive_peasants = [p for p in self.peasants if p.is_alive]
        if castle and len(alive_peasants) < 2 and self.peasant_spawn_timer >= 5.0:
            self.peasant_spawn_timer = 0.0
            self.peasants.append(Peasant(castle.center_x, castle.center_y))

        for peasant in self.peasants:
            peasant.update(dt, game_state)

    def _update_enemies(self, dt: float) -> list:
        """Update enemies and collect ranged projectile events."""
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
        return enemy_ranged_events

    def _update_guards(self, dt: float):
        """Update existing guard units."""
        # Update guards
        for guard in self.guards:
            guard.update(dt, self.enemies, world=self.world, buildings=self.buildings)

    def _spawn_enemies(self, dt: float):
        """Spawn enemies from waves and lairs with global cap enforcement."""
        # Spawn new enemies (with a safety cap to prevent runaway slowdown if enemies accumulate)
        alive_enemy_count = len([e for e in self.enemies if getattr(e, "is_alive", False)])
        remaining_slots = max(0, int(MAX_ALIVE_ENEMIES) - alive_enemy_count)
        if remaining_slots > 0:
            new_enemies = self.spawner.spawn(dt)
            if new_enemies:
                self.enemies.extend(new_enemies[:remaining_slots])

            # Spawn enemies from lairs (in addition to wave spawns)
            alive_enemy_count = len([e for e in self.enemies if getattr(e, "is_alive", False)])
            remaining_slots = max(0, int(MAX_ALIVE_ENEMIES) - alive_enemy_count)
            if remaining_slots > 0:
                lair_enemies = self.lair_system.spawn_enemies(dt, self.buildings)
                if lair_enemies:
                    self.enemies.extend(lair_enemies[:remaining_slots])

    def _process_combat(self, system_ctx: SystemContext, dt: float, enemy_ranged_events: list) -> list:
        """Run combat and queue downstream events in EventBus."""
        self.combat_system.update(system_ctx, dt)
        if enemy_ranged_events:
            # Enemy ranged attacks are emitted outside CombatSystem in enemy.update().
            self.event_bus.emit_batch(enemy_ranged_events)
        return self.combat_system.get_emitted_events()

    def _route_combat_events(self, events: list):
        """Handle user-facing combat outcomes and lair-clear follow-up effects."""
        # Handle combat events
        for event in events:
            if event["type"] == GameEventType.ENEMY_KILLED.value:
                self.hud.add_message(
                    f"{event['hero']} slew a {event['enemy']}! (+{event['gold']}g, +{event['xp']}xp)",
                    (255, 215, 0)
                )
            elif event["type"] == GameEventType.CASTLE_DESTROYED.value:
                self.hud.add_message("GAME OVER - Castle Destroyed!", (255, 0, 0))
                self.paused = True
            elif event["type"] == GameEventType.LAIR_CLEARED.value:
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
                            if getattr(b, "bounty_type", None) != BountyType.ATTACK_LAIR.value:
                                continue
                            if getattr(b, "target", None) is lair_obj:
                                if b.claim(hero_obj):
                                    # WK6 Mid-Sprint: Emit bounty_claimed event with position for visibility-gated audio
                                    bounty_claimed_events.append({
                                        "type": GameEventType.BOUNTY_CLAIMED.value,
                                        "x": float(b.x),
                                        "y": float(b.y),
                                        "reward": b.reward,
                                        "hero": hero_name,
                                    })
                except Exception:
                    # Bounty payout should never crash the sim.
                    pass
                
                if bounty_claimed_events:
                    self.event_bus.emit_batch(bounty_claimed_events)

                if lair_obj in self.buildings:
                    self.buildings.remove(lair_obj)
                if lair_obj in getattr(self.lair_system, "lairs", []):
                    self.lair_system.lairs.remove(lair_obj)

    def _cleanup_after_combat(self):
        """Remove dead entities and destroyed buildings after combat resolution."""
        # Clean up dead enemies
        self.enemies = [e for e in self.enemies if e.is_alive]

        # Clean up dead guards
        self.guards = [g for g in self.guards if getattr(g, "is_alive", False)]
        
        # Clean up destroyed buildings (WK5: auto-demolish at 0 HP + reference cleanup)
        self._cleanup_destroyed_buildings()

    def _process_bounties(self):
        """Resolve bounty claims and route claim events."""
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
                "type": GameEventType.BOUNTY_CLAIMED.value,
                "x": float(bounty.x),
                "y": float(bounty.y),
                "reward": bounty.reward,
                "hero": hero.name,
            })

        if bounty_claimed_events:
            self.event_bus.emit_batch(bounty_claimed_events)

        self.bounty_system.cleanup()

    def _update_neutral_systems(self, dt: float, castle):
        """Update neutral/economic support systems outside direct combat."""
        # Neutral buildings: auto-spawn + passive tax
        self.neutral_building_system.tick(dt, self.buildings, self.heroes, castle)

        # Update tax collector
        if self.tax_collector:
            self.tax_collector.update(dt, self.buildings, self.economy, world=self.world)

    def _update_buildings(self, dt: float):
        """Update buildings and collect building-driven projectile events."""
        # WK15: Advance timed research (sim-time based, deterministic).
        from game.sim.timebase import now_ms as sim_now_ms
        now_ms = int(sim_now_ms())
        for building in self.buildings:
            if getattr(building, "research_in_progress", None):
                advance = getattr(building, "advance_research", None)
                if callable(advance):
                    advance(now_ms)

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

        if building_ranged_events:
            self.event_bus.emit_batch(building_ranged_events)

    def _update_render_animations(self, dt: float):
        """Advance render-only entity animation state."""
        if self.headless:
            return
        # Ursina runs after this call; pygame HeroRenderer/EnemyRenderer clear
        # _render_anim_trigger here. Snapshot one-shots so Ursina billboards can still play attack/hurt.
        if getattr(self, "_ursina_skip_world_render", False):
            for hero in self.heroes:
                t = getattr(hero, "_render_anim_trigger", None)
                if t:
                    hero._ursina_anim_trigger = str(t)
            for enemy in self.enemies:
                t = getattr(enemy, "_render_anim_trigger", None)
                if t:
                    enemy._ursina_anim_trigger = str(t)
        self.renderer_registry.update_animations(
            dt=dt,
            heroes=self.heroes,
            enemies=self.enemies,
            peasants=self.peasants,
            tax_collector=self.tax_collector,
            guards=self.guards,
        )

    def _finalize_update(self, dt: float):
        """Finalize per-frame UI and VFX updates."""
        if self.headless:
            self._flush_event_bus()
            return
        # wk14: Interior building-under-attack rumble (throttled by sim time)
        from game.ui.micro_view_manager import ViewMode
        from game.events import GameEventType
        from game.sim.timebase import now_ms as sim_now_ms
        if (
            getattr(self.micro_view, "mode", None) == ViewMode.INTERIOR
            and getattr(self.micro_view, "interior_building", None) is not None
            and getattr(self.micro_view.interior_building, "is_under_attack", False)
        ):
            now_ms = float(sim_now_ms())
            last = getattr(self, "_last_interior_rumble_sim_ms", None)
            if last is None or (now_ms - last) >= 3000:
                self.event_bus.emit({"type": GameEventType.INTERIOR_BUILDING_UNDER_ATTACK.value})
                self._last_interior_rumble_sim_ms = now_ms
        self._flush_event_bus()

        # Update HUD
        self.hud.update()

        # Drop renderer instances for entities that no longer exist.
        self._renderer_prune_accum_s += float(dt)
        if self._renderer_prune_accum_s >= 1.0:
            self._renderer_prune_accum_s = 0.0
            self.renderer_registry.prune(
                heroes=self.heroes,
                enemies=self.enemies,
                peasants=self.peasants,
                tax_collector=self.tax_collector,
            )

        # Update VFX (after simulation state is updated).
        if self.vfx_system is not None and hasattr(self.vfx_system, "update"):
            try:
                self.vfx_system.update(dt)
            except Exception:
                pass

    def _flush_event_bus(self):
        """Flush queued events once per frame after updating listener context."""
        if self.audio_system is not None:
            win_w = int(self.window_width)
            win_h = int(self.window_height)
            self.audio_system.set_listener_view(
                self.camera_x, self.camera_y, self.zoom,
                win_w, win_h, self.world
            )
        self.event_bus.flush()
    
    def _cleanup_destroyed_buildings(self, emit_messages: bool = True):
        """Remove buildings at hp <= 0 (except castle) and clear references."""
        self.cleanup_manager.cleanup_destroyed_buildings(emit_messages=emit_messages)
    
    def apply_display_settings(self, display_mode: str, window_size: tuple[int, int] | None = None):
        """Apply display mode settings (fullscreen/borderless/windowed)."""
        # Ursina 3D viewer: pygame uses SDL dummy; real window is Ursina/Panda — use window.* APIs.
        if getattr(self, "headless_ui", False) and getattr(self, "_ursina_viewer", False):
            DisplayManager.apply_ursina_window(self, display_mode, window_size)
            return
        if self.display_manager is None:
            return
        self.display_manager.apply_settings(display_mode, window_size)
    
    def screen_to_world(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        """Convert screen-space pixels to world-space pixels, accounting for zoom."""
        z = self.zoom if self.zoom else 1.0
        return self.camera_x + (screen_x / z), self.camera_y + (screen_y / z)

    def clamp_camera(self):
        """Clamp camera to world bounds given current zoom."""
        win_w = int(self.window_width)
        win_h = int(self.window_height)
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

        win_w = int(self.window_width)
        win_h = int(self.window_height)
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

        mouse_x, mouse_y = self.input_manager.get_mouse_pos() if getattr(self, "input_manager", None) else pygame.mouse.get_pos()
        before_x, before_y = self.screen_to_world(mouse_x, mouse_y)

        self.set_zoom(self.zoom * factor)

        # Keep the same world point under the cursor after zooming.
        after_zoom = self.zoom if self.zoom else 1.0
        self.camera_x = before_x - (mouse_x / after_zoom)
        self.camera_y = before_y - (mouse_y / after_zoom)
        self.clamp_camera()

    def update_camera(self, dt: float):
        """Update camera position based on WASD + mouse edge scrolling."""
        # wk14: If chat is active, do not pan the camera (typing intercepts WASD)
        if hasattr(self, "hud"):
            chat_panel = getattr(self.hud, "_chat_panel", None)
            if chat_panel is not None and getattr(chat_panel, "is_active", lambda: False)():
                return

        keys = self.input_manager.get_key_mods() if getattr(self, "input_manager", None) else {'shift': False, 'ctrl': False, 'alt': False}
        speed = float(CAMERA_SPEED_PX_PER_SEC) * float(dt)

        dx = 0.0
        dy = 0.0

        # WASD pan (world-space pixels)
        if getattr(self, "input_manager", None):
            if self.input_manager.is_key_pressed('a'): dx -= speed
            if self.input_manager.is_key_pressed('d'): dx += speed
            if self.input_manager.is_key_pressed('w'): dy -= speed
            if self.input_manager.is_key_pressed('s'): dy += speed
        else:
            pg_keys = pygame.key.get_pressed()
            if pg_keys[pygame.K_a]: dx -= speed
            if pg_keys[pygame.K_d]: dx += speed
            if pg_keys[pygame.K_w]: dy -= speed
            if pg_keys[pygame.K_s]: dy += speed

        # Mouse edge scroll (still in world-space pixels)
        has_focus = self.input_manager.is_mouse_focused() if getattr(self, "input_manager", None) else pygame.mouse.get_focused()
        if has_focus:
            mx, my = self.input_manager.get_mouse_pos() if getattr(self, "input_manager", None) else pygame.mouse.get_pos()
            if mx < CAMERA_EDGE_MARGIN_PX:
                dx -= speed
            elif mx > int(self.window_width) - CAMERA_EDGE_MARGIN_PX:
                dx += speed

            if my < CAMERA_EDGE_MARGIN_PX:
                dy -= speed
            elif my > int(self.window_height) - CAMERA_EDGE_MARGIN_PX:
                dy += speed

        if dx or dy:
            self.camera_x += dx
            self.camera_y += dy
            self.clamp_camera()
    
    def get_game_state(self) -> dict:
        """Get current game state for AI and UI."""
        castle = next((b for b in self.buildings if b.building_type == "castle"), None)
        return {
            "screen_w": int(self.window_width),
            "screen_h": int(self.window_height),
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
            "selected_peasant": getattr(self, "selected_peasant", None),
            "castle": castle,
            "economy": self.economy,
            "world": self.world,
            # UI helper: placement mode info for HUD
            "placing_building_type": getattr(self.building_menu, "selected_building", None),
            # UI helper: whether debug UI is currently visible (used to gate debug-only HUD indicators)
            "debug_ui": bool(getattr(self.debug_panel, "visible", False)),
            # wk13 Living Interiors: right-panel mode and rect for input (ESC/map click exit)
            "micro_view_mode": getattr(self.micro_view, "mode", None),
            "micro_view_building": getattr(self.micro_view, "interior_building", None),
            # wk14: quest panel state for QuestViewPanel
            "micro_view_quest_hero": getattr(self.micro_view, "quest_hero", None),
            "micro_view_quest_data": getattr(self.micro_view, "quest_data", None),
            "right_panel_rect": getattr(self.hud, "_right_rect", None),
            "llm_available": getattr(self.ai_controller, "llm_brain", None) is not None,
            # Last MOUSEMOTION in engine.screen space — required when pygame.mouse is dummy (Ursina HUD).
            "ui_cursor_pos": getattr(self, "_last_ui_cursor_pos", None),
        }
    
    def render(self):
        """Render the game."""
        # Ursina viewer: 3D world is drawn by Ursina; pygame only composites HUD. Keep the
        # surface transparent where we skip drawing so the 3D layer shows through.
        skip_pygame_world = bool(
            getattr(self, "headless_ui", False)
            and getattr(self, "_ursina_skip_world_render", False)
        )
        if skip_pygame_world:
            self.screen.fill((0, 0, 0, 0))
        else:
            self.screen.fill(COLOR_BLACK)

        # Pixel art: quantize camera to integer pixels to reduce shimmer.
        camera_offset = (int(self.camera_x), int(self.camera_y))

        # Render-only context (do not affect simulation determinism).
        try:
            set_render_zoom(self.zoom if self.zoom else 1.0)
        except Exception:
            pass

        if skip_pygame_world:
            view_surface = self.screen
        elif abs((self.zoom if self.zoom else 1.0) - 1.0) < 1e-6:
            # If not zoomed, render directly to the screen to avoid an expensive smoothscale.
            view_surface = self.screen
        else:
            # Render world + entities to a zoomed "camera view" surface, then scale to window.
            win_w = int(self.window_width)
            win_h = int(self.window_height)
            view_w = max(1, int(win_w / (self.zoom if self.zoom else 1.0)))
            view_h = max(1, int(win_h / (self.zoom if self.zoom else 1.0)))
            if self._view_surface is None or self._view_surface_size != (view_w, view_h):
                self._view_surface = pygame.Surface((view_w, view_h))
                self._view_surface_size = (view_w, view_h)
            view_surface = self._view_surface
            view_surface.fill(COLOR_BLACK)

        if not skip_pygame_world:
            # Render world
            self.world.render(view_surface, camera_offset)

            # Render buildings
            for building in self.buildings:
                self.renderer_registry.render_building(view_surface, building, camera_offset)

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
                self.renderer_registry.render_enemy(view_surface, enemy, camera_offset)

            # Render heroes
            for hero in self.heroes:
                self.renderer_registry.render_hero(view_surface, hero, camera_offset)

            # Render guards
            for guard in self.guards:
                self.renderer_registry.render_guard(view_surface, guard, camera_offset)

            # Render peasants
            for peasant in self.peasants:
                self.renderer_registry.render_peasant(view_surface, peasant, camera_offset)

            # Render tax collector
            if self.tax_collector:
                self.renderer_registry.render_tax_collector(view_surface, self.tax_collector, camera_offset)

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
            self.renderer_registry.render_bounties(
                view_surface,
                getattr(self.bounty_system, "bounties", []),
                camera_offset,
            )

            # Scale the world to the actual window (reusing a destination surface)
            if view_surface is not self.screen:
                # Pixel art: nearest-neighbor scaling (no blur).
                win_w = int(self.window_width)
                win_h = int(self.window_height)
                try:
                    pygame.transform.scale(view_surface, (win_w, win_h), self._scaled_surface)
                    self.screen.blit(self._scaled_surface, (0, 0))
                except Exception as e:
                    raise
        else:
            # Bounty UI metrics still used by HUD/minimap; keep in sync without drawing world layers.
            if hasattr(self.bounty_system, "update_ui_metrics"):
                try:
                    self.bounty_system.update_ui_metrics(self.heroes, self.enemies, self.buildings)
                except Exception:
                    pass

        # Render HUD
        if not bool(getattr(self, "screenshot_hide_ui", False)):
            self.hud.render(self.screen, self.get_game_state())
            # wk14: If we transitioned out of interior (e.g. building destroyed), restore outdoor ambient
            from game.ui.micro_view_manager import ViewMode
            prev = getattr(self, "_previous_micro_view_mode", None)
            now_mode = getattr(self.micro_view, "mode", None)
            if prev == ViewMode.INTERIOR and now_mode != ViewMode.INTERIOR and self.audio_system is not None:
                self.audio_system.stop_interior_ambient()
            self._previous_micro_view_mode = now_mode

            # WK18: Hero Focus Minimap
            if now_mode == ViewMode.HERO_FOCUS and getattr(self.micro_view, "quest_hero", None):
                right_rect = getattr(self.hud, "_right_rect", None)
                if right_rect:
                    minimap_rect = pygame.Rect(
                        right_rect.x, right_rect.y, right_rect.width, right_rect.height // 2
                    )
                    self._render_hero_minimap(self.screen, minimap_rect, self.micro_view.quest_hero)

            # Render debug panel
            self.debug_panel.render(self.screen, self.get_game_state())
            # WK18: Dev Tools overlay (AI/LLM log stream)
            self.dev_tools_panel.render(self.screen)

            # Render building panel
            self.building_panel.render(self.screen, self.heroes, self.economy)
            
            # WK7: Render build catalog panel (castle-driven)
            if self.build_catalog_panel.visible:
                self.build_catalog_panel.render(self.screen, self.economy, self.buildings)

            # WK7: Pause menu (rendered before pause overlay)
            if self.pause_menu.visible:
                # Keep modal geometry in sync with the actual HUD surface (Ursina resizes can
                # otherwise leave page_buttons rects misaligned vs mouse for hover/hit-test).
                try:
                    sw, sh = self.screen.get_size()
                    if int(self.pause_menu.screen_width) != int(sw) or int(self.pause_menu.screen_height) != int(sh):
                        self.pause_menu.on_resize(sw, sh)
                except Exception:
                    pass
                # Prefer live input_manager coords (matches Ursina get_mouse_pos mapping) over
                # last-event cursor so hover matches the pointer when the menu is open.
                mp = None
                if getattr(self, "input_manager", None) is not None:
                    try:
                        mp = self.input_manager.get_mouse_pos()
                    except Exception:
                        mp = None
                if mp is not None and len(mp) >= 2:
                    self._last_ui_cursor_pos = (int(mp[0]), int(mp[1]))
                    self.pause_menu.render(
                        self.screen, mouse_pos=(int(mp[0]), int(mp[1]))
                    )
                else:
                    gs_pm = self.get_game_state()
                    ucp = gs_pm.get("ui_cursor_pos")
                    if ucp is not None and len(ucp) >= 2:
                        self.pause_menu.render(
                            self.screen, mouse_pos=(int(ucp[0]), int(ucp[1]))
                        )
                    else:
                        self.pause_menu.render(self.screen)

            # Perf overlay (helps diagnose lag spikes)
            if self.show_perf:
                self.render_perf_overlay(self.screen)
            
            # Pause overlay (only show if paused but menu not visible)
            if self.paused and not self.pause_menu.visible:
                self.screen.blit(self._pause_overlay, (0, 0))
                if self._pause_font is None:
                    self._pause_font = pygame.font.Font(None, 72)
                text = self._pause_font.render("PAUSED", True, (255, 255, 255))
                win_w = int(self.window_width)
                win_h = int(self.window_height)
                text_rect = text.get_rect(center=(win_w // 2, win_h // 2))
                self.screen.blit(text, text_rect)
        
        # NOTE (WK7): On some Windows setups, rapid mode switches can intermittently crash inside
        # SDL/driver during flip(). update() has proven more robust in practice.
        if not getattr(self, "headless_ui", False):
            try:
                pygame.display.update()
            except Exception as e:
                raise


    def _render_hero_minimap(self, surface: pygame.Surface, rect: pygame.Rect, hero):
        """Render a secondary map view centered on a specific hero (WK18)."""
        from game.graphics.render_context import set_render_zoom
        from game.world import Visibility
        old_zoom = self.zoom if self.zoom else 1.0
        try:
            set_render_zoom(1.0)
        except Exception:
            pass

        if getattr(self, "_minimap_surface", None) is None or self._minimap_surface.get_size() != (rect.width, rect.height):
            self._minimap_surface = pygame.Surface((rect.width, rect.height))
        mini_surf = self._minimap_surface
        mini_surf.fill(COLOR_BLACK)

        cam_x = hero.x - rect.width / 2
        cam_y = hero.y - rect.height / 2
        camera_offset = (int(cam_x), int(cam_y))

        # Map contents
        self.world.render(mini_surf, camera_offset)
        for b in self.buildings:
            self.renderer_registry.render_building(mini_surf, b, camera_offset)
        for e in self.enemies:
            gx, gy = self.world.world_to_grid(getattr(e, "x", 0.0), getattr(e, "y", 0.0))
            if 0 <= gx < self.world.width and 0 <= gy < self.world.height:
                if self.world.visibility[gy][gx] == Visibility.VISIBLE:
                    self.renderer_registry.render_enemy(mini_surf, e, camera_offset)
        for h in self.heroes:
            self.renderer_registry.render_hero(mini_surf, h, camera_offset)
        for g in self.guards:
            self.renderer_registry.render_guard(mini_surf, g, camera_offset)
        for p in self.peasants:
            self.renderer_registry.render_peasant(mini_surf, p, camera_offset)
        if self.tax_collector:
            self.renderer_registry.render_tax_collector(mini_surf, self.tax_collector, camera_offset)
            
        if hasattr(self.world, "render_fog"):
            self.world.render_fog(mini_surf, camera_offset)

        # Border
        pygame.draw.rect(mini_surf, (100, 100, 100), mini_surf.get_rect(), 2)
        pygame.draw.rect(mini_surf, (40, 40, 40), mini_surf.get_rect().inflate(-4, -4), 1)

        surface.blit(mini_surf, (rect.x, rect.y))

        try:
            set_render_zoom(old_zoom)
        except Exception:
            pass

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

            ursina_ema = getattr(self, "_ursina_window_fps_ema", None)
            if getattr(self, "_ursina_viewer", False):
                lines = [
                    f"FPS (pygame/HUD path): {fps:0.1f}",
                    "3D GPU: use top-left Ursina fps counter (not this number).",
                ]
                if ursina_ema is not None:
                    lines.append(f"Ursina dt EMA ~FPS (rough): {float(ursina_ema):0.1f}")
                lines.extend(
                    [
                        f"Entities: heroes={heroes_alive} peasants={peasants_alive} guards={guards_alive} enemies={enemies_alive} (cap={MAX_ALIVE_ENEMIES})",
                        f"Loop ms (ema): events={self._perf_events_ms:0.2f} update={self._perf_update_ms:0.2f} render={self._perf_render_ms:0.2f}",
                        f"PF calls/s: {self._perf_pf_calls}  fails/s: {self._perf_pf_failures}  ms/s: {self._perf_pf_total_ms:0.1f}",
                    ]
                )
            else:
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
    
    def tick_simulation(self, dt: float) -> tuple[float, float]:
        """
        Advance the game simulation by one logical step.
        Returns a tuple of (events_ms, update_ms) for profiling.
        """
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

        self._camera_dt = dt
        sim_dt = dt * get_time_multiplier()

        t0 = time.perf_counter()
        self.handle_events()
        t1 = time.perf_counter()

        self.update(sim_dt)
        t2 = time.perf_counter()

        evt_ms = (t1 - t0) * 1000.0
        upd_ms = (t2 - t1) * 1000.0
        return evt_ms, upd_ms

    def render_pygame(self) -> float:
        """
        Execute the standard Pygame rendering pipeline and UI overlays.
        Returns render_ms for profiling.
        """
        t2 = time.perf_counter()
        self.render()
        t3 = time.perf_counter()
        return (t3 - t2) * 1000.0

    def run(self):
        """Main game loop for standard Pygame playback."""
        while self.running:
            if DETERMINISTIC_SIM:
                # Keep realtime pacing, but do not use wall-clock delta for simulation.
                self.clock.tick(FPS)
                dt = 1.0 / max(1, int(SIM_TICK_HZ))
            else:
                tick_ms = self.clock.tick(FPS)
                dt = tick_ms / 1000.0  # Delta time in seconds

            # Step 1: Simulate
            evt_ms, upd_ms = self.tick_simulation(dt)

            # Step 2: Render
            rnd_ms = self.render_pygame()

            # Perf timings (EMA). Diagnostic only: must not affect simulation state.
            if getattr(self, "show_perf", False):
                alpha = 0.12
                self._perf_events_ms = evt_ms if self._perf_events_ms <= 0 else (self._perf_events_ms * (1 - alpha) + evt_ms * alpha)
                self._perf_update_ms = upd_ms if self._perf_update_ms <= 0 else (self._perf_update_ms * (1 - alpha) + upd_ms * alpha)
                self._perf_render_ms = rnd_ms if self._perf_render_ms <= 0 else (self._perf_render_ms * (1 - alpha) + rnd_ms * alpha)
        
        pygame.quit()

