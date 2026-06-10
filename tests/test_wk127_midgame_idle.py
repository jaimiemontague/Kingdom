"""WK127-T3 — midgame idle/defend-pin regression tests (Agent 06, AIBehaviorDirector).

WK127-BUG-001: heroes (rangers/wizards first) freeze near their guild after
~15 min of play. Root cause (confirmed by the WK127 35-sim-min realistic soak):

  1. ``ai/task_router.py`` hijacks every tick into ``defend_home_building``
     whenever ``hero.home_building.is_damaged`` (= ANY missing HP, forever).
     With no enemy within 5 tiles, ``defense.py`` parks the hero IDLE within
     2 tiles of the guild — a permanent statue while peasant repairs stall.
     The castle branch has the same ``is_damaged`` flaw. Fix (WK127-T1):
     gate both branches on ``defense.building_threatened`` (recently damaged
     OR live enemy near the building) instead of ``is_damaged``.
  2. The zero-purchase shopping loop: the "want" predicates fire below the
     buy rules (wants potions<5 / fallback <3 vs buy <2; naked gold>=50
     blacksmith branch), so a full-HP hero with gold and max gear orbits the
     marketplace forever. Fix (WK127-T2): a sim-time zero-purchase cooldown
     stamped by ``do_shopping`` + predicate alignment.

THE TESTS (deterministic, headless, dummy SDL):
  * test_damaged_guild_does_not_pin_heroes  — FAILS pre-fix (the T1 pin).
  * test_heroes_still_defend_threatened_guild — passes pre- AND post-fix
    (proves T1 did not neuter real defense).
  * test_damaged_castle_does_not_pin_heroes — r2/T6: FAILS if the CASTLE half
    of the T1 gate reverts to ``is_damaged``.
  * test_wounded_hero_rests_in_chipped_home_guild — r2/T7: FAILS if the T5
    rest gates (hero_rest.py) revert to ``is_damaged``; also asserts the
    fresh-hit (is_under_attack) refusal.
  * test_zero_purchase_shopping_cooldown    — FAILS pre-fix (the T2 loop).

Engine construction mirrors ``tests/test_wk124_ranger_idle_soak.py`` (headless
GameEngine + no-LLM BasicAI + neutralized spawner/lairs). Seeding gotcha from
that soak applies: ``SimEngine.__init__`` re-seeds from ``config.SIM_SEED``
(env ``SIM_SEED``, default 1), so the default world is identical in solo and
full-suite runs; we re-seed the stream AFTER construction for stability.

Guild damage is pinned to ``max_hp - 20`` each tick (mirrors stalled peasant
repairs) WITHOUT touching ``last_damage_time_ms`` — so ``is_damaged`` is True
while ``is_under_attack`` (the 3 s recently-damaged window) stays False, which
is exactly the state that pinned heroes in the live soak.

RUNTIME: ~35s total for all three tests on the dev box (3 + 0.5 + 2 sim-min
of headless 60 Hz ticks).
"""

from __future__ import annotations

import os
import statistics

# Headless-friendly drivers + deterministic sim BEFORE engine/config import, so
# config.DETERMINISTIC_SIM is read True and sprite/font loads work without a
# display. Mirrors tests/test_wk124_ranger_idle_soak.py.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("DETERMINISTIC_SIM", "1")

import pygame

from config import SIM_TICK_HZ, TILE_SIZE
from game.engine import GameEngine
from game.entities import RangerGuild
from game.entities.buildings.economic import Marketplace
from game.entities.enemy import Enemy
from game.entities.hero import Hero, HeroState

_SEED = 20260609
# Far-future meal deadline (sim ms): keeps hunger trips out of the measurement.
_NO_HUNGER_MS = 10**12
# "Pinned" = IDLE within this many tiles of the guild center (soak measured
# pre-fix heroes at 0.7-1.9 tiles; defend parks at <= 2 tiles).
_PIN_NEAR_TILES = 3.0


