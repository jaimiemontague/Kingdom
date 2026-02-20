from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.entities.buildings.base import Building, RESEARCH_UNLOCKS
from game.entities.buildings.economic import Blacksmith, Marketplace
from game.entities.buildings.guilds import WarriorGuild


@pytest.fixture(autouse=True)
def _reset_research_unlocks() -> None:
    snapshot = dict(RESEARCH_UNLOCKS)
    try:
        yield
    finally:
        RESEARCH_UNLOCKS.clear()
        RESEARCH_UNLOCKS.update(snapshot)


def test_mark_unconstructed_then_start_construction_changes_targetable_state() -> None:
    building = Building(2, 3, "marketplace")
    building.mark_unconstructed()

    assert building.is_constructed is False
    assert building.construction_started is False
    assert building.hp == 1
    assert building.is_targetable is False

    building.start_construction()
    assert building.construction_started is True
    assert building.is_targetable is True


def test_apply_work_completes_construction_and_caps_hp() -> None:
    building = Building(0, 0, "inn")
    building.mark_unconstructed()
    building.start_construction()

    done = building.apply_work(dt=1.0, percent_per_sec=1.0)

    assert done is True
    assert building.is_constructed is True
    assert building.hp == building.max_hp


def test_take_damage_sets_recent_under_attack_window(monkeypatch) -> None:
    now = {"value": 1_000}
    monkeypatch.setattr("game.entities.buildings.base.sim_now_ms", lambda: now["value"])
    building = Building(0, 0, "marketplace")

    building.take_damage(10)
    assert building.hp == building.max_hp - 10

    now["value"] = 3_500
    assert building.is_under_attack is True

    now["value"] = 4_200
    assert building.is_under_attack is False


def test_building_rect_hit_test_and_center_coordinates() -> None:
    building = Building(1, 2, "marketplace")
    rect = building.get_rect()

    assert rect.collidepoint(building.world_x + 1, building.world_y + 1) is True
    assert rect.collidepoint(building.world_x - 1, building.world_y - 1) is False
    assert building.center_x == building.world_x + building.width / 2
    assert building.center_y == building.world_y + building.height / 2


def test_hiring_building_mixin_tracks_hires_and_taxes() -> None:
    guild = WarriorGuild(0, 0)
    assert guild.can_hire() is True

    guild.hire_hero()
    guild.add_tax_gold(45)
    collected = guild.collect_taxes()

    assert guild.heroes_hired == 1
    assert collected == 45
    assert guild.stored_tax_gold == 0


def test_blacksmith_research_unlocks_upgraded_items() -> None:
    blacksmith = Blacksmith(0, 0)
    economy = SimpleNamespace(player_gold=1_000)

    ok = blacksmith.research("Weapon Upgrades", economy=economy)
    assert ok is True
    assert economy.player_gold == 800  # research cost $200
    # wk15: research is timed; advance timer to completion then check items.
    blacksmith.advance_research(blacksmith.research_started_ms + blacksmith.research_duration_ms + 1)
    item_names = {item["name"] for item in blacksmith.get_available_items()}
    assert "Steel Sword" in item_names
    assert "Mithril Blade" in item_names


def test_marketplace_reads_global_advanced_healing_unlock() -> None:
    RESEARCH_UNLOCKS["Advanced Healing"] = True
    marketplace = Marketplace(0, 0)
    item_names = [item["name"] for item in marketplace.get_available_items()]

    assert marketplace.potions_researched is True
    assert marketplace.potion_price == 15
    assert "Healing Potion" in item_names
