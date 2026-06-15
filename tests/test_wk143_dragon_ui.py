"""WK143 Dragon Hunt UI proof for the Adventure Ledger."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from game.sim.contracts import QuestChainHistorySummary, QuestChainPhaseSnapshot, QuestChainSnapshot
from game.ui.quest_view_panel import QuestViewPanel
from game.ui.theme import UITheme


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _out_dir() -> Path:
    out_dir = Path("docs/screenshots/wk143_dragon_hunt_ui")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _save(surface: pygame.Surface, name: str) -> Path:
    path = _out_dir() / name
    pygame.image.save(surface, path.as_posix())
    return path


def _ashwing_snapshot(status: str = "active") -> tuple[QuestChainSnapshot, SimpleNamespace]:
    hero_id = "wk143_hero"
    if status == "completed":
        phase_statuses = ("completed", "completed", "completed", "completed")
        current_phase_id = "claim_hoard"
        current_phase_title = "Claim Ashwing's Hoard"
        current_objective_type = "claim_hoard"
        current_target_id = "ashwing_hoard"
        current_target_name = "Ashwing's Hoard"
    else:
        phase_statuses = ("completed", "active", "upcoming", "upcoming")
        current_phase_id = "prepare_hunt"
        current_phase_title = "Prepare for Ashwing"
        current_objective_type = "prepare_hunt"
        current_target_id = "poi_dragon_cave"
        current_target_name = "Dragon Cave"

    cave_position = (448.0, 256.0)
    phases = (
        QuestChainPhaseSnapshot(
            phase_id="scout_dragon_cave",
            title="Scout the Dragon Cave",
            objective_type="scout_location",
            status=phase_statuses[0],
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
            status=phase_statuses[1],
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
            status=phase_statuses[2],
            assigned_hero_id=hero_id,
            target_id="ashwing_the_red",
            target_name="Ashwing the Red",
            target_position=cave_position,
        ),
        QuestChainPhaseSnapshot(
            phase_id="claim_hoard",
            title="Claim Ashwing's Hoard",
            objective_type="claim_hoard",
            status=phase_statuses[3],
            assigned_hero_id=hero_id,
            target_id="ashwing_hoard",
            target_name="Ashwing's Hoard",
            target_position=cave_position,
        ),
    )

    snapshot = QuestChainSnapshot(
        chain_id=143,
        chain_type="ashwings_hoard",
        name="Ashwing's Hoard",
        status=status,
        assigned_hero_id=hero_id,
        current_phase_id=current_phase_id,
        current_phase_title=current_phase_title,
        current_objective_type=current_objective_type,
        target_id=current_target_id,
        target_name=current_target_name,
        target_position=cave_position,
        phases=phases,
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
            "prep_target_prepared": status == "completed",
            "reward_item_name": "Dragonscale Armor",
            "reward_title": "Ashwing-Bane",
            "reward_memory_summary": "Claimed Ashwing's Hoard",
            "target_location_name": "Dragon Cave",
        },
    )
    return snapshot, live_chain


def _game_state(chain_snapshot: QuestChainSnapshot, live_chain: SimpleNamespace) -> dict:
    hero = SimpleNamespace(
        hero_id="wk143_hero",
        name="Astra",
        current_title="Ashwing-Bane" if chain_snapshot.status == "completed" else "",
        hero_title="Ashwing-Bane" if chain_snapshot.status == "completed" else "",
    )
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


def _render(size: tuple[int, int], status: str) -> tuple[list[str], pygame.Surface]:
    chain_snapshot, live_chain = _ashwing_snapshot(status=status)
    game_state = _game_state(chain_snapshot, live_chain)
    panel = QuestViewPanel(UITheme())
    surface = pygame.Surface(size, pygame.SRCALPHA)
    surface.fill((24, 26, 32))
    lines = panel.render_active_quests(surface, pygame.Rect(0, 0, size[0], size[1]), game_state)
    return lines, surface


def test_ashwing_ledger_active_state_renders_identity_preparation_fire_warning_reward_and_title():
    lines, surface = _render((246, 300), "active")

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

    saved = _save(surface, "wk143_dragon_ledger_active_246x300.png")
    assert saved.exists()

    compact_lines, compact = _render((320, 120), "active")
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

    compact_saved = _save(compact, "wk143_dragon_ledger_active_320x120.png")
    assert compact_saved.exists()


def test_ashwing_ledger_completed_state_renders_victory_title_and_outcome():
    lines, surface = _render((246, 300), "completed")

    assert "Adventure Ledger" in lines
    assert "Ashwing's Hoard" in lines
    assert any(line.startswith("Status: Completed") for line in lines)
    assert any("Hero: Astra" in line for line in lines)
    assert any("Reward: $520" in line for line in lines)
    assert any("Dragon: Ashwing the Red" in line for line in lines)
    assert any("Victory title: Ashwing-Bane" in line for line in lines)
    assert any("Weakness: Ashwing's fire" in line for line in lines)
    assert any("Prep: Shrine Ember Ward" in line for line in lines)
    assert any("Hoard reward: Dragonscale Armor" in line for line in lines)
    assert any("Memory: Claimed Ashwing's Hoard" in line for line in lines)
    assert any("Outcome: Completed" in line for line in lines)
    assert any(line.startswith("DONE Scout the Dragon Cave") for line in lines)
    assert any(line.startswith("DONE Prepare for Ashwing") for line in lines)
    assert any(line.startswith("DONE Slay Ashwing the Red") for line in lines)
    assert any(line.startswith("DONE Claim Ashwing's Hoard") for line in lines)

    saved = _save(surface, "wk143_dragon_ledger_completed_246x300.png")
    assert saved.exists()

    compact_lines, compact = _render((320, 120), "completed")
    assert "Adventure Ledger" in compact_lines
    assert any("Status: Completed" in line for line in compact_lines)
    assert any("Dragon: Ashwing the Red" in line for line in compact_lines)
    assert any("Victory title: Ashwing-Bane" in line for line in compact_lines)
    assert any("Weakness: Ashwing's fire" in line for line in compact_lines)
    assert any("Prep: Shrine Ember Ward" in line for line in compact_lines)
    assert any("Hoard reward: Dragonscale Armor" in line for line in compact_lines)
    assert any("Memory: Claimed Ashwing's Hoard" in line for line in compact_lines)
    assert any("Outcome: Completed" in line for line in compact_lines)

    compact_saved = _save(compact, "wk143_dragon_ledger_completed_320x120.png")
    assert compact_saved.exists()