def _build_engine() -> GameEngine:
    """Deterministic headless engine with a no-LLM BasicAI (fallback decision path)."""
    from ai.basic_ai import BasicAI
    from game.sim.determinism import set_sim_seed

    engine = GameEngine(headless=True)
    # SimEngine.__init__ already re-seeded from config.SIM_SEED; pin the
    # post-construction RNG stream explicitly so test edits upstream of this
    # point cannot shift the measured windows.
    set_sim_seed(_SEED)
    engine.ai_controller = BasicAI(llm_brain=None)
    # Isolate the behaviors under test: no spawner/lair enemy injection
    # (test-only monkeypatch on the instance — no production edit).
    engine.sim.spawner.spawn = lambda dt: []  # type: ignore[assignment]
    engine.sim.lair_system.spawn_enemies = lambda dt, buildings: []  # type: ignore[assignment]
    return engine


def _castle(engine: GameEngine):
    return next(b for b in engine.buildings if getattr(b, "building_type", None) == "castle")


def _add_guild(engine: GameEngine) -> RangerGuild:
    castle = _castle(engine)
    guild = RangerGuild(int(castle.grid_x) - 5, int(castle.grid_y) + 3)
    guild.is_constructed = True
    guild.construction_started = True
    if hasattr(guild, "set_event_bus") and getattr(engine, "event_bus", None):
        guild.set_event_bus(engine.event_bus)
    engine.buildings.append(guild)
    return guild


def _add_hero(engine: GameEngine, guild, hero_class: str, idx: int, *, gold: int = 0) -> Hero:
    h = Hero(
        guild.center_x + TILE_SIZE * (1 + idx),
        guild.center_y + TILE_SIZE,
        hero_class=hero_class,
        hero_id=f"wk127_{hero_class}_{idx}",
        name=f"Wk127{hero_class.capitalize()}{idx}",
    )
    h.home_building = guild
    h.gold = gold
    h.next_meal_due_ms = _NO_HUNGER_MS
    engine.heroes.append(h)
    return h


def _chip(building, amount: int = 20) -> None:
    """Force ``is_damaged`` True WITHOUT arming ``is_under_attack`` (no
    last_damage_time_ms write) — the stalled-repair state from the soak."""
    building.hp = building.max_hp - amount


def test_damaged_guild_does_not_pin_heroes():
    """WK127-T1: a chipped guild with NO enemies must not statue its heroes.

    Pre-fix: ``is_damaged`` hijacks the router every tick -> heroes pinned IDLE
    within ~2 tiles of the guild for ~100% of late samples (soak: 1.00).
    Post-fix: no threat -> normal pipeline (explore/roam/patrol) -> low pinned
    fraction and real travel away from the guild.
    """
    pygame.init()
    try:
        engine = _build_engine()
        guild = _add_guild(engine)
        heroes = [
            _add_hero(engine, guild, "ranger", 0),
            _add_hero(engine, guild, "ranger", 1),
            _add_hero(engine, guild, "wizard", 2),
        ]
        gx, gy = float(guild.center_x), float(guild.center_y)

        dt = 1.0 / float(SIM_TICK_HZ)
        sim_minutes = 3
        total_ticks = int(SIM_TICK_HZ * 60 * sim_minutes)
        sample_start = int(SIM_TICK_HZ * 60 * (sim_minutes - 1))  # last sim-minute

        max_dist_tiles = [0.0] * len(heroes)
        pinned = 0
        samples = 0
        for t in range(total_ticks):
            _chip(guild)  # keep is_damaged armed (repairs stalled), is_under_attack off
            engine.update(dt)
            engine.enemies.clear()  # belt-and-suspenders: NO enemies in this scenario
            for h in heroes:
                h.next_meal_due_ms = _NO_HUNGER_MS
            for i, h in enumerate(heroes):
                d_tiles = h.distance_to(gx, gy) / TILE_SIZE
                if d_tiles > max_dist_tiles[i]:
                    max_dist_tiles[i] = d_tiles
            if t >= sample_start:
                for h in heroes:
                    samples += 1
                    if h.state == HeroState.IDLE and h.distance_to(gx, gy) / TILE_SIZE <= _PIN_NEAR_TILES:
                        pinned += 1

        pinned_fraction = pinned / samples
        mean_max_dist = statistics.mean(max_dist_tiles)
        print(
            f"WK127_NO_PIN pinned_fraction={pinned_fraction:.4f} "
            f"mean_max_dist_tiles={mean_max_dist:.2f} "
            f"per_hero_max={[round(x, 1) for x in max_dist_tiles]} samples={samples}"
        )

        assert pinned_fraction < 0.5, (
            f"heroes are pinned IDLE at their damaged guild: pinned fraction "
            f"{pinned_fraction:.3f} >= 0.5 over the last sim-minute (pre-fix ~1.0) — "
            "the is_damaged defend hijack (WK127-T1) is still firing with no threat"
        )
        assert mean_max_dist > 4.0, (
            f"heroes never leave the guild: mean max distance {mean_max_dist:.1f} "
            "tiles <= 4.0 — the damaged-guild hijack is blocking the normal "
            "explore/roam pipeline"
        )
    finally:
        try:
            pygame.quit()
        except Exception:
            pass


