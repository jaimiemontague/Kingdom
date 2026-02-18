from __future__ import annotations

from ai.behaviors import exploration
from config import TILE_SIZE
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

    def set_target_position(self, x: float, y: float) -> None:
        self.target_position = (float(x), float(y))


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
