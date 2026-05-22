"""WK61 R5 — Guardhouse HP visible in selected building panel (Agent 08)."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pygame
import pytest

from config import COLOR_GREEN, COLOR_WHITE, GUARDHOUSE_MAX_HP
from game.entities.buildings.defensive import Guardhouse
from game.ui.building_panel import BuildingPanel
from game.ui.building_renderers.defensive_panel import DefensivePanelRenderer


@pytest.fixture
def _pygame_font_ready() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.font.init()
    try:
        yield
    finally:
        pygame.font.quit()


def _surface_has_color(surface: pygame.Surface, color: tuple[int, int, int]) -> bool:
    width, height = surface.get_size()
    for y in range(height):
        for x in range(width):
            if surface.get_at((x, y))[:3] == color:
                return True
    return False


def test_defensive_renderer_draws_guardhouse_hp(_pygame_font_ready: None) -> None:
    guardhouse = Guardhouse(0, 0)
    guardhouse.is_constructed = True
    guardhouse.hp = GUARDHOUSE_MAX_HP - 40
    guardhouse.max_hp = GUARDHOUSE_MAX_HP

    panel = SimpleNamespace(
        panel_width=224,
        font_normal=pygame.font.Font(None, 24),
        font_small=pygame.font.Font(None, 18),
    )
    surface = pygame.Surface((260, 180))

    renderer = DefensivePanelRenderer()
    y = renderer.render(panel, surface, guardhouse, [], 10, SimpleNamespace())

    assert y >= 55
    assert _surface_has_color(surface, COLOR_WHITE)
    assert _surface_has_color(surface, COLOR_GREEN)


def test_guardhouse_building_panel_shows_hp_and_demolish(_pygame_font_ready: None) -> None:
    panel = BuildingPanel(1920, 1080)
    guardhouse = Guardhouse(0, 0)
    guardhouse.is_constructed = True
    panel.select_building(guardhouse, [])

    surface = pygame.Surface((1920, 1080))
    panel.render(surface, heroes=[], economy=SimpleNamespace(player_gold=0))

    assert panel.demolish_button_rect is not None
    assert panel.demolish_button_rect.width > 0
    assert panel.demolish_button_rect.height > 0

    clip = surface.subsurface(
        pygame.Rect(panel.panel_x, panel.panel_y, panel.panel_width, panel.panel_height)
    )
    assert _surface_has_color(clip, COLOR_WHITE)
    assert _surface_has_color(clip, COLOR_GREEN)
