"""Castle building panel renderer."""

from __future__ import annotations

import pygame

from config import COLOR_RED, COLOR_GREEN, COLOR_WHITE
from game.ui.widgets import Button, HPBar


class CastlePanelRenderer:
    """Renderer for castle-specific panel content."""

    def render(
        self,
        panel,
        surface: pygame.Surface,
        building,
        heroes: list,
        y: int,
        economy,
    ) -> int:
        hp_text = panel.font_normal.render(
            f"HP: {int(getattr(building, 'hp', 0))}/{int(getattr(building, 'max_hp', 0))}",
            True,
            COLOR_WHITE,
        )
        surface.blit(hp_text, (10, y))
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

        alive_heroes = [hero for hero in heroes if hero.is_alive]
        total_text = panel.font_normal.render(f"Kingdom Heroes: {len(alive_heroes)}", True, COLOR_WHITE)
        surface.blit(total_text, (10, y))
        y += 25

        local_rect = pygame.Rect(10, y, panel.panel_width - 20, 32)
        button = Button(
            rect=local_rect,
            text="Build Buildings",
            font=panel.font_normal,
            enabled=True,
        )
        hover = bool(panel.build_catalog_button_hovered)
        button.render(
            surface,
            mouse_pos=pygame.mouse.get_pos() if hover else None,
            bg_normal=(60, 80, 100),
            bg_hover=(70, 100, 120),
            bg_pressed=(75, 105, 130),
            border_outer=(20, 20, 25),
            border_inner=(80, 80, 100),
            border_highlight=(107, 107, 132),
            text_color=COLOR_WHITE,
            text_shadow_color=(20, 20, 30),
        )
        panel.build_catalog_button_rect = pygame.Rect(
            panel.panel_x + local_rect.x,
            panel.panel_y + local_rect.y,
            local_rect.width,
            local_rect.height,
        )
        y += local_rect.height + 10
        return y
