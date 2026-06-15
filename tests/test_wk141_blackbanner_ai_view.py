"""WK141 Blackbanner AI/view pins.

These tests prove the read-only quest-chain, boss, and elite snapshots flow
through the engine without live object refs, while the no-content path stays
empty/default.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.engine import GameEngine
from game.sim.ai_view import AiGameView
from game.sim.contracts import (
    BossEncounterSnapshot,
    EliteEncounterSnapshot,
    QuestChainHistorySummary,
    QuestChainPhaseSnapshot,
    QuestChainSnapshot,
)


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _blackbanner_chain_snapshot() -> QuestChainSnapshot:
    hero_id = "wk141_hero"
    history = (
        QuestChainHistorySummary(
            event="chain_offered",
            status="offered",
            hero_id=hero_id,
            at_ms=1_000,
        ),
        QuestChainHistorySummary(
            event="chain_accepted",
            status="active",
            hero_id=hero_id,
            at_ms=1_050,
        ),
        QuestChainHistorySummary(
            event="phase_started",
            phase_id="scout_fortress",
            phase_title="Scout the Bandit Fortress",
            status="completed",
            hero_id=hero_id,
            target_id="poi_blackbanner_fortress",
            target_name="Bandit Fortress",
            target_position=(512.0, 256.0),
            at_ms=1_100,
        ),
        QuestChainHistorySummary(
            event="phase_completed",
            phase_id="scout_fortress",
            phase_title="Scout the Bandit Fortress",
            status="completed",
            hero_id=hero_id,
            target_id="poi_blackbanner_fortress",
            target_name="Bandit Fortress",
            target_position=(512.0, 256.0),
            at_ms=1_200,
        ),
        QuestChainHistorySummary(
            event="phase_started",
            phase_id="intercept_toll_taker",
            phase_title="Intercept the Toll-Taker",
            status="active",
            hero_id=hero_id,
            target_id="elite_blackbanner_toll_taker",
            target_name="Blackbanner Toll-Taker",
            target_position=(448.0, 224.0),
            at_ms=1_300,
        ),
    )
    phases = (
        QuestChainPhaseSnapshot(
            phase_id="scout_fortress",
            title="Scout the Bandit Fortress",
            objective_type="scout_fortress",
            status="completed",
            assigned_hero_id=hero_id,
            target_id="poi_blackbanner_fortress",
            target_name="Bandit Fortress",
            target_position=(512.0, 256.0),
            history=history[2:4],
        ),
        QuestChainPhaseSnapshot(
            phase_id="intercept_toll_taker",
            title="Intercept the Toll-Taker",
            objective_type="intercept_toll_taker",
            status="active",
            assigned_hero_id=hero_id,
            target_id="elite_blackbanner_toll_taker",
            target_name="Blackbanner Toll-Taker",
            target_position=(448.0, 224.0),
            history=history[4:],
        ),
        QuestChainPhaseSnapshot(
            phase_id="assault_gate",
            title="Assault the Gate",
            objective_type="assault_gate",
            status="upcoming",
            assigned_hero_id=hero_id,
            target_id="gate_blackbanner",
            target_name="Blackbanner Gate",
            target_position=(544.0, 288.0),
            history=(),
        ),
        QuestChainPhaseSnapshot(
            phase_id="slay_blackbanner",
            title="Defeat Rusk Blackbanner",
            objective_type="slay_blackbanner",
            status="upcoming",
            assigned_hero_id=hero_id,
            target_id="boss_rusk_blackbanner",
            target_name="Rusk Blackbanner",
            target_position=(576.0, 320.0),
            history=(),
        ),
        QuestChainPhaseSnapshot(
            phase_id="claim_reward",
            title="Claim the Spoils",
            objective_type="claim_reward",
            status="upcoming",
            assigned_hero_id=hero_id,
            target_id="castle",
            target_name="Castle",
            target_position=(384.0, 256.0),
            history=(),
        ),
    )
    return QuestChainSnapshot(
        chain_id=141,
        chain_type="blackbanners_toll",
        name="Blackbanner's Toll",
        status="active",
        assigned_hero_id=hero_id,
        current_phase_id="intercept_toll_taker",
        current_phase_title="Intercept the Toll-Taker",
        current_objective_type="intercept_toll_taker",
        target_id="elite_blackbanner_toll_taker",
        target_name="Blackbanner Toll-Taker",
        target_position=(448.0, 224.0),
        phases=phases,
        history=history,
    )


def _blackbanner_boss_snapshot() -> BossEncounterSnapshot:
    return BossEncounterSnapshot(
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


def _blackbanner_elite_snapshot() -> EliteEncounterSnapshot:
    return EliteEncounterSnapshot(
        elite_id="elite_blackbanner_toll_taker",
        base_type="bandit",
        name="Blackbanner Toll-Taker",
        status="active",
        affixes=("banner_bearer", "ironhide"),
        position=(448.0, 224.0),
    )


def _stub_system(*, chain: QuestChainSnapshot | None = None, boss=None, elite=None):
    chain_snapshots = () if chain is None else (chain,)
    boss_snapshots = () if boss is None else (boss,)
    elite_snapshots = () if elite is None else (elite,)
    return SimpleNamespace(
        get_active_chain_snapshots=lambda: chain_snapshots,
        get_active_chain_views=lambda: chain_snapshots,
        get_active_chains=lambda: chain_snapshots,
        get_active_boss_snapshots=lambda: boss_snapshots,
        get_active_boss_views=lambda: boss_snapshots,
        get_active_boss_encounters=lambda: boss_snapshots,
        get_active_elite_snapshots=lambda: elite_snapshots,
        get_active_elite_views=lambda: elite_snapshots,
        get_active_elites=lambda: elite_snapshots,
    )


def test_blackbanner_snapshots_flow_through_engine_read_models():
    engine = GameEngine(headless=True)
    try:
        empty_view = engine.sim.build_ai_view()
        empty_snapshot = engine.build_snapshot()
        assert empty_view.quest_chains == ()
        assert empty_view.boss_encounters == ()
        assert empty_view.elite_enemies == ()
        assert empty_view.elite_encounters == ()
        assert empty_snapshot.quest_chains == ()
        assert empty_snapshot.boss_encounters == ()
        assert empty_snapshot.elite_enemies == ()
        assert empty_snapshot.elite_encounters == ()

        chain = _blackbanner_chain_snapshot()
        boss = _blackbanner_boss_snapshot()
        elite = _blackbanner_elite_snapshot()
        engine.sim.quest_chain_system = _stub_system(chain=chain)
        engine.sim.boss_encounter_system = _stub_system(boss=boss, elite=elite)

        view = engine.sim.build_ai_view()
        snapshot = engine.build_snapshot()

        assert len(view.quest_chains) == 1
        assert len(snapshot.quest_chains) == 1
        assert view.quest_chains[0] == chain
        assert snapshot.quest_chains[0] == chain
        assert view.quest_chains[0].current_phase_id == "intercept_toll_taker"
        assert view.quest_chains[0].phases[0].target_name == "Bandit Fortress"
        assert view.quest_chains[0].phases[1].target_name == "Blackbanner Toll-Taker"
        assert view.quest_chains[0].phases[3].target_name == "Rusk Blackbanner"
        assert view.quest_chains[0].phases[1].history[-1].event == "phase_started"
        assert snapshot.quest_chains[0].phases[3].target_position == (576.0, 320.0)

        assert len(view.boss_encounters) == 1
        assert len(snapshot.boss_encounters) == 1
        assert view.boss_encounters[0] == boss
        assert snapshot.boss_encounters[0] == boss
        assert view.boss_encounters[0].name == "Rusk Blackbanner"
        assert view.boss_encounters[0].target_hero_id == "wk141_hero"

        assert len(view.elite_enemies) == 1
        assert len(snapshot.elite_enemies) == 1
        assert view.elite_enemies[0] == elite
        assert snapshot.elite_enemies[0] == elite
        assert view.elite_encounters == view.elite_enemies
        assert snapshot.elite_encounters == snapshot.elite_enemies
        assert view.elite_enemies[0].name == "Blackbanner Toll-Taker"
        assert view.elite_enemies[0].affixes == ("banner_bearer", "ironhide")
    finally:
        pygame.quit()


def test_blackbanner_ai_view_is_constructible_without_contract_kwargs():
    view = AiGameView(
        world=None,
        heroes=(),
        enemies=(),
        buildings=(),
        bounties=(),
        pois=(),
        player_gold=0,
        castle=None,
        wave=0,
    )
    assert view.quest_chains == ()
    assert view.boss_encounters == ()
    assert view.elite_enemies == ()
    assert view.elite_encounters == ()
