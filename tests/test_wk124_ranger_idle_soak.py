"""WK124-T6 — Ranger late-game roam soak test (Agent 11, QA_TestEngineering_Lead).

Proves the Wave-1/2 fix in ``ai/behaviors/exploration.py``: once a ranger has
revealed the near-castle fog "bubble" the LOCAL frontier scan returns ``[]`` and
the ranger USED to fall to the near-castle wander branch (a fixed patrol zone
assigned once 6-10 tiles from the castle) and "seize up" — oscillating in a small
cleared pocket near base. The fix adds a COARSE whole-map distant-frontier scan
(``_find_distant_frontier_tile``) + a productive lair-roam fallback
(``_roam_toward_distant_objective``) so late-game rangers keep traveling to
distant fog instead of churning near home.

WHAT THIS TEST DOES (deterministic, headless):
  * Builds a fresh ``GameEngine(headless=True)`` with ``DETERMINISTIC_SIM=1`` and
    dummy SDL drivers (so the sim-time clock is the fixed-tick clock and commit
    windows advance from ``engine.update``), a fixed ``set_sim_seed`` and a
    no-LLM ``BasicAI`` (the no-LLM fallback path drives idle rangers into
    ``explore()`` — the exact code path WK124-T6 patches).
  * Spawns 6 rangers out of a constructed ``RangerGuild`` (mirrors the
    ``tools/wk123_scenario.py`` guild+hero spawn pattern, but ranger class).
  * Neutralizes enemy/lair *spawning* (and clears any enemies each tick) so the
    soak isolates EXPLORATION behavior — rangers are never pulled into combat,
    which would confound the idle/distance measurement. This is a test-only
    monkeypatch on the engine instance; it edits no production code.
  * Runs 10 sim-minutes at SIM_TICK_HZ (60 Hz -> 36000 ticks). Over the LAST 3
    sim-minutes it samples, per tick per ranger, whether the ranger is "idle-ish"
    (churning near base) and tracks each ranger's MAX distance-from-castle.

"IDLE-ISH" = ``state == IDLE`` OR (``target.type == "patrol"`` AND distance to
that ranger's assigned patrol zone < 4 tiles) — i.e. parked in / returning to the
near-castle patrol pocket, which is precisely the "seized up" failure mode.

THRESHOLDS (and why they are meaningfully discriminating — measured 2026-06-03):
  * ``idle-ish fraction < 0.40``. This is the LOAD-BEARING assertion.
        post-fix (current tree): ~0.027
        pre-fix  (simulated by stubbing the two new exploration helpers to the
                  old empty/None behavior): ~0.80
    0.40 sits squarely between them with wide margin in both directions.
  * ``mean(per-ranger max distance-from-castle) > 15 tiles``. Secondary proof
    that rangers actually LEAVE the near-castle bubble (the assign_patrol_zone
    radius is 6-10 tiles; 15 is comfortably outside it).
        post-fix: ~76 tiles.
    (Pre-fix the max-distance alone is weaker evidence — the local scan still
    pushes rangers outward in the FIRST few minutes before the bubble is
    exhausted — so the idle-ish fraction is the assertion that actually catches
    the late-game seize-up; max-distance is the corroborating signal.)

RUNTIME: ~60s on the dev box for the full 10 sim-min (single-process headless
sim, no render). Kept at 10 sim-min because that is the timescale at which the
near-castle bubble is exhausted and the bug manifests; a shorter run would not
exercise the late-game branch the fix targets.

This test MUST PASS on the current (post-fix) tree and would FAIL pre-fix.
"""

from __future__ import annotations

import os
import statistics

# Headless-friendly drivers + deterministic sim BEFORE engine/config import, so
# config.DETERMINISTIC_SIM is read True and sprite/font loads work without a
# display. Mirrors tests/test_wk67_ai_boundary.py.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("DETERMINISTIC_SIM", "1")

import pygame

from config import SIM_TICK_HZ, TILE_SIZE
from game.engine import GameEngine
from game.entities import RangerGuild
from game.entities.hero import Hero, HeroState


# --- soak parameters --------------------------------------------------------
_SOAK_SEED = 20240603
_NUM_RANGERS = 6
_SIM_MINUTES = 10
_SAMPLE_LAST_MINUTES = 3  # measure idle-ish / distance over the final window
# Thresholds (see module docstring for the measured pre/post-fix separation).
_IDLEISH_FRACTION_MAX = 0.40
_MEAN_MAX_DIST_TILES_MIN = 15.0
# "idle-ish" patrol-pocket radius (tiles): within this of the assigned patrol
# zone while target.type == "patrol" counts as churning near base.
_PATROL_NEAR_TILES = 4.0


