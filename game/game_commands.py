"""
WK38 Stage 3: command surface for input routing (decoupled from raw GameEngine type).

R2: explicit property/method forwarders to GameEngine; InputHandler uses `c` = commands only.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Protocol, Tuple, Union, runtime_checkable

if TYPE_CHECKING:
    from game.engine import GameEngine


@runtime_checkable
class GameCommands(Protocol):
    """
    Presentation-facing surface GameEngine implements via EngineBackedGameCommands.
    Subsystem objects are typed as Any; narrow in later refactors.
    """

    def _game_commands_impl(self) -> None: ...

    # Subsystems & shared state
    @property
    def economy(self) -> Any: ...
    @property
    def hud(self) -> Any: ...
    @property
    def input_manager(self) -> Any: ...
    @property
    def dev_tools_panel(self) -> Any: ...
    @property
    def pause_menu(self) -> Any: ...
    @property
    def building_menu(self) -> Any: ...
    @property
    def building_list_panel(self) -> Any: ...
    @property
    def building_panel(self) -> Any: ...
    @property
    def build_catalog_panel(self) -> Any: ...
    @property
    def micro_view(self) -> Any: ...
    @property
    def audio_system(self) -> Any: ...
    @property
    def debug_panel(self) -> Any: ...
    @property
    def world(self) -> Any: ...
    @property
    def buildings(self) -> Any: ...

    @property
    def running(self) -> bool: ...
    @running.setter
    def running(self, v: bool) -> None: ...
    @property
    def paused(self) -> bool: ...
    @paused.setter
    def paused(self, v: bool) -> None: ...
    @property
    def show_perf(self) -> bool: ...
    @show_perf.setter
    def show_perf(self, v: bool) -> None: ...
    @property
    def display_mode(self) -> str: ...
    @property
    def window_size(self) -> Any: ...
    @property
    def camera_x(self) -> float: ...
    @property
    def camera_y(self) -> float: ...
    @property
    def zoom(self) -> float: ...
    @property
    def selected_hero(self) -> Any: ...
    @selected_hero.setter
    def selected_hero(self, v: Any) -> None: ...
    @property
    def selected_building(self) -> Any: ...
    @selected_building.setter
    def selected_building(self, v: Any) -> None: ...
    @property
    def selected_peasant(self) -> Any: ...
    @selected_peasant.setter
    def selected_peasant(self, v: Any) -> None: ...

    # Engine-private hooks used from input
    @property
    def _skip_event_processing_frames(self) -> int: ...
    @_skip_event_processing_frames.setter
    def _skip_event_processing_frames(self, v: int) -> None: ...
    @property
    def _borderless_drag_active(self) -> bool: ...
    @_borderless_drag_active.setter
    def _borderless_drag_active(self, v: bool) -> None: ...
    @property
    def _borderless_drag_start_pos(self) -> Any: ...
    @_borderless_drag_start_pos.setter
    def _borderless_drag_start_pos(self, v: Any) -> None: ...
    @property
    def _borderless_drag_window_offset(self) -> Any: ...
    @_borderless_drag_window_offset.setter
    def _borderless_drag_window_offset(self, v: Any) -> None: ...
    @property
    def _last_ui_cursor_pos(self) -> Any: ...
    @_last_ui_cursor_pos.setter
    def _last_ui_cursor_pos(self, v: Any) -> None: ...
    @property
    def _speed_before_pause(self) -> Any: ...
    @_speed_before_pause.setter
    def _speed_before_pause(self, v: Any) -> None: ...
    @property
    def _perf_close_rect(self) -> Any: ...

    def get_game_state(self) -> Any: ...
    def apply_display_settings(
        self, display_mode: str, window_size: Union[Tuple[int, int], Any, None]
    ) -> None: ...
    def request_display_settings(
        self, display_mode: str, window_size: Optional[Tuple[int, int]] = None
    ) -> None: ...
    def zoom_by(self, factor: float) -> None: ...
    def try_hire_hero(self) -> None: ...
    def place_bounty(self) -> None: ...
    def center_on_castle(self, reset_zoom: bool = True) -> None: ...
    def apply_hud_pin_action(self, action: str) -> None: ...
    def place_building(self, *args: Any) -> None: ...
    def send_player_message(self, *args: Any) -> None: ...
    def capture_screenshot(self) -> None: ...
    def _cleanup_destroyed_buildings(self, *args: Any) -> None: ...
    def try_select_hero(self, pos: Any) -> bool: ...
    def try_select_tax_collector(self, pos: Any) -> bool: ...
    def try_select_guard(self, pos: Any) -> bool: ...
    def try_select_peasant(self, pos: Any) -> bool: ...
    def try_select_building(self, pos: Any) -> bool: ...


class EngineBackedGameCommands:
    """Delegate every access to the real GameEngine (R2: explicit, no __getattr__)."""

    __slots__ = ("_engine",)

    def __init__(self, engine: "GameEngine") -> None:
        object.__setattr__(self, "_engine", engine)

    def _game_commands_impl(self) -> None:
        return None

    @property
    def economy(self) -> Any:
        return self._engine.economy

    @property
    def hud(self) -> Any:
        return self._engine.hud

    @property
    def input_manager(self) -> Any:
        return self._engine.input_manager

    @property
    def dev_tools_panel(self) -> Any:
        return self._engine.dev_tools_panel

    @property
    def pause_menu(self) -> Any:
        return self._engine.pause_menu

    @property
    def building_menu(self) -> Any:
        return self._engine.building_menu

    @property
    def building_list_panel(self) -> Any:
        return self._engine.building_list_panel

    @property
    def building_panel(self) -> Any:
        return self._engine.building_panel

    @property
    def build_catalog_panel(self) -> Any:
        return self._engine.build_catalog_panel

    @property
    def micro_view(self) -> Any:
        return self._engine.micro_view

    @property
    def audio_system(self) -> Any:
        return self._engine.audio_system

    @property
    def debug_panel(self) -> Any:
        return self._engine.debug_panel

    @property
    def world(self) -> Any:
        return self._engine.world

    @property
    def buildings(self) -> Any:
        return self._engine.buildings

    @property
    def running(self) -> bool:
        return self._engine.running

    @running.setter
    def running(self, v: bool) -> None:
        self._engine.running = v

    @property
    def paused(self) -> bool:
        return self._engine.paused

    @paused.setter
    def paused(self, v: bool) -> None:
        self._engine.paused = v

    @property
    def show_perf(self) -> bool:
        return self._engine.show_perf

    @show_perf.setter
    def show_perf(self, v: bool) -> None:
        self._engine.show_perf = v

    @property
    def display_mode(self) -> str:
        return self._engine.display_mode

    @property
    def window_size(self) -> Any:
        return self._engine.window_size

    @property
    def camera_x(self) -> float:
        return self._engine.camera_x

    @property
    def camera_y(self) -> float:
        return self._engine.camera_y

    @property
    def zoom(self) -> float:
        return self._engine.zoom

    @property
    def selected_hero(self) -> Any:
        return self._engine.selected_hero

    @selected_hero.setter
    def selected_hero(self, v: Any) -> None:
        self._engine.selected_hero = v

    @property
    def selected_building(self) -> Any:
        return self._engine.selected_building

    @selected_building.setter
    def selected_building(self, v: Any) -> None:
        self._engine.selected_building = v

    @property
    def selected_peasant(self) -> Any:
        return self._engine.selected_peasant

    @selected_peasant.setter
    def selected_peasant(self, v: Any) -> None:
        self._engine.selected_peasant = v

    @property
    def _skip_event_processing_frames(self) -> int:
        return int(getattr(self._engine, "_skip_event_processing_frames", 0) or 0)

    @_skip_event_processing_frames.setter
    def _skip_event_processing_frames(self, v: int) -> None:
        self._engine._skip_event_processing_frames = v  # type: ignore[attr-defined]

    @property
    def _borderless_drag_active(self) -> bool:
        return self._engine._borderless_drag_active  # type: ignore[attr-defined]

    @_borderless_drag_active.setter
    def _borderless_drag_active(self, v: bool) -> None:
        self._engine._borderless_drag_active = v  # type: ignore[attr-defined]

    @property
    def _borderless_drag_start_pos(self) -> Any:
        return self._engine._borderless_drag_start_pos  # type: ignore[attr-defined]

    @_borderless_drag_start_pos.setter
    def _borderless_drag_start_pos(self, v: Any) -> None:
        self._engine._borderless_drag_start_pos = v  # type: ignore[attr-defined]

    @property
    def _borderless_drag_window_offset(self) -> Any:
        return self._engine._borderless_drag_window_offset  # type: ignore[attr-defined]

    @_borderless_drag_window_offset.setter
    def _borderless_drag_window_offset(self, v: Any) -> None:
        self._engine._borderless_drag_window_offset = v  # type: ignore[attr-defined]

    @property
    def _last_ui_cursor_pos(self) -> Any:
        return self._engine._last_ui_cursor_pos  # type: ignore[attr-defined]

    @_last_ui_cursor_pos.setter
    def _last_ui_cursor_pos(self, v: Any) -> None:
        self._engine._last_ui_cursor_pos = v  # type: ignore[attr-defined]

    @property
    def _speed_before_pause(self) -> Any:
        return getattr(self._engine, "_speed_before_pause", None)

    @_speed_before_pause.setter
    def _speed_before_pause(self, v: Any) -> None:
        self._engine._speed_before_pause = v  # type: ignore[attr-defined]

    @property
    def _perf_close_rect(self) -> Any:
        return self._engine._perf_close_rect  # type: ignore[attr-defined]

    def get_game_state(self) -> Any:
        return self._engine.get_game_state()

    def apply_display_settings(
        self, display_mode: str, window_size: Union[Tuple[int, int], Any, None]
    ) -> None:
        self._engine.apply_display_settings(display_mode, window_size)

    def request_display_settings(
        self, display_mode: str, window_size: Optional[Tuple[int, int]] = None
    ) -> None:
        self._engine.request_display_settings(display_mode, window_size)

    def zoom_by(self, factor: float) -> None:
        self._engine.zoom_by(factor)

    def try_hire_hero(self) -> None:
        self._engine.try_hire_hero()

    def place_bounty(self) -> None:
        self._engine.place_bounty()

    def center_on_castle(self, reset_zoom: bool = True) -> None:
        self._engine.center_on_castle(reset_zoom=reset_zoom)

    def apply_hud_pin_action(self, action: str) -> None:
        self._engine.apply_hud_pin_action(action)

    def place_building(self, *args: Any) -> None:
        self._engine.place_building(*args)

    def send_player_message(self, *args: Any) -> None:
        self._engine.send_player_message(*args)

    def capture_screenshot(self) -> None:
        self._engine.capture_screenshot()

    def _cleanup_destroyed_buildings(self, *args: Any, **kwargs: Any) -> None:
        self._engine._cleanup_destroyed_buildings(*args, **kwargs)  # type: ignore[attr-defined]

    def try_select_hero(self, pos: Any) -> bool:
        return self._engine.try_select_hero(pos)

    def try_select_tax_collector(self, pos: Any) -> bool:
        return self._engine.try_select_tax_collector(pos)

    def try_select_guard(self, pos: Any) -> bool:
        return self._engine.try_select_guard(pos)

    def try_select_peasant(self, pos: Any) -> bool:
        return self._engine.try_select_peasant(pos)

    def try_select_building(self, pos: Any) -> bool:
        return self._engine.try_select_building(pos)
