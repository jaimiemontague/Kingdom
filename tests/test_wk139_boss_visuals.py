from __future__ import annotations

import os
from types import SimpleNamespace

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.graphics.renderers.registry import RendererRegistry
from game.graphics.vfx import VFXSystem
from game.sim.contracts import BossEncounterSnapshot


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


def _is_orange(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return r >= 190 and 70 <= g <= 200 and b <= 130


def _make_boss_enemy():
    return SimpleNamespace(
        entity_id="boss-1",
        enemy_type="goblin_warchief",
        name="Warchief",
        x=110.0,
        y=88.0,
        size=18,
        hp=120.0,
        max_hp=120.0,
        is_alive=True,
        facing=1,
    )


def _make_boss_snapshot():
    return BossEncounterSnapshot(
        boss_id="boss-1",
        boss_type="goblin_warchief",
        name="Warchief",
        status="active",
        current_phase="war_banner",
        current_phase_title="War Banner",
        hp_pct=1.0,
        position=(110.0, 88.0),
        target_hero_id=None,
        latest_telegraph="rally",
        memory_summaries=(),
    )


def _render_boss_frame(
    registry: RendererRegistry,
    vfx: VFXSystem,
    *,
    show_boss_marker: bool = True,
    telegraph_state: str = "none",
) -> pygame.Surface:
    boss = _make_boss_enemy()
    boss_snapshot = _make_boss_snapshot() if show_boss_marker or telegraph_state != "none" else None
    surface = pygame.Surface((240, 180))
    surface.fill((0, 0, 0))

    registry.render_enemy(surface, boss, (0.0, 0.0), boss_snapshot=boss_snapshot)

    if telegraph_state == "active":
        vfx.on_event(
            {
                "type": "boss_ability_telegraphed",
                "boss_id": "boss-1",
                "boss_type": "goblin_warchief",
                "name": "Warchief",
                "ability_id": "rally",
                "ability_name": "Rally",
                "current_phase_title": "War Banner",
                "telegraph_ms": 900,
                "resolve_at_ms": 1900,
                "time_ms": 1000,
            }
        )
    elif telegraph_state == "cleared":
        vfx.on_event(
            {
                "type": "boss_ability_resolved",
                "boss_id": "boss-1",
                "boss_type": "goblin_warchief",
                "name": "Warchief",
                "ability_id": "rally",
                "ability_name": "Rally",
                "current_phase_title": "War Banner",
                "time_ms": 1900,
            }
        )

    if boss_snapshot is not None:
        vfx.render(
            surface,
            (0, 0),
            boss_encounters=(boss_snapshot,),
            visible_enemy_ids={"boss-1"},
            visible_enemy_dtos={"boss-1": boss},
        )
    else:
        vfx.render(surface, (0, 0))
    return surface


def test_boss_marker_renders_above_hp_bar_without_covering_it():
    registry = RendererRegistry()
    vfx = VFXSystem()

    plain = _render_boss_frame(registry, vfx, show_boss_marker=False, telegraph_state="none")
    marked = _render_boss_frame(registry, vfx, show_boss_marker=True, telegraph_state="none")

    crown_region = pygame.Rect(84, 50, 52, 24)
    hp_bar_region = pygame.Rect(96, 72, 28, 4)

    assert _count_match(marked, crown_region, _is_gold) > _count_match(plain, crown_region, _is_gold)
    assert _rect_pixels(plain, hp_bar_region) == _rect_pixels(marked, hp_bar_region)


def test_boss_telegraph_draws_then_clears_after_resolve():
    registry = RendererRegistry()
    vfx = VFXSystem()

    active = _render_boss_frame(registry, vfx, telegraph_state="active")
    cleared = _render_boss_frame(registry, vfx, telegraph_state="cleared")

    telegraph_region = pygame.Rect(86, 18, 48, 32)

    assert _count_match(active, telegraph_region, _is_orange) > 0
    assert _count_match(cleared, telegraph_region, _is_orange) == 0
