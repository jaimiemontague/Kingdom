from __future__ import annotations

import os
from types import SimpleNamespace

import pygame
import pytest

from game.entities.buildings.economic import Blacksmith, Marketplace
from game.entities.buildings.types import BuildingType
from game.ui.building_panel import BuildingPanel
from game.ui.building_renderers import PANEL_RENDERERS, get_panel_renderer
from game.ui.building_renderers.economic_panel import EconomicPanelRenderer


@pytest.mark.parametrize(
    ("building_type", "expected"),
    [
        (BuildingType.MARKETPLACE, "marketplace"),
        (BuildingType.BLACKSMITH, "blacksmith"),
        (BuildingType.INN, "inn"),
        (BuildingType.TRADING_POST, "trading_post"),
    ],
)
def test_economic_renderer_dispatches_enum_building_types(
    monkeypatch: pytest.MonkeyPatch,
    building_type: BuildingType,
    expected: str,
) -> None:
    renderer = EconomicPanelRenderer()
    calls = {"marketplace": 0, "blacksmith": 0, "inn": 0, "trading_post": 0}

    monkeypatch.setattr(
        renderer,
        "_render_marketplace",
        lambda panel, surface, building, y, economy: calls.__setitem__("marketplace", calls["marketplace"] + 1) or 101,
    )
    monkeypatch.setattr(
        renderer,
        "_render_blacksmith",
        lambda panel, surface, building, y, economy: calls.__setitem__("blacksmith", calls["blacksmith"] + 1) or 102,
    )
    monkeypatch.setattr(
        renderer,
        "_render_inn",
        lambda panel, surface, building, heroes, y: calls.__setitem__("inn", calls["inn"] + 1) or 103,
    )
    monkeypatch.setattr(
        renderer,
        "_render_trading_post",
        lambda panel, surface, building, y: calls.__setitem__("trading_post", calls["trading_post"] + 1) or 104,
    )

    result = renderer.render(
        panel=SimpleNamespace(),
        surface=None,
        building=SimpleNamespace(building_type=building_type),
        heroes=[],
        y=0,
        economy=SimpleNamespace(player_gold=0),
    )

    expected_result = {
        "marketplace": 101,
        "blacksmith": 102,
        "inn": 103,
        "trading_post": 104,
    }[expected]
    assert result == expected_result
    for key, value in calls.items():
        assert value == (1 if key == expected else 0)


def test_marketplace_is_registered_and_resolves_with_enum() -> None:
    assert "marketplace" in PANEL_RENDERERS
    assert isinstance(get_panel_renderer(BuildingType.MARKETPLACE), EconomicPanelRenderer)


@pytest.fixture
def _pygame_font_ready() -> None:
    # Keep UI rendering tests headless-friendly.
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.font.init()
    try:
        yield
    finally:
        pygame.font.quit()


def test_marketplace_panel_renders_research_button_for_enum_type(_pygame_font_ready: None) -> None:
    panel = BuildingPanel(800, 600)
    panel.visible = True
    panel.selected_building = Marketplace(0, 0)
    panel.selected_building.potions_researched = False
    panel.selected_building.is_constructed = True

    surface = pygame.Surface((800, 600))
    economy = SimpleNamespace(player_gold=250)

    panel.render(surface, heroes=[], economy=economy)

    assert panel.research_button_rect is not None


def test_blacksmith_panel_renders_research_rows_for_enum_type(_pygame_font_ready: None) -> None:
    panel = BuildingPanel(800, 600)
    panel.visible = True
    panel.selected_building = Blacksmith(0, 0)
    panel.selected_building.is_constructed = True

    surface = pygame.Surface((800, 600))
    economy = SimpleNamespace(player_gold=1_000)

    panel.render(surface, heroes=[], economy=economy)

    assert panel.blacksmith_research_rects
