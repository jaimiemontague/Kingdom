"""WK65 Round 0 — Buildings/Systems characterization net (Agent 05).

These tests PIN the *current, observable* behavior of the gameplay-systems
surfaces that later rounds will dedup/refactor. They must be GREEN on the
unmodified code and stay GREEN after Round-0 deletions; that bracket is what
proves the deletions are inert.

What is pinned (and where the dedup lands later):
  1. Ranged-tower fire cadence  -> Round C `RangedAttackMixin`
       * Guardhouse and BallistaTower set the SINGULAR `_last_ranged_event`
         with the expected fields, deal damage to an in-range enemy, and then
         respect their cooldown (no second shot until it elapses).
       * We deliberately DO NOT assert on `_last_ranged_events` (plural) — that
         multi-arrow emission is entangled with the guardhouse and is
         explicitly deferred to Round C.
  2. Building `update()` dispatch -> Round B/C dispatch-ladder replacement
       * One observable outcome per building-type `update()` path:
         guardhouse guard-spawn, trading-post passive income, marketplace
         passive tax accrual, marketplace timed-research progress.
  3. Difficulty scaling          -> Round C `DifficultySystem.apply_to_enemy`
       * The hp/damage scaling currently triplicated across
         spawner/lairs/wave_events, pinned via the exact production formula.

Style mirrors tests/test_building.py / test_combat.py / test_enemy.py and
reuses the global research-unlock reset pattern so global tech-tree state does
not leak between tests.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config import (
    GUARDHOUSE_ARROW_COOLDOWN,
    GUARDHOUSE_ARROW_DAMAGE,
    GUARDHOUSE_ARROWS_PER_SHOT,
    GOBLIN_HP,
    GOBLIN_ATTACK,
    SKELETON_HP,
    SKELETON_ATTACK,
)
from game.entities.buildings.base import RESEARCH_UNLOCKS
from game.entities.buildings.defensive import BallistaTower, Guardhouse
from game.entities.buildings.economic import Marketplace, TradingPost
from game.entities.enemy import Goblin, Skeleton
from game.systems.difficulty import DifficultyLevel, DifficultySystem


@pytest.fixture(autouse=True)
def _reset_research_unlocks():
    """Isolate global tech-tree state so e.g. 'Defensive Spells' range bonus
    from another test cannot perturb tower range here."""
    snapshot = dict(RESEARCH_UNLOCKS)
    try:
        yield
    finally:
        RESEARCH_UNLOCKS.clear()
        RESEARCH_UNLOCKS.update(snapshot)


def _enemy_at(x: float, y: float, *, hp: int = 1000):
    """Minimal in-range enemy double: only the attrs the tower update() reads."""
    enemy = SimpleNamespace(x=float(x), y=float(y), hp=int(hp), is_alive=True)

    def _take_damage(amount: int) -> bool:
        enemy.hp = max(0, enemy.hp - int(amount))
        enemy.is_alive = enemy.hp > 0
        return enemy.hp <= 0

    enemy.take_damage = _take_damage
    return enemy


# ---------------------------------------------------------------------------
# 1. Ranged-tower fire cadence (singular `_last_ranged_event` + cooldown)
# ---------------------------------------------------------------------------

def test_guardhouse_ranged_fires_at_enemy_and_sets_singular_event() -> None:
    """Guardhouse.update fires at an in-range enemy, deals one volley of
    damage, and records the SINGULAR _last_ranged_event with expected fields."""
    gh = Guardhouse(4, 5)
    # Place the enemy exactly on the building center -> distance 0, always in range.
    enemy = _enemy_at(gh.center_x, gh.center_y)

    # Tick with a tiny dt so the arrow timer (starts at 0.0) is <= 0 and fires.
    gh.update(dt=0.001, guards_list=[], enemies=[enemy])

    # One volley = GUARDHOUSE_ARROWS_PER_SHOT arrows of GUARDHOUSE_ARROW_DAMAGE each.
    expected_volley = GUARDHOUSE_ARROW_DAMAGE * GUARDHOUSE_ARROWS_PER_SHOT
    assert enemy.hp == 1000 - expected_volley

    # Singular event is set with the documented projectile shape.
    event = gh._last_ranged_event
    assert event is not None
    assert event["type"] == "ranged_projectile"
    assert event["projectile_kind"] == "arrow"
    assert event["to_x"] == float(enemy.x)
    assert event["to_y"] == float(enemy.y)
    # Origin is anchored to the building center (offsets aside).
    assert "from_x" in event and "from_y" in event

    # Target is latched on the building.
    assert gh.target is enemy


def test_guardhouse_ranged_respects_cooldown_between_volleys() -> None:
    """After firing, the guardhouse will not fire again until the arrow
    cooldown (GUARDHOUSE_ARROW_COOLDOWN seconds) has elapsed."""
    gh = Guardhouse(4, 5)
    enemy = _enemy_at(gh.center_x, gh.center_y)
    per_volley = GUARDHOUSE_ARROW_DAMAGE * GUARDHOUSE_ARROWS_PER_SHOT

    # First volley.
    gh.update(dt=0.001, guards_list=[], enemies=[enemy])
    hp_after_first = enemy.hp
    assert hp_after_first == 1000 - per_volley

    # A tick well short of the cooldown must NOT fire again.
    gh.update(dt=GUARDHOUSE_ARROW_COOLDOWN / 4.0, guards_list=[], enemies=[enemy])
    assert enemy.hp == hp_after_first

    # Advancing past the remaining cooldown allows a second volley.
    gh.update(dt=GUARDHOUSE_ARROW_COOLDOWN, guards_list=[], enemies=[enemy])
    assert enemy.hp == hp_after_first - per_volley


def test_guardhouse_ranged_clears_event_when_no_target_in_range() -> None:
    """When the cooldown is ready but no live enemy is in range, the singular
    event is cleared and no target is latched."""
    gh = Guardhouse(4, 5)
    # Enemy far outside attack_range.
    far_enemy = _enemy_at(gh.center_x + gh.attack_range * 4, gh.center_y)

    gh.update(dt=0.001, guards_list=[], enemies=[far_enemy])

    assert far_enemy.hp == 1000  # untouched
    assert gh._last_ranged_event is None
    assert gh.target is None


def test_ballista_ranged_fires_sets_singular_event_and_respects_cooldown() -> None:
    """BallistaTower.update deals its attack_damage to an in-range enemy, sets
    the singular _last_ranged_event, and respects attack_interval cooldown."""
    ballista = BallistaTower(6, 7)
    enemy = _enemy_at(ballista.center_x, ballista.center_y)
    dmg = ballista.attack_damage
    interval = ballista.attack_interval

    # First shot (cooldown starts at 0.0).
    ballista.update(dt=0.001, enemies=[enemy])
    assert enemy.hp == 1000 - dmg

    event = ballista._last_ranged_event
    assert event is not None
    assert event["type"] == "ranged_projectile"
    assert event["to_x"] == float(enemy.x)
    assert event["to_y"] == float(enemy.y)
    assert ballista.target is enemy

    # Short tick: still on cooldown, no second shot.
    ballista.update(dt=interval / 4.0, enemies=[enemy])
    assert enemy.hp == 1000 - dmg

    # After the interval elapses, it fires again.
    ballista.update(dt=interval, enemies=[enemy])
    assert enemy.hp == 1000 - 2 * dmg


def test_unconstructed_ranged_tower_does_not_fire() -> None:
    """An in-progress (unconstructed) tower performs no ranged attack — pins the
    `if not self.is_constructed: return` guard at the top of update()."""
    ballista = BallistaTower(6, 7)
    ballista.is_constructed = False
    enemy = _enemy_at(ballista.center_x, ballista.center_y)

    ballista.update(dt=1.0, enemies=[enemy])

    assert enemy.hp == 1000
    assert ballista._last_ranged_event is None


# ---------------------------------------------------------------------------
# 2. Building update() dispatch — one observable outcome per update() path
# ---------------------------------------------------------------------------

def test_guardhouse_update_spawns_guard_when_interval_elapses() -> None:
    """The guard-spawning path: update() returns True (should_spawn) once the
    spawn_interval has elapsed and the guard cap is not yet reached."""
    gh = Guardhouse(4, 5)
    assert gh.max_guards >= 1

    # Short tick well under spawn_interval -> no spawn yet.
    assert gh.update(dt=0.1, guards_list=[], enemies=None) is False

    # Tick past the full spawn_interval -> spawn signalled.
    assert gh.update(dt=gh.spawn_interval + 0.1, guards_list=[], enemies=None) is True


def test_guardhouse_update_does_not_spawn_when_at_guard_cap() -> None:
    """At/over the guard cap, the spawn timer never advances to a spawn."""
    gh = Guardhouse(4, 5)
    full_roster = [object()] * gh.max_guards

    assert gh.update(dt=gh.spawn_interval * 5, guards_list=full_roster, enemies=None) is False


def test_trading_post_update_generates_passive_income() -> None:
    """TradingPost.update grants income_amount gold to the economy once its
    income_interval elapses, and tracks cumulative income."""
    tp = TradingPost(0, 0)
    economy = SimpleNamespace(player_gold=0)

    # Below the interval: nothing yet.
    tp.update(dt=tp.income_interval / 2.0, economy=economy)
    assert economy.player_gold == 0
    assert tp.total_income_generated == 0

    # Crossing the interval: one payout.
    tp.update(dt=tp.income_interval, economy=economy)
    assert economy.player_gold == tp.income_amount
    assert tp.total_income_generated == tp.income_amount


def test_marketplace_update_accrues_passive_tax(monkeypatch) -> None:
    """Marketplace.update accrues passive tax into the stored tax stash once the
    passive-tax interval elapses (deterministic via get_rng, sim clock pinned)."""
    clock = {"ms": 10_000}
    monkeypatch.setattr(
        "game.entities.buildings.economic.sim_now_ms", lambda: clock["ms"]
    )

    market = Marketplace(0, 0)
    start_stash = market.stored_tax_gold

    # Before the interval is reached, no accrual.
    market.update(dt=0.0, economy=None)
    assert market.stored_tax_gold == start_stash

    # Jump the clock past the scheduled passive-tax tick -> stash grows.
    clock["ms"] = market._passive_tax_next_ms + 1
    market.update(dt=0.0, economy=None)
    assert market.stored_tax_gold > start_stash


def test_marketplace_timed_research_progress_advances(monkeypatch) -> None:
    """Marketplace research_progress climbs from 0 -> 1 as the sim clock advances
    through the research duration, then advance_research completes it. Pins the
    timed-research update path."""
    clock = {"ms": 0}
    monkeypatch.setattr(
        "game.entities.buildings.economic.sim_now_ms", lambda: clock["ms"]
    )

    market = Marketplace(0, 0)
    # Fresh marketplace already has potions; force the un-researched start state
    # so start_research_potions actually begins a timer.
    market.potions_researched = False
    economy = SimpleNamespace(player_gold=500)

    assert market.start_research_potions(economy) is True
    assert economy.player_gold == 400  # research costs 100
    assert market.research_progress == 0.0

    # Halfway through the duration.
    clock["ms"] = market.research_started_ms + market.research_duration_ms // 2
    mid = market.research_progress
    assert 0.0 < mid < 1.0

    # Past the full duration: progress saturates and research completes.
    clock["ms"] = market.research_started_ms + market.research_duration_ms + 1
    assert market.research_progress == 1.0
    market.advance_research(clock["ms"])
    assert market.potions_researched is True
    assert market.research_in_progress is None


# ---------------------------------------------------------------------------
# 3. Difficulty scaling (the triplicated hp/damage scaling formula)
# ---------------------------------------------------------------------------

def _scaled(base: int, mult: float) -> int:
    """The exact production scaling formula used in spawner/lairs/wave_events:
    `max(1, int(round(base * mult)))`, applied only when mult != 1.0."""
    if mult == 1.0:
        return int(base)
    return max(1, int(round(base * mult)))


def _apply_difficulty(enemy, difficulty: DifficultySystem) -> None:
    """Mirror the (currently triplicated) per-enemy scaling so the pin tracks the
    real behavior Round C will unify into DifficultySystem.apply_to_enemy."""
    hp_mult = difficulty.get_multiplier("enemy_hp")
    dmg_mult = difficulty.get_multiplier("enemy_damage")
    if hp_mult != 1.0:
        enemy.max_hp = max(1, int(round(enemy.max_hp * hp_mult)))
        enemy.hp = enemy.max_hp
    if dmg_mult != 1.0:
        enemy.attack_power = max(1, int(round(enemy.attack_power * dmg_mult)))


def test_difficulty_multiplier_tables_normal_easy_hard() -> None:
    """The multiplier table itself: NORMAL is neutral; EASY softens hp/damage;
    HARD hardens them. (Unknown keys fall back to 1.0.)"""
    diff = DifficultySystem(default_level=DifficultyLevel.NORMAL)
    assert diff.get_multiplier("enemy_hp") == 1.0
    assert diff.get_multiplier("enemy_damage") == 1.0
    assert diff.get_multiplier("totally_unknown_key") == 1.0

    diff.set_difficulty(DifficultyLevel.EASY)
    assert diff.get_multiplier("enemy_hp") < 1.0
    assert diff.get_multiplier("enemy_damage") < 1.0

    diff.set_difficulty(DifficultyLevel.HARD)
    assert diff.get_multiplier("enemy_hp") > 1.0
    assert diff.get_multiplier("enemy_damage") > 1.0


def test_difficulty_normal_leaves_fresh_enemy_unscaled() -> None:
    """NORMAL difficulty applies no scaling: a fresh Goblin keeps its base stats."""
    diff = DifficultySystem(default_level=DifficultyLevel.NORMAL)
    goblin = Goblin(0, 0)
    base_hp = goblin.max_hp
    base_atk = goblin.attack_power

    _apply_difficulty(goblin, diff)

    assert goblin.max_hp == base_hp
    assert goblin.hp == base_hp
    assert goblin.attack_power == base_atk


def test_difficulty_easy_scales_fresh_goblin_down() -> None:
    """EASY difficulty reduces a fresh Goblin's hp and damage per the exact
    production rounding formula."""
    diff = DifficultySystem(default_level=DifficultyLevel.EASY)
    hp_mult = diff.get_multiplier("enemy_hp")
    dmg_mult = diff.get_multiplier("enemy_damage")

    goblin = Goblin(0, 0)
    base_hp = goblin.max_hp  # GOBLIN_HP
    base_atk = goblin.attack_power  # GOBLIN_ATTACK * 2

    _apply_difficulty(goblin, diff)

    assert goblin.max_hp == _scaled(base_hp, hp_mult)
    assert goblin.hp == goblin.max_hp
    assert goblin.attack_power == _scaled(base_atk, dmg_mult)
    # Sanity: base values flow from config as expected.
    assert base_hp == GOBLIN_HP
    assert base_atk == GOBLIN_ATTACK * 2


def test_difficulty_hard_scales_fresh_skeleton_up() -> None:
    """HARD difficulty raises a fresh Skeleton's hp and damage per the exact
    production rounding formula."""
    diff = DifficultySystem(default_level=DifficultyLevel.HARD)
    hp_mult = diff.get_multiplier("enemy_hp")
    dmg_mult = diff.get_multiplier("enemy_damage")

    skeleton = Skeleton(0, 0)
    base_hp = skeleton.max_hp
    base_atk = skeleton.attack_power

    _apply_difficulty(skeleton, diff)

    assert skeleton.max_hp == _scaled(base_hp, hp_mult)
    assert skeleton.hp == skeleton.max_hp
    assert skeleton.attack_power == _scaled(base_atk, dmg_mult)
    # Hard must be a strict increase over base for these non-trivial bases.
    assert skeleton.max_hp > base_hp
    assert skeleton.attack_power > base_atk
    # Sanity: skeleton base stats flow from config.
    assert base_hp == SKELETON_HP
    assert base_atk == SKELETON_ATTACK
