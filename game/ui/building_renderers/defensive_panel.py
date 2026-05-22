"""Defensive building panel renderers."""

from __future__ import annotations

import pygame

from config import COLOR_GREEN, COLOR_RED, COLOR_WHITE
from game.ui.widgets import HPBar


class DefensivePanelRenderer:
    """Renderer for guardhouse, ballista tower, and wizard tower."""

    def _render_hp_block(self, panel, surface: pygame.Surface, building, y: int) -> int:
        """Render current/max HP above type-specific stats (WK61-R5-BUG-001)."""
        hp = int(getattr(building, "hp", 0) or 0)
        max_hp = int(getattr(building, "max_hp", 0) or 0)
        hp_text = panel.font_normal.render(f"HP: {hp}/{max_hp}", True, COLOR_WHITE)
        surface.blit(hp_text, (10, y))
        y += 25

        bar_rect = pygame.Rect(10, y, panel.panel_width - 20, 12)
        HPBar.render(
            surface,
            bar_rect,
            hp,
            max(1, max_hp),
            color_scheme={
                "bg": (60, 60, 60),
                "good": COLOR_GREEN,
                "warn": (220, 180, 90),
                "bad": COLOR_RED,
                "border": COLOR_WHITE,
            },
        )
        y += 20
        return y

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
        y = self._render_hp_block(panel, surface, building, y)
        raw_building_type = getattr(building, "building_type", "")
        raw_building_type = getattr(raw_building_type, "value", raw_building_type)
        building_type = str(raw_building_type).strip().lower()
        if building_type.startswith("buildingtype.") and "." in building_type:
            building_type = building_type.split(".", 1)[1]
        if building_type == "guardhouse":
            return self._render_guardhouse(panel, surface, building, y)
        if building_type == "ballista_tower":
            return self._render_ballista_tower(panel, surface, building, y)
        if building_type == "wizard_tower":
            return self._render_wizard_tower(panel, surface, building, y)
        return y
