"""Economic building panel renderers."""

from __future__ import annotations

import pygame

from config import COLOR_GOLD, COLOR_GREEN, COLOR_UI_BORDER, COLOR_WHITE
from game.ui.building_renderers import render_occupants
from game.ui.widgets import Button, HPBar


def _request_live_hud_upload_for_ursina(panel) -> None:
    """Ursina skips GPU HUD refresh when a row-sampled CRC is unchanged; thin progress bars often miss samples."""
    eng = getattr(panel, "engine", None)
    if eng is not None:
        setattr(eng, "_ursina_hud_force_upload", True)


class EconomicPanelRenderer:
    """Renderer for marketplace, blacksmith, inn, and trading post."""

    def _render_construction_notice(self, panel, surface: pygame.Surface, y: int) -> int:
        under_construction = panel.font_normal.render("Status: UNDER CONSTRUCTION", True, (200, 200, 100))
        surface.blit(under_construction, (10, y))
        y += 25
        note = panel.font_small.render("Peasants must finish building it first.", True, (180, 180, 180))
        surface.blit(note, (10, y))
        y += 25
        return y

    def _render_marketplace(self, panel, surface: pygame.Surface, building, y: int, economy) -> int:
        if hasattr(building, "is_constructed") and not building.is_constructed:
            panel.research_button_rect = None
            return self._render_construction_notice(panel, surface, y)

        y = render_occupants(panel, surface, building, y)

        if hasattr(building, "potions_researched") and bool(building.potions_researched):
            researched = panel.font_normal.render("Healing Potions: RESEARCHED", True, COLOR_GREEN)
            surface.blit(researched, (10, y))
            y += 25
            potion_price = int(getattr(building, "potion_price", 20))
            detail = panel.font_small.render(
                f"Heroes can buy potions for ${potion_price} each",
                True,
                (180, 180, 180),
            )
            surface.blit(detail, (10, y))
            y += 20
            panel.research_button_rect = None
        else:
            not_researched = panel.font_normal.render("Healing Potions: Not Researched", True, (180, 180, 180))
            surface.blit(not_researched, (10, y))
            y += 25

            # If research is in progress, show progress bar instead of button (wk15)
            research_in_progress = getattr(building, "research_in_progress", False)
            research_progress = max(0.0, min(1.0, float(getattr(building, "research_progress", 0.0))))

            if research_in_progress and research_progress < 1.0:
                label = panel.font_small.render("Researching potions...", True, (200, 200, 180))
                surface.blit(label, (10, y))
                y += 18
                bar_rect = pygame.Rect(10, y, 200, 12)
                HPBar.render(
                    surface,
                    bar_rect,
                    research_progress,
                    1.0,
                    color_scheme={
                        "bg": (60, 60, 60),
                        "good": (100, 150, 200),
                        "warn": (220, 180, 90),
                        "bad": (220, 80, 80),
                        "border": (20, 20, 25),
                    },
                )
                _request_live_hud_upload_for_ursina(panel)
                panel.research_button_rect = None
                y += 22
            else:
                local_rect = pygame.Rect(10, y, 200, 30)
                can_afford = bool(economy.player_gold >= 100)
                button_text = "Research Potions ($100)" if can_afford else "Research Potions (Need $100)"
                button = Button(
                    rect=local_rect,
                    text=button_text,
                    font=panel.font_small,
                    enabled=can_afford,
                )
                hover = bool(panel.research_button_hovered and can_afford)
                mouse = pygame.mouse.get_pos() if hover else None
                button.render(
                    surface,
                    mouse_pos=mouse,
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
                panel.research_button_rect = pygame.Rect(
                    panel.panel_x + local_rect.x,
                    panel.panel_y + local_rect.y,
                    local_rect.width,
                    local_rect.height,
                )
                y += 40

        y += 10
        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (panel.panel_width - 10, y))
        y += 10

        items_title = panel.font_normal.render("Items for Sale:", True, COLOR_WHITE)
        surface.blit(items_title, (10, y))
        y += 22

        for item in building.get_available_items():
            line = panel.font_small.render(f"- {item['name']} - ${item['price']}", True, (180, 180, 180))
            surface.blit(line, (15, y))
            y += 16

        if hasattr(building, "potions_researched") and bool(building.potions_researched):
            potion_price = int(getattr(building, "potion_price", 20))
            potion_line = panel.font_small.render(f"- Healing Potion - ${potion_price}", True, COLOR_GREEN)
            surface.blit(potion_line, (15, y))
            y += 16

        return y

    def _render_blacksmith(self, panel, surface: pygame.Surface, building, y: int, economy) -> int:
        if hasattr(building, "is_constructed") and not building.is_constructed:
            return self._render_construction_notice(panel, surface, y)

        y = render_occupants(panel, surface, building, y)

        upgrades = panel.font_normal.render(
            f"Upgrades Sold: {int(getattr(building, 'upgrades_sold', 0))}",
            True,
            COLOR_WHITE,
        )
        surface.blit(upgrades, (10, y))
        y += 25

        info = panel.font_small.render("Research upgrades to unlock better gear", True, (180, 180, 180))
        surface.blit(info, (10, y))
        y += 20

        has_impl = callable(getattr(building, "research", None)) or any(
            callable(getattr(building, name, None))
            for name in ("research_upgrade", "research_weapon_upgrade", "research_armor_upgrade")
        )
        has_data = isinstance(getattr(building, "available_research", None), list)
        if not (has_impl and has_data):
            return y

        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (panel.panel_width - 10, y))
        y += 10

        options = []
        for item in getattr(building, "available_research", []) or []:
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            options.append(
                {
                    "key": name,
                    "label": name,
                    "cost": int(item.get("cost", 0) or 0),
                    "done": bool(item.get("researched", False)),
                }
            )

        for option in options:
            if option["done"]:
                done = panel.font_small.render(f"✓ {option['label']}", True, COLOR_GREEN)
                surface.blit(done, (15, y))
                y += 18
                continue

            research_in_progress = getattr(building, "research_in_progress", None)
            research_progress = max(0.0, min(1.0, float(getattr(building, "research_progress", 0.0))))
            
            if research_in_progress == option["key"] and research_progress < 1.0:
                label = panel.font_small.render(f"Researching {option['label']}...", True, (200, 200, 180))
                surface.blit(label, (10, y))
                y += 18
                bar_rect = pygame.Rect(10, y, 200, 12)
                HPBar.render(
                    surface,
                    bar_rect,
                    research_progress,
                    1.0,
                    color_scheme={
                        "bg": (60, 60, 60),
                        "good": (100, 150, 200),
                        "warn": (220, 180, 90),
                        "bad": (220, 80, 80),
                        "border": (20, 20, 25),
                    },
                )
                _request_live_hud_upload_for_ursina(panel)
                panel.blacksmith_research_rects[option["key"]] = pygame.Rect(0, 0, 0, 0)
                y += 22
                continue

            local_rect = pygame.Rect(10, y, panel.panel_width - 20, 24)
            can_afford = bool(economy.player_gold >= option["cost"])
            button_text = (
                f"Research: {option['label']} (${option['cost']})"
                if can_afford
                else f"Research: {option['label']} (Need ${option['cost']})"
            )
            button = Button(
                rect=local_rect,
                text=button_text,
                font=panel.font_small,
                enabled=can_afford,
            )
            hover = bool(panel.blacksmith_research_hovered == option["key"] and can_afford)
            mouse = pygame.mouse.get_pos() if hover else None
            button.render(
                surface,
                mouse_pos=mouse,
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
            panel.blacksmith_research_rects[option["key"]] = pygame.Rect(
                panel.panel_x + local_rect.x,
                panel.panel_y + local_rect.y,
                local_rect.width,
                local_rect.height,
            )
            y += local_rect.height + 8

        # Weapons & armor for sale (after research; shows what heroes can buy post-upgrade)
        if hasattr(building, "get_available_items"):
            pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (panel.panel_width - 10, y))
            y += 10
            sale_title = panel.font_normal.render("Weapons & armor for sale:", True, COLOR_WHITE)
            surface.blit(sale_title, (10, y))
            y += 22
            for item in building.get_available_items():
                name = item.get("name", "?")
                price = int(item.get("price", 0))
                extra = []
                if item.get("type") == "weapon" and "attack" in item:
                    extra.append(f"Atk {item['attack']}")
                if item.get("type") == "armor" and "defense" in item:
                    extra.append(f"Def {item['defense']}")
                suffix = f" ({', '.join(extra)})" if extra else ""
                line = panel.font_small.render(f"- {name} — ${price}{suffix}", True, (180, 180, 180))
                surface.blit(line, (15, y))
                y += 16
        return y

    def _render_inn(self, panel, surface: pygame.Surface, building, heroes: list, y: int) -> int:
        if hasattr(building, "is_constructed") and not building.is_constructed:
            return self._render_construction_notice(panel, surface, y)

        y = render_occupants(panel, surface, building, y)

        # Recovery rate (plan: 0.02 = 1 HP per second)
        recovery_text = panel.font_small.render(
            "Heals 1 HP per second",
            True,
            (180, 180, 180),
        )
        surface.blit(recovery_text, (10, y))
        y += 20

        # Gold earned from drinks (when Agent 05 wires it)
        drink_gold = int(getattr(building, "gold_earned_from_drinks", 0))
        drink_line = panel.font_small.render(
            f"Gold from drinks: ${drink_gold}",
            True,
            COLOR_GOLD,
        )
        surface.blit(drink_line, (10, y))
        y += 20
        return y

    def _render_trading_post(self, panel, surface: pygame.Surface, building, y: int) -> int:
        income = panel.font_normal.render(
            f"Total Income: ${int(getattr(building, 'total_income_generated', 0))}",
            True,
            COLOR_GOLD,
        )
        surface.blit(income, (10, y))
        y += 25
        info = panel.font_small.render(
            f"Generates ${int(getattr(building, 'income_amount', 0))} every {float(getattr(building, 'income_interval', 0.0)):.0f}s",
            True,
            (180, 180, 180),
        )
        surface.blit(info, (10, y))
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
        raw_building_type = getattr(building, "building_type", "")
        raw_building_type = getattr(raw_building_type, "value", raw_building_type)
        building_type = str(raw_building_type).strip().lower()
        if building_type.startswith("buildingtype.") and "." in building_type:
            building_type = building_type.split(".", 1)[1]
        if building_type == "marketplace":
            return self._render_marketplace(panel, surface, building, y, economy)
        if building_type == "blacksmith":
            return self._render_blacksmith(panel, surface, building, y, economy)
        if building_type == "inn":
            return self._render_inn(panel, surface, building, heroes, y)
        if building_type == "trading_post":
            return self._render_trading_post(panel, surface, building, y)
        return y
