"""Special building panel renderers."""

from __future__ import annotations

import pygame

from config import COLOR_GOLD, COLOR_GREEN, COLOR_RED, COLOR_UI_BORDER, COLOR_WHITE
from game.ui.widgets import Button, HPBar


class SpecialPanelRenderer:
    """Renderer for fairgrounds, library, royal gardens, and palace."""

    def _render_fairgrounds(self, panel, surface: pygame.Surface, building, y: int) -> int:
        tournaments = panel.font_normal.render(
            f"Tournaments: {int(getattr(building, 'total_tournaments', 0))}",
            True,
            COLOR_WHITE,
        )
        surface.blit(tournaments, (10, y))
        y += 25
        income = panel.font_small.render(
            f"Income per tournament: ${int(getattr(building, 'tournament_income', 0))}",
            True,
            COLOR_GOLD,
        )
        surface.blit(income, (10, y))
        y += 20
        info = panel.font_small.render(
            "Heroes nearby gain XP during tournaments",
            True,
            (180, 180, 180),
        )
        surface.blit(info, (10, y))
        y += 20
        return y

    def _render_library(self, panel, surface: pygame.Surface, building, y: int, economy) -> int:
        if hasattr(building, "is_constructed") and not building.is_constructed:
            uc = panel.font_normal.render("Status: UNDER CONSTRUCTION", True, (200, 200, 100))
            surface.blit(uc, (10, y))
            y += 25
            note = panel.font_small.render("Peasants must finish building it first.", True, (180, 180, 180))
            surface.blit(note, (10, y))
            y += 25
            return y

        researched_count = len(getattr(building, "researched_items", []))
        researched = panel.font_normal.render(f"Researched: {researched_count}", True, COLOR_WHITE)
        surface.blit(researched, (10, y))
        y += 25

        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (panel.panel_width - 10, y))
        y += 10

        title = panel.font_normal.render("Available Research:", True, COLOR_WHITE)
        surface.blit(title, (10, y))
        y += 22

        for item in getattr(building, "available_research", []):
            name = str(item.get("name", ""))
            cost = int(item.get("cost", 0))
            if bool(item.get("researched", False)):
                done = panel.font_small.render(f"✓ {name}", True, COLOR_GREEN)
                surface.blit(done, (15, y))
                y += 18
                continue

            local_rect = pygame.Rect(10, y, panel.panel_width - 20, 24)
            can_afford = bool(economy.player_gold >= cost)
            button_text = f"Research: {name} (${cost})" if can_afford else f"Research: {name} (Need ${cost})"
            button = Button(
                rect=local_rect,
                text=button_text,
                font=panel.font_small,
                enabled=can_afford,
            )
            hover = bool(panel.library_research_hovered == name and can_afford)
            button.render(
                surface,
                mouse_pos=pygame.mouse.get_pos() if hover else None,
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
            panel.library_research_rects[name] = pygame.Rect(
                panel.panel_x + local_rect.x,
                panel.panel_y + local_rect.y,
                local_rect.width,
                local_rect.height,
            )
            y += local_rect.height + 8
        return y

    def _render_royal_gardens(self, panel, surface: pygame.Surface, building, heroes: list, y: int) -> int:
        buffed = building.get_heroes_in_range(heroes)
        buffed_text = panel.font_normal.render(f"Heroes Buffed: {len(buffed)}", True, COLOR_WHITE)
        surface.blit(buffed_text, (10, y))
        y += 25
        attack_bonus = panel.font_small.render(
            f"Attack Bonus: +{int(getattr(building, 'buff_attack_bonus', 0))}",
            True,
            COLOR_GREEN,
        )
        surface.blit(attack_bonus, (10, y))
        y += 18
        defense_bonus = panel.font_small.render(
            f"Defense Bonus: +{int(getattr(building, 'buff_defense_bonus', 0))}",
            True,
            COLOR_GREEN,
        )
        surface.blit(defense_bonus, (10, y))
        y += 18
        range_text = panel.font_small.render(
            f"Buff Range: {int(getattr(building, 'buff_range', 0))}px",
            True,
            (180, 180, 180),
        )
        surface.blit(range_text, (10, y))
        y += 20
        return y

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
            panel.panel_y + local_rect.y,
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
        if building_type == "fairgrounds":
            return self._render_fairgrounds(panel, surface, building, y)
        if building_type == "library":
            return self._render_library(panel, surface, building, y, economy)
        if building_type == "royal_gardens":
            return self._render_royal_gardens(panel, surface, building, heroes, y)
        if building_type == "palace":
            return self._render_palace(panel, surface, building, y, economy)
        return y
