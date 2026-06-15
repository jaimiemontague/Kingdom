from __future__ import annotations

import os
from types import SimpleNamespace

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.graphics.renderers.registry import RendererRegistry
from game.graphics.vfx import VFXSystem
from game.sim.contracts import BossEncounterSnapshot, EliteEncounterSnapshot


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


def _make_rusk_enemy():
    return SimpleNamespace(
        entity_id="boss_rusk_blackbanner",
        enemy_type="bandit_lord",
        name="Rusk Blackbanner",
        x=110.0,
        y=88.0,
        size=18,
        hp=128.0,
        max_hp=180.0,
        is_alive=True,
        facing=1,
    )


def _make_rusk_snapshot(*, current_phase: str, current_phase_title: str) -> BossEncounterSnapshot:
    return BossEncounterSnapshot(
        boss_id="boss_rusk_blackbanner",
        boss_type="bandit_lord",
        name="Rusk Blackbanner",
        status="active",
        current_phase=current_phase,
        current_phase_title=current_phase_title,
        hp_pct=0.62,
        position=(110.0, 88.0),
        target_hero_id="wk141_hero",
        latest_telegraph=current_phase,
        memory_summaries=(),
    )


def _make_toll_taker_enemy():
    return SimpleNamespace(
        entity_id="elite_blackbanner_toll_taker",
        enemy_type="bandit",
        name="Blackbanner Toll-Taker",
        x=110.0,
        y=88.0,
        size=18,
        hp=80.0,
        max_hp=80.0,
        is_alive=True,
        facing=1,
    )


def _make_toll_taker_snapshot() -> EliteEncounterSnapshot:
    return EliteEncounterSnapshot(
        elite_id="elite_blackbanner_toll_taker",
        base_type="bandit",
        name="Blackbanner Toll-Taker",
        status="active",
        affixes=("banner_bearer", "ironhide"),
        position=(110.0, 88.0),
    )


def _render_rusk_frame(
    registry: RendererRegistry,
    vfx: VFXSystem,
    *,
    show_boss_marker: bool = True,
    telegraph_state: str = "none",
    current_phase_title: str = "Toll Banner",
) -> pygame.Surface:
    boss = _make_rusk_enemy()
    boss_snapshot = _make_rusk_snapshot(
        current_phase=current_phase_title.lower().replace(" ", "_"),
        current_phase_title=current_phase_title,
    )
    surface = pygame.Surface((240, 180))
    surface.fill((0, 0, 0))

    registry.render_enemy(
        surface,
        boss,
        (0.0, 0.0),
        boss_snapshot=boss_snapshot if show_boss_marker or telegraph_state != "none" else None,
    )

    if telegraph_state == "active":
        vfx.on_event(
            {
                "type": "boss_ability_telegraphed",
                "boss_id": "boss_rusk_blackbanner",
                "boss_type": "bandit_lord",
                "name": "Rusk Blackbanner",
                "ability_id": current_phase_title.lower().replace(" ", "_"),
                "ability_name": current_phase_title,
                "current_phase_title": current_phase_title,
                "telegraph_ms": 900,
                "resolve_at_ms": 1_900,
                "time_ms": 1_000,
            }
        )
    elif telegraph_state == "cleared":
        vfx.on_event(
            {
                "type": "boss_ability_resolved",
                "boss_id": "boss_rusk_blackbanner",
                "boss_type": "bandit_lord",
                "name": "Rusk Blackbanner",
                "ability_id": current_phase_title.lower().replace(" ", "_"),
                "ability_name": current_phase_title,
                "current_phase_title": current_phase_title,
                "time_ms": 1_900,
            }
        )

    if boss_snapshot is not None:
        vfx.render(
            surface,
            (0, 0),
            boss_encounters=(boss_snapshot,),
            visible_enemy_ids={"boss_rusk_blackbanner"},
            visible_enemy_dtos={"boss_rusk_blackbanner": boss},
        )
    else:
        vfx.render(surface, (0, 0))
    return surface


def _render_toll_taker_frame(
    registry: RendererRegistry,
    *,
    show_elite_marker: bool = True,
) -> pygame.Surface:
    elite = _make_toll_taker_enemy()
    elite_snapshot = _make_toll_taker_snapshot() if show_elite_marker else None
    surface = pygame.Surface((240, 180))
    surface.fill((0, 0, 0))

    registry.render_enemy(surface, elite, (0.0, 0.0), elite_snapshot=elite_snapshot)
    return surface


def test_rusk_blackbanner_marker_renders_crown_and_name_without_covering_hp_bar():
    registry = RendererRegistry()
    vfx = VFXSystem()

    plain = _render_rusk_frame(registry, vfx, show_boss_marker=False, telegraph_state="none")
    marked = _render_rusk_frame(registry, vfx, show_boss_marker=True, telegraph_state="none")

    crown_region = pygame.Rect(84, 50, 52, 24)
    name_region = pygame.Rect(70, 98, 80, 18)
    hp_bar_region = pygame.Rect(96, 72, 28, 4)

    assert _count_match(marked, crown_region, _is_gold) > _count_match(plain, crown_region, _is_gold)
    assert _count_match(marked, name_region, _is_gold) > _count_match(plain, name_region, _is_gold)
    assert _rect_pixels(plain, hp_bar_region) == _rect_pixels(marked, hp_bar_region)


def test_blackbanner_toll_taker_marker_renders_below_sprite_without_covering_hp_bar():
    registry = RendererRegistry()

    plain = _render_toll_taker_frame(registry, show_elite_marker=False)
    marked = _render_toll_taker_frame(registry, show_elite_marker=True)

    title_region = pygame.Rect(76, 98, 68, 26)
    hp_bar_region = pygame.Rect(96, 72, 28, 4)

    assert _count_match(marked, title_region, _is_gold) > _count_match(plain, title_region, _is_gold)
    assert _rect_pixels(plain, hp_bar_region) == _rect_pixels(marked, hp_bar_region)


@pytest.mark.parametrize("current_phase_title", ("Toll Banner", "Smoke Retreat"))
def test_blackbanner_phase_telegraph_draws_then_clears_after_resolve(current_phase_title: str):
    registry = RendererRegistry()
    vfx = VFXSystem()

    active = _render_rusk_frame(
        registry,
        vfx,
        telegraph_state="active",
        current_phase_title=current_phase_title,
    )
    cleared = _render_rusk_frame(
        registry,
        vfx,
        telegraph_state="cleared",
        current_phase_title=current_phase_title,
    )

    badge_region = pygame.Rect(82, 16, 76, 54)
    label_region = pygame.Rect(78, 42, 84, 22)

    assert _count_match(active, badge_region, _is_orange) > 0
    assert _count_match(active, label_region, _is_orange) > 0
    assert _count_match(active, badge_region, _is_orange) > _count_match(cleared, badge_region, _is_orange)
    assert _count_match(active, label_region, _is_orange) > _count_match(cleared, label_region, _is_orange)
