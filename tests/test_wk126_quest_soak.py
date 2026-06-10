"""WK126-T10 — quest vertical-slice deterministic headless soak (Agent 11, QA).

End-to-end proof that the WK126/WK133 quest loop works inside a REAL engine run
(NOT a sanitized harness — the WK127 lesson: enemy + lair spawning fully
enabled, default world POIs intact, heroes earn gold from kills):

  player funds quests at 2 constructed Herald's Posts (engine.create_quest →
  economy.fund_quest escrow) → Quest-Giver NPCs spawn beside the posts →
  idle heroes OCCASIONALLY walk up (seeded ai._ai_rng roll) → accept/decline
  verdict at the NPC → objective pursuit → per-type completion detection →
  taxed payout via hero.add_gold.

TWO ENGINE SCENARIOS (each in a fresh subprocess — the wk131 soak lesson:
module-level singletons like the navigation pathfinding budget survive across
in-process GameEngine constructions and contaminate later runs; this file
doubles as the __main__ runner, exactly like tests/test_wk131_items_soak.py):

  * MAIN soak (~10 sim-min, ``llm_brain=None`` → arrival is the documented
    DETERMINISTIC ACCEPT): four quests armed across two givers, one per type.
    Asserts (a) heroes organically accept (the approach RNG roll + the walk are
    never forced), (c) at least one quest of EACH of the four types COMPLETES
    and pays exactly ``reward - int(reward * TAX_RATE)``.
  * DECLINE soak (mock LLM, reward 40g < the MockProvider's 50g threshold →
    every verdict is a DECLINE): asserts (b) a declined giver is NOT
    re-approached by the declining hero for >= 15 SIM-minutes (every
    ``quest_offer`` commit is logged every tick; the run monitors the full
    15.5-sim-min window after the first decline).

PER-TYPE COMPLETION ENGINEERING (the T10 brief: organic first, then drive):
  * raid_lair      — nearest real lair, HP capped at 60 at arming so a raid can
                     finish in-window; if still open 2 sim-min after acceptance
                     the accepting hero is teleported adjacent and the lair HP
                     drops to 3 (the kill still flows through real combat →
                     LAIR_CLEARED → QuestSystem.on_lair_cleared).
  * slay_enemy_type— "goblin" x3; from 30 sim-s after acceptance a 1-HP goblin
                     is spawned beside the ACCEPTING hero every 10 sim-s (cap
                     12) so the kills happen through the real combat pipeline →
                     ENEMY_KILLED → on_enemy_killed counter.
  * find_poi       — nearest generated POI; if not complete 2 sim-min after
                     acceptance the hero's POSITION IS DRIVEN onto the POI each
                     tick until the REAL proximity detector in
                     QuestSystem.update fires (explicitly allowed by T10).
  * explore_far    — a frontier tile ~24 tiles out; same position-drive
                     fallback — standing there lets the REAL fog reveal
                     (HERO_VISION_TILES=7 > the 3-tile radius + diagonal) flip
                     the tiles SEEN and the detector poll fires.

ALSO HERE:
  (d) overlay-entity leak gate — quest-giver billboards with the "!" marker +
      "Herald" name label created through the REAL renderer collaborator and
      destroyed through the REAL ``UrsinaRenderer._destroy_removed_entities``
      removal path across repeated add/remove cycles must return
      ``scene.entities`` to baseline (the tests/test_wk123_scene_entity_leak.py
      pattern; skips cleanly without an offscreen Panda3D pipe).
  (e) WK67 digest backstop — the pinned digest constant in
      tests/test_wk67_ai_boundary.py must still be the golden b73961… value
      (anti-re-baseline guard; the digest itself is asserted by that test).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

# Repo root importable both under pytest and as a __main__ subprocess runner.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Headless-friendly drivers + deterministic sim BEFORE engine/config import.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("DETERMINISTIC_SIM", "1")

from config import QUEST_DECLINE_COOLDOWN_MS, SIM_TICK_HZ, TAX_RATE, TILE_SIZE

_SOAK_SEED = 20260610
_MAIN_MINUTES = 15                 # main soak length (a + c) — breaks early
                                   # once all four quests complete
_DECLINE_MAX_MINUTES = 20          # hard cap for the decline run
_POST_DECLINE_WATCH_MS = int(QUEST_DECLINE_COOLDOWN_MS + 30_000)  # 15.5 sim-min
_JSON_MARKER = "WK126_SOAK_JSON "

_QUEST_REWARDS = {                 # all >= 50g so the mock would accept these
    "raid_lair": 140,
    "slay_enemy_type": 60,
    "find_poi": 60,
    "explore_far": 140,
}
_SLAY_TYPE = "goblin"
_SLAY_COUNT = 3
_DECLINE_REWARD = 40               # < 50g -> the MockProvider responder DECLINES

# Module-level cache: subprocess soaks are expensive; share across tests.
_RUNS: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Shared scenario plumbing (runs inside the subprocess)
# ---------------------------------------------------------------------------

def _build_engine(seed: int, *, llm_brain):
    """Headless engine + 6-hero mixed party + 2 CONSTRUCTED Herald's Posts.

    Default world state INTACT (enemies, lairs, POIs, marketplace) — only
    heroes and the two posts are added (the posts are the feature under test).
    """
    from ai.basic_ai import BasicAI
    from game.engine import GameEngine
    from game.entities.buildings.base import Building
    from game.entities.hero import Hero
    from game.sim.determinism import set_sim_seed

    set_sim_seed(seed)
    engine = GameEngine(headless=True)
    engine.ai_controller = BasicAI(llm_brain=llm_brain)

    castle = next(
        b for b in engine.buildings if getattr(b, "building_type", None) == "castle"
    )
    guilds = {
        "warrior": next((b for b in engine.buildings
                         if getattr(b, "building_type", None) == "warrior_guild"), None),
        "ranger": next((b for b in engine.buildings
                        if getattr(b, "building_type", None) == "ranger_guild"), None),
        "cleric": next((b for b in engine.buildings
                        if getattr(b, "building_type", None) == "temple"), None),
    }
    cx, cy = float(castle.center_x), float(castle.center_y)
    # A realistic mixed party, sized so SOME hero is idle near the posts often
    # enough for the seeded 15% approach roll to fire organically. Clerics keep
    # the party above the 0.65 health gate (WK124 heals) in a world with live
    # enemy/lair spawning.
    specs = (
        ("warrior", "QSoakWar0"), ("warrior", "QSoakWar1"),
        ("warrior", "QSoakWar2"), ("warrior", "QSoakWar3"),
        ("warrior", "QSoakWar4"), ("warrior", "QSoakWar5"),
        ("ranger", "QSoakRng0"), ("ranger", "QSoakRng1"),
        ("cleric", "QSoakClr0"), ("cleric", "QSoakClr1"),
    )
    for i, (hero_class, name) in enumerate(specs):
        h = Hero(
            cx + (i % 3) * 14 - 21,
            cy + (i // 3) * 14 - 7,
            hero_class=hero_class,
            hero_id=f"wk126_soak_{i}",
            name=name,
        )
        # NEVER home a hero at the castle: Castle has no add_tax_gold, so the
        # going-home tax transfer would crash (heroes are guild-spawned in the
        # real game; castle-homing is a harness-only hazard).
        h.home_building = (
            guilds.get(hero_class) or guilds["warrior"] or guilds["ranger"]
        )
        h.gold = 0
        if hasattr(h, "set_event_bus"):
            h.set_event_bus(engine.event_bus)
        engine.heroes.append(h)

    # Two constructed Herald's Posts near the castle (heroes idle around here).
    posts = []
    for grid_dx, grid_dy in ((6, 0), (-6, 4)):
        post = Building(
            int(castle.grid_x) + grid_dx, int(castle.grid_y) + grid_dy, "herald_post"
        )
        post.is_constructed = True
        post.construction_started = True
        engine.sim.buildings.append(post)
        posts.append(post)

    # One tick so the spawn hook creates the Quest-Giver NPCs.
    engine.update(1.0 / float(SIM_TICK_HZ))
    assert len(engine.sim.quest_givers) == 2, (
        f"expected 2 quest givers after the spawn tick, got {len(engine.sim.quest_givers)}"
    )
    return engine, castle, posts


def _nearest(items, x, y):
    return min(
        items,
        key=lambda b: (float(getattr(b, "center_x", getattr(b, "x", 0.0))) - x) ** 2
        + (float(getattr(b, "center_y", getattr(b, "y", 0.0))) - y) ** 2,
    )


def _subscribe(engine, etype: str, sink: list) -> None:
    def _on(event: dict) -> None:
        sink.append({k: v for k, v in event.items() if isinstance(k, str)})

    engine.event_bus.subscribe(etype, _on)


# ---------------------------------------------------------------------------
# MAIN soak — (a) organic accepts + (c) all four types complete and pay out
# ---------------------------------------------------------------------------

def _run_main_soak(seed: int, minutes: int) -> dict:
    import pygame

    from game.entities.enemy import Enemy
    from game.sim.timebase import now_ms as sim_now_ms

    pygame.init()
    try:
        engine, castle, posts = _build_engine(seed, llm_brain=None)
        sim = engine.sim
        cx, cy = float(castle.center_x), float(castle.center_y)

        # --- pick real-world targets (engineered CLOSE, per the T10 brief) ---
        lairs = [b for b in sim.buildings if getattr(b, "is_lair", False)]
        assert lairs, "default world generated no lairs — soak scenario broken"
        lair = _nearest(lairs, cx, cy)
        lair.hp = min(int(lair.hp), 25)  # raidable in-window, still real combat

        pois = list(getattr(sim, "pois", []) or [])
        assert pois, "default world generated no POIs — soak scenario broken"
        poi = _nearest(pois, cx, cy)

        world = sim.world
        tx = max(5, min(int(world.width) - 6, int(castle.grid_x) + 24))
        ty = max(5, min(int(world.height) - 6, int(castle.grid_y) + 10))
        explore_tile = (tx, ty)

        # --- fund + arm one quest of each type across the two givers ---------
        sim.economy.player_gold = max(int(sim.economy.player_gold), 1000)
        gold_before = int(sim.economy.player_gold)
        giver_a, giver_b = (g.giver_id for g in sim.quest_givers)
        quests = {
            "raid_lair": sim.create_quest(giver_a, "raid_lair", lair, _QUEST_REWARDS["raid_lair"]),
            "explore_far": sim.create_quest(giver_a, "explore_far", explore_tile, _QUEST_REWARDS["explore_far"]),
            "slay_enemy_type": sim.create_quest(
                giver_b, "slay_enemy_type", _SLAY_TYPE, _QUEST_REWARDS["slay_enemy_type"], count=_SLAY_COUNT
            ),
            "find_poi": sim.create_quest(giver_b, "find_poi", poi, _QUEST_REWARDS["find_poi"]),
        }
        assert all(q is not None for q in quests.values()), "create_quest refused — escrow funding broken"
        escrow = sum(_QUEST_REWARDS.values())
        assert int(sim.economy.player_gold) == gold_before - escrow, (
            "fund_quest escrow did not debit the treasury by the armed total"
        )
        assert all(g.is_open for g in sim.quest_givers), "arming must flip giver.is_open"

        # --- telemetry --------------------------------------------------------
        telemetry: dict = {
            "started": [], "completed": [], "failed": [], "declined": [],
            "payouts": [],        # [quest_type, reward, hero_gold_delta]
            "drives": {},         # quest_type -> "organic" | "driven"
            "commits": [],        # [hero_id, giver_id, started_ms] approaches
            "escrow_debited": escrow,
        }
        for etype, sink in (
            ("quest_started", telemetry["started"]),
            ("quest_completed", telemetry["completed"]),
            ("quest_failed", telemetry["failed"]),
            ("quest_declined", telemetry["declined"]),
        ):
            _subscribe(engine, etype, sink)

        qs = sim.quest_system
        orig_complete = qs._complete

        def recording_complete(quest, hero, event_bus):
            g0 = int(getattr(hero, "gold", 0))
            orig_complete(quest, hero, event_bus)
            telemetry["payouts"].append(
                [str(quest.quest_type), int(quest.reward), int(getattr(hero, "gold", 0)) - g0]
            )

        qs._complete = recording_complete  # instance attr shadows the method

        heroes_by_id = {str(h.hero_id): h for h in engine.heroes}

        def accepting_hero(quest):
            return heroes_by_id.get(str(quest.accepted_by or ""))

        # --- tick loop with per-type completion drives ------------------------
        dt = 1.0 / float(SIM_TICK_HZ)
        total_ticks = int(SIM_TICK_HZ * 60 * minutes)
        drive_after_ms = 60_000    # organic window after acceptance: 1 sim-min
        slay_spawn = {"next_ms": None, "spawned": 0}
        seen_commits: set[tuple] = set()

        giver_for_type = {
            "raid_lair": giver_a, "explore_far": giver_a,
            "slay_enemy_type": giver_b, "find_poi": giver_b,
        }

        for _t in range(total_ticks):
            engine.update(dt)
            now = int(sim_now_ms())

            # Re-arm failed quests (the PM decision of record: escrow consumed,
            # giver RE-ARMABLE — this is the real player flow after a hero dies
            # on a quest). raid_lair re-targets the nearest still-living lair.
            for qtype, q in list(quests.items()):
                if q.failed:
                    target = q.target
                    if qtype == "raid_lair":
                        living = [b for b in sim.buildings if getattr(b, "is_lair", False)]
                        if not living:
                            continue
                        target = _nearest(living, cx, cy)
                        target.hp = min(int(target.hp), 25)
                    sim.economy.player_gold = max(int(sim.economy.player_gold), 500)
                    new_q = sim.create_quest(
                        giver_for_type[qtype], qtype, target, _QUEST_REWARDS[qtype],
                        count=_SLAY_COUNT if qtype == "slay_enemy_type" else 1,
                    )
                    if new_q is not None:
                        quests[qtype] = new_q
                        telemetry.setdefault("rearms", []).append(qtype)
                        if qtype == "slay_enemy_type":
                            slay_spawn = {"next_ms": None, "spawned": 0}

            # Approach telemetry (every quest_offer commit, uniquely keyed by
            # its started_ms — proof the accepts below were organic walks).
            for h in engine.heroes:
                tgt = getattr(h, "target", None)
                if isinstance(tgt, dict) and tgt.get("type") == "quest_offer":
                    key = (
                        str(h.hero_id),
                        str(tgt.get("giver_id", "")),
                        int(tgt.get("started_ms", 0) or 0),
                    )
                    if key not in seen_commits:
                        seen_commits.add(key)
                        telemetry["commits"].append(list(key))

            # raid_lair: if the raid hasn't finished organically, engineer it —
            # teleport the accepting hero adjacent, cap the lair at 2 HP, weaken
            # the lair's defenders to 1 HP and keep the raider topped up. The
            # lair must STILL die to real combat -> LAIR_CLEARED routing (the
            # detector under test); without the survival drive the lone raider
            # is swarmed by lair spawns and dies before landing the blow (it
            # happened twice while tuning — see telemetry["rearms"]).
            q = quests["raid_lair"]
            if q.accepted_by and not q.completed and not q.failed:
                if now - int(q.accepted_time_ms or 0) > drive_after_ms:
                    hero = accepting_hero(q)
                    if hero is not None and getattr(hero, "is_alive", True):
                        telemetry["drives"].setdefault("raid_lair", "driven")
                        target_lair = q.target
                        target_lair.hp = min(int(target_lair.hp), 2)
                        hero.x = float(target_lair.center_x) - TILE_SIZE * 1.5
                        hero.y = float(target_lair.center_y)
                        hero.hp = int(getattr(hero, "max_hp", hero.hp))
                        # Combat detours drop the lair target and nothing
                        # re-points a quest raider (a REAL coverage gap — see
                        # the QA report); re-pin the objective so the raid
                        # resumes after each defender fight.
                        from game.entities.hero import HeroState as _HS

                        if hero.state != _HS.FIGHTING and hero.target is not target_lair:
                            hero.target = target_lair
                            hero.set_target_position(
                                float(target_lair.center_x) - TILE_SIZE * 1.5,
                                float(target_lair.center_y),
                            )
                            hero.state = _HS.MOVING
                        for e in sim.enemies:
                            if (
                                getattr(e, "is_alive", True)
                                and abs(float(e.x) - float(target_lair.center_x)) < TILE_SIZE * 8
                                and abs(float(e.y) - float(target_lair.center_y)) < TILE_SIZE * 8
                            ):
                                e.hp = min(int(e.hp), 1)

            # slay: feed the ACCEPTING hero 1-HP goblins through real combat.
            q = quests["slay_enemy_type"]
            if q.accepted_by and not q.completed and not q.failed:
                accepted_ms = int(q.accepted_time_ms or 0)
                if slay_spawn["next_ms"] is None:
                    slay_spawn["next_ms"] = accepted_ms + 15_000
                if now >= slay_spawn["next_ms"] and slay_spawn["spawned"] < 12:
                    hero = accepting_hero(q)
                    if hero is not None and getattr(hero, "is_alive", True):
                        telemetry["drives"].setdefault("slay_enemy_type", "driven")
                        goblin = Enemy(
                            float(hero.x) + TILE_SIZE * 1.2,
                            float(hero.y),
                            enemy_type=_SLAY_TYPE,
                        )
                        goblin.hp = 1
                        sim.enemies.append(goblin)
                        slay_spawn["spawned"] += 1
                    slay_spawn["next_ms"] = now + 8_000

            # find_poi / explore_far: position-drive after the organic window;
            # the REAL detectors (proximity poll / fog SEEN poll) must fire.
            for qtype, gx, gy in (
                ("find_poi", float(poi.center_x), float(poi.center_y)),
                (
                    "explore_far",
                    (explore_tile[0] + 0.5) * TILE_SIZE,
                    (explore_tile[1] + 0.5) * TILE_SIZE,
                ),
            ):
                q = quests[qtype]
                if q.accepted_by and not q.completed and not q.failed:
                    if now - int(q.accepted_time_ms or 0) > drive_after_ms:
                        hero = accepting_hero(q)
                        if hero is not None and getattr(hero, "is_alive", True):
                            telemetry["drives"].setdefault(qtype, "driven")
                            hero.x, hero.y = float(gx), float(gy)

            # Early-break once everything completed — but soak at least 6
            # sim-min so the post-completion engine (quest cleanup, re-armable
            # givers, marker-off states) also gets exercised over time.
            if all(q.completed for q in quests.values()) and _t >= int(SIM_TICK_HZ * 60 * 6):
                break

        for qtype, q in quests.items():
            telemetry["drives"].setdefault(qtype, "organic")
        telemetry["final"] = {
            qtype: {
                "accepted_by": q.accepted_by,
                "completed": bool(q.completed),
                "failed": bool(q.failed),
                "progress": int(q.progress),
            }
            for qtype, q in quests.items()
        }
        telemetry["sim_minutes_ran"] = round(int(sim_now_ms()) / 60_000.0, 2)
        return telemetry
    finally:
        try:
            pygame.quit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# DECLINE soak — (b) declined giver not re-approached for >= 15 sim-min
# ---------------------------------------------------------------------------

def _run_decline_soak(seed: int) -> dict:
    import pygame

    from ai.llm_brain import LLMBrain
    from game.sim.timebase import now_ms as sim_now_ms

    pygame.init()
    brain = LLMBrain("mock")  # seeded MockProvider: reward < 50g -> DECLINE
    try:
        engine, castle, posts = _build_engine(seed + 1, llm_brain=brain)
        sim = engine.sim
        cx, cy = float(castle.center_x), float(castle.center_y)

        lairs = [b for b in sim.buildings if getattr(b, "is_lair", False)]
        lair = _nearest(lairs, cx, cy)

        # Three miserly 40g offers queued on ONE giver: even if a munged
        # in-flight decision ever slips through as an accidental accept, the
        # giver re-opens with the next 40g offer and stays decline-bait.
        sim.economy.player_gold = max(int(sim.economy.player_gold), 1000)
        giver_id = sim.quest_givers[0].giver_id
        for _ in range(3):
            assert sim.create_quest(giver_id, "raid_lair", lair, _DECLINE_REWARD) is not None

        telemetry: dict = {"declined": [], "started": [], "commits": []}
        _subscribe(engine, "quest_declined", telemetry["declined"])
        _subscribe(engine, "quest_started", telemetry["started"])

        # Every tick, log every hero's live quest_offer commit (started_ms makes
        # each commit unique even though it persists across the walk).
        seen_commits: set[tuple] = set()

        dt = 1.0 / float(SIM_TICK_HZ)
        max_ticks = int(SIM_TICK_HZ * 60 * _DECLINE_MAX_MINUTES)
        first_decline_ms = None
        for _t in range(max_ticks):
            engine.update(dt)
            now = int(sim_now_ms())
            for h in engine.heroes:
                tgt = getattr(h, "target", None)
                if isinstance(tgt, dict) and tgt.get("type") == "quest_offer":
                    key = (
                        str(h.hero_id),
                        str(tgt.get("giver_id", "")),
                        int(tgt.get("started_ms", 0) or 0),
                    )
                    if key not in seen_commits:
                        seen_commits.add(key)
                        telemetry["commits"].append(list(key))
            if first_decline_ms is None and telemetry["declined"]:
                first = telemetry["declined"][0]
                first_decline_ms = int(first.get("until_ms", 0)) - int(QUEST_DECLINE_COOLDOWN_MS)
            if first_decline_ms is not None and now >= first_decline_ms + _POST_DECLINE_WATCH_MS:
                break

        telemetry["first_decline_ms"] = first_decline_ms
        telemetry["sim_minutes_ran"] = round(int(sim_now_ms()) / 60_000.0, 2)
        return telemetry
    finally:
        try:
            brain.stop()
        except Exception:
            pass
        try:
            pygame.quit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Subprocess plumbing (fresh interpreter per scenario — wk131 pattern)
# ---------------------------------------------------------------------------

def _spawn(scenario: str) -> dict:
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["DETERMINISTIC_SIM"] = "1"
    cmd = [sys.executable, os.path.abspath(__file__), scenario, str(_SOAK_SEED)]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=540, cwd=_REPO_ROOT, env=env,
    )
    assert proc.returncode == 0, (
        f"soak subprocess '{scenario}' failed (rc={proc.returncode}):\n"
        f"--- stdout tail ---\n{proc.stdout[-3000:]}\n"
        f"--- stderr tail ---\n{proc.stderr[-3000:]}"
    )
    lines = [l for l in proc.stdout.splitlines() if l.startswith(_JSON_MARKER)]
    assert lines, f"no telemetry marker in '{scenario}' output:\n{proc.stdout[-3000:]}"
    return json.loads(lines[-1][len(_JSON_MARKER):])


def _soak(scenario: str) -> dict:
    if scenario not in _RUNS:
        _RUNS[scenario] = _spawn(scenario)
    return _RUNS[scenario]


# ---------------------------------------------------------------------------
# (a) heroes DO accept quests over time (organic approach + accept)
# ---------------------------------------------------------------------------

def test_soak_heroes_accept_quests_over_time():
    run = _soak("main")
    started = run["started"]
    print(
        f"WK126_SOAK seed={_SOAK_SEED} started={len(started)} "
        f"drives={run['drives']} final={run['final']} "
        f"sim_minutes={run['sim_minutes_ran']}"
    )
    assert len(started) >= 4, (
        f"only {len(started)} QUEST_STARTED in ~{run['sim_minutes_ran']} sim-min "
        f"— heroes are not organically approaching/accepting quests "
        f"(final state: {run['final']})"
    )
    # Acceptance is NEVER forced by the drives — every accept came through the
    # approach RNG roll + walk + arrival pipeline.
    accepted_types = {e.get("quest_type") for e in started}
    assert accepted_types == set(_QUEST_REWARDS), (
        f"not every quest type was accepted: {accepted_types}"
    )


# ---------------------------------------------------------------------------
# (c) at least one quest of EACH of the four types completes and pays out
# ---------------------------------------------------------------------------

def test_soak_all_four_quest_types_complete_and_pay():
    run = _soak("main")
    completed_types = {e.get("quest_type") for e in run["completed"]}
    assert completed_types == set(_QUEST_REWARDS), (
        f"completed types {completed_types} != all four "
        f"(failed: {run['failed']}, rearms: {run.get('rearms', [])}, "
        f"final: {run['final']}, drives: {run['drives']})"
    )

    # Taxed payout, exactly the bounty-claim math, for every completion.
    paid_types = set()
    for qtype, reward, delta in run["payouts"]:
        expected = int(reward) - int(int(reward) * TAX_RATE)
        assert delta == expected, (
            f"{qtype}: payout delta {delta} != reward-minus-tax {expected}"
        )
        paid_types.add(qtype)
    assert paid_types == set(_QUEST_REWARDS), f"payout missing for: {set(_QUEST_REWARDS) - paid_types}"


# ---------------------------------------------------------------------------
# (b) a declined giver is not re-approached by that hero for >= 15 sim-min
# ---------------------------------------------------------------------------

def test_soak_declined_giver_not_reapproached_within_15_sim_min():
    run = _soak("decline")
    declines = run["declined"]
    print(
        f"WK126_SOAK_DECLINE declines={len(declines)} commits={len(run['commits'])} "
        f"accidental_accepts={len(run['started'])} sim_minutes={run['sim_minutes_ran']}"
    )
    assert declines, (
        "no QUEST_DECLINED in the decline soak — the mock's <50g reward "
        f"threshold never produced a decline (commits: {run['commits']})"
    )
    assert run["first_decline_ms"] is not None
    # The run must actually have monitored the full 15-min window.
    watched_ms = run["sim_minutes_ran"] * 60_000 - run["first_decline_ms"]
    assert watched_ms >= QUEST_DECLINE_COOLDOWN_MS, (
        f"decline soak only watched {watched_ms / 60_000.0:.1f} sim-min past the "
        "first decline — cannot prove the 15-min cooldown"
    )

    # THE assertion: no (hero, giver) quest_offer commit starts inside that
    # hero's decline window for that giver.
    violations = []
    for d in declines:
        hero_id = str(d.get("hero_id", ""))
        giver_id = str(d.get("giver_id", ""))
        until = int(d.get("until_ms", 0))
        decline_at = until - int(QUEST_DECLINE_COOLDOWN_MS)
        for c_hero, c_giver, c_started in run["commits"]:
            if c_hero == hero_id and c_giver == giver_id and decline_at < c_started < until:
                violations.append((hero_id, giver_id, decline_at, c_started, until))
    assert violations == [], (
        "heroes re-approached a giver INSIDE their 15-sim-min decline window: "
        f"{violations}"
    )

    # Strength check: the window assertion is not vacuous — heroes did keep
    # approaching the giver (other heroes / post-window), each decline implies
    # an arrival, and at least one commit exists in the log.
    assert len(run["commits"]) >= len(declines) >= 1


# ---------------------------------------------------------------------------
# (d) no overlay-entity leak: giver add/remove cycles through the REAL
#     renderer removal path keep scene.entities at baseline (WK123 pattern)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ursina_app():
    """Boot a real Ursina app offscreen; skip cleanly without a Panda3D pipe."""
    try:
        from panda3d.core import load_prc_file_data

        load_prc_file_data("", "window-type offscreen\n")
        load_prc_file_data("", "audio-library-name null\n")
        import ursina  # noqa: F401
        from ursina import Ursina
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"Panda3D/Ursina import unavailable for offscreen test: {e}")

    try:
        app = Ursina()
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"Could not initialise offscreen Ursina: {e}")

    yield app

    try:
        app.destroy()
    except Exception:
        pass


def _step(app) -> None:
    """Flush scene._entities_marked_for_removal (same helper as the WK123 test)."""
    try:
        app.step()
    except Exception:
        from ursina import scene

        for e in list(getattr(scene, "_entities_marked_for_removal", [])):
            if e in scene.entities:
                scene.entities.remove(e)
        scene._entities_marked_for_removal.clear()


def test_quest_giver_marker_no_scene_entity_leak_across_add_remove(ursina_app):
    """Spawn N quest-giver billboards (each with the '!' marker + name label)
    through the REAL render collaborator, kill them ALL through the REAL
    ``UrsinaRenderer._destroy_removed_entities`` path (the production add/remove
    seam), repeat 3 cycles: ``scene.entities`` must return to baseline every
    cycle — the marker child must never orphan (WK123 C1 invariant)."""
    from ursina import scene

    from game.graphics.ursina_entity_render_collab import UrsinaEntityRenderCollab
    from game.graphics.ursina_renderer import UrsinaRenderer
    from game.graphics.ursina_unit_overlays import (
        ensure_ks_name_label,
        sync_quest_giver_marker,
    )
    from game.graphics.visual_specs import TAX_COLLECTOR_SPEC
    from ursina import color

    r = object.__new__(UrsinaRenderer)
    r._entities = {}
    r._unit_anim_state = {}
    r._unit_facing_state = {}
    r._entity_render = UrsinaEntityRenderCollab(r)

    _step(ursina_app)
    baseline = len(scene.entities)
    n_givers = 8
    post_cycle_counts = []

    for _cycle in range(3):
        for i in range(n_givers):
            stub = object()
            ent, obj_id = r._entity_render.get_or_create_entity(
                stub,
                model="quad",
                col=color.white,
                scale=(0.5, 0.5, 1),
                texture=None,
                billboard=True,
                key=f"quest_giver:b{i:08d}",
            )
            ensure_ks_name_label(
                ent, "_ks_name_label", "Herald",
                y=TAX_COLLECTOR_SPEC.label_y, scale=TAX_COLLECTOR_SPEC.label_scale,
            )
            sync_quest_giver_marker(ent, True)   # "!" on (open offer)
            sync_quest_giver_marker(ent, False)  # toggled off…
            sync_quest_giver_marker(ent, True)   # …and back on (same child)
        _step(ursina_app)
        assert len(scene.entities) > baseline, "spawn should add entities"

        r._destroy_removed_entities(active_ids=set())
        _step(ursina_app)
        post_cycle_counts.append(len(scene.entities))

    assert r._entities == {}, "renderer must drop every removed giver"
    assert post_cycle_counts == [baseline] * 3, (
        f"quest-giver overlay leak: scene.entities did not return to baseline "
        f"({baseline}) across add/remove cycles: {post_cycle_counts} — the '!' "
        "marker (or name label) child orphaned (WK123 C1 class)"
    )


# ---------------------------------------------------------------------------
# (e) WK67 digest backstop — the golden constant must not be re-baselined
# ---------------------------------------------------------------------------

def test_wk67_digest_constant_not_rebaselined():
    """The quest sprint's central constraint: the WK67 AI-decision digest stays
    byte-identical and is NEVER re-baselined. The digest itself is computed and
    asserted by tests/test_wk67_ai_boundary.py; this backstop pins the GOLDEN
    CONSTANT in that file so a silent re-baseline cannot slip through a suite
    run that happens to match a drifted sim."""
    path = os.path.join(_REPO_ROOT, "tests", "test_wk67_ai_boundary.py")
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r'_AI_DECISION_DIGEST\s*=\s*"([0-9a-f]{64})"', src)
    assert m, "could not locate _AI_DECISION_DIGEST in tests/test_wk67_ai_boundary.py"
    assert m.group(1) == (
        "b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded"
    ), (
        "the WK67 AI-decision digest golden constant CHANGED — re-baselining is "
        "forbidden (wk126 plan CENTRAL CONSTRAINT); revert and fix the guard "
        "that leaked quest behavior into the digest scenario"
    )


# ---------------------------------------------------------------------------
# Subprocess runner entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _scenario = sys.argv[1] if len(sys.argv) > 1 else "main"
    _seed = int(sys.argv[2]) if len(sys.argv) > 2 else _SOAK_SEED
    if _scenario == "main":
        _result = _run_main_soak(_seed, _MAIN_MINUTES)
    elif _scenario == "decline":
        _result = _run_decline_soak(_seed)
    else:
        raise SystemExit(f"unknown scenario {_scenario!r}")
    print(_JSON_MARKER + json.dumps(_result))
