from __future__ import annotations

import math
from types import SimpleNamespace

from ai.behaviors import exploration
from config import TILE_SIZE
from game.entities.hero import HeroState
from game.world import Visibility


class _FixedRNG:
    def __init__(self, *, random_value: float = 0.0, uniform_value: float = 0.0) -> None:
        self.random_value = float(random_value)
        self.uniform_value = float(uniform_value)

    def random(self) -> float:
        return self.random_value

    def uniform(self, a: float, b: float) -> float:
        lo = min(float(a), float(b))
        hi = max(float(a), float(b))
        if lo <= self.uniform_value <= hi:
            return self.uniform_value
        return (float(a) + float(b)) / 2.0


class _Hero:
    def __init__(self, *, name: str = "Scout", hero_class: str = "ranger", tile_x: int = 5, tile_y: int = 5) -> None:
        self.name = name
        self.hero_class = hero_class
        self.x = float(tile_x * TILE_SIZE + TILE_SIZE / 2)
        self.y = float(tile_y * TILE_SIZE + TILE_SIZE / 2)
        self.is_alive = True
        self.target = None
        self.target_position = None
        self._frontier_commit_until_ms = 0
        self.hp = 60
        self.max_hp = 60
        self.gold = 0
        self.potions = 0

    def set_target_position(self, x: float, y: float) -> None:
        self.target_position = (float(x), float(y))
        self.state = HeroState.MOVING

    def distance_to(self, x: float, y: float) -> float:
        return math.hypot(self.x - float(x), self.y - float(y))


class _World:
    def __init__(self, *, size: int = 11, seen_x: int = 5, seen_y: int = 5) -> None:
        self.width = size
        self.height = size
        self.visibility = [[Visibility.UNSEEN for _ in range(size)] for _ in range(size)]
        self.visibility[seen_y][seen_x] = Visibility.SEEN


class _AI:
    def __init__(self) -> None:
        self.hero_zones = {}
        self._ai_rng = _FixedRNG(random_value=0.0, uniform_value=0.0)
        self._debug_log = lambda *_args, **_kwargs: None
        self.bounty_behavior = SimpleNamespace(maybe_take_bounty=lambda *_a, **_k: False)
        self.shopping_behavior = SimpleNamespace(
            find_marketplace_with_potions=lambda *_a, **_k: None,
            find_blacksmith=lambda *_a, **_k: None,
        )


def test_find_black_fog_frontier_tiles_returns_sorted_deterministic_candidates() -> None:
    world = _World()
    hero = _Hero(tile_x=5, tile_y=5)

    candidates = exploration._find_black_fog_frontier_tiles(world, hero, max_candidates=8)

    assert len(candidates) >= 4
    assert candidates == sorted(candidates, key=lambda c: (c[2], c[1], c[0]))
    # Closest frontier directly above the seen center.
    assert candidates[0][0:2] == (5, 4)


def test_find_black_fog_frontier_tiles_honors_distance_filters() -> None:
    world = _World()
    hero = _Hero(tile_x=5, tile_y=5)

    candidates = exploration._find_black_fog_frontier_tiles(
        world,
        hero,
        max_candidates=8,
        min_dist_tiles=2.0,
    )

    assert candidates == []


def test_explore_ranger_uses_frontier_bias_and_sets_commit(monkeypatch) -> None:
    monkeypatch.setattr("ai.behaviors.exploration.sim_now_ms", lambda: 1_000)
    monkeypatch.setattr("ai.behaviors.exploration.RANGER_EXPLORE_BLACK_FOG_BIAS", 1.0)
    ai = _AI()
    hero = _Hero(name="FrontierRanger", hero_class="ranger", tile_x=5, tile_y=5)
    world = _World()
    castle = type("Castle", (), {"center_x": float(5 * TILE_SIZE), "center_y": float(5 * TILE_SIZE)})()

    exploration.explore(ai, hero, {"world": world, "castle": castle, "heroes": [hero]})

    assert hero.target is not None
    assert hero.target.get("type") == "explore_frontier"
    assert hero.target_position is not None
    assert hero._frontier_commit_until_ms > 1_000


def test_handle_idle_does_not_freeze_on_building_target_commit(monkeypatch) -> None:
    """WK61-R4-BUG-005: building is_alive must not block idle activity during enemy commit."""
    monkeypatch.setattr("ai.behaviors.exploration.sim_now_ms", lambda: 10_000)
    ai = _AI()
    hero = _Hero(name="Warrior", hero_class="warrior", tile_x=5, tile_y=5)
    hero.state = HeroState.IDLE
    hero._target_commit_until_ms = 20_000
    hero.target = type(
        "Building",
        (),
        {"is_alive": True, "building_type": "marketplace", "center_x": hero.x, "center_y": hero.y},
    )()
    castle = type("Castle", (), {"center_x": float(5 * TILE_SIZE), "center_y": float(5 * TILE_SIZE)})()
    enemy = type("Enemy", (), {"is_alive": True, "x": hero.x + TILE_SIZE, "y": hero.y})()

    exploration.handle_idle(
        ai,
        hero,
        {
            "world": None,
            "castle": castle,
            "heroes": [hero],
            "buildings": [],
            "enemies": [enemy],
            "bounties": [],
        },
    )

    assert hero.state == HeroState.MOVING
    assert hero.target is enemy


def test_handle_idle_warrior_explores_when_in_zone_without_target(monkeypatch) -> None:
    monkeypatch.setattr("ai.behaviors.exploration.sim_now_ms", lambda: 1_000)
    ai = _AI()
    hero = _Hero(name="Warrior", hero_class="warrior", tile_x=5, tile_y=5)
    hero.state = HeroState.IDLE
    castle = type("Castle", (), {"center_x": float(5 * TILE_SIZE), "center_y": float(5 * TILE_SIZE)})()

    exploration.handle_idle(
        ai,
        hero,
        {"world": None, "castle": castle, "heroes": [hero], "buildings": [], "enemies": [], "bounties": []},
    )

    assert hero.target_position is not None
    assert hero.state == HeroState.MOVING
