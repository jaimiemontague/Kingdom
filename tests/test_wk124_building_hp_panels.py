"""WK124-T2 — Guild / Inn / Market building menus show HP (Agent 08).

Mirrors ``tests/test_wk61_r5_guardhouse_hp_panel.py``: construct the building,
select it on a ``BuildingPanel``, render, and assert the HP text color (COLOR_WHITE)
and HP bar color (COLOR_GREEN) appear in the clipped panel region.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pygame
import pytest

from config import COLOR_GREEN, COLOR_WHITE
from game.entities.buildings.economic import Inn, Marketplace
from game.entities.buildings.guilds import WarriorGuild
from game.ui.building_panel import BuildingPanel


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


def _render_and_clip(building) -> pygame.Surface:
    panel = BuildingPanel(1920, 1080)
    building.is_constructed = True
    panel.select_building(building, [])

    surface = pygame.Surface((1920, 1080))
    panel.render(surface, heroes=[], economy=SimpleNamespace(player_gold=0))

    return surface.subsurface(
        pygame.Rect(panel.panel_x, panel.panel_y, panel.panel_width, panel.panel_height)
    )


def test_guild_panel_shows_hp(_pygame_font_ready: None) -> None:
    clip = _render_and_clip(WarriorGuild(0, 0))
    assert _surface_has_color(clip, COLOR_WHITE)  # "HP: N/max" text
    assert _surface_has_color(clip, COLOR_GREEN)  # full HP bar


def test_inn_panel_shows_hp(_pygame_font_ready: None) -> None:
    clip = _render_and_clip(Inn(0, 0))
    assert _surface_has_color(clip, COLOR_WHITE)
    assert _surface_has_color(clip, COLOR_GREEN)


def test_marketplace_panel_shows_hp(_pygame_font_ready: None) -> None:
    clip = _render_and_clip(Marketplace(0, 0))
    assert _surface_has_color(clip, COLOR_WHITE)
    assert _surface_has_color(clip, COLOR_GREEN)
