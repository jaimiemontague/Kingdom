"""
Right-panel state machine for overview vs interior view (wk13 Living Interiors).

Interior mode is UI-only; simulation continues unchanged.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

import pygame

from config import SPEED_SLOW
from game.sim.timebase import get_time_multiplier, set_time_multiplier

if TYPE_CHECKING:
    from game.entities.buildings.base import Building


class ViewMode(Enum):
    """Right panel content mode."""
    OVERVIEW = "overview"   # Hero panel / building summary / empty
    INTERIOR = "interior"   # Building interior (Enter Building)
    # QUEST = "quest"       # Sprint 3: remote exploration


class MicroViewManager:
    """
    Owns right-panel mode: OVERVIEW (default) or INTERIOR.
    Auto-slow on enter, restore on exit. Handles building destroyed while viewing.
    """

    def __init__(self) -> None:
        self.mode: ViewMode = ViewMode.OVERVIEW
        self.interior_building: Building | None = None
        self._previous_speed: float | None = None
        self._exit_message: str | None = None  # e.g. "Building destroyed!" for HUD

    def enter_interior(self, building: Building) -> None:
        """Switch to interior view for this building; auto-slow to SPEED_SLOW."""
        self._previous_speed = get_time_multiplier()
        set_time_multiplier(SPEED_SLOW)
        self.mode = ViewMode.INTERIOR
        self.interior_building = building
        self._exit_message = None

    def exit_interior(self, reason: str | None = None) -> None:
        """Return to OVERVIEW; restore previous speed; clear building. reason='destroyed' sets _exit_message."""
        if self._previous_speed is not None:
            set_time_multiplier(self._previous_speed)
            self._previous_speed = None
        if reason == "destroyed":
            self._exit_message = "Building destroyed!"
        self.mode = ViewMode.OVERVIEW
        self.interior_building = None

    def get_and_clear_exit_message(self) -> str | None:
        """Return and clear any exit message (for HUD.add_message)."""
        msg, self._exit_message = self._exit_message, None
        return msg

    def render(
        self,
        surface: pygame.Surface,
        right_rect: pygame.Rect,
        game_state: dict[str, Any],
        hud: Any,
        interior_panel: Any,
    ) -> str | None:
        """
        Draw right-panel content by mode. Returns message to show if we auto-exited (e.g. building destroyed).
        hud: HUD instance with _render_right_panel_overview(); interior_panel: InteriorViewPanel or None.
        """
        if self.mode == ViewMode.INTERIOR and self.interior_building is not None:
            if getattr(self.interior_building, "hp", 1) <= 0:
                self.exit_interior(reason="destroyed")
                return self.get_and_clear_exit_message()
            if interior_panel is not None and hasattr(interior_panel, "render"):
                interior_panel.render(
                    surface, right_rect, game_state, self.interior_building
                )
            else:
                # Placeholder until Agent 08 lands InteriorViewPanel
                pad = getattr(hud, "_right_panel_top_pad", lambda r: 8)(right_rect)
                font = getattr(hud.theme, "font_body", pygame.font.Font(None, 24))
                name = getattr(self.interior_building, "building_type", "Building").replace("_", " ").title()
                txt = font.render(f"Interior: {name}", True, (200, 200, 200))
                surface.blit(txt, (right_rect.x + 12, right_rect.y + pad))
            return None
        # OVERVIEW: delegate to HUD
        if hasattr(hud, "_render_right_panel_overview"):
            hud._render_right_panel_overview(surface, right_rect, game_state)
        return None

    def handle_click(self, mouse_pos: tuple[int, int], right_rect: pygame.Rect, interior_panel: Any) -> str | None:
        """
        Forward click to interior panel when in INTERIOR mode. Returns 'exit_interior' or None.
        """
        if self.mode != ViewMode.INTERIOR or not right_rect.collidepoint(mouse_pos):
            return None
        if interior_panel is not None and hasattr(interior_panel, "handle_click"):
            action = interior_panel.handle_click(mouse_pos, right_rect)
            if action == "exit_interior":
                return "exit_interior"
        return None
