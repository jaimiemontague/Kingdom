"""WK142 rescue/revenge UI proof for the Adventure Ledger."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from game.content.quest_chains import (
    AVENGE_FALLEN_HERO,
    BLACKBANNER_RESCUE,
    BLACKBANNER_REVENGE,
    REACH_FORTRESS,
    RESCUE_HERO,
    SLAY_NAMED_BOSS,
)
from game.sim.contracts import QuestChainPhaseSnapshot, QuestChainSnapshot
from game.ui.quest_create_panel import QuestCreatePanel
from game.ui.quest_view_panel import QuestViewPanel
from game.ui.theme import UITheme


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _out_dir() -> Path:
    out_dir = Path("docs/screenshots/wk142_rescue_revenge_ui")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _save(surface: pygame.Surface, name: str) -> Path:
    path = _out_dir() / name
    pygame.image.save(surface, path.as_posix())
    return path


def _quest_chain_system(chain_snapshot: QuestChainSnapshot, live_chain: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        get_active_chain_snapshots=lambda: (chain_snapshot,),
        get_active_chain_views=lambda: (chain_snapshot,),
        get_active_chains=lambda: (chain_snapshot,),
        get_chain=lambda chain_id, include_archived=True: live_chain if int(chain_id) == int(live_chain.chain_id) else None,
        get_definition=lambda chain_type: BLACKBANNER_RESCUE if chain_type == BLACKBANNER_RESCUE.chain_type else BLACKBANNER_REVENGE,
    )


def _quest_game_state(chain_snapshot: QuestChainSnapshot, live_chain: SimpleNamespace) -> dict:
    hero = SimpleNamespace(hero_id="wk142_rescuer", name="Bryn")
    quest_system = SimpleNamespace(get_active_quests=lambda: ())
    sim = SimpleNamespace(
        heroes=[hero],
        quest_chain_system=_quest_chain_system(chain_snapshot, live_chain),
        quest_system=quest_system,
        event_bus=SimpleNamespace(subscribe=lambda *args, **kwargs: None),
    )
    return {"sim": sim, "heroes": [hero]}


def _fake_post() -> SimpleNamespace:
    return SimpleNamespace(
        entity_id="post_wk142",
        center_x=512.0,
        center_y=320.0,
        building_type="herald_post",
    )


def _rescue_snapshot(status: str = "active") -> tuple[QuestChainSnapshot, SimpleNamespace]:
    phase_status = "completed" if status == "completed" else "active"
    phases = (
        QuestChainPhaseSnapshot(
            phase_id=REACH_FORTRESS,
            title="Reach the Bandit Fortress",
            objective_type=RESCUE_HERO,
            status=phase_status,
            assigned_hero_id="wk142_rescuer",
            target_id="poi_blackbanner_fortress",
            target_name="Bandit Fortress",
            target_position=(384.0, 224.0),
        ),
    )
    snapshot = QuestChainSnapshot(
        chain_id=1421,
        chain_type=BLACKBANNER_RESCUE.chain_type,
        name=BLACKBANNER_RESCUE.display_name,
        status=status,
        assigned_hero_id="wk142_rescuer",
        current_phase_id=REACH_FORTRESS,
        current_phase_title="Reach the Bandit Fortress",
        current_objective_type=RESCUE_HERO,
        target_id="poi_blackbanner_fortress",
        target_name="Bandit Fortress",
        target_position=(384.0, 224.0),
        phases=phases,
    )
    live_chain = SimpleNamespace(
        chain_id=1421,
        chain_type=BLACKBANNER_RESCUE.chain_type,
        reward_gold=BLACKBANNER_RESCUE.reward_profile.gold,
        facts={
            "captured_hero_id": "wk142_captive",
            "captured_hero_name": "Astra",
            "captor_boss_id": "boss_rusk_blackbanner",
            "captor_boss_name": "Rusk Blackbanner",
            "captor_boss_type": "bandit_lord",
            "origin_target_id": "poi_blackbanner_fortress",
            "origin_target_name": "Bandit Fortress",
            "origin_target_position": (384.0, 224.0),
            "rescue_id": "rescue_wk142_captive",
            "source_chain_id": "chain_blackbanner_cells",
            "source_chain_type": "blackbanners_toll",
        },
    )
    return snapshot, live_chain


def _revenge_snapshot(status: str = "active") -> tuple[QuestChainSnapshot, SimpleNamespace]:
    phase_status = "completed" if status == "completed" else "active"
    phases = (
        QuestChainPhaseSnapshot(
            phase_id=AVENGE_FALLEN_HERO,
            title="Avenge the Fallen",
            objective_type=SLAY_NAMED_BOSS,
            status=phase_status,
            assigned_hero_id="wk142_rescuer",
            target_id="boss_rusk_blackbanner",
            target_name="Rusk Blackbanner",
            target_position=(576.0, 320.0),
        ),
    )
    snapshot = QuestChainSnapshot(
        chain_id=1422,
        chain_type=BLACKBANNER_REVENGE.chain_type,
        name=BLACKBANNER_REVENGE.display_name,
        status=status,
        assigned_hero_id="wk142_rescuer",
        current_phase_id=AVENGE_FALLEN_HERO,
        current_phase_title="Avenge the Fallen",
        current_objective_type=SLAY_NAMED_BOSS,
        target_id="boss_rusk_blackbanner",
        target_name="Rusk Blackbanner",
        target_position=(576.0, 320.0),
        phases=phases,
    )
    live_chain = SimpleNamespace(
        chain_id=1422,
        chain_type=BLACKBANNER_REVENGE.chain_type,
        reward_gold=BLACKBANNER_REVENGE.reward_profile.gold,
        facts={
            "boss_target_id": "boss_rusk_blackbanner",
            "boss_target_entity_id": "boss_rusk_blackbanner",
            "boss_target_name": "Rusk Blackbanner",
            "boss_target_position": (576.0, 320.0),
            "boss_target_story_name": "Rusk Blackbanner",
            "boss_target_phase_id": AVENGE_FALLEN_HERO,
            "boss_target_revealed": True,
            "boss_target_defeated": status == "completed",
            "fallen_hero_id": "wk142_fallen",
            "fallen_hero_name": "Mira",
            "revenge_id": "revenge_rusk_mira",
            "revenge_chain_id": "revenge_rusk_mira",
            "target_location_id": "poi_blackbanner_fortress",
            "target_location_name": "Bandit Fortress",
            "target_location_position": (384.0, 224.0),
            "source_chain_id": "chain_blackbanner_cells",
            "source_chain_type": "blackbanners_toll",
        },
    )
    return snapshot, live_chain


def _render_direct_board(chain_snapshot: QuestChainSnapshot, live_chain: SimpleNamespace, size: tuple[int, int]) -> tuple[list[str], pygame.Surface]:
    game_state = _quest_game_state(chain_snapshot, live_chain)
    panel = QuestViewPanel(UITheme())
    surface = pygame.Surface(size, pygame.SRCALPHA)
    surface.fill((24, 26, 32))
    lines = panel.render_active_quests(surface, pygame.Rect(0, 0, size[0], size[1]), game_state)
    return lines, surface


def _render_modal(chain_snapshot: QuestChainSnapshot, live_chain: SimpleNamespace, size: tuple[int, int]) -> pygame.Surface:
    game_state = _quest_game_state(chain_snapshot, live_chain)
    panel = QuestCreatePanel(size[0], size[1])
    panel.open(_fake_post(), {"sim": game_state["sim"], "world": None})
    surface = pygame.Surface(size, pygame.SRCALPHA)
    surface.fill((24, 26, 32))
    panel.render(surface, economy=SimpleNamespace(player_gold=500))
    return surface


def test_blackbanner_rescue_active_state_renders_captive_captor_location_and_modal_png():
    chain_snapshot, live_chain = _rescue_snapshot("active")
    lines, board_surface = _render_direct_board(chain_snapshot, live_chain, (246, 300))

    assert "Adventure Ledger" in lines
    assert "Break the Blackbanner Cells" in lines
    assert any("Status: Active" in line for line in lines)
    assert any("Hero: Bryn" in line for line in lines)
    assert any("Reward: $180" in line for line in lines)
    assert any("Captive: Astra" in line for line in lines)
    assert any("Captor: Rusk Blackbanner" in line for line in lines)
    assert any("Location: Bandit Fortress" in line for line in lines)
    assert any("Current objective: Reach the Bandit Fortress" in line for line in lines)
    assert any(line.startswith("NOW Reach the Bandit Fortress") for line in lines)

    board_saved = _save(board_surface, "wk142_blackbanner_rescue_active_246x300.png")
    assert board_saved.exists()

    modal_surface = _render_modal(chain_snapshot, live_chain, (1920, 1080))
    modal_saved = _save(modal_surface, "wk142_blackbanner_rescue_modal_active_1920x1080.png")
    assert modal_saved.exists()


def test_blackbanner_rescue_completed_state_compacts_cleanly_with_outcome_and_location():
    chain_snapshot, live_chain = _rescue_snapshot("completed")
    lines, board_surface = _render_direct_board(chain_snapshot, live_chain, (320, 120))

    assert "Adventure Ledger" in lines
    assert any(line.startswith("Break the Blackbanner Cells") for line in lines)
    assert any("Status: Completed" in line for line in lines)
    assert any("Rescued: Astra" in line for line in lines)
    assert any("From: Rusk Blackbanner" in line for line in lines)
    assert any("Location: Bandit Fortress" in line for line in lines)
    assert any("Outcome: Completed" in line for line in lines)
    assert any(line.startswith("DONE Reach the Bandit Fortress") for line in lines)

    board_saved = _save(board_surface, "wk142_blackbanner_rescue_completed_320x120.png")
    assert board_saved.exists()


def test_blackbanner_revenge_active_state_renders_fallen_boss_location_and_modal_png():
    chain_snapshot, live_chain = _revenge_snapshot("active")
    lines, board_surface = _render_direct_board(chain_snapshot, live_chain, (246, 300))

    assert "Adventure Ledger" in lines
    assert "Avenge the Fallen" in lines
    assert any("Status: Active" in line for line in lines)
    assert any("Hero: Bryn" in line for line in lines)
    assert any("Reward: $220" in line for line in lines)
    assert any("Fallen: Mira" in line for line in lines)
    assert any("Boss: Rusk Blackbanner" in line for line in lines)
    assert any("Location: Bandit Fortress" in line for line in lines)
    assert any("Current objective: Avenge the Fallen" in line for line in lines)
    assert any("Boss: Rusk Blackbanner" in line for line in lines)
    assert any(line.startswith("NOW Avenge the Fallen") for line in lines)

    board_saved = _save(board_surface, "wk142_blackbanner_revenge_active_246x300.png")
    assert board_saved.exists()

    modal_surface = _render_modal(chain_snapshot, live_chain, (1920, 1080))
    modal_saved = _save(modal_surface, "wk142_blackbanner_revenge_modal_active_1920x1080.png")
    assert modal_saved.exists()


def test_blackbanner_revenge_completed_state_compacts_cleanly_with_outcome_and_location():
    chain_snapshot, live_chain = _revenge_snapshot("completed")
    lines, board_surface = _render_direct_board(chain_snapshot, live_chain, (320, 120))

    assert "Adventure Ledger" in lines
    assert any(line.startswith("Avenge the Fallen") for line in lines)
    assert any("Status: Completed" in line for line in lines)
    assert any("Avenged: Mira" in line for line in lines)
    assert any("Against: Rusk Blackbanner" in line for line in lines)
    assert any("Location: Bandit Fortress" in line for line in lines)
    assert any("Outcome: Completed" in line for line in lines)
    assert any(line.startswith("DONE Avenge the Fallen") for line in lines)

    board_saved = _save(board_surface, "wk142_blackbanner_revenge_completed_320x120.png")
    assert board_saved.exists()
