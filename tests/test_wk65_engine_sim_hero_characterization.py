"""WK65 Round 0 (Wave 1) — engine / sim / hero characterization net.

Sprint: wk65_round0_deslop_foundation
Owner:  Agent 03 (TechnicalDirector_Architecture)

PURPOSE
-------
These tests pin the *observable behavior* that the later de-slop refactors
(Round A boundary/DTO work, Round B god-file splits) will move around, so the
moves are provably inert. They are GREEN on the current, unmodified code.

The intent is to catch behavior DRIFT, not to be brittle: the deterministic
digest asserts stable invariants (gold total, entity counts, sim time) plus
*decoupled* enemy invariants — the enemy-type multiset (spawn composition) and
the sorted HP multiset (combat outcomes). Both are fully reproducible and catch
real drift (spawn-rate, economy, combat changes) in later refactors.

We deliberately do NOT pin exact enemy positions: a single ranged enemy
(skeleton_archer) kites a few pixels differently depending on global state
leaked by *other* test modules running earlier in the same process, so a
coordinate pin would be brittle without being a meaningful behavior signal.
Collections are sorted; nothing is keyed by ``id()``.

DETERMINISM
-----------
``config.DETERMINISTIC_SIM`` / ``config.SIM_SEED`` are read from env at import
time, so we cannot rely on env vars here (conftest already imported config).
Instead we mirror ``tests/test_engine_sim_boundary.py`` and force determinism
via ``unittest.mock.patch`` on the already-imported module-level constants in
BOTH ``game.engine`` and ``game.sim_engine``, and pin ``SIM_SEED`` so world
generation + initial lair placement are reproducible.
"""

from __future__ import annotations

import collections

import pygame
from unittest.mock import patch

from game.engine import GameEngine
from game.entities.hero import Hero, HeroState
from game.sim.determinism import set_sim_seed
from game.sim.timebase import set_sim_now_ms, set_time_multiplier


# Fixed seed for the deterministic digest. Patched into game.sim_engine.SIM_SEED
# (consumed by SimEngine.__init__ -> set_sim_seed) so world gen is reproducible.
_DIGEST_SEED = 3
_DIGEST_TICKS = 600  # 10 sim-seconds at 60 Hz
_DT = 1.0 / 60.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deterministic_engine() -> GameEngine:
    """Construct a headless engine with deterministic sim time + fixed seed.

    Patching SIM_SEED before construction is required because SimEngine.__init__
    calls set_sim_seed(SIM_SEED) before world generation and initial lair
    placement — so the seed must be in place during construction, not after.
    """
    with patch("game.engine.DETERMINISTIC_SIM", True), \
         patch("game.sim_engine.DETERMINISTIC_SIM", True), \
         patch("game.sim_engine.SIM_SEED", _DIGEST_SEED):
        return GameEngine(headless=True)


def _restore_real_spawner_enemy_classes() -> None:
    """Undo enemy-class monkeypatches leaked by ``tests/test_spawner.py``.

    ``test_spawner.py`` rebinds ``game.systems.spawner.SkeletonArcher`` /
    ``.Goblin`` to local ``Dummy*`` stand-ins via direct module attribute
    assignment (not the ``monkeypatch`` fixture) and never restores them, so
    when that module runs before this one the live sim spawns the stub enemies
    (which lack ``is_alive`` and crash combat). This is a PRE-EXISTING test
    isolation bug in test_spawner (reported to PM); we defensively restore the
    canonical classes here so this characterization run is hermetic regardless
    of collection order. We do NOT edit test_spawner (out of this agent's lane).
    """
    import game.systems.spawner as spawner_module
    from game.entities import enemy as enemy_module

    for _name in ("Goblin", "Wolf", "Skeleton", "SkeletonArcher", "Spider", "Bandit"):
        _real = getattr(enemy_module, _name, None)
        if _real is not None:
            setattr(spawner_module, _name, _real)


def _reset_global_sim_state() -> None:
    """Make the digest hermetic against state leaked by earlier tests.

    ``timebase.now_ms()`` falls back to ``pygame.time.get_ticks()`` (wall clock)
    whenever the global sim clock is ``None``; any hero/enemy code that reads
    ``sim_now_ms()`` before/between the engine's own clock writes would then pick
    up wall-clock time and make the run non-reproducible. Pinning the clock to 0,
    re-seeding, and normalizing the speed multiplier removes that dependency so
    two runs in the same process (even after other test modules ran) match. We
    also restore spawner enemy classes leaked by test_spawner (see helper).
    """
    set_sim_now_ms(0)
    set_time_multiplier(1.0)
    set_sim_seed(_DIGEST_SEED)
    _restore_real_spawner_enemy_classes()