def test_heroes_still_defend_threatened_guild():
    """WK127-T1 guardrail: a live enemy near the damaged guild MUST still pull
    heroes into defense (building_threatened gate passes). Holds pre- and
    post-fix — proves the threat gate did not neuter ``defend_home_building``.
    """
    pygame.init()
    try:
        engine = _build_engine()
        guild = _add_guild(engine)
        heroes = [
            _add_hero(engine, guild, "ranger", 0),
            _add_hero(engine, guild, "wizard", 1),
        ]
        _chip(guild)

        # A live enemy 3 tiles from the guild center (inside the 5-tile radius
        # defend_home_building scans). Massive HP so it survives the window.
        goblin = Enemy(guild.center_x + TILE_SIZE * 3, guild.center_y, "goblin")
        goblin.hp = goblin.max_hp = 100000
        engine.enemies.append(goblin)

        dt = 1.0 / float(SIM_TICK_HZ)
        engaged = False
        for _ in range(int(SIM_TICK_HZ * 30)):  # up to 30 sim-seconds
            _chip(guild)
            engine.update(dt)
            for h in heroes:
                h.next_meal_due_ms = _NO_HUNGER_MS
            if any(h.target is goblin or h.state == HeroState.FIGHTING for h in heroes):
                engaged = True
                break

        assert engaged, (
            "no hero engaged the live enemy beside their damaged guild within "
            "30 sim-seconds — the WK127-T1 threat gate broke real defense"
        )
    finally:
        try:
            pygame.quit()
        except Exception:
            pass


def test_damaged_castle_does_not_pin_heroes():
    """WK127-T6 (r2): a chipped CASTLE with NO enemies must not hijack heroes.

    Guards the castle half of the WK127-T1 fix (previously unprotected — a
    revert of the castle gate would have passed the suite). Pre-r1 the router
    fired ``defend_castle`` on ``castle.is_damaged`` (any missing HP, forever)
    and parked every hero IDLE within 3 tiles of the castle. Post-fix the
    chipped-but-quiet castle is ignored (``building_threatened`` False) and
    heroes keep travelling. Modeled on test_damaged_guild_does_not_pin_heroes;
    the guild stays at FULL HP here so only the castle branch is exercised.
    """
    pygame.init()
    try:
        engine = _build_engine()
        guild = _add_guild(engine)  # full HP — no home-guild hijack in this test
        castle = _castle(engine)
        heroes = [
            _add_hero(engine, guild, "ranger", 0),
            _add_hero(engine, guild, "ranger", 1),
            _add_hero(engine, guild, "wizard", 2),
        ]
        cx, cy = float(castle.center_x), float(castle.center_y)

        dt = 1.0 / float(SIM_TICK_HZ)
        sim_minutes = 2
        total_ticks = int(SIM_TICK_HZ * 60 * sim_minutes)
        sample_start = int(SIM_TICK_HZ * 60 * (sim_minutes - 1))  # last sim-minute

        last_min_max_dist = [0.0] * len(heroes)
        pinned = 0
        samples = 0
        for t in range(total_ticks):
            _chip(castle)  # keep is_damaged armed, is_under_attack off
            engine.update(dt)
            engine.enemies.clear()  # NO enemies in this scenario
            for h in heroes:
                h.next_meal_due_ms = _NO_HUNGER_MS
            if t >= sample_start:
                for i, h in enumerate(heroes):
                    samples += 1
                    d_tiles = h.distance_to(cx, cy) / TILE_SIZE
                    if d_tiles > last_min_max_dist[i]:
                        last_min_max_dist[i] = d_tiles
                    if h.state == HeroState.IDLE and d_tiles <= _PIN_NEAR_TILES:
                        pinned += 1

        pinned_fraction = pinned / samples
        mean_max_dist = statistics.mean(last_min_max_dist)
        print(
            f"WK127_NO_CASTLE_PIN pinned_fraction={pinned_fraction:.4f} "
            f"last_min_mean_max_dist_tiles={mean_max_dist:.2f} "
            f"per_hero_max={[round(x, 1) for x in last_min_max_dist]} samples={samples}"
        )

        assert pinned_fraction < 0.5, (
            f"heroes are pinned IDLE at the chipped castle: pinned fraction "
            f"{pinned_fraction:.3f} >= 0.5 over the last sim-minute (pre-r1 ~1.0) — "
            "the castle is_damaged defend hijack (WK127-T1) is firing with no threat"
        )
        assert mean_max_dist > 4.0, (
            f"heroes stay parked at the castle: last-sim-minute mean max distance "
            f"{mean_max_dist:.1f} tiles <= 4.0 — the chipped-castle hijack is "
            "blocking the normal explore/roam pipeline"
        )
    finally:
        try:
            pygame.quit()
        except Exception:
            pass


