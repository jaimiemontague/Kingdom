from __future__ import annotations

import os
from types import SimpleNamespace

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.graphics.renderers.registry import RendererRegistry
from game.sim.contracts import EliteEncounterSnapshot


@pytest.fixture(autouse=True)
def _pygame_hygiene():
    pygame.init()
    pygame.font.init()
    pygame.display.set_mode((1, 1))
    try:
        yield
    finally:
        try:
            from game.graphics.enemy_sprites import EnemySpriteLibrary

            EnemySpriteLibrary._cache.clear()
        except Exception:
            pass
        try:
            pygame.display.quit()
        except Exception:
            pass
        try:
            pygame.quit()
        except Exception:
            pass


def _rect_pixels(surface: pygame.Surface, rect: pygame.Rect) -> tuple[tuple[int, int, int], ...]:
    clipped = rect.clip(surface.get_rect())
    pixels: list[tuple[int, int, int]] = []
    for y in range(clipped.top, clipped.bottom):
        for x in range(clipped.left, clipped.right):
            pixels.append(surface.get_at((x, y))[:3])
    return tuple(pixels)


def _count_match(surface: pygame.Surface, rect: pygame.Rect, predicate) -> int:
    return sum(1 for rgb in _rect_pixels(surface, rect) if predicate(rgb))


def _is_gold(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return r >= 180 and g >= 130 and b <= 140


def _make_elite_enemy():
    return SimpleNamespace(
        entity_id="elite-1",
        enemy_type="goblin",
        name="Skull-Banner Goblin",
        x=110.0,
        y=88.0,
        size=18,
        hp=80.0,
        max_hp=80.0,
        is_alive=True,
        facing=1,
    )


def _make_elite_snapshot():
    return EliteEncounterSnapshot(
        elite_id="elite-1",
        base_type="goblin",
        name="Skull-Banner Goblin",
        status="active",
        affixes=("banner_bearer", "ironhide"),
        position=(110.0, 88.0),
    )


def _render_elite_frame(
    registry: RendererRegistry,
    *,
    show_elite_marker: bool = True,
) -> pygame.Surface:
    elite = _make_elite_enemy()
    elite_snapshot = _make_elite_snapshot() if show_elite_marker else None
    surface = pygame.Surface((240, 180))
    surface.fill((0, 0, 0))

    registry.render_enemy(surface, elite, (0.0, 0.0), elite_snapshot=elite_snapshot)
    return surface


def test_elite_marker_renders_below_sprite_without_covering_hp_bar():
    registry = RendererRegistry()

    plain = _render_elite_frame(registry, show_elite_marker=False)
    marked = _render_elite_frame(registry, show_elite_marker=True)

    title_region = pygame.Rect(76, 98, 68, 26)
    hp_bar_region = pygame.Rect(96, 72, 28, 4)

    assert _count_match(marked, title_region, _is_gold) > _count_match(plain, title_region, _is_gold)
    assert _rect_pixels(plain, hp_bar_region) == _rect_pixels(marked, hp_bar_region)