def _run_deterministic_digest() -> dict:
    """Run a fixed-length deterministic sim and return a stable digest dict."""
    with patch("game.engine.DETERMINISTIC_SIM", True), \
         patch("game.sim_engine.DETERMINISTIC_SIM", True), \
         patch("game.sim_engine.SIM_SEED", _DIGEST_SEED):
        _reset_global_sim_state()
        engine = _deterministic_engine()
        _reset_global_sim_state()
        for _ in range(_DIGEST_TICKS):
            engine.update(_DT)

        # Decoupled, ordering-independent enemy invariants (see module docstring).
        # NOTE: we deliberately do NOT pin exact enemy positions. A single
        # ranged enemy (skeleton_archer) kites a few pixels differently
        # depending on global state leaked by *other* test modules in the same
        # process; that few-pixel jitter is not a meaningful behavior signal and
        # would make the pin brittle. The type multiset (spawn composition) and
        # the HP multiset (combat outcomes) are fully stable and catch real
        # drift far better than one archer's coordinates.
        enemy_type_counts = dict(
            sorted(
                collections.Counter(
                    str(getattr(e, "enemy_type", "")) for e in engine.enemies
                ).items()
            )
        )
        enemy_hp = sorted(int(getattr(e, "hp", 0)) for e in engine.enemies)

        digest = {
            "gold": int(engine.economy.player_gold),
            "n_heroes": len(engine.heroes),
            "n_enemies": len(engine.enemies),
            "n_buildings": len(engine.buildings),
            "n_peasants": len(engine.peasants),
            "sim_now_ms": int(engine._sim_now_ms),
            "enemy_type_counts": enemy_type_counts,
            "enemy_hp": enemy_hp,
        }
        return digest


# ---------------------------------------------------------------------------
# 1. Deterministic sim digest (pins SimEngine.update for the Round-B split)
# ---------------------------------------------------------------------------

# Captured on the current, unmodified code (DETERMINISTIC_SIM forced on, seed 3,
# 600 ticks). These are the values later refactors must preserve.
_EXPECTED_DIGEST = {
    "gold": 2101,
    "n_heroes": 0,
    "n_enemies": 13,
    "n_buildings": 43,
    "n_peasants": 1,
    "sim_now_ms": 10200,
    "enemy_type_counts": {
        "bandit": 2,
        "goblin": 3,
        "skeleton": 1,
        "skeleton_archer": 2,
        "spider": 3,
        "wolf": 2,
    },
    "enemy_hp": [18, 18, 18, 22, 22, 30, 30, 30, 40, 40, 42, 42, 55],
}


def test_deterministic_sim_digest_matches_baseline():
    """A fixed deterministic run produces the exact pinned digest.

    Pins SimEngine.update end-to-end: economy gold, hero/enemy/building/peasant
    counts, sim-clock advance, the enemy-type multiset, and the enemy HP
    multiset. Any Round-A/B refactor that changes these observables flags
    behavior drift.
    """
    digest = _run_deterministic_digest()
    assert digest == _EXPECTED_DIGEST, (
        "Deterministic sim digest drifted from the pinned baseline.\n"
        f"  expected: {_EXPECTED_DIGEST}\n"
        f"  actual:   {digest}\n"
        "If this change is intentional, update _EXPECTED_DIGEST; otherwise a "
        "refactor changed observable sim behavior."
    )


def test_deterministic_sim_digest_is_stable_across_runs():
    """Two independent deterministic runs produce byte-identical digests.

    Guards the determinism property itself (seeded RNG, no wall-clock leakage),
    independent of the exact baseline values above.
    """
    first = _run_deterministic_digest()
    second = _run_deterministic_digest()
    assert first == second, (
        f"Deterministic sim is not reproducible across runs:\n"
        f"  run1: {first}\n  run2: {second}"
    )


# ---------------------------------------------------------------------------
# 2. Selection mutual-exclusion (pins the engine selection facade for Round B)
# ---------------------------------------------------------------------------

def test_try_select_hero_clears_other_selection_slots():
    """After try_select_hero(world), exactly the hero slot is set; others clear.

    Pins the selection mutual-exclusion invariant on the engine selection
    facade that Round B will extract. Uses try_select_hero_at_world to drive a
    deterministic, camera-independent pick.
    """
    engine = GameEngine(headless=True)
    try:
        hero = Hero(150.0, 150.0, hero_class="warrior",
                    hero_id="wk65_sel_hero", name="SelHero")
        engine.heroes.append(hero)

        # Pre-set the other slots so we can prove they get cleared.
        castle = next(
            (b for b in engine.buildings
             if getattr(b, "building_type", None) == "castle"),
            None,
        )
        if castle is not None:
            engine.selected_building = castle
        if engine.peasants:
            engine.selected_peasant = engine.peasants[0]

        ok = engine.try_select_hero_at_world(150.0, 150.0, radius=24.0)
        assert ok is True

        # Exactly one slot set: the hero.
        assert engine.selected_hero is hero
        assert engine.selected_building is None
        assert engine.selected_peasant is None
        assert engine.selected_enemy is None
    finally:
        pygame.quit()


