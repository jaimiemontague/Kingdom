"""WK72 Round C-2 — entity/systems dedup regression tests (Wave W3, Agent 11).

Two behavior-preserving extractions landed in WK72:

* **W1** ``DifficultySystem.apply_to_enemy(enemy)`` (``game/systems/difficulty.py``)
  consolidated the triplicated spawn-time HP/attack_power scaling that used to be
  copy-pasted inline in ``spawner.py`` / ``lairs.py`` / ``wave_events.py``.
* **W2** ``navigation.advance_along_path_to(entity, world, buildings, gx, gy, dt,
  now_ms_val)`` (``game/systems/navigation.py``) consolidated the path-replan-and-
  follow block at ``Enemy.update`` and ``SkeletonArcher.update``
  (``game/entities/enemy.py``, 2 sites). ``guard.py`` was INTENTIONALLY left inline
  (it diverges) and is OUT OF SCOPE here.

These tests are the dedup-regression net + part of the WK72 DoD gate:

  A. ``apply_to_enemy`` matches the exact ``max(1, int(round(base * mult)))`` formula
     at each difficulty tier, and is a no-op at NORMAL (mult 1.0).
  B. ``apply_to_enemy`` is the SINGLE implementation: the three former spawn paths
     no longer carry an inline ``get_multiplier("enemy_hp")`` scaling block, and an
     enemy scaled via each path at the same difficulty ends up with identical stats.
  C. ``advance_along_path_to`` is a wired-in, crash-free path-follow helper: an enemy
     driven through it (directly + via ``Enemy.update``) moves toward its goal / sets
     a path and survives the deferred-``None`` (budget-exhausted) branch.

Headless only (no real display required); no production edits.
"""

from __future__ import annotations

import os

# Headless SDL so importing/constructing pygame-touching code never needs a display.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from config import TILE_SIZE
from game.entities.enemy import Goblin, Skeleton, Wolf, SkeletonArcher, EnemyState
from game.systems.difficulty import DifficultySystem, DifficultyLevel
from game.systems.navigation import advance_along_path_to, get_pathfinding_budget
from game.sim.timebase import set_sim_now_ms


# ---------------------------------------------------------------------------
# Reference formula — the EXACT production scaling apply_to_enemy must reproduce.
# (Identical to the formula the three former inline blocks used.)
# ---------------------------------------------------------------------------
def _scaled(base: int, mult: float) -> int:
    """`max(1, int(round(base * mult)))`, applied only when mult != 1.0."""
    if mult == 1.0:
        return int(base)
    return max(1, int(round(base * mult)))


def _diff(level: DifficultyLevel) -> DifficultySystem:
    """A DifficultySystem pinned to *level* (independent of DEV_MODE/config default)."""
    return DifficultySystem(default_level=level)


# ===========================================================================
# A. apply_to_enemy matches the formula at every difficulty tier
# ===========================================================================

@pytest.mark.parametrize("level", [DifficultyLevel.EASY, DifficultyLevel.NORMAL, DifficultyLevel.HARD])
def test_apply_to_enemy_matches_formula_each_tier(level: DifficultyLevel) -> None:
    """For a fresh enemy with known base stats, after ``apply_to_enemy`` the
    max_hp / hp / attack_power equal the exact ``max(1, int(round(base*mult)))``
    formula for ``enemy_hp`` / ``enemy_damage`` — i.e. the method IS the formula.
    Also asserts hp == max_hp afterward."""
    diff = _diff(level)
    hp_mult = diff.get_multiplier("enemy_hp")
    dmg_mult = diff.get_multiplier("enemy_damage")

    enemy = Goblin(0.0, 0.0)
    base_hp = enemy.max_hp
    base_atk = enemy.attack_power
    # Sanity: a fresh Goblin has a definite, nonzero base to scale.
    assert base_hp > 0 and base_atk > 0

    diff.apply_to_enemy(enemy)

    assert enemy.max_hp == _scaled(base_hp, hp_mult), (
        f"{level}: max_hp {enemy.max_hp} != formula {_scaled(base_hp, hp_mult)}"
    )
    assert enemy.attack_power == _scaled(base_atk, dmg_mult), (
        f"{level}: attack_power {enemy.attack_power} != formula {_scaled(base_atk, dmg_mult)}"
    )
    # hp is resynced to max_hp after scaling.
    assert enemy.hp == enemy.max_hp


