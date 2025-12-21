"""
Headless performance benchmark runner.

Goal: provide a repeatable, low-friction way to measure simulation cost as entity counts scale.
This is deliberately simple and prints a short summary (ms/tick + breakdown + pathfinding stats).

Examples:
  python tools/perf_benchmark.py --seconds 10 --heroes 20 --enemies 20 --seed 3
  python tools/perf_benchmark.py --seconds 20 --heroes 40 --enemies 60 --csv perf.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
import time
from pathlib import Path

# Headless pygame setup (safe for CI / no-window environments)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

# Ensure imports work when running as `python tools/perf_benchmark.py`
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import TILE_SIZE, MAP_WIDTH, MAP_HEIGHT  # noqa: E402
from game.world import World  # noqa: E402
from game.entities import (  # noqa: E402
    Castle,
    WarriorGuild,
    Marketplace,
    Hero,
    Goblin,
    Peasant,
)
from game.systems.economy import EconomySystem  # noqa: E402
from game.systems.combat import CombatSystem  # noqa: E402
from game.systems import perf_stats  # noqa: E402
from ai.basic_ai import BasicAI  # noqa: E402


def _fmt(v: float) -> str:
    return f"{v:0.3f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Headless perf benchmark (ms/tick)")
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--heroes", type=int, default=20, help="number of warrior heroes")
    ap.add_argument("--enemies", type=int, default=20, help="number of goblins")
    ap.add_argument("--realtime", action="store_true", help="advance pygame time similarly to realtime (slower)")
    ap.add_argument("--csv", type=str, default="", help="optional path to append one row of results")
    ns = ap.parse_args()

    random.seed(int(ns.seed))

    pygame.init()
    pygame.display.init()
    pygame.display.set_mode((1, 1))

    world = World()

    # Center-ish placement
    cx = MAP_WIDTH // 2 - 1
    cy = MAP_HEIGHT // 2 - 1
    castle = Castle(cx, cy)
    guild = WarriorGuild(cx - 6, cy + 4)
    market = Marketplace(cx + 6, cy + 4)
    buildings = [castle, guild, market]

    # Ensure the tiles under the castle are walkable (mirror engine behavior)
    for dy in range(getattr(castle, "size", (3, 3))[1]):
        for dx in range(getattr(castle, "size", (3, 3))[0]):
            world.set_tile(cx + dx, cy + dy, 2)  # PATH

    heroes = []
    for _ in range(max(0, int(ns.heroes))):
        h = Hero(guild.center_x + TILE_SIZE, guild.center_y, hero_class="warrior")
        h.home_building = guild
        h.gold = 120
        heroes.append(h)

    peasants = [Peasant(castle.center_x, castle.center_y)]

    enemies = []
    n_enemies = max(0, int(ns.enemies))
    for i in range(n_enemies):
        # Spawn in a ring around the castle to create motion + occasional pathing.
        angle = (i / max(1, n_enemies)) * 6.283185307179586
        radius = TILE_SIZE * (10 + (i % 6))
        ex = castle.center_x + (radius * (0.7 * (1.0 if i % 2 == 0 else -1.0)))  # cheap spread
        ey = castle.center_y + (radius * (0.7 * (1.0 if (i // 2) % 2 == 0 else -1.0)))
        g = Goblin(ex, ey)
        enemies.append(g)

    economy = EconomySystem()
    combat = CombatSystem()
    ai = BasicAI(llm_brain=None)

    dt = 1.0 / 60.0
    ticks = int(float(ns.seconds) * 60.0)

    # Perf counters
    perf_stats.reset_pathfinding()

    t_total0 = time.perf_counter()
    t_ai = 0.0
    t_heroes = 0.0
    t_peasants = 0.0
    t_enemies = 0.0
    t_combat = 0.0

    for _ in range(ticks):
        if ns.realtime:
            pygame.time.delay(int(dt * 1000))
            pygame.event.pump()

        game_state = {
            "heroes": heroes,
            "peasants": peasants,
            "guards": [],
            "enemies": enemies,
            "buildings": buildings,
            "bounties": [],
            "castle": castle,
            "economy": economy,
            "world": world,
        }

        t0 = time.perf_counter()
        ai.update(dt, heroes, game_state)
        t1 = time.perf_counter()
        for h in heroes:
            h.update(dt, game_state)
        t2 = time.perf_counter()
        for p in peasants:
            p.update(dt, game_state)
        t3 = time.perf_counter()
        for e in enemies:
            e.update(dt, heroes, peasants, buildings, guards=[], world=world)
        t4 = time.perf_counter()
        combat.process_combat(heroes, enemies, buildings)
        t5 = time.perf_counter()

        t_ai += (t1 - t0)
        t_heroes += (t2 - t1)
        t_peasants += (t3 - t2)
        t_enemies += (t4 - t3)
        t_combat += (t5 - t4)

        # Cleanup (match engine-ish behavior)
        enemies[:] = [e for e in enemies if getattr(e, "is_alive", False)]

    t_total1 = time.perf_counter()

    sim_s = float(ns.seconds)
    ticks_done = max(1, ticks)
    total_ms_per_tick = ((t_total1 - t_total0) * 1000.0) / ticks_done

    ai_ms = (t_ai * 1000.0) / ticks_done
    heroes_ms = (t_heroes * 1000.0) / ticks_done
    peasants_ms = (t_peasants * 1000.0) / ticks_done
    enemies_ms = (t_enemies * 1000.0) / ticks_done
    combat_ms = (t_combat * 1000.0) / ticks_done

    pf_calls = int(perf_stats.pathfinding.calls)
    pf_fails = int(perf_stats.pathfinding.failures)
    pf_total_ms = float(perf_stats.pathfinding.total_ms)
    pf_ms_per_tick = (pf_total_ms / ticks_done) if ticks_done else 0.0

    print("[perf] seconds:", sim_s, "ticks:", ticks_done)
    print("[perf] entities: heroes=", len(heroes), "enemies(end)=", len(enemies), "peasants=", len(peasants))
    print("[perf] ms/tick total:", _fmt(total_ms_per_tick))
    print(
        "[perf] ms/tick breakdown: ai=",
        _fmt(ai_ms),
        "heroes=",
        _fmt(heroes_ms),
        "peasants=",
        _fmt(peasants_ms),
        "enemies=",
        _fmt(enemies_ms),
        "combat=",
        _fmt(combat_ms),
    )
    print("[perf] pathfinding: calls=", pf_calls, "fails=", pf_fails, "ms_total=", _fmt(pf_total_ms), "ms/tick=", _fmt(pf_ms_per_tick))

    if ns.csv:
        out_path = Path(ns.csv)
        write_header = not out_path.exists()
        with out_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(
                    [
                        "seconds",
                        "seed",
                        "heroes",
                        "enemies_start",
                        "enemies_end",
                        "ticks",
                        "ms_per_tick_total",
                        "ms_per_tick_ai",
                        "ms_per_tick_heroes",
                        "ms_per_tick_peasants",
                        "ms_per_tick_enemies",
                        "ms_per_tick_combat",
                        "pf_calls",
                        "pf_fails",
                        "pf_total_ms",
                        "pf_ms_per_tick",
                    ]
                )
            w.writerow(
                [
                    sim_s,
                    int(ns.seed),
                    int(ns.heroes),
                    int(ns.enemies),
                    int(len(enemies)),
                    int(ticks_done),
                    float(total_ms_per_tick),
                    float(ai_ms),
                    float(heroes_ms),
                    float(peasants_ms),
                    float(enemies_ms),
                    float(combat_ms),
                    int(pf_calls),
                    int(pf_fails),
                    float(pf_total_ms),
                    float(pf_ms_per_tick),
                ]
            )
        print("[perf] wrote:", str(out_path))

    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


