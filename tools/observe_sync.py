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
from game.sim.timebase import set_sim_now_ms  # noqa: E402
from game.world import World, TileType  # noqa: E402
from game.entities import Castle, WarriorGuild, RangerGuild, RogueGuild, WizardGuild, Marketplace, Hero, Goblin, Peasant  # noqa: E402
from game.systems.economy import EconomySystem  # noqa: E402
from game.systems.combat import CombatSystem  # noqa: E402
from game.systems.bounty import BountySystem  # noqa: E402
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


def bounties_summary(bounty_system) -> str:
    try:
        total = len(getattr(bounty_system, "bounties", []))
        unclaimed = len(bounty_system.get_unclaimed_bounties())
        total_claimed = int(getattr(bounty_system, "total_claimed", 0))
        total_spent = int(getattr(bounty_system, "total_spent", 0))
        return f"bounties_unclaimed={unclaimed}/{total} claimed={total_claimed} spent={total_spent}"
    except Exception:
        return "bounties=?"


def place_intent_bounty_scenario(*, bounty_system, castle, seed: int) -> None:
    """
    Deterministic mini-scenario intended to exercise bounty placement + response/claim quickly.

    - One close explore bounty (reachable/claimable quickly)
    - One farther explore bounty (gives an additional incentive target)
    """
    rnd = random.Random(int(seed) + 101)

    base_x = float(getattr(castle, "center_x", 0.0))
    base_y = float(getattr(castle, "center_y", 0.0))

    # Close: ~5 tiles away.
    bx1 = base_x + float(TILE_SIZE) * 5.0
    by1 = base_y + float(TILE_SIZE) * 1.0
    bounty_system.place_bounty(bx1, by1, reward=60, bounty_type="explore")

    # Far: ~14 tiles away, slight randomization within a tile to avoid exact overlaps.
    bx2 = base_x + float(TILE_SIZE) * 14.0 + float(rnd.randint(-8, 8))
    by2 = base_y - float(TILE_SIZE) * 6.0 + float(rnd.randint(-8, 8))
    bounty_system.place_bounty(bx2, by2, reward=90, bounty_type="explore")


def _clear_and_cage_tile(world: World, grid_x: int, grid_y: int) -> None:
    """
    Force a deterministic "stuck" situation by surrounding a single walkable tile with blocking tiles.

    This makes any attempt to path out fail, independent of emergent AI choices.
    """
    # Clear a small area to grass so procedural terrain doesn't affect the repro.
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            world.set_tile(grid_x + dx, grid_y + dy, TileType.GRASS)

    # Ring at radius 1 is blocking.
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            world.set_tile(grid_x + dx, grid_y + dy, TileType.TREE)

    # Center stays walkable.
    world.set_tile(grid_x, grid_y, TileType.GRASS)


