"""Per-domain building panel renderers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import pygame

from config import COLOR_GOLD, COLOR_RED, COLOR_WHITE

from .castle_panel import CastlePanelRenderer
from .defensive_panel import DefensivePanelRenderer
from .economic_panel import EconomicPanelRenderer
from .guild_panel import GuildPanelRenderer
from .special_panel import SpecialPanelRenderer
from .temple_panel import TemplePanelRenderer

if TYPE_CHECKING:
    from game.ui.building_panel import BuildingPanel


class BuildingDomainRenderer(Protocol):
    """Interface for building panel domain renderers."""

    def render(
        self,
        panel: "BuildingPanel",
        surface: pygame.Surface,
        building,
        heroes: list,
        y: int,
        economy,
    ) -> int:
        ...


class GenericPanelRenderer:
    """Fallback renderer for unsupported building types."""

    def render(
        self,
        panel: "BuildingPanel",
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
        y += 22

        if hasattr(building, "stored_tax_gold"):
            tax_text = panel.font_normal.render(
                f"Taxable Gold: ${int(getattr(building, 'stored_tax_gold', 0))}",
                True,
                COLOR_GOLD,
            )
            surface.blit(tax_text, (10, y))
            y += 22

        if getattr(building, "is_neutral", False):
            neutral = panel.font_small.render("Neutral building (auto-spawned)", True, (160, 160, 160))
            surface.blit(neutral, (10, y))
            y += 18

        if getattr(building, "is_under_attack", False):
            warning = panel.font_small.render("Status: UNDER ATTACK", True, COLOR_RED)
            surface.blit(warning, (10, y))
            y += 18
        return y


_guild_renderer = GuildPanelRenderer()
_temple_renderer = TemplePanelRenderer()
_economic_renderer = EconomicPanelRenderer()
_defensive_renderer = DefensivePanelRenderer()
_special_renderer = SpecialPanelRenderer()
_castle_renderer = CastlePanelRenderer()
_default_renderer = GenericPanelRenderer()

_GUILD_TYPES = {
    "warrior_guild",
    "ranger_guild",
    "rogue_guild",
    "wizard_guild",
    "gnome_hovel",
    "elven_bungalow",
    "dwarven_settlement",
}
_TEMPLE_TYPES = {
    "temple_agrela",
    "temple_dauros",
    "temple_fervus",
    "temple_krypta",
    "temple_krolm",
    "temple_helia",
    "temple_lunord",
}
_ECONOMIC_TYPES = {"marketplace", "blacksmith", "inn", "trading_post"}
_DEFENSIVE_TYPES = {"guardhouse", "ballista_tower", "wizard_tower"}
_SPECIAL_TYPES = {"fairgrounds", "library", "royal_gardens", "palace"}

PANEL_RENDERERS: dict[str, BuildingDomainRenderer] = {
    **{name: _guild_renderer for name in _GUILD_TYPES},
    **{name: _temple_renderer for name in _TEMPLE_TYPES},
    **{name: _economic_renderer for name in _ECONOMIC_TYPES},
    **{name: _defensive_renderer for name in _DEFENSIVE_TYPES},
    **{name: _special_renderer for name in _SPECIAL_TYPES},
    "castle": _castle_renderer,
}


def get_panel_renderer(building_type: str) -> BuildingDomainRenderer:
    """Return renderer instance for a building type."""
    key = normalize_building_type_key(building_type)
    return PANEL_RENDERERS.get(key, _default_renderer)


def normalize_building_type_key(building_type: object) -> str:
    """Normalize building type values for registry lookups."""
    raw = getattr(building_type, "value", building_type)
    text = str(raw).strip()
    if text.lower().startswith("buildingtype.") and "." in text:
        text = text.split(".", 1)[1]
    return text.lower()
