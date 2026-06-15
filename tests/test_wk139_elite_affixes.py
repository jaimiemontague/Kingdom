"""WK139 elite affix spawn-time tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config import TILE_SIZE
from game.content.elite_affixes import (
    apply_elite_affixes,
    elite_title_for_affixes,
    roll_elite_affixes,
    spawn_elite_enemy,
)
from game.entities.enemy import Goblin
from game.sim.timebase import set_sim_now_ms


@pytest.fixture(autouse=True)
def _sim_time_reset():
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(0)


def test_elite_roll_is_deterministic_for_a_spawn_key():
    first = roll_elite_affixes(spawn_key="wk139_spawn", enemy_type="goblin")
    second = roll_elite_affixes(spawn_key="wk139_spawn", enemy_type="goblin")

    assert first == second
    assert 1 <= len(first) <= 2


def test_banner_bearer_ironhide_frenzied_apply_spawn_time_effects():
    set_sim_now_ms(12_345)
    elite = Goblin(100.0, 100.0)
    ally = Goblin(100.0 + TILE_SIZE * 1.5, 100.0)

    facts = apply_elite_affixes(
        elite,
        ("banner_bearer", "ironhide", "frenzied"),
        nearby_enemies=[ally],
        now_ms=12_345,
        spawn_key="wk139_boss",
    )

    assert elite.is_elite is True
    assert elite.name == "Skull-Banner Goblin"
    assert elite.elite_affix_ids == ("banner_bearer", "ironhide", "frenzied")
    assert elite.elite_affix_names == ("Skull-Banner", "Ironhide", "Frenzied")
    assert elite.elite_title == "Skull-Banner"
    assert elite.elite_courage_bonus == 1
    assert elite.elite_spawn_markers == ("banner", "shield", "rage")
    assert elite.defense == 3
    assert elite.max_hp == 36
    assert elite.hp == 36
    assert elite.get_attack_bonus() == 2
    assert elite.effective_attack_power == 12
    assert ally.get_attack_bonus() == 2
    assert elite.elite_facts == facts
    assert facts[0]["spawn_marker"] == "banner"
    assert facts[0]["courage_bonus"] == 1
    assert facts[1]["defense_bonus"] == 3
    assert facts[2]["frenzy_attack_bonus"] == 4
    assert facts[0]["buffed_enemy_ids"] == (ally.entity_id,)

    elite.take_damage(25)
    assert elite.elite_frenzy_active is True
    assert elite.effective_attack_power == 16


def test_spawn_elite_enemy_rolls_once_and_applies_aura():
    set_sim_now_ms(9_001)
    elite_a = Goblin(50.0, 50.0)
    ally_a = Goblin(50.0 + TILE_SIZE, 50.0)
    elite_b = Goblin(50.0, 50.0)
    ally_b = Goblin(50.0 + TILE_SIZE, 50.0)

    rolled_a = spawn_elite_enemy(
        elite_a,
        nearby_enemies=[ally_a],
        now_ms=9_001,
        spawn_key="wk139_roll",
    )
    rolled_b = spawn_elite_enemy(
        elite_b,
        nearby_enemies=[ally_b],
        now_ms=9_001,
        spawn_key="wk139_roll",
    )

    assert rolled_a == rolled_b
    assert elite_a.is_elite is True
    assert elite_b.is_elite is True
    assert elite_title_for_affixes(rolled_a) == elite_a.elite_title
    assert ally_a.get_attack_bonus() == ally_b.get_attack_bonus()
