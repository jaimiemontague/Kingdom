"""Guild-style building panel renderer."""

from __future__ import annotations

import pygame

from config import COLOR_GOLD, COLOR_UI_BORDER, COLOR_WHITE


class GuildPanelRenderer:
    """Shared renderer for guild and dwelling buildings."""

    def render(
        self,
        panel,
        surface: pygame.Surface,
        building,
        heroes: list,
        y: int,
        economy,
    ) -> int:
        hero_info = panel.get_heroes_for_building(building, heroes)

        tax_text = panel.font_normal.render(
            f"Taxable Gold: ${int(getattr(building, 'stored_tax_gold', 0))}",
            True,
            COLOR_GOLD,
        )
        surface.blit(tax_text, (10, y))
        y += 25

        total_text = panel.font_normal.render(f"Total Heroes: {hero_info['total']}", True, COLOR_WHITE)
        surface.blit(total_text, (10, y))
        y += 25

        status_text = panel.font_small.render(
            f"Fighting: {len(hero_info['fighting'])} | Resting: {len(hero_info['resting'])} | Idle: {len(hero_info['idle'])}",
            True,
            (180, 180, 180),
        )
        surface.blit(status_text, (10, y))
        y += 20

        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (panel.panel_width - 10, y))
        y += 10

        resting_title = panel.font_normal.render("Heroes Resting:", True, COLOR_WHITE)
        surface.blit(resting_title, (10, y))
        y += 22

        if hero_info["resting"]:
            for index, hero in enumerate(hero_info["resting"][:5]):
                y = panel.render_hero_row(surface, hero, y, index)
        else:
            empty_text = panel.font_small.render("No heroes resting", True, (120, 120, 120))
            surface.blit(empty_text, (20, y))
            y += 18

        y += 10
        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (panel.panel_width - 10, y))
        y += 10

        all_title = panel.font_normal.render("All Guild Heroes:", True, COLOR_WHITE)
        surface.blit(all_title, (10, y))
        y += 22

        all_heroes = (
            hero_info["fighting"]
            + hero_info["idle"]
            + hero_info["moving"]
            + hero_info["resting"]
            + hero_info["other"]
        )

        for index, hero in enumerate(all_heroes[:6]):
            y = panel.render_hero_row(surface, hero, y, index)

        if len(all_heroes) > 6:
            more = panel.font_small.render(f"... and {len(all_heroes) - 6} more", True, (120, 120, 120))
            surface.blit(more, (20, y))
            y += 18

        return y
