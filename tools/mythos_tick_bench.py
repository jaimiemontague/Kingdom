"""Mythos Lag Fix — S5 sim-tick headless benchmark (gate scenario).

Measures the cost of ONE fixed-rate sim tick (``GameEngine.update(0.05)``, the
exact call the FAST-speed drain loop makes 20x/wall-second) at the gate
scenario: 24 heroes / 24 active buildings / 80 enemies (tools/wk123_scenario.py
spawn helpers), BasicAI wired, deterministic seed.

Usage (headless, no GUI):

    python tools/mythos_tick_bench.py                 # 6000 ticks, full report
    python tools/mythos_tick_bench.py --ticks 2000    # shorter probe

Per-candidate A/B: every S5 candidate is controlled by an env flag read by the
GAME code (not by this bench). Set the flag before running to measure one
candidate in isolation, e.g.:

    KINGDOM_POI_SCAN_INTERVAL=1       (disable the POI-discovery throttle)
    KINGDOM_TREE_DICT_FULL_REBUILD=1  (restore the per-tick tree-dict rebuild)
    KINGDOM_TREE_BLOCK_SET=0          (disable the blocking-tree tile set)
    KINGDOM_LAZY_HERO_PROFILES=0      (restore eager per-tick profile builds)
    KINGDOM_AI_THREAT_MEMO=0          (disable the per-tick AI threat memo)
    KINGDOM_FOG_ADAPTIVE_CADENCE=0    (restore the fixed 3-tick fog cadence)
    KINGDOM_ASTAR_TILE_GOALS=0        (restore pixel-keyed chase goals)
    KINGDOM_ASTAR_MAX_PLANS / KINGDOM_ASTAR_MAX_EXPANSIONS (override A* budget)
    KINGDOM_FAST_DT_SCALING=1         (enable FAST-speed dt scaling; default OFF)

The report prints mean/p50/p95/p99/max tick ms plus the flag states, so a
before/after table is just two runs of this script (use ``git stash`` for the
true pre-change baseline).
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Deterministic, headless: MUST be set before config / pygame import.
os.environ.setdefault("DETERMINISTIC_SIM", "1")
os.environ.setdefault("SIM_SEED", "3")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

# Flags reported in the output table (game-side env gates for each candidate).
_CANDIDATE_FLAGS = (
    "KINGDOM_LAZY_HERO_PROFILES",
    "KINGDOM_TREE_DICT_FULL_REBUILD",
    "KINGDOM_TREE_BLOCK_SET",
    "KINGDOM_POI_SCAN_INTERVAL",
    "KINGDOM_AI_THREAT_MEMO",
    "KINGDOM_FOG_ADAPTIVE_CADENCE",
    "KINGDOM_FOG_MAX_CADENCE",
    "KINGDOM_FOG_REVEALER_THRESHOLD",
    "KINGDOM_ASTAR_TILE_GOALS",
    "KINGDOM_ASTAR_MAX_PLANS",
    "KINGDOM_ASTAR_MAX_EXPANSIONS",
    "KINGDOM_FAST_DT_SCALING",
)


def _percentile(sorted_vals: list[float], p: float) -> float:
    """Nearest-rank percentile on a pre-sorted list."""
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, int(round((p / 100.0) * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def main() -> int:
    ap = argparse.ArgumentParser(description="Headless sim-tick benchmark (gate scenario)")
    ap.add_argument("--ticks", type=int, default=6000, help="number of 50ms sim ticks to run")
    ap.add_argument("--heroes", type=int, default=24)
    ap.add_argument("--buildings", type=int, default=24)
    ap.add_argument("--enemies", type=int, default=80)
    ap.add_argument("--warmup", type=int, default=100, help="warmup ticks excluded from stats")
    ap.add_argument("--topup-every", type=int, default=40,
                    help="re-pin alive hero/enemy counts every N ticks (mirrors the soak harness)")
    ap.add_argument("--csv", type=str, default="", help="optional per-tick CSV output path")
    args = ap.parse_args()

    import pygame
    pygame.init()

    from ai.basic_ai import BasicAI
    from game.engine import GameEngine
    from game.sim.timebase import set_time_multiplier
    from tools.run_headless_sim import DummyInputManager
    from tools import wk123_scenario as scen

    t_build0 = time.perf_counter()
    engine = GameEngine(input_manager=DummyInputManager(), headless=True)
    engine.ai_controller = BasicAI(llm_brain=None)
    counts = scen.build_heavy_scenario(
        engine,
        heroes=int(args.heroes),
        buildings_target=int(args.buildings),
        enemies=int(args.enemies),
    )
    # FAST speed (the player's real condition). The per-tick dt is fixed at the
    # engine's 50ms regardless; the multiplier matters for any timebase consumer.
    set_time_multiplier(1.0)
    t_build1 = time.perf_counter()

    dt = engine._FIXED_SIM_DT  # 50ms — exactly what lifecycle.tick_simulation drains
    n = int(args.ticks)
    warmup = max(0, int(args.warmup))
    topup_every = max(1, int(args.topup_every))

    print(f"[tick-bench] scenario: {counts} build={1000.0 * (t_build1 - t_build0):.0f}ms")
    print(f"[tick-bench] ticks={n} warmup={warmup} dt={dt * 1000:.0f}ms topup_every={topup_every}")
    for flag in _CANDIDATE_FLAGS:
        val = os.environ.get(flag)
        if val is not None:
            print(f"[tick-bench] env {flag}={val}")

    samples: list[float] = []
    t_run0 = time.perf_counter()
    for i in range(n):
        if i % topup_every == 0:
            scen.topup_enemies(engine)
            scen.topup_heroes(engine)
        t0 = time.perf_counter()
        engine.update(dt)
        t1 = time.perf_counter()
        if i >= warmup:
            samples.append((t1 - t0) * 1000.0)
    t_run1 = time.perf_counter()

    if args.csv:
        with open(args.csv, "w", encoding="utf-8") as fh:
            fh.write("tick,ms\n")
            for i, ms in enumerate(samples):
                fh.write(f"{i + warmup},{ms:.4f}\n")

    s = sorted(samples)
    mean = statistics.fmean(samples) if samples else 0.0
    p50 = _percentile(s, 50)
    p95 = _percentile(s, 95)
    p99 = _percentile(s, 99)
    mx = s[-1] if s else 0.0
    total_s = t_run1 - t_run0
    worst5 = ", ".join(f"{v:.1f}" for v in s[-5:])
    alive_h = len([h for h in engine.heroes if getattr(h, "is_alive", False)])
    alive_e = len([e for e in engine.enemies if getattr(e, "is_alive", False)])

    print(f"[tick-bench] end-state: heroes_alive={alive_h} enemies_alive={alive_e} "
          f"buildings={len(engine.buildings)} trees={len(engine.sim.trees)}")
    print(f"[tick-bench] RESULT ticks={len(samples)} "
          f"mean={mean:.3f}ms p50={p50:.3f}ms p95={p95:.3f}ms p99={p99:.3f}ms max={mx:.3f}ms")
    print(f"[tick-bench] worst5=[{worst5}] total={total_s:.1f}s "
          f"sim_cpu_per_wall_sec_at_FAST={mean * 20:.1f}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
