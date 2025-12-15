"""
Headless "observer" runner to reproduce and measure hero clumping / synchronized behavior.

Runs a simplified simulation loop (no rendering) and prints:
- duplicate hero names (if any)
- per-hero state + target
- a simple clumping metric (avg pairwise distance)

Usage:
  python tools/observe_sync.py --seconds 20 --heroes 8 --seed 3
"""

import os
import sys
import argparse
import math
import random
from collections import Counter
from pathlib import Path

# Headless pygame setup (safe for CI / no-window environments)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

# Ensure imports work when running as `python tools/observe_sync.py`
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import TILE_SIZE, MAP_WIDTH, MAP_HEIGHT  # noqa: E402
from game.world import World  # noqa: E402
from game.entities import Castle, WarriorGuild, Marketplace, Hero, Goblin  # noqa: E402
from game.systems.economy import EconomySystem  # noqa: E402
from ai.basic_ai import BasicAI  # noqa: E402
from ai.llm_brain import LLMBrain  # noqa: E402


def avg_pairwise_distance(objs) -> float:
    alive = [o for o in objs if getattr(o, "is_alive", True)]
    n = len(alive)
    if n < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = alive[i].x - alive[j].x
            dy = alive[i].y - alive[j].y
            total += math.sqrt(dx * dx + dy * dy)
            count += 1
    return total / max(count, 1)


def hero_target_label(hero) -> str:
    tgt = getattr(hero, "target", None)
    if tgt is None:
        return "-"
    if isinstance(tgt, dict):
        return tgt.get("type", "dict")
    if hasattr(tgt, "enemy_type"):
        return f"enemy:{tgt.enemy_type}"
    if hasattr(tgt, "building_type"):
        return f"building:{tgt.building_type}"
    return tgt.__class__.__name__


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--heroes", type=int, default=8)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--log-every", type=int, default=60, help="log every N ticks (60 ~= 1s at 60fps)")
    ap.add_argument("--start-gold", type=int, default=120, help="starting spendable gold per hero")
    ap.add_argument("--potions", action="store_true", help="start with potions researched at the marketplace")
    ap.add_argument("--llm", action="store_true", help="enable LLM brain (mock provider) to observe decisions")
    args = ap.parse_args()

    random.seed(args.seed)

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
    market.potions_researched = bool(args.potions)

    buildings = [castle, guild, market]

    heroes = []
    for _ in range(args.heroes):
        h = Hero(guild.center_x + TILE_SIZE, guild.center_y)
        h.home_building = guild
        h.gold = args.start_gold
        heroes.append(h)

    # Enemies: one far (should NOT be perceived), one near (should be perceived occasionally)
    enemies = [
        Goblin(TILE_SIZE * 2, TILE_SIZE * 2),
        Goblin(castle.center_x + TILE_SIZE * 4, castle.center_y),
    ]

    economy = EconomySystem()
    llm = LLMBrain(provider_name="mock") if args.llm else None
    ai = BasicAI(llm_brain=llm)

    name_counts = Counter([h.name for h in heroes])
    dupes = {n: c for n, c in name_counts.items() if c > 1}
    if dupes:
        print("[observe] Duplicate hero names detected:", dupes)
    else:
        print("[observe] No duplicate hero names.")

    dt = 1.0 / 60.0
    ticks = int(args.seconds * 60)

    for t in range(ticks):
        game_state = {
            "heroes": heroes,
            "enemies": enemies,
            "buildings": buildings,
            "bounties": [],
            "castle": castle,
            "economy": economy,
        }

        ai.update(dt, heroes, game_state)
        for h in heroes:
            h.update(dt, game_state)

        # Optional: keep the near goblin "tickling" the castle so we can observe defend behavior.
        if t % 180 == 0 and t > 0:
            castle.take_damage(1)

        if t % args.log_every == 0:
            apd = avg_pairwise_distance(heroes)
            print(f"[t={t:04d}] avg_pairwise_dist={apd:.1f}  alive={len([h for h in heroes if h.is_alive])}")
            for h in heroes[: min(8, len(heroes))]:
                hid = getattr(h, "debug_id", h.name)
                print(
                    f"  - {hid:<12} state={h.state.name:<10} gold={h.gold:<4} pos=({h.x:6.1f},{h.y:6.1f}) tgt={hero_target_label(h)}"
                )

    if llm:
        llm.stop()
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


