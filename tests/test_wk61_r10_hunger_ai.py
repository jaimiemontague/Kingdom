"""WK61-R10: deterministic hunger AI — heroes seek food stands and buy meals."""

from __future__ import annotations

from ai.basic_ai import BasicAI
from ai.behaviors import exploration, hunger
from config import FOOD_MEAL_COST_GOLD, TAX_RATE, TILE_SIZE
from game.entities.hero import Hero, HeroState
from game.entities.neutral_buildings import FoodStand
from game.sim.timebase import set_sim_now_ms


def test_find_nearest_food_stand_sorts_by_distance_then_grid() -> None:
    hero = Hero(0.0, 0.0, name="Sorter")
    near = FoodStand(2, 2)
    far = FoodStand(10, 10)
    tie_a = FoodStand(5, 5)
    tie_b = FoodStand(5, 6)

    assert hunger.find_nearest_food_stand(hero, [far, near]) is near

    hero_mid = Hero(
        float((tie_a.center_x + tie_b.center_x) / 2),
        float((tie_a.center_y + tie_b.center_y) / 2),
        name="TieHero",
    )
    dist_a = hero_mid.distance_to(tie_a.center_x, tie_a.center_y)
    dist_b = hero_mid.distance_to(tie_b.center_x, tie_b.center_y)
    assert abs(dist_a - dist_b) < 0.01
    assert hunger.find_nearest_food_stand(hero_mid, [tie_b, tie_a]) is tie_a


def test_find_nearest_food_stand_skips_unconstructed_or_destroyed() -> None:
    hero = Hero(0.0, 0.0, name="Filter")
    broken = FoodStand(1, 1, is_constructed=False)
    dead = FoodStand(2, 2)
    dead.hp = 0
    good = FoodStand(3, 3)

    assert hunger.find_nearest_food_stand(hero, [broken, dead, good]) is good


def test_should_seek_meal_respects_critical_hp_and_gold() -> None:
    set_sim_now_ms(200_000)
    hero = Hero(0.0, 0.0, name="Gate")
    hero.gold = 50
    hero.next_meal_due_ms = 100_000
    hero.hp = 60
    hero.max_hp = 100

    assert hero.hunger_urgent is True
    assert hunger.should_seek_meal(hero) is True

    hero.hp = 14
    assert hunger.should_seek_meal(hero) is False

    hero.hp = 60
    hero.gold = FOOD_MEAL_COST_GOLD - 1
    assert hunger.should_seek_meal(hero) is False


def test_idle_hungry_hero_paths_to_food_stand() -> None:
    set_sim_now_ms(300_000)
    stand = FoodStand(8, 8)
    hero = Hero(float(stand.center_x) + TILE_SIZE * 6, float(stand.center_y), name="Hungry")
    hero.gold = 30
    hero.next_meal_due_ms = 100_000
    hero.state = HeroState.IDLE

    ai = BasicAI(llm_brain=None)
    game_state = {"buildings": [stand], "enemies": [], "heroes": [hero], "world": None}

    exploration.handle_idle(ai, hero, game_state)

    assert hero.state == HeroState.MOVING
    assert isinstance(hero.target, dict)
    assert hero.target.get("type") == "buy_meal"
    assert hero.target.get("food_stand") is stand
    assert hero.target_position is not None


def test_idle_hero_at_stand_buys_meal_immediately() -> None:
    set_sim_now_ms(400_000)
    stand = FoodStand(4, 4)
    hero = Hero(float(stand.center_x), float(stand.center_y), name="AtStand")
    hero.gold = 25
    hero.next_meal_due_ms = 100_000
    hero.is_inside_building = True
    hero.inside_building = stand
    hero.state = HeroState.IDLE

    ai = BasicAI(llm_brain=None)
    game_state = {"buildings": [stand], "enemies": [], "heroes": [hero]}

    exploration.handle_idle(ai, hero, game_state)

    assert hero.gold == 25 - FOOD_MEAL_COST_GOLD
    assert stand.stored_tax_gold == int(FOOD_MEAL_COST_GOLD * TAX_RATE)
    assert hero.hunger_urgent is False
    assert hero.state == HeroState.IDLE


def test_meal_arrival_buys_meal_and_resets_hunger() -> None:
    set_sim_now_ms(500_000)
    stand = FoodStand(6, 6)
    hero = Hero(float(stand.center_x), float(stand.center_y), name="Arrived")
    hero.gold = 40
    hero.next_meal_due_ms = 100_000
    hero.state = HeroState.MOVING
    hero.target = {"type": "buy_meal", "food_stand": stand}
    hero.target_position = (stand.center_x, stand.center_y)

    ai = BasicAI(llm_brain=None)
    game_state = {"buildings": [stand], "enemies": [], "heroes": [hero]}

    assert hunger.handle_meal_arrival(ai, hero, game_state) is True
    assert hero.gold == 40 - FOOD_MEAL_COST_GOLD
    assert stand.stored_tax_gold == int(FOOD_MEAL_COST_GOLD * TAX_RATE)
    assert hero.hunger_urgent is False
    assert hero.state == HeroState.IDLE
    assert hero.target is None


def test_redirect_interrupts_patrol_for_hunger() -> None:
    set_sim_now_ms(600_000)
    stand = FoodStand(3, 3)
    hero = Hero(0.0, 0.0, name="Patroller")
    hero.gold = 20
    hero.next_meal_due_ms = 100_000
    hero.state = HeroState.MOVING
    hero.target = {"type": "patrol"}
    hero.target_position = (TILE_SIZE * 20, TILE_SIZE * 20)

    ai = BasicAI(llm_brain=None)
    game_state = {"buildings": [stand], "enemies": [], "heroes": [hero], "world": None}

    assert hunger.maybe_redirect_for_meal(ai, hero, game_state) is True
    assert hero.target.get("type") == "buy_meal"


def test_no_food_stand_falls_through_without_stalling() -> None:
    set_sim_now_ms(700_000)
    hero = Hero(0.0, 0.0, name="Stranded")
    hero.gold = 50
    hero.next_meal_due_ms = 100_000
    hero.state = HeroState.IDLE

    ai = BasicAI(llm_brain=None)
    game_state = {"buildings": [], "enemies": [], "heroes": [hero], "world": None}

    assert hunger.maybe_seek_meal_idle(ai, hero, game_state) is False
    assert hero.state == HeroState.IDLE
    assert hero.target is None
