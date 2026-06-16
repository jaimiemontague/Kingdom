"""WK144 elite-affix content and spawn-time validation tests."""

from __future__ import annotations

import pytest

from game.content.elite_affixes import (
    ELITE_AFFIX_DEFS,
    apply_elite_affixes,
    get_elite_affix_def,
    roll_elite_affixes,
)
from game.entities.enemy import BanditLord, Goblin
from game.sim.determinism import get_rng
from game.sim.timebase import set_sim_now_ms


EXPECTED_AFFIX_IDS = {
    "banner_bearer",
    "ironhide",
    "frenzied",
    "skirmisher",
    "gravebound",
    "venomous",
    "gold_taker",
    "oathbound",
}


@pytest.fixture(autouse=True)
def _sim_time_reset():
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(0)


def test_elite_affix_kit_has_eight_readable_entries_with_bounded_modifiers():
    assert set(ELITE_AFFIX_DEFS) == EXPECTED_AFFIX_IDS

    seen_display_names: set[str] = set()
    seen_spawn_markers: set[str] = set()

    for affix_id, affix in ELITE_AFFIX_DEFS.items():
        assert affix.affix_id == affix_id
        assert affix.display_name.strip()
        assert affix.description.strip()
        assert affix.tell.strip()
        assert affix.counterplay.strip()
        assert affix.display_name not in seen_display_names
        seen_display_names.add(affix.display_name)

        marker = affix.spawn_marker.strip()
        assert marker
        assert marker not in seen_spawn_markers
        seen_spawn_markers.add(marker)

        assert 0 <= affix.attack_bonus <= 2
        assert 0 <= affix.defense_bonus <= 3
        assert 0.85 <= affix.speed_multiplier <= 1.20
        assert 1.0 <= affix.hp_multiplier <= 1.25
        assert 0 <= affix.aura_attack_bonus <= 2
        assert 0.0 <= affix.aura_radius_tiles <= 5.0
        assert 0.0 <= affix.frenzy_threshold <= 0.5
        assert 0 <= affix.frenzy_attack_bonus <= 4
        assert 0 <= affix.courage_bonus <= 2

        looked_up = get_elite_affix_def(affix_id)
        assert looked_up is affix


def test_elite_affix_roll_is_deterministic_for_spawn_key_and_rng():
    first = roll_elite_affixes(spawn_key="wk144_spawn", enemy_type="goblin")
    second = roll_elite_affixes(spawn_key="wk144_spawn", enemy_type="goblin")

    assert first == second
    assert 1 <= len(first) <= 2
    assert len(set(first)) == len(first)
    assert set(first).issubset(EXPECTED_AFFIX_IDS)

    rng_a = get_rng("wk144_elite_roll")
    rng_b = get_rng("wk144_elite_roll")
    third = roll_elite_affixes(spawn_key="ignored_a", enemy_type="bandit", rng=rng_a)
    fourth = roll_elite_affixes(spawn_key="ignored_b", enemy_type="dragon", rng=rng_b)

    assert third == fourth
    assert len(set(third)) == len(third)
    assert set(third).issubset(EXPECTED_AFFIX_IDS)


def test_apply_elite_affixes_keeps_boss_names_and_marks_normal_elites_readably():
    set_sim_now_ms(12_345)

    goblin = Goblin(96.0, 96.0)
    normal_facts = apply_elite_affixes(
        goblin,
        ("skirmisher", "venomous"),
        now_ms=12_345,
        spawn_key="wk144_goblin",
    )

    assert goblin.is_elite is True
    assert goblin.name == "Skirmisher Goblin"
    assert goblin.elite_name == "Skirmisher Goblin"
    assert goblin.elite_affix_ids == ("skirmisher", "venomous")
    assert goblin.elite_affix_names == ("Skirmisher", "Venomous")
    assert goblin.elite_title == "Skirmisher"
    assert goblin.elite_spawn_markers == ("skirm", "venom")
    assert goblin.speed > 90.0
    assert goblin.get_attack_bonus() == 3
    assert normal_facts[0]["tell"].strip()
    assert normal_facts[0]["counterplay"].strip()
    assert normal_facts[1]["tell"].strip()
    assert normal_facts[1]["counterplay"].strip()

    boss = BanditLord(160.0, 160.0)
    original_name = boss.name
    boss_facts = apply_elite_affixes(
        boss,
        ("oathbound",),
        now_ms=12_345,
        spawn_key="wk144_boss",
    )

    assert boss.is_elite is True
    assert boss.name == original_name
    assert boss.elite_name == f"Oathbound {original_name}"
    assert boss.elite_affix_ids == ("oathbound",)
    assert boss.elite_affix_names == ("Oathbound",)
    assert boss.elite_title == "Oathbound"
    assert boss_facts[0]["tell"].strip()
    assert boss_facts[0]["counterplay"].strip()
