"""
Presentation shell for the running match: window/pygame, main loop, HUD, audio, and VFX.

The architecture refactor (see ``.cursor/plans/master_plan_architecture_refactor.md``) calls this
role *PresentationLayer*. The public class name remains ``GameEngine`` for import compatibility
with existing code and tests; it composes :class:`game.sim_engine.SimEngine` (``self.sim``) for
all simulation state and ticking.
"""
import os
import time
import pygame
from typing import TYPE_CHECKING
from config import (
    WINDOW_WIDTH, WINDOW_HEIGHT, FPS, TILE_SIZE,
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
from game.game_commands import EngineCommandHub
from game.presentation.selection_state import SelectionState
from game.input_handler import InputHandler
from game.display_manager import DisplayManager
from game.building_factory import BuildingFactory
from game.cleanup_manager import CleanupManager
from game.events import EventBus, GameEventType
from game.logging import get_logger
from game.types import BountyType, HeroClass
from game.graphics.pygame_renderer import PygameRenderer, PygameWorldRenderContext
from game.graphics.renderers import RendererRegistry
from game.sim.timebase import get_time_multiplier, set_time_multiplier
from ai.context_builder import ContextBuilder

from game.input_manager import InputManager
from game.sim_engine import SimEngine
from game.engine_facades.camera_display import EngineCameraDisplay
from game.engine_facades.render_coordinator import EngineRenderCoordinator

if TYPE_CHECKING:
    from game.sim.snapshot import (
        PresentationFrameState,
        RenderSnapshot,
        SimStateSnapshot,
    )

class GameEngine:
    """
    PresentationLayer implementation: wraps ``SimEngine``, owns pygame display, input, HUD, and the
    main loop; sim logic lives on ``self.sim``.
    """
    
    def __init__(
        self,
        early_nudge_mode: str | None = None,
        input_manager: InputManager | None = None,
        headless: bool = False,
        headless_ui: bool = False,
        *,
        playtest_start: bool = False,
    ):
        self.headless = headless
        self.headless_ui = headless_ui
        self.playtest_start = bool(playtest_start) or os.environ.get("KINGDOM_PLAYTEST_START", "").strip() == "1"
        pygame.init()
        pygame.font.init()
        
        self.input_manager = input_manager

        # Stage 2: simulation core moved into SimEngine.
        self.sim = SimEngine(early_nudge_mode=early_nudge_mode)

        # WK63: Presentation-owned selection state (stores entity IDs, not object refs).
        self.selection = SelectionState()

        # Camera dt is presentation-owned (camera moves independently of sim tick rate).
        self._camera_dt = 0.0

        # Fixed-rate simulation accumulator (decouples sim Hz from render Hz).
        self._sim_accumulator = 0.0
        
        # Camera state (always needed for simulation coordinate queries)
        self.camera_x = 0
        self.camera_y = 0
        # Ursina: last floor-ray hit in sim pixels (see ursina_app._engine_screen_pos_for_pointer).
        # EditorCamera pans/orbits in world space; engine.camera_x/y follow the 2D scroll path — mixing
        # them breaks placement/selection unless we prefer this ray hit when present.
        self._ursina_pointer_world_sim: tuple[float, float] | None = None
        self.zoom = 1.0
        self.default_zoom = 1.0
        self.clock = pygame.time.Clock()
        self.running = True
        self.paused = False

        # Universal command/chat input (opened with Enter key)
        self._command_mode = False
        self._command_buffer = ""

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
        self._last_frame_sim_ticks = 0
        self._last_frame_dt_ms = 0.0
        self._sim_tick_counter = 0
        self._smoothness_frame_times: list[float] = []
        self._smoothness_max_frames = 300

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
            # Bootstrap window before EngineCameraDisplay exists (facades created after full UI init).
            self.display_manager.apply_settings(self.display_mode, self.window_size)
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
        
        # (Sim-owned state moved to self.sim; keep compat via property forwarding below.)

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
            self.building_panel = BuildingPanel(
                self.window_width,
                self.window_height,
                on_request_ursina_hud_upload=self._request_ursina_hud_upload,
            )
            self.pause_menu = PauseMenu(self.window_width, self.window_height, engine=self, audio_system=self.audio_system, difficulty_system=self.difficulty_system)
            self.build_catalog_panel = BuildCatalogPanel(self.window_width, self.window_height)
            self.input_handler = InputHandler(EngineCommandHub(self))
            self.cleanup_manager = CleanupManager(self)
            self.vfx_system = VFXSystem()
            self.event_bus.subscribe("*", self.audio_system.on_event)
            self.event_bus.subscribe("*", self.vfx_system.on_event)
            self.pygame_renderer = PygameRenderer(
                PygameWorldRenderContext(
                    renderer_registry=self.renderer_registry,
                    bounty_system=self.sim.bounty_system,
                    vfx_system=self.vfx_system,
                    building_menu=self.building_menu,
                    building_list_panel=self.building_list_panel,
                    economy=self.sim.economy,
                )
            )
            # WK37 Stage2: bridge sim HUD_MESSAGE events into UI toasts.
            self.event_bus.subscribe(GameEventType.HUD_MESSAGE, self._on_hud_message_event)
            # WK60: wave event toasts (prominent countdown banner)
            self.event_bus.subscribe("wave_incoming", self._on_wave_incoming_event)
            self.event_bus.subscribe("wave_cleared", self._on_wave_cleared_event)
            if hasattr(getattr(self, "hud", None), "_alert_watcher"):
                try:
                    self.hud._alert_watcher.subscribe(self.event_bus)
                except Exception:
                    pass
            # Start ambient loop on game start (audio only if present)
            if self.audio_system is not None:
                self.audio_system.set_ambient("ambient_loop", volume=0.4)
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
            self.pygame_renderer = None

        # Initialize starting buildings (pure simulation)
        self.sim.setup_initial_state()
        if self.playtest_start:
            from game.sim.playtest_quick_start import apply_playtest_quick_start

            apply_playtest_quick_start(self)
        # Presentation-owned camera framing is handled by setup_initial_state() wrapper.
        self._camera_display = EngineCameraDisplay(self)
        self._render_coordinator = EngineRenderCoordinator(self)

    def _request_ursina_hud_upload(self) -> None:
        """Ursina: mark pygame HUD buffer dirty so the GPU texture re-uploads (e.g. thin building-panel bars)."""
        setattr(self, "_ursina_hud_force_upload", True)

    def _on_hud_message_event(self, event: dict) -> None:
        """Presentation hook: render sim-emitted HUD toasts."""
        try:
            text = event.get("text") or event.get("message") or ""
            color = event.get("color") or (255, 255, 255)
            if text and hasattr(self, "hud") and self.hud:
                self.hud.add_message(str(text), tuple(color))
        except Exception:
            pass

    def _on_wave_incoming_event(self, event: dict) -> None:
        """WK60: Route wave_incoming event to HUD wave toast banner."""
        try:
            if hasattr(self, "hud") and self.hud:
                self.hud.on_wave_incoming(event)
        except Exception:
            pass

    def _on_wave_cleared_event(self, event: dict) -> None:
        """WK60: Route wave_cleared event to HUD wave toast banner."""
        try:
            if hasattr(self, "hud") and self.hud:
                self.hud.on_wave_cleared(event)
        except Exception:
            pass

    # ----- Universal command/chat input (Enter key) -----

    def toggle_command_mode(self) -> None:
        """Flip the command input mode on/off."""
        self._command_mode = not self._command_mode
        if self._command_mode:
            self._command_buffer = ""

    def process_command(self, text: str) -> None:
        """Handle a typed command or chat message from the universal input."""
        from game import console
        return console.process_command(self, text)

    # ---------------------------------------------------------------------
    # Stage 2: backward-compat property forwarding (engine.<x> -> sim.<x>)
    # ---------------------------------------------------------------------
    @property
    def world(self):
        return self.sim.world

    @property
    def event_bus(self):
        return self.sim.event_bus

    @property
    def buildings(self):
        return self.sim.buildings

    @buildings.setter
    def buildings(self, v):
        self.sim.buildings = v

    @property
    def heroes(self):
        return self.sim.heroes

    @heroes.setter
    def heroes(self, v):
        self.sim.heroes = v

    @property
    def enemies(self):
        return self.sim.enemies

    @enemies.setter
    def enemies(self, v):
        self.sim.enemies = v

    @property
    def bounties(self):
        return self.sim.bounties

    @bounties.setter
    def bounties(self, v):
        self.sim.bounties = v

    @property
    def peasants(self):
        return self.sim.peasants

    @peasants.setter
    def peasants(self, v):
        self.sim.peasants = v

    @property
    def guards(self):
        return self.sim.guards

    @guards.setter
    def guards(self, v):
        self.sim.guards = v

    @property
    def peasant_spawn_timer(self):
        return self.sim.peasant_spawn_timer

    @peasant_spawn_timer.setter
    def peasant_spawn_timer(self, v):
        self.sim.peasant_spawn_timer = v

    @property
    def combat_system(self):
        return self.sim.combat_system

    @property
    def economy(self):
        return self.sim.economy

    @property
    def spawner(self):
        return self.sim.spawner

    @property
    def lair_system(self):
        return self.sim.lair_system

    @property
    def neutral_building_system(self):
        return self.sim.neutral_building_system

    @property
    def buff_system(self):
        return self.sim.buff_system

    @property
    def difficulty_system(self):
        return self.sim.difficulty_system

    @property
    def wave_event_system(self):
        return self.sim.wave_event_system

    @property
    def building_factory(self):
        return self.sim.building_factory

    @property
    def bounty_system(self):
        return self.sim.bounty_system

    # --- WK63: Selection properties backed by SelectionState (ID-based lookup) ---

    @property
    def selected_hero(self):
        if self.selection.selected_hero_id is None:
            return None
        for h in self.sim.heroes:
            if h.hero_id == self.selection.selected_hero_id:
                return h
        self.selection.selected_hero_id = None  # stale reference
        return None

    @selected_hero.setter
    def selected_hero(self, v):
        if v is None:
            self.selection.clear_hero()
        else:
            self.selection.select_hero(v.hero_id)

    @property
    def selected_building(self):
        if self.selection.selected_building_id is None:
            return None
        for b in self.sim.buildings:
            if getattr(b, "entity_id", None) == self.selection.selected_building_id:
                return b
        self.selection.selected_building_id = None
        return None

    @selected_building.setter
    def selected_building(self, v):
        if v is None:
            self.selection.clear_building()
        else:
            self.selection.select_building(v.entity_id)

    @property
    def selected_enemy(self):
        if self.selection.selected_enemy_id is None:
            return None
        for e in self.sim.enemies:
            if getattr(e, "entity_id", None) == self.selection.selected_enemy_id:
                return e
        self.selection.selected_enemy_id = None
        return None

    @selected_enemy.setter
    def selected_enemy(self, v):
        if v is None:
            self.selection.clear_enemy()
        else:
            self.selection.select_enemy(v.entity_id)

    @property
    def selected_peasant(self):
        if self.selection.selected_peasant_id is None:
            return None
        for p in self.sim.peasants:
            if getattr(p, "entity_id", None) == self.selection.selected_peasant_id:
                return p
        self.selection.selected_peasant_id = None
        return None

    @selected_peasant.setter
    def selected_peasant(self, v):
        if v is None:
            self.selection.clear_peasant()
        else:
            self.selection.select_peasant(v.entity_id)

    @property
    def ai_controller(self):
        return self.sim.ai_controller

    @ai_controller.setter
    def ai_controller(self, v):
        self.sim.ai_controller = v

    @property
    def tax_collector(self):
        return self.sim.tax_collector

    @tax_collector.setter
    def tax_collector(self, v):
        self.sim.tax_collector = v

    # Sim time + early pacing nudge state (compat: tests and engine methods access these attrs)
    @property
    def _sim_now_ms(self):
        return self.sim._sim_now_ms

    @_sim_now_ms.setter
    def _sim_now_ms(self, v):
        self.sim._sim_now_ms = v

    @property
    def _early_nudge_elapsed_s(self):
        return self.sim._early_nudge_elapsed_s

    @_early_nudge_elapsed_s.setter
    def _early_nudge_elapsed_s(self, v):
        self.sim._early_nudge_elapsed_s = v

    @property
    def _early_nudge_tip_shown(self):
        return self.sim._early_nudge_tip_shown

    @_early_nudge_tip_shown.setter
    def _early_nudge_tip_shown(self, v):
        self.sim._early_nudge_tip_shown = v

    @property
    def _early_nudge_starter_bounty_done(self):
        return self.sim._early_nudge_starter_bounty_done

    @_early_nudge_starter_bounty_done.setter
    def _early_nudge_starter_bounty_done(self, v):
        self.sim._early_nudge_starter_bounty_done = v

    @property
    def _early_nudge_mode(self):
        return self.sim._early_nudge_mode

    @_early_nudge_mode.setter
    def _early_nudge_mode(self, v):
        self.sim._early_nudge_mode = v

    @property
    def _fog_revision(self) -> int:
        return int(getattr(self.sim, "_fog_revision", 0))

    @_fog_revision.setter
    def _fog_revision(self, v: int) -> None:
        self.sim._fog_revision = int(v)

    @property
    def _fog_revealers_snapshot(self):
        return getattr(self.sim, "_fog_revealers_snapshot", None)

    @_fog_revealers_snapshot.setter
    def _fog_revealers_snapshot(self, v) -> None:
        self.sim._fog_revealers_snapshot = v

    def _update_fog_of_war(self) -> None:
        """SimEngine owns the authoritative fog update; keep a thin wrapper for legacy call sites / profilers."""
        self.sim._update_fog_of_war()
        
    def setup_initial_state(self):
        """Backward-compat wrapper (Stage 2): sim owns initial state."""
        self.sim.setup_initial_state()
        try:
            castle = next((b for b in self.buildings if getattr(b, "building_type", None) == "castle"), None)
            self.center_on_castle(reset_zoom=True, castle=castle)
            self.clamp_camera()
        except Exception:
            pass
        
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
    
    def pointer_world_xy(self, screen_pos: tuple) -> tuple[float, float]:
        """Sim-world (px, py) under the HUD cursor; prefers Ursina floor-ray hit when valid."""
        wptr = getattr(self, "_ursina_pointer_world_sim", None)
        if wptr is not None and getattr(self, "_ursina_viewer", False):
            return float(wptr[0]), float(wptr[1])
        return self.screen_to_world(screen_pos[0], screen_pos[1])

    def try_select_hero(self, screen_pos: tuple) -> bool:
        """Try to select a hero at the given screen position. Returns True if selected."""
        from game.engine_facades import selection
        return selection.try_select_hero(self, screen_pos)

    def try_select_hero_at_world(self, wx: float, wy: float, radius: float = 24.0) -> bool:
        """Pick the closest live hero within ``radius`` px of world position (watch-card map — WK52)."""
        from game.engine_facades import selection
        return selection.try_select_hero_at_world(self, wx, wy, radius)

    def try_select_tax_collector(self, screen_pos: tuple) -> bool:
        """Try to select the tax collector at the given screen position. Returns True if selected. (wk16)"""
        from game.engine_facades import selection
        return selection.try_select_tax_collector(self, screen_pos)

    def try_select_guard(self, screen_pos: tuple) -> bool:
        """Try to select a guard at the given screen position. Returns True if selected."""
        from game.engine_facades import selection
        return selection.try_select_guard(self, screen_pos)

    def try_select_peasant(self, screen_pos: tuple) -> bool:
        """Try to select a peasant at the given screen position. Returns True if selected."""
        from game.engine_facades import selection
        return selection.try_select_peasant(self, screen_pos)

    def try_select_enemy(self, screen_pos: tuple) -> bool:
        """Try to select an enemy at the given screen position. Returns True if selected (WK61)."""
        from game.engine_facades import selection
        return selection.try_select_enemy(self, screen_pos)

    def try_ursina_select_unit_at_screen(self, screen_pos: tuple) -> bool:
        """Ursina-only screen-space unit pick (WK61-R4-BUG-002). Returns True if selected."""
        from game.engine_facades import selection
        return selection.try_ursina_select_unit_at_screen(self, screen_pos)

    def try_select_building(self, screen_pos: tuple) -> bool:
        """Try to select a building at the given screen position. Returns True if selected."""
        from game.engine_facades import selection
        return selection.try_select_building(self, screen_pos)

    def try_hire_hero(self):
        """Try to hire a hero from the selected guild building or auto-locate one."""
        from game.engine_facades import actions
        return actions.try_hire_hero(self)

    def place_building(self, grid_x: int, grid_y: int):
        """Place the selected building."""
        from game.engine_facades import actions
        return actions.place_building(self, grid_x, grid_y)

    def place_bounty(self):
        """Place a bounty at the current mouse position."""
        from game.engine_facades import actions
        return actions.place_bounty(self)

    def update(self, dt: float):
        """Update game state."""
        from game.engine_facades import lifecycle
        return lifecycle.update(self, dt)

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
        # WK68 R4 (finishes Move 5): build the conversation prompt context from the
        # read-only AiGameView (NO live sim/world/economy/engine), projected to the
        # legacy context shape ContextBuilder consumes.
        from ai.behaviors.view_compat import view_to_legacy_context

        context = ContextBuilder.build_hero_context(
            hero, view_to_legacy_context(self.sim.build_ai_view())
        )
        llm.request_conversation(hero.name, context, history, text)
        chat_panel.waiting_for_response = True
        self._last_chat_player_message = text

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
            tool_action = response_dict.get("tool_action")
            physical_committed = False
            if tool_action:
                from game.sim.direct_prompt_exec import apply_validated_direct_prompt_physical

                # WK68 R4 (finishes Move 5): the chat path consumes the read-only
                # AiGameView (NO live sim/world/economy/engine), not the live UI
                # state dict. build_ai_view exposes exactly the read + command
                # surface this path needs.
                ai_view = self.sim.build_ai_view()
                response_dict["action"] = tool_action
                physical_committed = bool(
                    apply_validated_direct_prompt_physical(
                        self.ai_controller,
                        hero_target,
                        response_dict,
                        ai_view,
                        player_message=getattr(self, "_last_chat_player_message", "") or "",
                        source="chat",
                    )
                )
            direct_feedback = {
                "tool_action": response_dict.get("tool_action"),
                "obey_defy": response_dict.get("obey_defy"),
                "interpreted_intent": response_dict.get("interpreted_intent"),
                "refusal_reason": response_dict.get("refusal_reason"),
                "safety_assessment": response_dict.get("safety_assessment"),
                "physical_committed": physical_committed,
            }
            chat_panel.receive_response(spoken, direct_feedback=direct_feedback)

    def _prepare_sim_and_camera(self, dt: float) -> bool:
        """Check pause/menu state and update camera. Returns True if sim should tick."""
        from game.engine_facades import lifecycle
        return lifecycle._prepare_sim_and_camera(self, dt)

    # -----------------------------------------------------------------------
    # WK62 Task C: Dead sim-era helpers removed.
    # The following methods were deleted because all authoritative sim logic
    # now lives in SimEngine.update():
    #   _update_ai_and_heroes, _apply_entity_separation,
    #   _update_world_systems, _update_peasants, _update_enemies,
    #   _update_guards, _spawn_enemies, _process_combat,
    #   _route_combat_events, _cleanup_after_combat, _process_bounties,
    #   _update_neutral_systems, _update_buildings
    # tools/ursina_frame_profiler.py references some of these and will need
    # updating to wrap SimEngine methods instead (follow-up ticket).
    # -----------------------------------------------------------------------

    def _update_render_animations(self, dt: float):
        """Advance render-only entity animation state."""
        from game.engine_facades import lifecycle
        return lifecycle._update_render_animations(self, dt)

    def _finalize_update(self, dt: float):
        """Finalize per-frame UI and VFX updates."""
        if self.headless:
            # Flush + VFX: headless sim/observers must still age projectiles so snapshots stay in sync
            # with the pygame path and Ursina (projectile positions depend on vfx.update).
            self._flush_event_bus()
            if self.vfx_system is not None and hasattr(self.vfx_system, "update"):
                try:
                    self.vfx_system.update(dt)
                except Exception:
                    pass
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
                get_logger(__name__).exception("VFX update/render failed")  # behavior unchanged; now observable

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
        # WK61-FEAT-002: Tick enemy ambient sounds (per-type growls/hisses/clatters).
        if self.audio_system is not None:
            try:
                self.audio_system.update_enemy_ambient(self.enemies)
            except Exception:
                pass  # Non-authoritative: never crash sim for audio
    
    def _cleanup_destroyed_buildings(self, emit_messages: bool = True):
        """Remove buildings at hp <= 0 (except castle) and clear references."""
        self.cleanup_manager.cleanup_destroyed_buildings(emit_messages=emit_messages)
    
    def apply_display_settings(self, display_mode: str, window_size: tuple[int, int] | None = None):
        """Apply display mode settings (fullscreen/borderless/windowed)."""
        return self._camera_display.apply_display_settings(display_mode, window_size)

    def screen_to_world(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        """Convert screen-space pixels to world-space pixels, accounting for zoom."""
        return self._camera_display.screen_to_world(screen_x, screen_y)

    def clamp_camera(self):
        """Clamp camera to world bounds given current zoom."""
        return self._camera_display.clamp_camera()

    def center_on_castle(self, reset_zoom: bool = True, castle=None):
        """Center camera on the castle; optionally reset zoom to the starting zoom."""
        return self._camera_display.center_on_castle(reset_zoom=reset_zoom, castle=castle)

    def center_camera_on_world_pos(self, world_x: float, world_y: float) -> None:
        """Snap presentation camera to center on world pixel coordinates (pygame + Ursina)."""
        self._camera_display.center_on_world_px(world_x, world_y)
        fn = getattr(self, "_ursina_recenter_fn", None)
        if callable(fn):
            try:
                fn(float(world_x), float(world_y))
            except Exception:
                pass
        setattr(self, "_ursina_hud_force_upload", True)

    def _find_hero_by_id(self, hero_id: str):
        for h in self.heroes:
            if str(getattr(h, "hero_id", "")) == str(hero_id):
                return h
        return None

    def apply_hud_pin_action(self, action: str) -> None:
        """WK51: Pin / unpin / recall (UI state + camera + selection only)."""
        from game.engine_facades import actions
        return actions.apply_hud_pin_action(self, action)

    def capture_screenshot(self):
        """Capture a screenshot to docs/screenshots/manual/ with timestamp filename."""
        return self._camera_display.capture_screenshot()

    def set_zoom(self, new_zoom: float):
        """Set zoom with clamping."""
        return self._camera_display.set_zoom(new_zoom)

    def zoom_by(self, factor: float):
        """Zoom in/out around the mouse cursor."""
        return self._camera_display.zoom_by(factor)

    def update_camera(self, dt: float):
        """Update camera position based on WASD + mouse edge scrolling."""
        return self._camera_display.update_camera(dt)

    def get_game_state(self) -> dict:
        """Get current game state for AI and UI.

        WK32: each entry in ``buildings`` has ``construction_progress`` in [0, 1] for staged build visuals;
        ``buildings_construction_progress`` matches ``buildings`` order for consumers that need parallel arrays.
        """
        gs = self.sim.get_game_state(
            screen_w=int(getattr(self, "window_width", WINDOW_WIDTH)),
            screen_h=int(getattr(self, "window_height", WINDOW_HEIGHT)),
            display_mode=getattr(self, "display_mode", "windowed"),
            window_size=getattr(self, "window_size", (WINDOW_WIDTH, WINDOW_HEIGHT)),
            placing_building_type=getattr(getattr(self, "building_menu", None), "selected_building", None),
            debug_ui=bool(getattr(getattr(self, "debug_panel", None), "visible", False)),
            micro_view_mode=getattr(getattr(self, "micro_view", None), "mode", None),
            micro_view_building=getattr(getattr(self, "micro_view", None), "interior_building", None),
            micro_view_quest_hero=getattr(getattr(self, "micro_view", None), "quest_hero", None),
            micro_view_quest_data=getattr(getattr(self, "micro_view", None), "quest_data", None),
            right_panel_rect=getattr(getattr(self, "hud", None), "_right_rect", None),
            llm_available=getattr(self.ai_controller, "llm_brain", None) is not None,
            ui_cursor_pos=getattr(self, "_last_ui_cursor_pos", None),
        )
        # WK63: Override selection state from presentation-owned SelectionState.
        gs["selected_hero"] = self.selected_hero
        gs["selected_building"] = self.selected_building
        gs["selected_peasant"] = self.selected_peasant
        gs["selected_enemy"] = self.selected_enemy
        # Recompute selected_hero_profile from updated selected_hero.
        _sel = gs["selected_hero"]
        if _sel is not None:
            _sel_id = str(getattr(_sel, "hero_id", "") or "")
            gs["selected_hero_profile"] = gs.get("hero_profiles_by_id", {}).get(_sel_id)
        else:
            gs["selected_hero_profile"] = None
        # Expose the presentation-layer engine for HUD command mode rendering.
        gs["engine"] = self
        return gs

    def build_snapshot(self) -> "RenderSnapshot":
        """Build a frozen snapshot of current SIM TRUTH for renderers (read-only).

        WK67 Move 4 / L6: this returns a ``RenderSnapshot`` carrying sim truth ONLY
        (entities/world/fog/economy/effects). Per-frame presentation state
        (camera/zoom/screen/paused/running/pause-menu/selection/blend/tick) is built
        separately by :meth:`build_presentation_frame` and the two are passed together
        to the renderer as ``renderer.update(render_snapshot, frame)``.
        """
        vfx_projectiles: tuple = ()
        if self.vfx_system is not None:
            # VFXSystem exposes get_active_projectiles() — there is no .active_projectiles attr;
            # using getattr(..., "active_projectiles", ()) made Ursina snapshots always empty.
            getter = getattr(self.vfx_system, "get_active_projectiles", None)
            if callable(getter):
                vfx_projectiles = tuple(getter())
            else:
                vfx_projectiles = tuple(getattr(self.vfx_system, "active_projectiles", ()))

        return self.sim.build_snapshot(vfx_projectiles=vfx_projectiles)

    def build_presentation_frame(self) -> "PresentationFrameState":
        """Build the per-frame presentation state from engine-owned state (WK67 Move 4).

        Camera/zoom/screen/pause/selection/blend/tick are presentation, not sim
        truth — they live here, not on the sim snapshot. Selection comes from the
        presentation-owned ``SelectionState`` (``self.selected_*``), exactly as the
        UI dict path resolves it (see :meth:`get_game_state`). Renderers read these
        via the ``frame`` arg of ``renderer.update(render_snapshot, frame)``.
        """
        from game.sim.snapshot import PresentationFrameState

        blend = 0.0
        if self._FIXED_SIM_DT > 0:
            blend = max(0.0, min(1.0, self._sim_accumulator / self._FIXED_SIM_DT))

        return PresentationFrameState(
            camera_x=float(getattr(self, "camera_x", 0.0) or 0.0),
            camera_y=float(getattr(self, "camera_y", 0.0) or 0.0),
            zoom=float(getattr(self, "zoom", 1.0) or 1.0),
            default_zoom=float(getattr(self, "default_zoom", 1.0) or 1.0),
            screen_w=int(getattr(self, "window_width", 0) or 0),
            screen_h=int(getattr(self, "window_height", 0) or 0),
            paused=bool(getattr(self, "paused", False)),
            running=bool(getattr(self, "running", True)),
            pause_menu_visible=bool(getattr(getattr(self, "pause_menu", None), "visible", False)),
            sim_blend_fraction=blend,
            sim_tick_id=self._sim_tick_counter,
            selected_hero=self.selected_hero,
            selected_building=self.selected_building,
        )

    def render(self):
        """Render the game."""
        return self._render_coordinator.render()

    def _render_hero_minimap(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        hero,
        snapshot: "SimStateSnapshot",
    ):
        """Render a secondary map view centered on a specific hero (WK18). Uses the same
        world draw path as :class:`PygameRenderer` via ``render_minimap_contents`` and the
        current frame ``SimStateSnapshot`` (no second sim query for entity lists).
        """
        return self._render_coordinator._render_hero_minimap(surface, rect, hero, snapshot)

    def render_perf_overlay(self, surface: pygame.Surface):
        return self._render_coordinator.render_perf_overlay(surface)

    # Fixed-rate simulation constants (decouples sim Hz from render Hz).
    _FIXED_SIM_DT = 1.0 / 20.0   # 50ms per sim tick (20 Hz sim rate)
    _MAX_TICKS_PER_FRAME = 4      # Safety cap: never run more than 4 ticks per render frame

    def tick_simulation(self, dt: float) -> tuple[float, float]:
        """
        Advance the game simulation using a fixed-rate accumulator loop.
        The sim runs at 20 Hz regardless of render frame rate; the accumulator
        carries leftover time to the next frame for natural interpolation.
        Returns a tuple of (events_ms, update_ms) covering ALL ticks this frame.
        """
        from game.engine_facades import lifecycle
        return lifecycle.tick_simulation(self, dt)

    def render_pygame(self) -> float:
        """
        Execute the standard Pygame rendering pipeline and UI overlays.
        Returns render_ms for profiling.
        """
        return self._render_coordinator.render_pygame()

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

# Public alias: ``GameEngine`` is the name used in imports and tests; refactor docs use "PresentationLayer".
PresentationLayer = GameEngine

