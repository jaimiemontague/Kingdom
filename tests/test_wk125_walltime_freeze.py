"""WK125-T4 — Wall-clock timebase freeze regression (Agent 10, PerformanceStability_Lead).

ROOT CAUSE THIS GUARDS (confirmed by an 8-agent diagnosis + empirical headless repro):
In shipped play ``config.DETERMINISTIC_SIM = 0``. PRE-FIX, ``SimEngine.update()`` called
``set_sim_now_ms(None)`` every tick, so the AI clock ``timebase.now_ms()`` fell back to
``pygame.time.get_ticks()`` — a REAL WALL CLOCK. That clock keeps advancing while the
game is PAUSED (the render loop runs but ``SimEngine.update`` is skipped) and grows with
app uptime, while hero AI timestamps (``last_progress_ms``, ``next_meal_due_ms``, bounty
``started_ms``, ``*_commit_until_ms``) only refresh on a sim tick. After long real uptime
``now_ms()`` is huge vs the stale stamps, so EVERY staleness gate trips for ALL heroes at
once (stuck-recovery -> fallback_idle; hunger permanently urgent; bounty pursuit timeout;
expired anti-oscillation commit windows) -> heroes freeze / churn.

THE FIX (WK125-T1/T2): ``SimEngine.update()`` now ALWAYS advances + publishes a monotonic,
pause-frozen sim-time accumulator (``self._sim_now_ms``) in BOTH modes, and ``__init__``
publishes it (= 0) at construction. ``now_ms()`` therefore never reads the wall clock from
the running sim, so a wall-clock jump (paused 1 hr, or long uptime) cannot leak in.

WHY THIS TEST EXERCISES THE SHIPPED (NON-DETERMINISTIC) PATH:
``DETERMINISTIC_SIM`` is imported into ``game.sim_engine`` at module load, so setting
``os.environ`` after import would NOT take. We monkeypatch the MODULE ATTRIBUTE
``game.sim_engine.DETERMINISTIC_SIM = False`` so ``SimEngine.update`` runs the exact
real-play branch. (The whole rest of the suite — WK67 digest, WK124 soak — pins
``DETERMINISTIC_SIM=1`` and is unaffected; DET=1 already used this same accumulator clock,
so the WK67 digest stays byte-identical.)

PRE-FIX vs POST-FIX (the load-bearing assertion):
After a +1 hr ``pygame.time.get_ticks`` jump and one ``engine.update`` tick,
  * PRE-FIX:  ``timebase.now_ms()`` ~= 3,600,000  -> assertion FAILS.
  * POST-FIX: ``timebase.now_ms()`` stays sim-time (a few hundred ms) -> assertion PASSES.
A local revert of WK125-T1 was used to confirm the test fails on the pre-fix path; see the
agent log r1 evidence.

Headless, deterministic-seeded, ~10s runtime (no GPU / no display).
"""

from __future__ import annotations

import os

# Headless-friendly drivers BEFORE engine/config import (mirrors the WK124 soak +
# WK67 digest tests). NOTE: we deliberately do NOT force DETERMINISTIC_SIM here —
# we exercise the SHIPPED non-deterministic path by monkeypatching the already-
# imported game.sim_engine.DETERMINISTIC_SIM module attribute inside the test.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from config import SIM_TICK_HZ
from game.engine import GameEngine
from game.entities import WarriorGuild
from game.entities.hero import Hero, HeroState
from game.sim import timebase
from game.sim.determinism import set_sim_seed
from ai.basic_ai import BasicAI
import game.sim_engine as sim_engine_mod


_SEED = 1
_NUM_HEROES = 6
_WALL_JUMP_MS = 3_600_000  # == sat PAUSED for 1 hour (no sim ticks elapsed)