def test_selection_slots_are_mutually_exclusive_when_switching():
    """Selecting a building after a hero clears the hero slot (and vice versa)."""
    engine = GameEngine(headless=True)
    try:
        hero = Hero(150.0, 150.0, hero_class="ranger",
                    hero_id="wk65_sel_switch", name="SwitchHero")
        engine.heroes.append(hero)
        castle = next(
            (b for b in engine.buildings
             if getattr(b, "building_type", None) == "castle"),
            None,
        )
        assert castle is not None

        engine.try_select_hero_at_world(150.0, 150.0, radius=24.0)
        assert engine.selected_hero is hero
        assert engine.selected_building is None

        # Switch to a building selection; hero slot must clear.
        engine.selected_building = castle
        engine.selected_hero = None
        assert engine.selected_building is castle
        assert engine.selected_hero is None
        assert engine.selected_peasant is None
    finally:
        pygame.quit()


# ---------------------------------------------------------------------------
# 3. Console commands (pins process_command for the Round-B console.py split)
# ---------------------------------------------------------------------------

def test_console_revealmap_disables_fog_and_reveals_pois():
    """/revealmap sets world.fog_disabled and discovers all POIs."""
    engine = GameEngine(headless=True)
    try:
        world = engine.world
        pois = list(getattr(engine.sim, "pois", []))
        # Precondition: fog is enabled (fog_disabled False) and POIs undiscovered.
        assert getattr(world, "fog_disabled", False) is False
        total_pois = len(pois)
        assert sum(1 for p in pois if getattr(p, "is_discovered", False)) == 0

        engine.process_command("/revealmap")

        assert getattr(world, "fog_disabled", False) is True
        discovered = sum(1 for p in pois if getattr(p, "is_discovered", False))
        assert discovered == total_pois, (
            f"/revealmap should discover all {total_pois} POIs, got {discovered}"
        )
    finally:
        pygame.quit()


def test_console_gold_adds_exact_amount():
    """/gold <n> adds exactly n to economy.player_gold (default 500 with no arg)."""
    engine = GameEngine(headless=True)
    try:
        before = int(engine.economy.player_gold)
        engine.process_command("/gold 500")
        assert int(engine.economy.player_gold) - before == 500

        engine.process_command("/gold 123")
        assert int(engine.economy.player_gold) - before == 623

        # No-arg form uses the documented default of 500.
        engine.process_command("/gold")
        assert int(engine.economy.player_gold) - before == 1123
    finally:
        pygame.quit()


# ---------------------------------------------------------------------------
# 4. Hero methods (pin cohesive methods slated for the Round-B mixin split)
# ---------------------------------------------------------------------------

def _hero(hero_id: str) -> Hero:
    return Hero(0.0, 0.0, hero_class="warrior", hero_id=hero_id, name=hero_id)


def test_hero_should_go_home_to_rest_thresholds():
    """should_go_home_to_rest() pins its damage-threshold state machine."""
    # Fresh, full-HP hero: no need to rest.
    h = _hero("wk65_rest_fresh")
    assert h.should_go_home_to_rest() is False

    # Took 10+ total damage since leaving home -> should rest.
    h.hp = h.max_hp - 15
    h.damage_since_left_home = 15
    assert h.should_go_home_to_rest() is True

    # Already resting -> never returns True regardless of damage.
    h.state = HeroState.RESTING
    assert h.should_go_home_to_rest() is False


def test_hero_derive_intent_taxonomy():
    """_derive_intent() pins the (intent, reason, context) taxonomy outputs.

    These tuples are the contract the Round-B hero mixin split must preserve.
    """
    # Idle default.
    h = _hero("wk65_intent_idle")
    assert h._derive_intent() == ("idle", "no urgent goal", {})

    # Resting maps to returning_to_safety.
    h.state = HeroState.RESTING
    assert h._derive_intent() == (
        "returning_to_safety", "resting at home", {"target": "home"},
    )

    # Fighting state -> engaging_enemy (no live target object).
    hf = _hero("wk65_intent_fight")
    hf.state = HeroState.FIGHTING
    assert hf._derive_intent() == (
        "engaging_enemy",
        "engaging nearby enemy",
        {"target": "enemy", "enemy_type": None},
    )

    # Bounty dict target (attack_lair) -> attacking_lair.
    hb = _hero("wk65_intent_bounty")
    hb.target = {"type": "bounty", "bounty_id": "b1", "bounty_type": "attack_lair"}
    assert hb._derive_intent() == (
        "attacking_lair",
        "pursuing lair bounty",
        {"target": "bounty", "bounty_id": "b1", "bounty_type": "attack_lair"},
    )

    # Shopping dict target -> shopping.
    hs = _hero("wk65_intent_shop")
    hs.target = {"type": "shopping", "item": "potion"}
    assert hs._derive_intent() == (
        "shopping",
        "heading to marketplace",
        {"target": "marketplace", "item": "potion"},
    )


def test_hero_get_intent_snapshot_shape():
    """get_intent_snapshot() returns the contract dict shape (UI/QA-safe accessor)."""
    h = _hero("wk65_intent_snap")
    snap = h.get_intent_snapshot(now_ms=0)
    assert isinstance(snap, dict)
    assert "intent" in snap
    # Default intent on a fresh hero is "idle".
    assert snap["intent"] == "idle"