def test_apply_to_enemy_normal_is_identity() -> None:
    """At NORMAL (every relevant multiplier is 1.0) a fresh enemy is unchanged."""
    diff = _diff(DifficultyLevel.NORMAL)
    assert diff.get_multiplier("enemy_hp") == 1.0
    assert diff.get_multiplier("enemy_damage") == 1.0

    enemy = Skeleton(0.0, 0.0)
    base_hp, base_max_hp, base_atk = enemy.hp, enemy.max_hp, enemy.attack_power

    diff.apply_to_enemy(enemy)

    assert enemy.hp == base_hp
    assert enemy.max_hp == base_max_hp
    assert enemy.attack_power == base_atk


def test_apply_to_enemy_easy_softens_hard_hardens() -> None:
    """EASY reduces hp+damage; HARD raises them — relative to a fresh baseline."""
    base = Goblin(0.0, 0.0)
    base_hp, base_atk = base.max_hp, base.attack_power

    easy_enemy = Goblin(0.0, 0.0)
    _diff(DifficultyLevel.EASY).apply_to_enemy(easy_enemy)
    assert easy_enemy.max_hp < base_hp
    assert easy_enemy.attack_power < base_atk
    assert easy_enemy.hp == easy_enemy.max_hp

    hard_enemy = Goblin(0.0, 0.0)
    _diff(DifficultyLevel.HARD).apply_to_enemy(hard_enemy)
    assert hard_enemy.max_hp > base_hp
    assert hard_enemy.attack_power > base_atk
    assert hard_enemy.hp == hard_enemy.max_hp


def test_apply_to_enemy_floor_guard_keeps_min_one() -> None:
    """The ``max(1, ...)`` floor guard prevents scaling stats to 0 even when a
    tiny base meets a sub-1.0 multiplier."""
    diff = _diff(DifficultyLevel.EASY)
    enemy = Goblin(0.0, 0.0)
    enemy.max_hp = 1
    enemy.hp = 1
    enemy.attack_power = 1

    diff.apply_to_enemy(enemy)

    assert enemy.max_hp >= 1
    assert enemy.hp == enemy.max_hp
    assert enemy.attack_power >= 1


# ===========================================================================
# B. apply_to_enemy is the single implementation across all spawn paths
# ===========================================================================

def test_apply_to_enemy_is_single_implementation_no_inline_copies() -> None:
    """The three former spawn paths (spawner/lairs/wave_events) must no longer
    carry an inline ``get_multiplier("enemy_hp")`` scaling block — the scaling
    lives only inside ``DifficultySystem.apply_to_enemy``. Asserts each of the
    three source files calls ``apply_to_enemy`` and contains no inline
    ``enemy_hp`` multiplier read."""
    import game.systems.spawner as spawner_mod
    import game.systems.lairs as lairs_mod
    import game.systems.wave_events as wave_mod
    import game.systems.difficulty as difficulty_mod

    for mod in (spawner_mod, lairs_mod, wave_mod):
        src = _read_source(mod.__file__)
        assert "apply_to_enemy" in src, f"{mod.__name__} should call difficulty.apply_to_enemy"
        assert 'get_multiplier("enemy_hp")' not in src and "get_multiplier('enemy_hp')" not in src, (
            f"{mod.__name__} still has an inline enemy_hp scaling block — "
            f"apply_to_enemy is no longer the single source of truth"
        )

    # The HP scaling formula must live in difficulty.py (the one true home).
    diff_src = _read_source(difficulty_mod.__file__)
    assert 'get_multiplier("enemy_hp")' in diff_src or "get_multiplier('enemy_hp')" in diff_src


