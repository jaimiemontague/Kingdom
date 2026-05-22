"""WK61-R8: marketplace taxable gold accrues on real deferred potion purchase path."""

from __future__ import annotations

from types import SimpleNamespace

from ai.behaviors import shopping
from config import TAX_RATE
from game.entities.buildings.economic import Marketplace
from game.entities.hero import Hero


class _JourneyBehavior:
    def _maybe_start_journey(self, _ai, _hero, _game_state, _purchased_types: set[str]) -> bool:
        return False


class _AI:
    def __init__(self) -> None:
        self.journey_behavior = _JourneyBehavior()


def test_marketplace_potion_purchase_via_do_shopping_deposits_tax() -> None:
    """Live path: hero exits shop, then do_shopping buys without inside_building set."""
    marketplace = Marketplace(0, 0)
    marketplace.potions_researched = True
    marketplace.potion_price = 20

    hero = Hero(0.0, 0.0, name="PotionBuyer")
    hero.gold = 35
    hero.potions = 0
    hero.is_inside_building = False
    hero.inside_building = None
    hero.pending_task = "shopping"
    hero.pending_task_building = marketplace

    economy = SimpleNamespace(calls=[])

    def hero_purchase(hero_name: str, item_name: str, price: int) -> int:
        economy.calls.append((hero_name, item_name, price))
        return int(price * TAX_RATE)

    economy.hero_purchase = hero_purchase

    ai = _AI()
    started_journey = shopping.do_shopping(
        ai,
        hero,
        marketplace,
        {"economy": economy},
    )

    assert started_journey is False
    assert hero.potions == 1
    assert economy.calls == [("PotionBuyer", "Healing Potion", 20)]
    expected_tax = int(marketplace.potion_price * TAX_RATE)
    assert marketplace.stored_tax_gold == expected_tax
    assert marketplace.get_overlay_tax_gold() == expected_tax


def test_marketplace_potion_buy_item_after_pop_out_uses_pending_shop() -> None:
    """Deferred finalize calls buy_item directly with pending_task_building only."""
    marketplace = Marketplace(0, 0)
    hero = Hero(0.0, 0.0, name="Buyer")
    hero.gold = 100
    hero.is_inside_building = False
    hero.inside_building = None
    hero.pending_task = "shopping"
    hero.pending_task_building = marketplace

    ok = hero.buy_item(
        {"name": "Healing Potion", "type": "potion", "price": 20, "effect": 50},
    )

    assert ok is True
    assert marketplace.stored_tax_gold == int(20 * TAX_RATE)
