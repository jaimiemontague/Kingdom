"""Defensive building panel renderers."""

from __future__ import annotations

import pygame

from config import COLOR_WHITE

from game.ui.building_renderers import render_hp_block


class DefensivePanelRenderer:
    """Renderer for the guardhouse."""

    def _render_hp_block(self, panel, surface: pygame.Surface, building, y: int) -> int:
        """Render current/max HP above type-specific stats (WK61-R5-BUG-001).

        WK124-T2: now delegates to the shared ``render_hp_block`` helper so all
        building families render HP identically.
        """
        return render_hp_block(panel, surface, building, y)

    def _render_guardhouse(self, panel, surface: pygame.Surface, building, y: int) -> int:
        guards = panel.font_normal.render(
            f"Guards Spawned: {int(getattr(building, 'guards_spawned', 0))}",
            True,
            COLOR_WHITE,
        )
        surface.blit(guards, (10, y))
        y += 25
        maximum = panel.font_small.render(
            f"Max Guards: {int(getattr(building, 'max_guards', 0))}",
            True,
            (180, 180, 180),
        )
        surface.blit(maximum, (10, y))
        y += 20
        return y

    def render(
        self,
        panel,
        surface: pygame.Surface,
        building,
        heroes: list,
        y: int,
        economy,
    ) -> int:
        y = self._render_hp_block(panel, surface, building, y)
        raw_building_type = getattr(building, "building_type", "")
        raw_building_type = getattr(raw_building_type, "value", raw_building_type)
        building_type = str(raw_building_type).strip().lower()
        if building_type.startswith("buildingtype.") and "." in building_type:
            building_type = building_type.split(".", 1)[1]
        if building_type == "guardhouse":
            return self._render_guardhouse(panel, surface, building, y)
        return y
