"""WK139 boss contract pins."""

from __future__ import annotations

import dataclasses

import pytest

from game.events import GameEventType
from game.sim.contracts import BossEncounterSnapshot, BossMemorySummary, EliteEncounterSnapshot


def test_boss_event_names_are_defined():
    assert GameEventType.BOSS_ENCOUNTER_STARTED.value == "boss_encounter_started"
    assert GameEventType.BOSS_PHASE_CHANGED.value == "boss_phase_changed"
    assert GameEventType.BOSS_ABILITY_TELEGRAPHED.value == "boss_ability_telegraphed"
    assert GameEventType.BOSS_ABILITY_RESOLVED.value == "boss_ability_resolved"
    assert GameEventType.BOSS_DEFEATED.value == "boss_defeated"
    assert GameEventType.ELITE_SPAWNED.value == "elite_spawned"


def test_boss_snapshots_are_frozen_and_primitive_only():
    minimal_boss = BossEncounterSnapshot(
        boss_id="boss_7",
        boss_type="goblin_warchief",
        name="The Goblin Warchief",
        status="active",
        current_phase="war_banner",
        current_phase_title="War Banner",
        hp_pct=0.75,
    )
    memory = BossMemorySummary(
        event="defeated_by",
        hero_id="h12",
        hero_name="Astra",
        detail="ended the war",
        at_ms=12345,
    )
    boss = BossEncounterSnapshot(
        boss_id="boss_7",
        boss_type="goblin_warchief",
        name="The Goblin Warchief",
        status="active",
        current_phase="rally",
        current_phase_title="Rally",
        hp_pct=0.42,
        position=(128.0, 96.0),
        target_hero_id="h12",
        latest_telegraph="rally",
        memory_summaries=(memory,),
    )
    minimal_elite = EliteEncounterSnapshot(
        elite_id="elite_9",
        base_type="goblin",
        name="Skull-Banner Goblin",
        status="active",
    )
    elite = EliteEncounterSnapshot(
        elite_id="elite_9",
        base_type="goblin",
        name="Skull-Banner Goblin",
        status="active",
        affixes=("banner_bearer", "ironhide"),
        position=(64.0, 64.0),
    )

    assert dataclasses.is_dataclass(minimal_boss)
    assert dataclasses.is_dataclass(boss)
    assert dataclasses.is_dataclass(minimal_elite)
    assert dataclasses.is_dataclass(elite)
    assert minimal_boss.position is None
    assert minimal_boss.target_hero_id is None
    assert minimal_boss.latest_telegraph == ""
    assert minimal_boss.memory_summaries == ()
    assert minimal_elite.affixes == ()
    assert minimal_elite.position is None
    assert boss.to_dict()["memory_summaries"][0]["hero_name"] == "Astra"
    assert boss.to_dict()["latest_telegraph"] == "rally"
    assert elite.to_dict()["affixes"] == ("banner_bearer", "ironhide")

    with pytest.raises(dataclasses.FrozenInstanceError):
        boss.name = "mutated"  # type: ignore[misc]
