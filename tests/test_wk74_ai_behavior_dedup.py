"""
WK74 Round C-2b — focused behavior tests for the two AI-behavior dedup helpers.

WK74 extracted two of the most-duplicated AI behavior blocks into single
helpers, leaving the AI's 300-tick decision digest byte-identical (the perfect
guard, ``b73961...`` in ``test_wk67_ai_boundary``). The digest already proves
behavior is unchanged at every wired call site; these tests pin the *contract*
of the two helpers directly so a future edit that drifts the math (but somehow
slips past the digest) is caught locally and legibly.

  (W1) ``route_to_building(hero, world, buildings, building)`` in
       ``ai/behaviors/movement.py`` — sets ``hero.target_position`` to the
       adjacent-tile world-center when ``best_adjacent_tile`` returns a tile,
       else the building center; also falls back to the building center when
       ``world`` is falsy.

  (W2) ``engage(hero, enemy, now_ms, *, set_fighting=False, set_position=True)``
       and ``_commit_until_ms(now_ms)`` in ``ai/behaviors/defense.py`` — sets
       ``hero.target = enemy``, refreshes the anti-oscillation commit deadline,
       optionally flips ``HeroState.FIGHTING``, optionally steers toward the
       enemy via ``set_target_position``.

This is Agent 11's WAVE W3 deliverable. No production code is touched.
"""
from __future__ import annotations

import pytest

from config import TILE_SIZE
from game.entities.hero import HeroState
from game.sim.hero_guardrails_tunables import TARGET_COMMIT_WINDOW_S

import ai.behaviors.movement as movement
from ai.behaviors.movement import route_to_building
from ai.behaviors.defense import engage, _commit_until_ms


# --------------------------------------------------------------------------- #
# Minimal fakes
# --------------------------------------------------------------------------- #
class _FakeHero:
    """Bare hero surface the helpers touch — no game.entities.Hero machinery."""

    def __init__(self, x: float = 100.0, y: float = 200.0) -> None:
        self.x = x
        self.y = y
        self.target_position = None
        self.target = None
        self._target_commit_until_ms = 0
        self.state = HeroState.IDLE
        self.set_target_position_calls: list[tuple] = []

    def set_target_position(self, px, py):  # noqa: D401 - recording stub
        self.set_target_position_calls.append((px, py))


class _FakeBuilding:
    def __init__(self, center_x: float = 512.0, center_y: float = 384.0) -> None:
        self.center_x = center_x
        self.center_y = center_y


class _FakeEnemy:
    def __init__(self, x: float = 333.0, y: float = 444.0) -> None:
        self.x = x
        self.y = y


# --------------------------------------------------------------------------- #
# route_to_building — ai/behaviors/movement.py
# --------------------------------------------------------------------------- #
def test_route_to_building_uses_adjacent_tile_world_center(monkeypatch):
    """When best_adjacent_tile returns (gx, gy), target_position is its center."""
    gx, gy = 7, 11
    monkeypatch.setattr(
        movement, "best_adjacent_tile", lambda *a, **k: (gx, gy)
    )

    hero = _FakeHero()
    building = _FakeBuilding()
    # truthy non-empty world sentinel so the helper enters the adj-tile branch
    route_to_building(hero, world=object(), buildings=[building], building=building)

    expected = (
        gx * TILE_SIZE + TILE_SIZE / 2,
        gy * TILE_SIZE + TILE_SIZE / 2,
    )
    assert hero.target_position == expected


def test_route_to_building_falls_back_to_building_center_when_no_adj(monkeypatch):
    """When best_adjacent_tile returns None, target_position is the building center."""
    monkeypatch.setattr(movement, "best_adjacent_tile", lambda *a, **k: None)

    hero = _FakeHero()
    building = _FakeBuilding(center_x=640.0, center_y=480.0)
    route_to_building(hero, world=object(), buildings=[building], building=building)

    assert hero.target_position == (building.center_x, building.center_y)


def test_route_to_building_falls_back_to_building_center_when_world_falsy(monkeypatch):
    """A falsy world short-circuits straight to the building center.

    best_adjacent_tile must NOT be consulted in this branch.
    """
    called = {"hit": False}

    def _should_not_run(*a, **k):
        called["hit"] = True
        return (1, 1)

    monkeypatch.setattr(movement, "best_adjacent_tile", _should_not_run)

    hero = _FakeHero()
    building = _FakeBuilding(center_x=128.0, center_y=256.0)
    route_to_building(hero, world=None, buildings=[building], building=building)

    assert hero.target_position == (building.center_x, building.center_y)
    assert called["hit"] is False


# --------------------------------------------------------------------------- #
# engage / _commit_until_ms — ai/behaviors/defense.py
# --------------------------------------------------------------------------- #
def _expected_commit(now_ms: int) -> int:
    return int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))


def test_commit_until_ms_matches_inline_formula():
    for now in (0, 1, 1234, 999999, 5_000_000):
        assert _commit_until_ms(now) == _expected_commit(now)


def test_engage_defaults_set_target_commit_and_position():
    hero = _FakeHero()
    enemy = _FakeEnemy(x=321.0, y=654.0)
    now = 10_000

    engage(hero, enemy, now)

    assert hero.target is enemy
    assert hero._target_commit_until_ms == _expected_commit(now)
    # default set_position=True -> steered toward the enemy's coords exactly once
    assert hero.set_target_position_calls == [(enemy.x, enemy.y)]
    # default set_fighting=False -> state untouched
    assert hero.state == HeroState.IDLE


def test_engage_set_fighting_true_flips_state():
    hero = _FakeHero()
    enemy = _FakeEnemy()
    now = 42_000

    engage(hero, enemy, now, set_fighting=True)

    assert hero.state == HeroState.FIGHTING
    assert hero.target is enemy
    assert hero._target_commit_until_ms == _expected_commit(now)


def test_engage_set_fighting_false_leaves_state_unchanged():
    hero = _FakeHero()
    hero.state = HeroState.MOVING  # pre-existing non-default state
    enemy = _FakeEnemy()

    engage(hero, enemy, 7_777, set_fighting=False)

    assert hero.state == HeroState.MOVING


def test_engage_set_position_false_skips_set_target_position():
    hero = _FakeHero()
    enemy = _FakeEnemy()
    now = 5_555

    engage(hero, enemy, now, set_fighting=True, set_position=False)

    # in-range engage variant: FIGHTING flipped, but no steering call
    assert hero.set_target_position_calls == []
    assert hero.state == HeroState.FIGHTING
    assert hero.target is enemy
    assert hero._target_commit_until_ms == _expected_commit(now)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
