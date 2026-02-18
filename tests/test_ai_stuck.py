from __future__ import annotations

from types import SimpleNamespace

from ai.behaviors import stuck_recovery
from config import TILE_SIZE
from game.entities.hero import HeroState
from game.sim.hero_guardrails_tunables import UNSTUCK_MAX_ATTEMPTS_PER_TARGET


class _Hero:
    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.state = HeroState.MOVING
        self.target = {"type": "patrol"}
        self.target_position = (128.0, 128.0)
        self.path = [(1, 1)]
        self._path_goal = (128.0, 128.0)
        self.is_inside_building = False
        self.stuck_active = False
        self.stuck_since_ms = None
        self.stuck_reason = ""
        self.last_progress_ms = 0
        self.last_progress_pos = (0.0, 0.0)
        self._last_unstuck_attempt_ms = 0
        self._unstuck_attempts_for_target = 0
        self._unstuck_target_key = None
        self.unstuck_attempts = 0


class _World:
    def world_to_grid(self, _x: float, _y: float) -> tuple[int, int]:
        return (5, 5)

    def is_walkable(self, x: int, y: int) -> bool:
        return (x, y) == (6, 5)


class _AI:
    def __init__(self) -> None:
        self.exploration_behavior = SimpleNamespace(assign_patrol_zone=lambda *_args, **_kwargs: (320.0, 320.0))


def test_stuck_target_key_uses_bounty_identity() -> None:
    hero = _Hero()
    hero.target = {"type": "bounty", "bounty_id": 42, "bounty_type": "attack_lair"}

    key = stuck_recovery._stuck_target_key(hero)

    assert key == ("bounty", 42, "attack_lair")


def test_update_stuck_recovery_marks_stuck_and_repaths_on_first_attempt(monkeypatch) -> None:
    monkeypatch.setattr("ai.behaviors.stuck_recovery.sim_now_ms", lambda: 5_000)
    ai = _AI()
    hero = _Hero()

    stuck_recovery._update_stuck_and_recover(ai, hero, {"world": None, "buildings": []})

    assert hero.stuck_active is True
    assert hero.stuck_reason == "repath"
    assert hero.path == []
    assert hero._path_goal is None
    assert hero._unstuck_attempts_for_target == 1
    assert hero.unstuck_attempts == 1


def test_update_stuck_recovery_nudges_adjacent_tile_on_second_attempt(monkeypatch) -> None:
    monkeypatch.setattr("ai.behaviors.stuck_recovery.sim_now_ms", lambda: 8_000)
    ai = _AI()
    hero = _Hero()
    hero._unstuck_attempts_for_target = 1
    hero._unstuck_target_key = stuck_recovery._stuck_target_key(hero)

    stuck_recovery._update_stuck_and_recover(ai, hero, {"world": _World(), "buildings": []})

    assert hero.stuck_reason == "nudge_adjacent"
    assert hero.target_position == (6 * TILE_SIZE + TILE_SIZE / 2, 5 * TILE_SIZE + TILE_SIZE / 2)
    assert hero.state == HeroState.MOVING
    assert hero._unstuck_attempts_for_target == 2


def test_update_stuck_recovery_falls_back_to_idle_after_max_attempts(monkeypatch) -> None:
    monkeypatch.setattr("ai.behaviors.stuck_recovery.sim_now_ms", lambda: 9_000)
    ai = _AI()
    hero = _Hero()
    hero._unstuck_attempts_for_target = UNSTUCK_MAX_ATTEMPTS_PER_TARGET
    hero._unstuck_target_key = stuck_recovery._stuck_target_key(hero)

    stuck_recovery._update_stuck_and_recover(ai, hero, {"world": None, "buildings": []})

    assert hero.stuck_reason == "fallback_idle"
    assert hero.state == HeroState.IDLE
    assert hero.target is None
    assert hero.target_position is None
    assert hero.path == []
    assert hero._path_goal is None
    assert hero.stuck_active is False
