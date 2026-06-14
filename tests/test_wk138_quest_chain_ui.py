"""WK138 quest-chain UI verification for Agent 08.

This suite renders the chain board directly and through the existing
quest-create modal, then saves deterministic PNGs under docs/screenshots/wk138_*.
The active chain path is not currently surfaced by tools/screenshot_scenarios.py
ui_panels, so this fixture is the smallest UI-owned proof path available in-lane.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from game.content.quest_chains import COLLECT_ITEM, DELIVER_ITEM, RELIC_OF_THE_OLD_SHRINE, SCOUT_LOCATION
from game.sim.contracts import QuestChainHistorySummary, QuestChainPhaseSnapshot, QuestChainSnapshot
from game.ui.quest_create_panel import QuestCreatePanel
from game.ui.quest_view_panel import QuestViewPanel
from game.ui.theme import UITheme


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _build_chain_snapshot(status: str = "active") -> tuple[QuestChainSnapshot, SimpleNamespace]:
    if status == "completed":
        phase_statuses = ("completed", "completed", "completed")
        current_phase_id = DELIVER_ITEM
        current_phase_title = "Deliver the Relic"
        current_objective_type = DELIVER_ITEM
    elif status == "failed":
        phase_statuses = ("failed", "failed", "upcoming")
        current_phase_id = COLLECT_ITEM
        current_phase_title = "Recover the Relic"
        current_objective_type = COLLECT_ITEM
    else:
        phase_statuses = ("completed", "active", "upcoming")
        current_phase_id = COLLECT_ITEM
        current_phase_title = "Recover the Relic"
        current_objective_type = COLLECT_ITEM

    phases = (
        QuestChainPhaseSnapshot(
            phase_id=SCOUT_LOCATION,
            title="Scout the Ancient Ruins",
            objective_type=SCOUT_LOCATION,
            status=phase_statuses[0],
            assigned_hero_id="hero_1",
            target_id="poi_ancient_ruins",
            target_name="Ancient Ruins",
            target_position=(128.0, 96.0),
            history=(
                QuestChainHistorySummary(
                    event="phase_started",
                    phase_id=SCOUT_LOCATION,
                    phase_title="Scout the Ancient Ruins",
                    status="active",
                    hero_id="hero_1",
                    target_id="poi_ancient_ruins",
                    target_name="Ancient Ruins",
                    target_position=(128.0, 96.0),
                    at_ms=1000,
                ),
                QuestChainHistorySummary(
                    event="phase_completed",
                    phase_id=SCOUT_LOCATION,
                    phase_title="Scout the Ancient Ruins",
                    status="completed",
                    hero_id="hero_1",
                    target_id="poi_ancient_ruins",
                    target_name="Ancient Ruins",
                    target_position=(128.0, 96.0),
                    at_ms=2000,
                ),
            ),
        ),
        QuestChainPhaseSnapshot(
            phase_id=COLLECT_ITEM,
            title="Recover the Relic",
            objective_type=COLLECT_ITEM,
            status=phase_statuses[1],
            assigned_hero_id="hero_1",
            target_id="poi_ancient_ruins",
            target_name="Ancient Ruins",
            target_position=(128.0, 96.0),
            history=(
                QuestChainHistorySummary(
                    event="phase_started",
                    phase_id=COLLECT_ITEM,
                    phase_title="Recover the Relic",
                    status="active",
                    hero_id="hero_1",
                    target_id="poi_ancient_ruins",
                    target_name="Ancient Ruins",
                    target_position=(128.0, 96.0),
                    at_ms=3000,
                ),
            ),
        ),
        QuestChainPhaseSnapshot(
            phase_id=DELIVER_ITEM,
            title="Deliver the Relic",
            objective_type=DELIVER_ITEM,
            status=phase_statuses[2],
            assigned_hero_id="hero_1",
            target_id="castle",
            target_name="Castle",
            target_position=(384.0, 256.0),
            history=(),
        ),
    )
    snapshot = QuestChainSnapshot(
        chain_id=7,
        chain_type=RELIC_OF_THE_OLD_SHRINE.chain_type,
        name=RELIC_OF_THE_OLD_SHRINE.display_name,
        status=status,
        assigned_hero_id="hero_1",
        current_phase_id=current_phase_id,
        current_phase_title=current_phase_title,
        current_objective_type=current_objective_type,
        target_id="poi_ancient_ruins",
        target_name="Ancient Ruins",
        target_position=(128.0, 96.0),
        phases=phases,
        history=(
            QuestChainHistorySummary(
                event="chain_offered",
                status="offered",
                hero_id="hero_1",
                target_id="poi_ancient_ruins",
                target_name="Ancient Ruins",
                target_position=(128.0, 96.0),
                at_ms=1000,
            ),
            QuestChainHistorySummary(
                event="chain_accepted",
                status="active",
                hero_id="hero_1",
                target_id="poi_ancient_ruins",
                target_name="Ancient Ruins",
                target_position=(128.0, 96.0),
                at_ms=2000,
            ),
        ),
    )
    live_chain = SimpleNamespace(chain_id=7, reward_gold=RELIC_OF_THE_OLD_SHRINE.reward_profile.gold)
    return snapshot, live_chain


def _make_game_state(chain_snapshot, live_chain, hero=None):
    hero = hero or SimpleNamespace(hero_id="hero_1", name="Astra")
    quest_chain_system = SimpleNamespace(
        get_active_chain_snapshots=lambda: (chain_snapshot,),
        get_active_chain_views=lambda: (chain_snapshot,),
        get_active_chains=lambda: (chain_snapshot,),
        get_chain=lambda chain_id, include_archived=True: live_chain if int(chain_id) == int(live_chain.chain_id) else None,
        get_definition=lambda chain_type: RELIC_OF_THE_OLD_SHRINE,
    )
    quest_system = SimpleNamespace(get_active_quests=lambda: ())
    sim = SimpleNamespace(heroes=[hero], quest_chain_system=quest_chain_system, quest_system=quest_system)
    return {"sim": sim, "heroes": [hero]}


def _ensure_out_dir() -> Path:
    out_dir = Path("docs/screenshots/wk138_quest_chain_ui_panels")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _save(surface: pygame.Surface, name: str) -> Path:
    out_dir = _ensure_out_dir()
    path = out_dir / name
    pygame.image.save(surface, path.as_posix())
    return path


def test_active_chain_board_renders_completed_current_upcoming_and_saves_pngs():
    chain_snapshot, live_chain = _build_chain_snapshot("active")
    game_state = _make_game_state(chain_snapshot, live_chain)

    panel = QuestViewPanel(UITheme())
    surface = pygame.Surface((246, 300), pygame.SRCALPHA)
    lines = panel.render_active_quests(surface, pygame.Rect(0, 0, 246, 300), game_state)

    assert "Adventure Ledger" in lines
    assert "Relic of the Old Shrine" in lines
    assert any(line.startswith("Status: Active") for line in lines)
    assert any("Hero: Astra" in line for line in lines)
    assert any("Reward: $180" in line for line in lines)
    assert any("Current objective: Recover the Relic" in line for line in lines)
    assert any(line.startswith("DONE Scout the Ancient Ruins") for line in lines)
    assert any(line.startswith("NOW Recover the Relic") for line in lines)
    assert any(line.startswith("NEXT Deliver the Relic") for line in lines)

    saved = _save(surface, "wk138_quest_chain_board_246x300.png")
    assert saved.exists()


def test_active_chain_board_compacts_cleanly_in_short_rows():
    chain_snapshot, live_chain = _build_chain_snapshot("active")
    game_state = _make_game_state(chain_snapshot, live_chain)

    panel = QuestViewPanel(UITheme())
    surface = pygame.Surface((320, 120), pygame.SRCALPHA)
    lines = panel.render_active_quests(surface, pygame.Rect(0, 0, 320, 120), game_state)

    assert "Adventure Ledger" in lines
    assert any(line.startswith("Relic of the Old Shrine") for line in lines)
    assert any("Status: Active" in line for line in lines)
    assert any("Current objective: Recover the Relic" in line for line in lines)
    assert any(
        "DONE Scout the Ancient Ruins" in line
        and "NOW Recover the Relic" in line
        and "NEXT Deliver the Relic" in line
        for line in lines
    )

    saved = _save(surface, "wk138_quest_chain_board_320x120.png")
    assert saved.exists()


def test_completed_and_failed_chain_outcomes_are_readable():
    panel = QuestViewPanel(UITheme())
    for status, expected in (("completed", "Outcome: Completed"), ("failed", "Outcome: Failed")):
        chain_snapshot, live_chain = _build_chain_snapshot(status)
        game_state = _make_game_state(chain_snapshot, live_chain)
        surface = pygame.Surface((320, 360), pygame.SRCALPHA)
        lines = panel.render_active_quests(surface, pygame.Rect(0, 0, 320, 360), game_state)
        assert expected in lines
        assert any(line.startswith("DONE ") or line.startswith("FAIL ") for line in lines)


def test_quest_create_modal_renders_chain_board_in_full_modal_sizes():
    chain_snapshot, live_chain = _build_chain_snapshot("active")
    game_state = _make_game_state(chain_snapshot, live_chain)
    panel = QuestCreatePanel(1920, 1080)
    panel.open(
        SimpleNamespace(entity_id="post_1", center_x=0.0, center_y=0.0, building_type="herald_post"),
        {"sim": game_state["sim"], "world": None},
    )

    surface_1920 = pygame.Surface((1920, 1080), pygame.SRCALPHA)
    panel.render(surface_1920, economy=SimpleNamespace(player_gold=500))
    path_1920 = _save(surface_1920, "wk138_quest_chain_modal_1920x1080.png")

    panel.on_resize(1024, 576)
    surface_1024 = pygame.Surface((1024, 576), pygame.SRCALPHA)
    panel.render(surface_1024, economy=SimpleNamespace(player_gold=500))
    path_1024 = _save(surface_1024, "wk138_quest_chain_modal_1024x576.png")

    assert path_1920.exists()
    assert path_1024.exists()