def _scenario_setup(
    *,
    scenario: str,
    seed: int,
    world: World,
    heroes: list,
    buildings: list,
    enemies: list,
    bounty_system: BountySystem,
    castle,
    market,
) -> None:
    """Apply deterministic scenario modifications (tools-only)."""
    if scenario == "hero_stuck_repro":
        if heroes:
            hx, hy = world.world_to_grid(float(heroes[0].x), float(heroes[0].y))
            _clear_and_cage_tile(world, hx, hy)
        return

    if scenario == "inside_combat_repro":
        if heroes:
            h = heroes[0]
            h.is_inside_building = True
            h.inside_building = market
            h.inside_timer = 0.0
            # Keep the hero inside (RESTING bypasses inside_timer pop-out).
            try:
                h.state = h.state.RESTING
            except Exception:
                pass

            # Ensure at least one enemy is within attack range.
            if not enemies:
                gx, gy = world.world_to_grid(float(h.x), float(h.y))
                ex, ey = world.grid_to_world(gx + 1, gy)
                enemies.append(Goblin(ex + TILE_SIZE / 2, ey + TILE_SIZE / 2))
        return


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
    ap.add_argument(
        "--scenario",
        type=str,
        default="default",
        choices=["default", "intent_bounty", "hero_stuck_repro", "inside_combat_repro"],
        help="deterministic test setup presets (default: default)",
    )
    ap.add_argument("--no-enemies", action="store_true", help="disable enemies (useful to isolate shopping/potions behavior)")
    ap.add_argument("--realtime", action="store_true", help="run the sim in (approx) real time so pygame ticks/cooldowns advance")
    ap.add_argument("--llm", action="store_true", help="enable LLM brain (mock provider) to observe decisions")
    ap.add_argument("--qa", action="store_true", help="enable QA assertions (nonzero exit on failure)")
    ap.add_argument("--qa-warmup-ticks", type=int, default=240, help="wait N ticks before starting QA assertions")
    args = ap.parse_args()

    random.seed(args.seed)

    pygame.init()
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    # Drive sim-time deterministically (avoid dependence on wall-clock ticks).
    set_sim_now_ms(0)

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

    bounty_system = BountySystem()
    if args.bounty:
        if args.qa:
            # QA runs need a bounty that a baseline warrior will actually take quickly.
            bx = min((MAP_WIDTH - 2) * TILE_SIZE, castle.center_x + TILE_SIZE * 6)
            by = castle.center_y
            bounty_system.place_bounty(bx, by, reward=140, bounty_type="explore")
        else:
            # Default observer: place far enough that warriors usually ignore it, but rangers consider it.
            bx = min((MAP_WIDTH - 2) * TILE_SIZE, castle.center_x + TILE_SIZE * 12)
            by = castle.center_y
            bounty_system.place_bounty(bx, by, reward=60, bounty_type="explore")
    if args.scenario == "intent_bounty":
        place_intent_bounty_scenario(bounty_system=bounty_system, castle=castle, seed=int(args.seed))

    # WK2 deterministic repro scenarios (tools-only setup).
    if args.scenario in ("hero_stuck_repro", "inside_combat_repro"):
        _scenario_setup(
            scenario=str(args.scenario),
            seed=int(args.seed),
            world=world,
            heroes=heroes,
            buildings=buildings,
            enemies=enemies,
            bounty_system=bounty_system,
            castle=castle,
            market=market,
        )

    # Local view (unclaimed only); refreshed per tick.
    bounties = bounty_system.get_unclaimed_bounties()

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

    # Drive deterministic sim-time for code that reads "now" (bounties, etc).
    set_sim_now_ms(0)

    # QA assertion tracking (best-effort; will skip checks if features are not implemented yet)
    qa_bounty_exists = False
    qa_bounty_has_responder = False
    qa_any_intent_seen = False
    qa_intent_attr_present = False
    qa_bounty_responder_attr_present = False
    qa_explicit_responder_seen = False
    qa_explicit_responder_positive = False
    qa_seen_bounty_target = False

    # WK2 scenario counters (deterministic repro harness).
    scenario_counters = {"stuck_events": 0, "unstuck_attempts": 0, "inside_attack_blocks": 0, "max_stuck_ms": 0}
    _prev_stuck_active: dict[int, bool] = {}
    _prev_unstuck_attempts: dict[int, int] = {}
    _any_can_attack_field = False
    _any_stuck_fields = False

    def _hero_intent_label(h) -> str:
        # Prefer new explicit intent if present.
        if hasattr(h, "intent"):
            return str(getattr(h, "intent") or "").strip()
        # Fallback: derive from target/state for current prototype.
        tgt = getattr(h, "target", None)
        if isinstance(tgt, dict):
            t = str(tgt.get("type", "")).strip()
            if t:
                return t
        st = getattr(getattr(h, "state", None), "name", "")
        return str(st or "").strip()

    def _bounty_responder_count(bs, hs) -> int:
        # Prefer explicit responder metadata if present.
        if hasattr(bs, "responders"):
            resp = getattr(bs, "responders", None)
            if isinstance(resp, (list, set, tuple)):
                return len(resp)
        if hasattr(bs, "responder_count"):
            try:
                return int(getattr(bs, "responder_count"))
            except Exception:
                return 0
        # Fallback: infer from hero targets + assignment.
        bid = getattr(bs, "bounty_id", None)
        count = 0
        for h in hs:
            if not getattr(h, "is_alive", True):
                continue
            tgt = getattr(h, "target", None)
            if isinstance(tgt, dict) and tgt.get("type") == "bounty":
                if bid is None:
                    # If no id, treat any bounty target as "responding"
                    count += 1
                elif tgt.get("bounty_id") == bid:
                    count += 1
        if getattr(bs, "assigned_to", None):
            # Ensure at least 1 responder when assigned.
            count = max(count, 1)
        return count

    for t in range(ticks):
        # Advance deterministic sim time (ms) at 60Hz.
        set_sim_now_ms(int((t * 1000) / 60))
        if args.realtime:
            # Keep pygame's internal clock advancing similarly to the real game loop.
            pygame.time.delay(int(dt * 1000))
            pygame.event.pump()

        # Keep bounties consistent with the live game: expose only unclaimed bounties.
        bounties = bounty_system.get_unclaimed_bounties()

        game_state = {
            "heroes": heroes,
            "peasants": peasants,
            "enemies": enemies,
            "buildings": buildings,
            "bounties": bounties,
            "bounty_system": bounty_system,
            "castle": castle,
            "economy": economy,
            "world": world,
        }

        ai.update(dt, heroes, game_state)
        for h in heroes:
            h.update(dt, game_state)
        for p in peasants:
            p.update(dt, game_state)

        # Populate bounty contract fields (responders/tier) before any claims/cleanup so QA can observe >0.
        if hasattr(bounty_system, "update_ui_metrics"):
            try:
                bounty_system.update_ui_metrics(heroes, enemies, buildings)
            except Exception:
                pass

        # Process combat so hero hits can trigger retarget logic in CombatSystem.
        combat.process_combat(heroes, enemies, buildings)

        # Process bounties similarly to the live game loop.
        bounty_system.check_claims(heroes)
        bounty_system.cleanup()

        # WK2 scenario metrics/counters (contract-aware, deterministic-friendly).
        now_ms_val = int((t * 1000) / 60)
        for h in heroes:
            hid = id(h)

            # Stuck signals (prefer locked contract fields if present).
            if hasattr(h, "stuck_active") or hasattr(h, "get_stuck_snapshot"):
                _any_stuck_fields = True
            stuck_active = bool(getattr(h, "stuck_active", False))
            if stuck_active and not _prev_stuck_active.get(hid, False):
                scenario_counters["stuck_events"] += 1
            _prev_stuck_active[hid] = stuck_active

            if stuck_active:
                stuck_since = getattr(h, "stuck_since_ms", None)
                if stuck_since is not None:
                    try:
                        dur = max(0, int(now_ms_val) - int(stuck_since))
                        scenario_counters["max_stuck_ms"] = max(int(scenario_counters["max_stuck_ms"]), dur)
                    except Exception:
                        pass

            # Count recovery attempts as deltas (handles resets per target).
            if hasattr(h, "unstuck_attempts"):
                prev = int(_prev_unstuck_attempts.get(hid, 0))
                cur = int(getattr(h, "unstuck_attempts", 0))
                if cur > prev:
                    scenario_counters["unstuck_attempts"] += int(cur - prev)
                _prev_unstuck_attempts[hid] = cur

            # Inside-combat gating counters:
            # Count times a hero is inside, cannot attack, and has an enemy in range while off cooldown.
            if getattr(h, "is_inside_building", False):
                if hasattr(h, "can_attack"):
                    _any_can_attack_field = True
                can_attack_val = bool(getattr(h, "can_attack", True))
                if (not can_attack_val) and getattr(h, "attack_cooldown", 0) <= 0:
                    for e in enemies:
                        if not getattr(e, "is_alive", True):
                            continue
                        try:
                            if h.distance_to(e.x, e.y) <= getattr(h, "attack_range", TILE_SIZE * 1.5):
                                scenario_counters["inside_attack_blocks"] += 1
                                break
                        except Exception:
                            continue

        # QA assertions:
        # - Bounty existence/response should be tracked for the whole run (a bounty may be claimed before warmup).
        # - Intent checks are gated by warmup to give the AI time to transition.
        if args.qa:
            bounties_enabled = bool(args.bounty) or (str(args.scenario) == "intent_bounty")
            if bounties_enabled:
                qa_bounty_exists = qa_bounty_exists or (int(getattr(bounty_system, "total_spent", 0)) > 0)
                if int(getattr(bounty_system, "total_claimed", 0)) > 0:
                    qa_bounty_has_responder = True
                if bounties:
                    b0 = bounties[0]
                    qa_bounty_responder_attr_present = qa_bounty_responder_attr_present or (
                        hasattr(b0, "responders") or hasattr(b0, "responder_count")
                    )
                    # Track whether any hero ever explicitly targets a bounty. Some profiles may
                    # incidentally claim a bounty while chasing enemies without ever "responding"
                    # to it as a chosen goal; don't fail those runs on responder-count positivity.
                    for h in heroes:
                        if not getattr(h, "is_alive", True):
                            continue
                        tgt = getattr(h, "target", None)
                        if isinstance(tgt, dict) and tgt.get("type") == "bounty":
                            qa_seen_bounty_target = True
                            break
                    # If responder tracking exists, enforce that it becomes >0 at least once.
                    if hasattr(b0, "responders") or hasattr(b0, "responder_count"):
                        qa_explicit_responder_seen = True
                        if _bounty_responder_count(b0, heroes) > 0:
                            qa_explicit_responder_positive = True
                            qa_bounty_has_responder = True
                    else:
                        # Pre-responder-tracking fallback: infer from hero target/assignment.
                        if _bounty_responder_count(b0, heroes) > 0:
                            qa_bounty_has_responder = True

            if t >= int(args.qa_warmup_ticks):
                for h in heroes:
                    if not getattr(h, "is_alive", True):
                        continue
                    if hasattr(h, "intent"):
                        qa_intent_attr_present = True
                    if _hero_intent_label(h):
                        qa_any_intent_seen = True

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
            bstate = bounties_summary(bounty_system)
            print(f"[t={t:04d}] avg_pairwise_dist={apd:.1f}  alive={len([h for h in heroes if h.is_alive])}  {pot_state}  {bstate}  {castle_state}  new_building[{nb_state}]")
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
    # Restore default time behavior for any subsequent runs in the same Python process.
    set_sim_now_ms(None)

    if args.qa:
        failed = False
        # If the run is configured with bounties, require existence + at least one responder.
        bounties_enabled = bool(args.bounty) or (str(args.scenario) == "intent_bounty")
        if bounties_enabled:
            if not qa_bounty_exists:
                print("[qa] FAIL: expected at least one bounty to exist (bounties enabled)")
                failed = True
            if not qa_bounty_has_responder:
                print("[qa] FAIL: expected at least one bounty responder after warmup")
                failed = True
            if qa_explicit_responder_seen and qa_seen_bounty_target and not qa_explicit_responder_positive:
                print("[qa] FAIL: expected explicit bounty responder count to become > 0 (bounty targeting observed)")
                failed = True

        # Only enforce 'intent' non-empty if intent field is present (future-proof integration).
        if qa_intent_attr_present and not qa_any_intent_seen:
            print("[qa] FAIL: hero.intent exists but no non-empty intent observed after warmup")
            failed = True

        # WK2 scenario assertions (contract-aware; avoid flakiness before contracts exist).
        if str(args.scenario) == "hero_stuck_repro" and _any_stuck_fields:
            if int(scenario_counters.get("stuck_events", 0)) <= 0:
                print("[qa] FAIL: hero_stuck_repro expected >=1 stuck detection event (stuck_active)")
                failed = True
            if int(scenario_counters.get("unstuck_attempts", 0)) <= 0:
                print("[qa] FAIL: hero_stuck_repro expected >=1 recovery attempt (unstuck_attempts delta)")
                failed = True

        if str(args.scenario) == "inside_combat_repro" and _any_can_attack_field:
            if int(scenario_counters.get("inside_attack_blocks", 0)) <= 0:
                print("[qa] FAIL: inside_combat_repro expected >=1 inside_attack_blocks when can_attack field exists")
                failed = True

        if not failed:
            # Print a small summary so CI logs show what was checked vs skipped.
            print(
                "[qa] PASS:"
                f" bounty_exists={qa_bounty_exists if bounties_enabled else 'n/a'}"
                f" bounty_has_responder={qa_bounty_has_responder if bounties_enabled else 'n/a'}"
                f" bounty_responder_attr_present={qa_bounty_responder_attr_present if bounties_enabled else 'n/a'}"
                f" bounty_responder_explicit={qa_explicit_responder_positive if qa_explicit_responder_seen else 'n/a'}"
                f" intent_attr_present={qa_intent_attr_present}"
            )

        # Always print scenario counters for CI triage.
        try:
            print(
                "[scenario] counters:"
                f" scenario={args.scenario}"
                f" stuck_events={int(scenario_counters.get('stuck_events', 0))}"
                f" unstuck_attempts={int(scenario_counters.get('unstuck_attempts', 0))}"
                f" inside_attack_blocks={int(scenario_counters.get('inside_attack_blocks', 0))}"
                f" max_stuck_ms={int(scenario_counters.get('max_stuck_ms', 0))}"
            )
        except Exception:
            pass
        return 1 if failed else 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


