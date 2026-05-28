"""WK61-R11: hunger meal redirect on live BasicAI tick path (no-LLM + fallback)."""

from __future__ import annotations

import math

from ai.basic_ai import BasicAI
from ai.behaviors import hunger
from ai.prompt_templates import get_fallback_decision
from ai.context_builder import ContextBuilder
from config import TILE_SIZE
from game.entities.hero import Hero, HeroState
from game.entities.neutral_buildings import FoodStand
from game.sim.timebase import set_sim_now_ms


def _move_toward_target(hero: Hero, step_px: float | None = None) -> None:
    """Simulate physical movement toward target_position."""
    if hero.target_position is None:
        return
    step = step_px if step_px is not None else TILE_SIZE * 0.5
    tx, ty = hero.target_position
    dx, dy = tx - hero.x, ty - hero.y
    dist = math.hypot(dx, dy)
    if dist <= step:
        hero.x, hero.y = tx, ty
        return
    hero.x += (dx / dist) * step
    hero.y += (dy / dist) * step


def test_update_hero_redirects_idle_hungry_hero_within_few_ticks() -> None:
    """Hungry idle hero must path to food stand via update_hero before explore fallback."""
    set_sim_now_ms(800_000)
    try:
        stand = FoodStand(12, 12)
        hero = Hero(0.0, 0.0, name="LiveIdle")
        hero.gold = 30
        hero.next_meal_due_ms = 100_000
        hero.state = HeroState.IDLE

        ai = BasicAI(llm_brain=None)
        gs = {"buildings": [stand], "enemies": [], "heroes": [hero], "world": None, "bounties": []}

        redirected = False
        for _ in range(5):
            ai.update_hero(hero, 0.05, gs)
            target = getattr(hero, "target", None)
            if isinstance(target, dict) and target.get("type") == "buy_meal":
                redirected = True
                break

        assert redirected is True
        assert hero.state == HeroState.MOVING
        assert hero.target.get("food_stand") is stand
    finally:
        set_sim_now_ms(None)


def test_update_hero_moves_closer_to_food_stand_over_ticks() -> None:
    """After redirect, simulated movement reduces distance to the food stand."""
    set_sim_now_ms(810_000)
    try:
        stand = FoodStand(10, 10)
        hero = Hero(0.0, 0.0, name="LiveMove")
        hero.gold = 25
        hero.next_meal_due_ms = 50_000
        hero.state = HeroState.IDLE

        ai = BasicAI(llm_brain=None)
        gs = {"buildings": [stand], "enemies": [], "heroes": [hero], "world": None, "bounties": []}

        start_dist = hero.distance_to(stand.center_x, stand.center_y)

        for _ in range(30):
            ai.update_hero(hero, 0.05, gs)
            _move_toward_target(hero)

        end_dist = hero.distance_to(stand.center_x, stand.center_y)
        assert end_dist < start_dist
        target = getattr(hero, "target", None)
        still_seeking = isinstance(target, dict) and target.get("type") == "buy_meal"
        ate_meal = not hero.hunger_urgent and hero.gold < 25
        assert still_seeking or ate_meal
    finally:
        set_sim_now_ms(None)


def test_update_hero_interrupts_shopping_move_for_hunger() -> None:
    """Hungry hero en route to marketplace should redirect to food stand."""
    set_sim_now_ms(820_000)
    try:
        stand = FoodStand(4, 4)
        hero = Hero(0.0, 0.0, name="ShopInterrupt")
        hero.gold = 20
        hero.next_meal_due_ms = 100_000
        hero.state = HeroState.MOVING
        hero.target = {"type": "shopping"}
        hero.target_position = (TILE_SIZE * 20, TILE_SIZE * 20)

        ai = BasicAI(llm_brain=None)
        gs = {"buildings": [stand], "enemies": [], "heroes": [hero], "world": None, "bounties": []}

        ai.update_hero(hero, 0.05, gs)

        assert hero.target.get("type") == "buy_meal"
        assert hero.target.get("food_stand") is stand
    finally:
        set_sim_now_ms(None)


def test_fallback_decision_prefers_meal_when_hungry() -> None:
    set_sim_now_ms(830_000)
    try:
        stand = FoodStand(6, 6)
        hero = Hero(float(stand.center_x), float(stand.center_y), name="Fallback")
        hero.gold = 40
        hero.next_meal_due_ms = 100_000
        hero.state = HeroState.IDLE

        gs = {"buildings": [stand], "enemies": [], "heroes": [hero], "bounties": []}
        context = ContextBuilder.build_hero_context(hero, gs)
        decision = get_fallback_decision(context)

        assert decision["action"] == "seek_meal"
    finally:
        set_sim_now_ms(None)


def test_no_food_stand_logs_once_per_hero() -> None:
    set_sim_now_ms(840_000)
    try:
        hero_a = Hero(0.0, 0.0, name="NoStandA")
        hero_b = Hero(1.0, 1.0, name="NoStandB")
        for h in (hero_a, hero_b):
            h.gold = 50
            h.next_meal_due_ms = 100_000
            h.state = HeroState.IDLE

        ai = BasicAI(llm_brain=None)
        gs = {"buildings": [], "enemies": [], "heroes": [hero_a, hero_b], "world": None}

        hunger.maybe_seek_meal_idle(ai, hero_a, gs)
        hunger.maybe_seek_meal_idle(ai, hero_a, gs)
        hunger.maybe_seek_meal_idle(ai, hero_b, gs)

        logged = ai._hunger_no_stand_logged_heroes
        assert "NoStandA" in logged
        assert "NoStandB" in logged
        assert len(logged) == 2
    finally:
        set_sim_now_ms(None)