def test_wounded_hero_rests_in_chipped_home_guild():
    """WK127-T5/T7 (r2): chip damage must not block resting at home, forever.

    Pre-T5 ``can_rest_at_home``/``start_resting_at_building`` gated on
    ``is_damaged`` (any missing HP) — a wounded hero with a chipped (NOT
    recently damaged) home guild could NEVER rest. Post-T5 they gate on
    ``is_under_attack`` (3 s recently-damaged window): the hero routes home
    and enters RESTING within a couple sim-minutes.

    Inverse guard: a guild hit within the last 3 s (``is_under_attack`` True)
    must still REFUSE ``start_resting_at_building``.
    """
    pygame.init()
    try:
        engine = _build_engine()
        guild = _add_guild(engine)
        hero = _add_hero(engine, guild, "warrior", 0)
        # Wounded (50% HP, HERO_BASE_HP=60) with enough damage-since-left-home
        # that should_go_home_to_rest() is True (>= 10 threshold), but not so
        # low that retreat/critical paths kick in.
        hero.hp = hero.max_hp - 30
        hero.damage_since_left_home = 30
        assert hero.should_go_home_to_rest() is True

        dt = 1.0 / float(SIM_TICK_HZ)
        total_ticks = int(SIM_TICK_HZ * 60 * 2)  # up to 2 sim-minutes
        entered_resting = False
        for _ in range(total_ticks):
            _chip(guild)  # is_damaged True, is_under_attack False (stalled repairs)
            engine.update(dt)
            engine.enemies.clear()  # NO enemies in this scenario
            hero.next_meal_due_ms = _NO_HUNGER_MS
            if hero.state == HeroState.RESTING:
                entered_resting = True
                break

        assert entered_resting, (
            "wounded hero never entered RESTING at their chipped (not recently "
            "damaged) home guild within 2 sim-minutes — the WK127-T5 is_damaged "
            "rest blocker is back (pre-T5: can_rest_at_home False forever)"
        )

        # Inverse guard: a FRESH hit (is_under_attack True) refuses resting.
        from game.sim.timebase import now_ms as sim_now_ms

        guard = _add_hero(engine, guild, "warrior", 1)
        guard.hp = guard.max_hp - 30
        guild.last_damage_time_ms = int(sim_now_ms())  # arm the 3 s window
        assert guild.is_under_attack is True
        assert guard.start_resting_at_building(guild) is False, (
            "start_resting_at_building accepted a building hit within the last "
            "3 s (is_under_attack) — the WK127-T5 fresh-hit guard is gone"
        )
        assert guard.state == HeroState.IDLE
        assert not guard.is_inside_building
    finally:
        try:
            pygame.quit()
        except Exception:
            pass