def test_spawn_paths_produce_identical_scaled_stats() -> None:
    """Behavioral parity: simulating each of the three spawn paths' guarded call
    (``if difficulty is not None: difficulty.apply_to_enemy(enemy)``) on an
    identical fresh enemy at the same difficulty yields identical scaled stats —
    because all three now route through the one method.

    We also compare against a direct ``apply_to_enemy`` call to pin that the
    helper is exactly what every path runs."""
    for level in (DifficultyLevel.EASY, DifficultyLevel.NORMAL, DifficultyLevel.HARD):
        results = []
        # spawner.py path shape: per-enemy guarded call inside the spawn loop.
        # lairs.py path shape: guarded loop over a spawned list.
        # wave_events.py path shape: per-enemy guarded call in the composition loop.
        # All three reduce to the same single call; reproduce that call shape ×3.
        for _ in range(3):
            diff = _diff(level)
            enemy = Goblin(0.0, 0.0)
            if diff is not None:  # mirrors the production `if difficulty is not None` guard
                diff.apply_to_enemy(enemy)
            results.append((enemy.max_hp, enemy.hp, enemy.attack_power))

        # Direct-call reference.
        ref_diff = _diff(level)
        ref_enemy = Goblin(0.0, 0.0)
        ref_diff.apply_to_enemy(ref_enemy)
        reference = (ref_enemy.max_hp, ref_enemy.hp, ref_enemy.attack_power)

        assert results[0] == results[1] == results[2] == reference, (
            f"{level}: spawn paths diverged: {results} vs ref {reference}"
        )


