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
from game.entities import Castle, WarriorGuild, RangerGuild, RogueGuild, WizardGuild, Marketplace, Hero, Goblin, Peasant  # noqa: E402
from game.systems.economy import EconomySystem  # noqa: E402
from game.systems.combat import CombatSystem  # noqa: E402
from game.systems.bounty import Bounty  # noqa: E402
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


def hero_potions_summary(heroes) -> str:
    alive = [h for h in heroes if getattr(h, "is_alive", True)]
    counts = [getattr(h, "potions", 0) for h in alive]
    if not counts:
        return "potions=none"
    total = sum(counts)
    mx = max(counts)
    return f"potions_total={total} max={mx}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--heroes", type=int, default=8)
    ap.add_argument("--rangers", type=int, default=0, help="number of ranger heroes to spawn (in addition to --heroes)")
    ap.add_argument("--rogues", type=int, default=0, help="number of rogue heroes to spawn")
    ap.add_argument("--wizards", type=int, default=0, help="number of wizard heroes to spawn")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--log-every", type=int, default=60, help="log every N ticks (60 ~= 1s at 60fps)")
    ap.add_argument("--start-gold", type=int, default=120, help="starting spendable gold per hero")
    ap.add_argument("--potions", action="store_true", help="start with potions researched at the marketplace")
    ap.add_argument("--bounty", action="store_true", help="add one explore bounty to observe class-weighted pursuit")
    ap.add_argument("--no-enemies", action="store_true", help="disable enemies (useful to isolate shopping/potions behavior)")
    ap.add_argument("--realtime", action="store_true", help="run the sim in (approx) real time so pygame ticks/cooldowns advance")
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
    ranger_guild = RangerGuild(cx - 6, cy + 8)
    rogue_guild = RogueGuild(cx - 10, cy + 4)
    wizard_guild = WizardGuild(cx - 10, cy + 8)
    market = Marketplace(cx + 6, cy + 4)
    market.potions_researched = bool(args.potions)

    buildings = [castle, guild, ranger_guild, rogue_guild, wizard_guild, market]

    # Simulate one newly placed (unconstructed) building to exercise peasant behavior.
    new_building = Marketplace(cx + 10, cy - 2)
    new_building.potions_researched = False
    if hasattr(new_building, "mark_unconstructed"):
        new_building.mark_unconstructed()
    buildings.append(new_building)

    heroes = []
    for _ in range(args.heroes):
        h = Hero(guild.center_x + TILE_SIZE, guild.center_y)
        h.home_building = guild
        h.gold = args.start_gold
        heroes.append(h)

    for _ in range(args.rangers):
        h = Hero(ranger_guild.center_x + TILE_SIZE, ranger_guild.center_y, hero_class="ranger")
        h.home_building = ranger_guild
        h.gold = args.start_gold
        heroes.append(h)

    for _ in range(args.rogues):
        h = Hero(rogue_guild.center_x + TILE_SIZE, rogue_guild.center_y, hero_class="rogue")
        h.home_building = rogue_guild
        h.gold = args.start_gold
        heroes.append(h)

    for _ in range(args.wizards):
        h = Hero(wizard_guild.center_x + TILE_SIZE, wizard_guild.center_y, hero_class="wizard")
        h.home_building = wizard_guild
        h.gold = args.start_gold
        heroes.append(h)

    # A dedicated tester hero near the new building to validate enemy retarget-on-hit.
    tester = Hero(new_building.center_x - TILE_SIZE * 1.0, new_building.center_y)
    tester.home_building = guild
    tester.gold = args.start_gold
    tester.state = tester.state.IDLE
    heroes.append(tester)

    enemies = []
    attacker = None
    if not args.no_enemies:
        # Enemies: one far (should NOT be perceived), one near (should be perceived occasionally)
        enemies = [
            Goblin(TILE_SIZE * 2, TILE_SIZE * 2),
            Goblin(castle.center_x + TILE_SIZE * 4, castle.center_y),
        ]
        # Force a goblin to start by attacking the new building, so we can verify retarget-on-hit.
        attacker = Goblin(new_building.center_x + TILE_SIZE * 0.5, new_building.center_y)
        attacker.target = new_building
        enemies.append(attacker)

    # One peasant to build/repair in the observer
    peasants = [Peasant(castle.center_x, castle.center_y)]

    bounties = []
    if args.bounty:
        # Place a bounty far enough that warriors usually ignore it, but rangers consider it.
        bx = min((MAP_WIDTH - 2) * TILE_SIZE, castle.center_x + TILE_SIZE * 12)
        by = castle.center_y
        bounties = [Bounty(bx, by, reward=60, bounty_type="explore")]

    economy = EconomySystem()
    combat = CombatSystem()
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
        if args.realtime:
            # Keep pygame's internal clock advancing similarly to the real game loop.
            pygame.time.delay(int(dt * 1000))
            pygame.event.pump()

        game_state = {
            "heroes": heroes,
            "peasants": peasants,
            "enemies": enemies,
            "buildings": buildings,
            "bounties": bounties,
            "castle": castle,
            "economy": economy,
        }

        ai.update(dt, heroes, game_state)
        for h in heroes:
            h.update(dt, game_state)
        for p in peasants:
            p.update(dt, game_state)

        # Process combat so hero hits can trigger retarget logic in CombatSystem.
        combat.process_combat(heroes, enemies, buildings)

        # Damage castle once to confirm peasants prioritize repairing it over construction.
        if (not args.no_enemies) and t == 180:
            castle.take_damage(50)

        # Optional: keep the near goblin "tickling" the castle so we can observe defend behavior.
        if (not args.no_enemies) and t % 180 == 0 and t > 0:
            castle.take_damage(1)

        if t % args.log_every == 0:
            apd = avg_pairwise_distance(heroes)
            nb = new_building
            nb_state = f"hp={int(getattr(nb,'hp',0))}/{int(getattr(nb,'max_hp',0))} started={getattr(nb,'construction_started',False)} built={getattr(nb,'is_constructed',True)} targetable={getattr(nb,'is_targetable',True)}"
            castle_state = f"castle_hp={int(getattr(castle,'hp',0))}/{int(getattr(castle,'max_hp',0))}"
            pot_state = hero_potions_summary(heroes)
            print(f"[t={t:04d}] avg_pairwise_dist={apd:.1f}  alive={len([h for h in heroes if h.is_alive])}  {pot_state}  {castle_state}  new_building[{nb_state}]")
            for h in heroes[: min(8, len(heroes))]:
                hid = getattr(h, "debug_id", h.name)
                hcls = getattr(h, "hero_class", "?")
                print(
                    f"  - {hid:<12} cls={hcls:<7} state={h.state.name:<10} gold={h.gold:<4} pots={getattr(h,'potions',0):<2} pos=({h.x:6.1f},{h.y:6.1f}) tgt={hero_target_label(h)}"
                )
            for p in peasants:
                print(f"  - Peasant      state={getattr(p,'state',None).name if getattr(p,'state',None) else '?':<10} hp={p.hp}/{p.max_hp} inside_castle={getattr(p,'is_inside_castle',False)} pos=({p.x:6.1f},{p.y:6.1f})")
            if attacker is not None:
                # Show whether the forced building-attacker goblin has retargeted off the building.
                tgt = getattr(attacker, "target", None)
                tgt_label = "None"
                if tgt is not None:
                    if hasattr(tgt, "building_type"):
                        tgt_label = f"building:{tgt.building_type}"
                    elif hasattr(tgt, "hero_class"):
                        tgt_label = f"hero:{getattr(tgt,'name','?')}"
                    elif hasattr(tgt, "is_inside_castle"):
                        tgt_label = "peasant"
                    else:
                        tgt_label = tgt.__class__.__name__
                print(f"  - GoblinAttacker target={tgt_label}")

    if llm:
        llm.stop()
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