def _build_walltime_engine() -> tuple[GameEngine, list[Hero], tuple[float, float]]:
    """Headless engine + 6 warriors out of a constructed WarriorGuild.

    Mirrors the WK124 soak / adversarial-repro spawn pattern. Spawner + lair are
    neutralized so the run isolates hero AI (no combat pull); gold=0 so heroes are
    not diverted to shopping. Touches no production code.
    """
    set_sim_seed(_SEED)
    engine = GameEngine(headless=True)
    # No-LLM controller: idle heroes go through the deterministic fallback, which
    # reads the staleness gates this fix protects.
    engine.ai_controller = BasicAI(llm_brain=None)
    engine.sim.spawner.spawn = lambda dt: []  # type: ignore[assignment]
    engine.sim.lair_system.spawn_enemies = lambda dt, buildings: []  # type: ignore[assignment]

    castle = next(
        b for b in engine.buildings if getattr(b, "building_type", None) == "castle"
    )
    cx, cy = float(castle.center_x), float(castle.center_y)

    guild = WarriorGuild(int(castle.grid_x) - 5, int(castle.grid_y) + 3)
    guild.is_constructed = True
    guild.construction_started = True
    if hasattr(guild, "set_event_bus") and getattr(engine, "event_bus", None):
        guild.set_event_bus(engine.event_bus)
    engine.buildings.append(guild)

    heroes: list[Hero] = []
    for i in range(_NUM_HEROES):
        h = Hero(
            cx + (i % 3) * 12 - 18,
            cy + (i // 3) * 12,
            hero_class="warrior",
            hero_id=f"wk125_w{i}",
            name=f"W{i}",
        )
        h.home_building = guild
        h.gold = 0
        engine.heroes.append(h)
        heroes.append(h)

    return engine, heroes, (cx, cy)


def test_walltime_jump_does_not_leak_into_now_ms(monkeypatch):
    """LOAD-BEARING: a +1hr wall-clock jump must NOT leak into now_ms() (shipped path).

    Pre-fix now_ms() would return ~3,600,000 after the jump (it read get_ticks);
    post-fix it stays sim-time (< 60_000). Also asserts heroes keep deciding+moving
    after the jump (most net-displace > 50px; not all-IDLE-with-null-target), which
    is the player-visible "heroes freeze after long uptime/pause" symptom.
    """
    # Exercise the SHIPPED non-deterministic path (flag imported at module load).
    monkeypatch.setattr(sim_engine_mod, "DETERMINISTIC_SIM", False)

    pygame.init()
    engine = None
    try:
        engine, heroes, (cx, cy) = _build_walltime_engine()
        dt = 1.0 / float(SIM_TICK_HZ)

        # Warm up a few sim ticks (heroes wake up, AI assigns targets).
        for _ in range(int(SIM_TICK_HZ * 0.5)):  # ~0.5 sim-seconds
            engine.update(dt)
            engine.enemies.clear()

        now_before_jump = timebase.now_ms()
        warm_positions = [(h.x, h.y) for h in heroes]

        # --- INJECT THE PAUSED-FOR-1-HOUR CONDITION ---------------------------
        # The render loop kept running (wall clock advanced) but the sim did NOT
        # tick while paused. Simulate by jumping pygame's wall clock +1hr; we run
        # ZERO sim ticks during the "pause" itself.
        orig_get_ticks = pygame.time.get_ticks
        monkeypatch.setattr(
            pygame.time, "get_ticks", lambda: orig_get_ticks() + _WALL_JUMP_MS
        )

        # One tick AFTER the jump — this is where pre-fix now_ms() snapped to the
        # wall clock (set_sim_now_ms(None) -> get_ticks ~= 3.6M).
        engine.update(dt)
        engine.enemies.clear()
        now_after_jump = timebase.now_ms()

        print(
            f"WK125_WALLTIME now_before_jump={now_before_jump} "
            f"now_after_jump={now_after_jump} wall_jump_ms={_WALL_JUMP_MS}"
        )

        # ===== LOAD-BEARING ASSERTION =====
        # Post-fix the sim clock is monotonic + pause-frozen, so one extra dt after
        # the jump leaves now_ms() still a few hundred ms — nowhere near the 3.6M
        # wall jump. Pre-fix this is ~3,600,000 and FAILS.
        assert now_after_jump < 60_000, (
            f"now_ms() leaked the wall clock: {now_after_jump} ms after a "
            f"{_WALL_JUMP_MS} ms get_ticks jump (expected sim-time < 60_000). "
            "SimEngine.update is falling back to pygame.time.get_ticks() — the "
            "WK125 pause/uptime hero-freeze bug is present."
        )
        # The sim clock must also be MONOTONIC across the jump (only advanced by dt,
        # never by the wall jump).
        assert now_after_jump >= now_before_jump, "sim clock went backwards"
        assert now_after_jump - now_before_jump < 5_000, (
            "sim clock jumped far more than the elapsed sim dt across the wall jump"
        )

        # --- SECONDARY: heroes still decide + move after the jump --------------
        # Run ~8 sim-seconds and assert the swarm keeps acting (the visible repro
        # is "all heroes stand still"). Most heroes should net-displace > 50px and
        # they must NOT all be IDLE-with-null-target.
        start_positions = [(h.x, h.y) for h in heroes]
        for _ in range(int(SIM_TICK_HZ * 8)):
            engine.update(dt)
            engine.enemies.clear()

        net_disp = []
        for i, h in enumerate(heroes):
            ddx = h.x - start_positions[i][0]
            ddy = h.y - start_positions[i][1]
            net_disp.append((ddx * ddx + ddy * ddy) ** 0.5)

        moved = sum(1 for d in net_disp if d > 50.0)
        all_idle_no_target = all(
            h.state == HeroState.IDLE and getattr(h, "target", None) is None
            for h in heroes
        )

        print(
            f"WK125_WALLTIME net_disp={[round(d, 1) for d in net_disp]} "
            f"moved_gt_50px={moved}/{len(heroes)} all_idle_no_target={all_idle_no_target} "
            f"hunger_urgent={[h.hunger_urgent for h in heroes]} "
            f"now_ms_final={timebase.now_ms()}"
        )

        assert not all_idle_no_target, (
            "ALL heroes are IDLE with no target after the wall-clock jump — the "
            "every-staleness-gate-trips freeze is present (WK125 regression)"
        )
        assert moved > len(heroes) // 2, (
            f"only {moved}/{len(heroes)} heroes net-moved > 50px after the jump — "
            "heroes are frozen/churning (WK125 regression). "
            f"net_disp={[round(d, 1) for d in net_disp]}"
        )
    finally:
        try:
            pygame.quit()
        except Exception:
            pass
