"""WK141 Blackbanner contract pins.

This locks the primitive-only snapshot shapes used by Blackbanner's Toll while
keeping the empty-default contract from WK138/WK139 intact.
"""

from __future__ import annotations

import dataclasses

import pytest

from game.sim.contracts import (
    BossEncounterSnapshot,
    BossMemorySummary,
    EliteEncounterSnapshot,
    QuestChainHistorySummary,
    QuestChainPhaseSnapshot,
    QuestChainSnapshot,
)


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
        QuestChainHistorySummary(
            event="phase_started",
            phase_id="slay_blackbanner",
            phase_title="Defeat Rusk Blackbanner",
            status="upcoming",
            hero_id=hero_id,
            target_id="boss_rusk_blackbanner",
            target_name="Rusk Blackbanner",
            target_position=(576.0, 320.0),
            at_ms=1_400,
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
            history=history[4:5],
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
            history=history[5:],
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
        memory_summaries=(
            BossMemorySummary(
                event="defeated_by",
                hero_id="wk141_hero",
                hero_name="Astra",
                detail="the toll was broken",
                at_ms=1_500,
            ),
        ),
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


def test_blackbanner_contract_snapshots_are_frozen_and_primitive_only():
    chain = _blackbanner_chain_snapshot()
    boss = _blackbanner_boss_snapshot()
    elite = _blackbanner_elite_snapshot()

    assert dataclasses.is_dataclass(chain)
    assert dataclasses.is_dataclass(boss)
    assert dataclasses.is_dataclass(elite)
    assert chain.phases[0].target_name == "Bandit Fortress"
    assert chain.phases[1].target_name == "Blackbanner Toll-Taker"
    assert chain.phases[3].target_name == "Rusk Blackbanner"
    assert chain.history[-1].phase_id == "slay_blackbanner"
    assert chain.to_dict()["phases"][3]["target_position"] == (576.0, 320.0)
    assert chain.to_dict()["history"][4]["target_name"] == "Blackbanner Toll-Taker"
    assert boss.to_dict()["name"] == "Rusk Blackbanner"
    assert boss.to_dict()["target_hero_id"] == "wk141_hero"
    assert boss.to_dict()["memory_summaries"][0]["hero_name"] == "Astra"
    assert elite.to_dict()["name"] == "Blackbanner Toll-Taker"
    assert elite.to_dict()["affixes"] == ("banner_bearer", "ironhide")

    with pytest.raises(dataclasses.FrozenInstanceError):
        chain.name = "mutated"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        boss.name = "mutated"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        elite.name = "mutated"  # type: ignore[misc]
