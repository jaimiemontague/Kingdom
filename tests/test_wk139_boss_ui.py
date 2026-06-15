"""WK139 boss status UI tests and screenshot proof."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from game.engine import GameEngine
from game.entities.enemy import Goblin, GoblinWarchief
from game.sim.contracts import BossEncounterSnapshot, EliteEncounterSnapshot
from game.sim.timebase import set_sim_now_ms
from game.systems.boss_encounter import BossEncounterSystem
from game.systems.protocol import SystemContext
from game.ui.hud import HUD


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _fake_snapshot_state(
    *,
    boss_snapshots: tuple[BossEncounterSnapshot, ...],
    elite_snapshots: tuple[EliteEncounterSnapshot, ...] = (),
) -> dict:
    boss_system = SimpleNamespace(
        get_active_boss_snapshots=lambda: boss_snapshots,
        get_active_boss_views=lambda: boss_snapshots,
        get_active_boss_encounters=lambda: boss_snapshots,
        get_active_elite_snapshots=lambda: elite_snapshots,
        get_active_elite_views=lambda: elite_snapshots,
        get_active_elites=lambda: elite_snapshots,
    )
    sim = SimpleNamespace(boss_encounter_system=boss_system)
    return {"sim": sim}


def _make_boss_snapshot(
    *,
    latest_telegraph: str = "rally",
    hp_pct: float = 0.42,
) -> BossEncounterSnapshot:
    return BossEncounterSnapshot(
        boss_id="boss_7",
        boss_type="goblin_warchief",
        name="The Goblin Warchief",
        status="active",
        current_phase="rally",
        current_phase_title="Rally",
        hp_pct=hp_pct,
        position=(128.0, 96.0),
        target_hero_id="h12",
        latest_telegraph=latest_telegraph,
    )


def _make_elite_snapshot() -> EliteEncounterSnapshot:
    return EliteEncounterSnapshot(
        elite_id="elite_9",
        base_type="goblin",
        name="Skull-Banner Goblin",
        status="active",
        affixes=("banner_bearer", "ironhide"),
        position=(64.0, 64.0),
    )


def test_boss_status_lines_show_name_phase_hp_telegraph_and_elite_hint():
    hud = HUD(1920, 1080)
    game_state = _fake_snapshot_state(
        boss_snapshots=(_make_boss_snapshot(),),
        elite_snapshots=(_make_elite_snapshot(),),
    )

    lines = hud._top_bar._boss_status_lines(game_state)

    assert lines[0][0] == "The Goblin Warchief"
    assert "Phase: Rally" in lines[1][0]
    assert "HP: 42%" in lines[1][0]
    assert "Tell: Rally" in lines[1][0]
    assert lines[2][0] == "Elites: 1 | banner/shield"


def test_boss_status_lines_fall_back_to_status_without_telegraph():
    hud = HUD(1920, 1080)
    game_state = _fake_snapshot_state(
        boss_snapshots=(_make_boss_snapshot(latest_telegraph="", hp_pct=1.0),),
    )

    lines = hud._top_bar._boss_status_lines(game_state)

    assert lines[0][0] == "The Goblin Warchief"
    assert "Phase: Rally" in lines[1][0]
    assert "HP: 100%" in lines[1][0]
    assert "Status: Active" in lines[1][0]
    assert len(lines) == 2


def test_boss_status_lines_hide_when_no_boss_or_elite():
    hud = HUD(1920, 1080)
    game_state = _fake_snapshot_state(boss_snapshots=())

    assert hud._top_bar._boss_status_lines(game_state) == ()


def _make_engine_with_boss_ui_state() -> GameEngine:
    engine = GameEngine(headless=True, headless_ui=True)
    boss_system = engine.sim.boss_encounter_system
    assert isinstance(boss_system, BossEncounterSystem)

    boss = GoblinWarchief(160.0, 160.0)
    elite = Goblin(220.0, 160.0)
    engine.sim.enemies.extend([boss, elite])

    boss_system.register_boss(boss, event_bus=engine.sim.event_bus, now_ms=1000)
    boss_system.register_elite(
        elite,
        affix_ids=("banner_bearer", "ironhide"),
        event_bus=engine.sim.event_bus,
        now_ms=1000,
    )

    boss.take_damage(30)
    set_sim_now_ms(2000)
    ctx = SystemContext(
        heroes=list(engine.sim.heroes),
        enemies=engine.sim.enemies,
        buildings=engine.sim.buildings,
        world=engine.sim.world,
        economy=engine.sim.economy,
        event_bus=engine.sim.event_bus,
        castle=next((b for b in engine.sim.buildings if getattr(b, "building_type", None) == "castle"), None),
    )
    boss_system.update(ctx, 1 / 60)
    return engine


def test_boss_status_panel_renders_and_saves_png():
    engine = _make_engine_with_boss_ui_state()
    game_state = engine.get_game_state()

    surface = pygame.Surface((1920, 1080), pygame.SRCALPHA)
    surface.fill((44, 58, 44))
    engine.hud.render(surface, game_state)

    out_dir = Path("docs/screenshots/wk139_boss_ui")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "wk139_boss_ui_telegraph_1920x1080.png"
    pygame.image.save(surface, out_path.as_posix())

    assert out_path.exists()
    assert engine.hud._top_bar._boss_status_lines(game_state)[1][0].startswith("Phase: Rally")
