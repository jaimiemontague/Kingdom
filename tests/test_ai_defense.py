from __future__ import annotations

import math
from types import SimpleNamespace

from ai.behaviors import defense
from config import TILE_SIZE
from game.entities.hero import HeroState


class _FixedRNG:
    def __init__(self, *, random_value: float = 0.0) -> None:
        self.random_value = float(random_value)

    def random(self) -> float:
        return self.random_value

    def uniform(self, a: float, b: float) -> float:
        return (float(a) + float(b)) / 2.0


class _Hero:
    def __init__(self, *, x: float = 0.0, y: float = 0.0, attack_range: float = TILE_SIZE * 2) -> None:
        self.x = float(x)
        self.y = float(y)
        self.attack_range = float(attack_range)
        self.state = HeroState.IDLE
        self.target = None
        self.target_position = None
        self.home_building = None
        self.hero_class = "warrior"
        self._target_commit_until_ms = 0

    def distance_to(self, x: float, y: float) -> float:
        return math.hypot(self.x - float(x), self.y - float(y))

    def set_target_position(self, x: float, y: float) -> None:
        self.target_position = (float(x), float(y))


class _Enemy:
    def __init__(self, *, x: float, y: float, is_alive: bool = True) -> None:
        self.x = float(x)
        self.y = float(y)
        self.is_alive = bool(is_alive)

    def distance_to(self, x: float, y: float) -> float:
        return math.hypot(self.x - float(x), self.y - float(y))


class _AI:
    def __init__(self) -> None:
        self._ai_rng = _FixedRNG(random_value=0.0)


def test_defend_castle_enters_fighting_when_enemy_in_range(monkeypatch) -> None:
    monkeypatch.setattr("ai.behaviors.defense.sim_now_ms", lambda: 1_000)
    ai = _AI()
    hero = _Hero(x=0.0, y=0.0, attack_range=128.0)
    enemy = _Enemy(x=32.0, y=0.0)
    castle = SimpleNamespace(center_x=0.0, center_y=0.0, is_damaged=True)

    defense.defend_castle(ai, hero, {"enemies": [enemy]}, castle)

    assert hero.state == HeroState.FIGHTING
    assert hero.target is enemy
    assert hero._target_commit_until_ms > 1_000


def test_defend_castle_moves_toward_enemy_when_out_of_range(monkeypatch) -> None:
    monkeypatch.setattr("ai.behaviors.defense.sim_now_ms", lambda: 2_000)
    ai = _AI()
    hero = _Hero(x=0.0, y=0.0, attack_range=8.0)
    enemy = _Enemy(x=80.0, y=16.0)
    castle = SimpleNamespace(center_x=0.0, center_y=0.0, is_damaged=True)

    defense.defend_castle(ai, hero, {"enemies": [enemy]}, castle)

    assert hero.state == HeroState.MOVING
    assert hero.target is enemy
    assert hero.target_position == (80.0, 16.0)


def test_start_retreat_targets_safe_building_location() -> None:
    ai = _AI()
    hero = _Hero(x=160.0, y=160.0)
    far_castle = SimpleNamespace(building_type="castle", center_x=600.0, center_y=600.0)
    near_market = SimpleNamespace(building_type="marketplace", center_x=96.0, center_y=96.0)
    barracks = SimpleNamespace(building_type="barracks", center_x=128.0, center_y=128.0)

    defense.start_retreat(ai, hero, {"buildings": [barracks, near_market, far_castle]})

    assert hero.state == HeroState.RETREATING
    assert hero.target_position == (near_market.center_x, near_market.center_y)


def test_defend_neutral_building_if_visible_engages_enemy_when_willing(monkeypatch) -> None:
    monkeypatch.setattr("ai.behaviors.defense.sim_now_ms", lambda: 3_000)
    ai = _AI()
    hero = _Hero(x=0.0, y=0.0, attack_range=24.0)
    hero.hero_class = "warrior"
    neutral_building = SimpleNamespace(
        is_neutral=True,
        hp=100,
        is_under_attack=True,
        center_x=32.0,
        center_y=0.0,
    )
    enemy = _Enemy(x=40.0, y=0.0)

    defended = defense.defend_neutral_building_if_visible(
        ai,
        hero,
        {"buildings": [neutral_building], "enemies": [enemy]},
    )

    assert defended is True
    assert hero.state in (HeroState.MOVING, HeroState.FIGHTING)
    assert hero.target is enemy or (
        isinstance(hero.target, dict) and hero.target.get("type") == "defend_neutral"
    )
