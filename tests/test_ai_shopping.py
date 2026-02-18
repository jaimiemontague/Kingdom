from __future__ import annotations

from types import SimpleNamespace

from ai.behaviors import shopping
from config import TILE_SIZE
from game.entities.hero import HeroState


class _Hero:
    def __init__(self, *, name: str = "Shopper", x: float = 0.0, y: float = 0.0) -> None:
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.state = HeroState.IDLE
        self.target = None
        self.target_position = None
        self.gold = 100
        self.potions = 0
        self.weapon = None
        self.armor = None
        self.last_purchase_ms = 0

    def set_target_position(self, x: float, y: float) -> None:
        self.target_position = (float(x), float(y))

    def buy_item(self, item: dict) -> bool:
        price = int(item.get("price", 0))
        if self.gold < price:
            return False
        self.gold -= price
        item_type = item.get("type")
        if item_type == "potion":
            self.potions += 1
        elif item_type == "weapon":
            self.weapon = {"attack": int(item.get("attack", 0))}
        elif item_type == "armor":
            self.armor = {"defense": int(item.get("defense", 0))}
        self.last_purchase_ms += 1
        return True


class _Economy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def hero_purchase(self, hero_name: str, item_name: str, price: int) -> None:
        self.calls.append((str(hero_name), str(item_name), int(price)))


class _JourneyBehavior:
    def __init__(self, return_value: bool = False) -> None:
        self.return_value = bool(return_value)
        self.received_purchased_types: set[str] | None = None

    def _maybe_start_journey(self, _ai, _hero, _game_state, purchased_types: set[str]) -> bool:
        self.received_purchased_types = set(purchased_types)
        return self.return_value


class _AI:
    def __init__(self, *, journey_returns: bool = False) -> None:
        self.journey_behavior = _JourneyBehavior(return_value=journey_returns)


def test_find_marketplace_with_potions_returns_only_researched_market() -> None:
    without_potions = SimpleNamespace(building_type="marketplace", potions_researched=False)
    with_potions = SimpleNamespace(building_type="marketplace", potions_researched=True)

    found = shopping.find_marketplace_with_potions([without_potions, with_potions])

    assert found is with_potions


def test_find_blacksmith_with_upgrades_respects_hero_needs() -> None:
    hero = _Hero()
    hero.weapon = {"attack": 4}
    blacksmith = SimpleNamespace(
        building_type="blacksmith",
        weapon_upgrades_researched=True,
        armor_upgrades_researched=False,
        has_better_weapon=lambda _hero: True,
        has_better_armor=lambda _hero: False,
    )

    found = shopping.find_blacksmith_with_upgrades([blacksmith], hero)

    assert found is blacksmith


def test_do_shopping_buys_potion_and_records_economy_purchase() -> None:
    ai = _AI(journey_returns=False)
    hero = _Hero(name="PotionBuyer")
    hero.gold = 40
    economy = _Economy()
    marketplace = SimpleNamespace(
        get_available_items=lambda: [
            {"name": "Healing Potion", "type": "potion", "price": 20, "effect": 60}
        ]
    )

    started_journey = shopping.do_shopping(
        ai,
        hero,
        marketplace,
        {"economy": economy},
    )

    assert started_journey is False
    assert hero.potions >= 1
    assert economy.calls == [("PotionBuyer", "Healing Potion", 20)]


def test_do_shopping_passes_purchased_types_to_journey_and_returns_value() -> None:
    ai = _AI(journey_returns=True)
    hero = _Hero(name="Upgrader")
    hero.weapon = {"attack": 2}
    hero.gold = 200
    economy = _Economy()
    blacksmith = SimpleNamespace(
        get_available_items=lambda: [
            {"name": "Iron Sword", "type": "weapon", "price": 80, "attack": 6}
        ]
    )

    started_journey = shopping.do_shopping(
        ai,
        hero,
        blacksmith,
        {"economy": economy},
    )

    assert started_journey is True
    assert ai.journey_behavior.received_purchased_types is not None
    assert "weapon" in ai.journey_behavior.received_purchased_types
    assert economy.calls == [("Upgrader", "Iron Sword", 80)]


def test_go_shopping_uses_adjacent_tile_when_available(monkeypatch) -> None:
    monkeypatch.setattr("ai.behaviors.shopping.best_adjacent_tile", lambda *_args, **_kwargs: (3, 4))
    ai = _AI(journey_returns=False)
    hero = _Hero()
    marketplace = SimpleNamespace(building_type="marketplace", center_x=999.0, center_y=888.0)

    shopping.go_shopping(
        ai,
        hero,
        "potion",
        {"buildings": [marketplace], "world": object()},
    )

    assert hero.state == HeroState.MOVING
    assert hero.target == {"type": "shopping", "item": "potion"}
    assert hero.target_position == (3 * TILE_SIZE + TILE_SIZE / 2, 4 * TILE_SIZE + TILE_SIZE / 2)
