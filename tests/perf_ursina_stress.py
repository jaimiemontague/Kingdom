"""
Full-pipeline Ursina FPS stress test: 30 heroes + 60 enemies.

Launches the actual 3D renderer, injects stress entities, measures real FPS for 8 seconds.
Usage:
    python -m tests.perf_ursina_stress
"""
from __future__ import annotations

import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure environment for stress test
os.environ["KINGDOM_URSINA_FPS_PROBE"] = "1"
os.environ["KINGDOM_URSINA_FPS_PROBE_WARMUP_SEC"] = "2"
os.environ["KINGDOM_URSINA_AUTO_EXIT_SEC"] = "10"
os.environ["KINGDOM_URSINA_AUTO_SCREENSHOT"] = "0"
os.environ["KINGDOM_PLAYTEST_START"] = "0"
os.environ["DETERMINISTIC_SIM"] = "1"
os.environ["SIM_SEED"] = "42"


def inject_stress_entities(app):
    """Inject 30 heroes and 60 enemies after engine setup."""
    from game.entities.hero import Hero
    from game.entities.enemy import Goblin, Skeleton, Bandit
    from game.sim.determinism import get_rng
    from config import TILE_SIZE, MAP_WIDTH, MAP_HEIGHT

    sim = app.engine.sim
    rng = get_rng("ursina_stress_setup")
    map_px_w = MAP_WIDTH * TILE_SIZE
    map_px_h = MAP_HEIGHT * TILE_SIZE

    # 30 heroes scattered
    for i in range(30):
        angle = 2 * math.pi * i / 30
        radius_frac = 0.25 + 0.35 * rng.random()
        cx, cy = map_px_w * 0.5, map_px_h * 0.5
        hx = cx + math.cos(angle) * radius_frac * cx
        hy = cy + math.sin(angle) * radius_frac * cy
        hx = max(TILE_SIZE * 3, min(map_px_w - TILE_SIZE * 3, hx))
        hy = max(TILE_SIZE * 3, min(map_px_h - TILE_SIZE * 3, hy))
        classes = ["warrior", "ranger", "rogue", "cleric"]
        hero = Hero(hx, hy, hero_class=classes[i % 4])
        sim.heroes.append(hero)

    # 60 enemies scattered
    for i in range(60):
        ex = rng.uniform(TILE_SIZE * 5, map_px_w - TILE_SIZE * 5)
        ey = rng.uniform(TILE_SIZE * 5, map_px_h - TILE_SIZE * 5)
        etype = [Goblin, Skeleton, Bandit][i % 3]
        sim.enemies.append(etype(ex, ey))

    # Force-discover all POIs
    for poi in getattr(sim, "pois", []):
        poi.is_discovered = True

    # Give heroes movement targets
    for hero in sim.heroes:
        if getattr(hero, "is_alive", False):
            tx = rng.uniform(TILE_SIZE * 5, map_px_w - TILE_SIZE * 5)
            ty = rng.uniform(TILE_SIZE * 5, map_px_h - TILE_SIZE * 5)
            hero.set_target_position(tx, ty)

    print(f"  Injected: {len(sim.heroes)} heroes, {len(sim.enemies)} enemies")
    print(f"  POIs discovered: {len(getattr(sim, 'pois', []))}")
    print(f"  Instancing: {'ON' if os.environ.get('KINGDOM_URSINA_INSTANCING', '1') != '0' else 'OFF'}")


def main():
    print("=" * 60)
    print("  URSINA FPS STRESS TEST (30 heroes + 60 enemies)")
    print("=" * 60)
    print(f"  Will auto-exit after 10 seconds.")
    print(f"  FPS probe: warmup 2s, then measure for 8s.")
    print()

    from game.graphics.ursina_app import UrsinaApp
    from ai.basic_ai import BasicAI

    def create_ai():
        return BasicAI(llm_brain=None)

    app = UrsinaApp(ai_controller_factory=create_ai)
    inject_stress_entities(app)

    print("\n  Launching Ursina renderer... (watch FPS counter in window)")
    print("  Will print results after 10 seconds.\n")
    app.run()

    # After app.run() exits, print FPS probe results
    probe_samples = getattr(app, "_fps_probe_samples", [])
    stage_samples = getattr(app, "_fps_probe_stage_samples", {})

    if probe_samples:
        fps_vals = [1.0 / max(d, 0.001) for d in probe_samples]
        fps_vals.sort()
        avg_fps = sum(fps_vals) / len(fps_vals)
        p1 = fps_vals[max(0, int(len(fps_vals) * 0.01))]
        p5 = fps_vals[max(0, int(len(fps_vals) * 0.05))]
        p50 = fps_vals[len(fps_vals) // 2]

        print("\n" + "=" * 60)
        print("  FPS RESULTS (after 2s warmup)")
        print("=" * 60)
        print(f"  Samples: {len(fps_vals)}")
        print(f"  Avg FPS: {avg_fps:.1f}")
        print(f"  P50 FPS: {p50:.1f}")
        print(f"  P5 (low): {p5:.1f}")
        print(f"  P1 (worst): {p1:.1f}")

        if stage_samples:
            print(f"\n  {'Stage':<22} {'Avg ms':>8} {'Max ms':>8}")
            print("  " + "-" * 40)
            for stage, samples in sorted(stage_samples.items()):
                if samples:
                    avg_ms = sum(samples) / len(samples)
                    max_ms = max(samples)
                    print(f"  {stage:<22} {avg_ms:>8.2f} {max_ms:>8.2f}")

        target = 30.0
        if avg_fps >= target:
            print(f"\n  PASS: Average FPS {avg_fps:.0f} meets {target:.0f} FPS target")
        else:
            print(f"\n  BELOW TARGET: {avg_fps:.0f} FPS (target: {target:.0f})")
        print("=" * 60)
    else:
        print("\n  No FPS probe data collected (app may have exited too early).")


if __name__ == "__main__":
    main()
