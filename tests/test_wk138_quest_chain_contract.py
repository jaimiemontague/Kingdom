"""WK138 quest-chain contract pins.

These are read-model / event-vocabulary guards only. The gameplay runtime lives
in `game.systems.quest_chain`; this contract stays primitive-only, frozen, and
empty-default so the no-chain path remains a no-op.
"""

from __future__ import annotations

import dataclasses

import pytest

from game.events import GameEventType
from game.sim.contracts import (
    QuestChainHistorySummary,
    QuestChainPhaseSnapshot,
    QuestChainSnapshot,
)


def test_chain_event_names_are_defined():
    assert GameEventType.QUEST_CHAIN_OFFERED.value == "quest_chain_offered"
    assert GameEventType.QUEST_CHAIN_ACCEPTED.value == "quest_chain_accepted"
    assert GameEventType.QUEST_CHAIN_PHASE_STARTED.value == "quest_chain_phase_started"
    assert GameEventType.QUEST_CHAIN_PHASE_COMPLETED.value == "quest_chain_phase_completed"
    assert GameEventType.QUEST_CHAIN_COMPLETED.value == "quest_chain_completed"
    assert GameEventType.QUEST_CHAIN_FAILED.value == "quest_chain_failed"


def test_chain_snapshots_are_frozen_and_primitive_only():
    history = QuestChainHistorySummary(
        event="phase_completed",
        phase_id="collect_relic",
        phase_title="Recover the relic",
        status="completed",
        hero_id="h12",
        target_id="poi_ancient_ruins",
        target_name="Ancient Ruins",
        target_position=(120.0, 240.0),
        at_ms=12345,
    )
    phase = QuestChainPhaseSnapshot(
        phase_id="collect_relic",
        title="Recover the relic",
        objective_type="collect_item",
        status="completed",
        assigned_hero_id="h12",
        target_id="item_relic",
        target_name="Relic of the Old Shrine",
        target_position=(120.0, 240.0),
        history=(history,),
    )
    chain = QuestChainSnapshot(
        chain_id=7,
        chain_type="relic_of_the_old_shrine",
        name="Relic of the Old Shrine",
        status="active",
        assigned_hero_id="h12",
        current_phase_id="collect_relic",
        current_phase_title="Recover the relic",
        current_objective_type="collect_item",
        target_id="item_relic",
        target_name="Relic of the Old Shrine",
        target_position=(120.0, 240.0),
        phases=(phase,),
        history=(history,),
    )

    assert dataclasses.is_dataclass(history)
    assert dataclasses.is_dataclass(phase)
    assert dataclasses.is_dataclass(chain)
    assert chain.history[0].event == "phase_completed"
    assert chain.phases[0].objective_type == "collect_item"
    assert chain.to_dict()["phases"][0]["history"][0]["target_name"] == "Ancient Ruins"

    with pytest.raises(dataclasses.FrozenInstanceError):
        chain.name = "mutated"  # type: ignore[misc]
