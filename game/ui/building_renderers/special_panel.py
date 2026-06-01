"""Special building panel renderers."""

from __future__ import annotations

import pygame

from config import COLOR_GREEN, COLOR_RED, COLOR_UI_BORDER, COLOR_WHITE
from game.ui.widgets import Button, HPBar


class SpecialPanelRenderer:
    """Renderer for the palace."""

    def _render_palace(self, panel, surface: pygame.Surface, building, y: int, economy) -> int:
        level = panel.font_normal.render(
            f"Level: {int(getattr(building, 'level', 1))}/{int(getattr(building, 'max_level', 1))}",
            True,
            COLOR_WHITE,
        )
        surface.blit(level, (10, y))
        y += 25

        hp = panel.font_normal.render(
            f"HP: {int(getattr(building, 'hp', 0))}/{int(getattr(building, 'max_hp', 0))}",
            True,
            COLOR_WHITE,
        )
        surface.blit(hp, (10, y))
        y += 25

        bar_rect = pygame.Rect(10, y, panel.panel_width - 20, 12)
        HPBar.render(
            surface,
            bar_rect,
            int(getattr(building, "hp", 0)),
            int(getattr(building, "max_hp", 1)),
            color_scheme={
                "bg": (60, 60, 60),
                "good": COLOR_GREEN,
                "warn": (220, 180, 90),
                "bad": COLOR_RED,
                "border": COLOR_WHITE,
            },
        )
        y += 20

        capacity = panel.font_small.render(
            "Peasants: "
            f"{int(getattr(building, 'max_peasants', 0))} | "
            "Tax Collectors: "
            f"{int(getattr(building, 'max_tax_collectors', 0))} | "
            "Guards: "
            f"{int(getattr(building, 'max_palace_guards', 0))}",
            True,
            (180, 180, 180),
        )
        surface.blit(capacity, (10, y))
        y += 20

        panel.upgrade_button_rect = None
        can_upgrade = bool(callable(getattr(building, "can_upgrade", None)) and building.can_upgrade())
        if not can_upgrade:
            return y

        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (panel.panel_width - 10, y))
        y += 10

        upgrade_cost = int(building.get_upgrade_cost())
        local_rect = pygame.Rect(10, y, 200, 30)
        can_afford = bool(economy.player_gold >= upgrade_cost)
        button_text = (
            f"Upgrade to Level {int(building.level) + 1} (${upgrade_cost})"
            if can_afford
            else f"Upgrade (Need ${upgrade_cost})"
        )
        button = Button(
            rect=local_rect,
            text=button_text,
            font=panel.font_small,
            enabled=can_afford,
        )
        button.render(
            surface,
            mouse_pos=pygame.mouse.get_pos() if panel.upgrade_button_hovered else None,
            enabled=can_afford,
            bg_normal=(60, 120, 60) if can_afford else (80, 80, 80),
            bg_hover=(80, 150, 80),
            bg_pressed=(70, 140, 70),
            border_outer=(20, 20, 25),
            border_inner=(80, 80, 100),
            border_highlight=(107, 107, 132),
            text_color=COLOR_WHITE,
            text_disabled_color=(180, 180, 180),
        )
        panel.upgrade_button_rect = pygame.Rect(
            panel.panel_x + local_rect.x,
            panel.panel_y + local_rect.y - panel.menu_scroll_px,
            local_rect.width,
            local_rect.height,
        )
        y += local_rect.height + 10
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
        if building_type == "palace":
            return self._render_palace(panel, surface, building, y, economy)
        return y
