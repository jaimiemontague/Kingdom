"""
Differential Frame Profiler: Measures per-subsystem frame cost before and
after hero hires to isolate the FPS-drop root cause.

Runs HEADLESS (no GPU). Exercises the same simulation code paths as the
Ursina app loop: entity separation, fog, AI, hero/peasant updates, combat.

Usage:
  python tools/ursina_frame_profiler.py
  python tools/ursina_frame_profiler.py --max-hires 8
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
import types
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pygame  # noqa: E402
pygame.init()
pygame.display.init()
pygame.display.set_mode((1, 1))

from config import TILE_SIZE  # noqa: E402
from game.engine import GameEngine  # noqa: E402
from game.entities.hero import Hero  # noqa: E402
from game.entities import WarriorGuild  # noqa: E402
from ai.basic_ai import BasicAI  # noqa: E402


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------
class Bucket:
    __slots__ = ("name", "total", "n")
    def __init__(self, name: str):
        self.name = name; self.total = 0.0; self.n = 0
    def add(self, s: float):
        self.total += s; self.n += 1
    @property
    def avg_ms(self) -> float:
        return (self.total / max(1, self.n)) * 1000.0
    def reset(self):
        self.total = 0.0; self.n = 0

class Profile:
    def __init__(self):
        self.total = Bucket("total_frame")
        self.entity_sep = Bucket("entity_sep")
        self.fog = Bucket("fog_of_war")
        self.ai = Bucket("ai_ctrl")
        self.hero_upd = Bucket("hero_update")
        self.enemy_upd = Bucket("enemy_upd")
        self.combat = Bucket("combat")
        self.world_sys = Bucket("world_systems")
        self.peasant_upd = Bucket("peasant_upd")
    @property
    def buckets(self) -> list[Bucket]:
        return [self.total, self.entity_sep, self.fog, self.ai,
                self.hero_upd, self.enemy_upd, self.combat,
                self.world_sys, self.peasant_upd]
    def reset(self):
        for b in self.buckets: b.reset()


def _patch(engine: GameEngine, p: Profile):
    """Monkey-patch engine methods for timing."""

    def _wrap(attr_name: str, bucket: Bucket):
        orig = getattr(type(engine), attr_name)
        def wrapper(self, *a, **kw):
            t0 = time.perf_counter()
            r = orig(self, *a, **kw)
            bucket.add(time.perf_counter() - t0)
            return r
        setattr(engine, attr_name, types.MethodType(wrapper, engine))

    _wrap("_apply_entity_separation", p.entity_sep)
    _wrap("_update_fog_of_war", p.fog)
    _wrap("_update_enemies", p.enemy_upd)
    _wrap("_process_combat", p.combat)
    _wrap("_update_world_systems", p.world_sys)
    _wrap("_update_peasants", p.peasant_upd)

    # Split AI + hero update
    orig_aih = type(engine)._update_ai_and_heroes
    def split_aih(self, dt, gs):
        t0 = time.perf_counter()
        if self.ai_controller:
            self.ai_controller.update(dt, self.heroes, gs)
        p.ai.add(time.perf_counter() - t0)
        for h in self.heroes:
            if getattr(h, "llm_move_request", None) is not None:
                h.set_target_position(*h.llm_move_request)
                h.llm_move_request = None
        t1 = time.perf_counter()
        for h in self.heroes:
            h.update(dt, gs)
        p.hero_upd.add(time.perf_counter() - t1)
    engine._update_ai_and_heroes = types.MethodType(split_aih, engine)


def hire(engine: GameEngine) -> Hero | None:
    guild = None
    for b in engine.buildings:
        if getattr(b, "building_type", "") == "warrior_guild":
            guild = b
            break
    if guild is None:
        castle = next((b for b in engine.buildings
                       if getattr(b, "building_type", "") == "castle"), None)
        if not castle:
            return None
        guild = WarriorGuild(castle.grid_x - 4, castle.grid_y + 2)
        guild.is_constructed = True
        guild.construction_started = True
        engine.buildings.append(guild)
        if hasattr(guild, "set_event_bus"):
            guild.set_event_bus(engine.event_bus)
    hero = Hero(guild.center_x + TILE_SIZE, guild.center_y, hero_class="warrior")
    hero.home_building = guild
    engine.heroes.append(hero)
    return hero


def run(baseline: int = 300, per_hire: int = 180, max_hires: int = 6, dt: float = 1/60):
    print("=" * 72)
    print("  Agent 10 — Differential Frame Profiler (Hero Hire)")
    print("=" * 72)

    engine = GameEngine(headless=True)
    engine.ai_controller = BasicAI(llm_brain=None)
    # No enemies — isolate hero-side costs. Enemies add pathfinding noise.
    engine.enemies.clear()

    p = Profile()
    _patch(engine, p)

    results = []

    def phase(label: str, ticks: int):
        p.reset()
        for _ in range(ticks):
            t0 = time.perf_counter()
            engine.update(dt)
            p.total.add(time.perf_counter() - t0)
        nh = len(engine.heroes)
        ne = len([e for e in engine.enemies if getattr(e, "is_alive", True)])
        na = nh + ne + len(engine.peasants) + len(engine.guards) + (1 if engine.tax_collector else 0)
        row = {"label": label, "H": nh, "E": ne, "N": na}
        for b in p.buckets:
            row[b.name] = round(b.avg_ms, 4)
        results.append(row)
        # Print progress
        sep_ms = row["entity_sep"]
        tot_ms = row["total_frame"]
        print(f"  {label:<16} heroes={nh:<3} alive={na:<4} total={tot_ms:.3f} ms  "
              f"entity_sep={sep_ms:.3f} ms  fog={row['fog_of_war']:.3f} ms  "
              f"ai={row['ai_ctrl']:.3f} ms")

    print(f"\n[Baseline] 0 heroes, 0 enemies, {baseline} ticks")
    phase("baseline", baseline)

    for i in range(1, max_hires + 1):
        h = hire(engine)
        if not h:
            break
        print(f"\n[Hire #{i}] {h.name}, total={len(engine.heroes)} heroes, {per_hire} ticks")
        phase(f"hire_{i}", per_hire)

    # Summary table
    bnames = [b.name for b in p.buckets]
    print("\n" + "=" * 72)
    print("  SUMMARY TABLE (ms/tick)")
    print("=" * 72)
    hdr = f"{'Phase':<16} {'H':>2} {'N':>3}"
    for bn in bnames:
        hdr += f" {bn[:14]:>14}"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        row = f"{r['label']:<16} {r['H']:>2} {r['N']:>3}"
        for bn in bnames:
            row += f" {r[bn]:>14.4f}"
        print(row)

    # Delta
    if len(results) >= 2:
        base = results[0]
        print("\n" + "=" * 72)
        print("  DELTA vs BASELINE")
        print("=" * 72)
        for r in results[1:]:
            print(f"\n  {r['label']}  (H={r['H']}, N={r['N']}):")
            for bn in bnames:
                bv, cv = base[bn], r[bn]
                d = cv - bv
                pct = (d / max(bv, 0.0001)) * 100
                flag = " <<<" if pct > 25 else ""
                # ASCII-only output so Windows cp1252 terminals don't crash.
                print(f"    {bn:<16} {bv:>8.3f} -> {cv:>8.3f}  d={d:>+7.3f}  ({pct:>+6.1f}%){flag}")

    # O(N²) check
    if len(results) >= 3:
        b0 = results[0]; bL = results[-1]
        n0 = max(1, b0["N"]); nL = max(1, bL["N"])
        s0 = max(0.0001, b0["entity_sep"]); sL = bL["entity_sep"]
        rN = nL / n0; rC = sL / s0
        print(f"\n  Entity sep scaling: N {n0}->{nL} ({rN:.1f}x), cost {s0:.4f}->{sL:.4f} ({rC:.1f}x)")
        print(f"  O(N²) expects {rN**2:.1f}x.  ", end="")
        if rC > rN ** 1.5:
            print("CONFIRMED super-linear scaling <<<")
        else:
            print("Linear or sub-quadratic.")

    print("\n[Done]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-ticks", type=int, default=300)
    ap.add_argument("--per-hire-ticks", type=int, default=180)
    ap.add_argument("--max-hires", type=int, default=6)
    run(ap.parse_args().baseline_ticks, ap.parse_args().per_hire_ticks, ap.parse_args().max_hires)
