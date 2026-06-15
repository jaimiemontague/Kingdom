"""WK143 Dragon Hunt showcase capture-scenario proof."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from game.engine import GameEngine
from game.sim.contracts import QuestChainHistorySummary, QuestChainPhaseSnapshot, QuestChainSnapshot
from game.ui.quest_view_panel import QuestViewPanel
from game.ui.theme import UITheme
from tools.screenshot_scenarios import get_scenario


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _out_dir() -> Path:
    out_dir = Path("docs/screenshots/wk143_dragon_hunt_showcase")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _save(surface: pygame.Surface, name: str) -> Path:
    path = _out_dir() / name
    pygame.image.save(surface, path.as_posix())
    return path


def _build_ashwing_chain_snapshot(
    *,
    hero_id: str = "wk143_hero",
    cave_position: tuple[float, float] = (448.0, 256.0),
) -> tuple[QuestChainSnapshot, SimpleNamespace]:
    chain_snapshot = QuestChainSnapshot(
        chain_id=143,
        chain_type="ashwings_hoard",
        name="Ashwing's Hoard",
        status="active",
        assigned_hero_id=hero_id,
        current_phase_id="prepare_hunt",
        current_phase_title="Prepare for Ashwing",
        current_objective_type="prepare_hunt",
        target_id="poi_dragon_cave",
        target_name="Dragon Cave",
        target_position=cave_position,
        phases=(
            QuestChainPhaseSnapshot(
                phase_id="scout_dragon_cave",
                title="Scout the Dragon Cave",
                objective_type="scout_location",
                status="completed",
                assigned_hero_id=hero_id,
                target_id="poi_dragon_cave",
                target_name="Dragon Cave",
                target_position=cave_position,
                history=(
                    QuestChainHistorySummary(
                        event="phase_started",
                        phase_id="scout_dragon_cave",
                        phase_title="Scout the Dragon Cave",
                        status="completed",
                        hero_id=hero_id,
                        target_id="poi_dragon_cave",
                        target_name="Dragon Cave",
                        target_position=cave_position,
                        at_ms=9_000,
                    ),
                    QuestChainHistorySummary(
                        event="phase_completed",
                        phase_id="scout_dragon_cave",
                        phase_title="Scout the Dragon Cave",
                        status="completed",
                        hero_id=hero_id,
                        target_id="poi_dragon_cave",
                        target_name="Dragon Cave",
                        target_position=cave_position,
                        at_ms=10_000,
                    ),
                ),
            ),
            QuestChainPhaseSnapshot(
                phase_id="prepare_hunt",
                title="Prepare for Ashwing",
                objective_type="prepare_hunt",
                status="active",
                assigned_hero_id=hero_id,
                target_id="poi_dragon_cave",
                target_name="Dragon Cave",
                target_position=cave_position,
                history=(
                    QuestChainHistorySummary(
                        event="phase_started",
                        phase_id="prepare_hunt",
                        phase_title="Prepare for Ashwing",
                        status="active",
                        hero_id=hero_id,
                        target_id="poi_dragon_cave",
                        target_name="Dragon Cave",
                        target_position=cave_position,
                        at_ms=11_000,
                    ),
                ),
            ),
            QuestChainPhaseSnapshot(
                phase_id="slay_ashwing",
                title="Slay Ashwing the Red",
                objective_type="slay_named_boss",
                status="upcoming",
                assigned_hero_id=hero_id,
                target_id="ashwing_the_red",
                target_name="Ashwing the Red",
                target_position=cave_position,
            ),
            QuestChainPhaseSnapshot(
                phase_id="claim_hoard",
                title="Claim Ashwing's Hoard",
                objective_type="claim_hoard",
                status="upcoming",
                assigned_hero_id=hero_id,
                target_id="ashwing_hoard",
                target_name="Ashwing's Hoard",
                target_position=cave_position,
            ),
        ),
        history=(
            QuestChainHistorySummary(
                event="chain_offered",
                status="offered",
                hero_id=hero_id,
                target_id="poi_dragon_cave",
                target_name="Dragon Cave",
                target_position=cave_position,
                at_ms=8_500,
            ),
            QuestChainHistorySummary(
                event="chain_accepted",
                status="active",
                hero_id=hero_id,
                target_id="poi_dragon_cave",
                target_name="Dragon Cave",
                target_position=cave_position,
                at_ms=9_500,
            ),
        ),
    )
    live_chain = SimpleNamespace(
        chain_id=143,
        chain_type="ashwings_hoard",
        reward_gold=520,
        facts={
            "boss_target_revealed": True,
            "boss_target_name": "Ashwing the Red",
            "boss_target_weakness_name": "Ashwing's fire",
            "boss_target_weakness_detail": "Prepare at the shrine before the hunt",
            "prep_target_name": "Shrine Ember Ward",
            "prep_target_story_name": "Shrine Ember Ward",
            "reward_item_name": "Dragonscale Armor",
            "reward_title": "Ashwing-Bane",
            "reward_memory_summary": "Claimed Ashwing's Hoard",
            "target_location_name": "Dragon Cave",
        },
    )
    return chain_snapshot, live_chain


def _dragon_hunt_game_state(chain_snapshot: QuestChainSnapshot, live_chain: SimpleNamespace) -> dict:
    hero = SimpleNamespace(hero_id="wk143_hero", name="Astra")
    quest_chain_system = SimpleNamespace(
        get_active_chain_snapshots=lambda: (chain_snapshot,),
        get_active_chain_views=lambda: (chain_snapshot,),
        get_active_chains=lambda: (chain_snapshot,),
        get_chain=lambda chain_id, include_archived=True: live_chain if int(chain_id) == int(live_chain.chain_id) else None,
        get_definition=lambda chain_type: SimpleNamespace(reward_profile=SimpleNamespace(gold=520)),
    )
    quest_system = SimpleNamespace(get_active_quests=lambda: ())
    sim = SimpleNamespace(
        heroes=[hero],
        quest_chain_system=quest_chain_system,
        quest_system=quest_system,
    )
    return {"sim": sim, "heroes": [hero]}


def test_dragon_hunt_showcase_registers_ashwing_scene_and_modal_state():
    engine = GameEngine(headless=True, headless_ui=True)

    shots = get_scenario(engine, "dragon_hunt_showcase", seed=3)
    assert len(shots) == 2
    assert [shot.filename for shot in shots] == [
        "dragon_hunt_showcase_world.png",
        "dragon_hunt_showcase_ledger.png",
    ]

    world_shot = shots[0]
    ledger_shot = shots[1]

    assert callable(world_shot.apply)
    world_shot.apply(engine)

    boss_snapshots = engine.sim.boss_encounter_system.get_active_boss_snapshots()
    assert len(boss_snapshots) == 1
    boss = boss_snapshots[0]
    assert boss.name == "Ashwing the Red"
    assert boss.current_phase_title == "Air And Fire"
    assert boss.latest_telegraph == "fire_breath"

    telegraphs = getattr(engine.vfx_system, "_boss_telegraphs", {})
    assert boss.boss_id in telegraphs
    assert telegraphs[boss.boss_id].ability_name == "Fire Breath"

    cave = engine.sim.pois[0]
    assert getattr(cave.poi_def, "display_name", "") == "Dragon Cave"
    assert cave.is_discovered is True

    top_bar_lines = engine.hud._top_bar._boss_status_lines(engine.get_game_state())
    assert top_bar_lines[0][0] == "Ashwing the Red"
    assert "Phase: Air And Fire" in top_bar_lines[1][0]
    assert "Tell: Fire Breath" in top_bar_lines[1][0]

    assert callable(ledger_shot.apply)
    ledger_shot.apply(engine)
    assert engine.building_panel.visible is True
    assert engine.building_panel.selected_building is not None
    assert getattr(engine.building_panel.selected_building, "building_type", "") == "herald_post"
    assert engine.building_panel.quest_create_panel.visible is True

    quest_chain_snapshots = engine.sim.quest_chain_system.get_active_chain_snapshots()
    assert len(quest_chain_snapshots) == 1
    assert quest_chain_snapshots[0].name == "Ashwing's Hoard"
    assert quest_chain_snapshots[0].current_phase_title == "Prepare for Ashwing"


def test_dragon_hunt_ledger_renders_and_saves_pngs():
    chain_snapshot, live_chain = _build_ashwing_chain_snapshot()
    game_state = _dragon_hunt_game_state(chain_snapshot, live_chain)

    panel = QuestViewPanel(UITheme())

    surface = pygame.Surface((246, 300), pygame.SRCALPHA)
    lines = panel.render_active_quests(surface, pygame.Rect(0, 0, 246, 300), game_state)
    assert "Adventure Ledger" in lines
    assert "Ashwing's Hoard" in lines
    assert any(line.startswith("Status: Active") for line in lines)
    assert any("Hero: Astra" in line for line in lines)
    assert any("Reward: $520" in line for line in lines)
    assert any("Now: Prepare for Ashwing" in line for line in lines)
    assert any("Dragon: Ashwing the Red" in line for line in lines)
    assert any("Weakness: Ashwing's fire" in line for line in lines)
    assert any("Prep: Shrine Ember Ward" in line for line in lines)
    assert any("Fire warning: exposed" in line for line in lines)
    assert any("Hoard reward: Dragonscale Armor" in line for line in lines)
    assert any("Victory title: Ashwing-Bane" in line for line in lines)
    assert any(line.startswith("DONE Scout the Dragon Cave") for line in lines)
    assert any(line.startswith("NOW Prepare for Ashwing") for line in lines)
    assert any(line.startswith("NEXT Slay Ashwing the Red") for line in lines)
    assert any(line.startswith("NEXT Claim Ashwing's Hoard") for line in lines)
    saved_246 = _save(surface, "wk143_dragon_ledger_246x300.png")
    assert saved_246.exists()

    compact = pygame.Surface((320, 120), pygame.SRCALPHA)
    compact_lines = panel.render_active_quests(compact, pygame.Rect(0, 0, 320, 120), game_state)
    assert "Adventure Ledger" in compact_lines
    assert any("Now: Prepare for Ashwing" in line for line in compact_lines)
    assert any("Dragon: Ashwing the Red" in line for line in compact_lines)
    assert any("Weakness: Ashwing's fire" in line for line in compact_lines)
    assert any("Prep: Shrine Ember Ward" in line for line in compact_lines)
    assert any("Fire warning: exposed" in line for line in compact_lines)
    assert any("Victory title: Ashwing-Bane" in line for line in compact_lines)
    assert any(
        "DONE Scout the Dragon Cave" in line
        and "NOW Prepare for Ashwing" in line
        and "NEXT Slay Ashwing the Red" in line
        and "NEXT Claim Ashwing's Hoard" in line
        for line in compact_lines
    )
    saved_320 = _save(compact, "wk143_dragon_ledger_320x120.png")
    assert saved_320.exists()
