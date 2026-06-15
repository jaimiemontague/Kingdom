"""WK143 Ashwing dragon visuals pins.

These tests verify the renderer-only Dragon Hunt presentation: Ashwing's
phase/readability markers, the fire-breath cone telegraph, and the impact burst.
The render path must not mutate sim state.
"""

from __future__ import annotations

import os
from pathlib import Path
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


def _out_dir() -> Path:
    out_dir = Path("docs/screenshots/wk143_dragon_hunt_visuals")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _save(surface: pygame.Surface, name: str) -> Path:
    path = _out_dir() / name
    pygame.image.save(surface, path.as_posix())
    return path


def test_ashwing_procedural_dragon_sprite_clips_build_without_name_error(monkeypatch):
    from game.graphics import enemy_sprites as enemy_sprites_module

    monkeypatch.setattr(enemy_sprites_module, "load_png_frames", lambda *args, **kwargs: [])

    clips = enemy_sprites_module.EnemySpriteLibrary.clips_for("dragon", size=36)
    assert {"idle", "walk", "attack", "hurt", "dead"} <= set(clips)
    assert all(clip.frames for clip in clips.values())


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
    return r >= 185 and g >= 145 and b <= 140


def _is_orange(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return r >= 200 and 70 <= g <= 200 and b <= 140


def _is_hot_red(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return r >= 215 and g <= 130 and b <= 120


def _make_hero(*, hero_id: str = "wk143_hero", x: float = 156.0, y: float = 88.0):
    return SimpleNamespace(
        hero_id=hero_id,
        name="Astra",
        x=x,
        y=y,
        is_alive=True,
    )


def _make_dragon(*, x: float = 110.0, y: float = 88.0, hero=None):
    hero = hero or _make_hero()
    return SimpleNamespace(
        entity_id="boss-ashwing",
        enemy_type="dragon",
        name="Ashwing the Red",
        x=x,
        y=y,
        size=36,
        hp=390.0,
        max_hp=650.0,
        is_alive=True,
        facing=1,
        is_boss=True,
        boss_type="dragon",
        boss_status="active",
        current_boss_phase="air_and_fire",
        current_boss_phase_title="Air And Fire",
        boss_phase="air_and_fire",
        boss_phase_title="Air And Fire",
        latest_telegraph="fire_breath",
        latest_boss_telegraph="fire_breath",
        current_boss_ability_id="ashwing_fire_breath",
        current_boss_ability_name="Fire Breath",
        current_boss_ability_trigger="cooldown",
        current_boss_ability_cooldown_ms=9_000,
        current_boss_ability_telegraph_ms=1_400,
        current_boss_ability_payload={
            "shape": "cone",
            "range": 9.0,
            "angle_degrees": 60.0,
            "warning_event": "dragon_fire_telegraph",
            "impact_event": "dragon_fire_impact",
            "telegraph_id": "fire_breath",
        },
        target=hero,
    )


def _make_snapshot(*, phase_title: str, hero_id: str, latest_telegraph: str = "fire_breath") -> BossEncounterSnapshot:
    return BossEncounterSnapshot(
        boss_id="boss-ashwing",
        boss_type="dragon",
        name="Ashwing the Red",
        status="active",
        current_phase=phase_title.lower().replace(" ", "_"),
        current_phase_title=phase_title,
        hp_pct=0.6,
        position=(110.0, 88.0),
        target_hero_id=hero_id,
        latest_telegraph=latest_telegraph,
        memory_summaries=(),
    )


def _render_dragon_frame(
    registry: RendererRegistry,
    vfx: VFXSystem,
    *,
    phase_title: str,
    telegraph_state: str,
    hero_x: float = 156.0,
    hero_y: float = 88.0,
    show_boss_marker: bool = True,
) -> tuple[pygame.Surface, SimpleNamespace, SimpleNamespace]:
    hero = _make_hero(x=hero_x, y=hero_y)
    dragon = _make_dragon(hero=hero)
    dragon_snapshot = _make_snapshot(phase_title=phase_title, hero_id=hero.hero_id)
    surface = pygame.Surface((240, 180))
    surface.fill((0, 0, 0))

    before = dict(dragon.__dict__)
    registry.render_enemy(
        surface,
        dragon,
        (0.0, 0.0),
        boss_snapshot=dragon_snapshot if show_boss_marker else None,
    )

    if telegraph_state == "active":
        vfx.on_event(
            {
                "type": "boss_ability_telegraphed",
                "boss_id": dragon.entity_id,
                "boss_type": "dragon",
                "name": dragon.name,
                "ability_id": "ashwing_fire_breath",
                "ability_name": "Fire Breath",
                "current_phase_title": phase_title,
                "telegraph_ms": 1_400,
                "resolve_at_ms": 2_400,
                "detail": "dragon_fire_telegraph",
                "time_ms": 1_000,
            }
        )
    elif telegraph_state == "resolved":
        vfx.on_event(
            {
                "type": "boss_ability_telegraphed",
                "boss_id": dragon.entity_id,
                "boss_type": "dragon",
                "name": dragon.name,
                "ability_id": "ashwing_fire_breath",
                "ability_name": "Fire Breath",
                "current_phase_title": phase_title,
                "telegraph_ms": 1_400,
                "resolve_at_ms": 2_400,
                "detail": "dragon_fire_telegraph",
                "time_ms": 1_000,
            }
        )
        vfx.on_event(
            {
                "type": "boss_ability_resolved",
                "boss_id": dragon.entity_id,
                "boss_type": "dragon",
                "name": dragon.name,
                "ability_id": "ashwing_fire_breath",
                "ability_name": "Fire Breath",
                "current_phase_title": phase_title,
                "detail": "dragon_fire_impact",
                "impact_event": "dragon_fire_impact",
                "time_ms": 2_400,
            }
        )

    vfx.render(
        surface,
        (0.0, 0.0),
        boss_encounters=(dragon_snapshot,),
        visible_enemy_ids={"boss-ashwing"},
        visible_enemy_dtos={"boss-ashwing": dragon},
        hero_dtos=(hero,),
    )

    assert before == dragon.__dict__, "rendering must not mutate the live dragon DTO"
    return surface, dragon, hero


def test_ashwing_phase_aura_reads_as_hoard_then_fire_without_mutating_state():
    registry = RendererRegistry()
    vfx = VFXSystem()

    plain, _, _ = _render_dragon_frame(
        registry,
        vfx,
        phase_title="Sleeping Hoard",
        telegraph_state="none",
        show_boss_marker=False,
    )
    hoard, _, _ = _render_dragon_frame(
        registry,
        vfx,
        phase_title="Sleeping Hoard",
        telegraph_state="none",
    )
    fire, _, _ = _render_dragon_frame(
        registry,
        vfx,
        phase_title="Air And Fire",
        telegraph_state="none",
    )

    aura_region = pygame.Rect(70, 40, 90, 72)
    assert _count_match(hoard, aura_region, _is_gold) > _count_match(plain, aura_region, _is_gold)
    assert _count_match(fire, aura_region, _is_orange) > _count_match(hoard, aura_region, _is_orange)

    _save(hoard, "wk143_dragon_hoard_phase.png")
    _save(fire, "wk143_dragon_fire_phase.png")


def test_ashwing_fire_telegraph_draws_cone_and_impact_burst_then_clears():
    registry = RendererRegistry()
    vfx = VFXSystem()

    active, _, _ = _render_dragon_frame(
        registry,
        vfx,
        phase_title="Air And Fire",
        telegraph_state="active",
    )
    resolved, dragon, hero = _render_dragon_frame(
        registry,
        vfx,
        phase_title="Air And Fire",
        telegraph_state="resolved",
    )
    vfx.update(1.0)
    cleared_surface = pygame.Surface((240, 180))
    cleared_surface.fill((0, 0, 0))
    boss_snapshot = _make_snapshot(phase_title="Air And Fire", hero_id=hero.hero_id, latest_telegraph="")
    vfx.render(
        cleared_surface,
        (0.0, 0.0),
        boss_encounters=(boss_snapshot,),
        visible_enemy_ids={dragon.entity_id},
        visible_enemy_dtos={dragon.entity_id: dragon},
        hero_dtos=(hero,),
    )

    cone_region = pygame.Rect(120, 70, 40, 36)
    impact_region = pygame.Rect(146, 74, 26, 26)

    assert _count_match(active, cone_region, _is_orange) > 0
    assert _count_match(resolved, impact_region, _is_hot_red) > _count_match(active, impact_region, _is_hot_red)
    assert _count_match(cleared_surface, impact_region, _is_hot_red) == 0
    assert _count_match(cleared_surface, cone_region, _is_orange) == 0

    _save(active, "wk143_dragon_fire_telegraph.png")
    _save(resolved, "wk143_dragon_fire_impact.png")
