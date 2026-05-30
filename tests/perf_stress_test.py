"""
Performance stress test: 30 heroes exploring map, discovering POIs, spawning enemies.

Runs the headless sim for N ticks and profiles each subsystem to identify bottlenecks.
Usage:
    python -m tests.perf_stress_test [--ticks 600] [--heroes 30] [--verbose]
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["DETERMINISTIC_SIM"] = "1"
# WK68 R0 (Agent 04): SIM_SEED is set inside main(), NOT at import scope. pytest
# collection imports this module; setting SIM_SEED here would mutate the shared
# process env and shift config.SIM_SEED for the whole suite (e.g. the WK67
# AI-decision digest). The run-as-script path applies it in main() instead.


def setup_sim(num_heroes: int):
    """Create a headless SimEngine with N heroes scattered across the map."""
    import pygame
    pygame.init()

    from game.sim_engine import SimEngine
    from game.entities.hero import Hero
    from game.sim.determinism import get_rng
    from config import TILE_SIZE, MAP_WIDTH, MAP_HEIGHT

    sim = SimEngine()
    sim.setup_initial_state()

    rng = get_rng("perf_stress_setup")
    map_px_w = MAP_WIDTH * TILE_SIZE
    map_px_h = MAP_HEIGHT * TILE_SIZE

    # Scatter heroes across the map to simulate exploration
    for i in range(num_heroes):
        angle = 2 * math.pi * i / num_heroes
        radius_frac = 0.3 + 0.4 * rng.random()
        cx = map_px_w * 0.5
        cy = map_px_h * 0.5
        hx = cx + math.cos(angle) * radius_frac * cx
        hy = cy + math.sin(angle) * radius_frac * cy
        hx = max(TILE_SIZE * 2, min(map_px_w - TILE_SIZE * 2, hx))
        hy = max(TILE_SIZE * 2, min(map_px_h - TILE_SIZE * 2, hy))

        classes = ["warrior", "ranger", "rogue", "cleric"]
        hero = Hero(hx, hy, hero_class=classes[i % len(classes)])
        sim.heroes.append(hero)

    # Force-discover all POIs so the interaction system fires every tick
    for poi in sim.pois:
        poi.is_discovered = True

    return sim


def run_stress_test(sim, num_ticks: int, verbose: bool = False):
    """Run sim ticks and profile each major subsystem."""
    from config import TILE_SIZE, MAP_WIDTH, MAP_HEIGHT
    from game.sim.determinism import get_rng

    rng = get_rng("perf_stress_movement")
    map_px_w = MAP_WIDTH * TILE_SIZE
    map_px_h = MAP_HEIGHT * TILE_SIZE

    dt = 1.0 / 60.0  # simulate at 60Hz

    # Build game_state dict (mimics engine.get_game_state())
    castle = next((b for b in sim.buildings if getattr(b, "building_type", "") == "castle"), None)
    game_state = {
        "heroes": sim.heroes,
        "enemies": sim.enemies,
        "buildings": sim.buildings,
        "world": sim.world,
        "castle": castle,
        "economy": sim.economy,
        "bounties": sim.bounties,
        "peasants": sim.peasants,
        "guards": sim.guards,
    }

    # Profiling accumulators (milliseconds)
    timings = {
        "hero_update": 0.0,
        "enemy_update": 0.0,
        "combat": 0.0,
        "separation": 0.0,
        "poi_discovery": 0.0,
        "poi_interaction": 0.0,
        "fog_of_war": 0.0,
        "spawner": 0.0,
        "nature": 0.0,
        "total_tick": 0.0,
    }
    tick_times = []
    max_enemies_seen = 0
    max_heroes_alive = len(sim.heroes)

    for tick in range(num_ticks):
        tick_start = time.perf_counter()

        # Give heroes random movement targets every 60 ticks
        if tick % 60 == 0:
            for hero in sim.heroes:
                if getattr(hero, "is_alive", False):
                    tx = rng.uniform(TILE_SIZE * 5, map_px_w - TILE_SIZE * 5)
                    ty = rng.uniform(TILE_SIZE * 5, map_px_h - TILE_SIZE * 5)
                    hero.set_target_position(tx, ty)

        # --- Profile each subsystem independently ---

        # Hero updates (movement + pathfinding)
        t0 = time.perf_counter()
        for hero in sim.heroes:
            hero.update(dt, game_state)
        timings["hero_update"] += (time.perf_counter() - t0) * 1000.0

        # Enemy updates
        t0 = time.perf_counter()
        for enemy in sim.enemies:
            enemy.update(dt, sim.heroes, sim.peasants, sim.buildings, guards=sim.guards, world=sim.world)
        timings["enemy_update"] += (time.perf_counter() - t0) * 1000.0

        # Combat
        t0 = time.perf_counter()
        ctx = sim._build_system_context()
        sim.combat_system.update(ctx, dt)
        events = sim.combat_system.get_emitted_events()
        sim._route_combat_events(events)
        timings["combat"] += (time.perf_counter() - t0) * 1000.0

        # Entity separation
        t0 = time.perf_counter()
        sim._apply_entity_separation(dt)
        timings["separation"] += (time.perf_counter() - t0) * 1000.0

        # POI discovery
        t0 = time.perf_counter()
        sim._check_poi_discovery()
        timings["poi_discovery"] += (time.perf_counter() - t0) * 1000.0

        # POI interaction (this spawns enemies via combat POIs)
        t0 = time.perf_counter()
        sim.poi_interaction_system.tick_cooldowns(sim.pois, dt)
        sim.poi_interaction_system.check_interactions(
            sim.heroes, sim.pois, sim.world, sim.economy, sim.event_bus, dt
        )
        timings["poi_interaction"] += (time.perf_counter() - t0) * 1000.0

        # Fog of war
        t0 = time.perf_counter()
        sim._update_fog_of_war()
        timings["fog_of_war"] += (time.perf_counter() - t0) * 1000.0

        # Enemy spawner (lair + random)
        t0 = time.perf_counter()
        from config import MAX_ALIVE_ENEMIES
        alive_enemy_count = len([e for e in sim.enemies if getattr(e, "is_alive", False)])
        remaining_slots = max(0, int(MAX_ALIVE_ENEMIES) - alive_enemy_count)
        if remaining_slots > 0:
            new_enemies = sim.spawner.spawn(dt)
            if new_enemies:
                sim.enemies.extend(new_enemies[:remaining_slots])
            alive_enemy_count = len([e for e in sim.enemies if getattr(e, "is_alive", False)])
            remaining_slots = max(0, int(MAX_ALIVE_ENEMIES) - alive_enemy_count)
            if remaining_slots > 0:
                lair_enemies = sim.lair_system.spawn_enemies(dt, sim.buildings)
                if lair_enemies:
                    sim.enemies.extend(lair_enemies[:remaining_slots])
        timings["spawner"] += (time.perf_counter() - t0) * 1000.0

        # Cleanup dead
        sim.enemies = [e for e in sim.enemies if getattr(e, "is_alive", False)]

        # Nature (tree growth)
        t0 = time.perf_counter()
        try:
            sim.nature_system.tick(dt, sim.trees, world=sim.world, buildings=sim.buildings)
        except TypeError:
            sim.nature_system.tick(dt, sim.trees)
        timings["nature"] += (time.perf_counter() - t0) * 1000.0

        tick_elapsed_ms = (time.perf_counter() - tick_start) * 1000.0
        timings["total_tick"] += tick_elapsed_ms
        tick_times.append(tick_elapsed_ms)

        alive_enemies = len([e for e in sim.enemies if getattr(e, "is_alive", False)])
        max_enemies_seen = max(max_enemies_seen, alive_enemies)
        alive_heroes = len([h for h in sim.heroes if getattr(h, "is_alive", False)])
        max_heroes_alive = max(max_heroes_alive, alive_heroes)

        if verbose and tick % 100 == 0:
            print(f"  tick {tick:4d}: {tick_elapsed_ms:6.2f}ms | "
                  f"heroes={alive_heroes} enemies={alive_enemies}")

    return timings, tick_times, max_enemies_seen, max_heroes_alive


def print_results(timings, tick_times, num_ticks, max_enemies, max_heroes, num_heroes):
    """Print formatted profiling results."""
    print("\n" + "=" * 70)
    print(f"  PERFORMANCE STRESS TEST RESULTS ({num_heroes} heroes, {num_ticks} ticks)")
    print("=" * 70)

    print(f"\n  Peak entities: {max_heroes} heroes, {max_enemies} enemies")
    print(f"  Total sim time: {timings['total_tick']:.1f}ms over {num_ticks} ticks")

    avg_tick = timings["total_tick"] / num_ticks
    target_budget_ms = 1000.0 / 60.0  # 16.67ms for 60fps
    estimated_fps = 1000.0 / max(0.01, avg_tick)

    print(f"\n  Avg tick: {avg_tick:.2f}ms (budget: {target_budget_ms:.2f}ms for 60fps)")
    print(f"  Estimated headless FPS: {estimated_fps:.1f}")

    # Worst ticks
    sorted_ticks = sorted(tick_times, reverse=True)
    p99 = sorted_ticks[max(0, int(len(sorted_ticks) * 0.01))]
    p95 = sorted_ticks[max(0, int(len(sorted_ticks) * 0.05))]
    p50 = sorted_ticks[len(sorted_ticks) // 2]
    print(f"  P50: {p50:.2f}ms | P95: {p95:.2f}ms | P99: {p99:.2f}ms | Max: {sorted_ticks[0]:.2f}ms")

    print(f"\n  {'Subsystem':<20} {'Total (ms)':>12} {'Avg/tick (ms)':>14} {'% of tick':>10}")
    print("  " + "-" * 58)
    for key in sorted(timings.keys(), key=lambda k: timings[k], reverse=True):
        if key == "total_tick":
            continue
        total = timings[key]
        avg = total / num_ticks
        pct = (total / timings["total_tick"]) * 100 if timings["total_tick"] > 0 else 0
        marker = " <<<" if pct > 25 else (" !!" if pct > 15 else "")
        print(f"  {key:<20} {total:>12.1f} {avg:>14.3f} {pct:>9.1f}%{marker}")

    print("\n  Legend: <<< = primary bottleneck (>25%), !! = significant (>15%)")

    if avg_tick > target_budget_ms:
        overshoot = avg_tick / target_budget_ms
        print(f"\n  WARNING: Tick budget exceeded by {overshoot:.1f}x!")
        print(f"  Need to reduce tick cost from {avg_tick:.2f}ms to <{target_budget_ms:.2f}ms")
    else:
        headroom = target_budget_ms - avg_tick
        print(f"\n  OK: {headroom:.2f}ms headroom within 60fps budget (sim only, no render)")

    print("=" * 70)


def main():
    # WK68 R0: apply the fixed perf seed here (script entry point), not at import
    # scope, so pytest collection never mutates the shared process env.
    os.environ["SIM_SEED"] = "42"
    parser = argparse.ArgumentParser(description="Kingdom Sim performance stress test")
    parser.add_argument("--ticks", type=int, default=600, help="Number of sim ticks to run")
    parser.add_argument("--heroes", type=int, default=30, help="Number of heroes to spawn")
    parser.add_argument("--verbose", action="store_true", help="Print per-tick status")
    args = parser.parse_args()

    print(f"Setting up stress test: {args.heroes} heroes, {args.ticks} ticks...")
    sim = setup_sim(args.heroes)
    print(f"  World: {sim.world.width}x{sim.world.height} tiles")
    print(f"  POIs: {len(sim.pois)} (all pre-discovered)")
    print(f"  Initial enemies: {len(sim.enemies)}")
    print(f"  Lairs: {len([b for b in sim.buildings if hasattr(b, 'stash_gold')])}")
    print(f"\nRunning {args.ticks} ticks...")

    timings, tick_times, max_enemies, max_heroes = run_stress_test(
        sim, args.ticks, verbose=args.verbose
    )

    print_results(timings, tick_times, args.ticks, max_enemies, max_heroes, args.heroes)


if __name__ == "__main__":
    main()