def test_zero_purchase_shopping_cooldown():
    """WK127-T2: a completed shopping trip that buys NOTHING must not re-fire
    shopping immediately (sim-time cooldown), and the want/buy predicates must
    not disagree into an infinite marketplace orbit.

    Hero A (plan config): 500 gold, 2 potions, best gear — pre-fix orbits the
    marketplace forever (wants potions<5 vs buy <2). Hero B: 35 gold, 0 potions,
    best gear, but the market only stocks an UNAFFORDABLE potion (price 100) —
    wants_to_shop fires (priority-1: no potions) yet the buy fails, so its trip
    completes with zero purchases and must stamp the cooldown. (r2/T8: hero B
    previously relied on the misaligned 1-potion/30-49-gold middle clause,
    which the WK127-T8 predicate alignment removed.)
    Pre-fix: both re-fire back-to-back -> many trips. Post-fix: <= 3 total.
    """
    pygame.init()
    try:
        engine = _build_engine()
        guild = _add_guild(engine)  # full HP — no defend hijack in this test
        castle = _castle(engine)

        market = Marketplace(int(castle.grid_x) + 6, int(castle.grid_y) + 4)
        market.is_constructed = True
        market.construction_started = True
        if hasattr(market, "set_event_bus") and getattr(engine, "event_bus", None):
            market.set_event_bus(engine.event_bus)
        engine.buildings.append(market)

        best_weapon = {"name": "Test Blade", "type": "weapon", "price": 0, "attack": 99}
        best_armor = {"name": "Test Plate", "type": "armor", "price": 0, "defense": 99}

        # r2/T8: EVERY marketplace (the default map ships one too) stocks ONLY
        # an unaffordable potion, so hero B's trip (wants_to_shop priority-1:
        # no potions) completes with ZERO purchases and must stamp the
        # cooldown (test-only instance patches — no production edit).
        def _expensive_stock():
            return [{"name": "Expensive Potion", "type": "potion", "price": 100, "effect": 50}]

        for b in engine.buildings:
            if getattr(b, "building_type", None) == "marketplace":
                b.get_available_items = _expensive_stock

        hero_a = _add_hero(engine, guild, "ranger", 0, gold=500)
        hero_b = _add_hero(engine, guild, "ranger", 1, gold=35)
        for h, potions in ((hero_a, 2), (hero_b, 0)):
            h.potions = potions
            h.weapon = dict(best_weapon)
            h.armor = dict(best_armor)
            # Beside the marketplace (within the 6-tile shopping-moment radius).
            h.x = float(market.center_x + TILE_SIZE * 2)
            h.y = float(market.center_y)

        def _is_shopping(h) -> bool:
            t = getattr(h, "target", None)
            if isinstance(t, dict) and t.get("type") == "shopping":
                return True
            return getattr(h, "pending_task", None) == "shopping"

        dt = 1.0 / float(SIM_TICK_HZ)
        total_ticks = int(SIM_TICK_HZ * 60 * 2)  # 2 sim-minutes
        trip_starts = {hero_a.name: 0, hero_b.name: 0}
        was_shopping = {hero_a.name: False, hero_b.name: False}
        for _ in range(total_ticks):
            engine.update(dt)
            engine.enemies.clear()  # keep both heroes full-HP and out of combat
            for h in (hero_a, hero_b):
                h.next_meal_due_ms = _NO_HUNGER_MS
                now_shopping = _is_shopping(h)
                if now_shopping and not was_shopping[h.name]:
                    trip_starts[h.name] += 1
                was_shopping[h.name] = now_shopping

        total_trips = sum(trip_starts.values())
        cooldown_b = int(getattr(hero_b, "_shop_cooldown_until_ms", 0) or 0)
        print(
            f"WK127_SHOP_COOLDOWN trip_starts={trip_starts} total={total_trips} "
            f"hero_b_cooldown_until_ms={cooldown_b}"
        )

        assert total_trips <= 3, (
            f"zero-purchase shopping loop: {total_trips} trip starts in 2 sim-min "
            f"({trip_starts}) — expected <= 3 (one trip + at most one post-cooldown "
            "retry); the WK127-T2 cooldown/predicate fix is not holding"
        )
        assert cooldown_b > 0, (
            "hero B completed a zero-purchase shopping trip but no sim-time "
            "cooldown was stamped (_shop_cooldown_until_ms unset) — the WK127-T2 "
            "backstop is missing"
        )
    finally:
        try:
            pygame.quit()
        except Exception:
            pass
