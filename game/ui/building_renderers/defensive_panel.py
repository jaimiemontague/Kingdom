"""Defensive building panel renderers."""

from __future__ import annotations

import pygame

from config import COLOR_RED, COLOR_WHITE


class DefensivePanelRenderer:
    """Renderer for guardhouse, ballista tower, and wizard tower."""

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

    def _render_ballista_tower(self, panel, surface: pygame.Surface, building, y: int) -> int:
        range_text = panel.font_normal.render(
            f"Range: {int(getattr(building, 'attack_range', 0))}px",
            True,
            COLOR_WHITE,
        )
        surface.blit(range_text, (10, y))
        y += 25
        damage_text = panel.font_small.render(
            f"Damage: {int(getattr(building, 'attack_damage', 0))}",
            True,
            (180, 180, 180),
        )
        surface.blit(damage_text, (10, y))
        y += 20
        if getattr(building, "target", None):
            targeting = panel.font_small.render("Targeting enemy", True, COLOR_RED)
            surface.blit(targeting, (10, y))
            y += 20
        return y

    def _render_wizard_tower(self, panel, surface: pygame.Surface, building, y: int) -> int:
        spell_range = panel.font_normal.render(
            f"Spell Range: {int(getattr(building, 'spell_range', 0))}px",
            True,
            COLOR_WHITE,
        )
        surface.blit(spell_range, (10, y))
        y += 25
        damage = panel.font_small.render(
            f"Spell Damage: {int(getattr(building, 'spell_damage', 0))}",
            True,
            (180, 180, 180),
        )
        surface.blit(damage, (10, y))
        y += 20
        cooldown = panel.font_small.render(
            f"Cooldown: {float(getattr(building, 'spell_interval', 0.0)):.1f}s",
            True,
            (180, 180, 180),
        )
        surface.blit(cooldown, (10, y))
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
        building_type = str(getattr(building, "building_type", "") or "")
        if building_type == "guardhouse":
            return self._render_guardhouse(panel, surface, building, y)
        if building_type == "ballista_tower":
            return self._render_ballista_tower(panel, surface, building, y)
        if building_type == "wizard_tower":
            return self._render_wizard_tower(panel, surface, building, y)
        return y
