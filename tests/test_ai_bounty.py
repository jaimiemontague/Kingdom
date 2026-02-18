from __future__ import annotations

import math
from types import SimpleNamespace

from ai.behaviors import bounty_pursuit
from config import TILE_SIZE
from game.entities.hero import HeroState
from game.systems.bounty import Bounty


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
    def __init__(
        self,
        *,
        name: str = "RangerOne",
        x: float = 0.0,
        y: float = 0.0,
        health_percent: float = 1.0,
        hero_class: str = "warrior",
    ) -> None:
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.hero_class = hero_class
        self.health_percent = float(health_percent)
        self.state = HeroState.IDLE
        self.target = None
        self.target_position = None
        self.attack_range = float(TILE_SIZE * 2)
        self.gold = 0
        self._bounty_commit_until_ms = 0
        self._last_bounty_pick_ms = 0

    def distance_to(self, x: float, y: float) -> float:
        return math.hypot(self.x - float(x), self.y - float(y))

    def add_gold(self, amount: int) -> None:
        self.gold += int(amount)

    def set_target_position(self, x: float, y: float) -> None:
        self.target_position = (float(x), float(y))

    def transfer_taxes_to_home(self) -> None:
        return None

    def start_resting(self) -> None:
        self.state = HeroState.RESTING

    def enter_building_briefly(self, *_args, **_kwargs) -> None:
        return None


class _AI:
    def __init__(self) -> None:
        self._ai_rng = _FixedRNG(random_value=0.0, uniform_value=0.0)
        self.bounty_assign_ttl_ms = 15_000
        self.bounty_pick_cooldown_ms = 2_500
        self.bounty_max_pursue_ms = 35_000
        self.bounty_claim_radius_px = TILE_SIZE * 2
        self.shopping_behavior = SimpleNamespace(do_shopping=lambda *_args, **_kwargs: False)
        self.exploration_behavior = SimpleNamespace(assign_patrol_zone=lambda *_args, **_kwargs: (0.0, 0.0))
        self._debug_log = lambda *_args, **_kwargs: None


def test_score_bounty_prefers_higher_reward_at_same_distance() -> None:
    ai = _AI()
    hero = _Hero(x=0.0, y=0.0, hero_class="warrior")
    low_reward = Bounty(4 * TILE_SIZE, 0, reward=20, bounty_type="explore")
    high_reward = Bounty(4 * TILE_SIZE, 0, reward=200, bounty_type="explore")

    low_score = bounty_pursuit.score_bounty(ai, hero, low_reward, buildings=[], enemies=[])
    high_score = bounty_pursuit.score_bounty(ai, hero, high_reward, buildings=[], enemies=[])

    assert high_score > low_score


def test_maybe_take_bounty_starts_pursuit_and_sets_commit(monkeypatch) -> None:
    monkeypatch.setattr("ai.behaviors.bounty_pursuit.sim_now_ms", lambda: 10_000)
    ai = _AI()
    hero = _Hero(name="Pursuer", x=0.0, y=0.0, health_percent=1.0)
    bounty = Bounty(3 * TILE_SIZE, 2 * TILE_SIZE, reward=100, bounty_type="explore")

    took = bounty_pursuit.maybe_take_bounty(
        ai,
        hero,
        {"bounties": [bounty], "buildings": [], "enemies": [], "world": None},
    )

    assert took is True
    assert hero.state == HeroState.MOVING
    assert hero.target["type"] == "bounty"
    assert hero.target["bounty_id"] == bounty.bounty_id
    assert hero._bounty_commit_until_ms > 10_000
    assert bounty.assigned_to == "Pursuer"


def test_maybe_take_bounty_honors_active_commit_window(monkeypatch) -> None:
    monkeypatch.setattr("ai.behaviors.bounty_pursuit.sim_now_ms", lambda: 1_500)
    ai = _AI()
    hero = _Hero(name="Committed", x=0.0, y=0.0, health_percent=1.0)
    hero._bounty_commit_until_ms = 2_000
    bounty = Bounty(2 * TILE_SIZE, 0, reward=120, bounty_type="explore")

    took = bounty_pursuit.maybe_take_bounty(
        ai,
        hero,
        {"bounties": [bounty], "buildings": [], "enemies": [], "world": None},
    )

    assert took is False
    assert hero.target is None
    assert hero.state == HeroState.IDLE


def test_handle_moving_claims_explore_bounty_within_claim_radius(monkeypatch) -> None:
    monkeypatch.setattr("ai.behaviors.bounty_pursuit.sim_now_ms", lambda: 10_000)
    ai = _AI()
    hero = _Hero(name="Claimer", x=64.0, y=64.0)
    bounty = Bounty(64.0, 64.0, reward=50, bounty_type="explore")
    hero.target = {"type": "bounty", "bounty_id": bounty.bounty_id, "started_ms": 9_000}
    hero.target_position = (64.0, 64.0)
    hero.state = HeroState.MOVING

    bounty_pursuit.handle_moving(
        ai,
        hero,
        {"bounties": [bounty], "buildings": [], "world": None},
    )

    assert bounty.claimed is True
    assert bounty.claimed_by == "Claimer"
    assert hero.target is None
    assert hero.target_position is None
    assert hero.state == HeroState.IDLE
