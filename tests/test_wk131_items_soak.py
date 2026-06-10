"""WK131 — Items & Inventory deterministic headless soak (Agent 11, QA).

End-to-end proof that the WK131 loot loop works inside a REAL engine run (not
a sanitized harness — enemies enabled, heroes earn gold, shops present):

  enemy killed -> seeded LootSystem.roll_enemy_drop -> grant_item ->
  hero.receive_item (auto-equip if better, else backpack) ->
  hero walks to a shop -> do_shopping sells backpack loot first
  (hero.sell_backpack_items -> add_gold w/ tax -> "hero_sold_items" event).

WHAT THIS SOAK DOES (deterministic, headless):
  * ``GameEngine(headless=True)`` with ``DETERMINISTIC_SIM=1``, dummy SDL
    drivers and a fixed ``set_sim_seed``; no-LLM ``BasicAI`` so idle heroes run
    the deterministic fallback pipeline (explore / hunt / go_shopping). Mirrors
    tests/test_wk124_ranger_idle_soak.py's engine setup.
  * Spawns 4 warriors + 2 rangers homed at the starting warrior/ranger guilds.
    Enemy + lair spawning is left FULLY ENABLED (the WK127 lesson: sanitized
    no-enemy/zero-gold harnesses mask real bugs) and the default world already
    contains a marketplace, lairs and generated POIs (loot caches included).
  * Runs 10 sim-minutes at SIM_TICK_HZ, recording telemetry via test-only
    instance wrappers (call-through, zero extra RNG draws, no production
    edits): every enemy-kill loot roll, every grant outcome
    (equipped/stored/dropped), every ``hero_sold_items`` event, and a per-tick
    backpack-capacity check across ALL heroes.

SUBPROCESS ISOLATION (load-bearing — measured 2026-06-09): each scenario run
executes in a FRESH python subprocess (this file doubles as the runner via the
``__main__`` block). In-process back-to-back engine runs are NOT reproducible:
module-level singletons survive across ``GameEngine`` constructions (e.g. the
``game/systems/navigation.py`` global ``_pathfinding_budget`` pending replan
queue and blocked-tile caches), so a second same-seed run in the same process
diverges after ~2-4 sim-minutes (verified: in-process A/B/C runs all differ,
while two fresh-process runs are byte-identical, finals sha1 a77f0fa915f2 at
4 sim-min). Subprocesses make the determinism assertion test the
production-relevant property (same seed + fresh process -> same outcome) and
shield the soak from global-state pollution by earlier tests in a full-suite
run. The cross-run residue itself is filed in the QA report (Agent 03/04
follow-up: a "new game" in a live session reuses those singletons too).

ASSERTIONS (WK131 acceptance, per PM kickoff):
  (a) >= 1 enemy-kill drop actually landed (outcome equipped/stored). With
      seed 20260609 the 10-min run yields ~770 kill rolls and ~50 drops, so
      the 7% common-drop chance fires many times — wide margin.
  (b) >= 1 hero sold backpack loot at a shop (``hero_sold_items`` with items
      and gold > 0; seed 20260609 yields 5 sale events).
  (c) determinism: run twice with the same seed -> identical per-hero
      (gold, taxed_gold, weapon, armor, accessory, backpack ids, potions)
      tuples AND identical drop/sale/kill event sequences. Run B is 5
      sim-minutes and is compared against run A's 5-minute CHECKPOINT
      fingerprint (same tick count -> must be byte-identical), which keeps
      module runtime < 120s while still proving determinism over a window
      far past where contamination-induced divergence appeared (~min 2-4).
  (d) no hero's backpack ever exceeds ``backpack_capacity`` on any tick
      (checked in both runs).

POI half of (a): whether a hero physically reaches a loot POI inside the soak
window is route-dependent, so per the kickoff's explicit fallback this module
covers the POI path with a DIRECT seeded determinism test on
``POIInteractionSystem``/``LootSystem.roll_poi_drop`` (same seed -> same item
sequence; different seed -> differs; rolled items land via receive_item).

RUNTIME: ~90s on the dev box (10-min run ~55s + 5-min run ~30s, in parallel-
free sequence) — under the 120s budget.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

# Repo root importable both under pytest and as a __main__ subprocess runner.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Headless-friendly drivers + deterministic sim BEFORE engine/config import
# (mirrors tests/test_wk67_ai_boundary.py / tests/test_wk124_ranger_idle_soak.py).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("DETERMINISTIC_SIM", "1")

import pygame

from config import SIM_TICK_HZ
from game.engine import GameEngine
from game.entities.hero import Hero


# --- soak parameters ---------------------------------------------------------
_SOAK_SEED = 20260609
_SIM_MINUTES = 10           # run A (assertions a/b/d)
_CHECKPOINT_MINUTES = 5     # run A checkpoint == run B length (assertion c)
_HERO_SPECS = (  # (class, name) — mixed party: warriors hunt, rangers roam far
    ("warrior", "SoakWarrior0"),
    ("warrior", "SoakWarrior1"),
    ("warrior", "SoakWarrior2"),
    ("warrior", "SoakWarrior3"),
    ("ranger", "SoakRanger0"),
    ("ranger", "SoakRanger1"),
)
_JSON_MARKER = "WK131_SOAK_JSON "

# Module-level cache: each subprocess soak is expensive; share across tests.
_RUNS: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Scenario (executed inside the subprocess runner)
# ---------------------------------------------------------------------------

def _build_soak_engine(seed: int) -> GameEngine:
    """Deterministic headless engine + mixed hero party. Default world state is
    kept INTACT (enemies, lairs, POIs, marketplace) — only heroes are added."""
    from ai.basic_ai import BasicAI
    from game.sim.determinism import set_sim_seed

    set_sim_seed(seed)
    engine = GameEngine(headless=True)
    engine.ai_controller = BasicAI(llm_brain=None)

    castle = next(
        b for b in engine.buildings if getattr(b, "building_type", None) == "castle"
    )
    guilds = {
        "warrior": next((b for b in engine.buildings
                         if getattr(b, "building_type", None) == "warrior_guild"), None),
        "ranger": next((b for b in engine.buildings
                        if getattr(b, "building_type", None) == "ranger_guild"), None),
    }
    cx, cy = float(castle.center_x), float(castle.center_y)
    for i, (hero_class, name) in enumerate(_HERO_SPECS):
        h = Hero(
            cx + (i % 3) * 14 - 21,
            cy + (i // 3) * 14 - 7,
            hero_class=hero_class,
            hero_id=f"wk131_soak_{i}",
            name=name,
        )
        h.home_building = guilds.get(hero_class) or castle
        h.gold = 0  # all gold must come from kills/loot — no sanitized head start
        if hasattr(h, "set_event_bus"):
            h.set_event_bus(engine.event_bus)
        engine.heroes.append(h)
    return engine


def _hero_finals(engine: GameEngine) -> list:
    """JSON-safe per-hero end-state fingerprint (the (c) determinism tuple)."""
    finals = []
    for h in sorted(engine.heroes, key=lambda x: str(getattr(x, "hero_id", ""))):
        weapon = h.weapon if isinstance(getattr(h, "weapon", None), dict) else None
        armor = h.armor if isinstance(getattr(h, "armor", None), dict) else None
        acc = getattr(h, "accessory", None)
        acc = acc if isinstance(acc, dict) else None
        finals.append([
            str(getattr(h, "hero_id", "")),
            str(getattr(h, "name", "")),
            int(getattr(h, "gold", 0)),
            int(getattr(h, "taxed_gold", 0) or 0),
            (weapon or {}).get("name", ""),
            (armor or {}).get("name", ""),
            (acc or {}).get("name", ""),
            [str(getattr(i, "item_id", i)) for i in (getattr(h, "backpack", None) or ())],
            int(getattr(h, "potions", 0)),
        ])
    return finals


def _run_soak(seed: int, minutes: int, checkpoint_minutes: int | None = None) -> dict:
    """Run the scenario once in THIS process; return JSON-safe telemetry.

    Meant to be called inside a fresh subprocess (see module docstring); the
    pytest-side tests never call it directly in the test process.
    """
    pygame.init()
    try:
        engine = _build_soak_engine(seed)

        telemetry: dict = {
            "enemy_rolls": 0,           # every kill-loot roll (incl. no-drop)
            "enemy_drops": [],          # [[item_id, hero_name, outcome], ...]
            "drops_landed": 0,          # equipped|stored outcomes
            "sold_events": [],          # [[hero_name, [items...], gold, shop], ...]
            "cap_violations": [],       # [[tick, hero_name, len, cap], ...]
            "checkpoint": None,
        }

        # --- test-only instance wrappers (call-through, zero extra RNG) ------
        loot = engine.sim.loot_system
        orig_roll = loot.roll_enemy_drop
        orig_grant = loot.grant_item

        def counting_roll(enemy_type):
            item = orig_roll(enemy_type)
            telemetry["enemy_rolls"] += 1
            return item

        def recording_grant(hero, item):
            outcome = orig_grant(hero, item)
            telemetry["enemy_drops"].append(
                [item.item_id, str(getattr(hero, "name", "?")), str(outcome)]
            )
            if outcome in ("equipped", "stored"):
                telemetry["drops_landed"] += 1
            return outcome

        loot.roll_enemy_drop = counting_roll   # instance attr shadows method
        loot.grant_item = recording_grant      # shadows the staticmethod

        def on_sold(event: dict) -> None:
            telemetry["sold_events"].append([
                str(event.get("hero_name", "")),
                [str(x) for x in (event.get("items") or ())],
                int(event.get("gold", 0)),
                str(event.get("shop_type", "")),
            ])

        engine.event_bus.subscribe("hero_sold_items", on_sold)

        # --- tick loop --------------------------------------------------------
        dt = 1.0 / float(SIM_TICK_HZ)
        total_ticks = int(SIM_TICK_HZ * 60 * minutes)
        ckpt_tick = (
            int(SIM_TICK_HZ * 60 * checkpoint_minutes) if checkpoint_minutes else None
        )
        for t in range(total_ticks):
            engine.update(dt)
            for h in engine.heroes:  # (d): cap can never be exceeded, any tick
                cap = int(getattr(h, "backpack_capacity", 0) or 0)
                n = len(getattr(h, "backpack", ()) or ())
                if n > cap:
                    telemetry["cap_violations"].append([t, str(h.name), n, cap])
            if ckpt_tick is not None and (t + 1) == ckpt_tick:
                telemetry["checkpoint"] = {
                    "finals": _hero_finals(engine),
                    "enemy_rolls": telemetry["enemy_rolls"],
                    "enemy_drops": [list(x) for x in telemetry["enemy_drops"]],
                    "sold_events": [
                        [h_, list(i_), g_, s_] for (h_, i_, g_, s_) in telemetry["sold_events"]
                    ],
                }

        telemetry["finals"] = _hero_finals(engine)
        return telemetry
    finally:
        try:
            pygame.quit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Subprocess plumbing (fresh interpreter per run — see module docstring)
# ---------------------------------------------------------------------------

def _spawn_soak(minutes: int, checkpoint_minutes: int | None) -> dict:
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["DETERMINISTIC_SIM"] = "1"
    cmd = [
        sys.executable, os.path.abspath(__file__),
        str(_SOAK_SEED), str(minutes), str(checkpoint_minutes or 0),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=420, cwd=_REPO_ROOT, env=env,
    )
    assert proc.returncode == 0, (
        f"soak subprocess failed (rc={proc.returncode}):\n"
        f"--- stdout tail ---\n{proc.stdout[-2000:]}\n"
        f"--- stderr tail ---\n{proc.stderr[-2000:]}"
    )
    lines = [l for l in proc.stdout.splitlines() if l.startswith(_JSON_MARKER)]
    assert lines, f"no telemetry marker in soak subprocess output:\n{proc.stdout[-2000:]}"
    return json.loads(lines[-1][len(_JSON_MARKER):])


def _soak(run_key: str) -> dict:
    if run_key not in _RUNS:
        if run_key == "A":
            _RUNS[run_key] = _spawn_soak(_SIM_MINUTES, _CHECKPOINT_MINUTES)
        else:  # "B": determinism re-run, compared against run A's checkpoint
            _RUNS[run_key] = _spawn_soak(_CHECKPOINT_MINUTES, None)
    return _RUNS[run_key]


# ---------------------------------------------------------------------------
# (a) enemy-kill loot lands in inventory (equip or backpack)
# ---------------------------------------------------------------------------

def test_soak_enemy_kill_loot_lands_in_hero_inventory():
    run = _soak("A")
    print(
        f"WK131_SOAK seed={_SOAK_SEED} enemy_rolls={run['enemy_rolls']} "
        f"drops_landed={run['drops_landed']} sold={run['sold_events']}"
    )
    assert run["enemy_rolls"] >= 20, (
        f"only {run['enemy_rolls']} enemy-kill loot rolls in {_SIM_MINUTES} "
        "sim-min — heroes are not killing enemies; the soak scenario regressed"
    )
    assert run["drops_landed"] >= 1, (
        f"no enemy-kill drop was equipped/stored over {run['enemy_rolls']} kills "
        f"(drops seen: {run['enemy_drops']}) — loot delivery is broken"
    )


# ---------------------------------------------------------------------------
# (b) heroes sell backpack loot at shops
# ---------------------------------------------------------------------------

def test_soak_hero_sells_backpack_loot_at_shop():
    run = _soak("A")
    sold = run["sold_events"]
    assert sold, (
        "no hero_sold_items event in the whole soak — heroes never sold "
        f"backpack loot at a shop (drops: {run['enemy_drops']})"
    )
    assert any(gold > 0 and items for (_h, items, gold, _s) in sold), (
        f"hero_sold_items fired but with no items/gold: {sold}"
    )


# ---------------------------------------------------------------------------
# (d) backpack never exceeds capacity (checked every tick, both runs)
# ---------------------------------------------------------------------------

def test_soak_backpack_never_exceeds_capacity():
    a = _soak("A")
    b = _soak("B")
    assert a["cap_violations"] == [], (
        f"backpack exceeded capacity during run A: {a['cap_violations'][:5]}"
    )
    assert b["cap_violations"] == [], (
        f"backpack exceeded capacity during run B: {b['cap_violations'][:5]}"
    )


# ---------------------------------------------------------------------------
# (c) determinism: same seed, fresh process -> identical state + event streams
# ---------------------------------------------------------------------------

def test_soak_same_seed_is_deterministic():
    ckpt = _soak("A")["checkpoint"]
    assert ckpt, "run A recorded no checkpoint — soak runner misconfigured"
    b = _soak("B")
    assert b["finals"] == ckpt["finals"], (
        "same-seed soak diverged in hero state at the "
        f"{_CHECKPOINT_MINUTES}-sim-min mark:\n"
        f"  run A ckpt: {ckpt['finals']}\n  run B:      {b['finals']}"
    )
    assert b["enemy_drops"] == ckpt["enemy_drops"], (
        "drop sequence diverged across same-seed runs"
    )
    assert b["sold_events"] == ckpt["sold_events"], (
        "sale sequence diverged across same-seed runs"
    )
    assert b["enemy_rolls"] == ckpt["enemy_rolls"], (
        "kill count diverged across same-seed runs"
    )


# ---------------------------------------------------------------------------
# POI half of (a): direct seeded POI loot-roll determinism (substitute test —
# whether a hero physically reaches a loot POI in the 10-min window is
# route-dependent, so the engine soak does not assert it; this does).
# ---------------------------------------------------------------------------

def _poi_roll_sequence(seed: int, n: int = 120) -> tuple:
    from game.sim.determinism import set_sim_seed
    from game.systems.poi_interaction import POIInteractionSystem

    set_sim_seed(seed)
    system = POIInteractionSystem()  # owns its own get_rng("loot") LootSystem
    out = []
    for i in range(n):
        item = system._loot_system.roll_poi_drop(tier=(i % 4) + 1)
        out.append(item.item_id if item is not None else "-")
    return tuple(out)


def test_poi_loot_roll_seeded_determinism_and_delivery():
    from game.sim.determinism import set_sim_seed

    try:
        a1 = _poi_roll_sequence(_SOAK_SEED)
        a2 = _poi_roll_sequence(_SOAK_SEED)
        b = _poi_roll_sequence(_SOAK_SEED + 1)
        assert a1 == a2, "same-seed POI loot rolls must be identical"
        assert a1 != b, "different seeds should produce different POI roll sequences"
        hits = [x for x in a1 if x != "-"]
        # 120 rolls at 35%: statistically certain band, catches a dead roller.
        assert 20 <= len(hits) <= 70, f"POI drop rate implausible: {len(hits)}/120"

        # Rolled POI items land via the same receive_item delivery path.
        from game.content.items import get_item

        hero = Hero(0.0, 0.0, name="PoiLooter")
        outcome = hero.receive_item(get_item(hits[0]))
        assert outcome in ("equipped", "stored")
        landed = (hero.backpack and hero.backpack[0].item_id == hits[0]) or (
            hits[0] in {
                (hero.weapon or {}).get("id"), (hero.armor or {}).get("id"),
                (getattr(hero, "accessory", None) or {}).get("id"),
            }
        ) or (hero.potions > 0)
        assert landed, f"rolled POI item {hits[0]} did not land anywhere on the hero"
    finally:
        set_sim_seed(1)


# ---------------------------------------------------------------------------
# Subprocess runner entrypoint (fresh-interpreter soak; prints JSON telemetry)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _seed = int(sys.argv[1]) if len(sys.argv) > 1 else _SOAK_SEED
    _minutes = int(sys.argv[2]) if len(sys.argv) > 2 else _SIM_MINUTES
    _ckpt = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    _result = _run_soak(_seed, _minutes, _ckpt or None)
    print(_JSON_MARKER + json.dumps(_result))