def _build_ranger_soak_engine() -> tuple[GameEngine, list[Hero], tuple[float, float]]:
    """Construct a deterministic headless engine seeded with ``_NUM_RANGERS`` rangers.

    Returns ``(engine, rangers, (castle_cx, castle_cy))``. Enemy/lair spawning is
    neutralized on the instance so the soak measures pure exploration (no combat
    pull). Touches no production code.
    """
    from ai.basic_ai import BasicAI
    from game.sim.determinism import set_sim_seed

    set_sim_seed(_SOAK_SEED)
    engine = GameEngine(headless=True)
    # No-LLM controller: idle rangers go through the deterministic fallback into
    # explore() (the WK124-T6 code path). Mirrors the WK67 digest engine wiring.
    engine.ai_controller = BasicAI(llm_brain=None)

    # Isolate exploration: stop the spawner/lair from injecting enemies during the
    # run (test-only monkeypatch on the instance — no production edit). Belt-and-
    # suspenders enemy clearing happens in the tick loop too.
    engine.sim.spawner.spawn = lambda dt: []  # type: ignore[assignment]
    engine.sim.lair_system.spawn_enemies = lambda dt, buildings: []  # type: ignore[assignment]

    castle = next(
        b for b in engine.buildings if getattr(b, "building_type", None) == "castle"
    )
    cx = float(castle.center_x)
    cy = float(castle.center_y)

    # A constructed RangerGuild as the rangers' home (mirrors wk123_scenario's
    # guild+hero spawn pattern; ranger class instead of warrior).
    guild = RangerGuild(int(castle.grid_x) - 5, int(castle.grid_y) + 3)
    guild.is_constructed = True
    guild.construction_started = True
    if hasattr(guild, "set_event_bus") and getattr(engine, "event_bus", None):
        guild.set_event_bus(engine.event_bus)
    engine.buildings.append(guild)

    rangers: list[Hero] = []
    for i in range(_NUM_RANGERS):
        h = Hero(
            cx + (i % 3) * 12 - 18,
            cy + (i // 3) * 12,
            hero_class="ranger",
            hero_id=f"wk124_soak_ranger_{i}",
            name=f"SoakRanger{i}",
        )
        h.home_building = guild
        # 0 gold so rangers are not constantly diverted to shopping/blacksmith;
        # keeps the soak focused on the explore/roam decision path.
        h.gold = 0
        engine.heroes.append(h)
        rangers.append(h)

    assert all(r.hero_class == "ranger" for r in rangers), "all soak heroes must be rangers"
    return engine, rangers, (cx, cy)


def _is_idleish(ai, ranger: Hero, castle: tuple[float, float]) -> bool:
    """True if the ranger is churning near base (the 'seized up' failure mode)."""
    if ranger.state == HeroState.IDLE:
        return True
    target = getattr(ranger, "target", None)
    if isinstance(target, dict) and target.get("type") == "patrol":
        zone_x, zone_y = ai.hero_zones.get(ranger.name, castle)
        if ranger.distance_to(zone_x, zone_y) / TILE_SIZE < _PATROL_NEAR_TILES:
            return True
    return False


def test_ranger_late_game_roam_soak():
    """Late-game rangers leave the near-castle bubble (WK124-T6).

    Over the final 3 of 10 sim-minutes: ranger idle-ish fraction < 0.40 and mean
    per-ranger max distance-from-castle > 15 tiles. Both pass comfortably on the
    post-fix tree; the idle-ish fraction would blow past 0.40 pre-fix.
    """
    pygame.init()
    engine = None
    try:
        engine, rangers, castle = _build_ranger_soak_engine()
        ai = engine.ai_controller
        cx, cy = castle

        dt = 1.0 / float(SIM_TICK_HZ)
        total_ticks = int(SIM_TICK_HZ * 60 * _SIM_MINUTES)
        sample_start_tick = int(SIM_TICK_HZ * 60 * (_SIM_MINUTES - _SAMPLE_LAST_MINUTES))

        max_dist_tiles = [0.0] * len(rangers)
        idleish_count = 0
        sample_count = 0

        for t in range(total_ticks):
            engine.update(dt)
            # Keep the world enemy-free so rangers never enter combat (spawn was
            # neutralized, but clear defensively in case lairs/waves inject any).
            engine.enemies.clear()

            for i, ranger in enumerate(rangers):
                d_tiles = ranger.distance_to(cx, cy) / TILE_SIZE
                if d_tiles > max_dist_tiles[i]:
                    max_dist_tiles[i] = d_tiles

            if t >= sample_start_tick:
                for ranger in rangers:
                    sample_count += 1
                    if _is_idleish(ai, ranger, castle):
                        idleish_count += 1

        assert sample_count > 0, "no samples collected — soak window misconfigured"
        idleish_fraction = idleish_count / sample_count
        mean_max_dist = statistics.mean(max_dist_tiles)

        # Diagnostic line surfaces the measured numbers on failure (and via -s).
        print(
            f"WK124_RANGER_SOAK idleish_fraction={idleish_fraction:.4f} "
            f"mean_max_dist_tiles={mean_max_dist:.2f} "
            f"per_ranger_max={[round(x, 1) for x in max_dist_tiles]} "
            f"samples={sample_count}"
        )

        assert idleish_fraction < _IDLEISH_FRACTION_MAX, (
            f"rangers churn near base too much: idle-ish fraction "
            f"{idleish_fraction:.3f} >= {_IDLEISH_FRACTION_MAX} (pre-fix ~0.80) — "
            "the late-game distant-frontier roam (WK124-T6) is not firing"
        )
        assert mean_max_dist > _MEAN_MAX_DIST_TILES_MIN, (
            f"rangers stay in the near-castle bubble: mean max distance "
            f"{mean_max_dist:.1f} tiles <= {_MEAN_MAX_DIST_TILES_MIN} — rangers "
            "are not reaching distant fog"
        )
    finally:
        try:
            pygame.quit()
        except Exception:
            pass