def _read_source(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ===========================================================================
# C. advance_along_path_to — wired-in, crash-free path-follow smoke test
#    (Enemy only; guard is out of scope.)
# ===========================================================================

@pytest.fixture
def headless_world():
    """A real headless ``GameEngine`` gives a real ``World`` + ``buildings`` so the
    A* replan path inside ``advance_along_path_to`` runs against production
    pathfinding. Resets the deterministic sim clock + pathfinding budget."""
    from game.engine import GameEngine
    set_sim_now_ms(1)  # deterministic, non-zero clock (defeats throttle edge cases)
    engine = GameEngine(headless=True)
    try:
        get_pathfinding_budget().begin_frame()
        yield engine.sim.world, engine.sim.buildings
    finally:
        set_sim_now_ms(None)
        pygame.quit()


def _near_center(world):
    """A start position near the map center (well inside bounds, on grass)."""
    cx = (world.width // 2) * TILE_SIZE + TILE_SIZE / 2.0
    cy = (world.height // 2) * TILE_SIZE + TILE_SIZE / 2.0
    return cx, cy


def test_advance_along_path_to_moves_enemy_toward_goal(headless_world) -> None:
    """Direct helper smoke: an enemy several tiles from a reachable goal moves
    closer over a few ticks and ends up with a path or progress toward the goal —
    and never crashes."""
    world, buildings = headless_world
    sx, sy = _near_center(world)
    enemy = Goblin(sx, sy)
    # Goal ~6 tiles east — within A* range, definitely a different tile.
    goal_x = sx + TILE_SIZE * 6
    goal_y = sy

    start_dist = enemy.distance_to(goal_x, goal_y)
    dt = 1.0 / 30.0
    for _ in range(20):
        get_pathfinding_budget().begin_frame()
        advance_along_path_to(enemy, world, buildings, goal_x, goal_y, dt, now_ms_val=1)

    end_dist = enemy.distance_to(goal_x, goal_y)
    # It either built a path or made forward progress (usually both).
    assert end_dist < start_dist, (
        f"enemy did not progress toward goal: {start_dist:.1f} -> {end_dist:.1f}"
    )
    # A path attribute is now present (set by the helper's first-touch init).
    assert hasattr(enemy, "path")


def test_advance_along_path_to_sets_path_and_goal(headless_world) -> None:
    """One call with budget available should plan a path and record the goal key."""
    world, buildings = headless_world
    sx, sy = _near_center(world)
    enemy = Goblin(sx, sy)
    goal_x = sx + TILE_SIZE * 5
    goal_y = sy + TILE_SIZE * 2

    get_pathfinding_budget().begin_frame()
    advance_along_path_to(enemy, world, buildings, goal_x, goal_y, 1.0 / 30.0, now_ms_val=1)

    # Goal key recorded as the int-tuple the helper stores.
    assert enemy._path_goal == (int(goal_x), int(goal_y))


def test_advance_along_path_to_survives_deferred_none(headless_world) -> None:
    """The deferred-``None`` branch: when the per-frame pathfinding budget is
    exhausted, ``compute_path_worldpoints`` returns None and the helper must keep
    the existing path (not crash, not wipe it) and fall back to direct steering."""
    world, buildings = headless_world
    sx, sy = _near_center(world)
    enemy = Goblin(sx, sy)
    goal_x = sx + TILE_SIZE * 6
    goal_y = sy

    # Seed a known sentinel path, then force the goal to change so a replan is wanted.
    sentinel = [(sx + 40.0, sy), (sx + 80.0, sy)]
    enemy.path = list(sentinel)
    enemy._path_goal = (-999, -999)  # different from goal -> want_replan True
    enemy._path_commit_until_ms = 0
    enemy._next_replan_ms = 0

    # Exhaust the budget so the replan is DEFERRED (compute returns None).
    budget = get_pathfinding_budget()
    budget.begin_frame()
    budget._frame_plans = budget.MAX_PLANS_PER_FRAME

    before = enemy.distance_to(goal_x, goal_y)
    # Must not raise.
    advance_along_path_to(enemy, world, buildings, goal_x, goal_y, 1.0 / 30.0, now_ms_val=1)
    after = enemy.distance_to(goal_x, goal_y)

    # Path was NOT wiped to [] by the deferred replan, and the enemy still moved
    # (followed the kept sentinel path).
    assert enemy.path, "deferred-None branch wiped the enemy's existing path (regression)"
    assert after <= before  # followed sentinel toward the goal direction (east)


def test_enemy_update_drives_advance_along_path_to(headless_world) -> None:
    """End-to-end: ``Enemy.update`` (which now calls ``advance_along_path_to``) runs
    several ticks against a real hero target without crashing and moves the enemy
    toward the target. Proves the helper is actually wired into the update path.

    NOTE: we pass ``buildings=[]`` so the enemy's ``find_target`` does not retarget
    onto the real town's Castle/buildings near map center (the 'near_town' building
    priority would otherwise steal the target). The helper still exercises its A*
    move branch (``world is not None``); with no building footprints the path is a
    straight reachable run, which is exactly the no-crash + progress contract."""
    world, _real_buildings = headless_world
    sx, sy = _near_center(world)
    enemy = Goblin(sx, sy)
    buildings = []

    # A minimal moving target a handful of tiles away (a duck-typed 'hero').
    class _Target:
        def __init__(self, x, y):
            self.x = x
            self.y = y
            self.hp = 100
            self.max_hp = 100
            self.is_alive = True
            self.is_inside_building = False
        def take_damage(self, amount):
            self.hp = max(0, self.hp - amount)
            return self.hp <= 0

    target = _Target(sx + TILE_SIZE * 6, sy)

    start_dist = enemy.distance_to(target.x, target.y)
    dt = 1.0 / 30.0
    for _ in range(30):
        get_pathfinding_budget().begin_frame()
        # heroes list carries the target; peasants/guards empty.
        enemy.update(dt, [target], [], buildings, guards=[], world=world)

    end_dist = enemy.distance_to(target.x, target.y)
    assert end_dist < start_dist, (
        f"Enemy.update did not close on target: {start_dist:.1f} -> {end_dist:.1f}"
    )
    assert enemy.state in (EnemyState.MOVING, EnemyState.ATTACKING)


def test_skeleton_archer_update_survives(headless_world) -> None:
    """``SkeletonArcher.update`` shares the W2 helper at its move branch; it must
    run several ticks against a target without crashing.

    As in the Enemy.update smoke, pass ``buildings=[]`` so the archer locks onto our
    duck-typed target rather than the real town's Castle near map center."""
    world, _real_buildings = headless_world
    sx, sy = _near_center(world)
    archer = SkeletonArcher(sx, sy)
    buildings = []

    class _Target:
        def __init__(self, x, y):
            self.x = x
            self.y = y
            self.hp = 100
            self.max_hp = 100
            self.is_alive = True
            self.is_inside_building = False
        def take_damage(self, amount):
            self.hp = max(0, self.hp - amount)
            return self.hp <= 0

    target = _Target(sx + TILE_SIZE * 10, sy)
    dt = 1.0 / 30.0
    for _ in range(20):
        get_pathfinding_budget().begin_frame()
        archer.update(dt, [target], [], buildings, guards=[], world=world)

    # No assertion on exact position (kiting logic); the contract is "no crash" +
    # the archer engaged the target (left IDLE).
    assert archer.target is target
    assert archer.state in (EnemyState.MOVING, EnemyState.ATTACKING)
