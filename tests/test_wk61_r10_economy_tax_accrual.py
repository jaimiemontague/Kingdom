"""WK61-R10: faster neutral tax accrual + hero meal purchases at food stands."""

from __future__ import annotations

from types import SimpleNamespace

from ai.behaviors import shopping
from config import FOOD_MEAL_COST_GOLD, TAX_RATE
from game.entities.buildings.economic import Marketplace
from game.entities.hero import Hero
from game.entities.neutral_buildings import FoodStand
from game.sim.timebase import set_sim_now_ms


class _JourneyBehavior:
    def _maybe_start_journey(self, _ai, _hero, _game_state, _purchased_types: set[str]) -> bool:
        return False


class _AI:
    def __init__(self) -> None:
        self.journey_behavior = _JourneyBehavior()


def test_food_stand_passive_tax_accrual_r10_rate() -> None:
    """FoodStand at 10/min should accrue >= 9g after 60 sim seconds."""
    stand = FoodStand(5, 5)
    stand.update(60.0)
    assert stand.stored_tax_gold >= 9


def test_marketplace_potion_purchase_still_deposits_tax() -> None:
    """R8 deferred shopping path unchanged after R10 economy tuning."""
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
    expected_tax = int(marketplace.potion_price * TAX_RATE)
    assert marketplace.stored_tax_gold == expected_tax


def test_buy_meal_at_food_stand_deposits_tax_and_resets_hunger() -> None:
    set_sim_now_ms(100_000)
    stand = FoodStand(10, 10)
    hero = Hero(float(stand.center_x), float(stand.center_y), name="HungryHero")
    hero.gold = 25
    hero.next_meal_due_ms = 50_000
    hero.is_inside_building = True
    hero.inside_building = stand

    assert hero.hunger_urgent is True
    assert hero.buy_meal_at_food_stand(stand) is True
    assert hero.gold == 25 - FOOD_MEAL_COST_GOLD
    assert stand.stored_tax_gold == int(FOOD_MEAL_COST_GOLD * TAX_RATE)
    assert hero.hunger_urgent is False
