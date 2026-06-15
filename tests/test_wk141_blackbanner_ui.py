"""WK141 Blackbanner UI proof for the Adventure Ledger and boss strip."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from game.sim.contracts import BossEncounterSnapshot, EliteEncounterSnapshot, QuestChainPhaseSnapshot, QuestChainSnapshot
from game.ui.hud import HUD
from game.ui.quest_view_panel import QuestViewPanel
from game.ui.theme import UITheme


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _out_dir() -> Path:
    out_dir = Path("docs/screenshots/wk141_blackbanner_ui")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _save(surface: pygame.Surface, name: str) -> Path:
    path = _out_dir() / name
    pygame.image.save(surface, path.as_posix())
    return path


def _blackbanner_chain_snapshot(status: str = "active") -> tuple[QuestChainSnapshot, SimpleNamespace]:
    hero_id = "wk141_hero"
    if status == "completed":
        phase_statuses = ("completed", "completed", "completed", "completed", "completed")
        current_phase_id = "claim_reward"
        current_phase_title = "Claim the Spoils"
        current_objective_type = "claim_reward"
        current_target_id = "castle"
        current_target_name = "Castle"
    else:
        phase_statuses = ("completed", "active", "upcoming", "upcoming", "upcoming")
        current_phase_id = "intercept_toll_taker"
        current_phase_title = "Intercept the Toll-Taker"
        current_objective_type = "intercept_toll_taker"
        current_target_id = "elite_blackbanner_toll_taker"
        current_target_name = "Blackbanner Toll-Taker"

    phases = (
        QuestChainPhaseSnapshot(
            phase_id="scout_fortress",
            title="Scout the Bandit Fortress",
            objective_type="scout_fortress",
            status=phase_statuses[0],
            assigned_hero_id=hero_id,
            target_id="poi_blackbanner_fortress",
            target_name="Bandit Fortress",
            target_position=(512.0, 256.0),
        ),
        QuestChainPhaseSnapshot(
            phase_id="intercept_toll_taker",
            title="Intercept the Toll-Taker",
            objective_type="intercept_toll_taker",
            status=phase_statuses[1],
            assigned_hero_id=hero_id,
            target_id="elite_blackbanner_toll_taker",
            target_name="Blackbanner Toll-Taker",
            target_position=(448.0, 224.0),
        ),
        QuestChainPhaseSnapshot(
            phase_id="assault_gate",
            title="Assault the Gate",
            objective_type="assault_gate",
            status=phase_statuses[2],
            assigned_hero_id=hero_id,
            target_id="gate_blackbanner",
            target_name="Blackbanner Gate",
            target_position=(544.0, 288.0),
        ),
        QuestChainPhaseSnapshot(
            phase_id="slay_blackbanner",
            title="Defeat Rusk Blackbanner",
            objective_type="slay_blackbanner",
            status=phase_statuses[3],
            assigned_hero_id=hero_id,
            target_id="boss_rusk_blackbanner",
            target_name="Rusk Blackbanner",
            target_position=(576.0, 320.0),
        ),
        QuestChainPhaseSnapshot(
            phase_id="claim_reward",
            title="Claim the Spoils",
            objective_type="claim_reward",
            status=phase_statuses[4],
            assigned_hero_id=hero_id,
            target_id="castle",
            target_name="Castle",
            target_position=(384.0, 256.0),
        ),
    )
    snapshot = QuestChainSnapshot(
        chain_id=141,
        chain_type="blackbanners_toll",
        name="Blackbanner's Toll",
        status=status,
        assigned_hero_id=hero_id,
        current_phase_id=current_phase_id,
        current_phase_title=current_phase_title,
        current_objective_type=current_objective_type,
        target_id=current_target_id,
        target_name=current_target_name,
        target_position=(448.0, 224.0) if status != "completed" else (384.0, 256.0),
        phases=phases,
    )
    live_chain = SimpleNamespace(
        chain_id=141,
        chain_type="blackbanners_toll",
        reward_gold=260,
        facts={
            "boss_target_revealed": True,
            "boss_target_name": "Rusk Blackbanner",
        },
    )
    return snapshot, live_chain


def _make_quest_game_state(chain_snapshot: QuestChainSnapshot, live_chain: SimpleNamespace) -> dict:
    hero = SimpleNamespace(hero_id="wk141_hero", name="Astra")
    quest_chain_system = SimpleNamespace(
        get_active_chain_snapshots=lambda: (chain_snapshot,),
        get_active_chain_views=lambda: (chain_snapshot,),
        get_active_chains=lambda: (chain_snapshot,),
        get_chain=lambda chain_id, include_archived=True: live_chain if int(chain_id) == int(live_chain.chain_id) else None,
        get_definition=lambda chain_type: SimpleNamespace(reward_profile=SimpleNamespace(gold=260)),
    )
    quest_system = SimpleNamespace(get_active_quests=lambda: ())
    event_bus = SimpleNamespace(subscribe=lambda *args, **kwargs: None)
    sim = SimpleNamespace(
        heroes=[hero],
        quest_chain_system=quest_chain_system,
        quest_system=quest_system,
        event_bus=event_bus,
    )
    return {"sim": sim, "heroes": [hero]}


def _make_boss_game_state() -> dict:
    boss = BossEncounterSnapshot(
        boss_id="boss_rusk_blackbanner",
        boss_type="bandit_lord",
        name="Rusk Blackbanner",
        status="active",
        current_phase="toll_banner",
        current_phase_title="Toll Banner",
        hp_pct=0.62,
        position=(576.0, 320.0),
        target_hero_id="wk141_hero",
        latest_telegraph="toll_banner",
    )
    elite = EliteEncounterSnapshot(
        elite_id="elite_blackbanner_toll_taker",
        base_type="bandit",
        name="Blackbanner Toll-Taker",
        status="active",
        affixes=("banner_bearer", "ironhide"),
        position=(448.0, 224.0),
    )
    boss_system = SimpleNamespace(
        get_active_boss_snapshots=lambda: (boss,),
        get_active_boss_views=lambda: (boss,),
        get_active_boss_encounters=lambda: (boss,),
        get_active_elite_snapshots=lambda: (elite,),
        get_active_elite_views=lambda: (elite,),
        get_active_elites=lambda: (elite,),
    )
    event_bus = SimpleNamespace(subscribe=lambda *args, **kwargs: None)
    sim = SimpleNamespace(
        boss_encounter_system=boss_system,
        event_bus=event_bus,
    )
    return {
        "sim": sim,
        "engine": SimpleNamespace(sim=sim),
        "heroes": [],
        "enemies": [],
        "gold": 0,
        "wave": 1,
        "ui_cursor_pos": (0, 0),
    }


def test_blackbanner_ledger_active_state_renders_current_target_and_revealed_boss():
    chain_snapshot, live_chain = _blackbanner_chain_snapshot("active")
    game_state = _make_quest_game_state(chain_snapshot, live_chain)

    panel = QuestViewPanel(UITheme())
    surface = pygame.Surface((246, 300), pygame.SRCALPHA)
    surface.fill((24, 26, 32))
    lines = panel.render_active_quests(surface, pygame.Rect(0, 0, 246, 300), game_state)

    assert "Adventure Ledger" in lines
    assert "Blackbanner's Toll" in lines
    assert any(line.startswith("Status: Active") for line in lines)
    assert any("Hero: Astra" in line for line in lines)
    assert any("Reward: $260" in line for line in lines)
    assert any("Current objective: Intercept the Toll-Taker" in line for line in lines)
    assert any("Target: Blackbanner Toll-Taker" in line for line in lines)
    assert any("Boss: Rusk Blackbanner" in line for line in lines)
    assert any(line.startswith("DONE Scout the Bandit Fortress") for line in lines)
    assert any(line.startswith("NOW Intercept the Toll-Taker") for line in lines)
    assert any(line.startswith("NEXT Assault the Gate") for line in lines)
    assert any(line.startswith("NEXT Defeat Rusk Blackbanner") for line in lines)
    assert any(line.startswith("NEXT Claim the Spoils") for line in lines)

    saved = _save(surface, "wk141_blackbanner_ledger_active_246x300.png")
    assert saved.exists()


def test_blackbanner_ledger_completed_state_compacts_cleanly():
    chain_snapshot, live_chain = _blackbanner_chain_snapshot("completed")
    game_state = _make_quest_game_state(chain_snapshot, live_chain)

    panel = QuestViewPanel(UITheme())
    surface = pygame.Surface((320, 120), pygame.SRCALPHA)
    surface.fill((24, 26, 32))
    lines = panel.render_active_quests(surface, pygame.Rect(0, 0, 320, 120), game_state)

    assert "Adventure Ledger" in lines
    assert any(line.startswith("Blackbanner's Toll") for line in lines)
    assert any("Status: Completed" in line for line in lines)
    assert any("Hero: Astra" in line for line in lines)
    assert any("Reward: $260" in line for line in lines)
    assert any("Outcome: Completed" in line for line in lines)
    assert any(
        "DONE Scout the Bandit Fortress" in line
        and "DONE Intercept the Toll-Taker" in line
        and "DONE Assault the Gate" in line
        and "DONE Defeat Rusk Blackbanner" in line
        and "DONE Claim the Spoils" in line
        for line in lines
    )

    saved = _save(surface, "wk141_blackbanner_ledger_completed_320x120.png")
    assert saved.exists()


def test_blackbanner_ledger_active_compact_state_still_shows_revealed_boss():
    chain_snapshot, live_chain = _blackbanner_chain_snapshot("active")
    game_state = _make_quest_game_state(chain_snapshot, live_chain)

    panel = QuestViewPanel(UITheme())
    surface = pygame.Surface((320, 120), pygame.SRCALPHA)
    surface.fill((24, 26, 32))
    lines = panel.render_active_quests(surface, pygame.Rect(0, 0, 320, 120), game_state)

    assert "Adventure Ledger" in lines
    assert any(line.startswith("Blackbanner's Toll") for line in lines)
    assert any("Status: Active" in line for line in lines)
    assert any("Hero: Astra" in line for line in lines)
    assert any("Reward: $260" in line for line in lines)
    assert any("Now: Intercept" in line for line in lines)
    assert any("Boss: Rusk Blackbanner" in line for line in lines)
    assert any(
        "DONE Scout the Bandit Fortress" in line
        and "NOW Intercept the Toll-Taker" in line
        and "NEXT Assault the Gate" in line
        and "NEXT Defeat Rusk Blackbanner" in line
        and "NEXT Claim the Spoils" in line
        for line in lines
    )

    saved = _save(surface, "wk141_blackbanner_ledger_active_320x120.png")
    assert saved.exists()


def test_blackbanner_boss_ui_lines_show_rusk_phase_hp_telegraph_and_elite_hint():
    hud = HUD(1920, 1080)
    hud._session_start_ms = -100000
    game_state = _make_boss_game_state()

    lines = hud._top_bar._boss_status_lines(game_state)

    assert lines[0][0] == "Rusk Blackbanner"
    assert "Phase: Toll Banner" in lines[1][0]
    assert "HP: 62%" in lines[1][0]
    assert "Tell: Toll Banner" in lines[1][0]
    assert lines[2][0] == "Elites: 1 | banner/shield"

    surface = pygame.Surface((1920, 1080), pygame.SRCALPHA)
    surface.fill((44, 58, 44))
    hud._top_bar.render(surface, pygame.Rect(0, 0, 1920, hud.top_bar_height), game_state)
    saved = _save(surface, "wk141_blackbanner_boss_ui_1920x1080.png")
    assert saved.exists()
