"""WK61 R6 — taxable gold data contract for hold-G building overlays (Agent 05)."""
from __future__ import annotations

import pytest

from config import NON_TAX_STASH_BUILDING_TYPES, TAX_RATE, TAX_STASH_BUILDING_TYPES
from game.entities.buildings.base import Building
from game.entities.buildings.castle import Castle
from game.entities.buildings.defensive import Guardhouse
from game.entities.buildings.dwellings import (
    DwarvenSettlement,
    ElvenBungalow,
    GnomeHovel,
)
from game.entities.buildings.economic import Blacksmith, Inn, Marketplace, TradingPost
from game.entities.buildings.guilds import (
    RangerGuild,
    RogueGuild,
    WarriorGuild,
    WizardGuild,
)
from game.entities.buildings.special import Fairgrounds, Library
from game.entities.buildings.temples import TempleAgrela, TempleKrolm
from game.entities.hero import Hero
from game.entities.neutral_buildings import Farm, FoodStand, House


TAX_STASH_INSTANCES = [
    ("marketplace", Marketplace(0, 0)),
    ("blacksmith", Blacksmith(0, 0)),
    ("warrior_guild", WarriorGuild(0, 0)),
    ("ranger_guild", RangerGuild(0, 0)),
    ("rogue_guild", RogueGuild(0, 0)),
    ("wizard_guild", WizardGuild(0, 0)),
    ("temple_agrela", TempleAgrela(0, 0)),
    ("temple_krolm", TempleKrolm(0, 0)),
    ("gnome_hovel", GnomeHovel(0, 0)),
    ("elven_bungalow", ElvenBungalow(0, 0)),
    ("dwarven_settlement", DwarvenSettlement(0, 0)),
    ("house", House(0, 0)),
    ("farm", Farm(0, 0)),
    ("food_stand", FoodStand(0, 0)),
]

NON_TAX_STASH_INSTANCES = [
    ("castle", Castle(0, 0)),
    ("guardhouse", Guardhouse(0, 0)),
    ("inn", Inn(0, 0)),
    ("trading_post", TradingPost(0, 0)),
    ("fairgrounds", Fairgrounds(0, 0)),
    ("library", Library(0, 0)),
]


@pytest.mark.parametrize("type_key,building", TAX_STASH_INSTANCES)
def test_tax_stash_buildings_expose_numeric_field_even_at_zero(
    type_key: str, building
) -> None:
    assert type_key in TAX_STASH_BUILDING_TYPES
    assert building.has_tax_stash_data is True
    assert hasattr(building, "stored_tax_gold")
    assert building.stored_tax_gold == 0
    assert building.get_overlay_tax_gold() == 0
    assert building.get_overlay_tax_gold() is not None


@pytest.mark.parametrize("type_key,building", NON_TAX_STASH_INSTANCES)
def test_non_tax_stash_buildings_distinguish_missing_data(type_key: str, building) -> None:
    assert type_key in NON_TAX_STASH_BUILDING_TYPES
    assert building.has_tax_stash_data is False
    assert building.get_overlay_tax_gold() is None
    assert not hasattr(building, "stored_tax_gold")


def test_zero_gold_differs_from_missing_data() -> None:
    marketplace = Marketplace(0, 0)
    guardhouse = Guardhouse(0, 0)

    assert marketplace.get_overlay_tax_gold() == 0
    assert guardhouse.get_overlay_tax_gold() is None


def test_marketplace_shop_purchase_updates_overlay_field() -> None:
    marketplace = Marketplace(0, 0)
    hero = Hero(0.0, 0.0, name="Buyer")
    hero.gold = 100
    hero.inside_building = marketplace
    hero.is_inside_building = True

    ok = hero.buy_item({"name": "Healing Potion", "type": "potion", "price": 20, "effect": 50})

    assert ok is True
    expected = int(20 * TAX_RATE)
    assert marketplace.stored_tax_gold == expected
    assert marketplace.get_overlay_tax_gold() == expected


def test_blacksmith_shop_purchase_updates_overlay_field() -> None:
    blacksmith = Blacksmith(0, 0)
    hero = Hero(0.0, 0.0, name="Smith")
    hero.gold = 200
    hero.inside_building = blacksmith
    hero.is_inside_building = True

    ok = hero.buy_item({"name": "Iron Sword", "type": "weapon", "price": 48, "attack": 5})

    assert ok is True
    expected = int(48 * TAX_RATE)
    assert blacksmith.stored_tax_gold == expected
    assert blacksmith.get_overlay_tax_gold() == expected


def test_guild_hero_tax_deposit_updates_overlay_field() -> None:
    guild = WarriorGuild(0, 0)
    guild.add_tax_gold(33)

    assert guild.stored_tax_gold == 33
    assert guild.get_overlay_tax_gold() == 33

    collected = guild.collect_taxes()
    assert collected == 33
    assert guild.get_overlay_tax_gold() == 0


def test_neutral_food_stand_passive_tax_accumulates_overlay_field() -> None:
    stand = FoodStand(0, 0)
    stand.update(60.0)

    assert stand.stored_tax_gold > 0
    assert stand.get_overlay_tax_gold() == stand.stored_tax_gold


def test_config_tax_stash_types_match_building_instances() -> None:
    instance_types = {key for key, _ in TAX_STASH_INSTANCES}
    assert instance_types.issubset(TAX_STASH_BUILDING_TYPES)


def test_generic_building_has_no_tax_stash_data() -> None:
    generic = Building(0, 0, "inn")
    assert generic.has_tax_stash_data is False
    assert generic.get_overlay_tax_gold() is None
