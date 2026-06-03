# WK64 Sprint Plan — AI Contracts & System Runner

**Created:** 2026-05-28 | **PM:** Agent 01 | **Status:** READY TO KICK OFF
**Sprint ID:** `wk64_ai_contracts_and_system_runner`
**Source:** `.cursor/plans/GPT 5.5 Codebase Improvements Recommendations.md` items 15, 17, 22
**Depends on:** Sprint `wk63_engine_boundary_cleanup` (applied uncommitted; landed cleanly by **Phase A** below — see Precondition).
**Execution model:** Claude Code parent Agent 1 coordinates role-based subagents (orchestrator). All subagents run on **Opus (max effort)**.

---

## Precondition & Baseline — WK63 carries a pathfinding regression; Phase A fixes it

WK63's code is applied in the working tree (verified 2026-05-28: `entity_id` exists on Enemy/Peasant/Guard/Building, `EngineCommandHub` + the five command Protocols exist in `game/game_commands.py`, `game/presentation/selection_state.py` exists) **but it is not committed**, and its plan file is untracked.

**WK63 is NOT safe to commit as-is.** Gate verification on 2026-05-28 found:

| Gate | Result |
|------|--------|
| `python -m pytest tests/` | ✅ 503 passed |
| `python tools/determinism_guard.py` | ✅ PASS |
| `python tools/qa_smoke.py --quick` | ❌ **FAIL** on `speed_scaling 0.25x`: "expected at least one bounty responder" |

This is a **real regression**, isolated to WK63's deterministic pathfinding budget (Agent 04's WK63 work in `game/systems/navigation.py`). Controlled experiments:

| Experiment | Result |
|---|---|
| Clean HEAD, 10 heroes, 0.25x | PASS, `stuck_events=0` |
| Full WK63, 10 heroes, 0.25x | **FAIL**, `stuck_events=9` |
| WK63 with only the 3 budget files reverted | PASS (selection-state + command-ports are clean) |
| WK63 + budget caps monkeypatched to ∞ | PASS, `stuck_events=0` |
| WK63, 30 heroes, 1.0x | PASS but `stuck_events=37`, 141 recoveries |

**Root cause (two coupled defects):**
1. `compute_path_worldpoints` returns `[]` when the per-frame budget is exhausted, and **every caller blindly overwrites its path with it** (`hero.py:946`, `enemy.py:303/534/568`, `guard.py:172`, `tax_collector.py:147/199` all do `self.path = compute_path_worldpoints(...)`). A unit that *had* a valid path **loses it** the moment it loses the per-frame budget race — indistinguishable from "no path exists." The `navigation.py:149` comment even claims *"caller keeps existing path,"* but no caller does.
2. The intended defer mechanism is **dead code**: `PathfindingBudget.enqueue()`/`drain_pending()`/`_pending_queue` exist but `compute_path_worldpoints` never enqueues and `begin_frame` never drains. The audit's guidance (item 3: *"return a deterministic 'defer path request' result rather than an empty path that looks like failure"*) was never wired in.

Raising the caps only masks it — starvation returns at higher entity counts (30 heroes → 37 stuck events even at 1.0x). The correct fix is the audit's: **on exhaustion, keep the existing path and retry next frame.**

**Therefore WK64 now opens with Phase A** (below), which fixes the budget defect, re-greens all gates, and commits the combined WK63 + fix as the WK64 baseline. Only after Phase A is committed green does **Phase B** (the AI-contracts + system-runner waves) begin.

> Why fold the fix into WK64 instead of a separate WK63 commit: per the human's direction (2026-05-28), all remaining work lands in this plan since WK64 is the active sprint. Phase A *is* the act of landing WK63 cleanly.

---

## Why This Sprint

WK62 fixed engine correctness and extracted UI/render seams. WK63 finished the engine boundary (selection state, pathfinding determinism, command ports). This sprint tackles the **AI and gameplay systems layer** — the code feature agents touch most often when adding hero behaviors, combat mechanics, or building interactions.

The core problem: every new hero behavior (hunger, shopping, resting, bounty pursuit, journey exploration, direct prompts) requires changes in 4–5 files in sync because:
- Task types are **stringly typed** — `hero.target` is a raw dict whose `"type"` key is a magic string, and the same field also sometimes holds a *live entity object* (enemy/lair/building) for combat. Nothing enforces the shape.
- Arrival handling is **dumped into `bounty_pursuit.py`** — a single `handle_moving()` function dispatches shopping, rest, inn drinks, meals, direct prompts, POIs, and bounties through a deeply nested if/elif ladder.
- Systems **bypass the `SystemContext` protocol** — several systems (`spawner`, `lairs`, `neutral_buildings`, `bounty`) already have an `update(ctx, dt)` method, but `SimEngine.update()` still calls bespoke `.tick()`/`.spawn()`/`.check_claims()` methods instead, because `SystemContext` is too narrow to carry the data those systems need.

## Goals

1. **Typed `HeroTask` and `TargetType` registry** (audit item 15) — Add `ai/contracts.py` with a `TargetType` enum and a `HeroTask` dataclass plus `to_dict`/`from_dict`/`coerce_task` bridges. The dict stays the on-hero storage format (single source of truth) so nothing breaks; `HeroTask` becomes the typed authoring + validation API.

2. **Extract arrival handlers from `bounty_pursuit.py`** (audit item 17) — Move the reached-destination dispatch out of `handle_moving()` into a new `ai/arrival_handlers.py` with a registry keyed by `TargetType`. Convert the **hunger** and **shopping** behaviors to author their tasks through `HeroTask` end-to-end (the live-conversion proof), while all other behaviors keep emitting dicts via the compatibility bridge.

3. **Expand `SystemContext` + ordered `SystemRunner`** (audit item 22) — Widen `SystemContext` with `peasants`, `guards`, `bounties`, `pois`, `rubble_records`, `lairs`, `castle` (all defaulted so existing call sites don't break), then introduce a `SystemRunner` that calls `update(ctx, dt)` on an ordered tuple of systems whose `update()` is **proven equivalent** to their current bespoke call. Systems that cannot be safely migrated this sprint stay bespoke and are listed as documented exceptions.

## Non-Goals

- Do **not** rewrite `BasicAI.update_hero()` into a full task router (audit item 18) — larger follow-up.
- Do **not** convert behaviors other than hunger and shopping to author `HeroTask` objects this sprint (bounty/direct_prompt/POI/defense/journey keep emitting dicts via the bridge).
- Do **not** make `hero.target` hold a `HeroTask` object — it stays a dict. (See "Critical design rule" below.)
- Do **not** split `SimEngine` into services (audit item 12) — keep the hand-written orchestration in `SimEngine.update()`; the runner only wraps the system calls that are provably fire-and-forget.
- Do **not** split `Hero` into services (item 20), centralize combat/projectiles (item 21), or split LLM context (item 19).
- Do **not** change any rendering, UI, or audio code.

## Definition of Done

- **Phase A:** `python tools/qa_smoke.py --quick` PASS *including* `speed_scaling 0.25x`; `compute_path_worldpoints` distinguishes "deferred" (budget exhausted) from "no path"; callers keep their existing path on defer; path-less heroes direct-steer on defer (Step A2.1); 30-hero/1.0x `stuck_events` ≤ 30 (≈ the measured 27 crowding baseline); WK63 + fix committed.
- `python -m pytest tests/ -x -q` PASS
- `python tools/determinism_guard.py` PASS
- `python tools/qa_smoke.py --quick` PASS
- `ai/contracts.py` exists with `TargetType` (13 members) and `HeroTask` (+ `to_dict`/`from_dict`/`coerce_task`/`assign_hero_task`).
- `ai/arrival_handlers.py` exists with a `TargetType`-keyed registry; `bounty_pursuit.handle_moving()` delegates its reached-destination dispatch to it.
- **hunger** (`ai/behaviors/hunger.py`) and **shopping** (`ai/behaviors/shopping.py`) author their tasks via `HeroTask` + `assign_hero_task`; round-trip leaves `hero.target` as the same dict shape as before.
- `SystemContext` includes `peasants`, `guards`, `bounties`, `pois`, `rubble_records`, `lairs`, `castle`.
- A `SystemRunner` (`game/sim/system_runner.py`) drives the proven-equivalent systems in a fixed order; remaining systems are documented exceptions in the code and in this plan's Gate 2 notes.
- Hero behavior is visually unchanged: before/after screenshots of a heroes-shopping-and-eating scenario show no regression (see Gate 2).

---

## Critical Design Rule (read before any code)

**`hero.target` remains a `dict` at all times.** It is the single source of truth that ~30 call sites already read via `isinstance(target, dict)` and `target.get("type")`. If we ever store a `HeroTask` *object* there, every one of those `isinstance(..., dict)` checks silently returns `False` and the behavior breaks invisibly.

Therefore:
- Behaviors **construct** a `HeroTask` (for type-safety and validation), then immediately **serialize** it to the dict via `assign_hero_task(hero, task)`, which sets `hero.target = task.to_dict()`.
- Arrival handlers **consume** by calling `coerce_task(hero.target)` to get a typed `HeroTask` back from the dict, then read `task.payload[...]`.
- We do **not** keep a parallel `hero.task` attribute. One source of truth (the dict); `HeroTask` is a transient view at the construction and consumption boundaries.

This is exactly the "compat shim" approach: `to_dict`/`from_dict` bridge the typed and dict worlds, hunger+shopping author through the typed API ("convert live"), and every other reader keeps working unchanged.

---

## Wave Structure

```
PHASE A — Baseline Stabilization (MUST land + commit before Phase B):
    Step A1: Agent 11 writes failing-first pathfinding-defer regression tests
    Step A2: Agent 04 implements keep-path/defer fix (navigation.py + 4 caller files)
    Step A3: Agent 11 gate — full suite + determinism + qa_smoke (incl 0.25x) + 30-hero stuck check + screenshot
    Step A4: PM (Agent 01) commits WK63 + Phase-A fix as the WK64 baseline
    |
    v
PHASE B — AI Contracts & System Runner (waves below assume Phase A committed green):
    Wave 0: Characterization tests (Agent 11)
        |  capture current AI arrival behavior + current system update order BEFORE changes
        v
    Wave 1 (parallel — NO file overlap):
        Agent 06: ai/contracts.py            (new file only; zero behavior change)
        Agent 05: SystemContext + SystemRunner (protocol.py, new system_runner.py, sim_engine.py)
        |
        v
    Gate 1: Agent 11 verifies both (full suite + determinism + qa_smoke)
        |
        v
    Wave 2: Agent 06: ai/arrival_handlers.py + convert hunger & shopping to HeroTask
        |          (depends on contracts.py from Wave 1)
        v
    Gate 2: Agent 11 (regression + screenshots) + Agent 04 (determinism)
```

## File Ownership (no collisions within a wave)

### Phase A (sequential: A2 fix, then A1 tests can be written in parallel before A2)

| Agent | May create / edit | Must NOT edit |
|-------|-------------------|---------------|
| 04 (Determinism) | `game/systems/navigation.py`, `game/entities/hero.py`, `game/entities/enemy.py`, `game/entities/guard.py`, `game/entities/tax_collector.py` (caller path-assignment lines only) | `ai/**`, `game/systems/protocol.py`, `game/sim_engine.py`, `game/ui/**`, `game/graphics/**`, `config.py` |
| 11 (QA) | `tests/test_wk64_pathfinding_defer.py` (NEW) | production code |

> Phase A and Phase B do not overlap in time — Phase A is fully committed before Phase B starts — so even files touched by both (`hero.py`) are sequential, not concurrent. Note Phase B Wave 1/2 do **not** edit `hero.py` movement code, so there is no residual conflict.

### Wave 1 (parallel) — Phase B

| Agent | May create / edit | Must NOT edit |
|-------|-------------------|---------------|
| 06 (AI) | `ai/contracts.py` (NEW only) | everything else |
| 05 (Gameplay) | `game/systems/protocol.py`, `game/sim/system_runner.py` (NEW), `game/sim_engine.py` | `ai/**`, `game/engine.py`, `game/entities/**`, `game/graphics/**`, `game/ui/**`, `config.py` |

**No conflict:** Agent 06's only Wave-1 file is brand-new (`ai/contracts.py`). Agent 05 owns `sim_engine.py` alone this wave. Agent 06 does **not** touch `sim_engine.py`.

### Wave 2 — Phase B

| Agent | May create / edit | Must NOT edit |
|-------|-------------------|---------------|
| 06 (AI) | `ai/arrival_handlers.py` (NEW), `ai/behaviors/bounty_pursuit.py`, `ai/behaviors/hunger.py`, `ai/behaviors/shopping.py`, `ai/basic_ai.py` (only if a delegation line needs updating) | `game/sim_engine.py`, `game/systems/**`, `game/engine.py`, `game/graphics/**`, `game/ui/**`, `config.py` |

### Test files

| Agent | Owns |
|-------|------|
| 11 (QA) | `tests/test_wk64_ai_contracts.py` (NEW), `tests/test_wk64_system_runner.py` (NEW). May also extend existing AI tests only to update assertions that changed shape. |

**Universal rule for every subagent:** **DO NOT COMMIT, push, or create branches.** Make your edits, run your verification, report results, and STOP. The PM (Agent 01) commits after gates pass. Do not iterate further or "improve" unrelated code after your task's acceptance criteria are met.

---

## Phase A — Baseline Stabilization (Pathfinding Budget Fix)

**Goal:** Fix the WK63 pathfinding-budget regression so an exhausted per-frame budget **defers** (keeps the existing path, retries next frame) instead of returning `[]` that callers blindly assign — then re-green all gates and commit WK63 + fix as the WK64 baseline.

**Owners:** Agent 04 (NetworkingDeterminism_Lead) — the fix (Intelligence: HIGH, determinism reasoning); Agent 11 (QA) — failing-first tests + gate (Intelligence: HIGH).

### Step A1 — Agent 11: failing-first regression tests

Create `tests/test_wk64_pathfinding_defer.py`. These tests must **FAIL on the current (pre-fix) code** and **PASS after Step A2**. Write them first so the fix is verified, not assumed.

**Files you may create:** `tests/test_wk64_pathfinding_defer.py` · **Must NOT edit:** any production code.

```python
import pygame
import pytest

from game.engine import GameEngine


def test_exhausted_budget_returns_none_not_empty():
    """Budget exhaustion must be DISTINGUISHABLE from 'no path found'.

    Pre-fix: returns [] (ambiguous). Post-fix: returns None (deferred).
    """
    from game.systems.navigation import compute_path_worldpoints, get_pathfinding_budget
    engine = GameEngine(headless=True)
    try:
        budget = get_pathfinding_budget()
        budget.begin_frame()
        # Force exhaustion.
        budget._frame_plans = budget.MAX_PLANS_PER_FRAME
        result = compute_path_worldpoints(
            engine.sim.world, engine.sim.buildings, 100.0, 100.0, 500.0, 500.0
        )
        assert result is None, (
            "exhausted budget must return None (deferred), not [] (no-path). "
            f"got {result!r}"
        )
    finally:
        pygame.quit()


def test_available_budget_returns_list():
    """With budget available, the function returns a list (a path, or [] if truly no path)."""
    from game.systems.navigation import compute_path_worldpoints, get_pathfinding_budget
    engine = GameEngine(headless=True)
    try:
        budget = get_pathfinding_budget()
        budget.begin_frame()  # fresh budget
        result = compute_path_worldpoints(
            engine.sim.world, engine.sim.buildings, 100.0, 100.0, 200.0, 200.0
        )
        assert isinstance(result, list), f"expected list with budget available, got {result!r}"
    finally:
        pygame.quit()


def test_hero_keeps_existing_path_when_budget_deferred():
    """A hero with a valid path must NOT lose it when the budget is exhausted."""
    from game.entities.hero import HeroState
    from game.systems.navigation import get_pathfinding_budget
    engine = GameEngine(headless=True)
    try:
        heroes = engine.sim.heroes
        if not heroes:
            pytest.skip("no heroes in headless engine")
        hero = heroes[0]
        sentinel_path = [(hero.x + 320.0, hero.y), (hero.x + 640.0, hero.y)]
        hero.path = list(sentinel_path)
        hero.state = HeroState.MOVING
        # A goal whose tile differs from the current path goal -> triggers a replan attempt.
        hero.target_position = (hero.x + 640.0, hero.y)
        hero._path_goal = None  # force goal_changed -> need_replan True

        # Exhaust the budget so the replan attempt is deferred.
        budget = get_pathfinding_budget()
        budget.begin_frame()
        budget._frame_plans = budget.MAX_PLANS_PER_FRAME

        gs = engine.sim.get_game_state(
            screen_w=1920, screen_h=1080, display_mode="windowed", window_size=(1920, 1080),
            placing_building_type=None, debug_ui=False, micro_view_mode=None,
            micro_view_building=None, micro_view_quest_hero=None, micro_view_quest_data=None,
            right_panel_rect=None, llm_available=False, ui_cursor_pos=None,
        )
        hero.update(1.0 / 30.0, gs)

        # The hero may have consumed the first waypoint by moving, but it must still
        # have a non-empty path (it was NOT wiped to [] by the deferred replan).
        assert hero.path, "deferred budget wiped the hero's existing path (regression)"
    finally:
        pygame.quit()
```

> Note for Agent 11: `test_hero_keeps_existing_path_when_budget_deferred` is the behavioral heart of the fix. If the hero's `update()` path-replan logic differs slightly from the lines quoted in Step A2, READ `game/entities/hero.py` around line 945 and adjust the test setup (e.g. how `need_replan` is triggered) so it genuinely exercises a deferred replan — but keep the final assertion (`hero.path` stays non-empty) intact.

### Step A2 — Agent 04: implement the keep-path / defer fix

**Files you may edit:** `game/systems/navigation.py`, `game/entities/hero.py`, `game/entities/enemy.py`, `game/entities/guard.py`, `game/entities/tax_collector.py`.
**Files you must NOT edit:** `ai/**`, `game/systems/protocol.py`, `game/sim_engine.py`, `game/ui/**`, `game/graphics/**`, `config.py`, `game/systems/pathfinding.py`.

**The invariant:** `compute_path_worldpoints` returns `None` to mean *"deferred — budget exhausted this frame"* and a `list` (possibly `[]`) to mean *"this is the answer; [] = genuinely no path."* No caller may ever assign `None` to `self.path`.

**(a) `game/systems/navigation.py` — `compute_path_worldpoints` (lines 138–173).** Change only the exhaustion branch + the return type/docstring:

```python
def compute_path_worldpoints(
    world,
    buildings: list,
    start_x: float,
    start_y: float,
    goal_x: float,
    goal_y: float,
) -> list[tuple[float, float]] | None:
    """Compute an A* path (world-space waypoints) avoiding solid buildings.

    Returns:
        list: the path, or [] when there is genuinely no path to the goal.
        None: DEFERRED -- the per-frame budget is exhausted. The caller MUST
              keep its existing ``path`` and retry next frame. Do NOT treat
              None as failure and do NOT assign it to ``entity.path``.
    """
    budget = get_pathfinding_budget()

    # Budget exhausted -> defer (do NOT return [], which callers would assign,
    # wiping a still-valid path and looking like 'no path found').
    if not budget.budget_available():
        return None

    start = world.world_to_grid(start_x, start_y)
    goal = world.world_to_grid(goal_x, goal_y)

    t0 = time.perf_counter()
    grid_path, expansions = find_path(world, start, goal, buildings=buildings, max_expansions=8000)
    t1 = time.perf_counter()
    wall_ms = (t1 - t0) * 1000.0

    budget.record_plan(expansions, wall_ms)

    perf_stats.pathfinding.calls += 1
    perf_stats.pathfinding.total_ms += wall_ms
    perf_stats.pathfinding.total_expansions += expansions
    if not grid_path:
        perf_stats.pathfinding.failures += 1
        return []

    return grid_to_world_path(grid_path)
```

Also bump the per-frame plan cap as a latency tweak (NOT a correctness crutch — the defer logic is what makes it correct):

```python
    MAX_PLANS_PER_FRAME: int = 24          # was 12
    MAX_EXPANSIONS_PER_FRAME: int = 24_000  # unchanged
```

**(b) `game/entities/hero.py` (lines 945–950) — THE critical caller** (heroes have no direct-move fallback in this branch, so a wiped path = stuck):

```python
                if need_replan:
                    _new_path = compute_path_worldpoints(
                        world, buildings, self.x, self.y, goal_x, goal_y
                    )
                    if _new_path is not None:
                        self.path = _new_path
                        self._path_goal = goal_key
                        self._path_last_replan_ms = int(sim_now_ms())
                    elif not self.path:
                        # WK64 A2.1: budget DEFERRED and we have NO path to follow.
                        # Do NOT stall -- direct-steer toward the goal this frame (the
                        # same fallback the far-target/black-fog branch above uses, and
                        # that guard.py/tax_collector.py already use). A precise A* path
                        # is acquired on a later frame once budget frees up. This prevents
                        # first-path starvation under heavy entity load (30+ heroes) from
                        # registering as a stuck unit. Do NOT stamp _path_last_replan_ms.
                        self.move_towards(goal_x, goal_y, dt)
                        return
                    # else: budget DEFERRED but we still have a path -- keep following it
                    # and retry the replan next frame. Do NOT stamp _path_last_replan_ms.
```

> **Step A2.1 (added after the first Phase-A gate).** The first gate revealed that keep-path alone is not enough at 30-hero scale: heroes that cannot acquire their *first* path within the per-frame budget sit with an empty path and trip stuck-recovery. The `elif not self.path:` branch above is the fix — a path-less hero whose replan is deferred direct-steers this frame instead of stalling. This is deterministic (`move_towards` uses only dt + positions) and mirrors the existing far-target direct-steering, so `determinism_guard` stays green. Heroes are the only caller that needs this (guard/tax_collector already have a `move_towards` fallback when `self.path` is empty; enemies have `_long_distance_mode` direct steering).

**(c) `game/entities/enemy.py`** — three call sites (chase ~line 303, kite ~line 534, and ~line 568). For each, wrap the assignment. Example for the chase site (lines 302–307):

```python
                if want_replan:
                    _new_path = compute_path_worldpoints(world, buildings, self.x, self.y, target_x, target_y)
                    if _new_path is not None:
                        self.path = _new_path
                        self._path_goal = goal_key
                        self._path_commit_until_ms = now_ms_val + getattr(self, "_path_commit_duration_ms", 500)
                        if not self.path:
                            self._next_replan_ms = now_ms_val + 800
                    # else: deferred -- keep existing path, retry next frame
```

Apply the same `_new_path is not None` guard to the other two enemy sites. READ each one first; preserve its surrounding bookkeeping exactly, only gating the `self.path = ...` assignment (and any "no path" backoff) behind `if _new_path is not None:`.

**(d) `game/entities/guard.py` (line 172)** and **(e) `game/entities/tax_collector.py` (lines 147 and 199)** — same guard:

```python
                    _new_path = compute_path_worldpoints(world, buildings, self.x, self.y, tx, ty)
                    if _new_path is not None:
                        self.path = _new_path
                        self._path_goal = goal_key
                    # else: deferred -- keep existing path
```

> Leave the `if not hasattr(self, "path"): self.path = []` initialization lines alone — those run only when the attribute is first created, not as path wipes. Leave the dead `enqueue`/`drain_pending`/`_pending_queue` code in `PathfindingBudget` as-is (removing it is out of scope; the next-frame-retry approach does not need it).

**Determinism:** the defer decision is made from `budget_available()`, which depends only on plans/expansions consumed in deterministic entity-update order. No wall-clock gates gameplay. `determinism_guard.py` must stay green.

### Step A3 — Agent 11: gate

```powershell
python -m pytest tests/test_wk64_pathfinding_defer.py -x -v
python -m pytest tests/ -x -q
python tools/determinism_guard.py
python tools/qa_smoke.py --quick
```

All must pass — **including `qa_smoke`'s `speed_scaling 0.25x` scenario**, which was the original failure.

Then the **starvation-scaling check** (this is the gate that proves caps weren't just band-aided): run the 30-hero / 1.0x scenario and confirm stuck-event churn is near clean-HEAD levels:

```powershell
python tools/observe_sync.py --seconds 48.0 --heroes 30 --seed 3 --log-every 9999 --qa --bounty
```

Read the final `[scenario] counters:` line. **Acceptance: `[qa] PASS` and `stuck_events` ≤ 30** — i.e. within ~3 of the clean pre-WK63 30-hero crowding baseline of **27** (measured 2026-05-28). IMPORTANT: at 30-hero density, crowding alone produces ~27 stuck events even on pristine code, so the 10-hero "≤0" intuition does NOT apply here. Reference points: clean HEAD 30h = **27**; broken WK63 30h = **37**; keep-path-only fix 30h = **34**; keep-path + direct-steer-on-defer (Step A2.1) should land **≤ 30** (≈ baseline). If `stuck_events` is materially above ~30, path-less heroes are still starving — confirm the Step A2.1 `elif not self.path:` direct-steer branch is present and correct.

**Screenshot verification (pathfinding is visible behavior):**

```powershell
python tools/capture_screenshots.py --scenario base_overview --seed 3 --out docs/screenshots/wk64_phaseA_pathfix --size 1920x1080 --ticks 480
```

View the PNGs and give a verdict: units (heroes, enemies, guards, tax collector) move smoothly toward targets; none frozen mid-field or vibrating in place; heroes reach buildings/bounties. Report the verdict with paths inline.

### Step A4 — PM (Agent 01): commit the baseline

Once Step A3 is fully green, the PM commits the combined WK63 + Phase-A fix as the WK64 baseline (this is the act of "landing WK63"). Suggested message body: `Sprint wk64 Phase A: land wk63 (entity IDs, selection state, command ports) + fix pathfinding-budget starvation (defer instead of wiping path)`. Subagents do **not** commit; only the PM does, after gates pass.

---

## Phase B — AI Contracts & System Runner

> All waves below (Wave 0 → Gate 2) are **Phase B** and assume **Phase A is committed and green**. Do not start Phase B until the baseline commit from Step A4 exists.

## Wave 0 — Characterization Tests

**Owner:** Agent 11 (QA_TestEngineering_Lead) · **Intelligence:** HIGH (novel characterization tests)

### Purpose

Lock down current behavior so Wave 1/2 agents have a regression net. These tests must PASS against the **current** code (before any WK64 change). They document the contract that must not change.

**Files you may create:** `tests/test_wk64_ai_contracts.py`, `tests/test_wk64_system_runner.py`
**Files you must NOT edit:** any `game/**`, `ai/**`, `config.py`, `tools/**`.

### Task A — Arrival-behavior characterization (`tests/test_wk64_ai_contracts.py`)

Write tests that pin the *observable* outcome of each arrival type, driving through the real `BasicAI`/`bounty_pursuit.handle_moving` path. The pattern: construct a headless engine, place a hero next to the relevant building, set the legacy `hero.target` dict + `hero.target_position` to the hero's location (so it counts as "arrived"), call the moving handler, then assert the resulting hero state.

Use this exact scaffold (it matches how the codebase constructs a headless world):

```python
import pygame
import pytest

from game.engine import GameEngine
from game.entities.hero import HeroState


def _engine():
    return GameEngine(headless=True)


def test_buy_meal_arrival_purchases_and_returns_idle():
    """Arriving at a buy_meal waypoint buys a meal and resets to IDLE.

    This pins the BUY_MEAL arrival contract that arrival_handlers.py must
    preserve after extraction.
    """
    engine = _engine()
    try:
        ai = engine.sim.ai_controller
        heroes = engine.sim.heroes
        if not heroes:
            pytest.skip("no heroes in headless engine")
        hero = heroes[0]

        # Find or skip: we need a constructed food stand. If none spawns in the
        # default headless world, document the gap with skip (do NOT fabricate
        # buildings — keep the test honest about what the default world has).
        from ai.behaviors.hunger import find_nearest_food_stand
        stand = find_nearest_food_stand(hero, engine.sim.buildings)
        if stand is None:
            pytest.skip("default headless world has no food stand")

        hero.x, hero.y = float(stand.center_x), float(stand.center_y)
        hero.gold = 999
        hero.state = HeroState.MOVING
        hero.target = {"type": "buy_meal", "food_stand": stand}
        hero.target_position = (hero.x, hero.y)

        ai.handle_moving(hero, engine.sim.get_game_state(
            screen_w=1920, screen_h=1080, display_mode="windowed",
            window_size=(1920, 1080), placing_building_type=None, debug_ui=False,
            micro_view_mode=None, micro_view_building=None, micro_view_quest_hero=None,
            micro_view_quest_data=None, right_panel_rect=None, llm_available=False,
            ui_cursor_pos=None,
        ))

        assert hero.target is None
        assert hero.state == HeroState.IDLE
    finally:
        pygame.quit()
```

**Important:** Before you write the other arrival tests, READ `ai/behaviors/bounty_pursuit.py::handle_moving` (lines ~361–542) so you know the exact post-conditions for each `type`. Write one test per arrival type that the default headless world can exercise without fabricating buildings:
- `buy_meal` → `hero.target is None`, state `IDLE` (shown above).
- `shopping` → after arrival, `hero.state == HeroState.SHOPPING`, `hero.target is None`, and `hero.pending_task == "shopping"`, `hero.pending_task_building` is the shop. (Read lines 488–505.)
- `rest_inn` → `hero.target is None`, `pending_task == "rest_inn"`. (Lines 508–518; needs an inn — skip if absent.)
- `get_drink` → `hero.target is None`, state `IDLE`, `pending_task == "get_drink"`. (Lines 527–538.)
- `going_home` → `hero.target is None`. (Lines 480–485; needs `hero.home_building`.)
- `visit_poi` → `hero.target is None`, state `IDLE`. (Lines 473–477.)

For any type whose building isn't present in the default world, use `pytest.skip(...)` with a clear reason rather than fabricating state. The goal is a faithful snapshot of current behavior, not maximal coverage.

Also add a pure round-trip placeholder test that will become meaningful after Wave 1 (write it now so Wave 1 can flip it green):

```python
def test_contracts_module_round_trips_when_present():
    """After Wave 1, HeroTask.to_dict/from_dict must round-trip the legacy shape.

    Skips cleanly until ai/contracts.py lands so this file passes on current code.
    """
    pytest.importorskip("ai.contracts")
    from ai.contracts import HeroTask, TargetType, coerce_task

    d = {"type": "shopping", "item": "potion", "marketplace": None,
         "blacksmith": None, "shop_building": None}
    task = HeroTask.from_dict(d)
    assert task is not None
    assert task.type == TargetType.SHOPPING
    # Round-trip preserves every legacy key the arrival handler reads.
    back = task.to_dict()
    assert back["type"] == "shopping"
    for k in ("item", "marketplace", "blacksmith", "shop_building"):
        assert k in back
    # A live entity target is NOT a task.
    assert coerce_task(object()) is None
    assert coerce_task(None) is None
```

### Task B — System update characterization (`tests/test_wk64_system_runner.py`)

Pin the current system update behavior so Agent 05's runner refactor can't change it:

```python
import pygame
import pytest

from game.engine import GameEngine


def test_sim_update_runs_without_error_and_advances():
    """A single sim update tick completes and advances sim time deterministically."""
    engine = GameEngine(headless=True)
    try:
        before = int(engine.sim._sim_now_ms)
        engine.update(0.05)
        after = int(engine.sim._sim_now_ms)
        assert after - before == 50, f"expected +50ms, got {after - before}"
    finally:
        pygame.quit()


def test_system_context_has_core_fields_today():
    """Documents the CURRENT SystemContext shape. Wave 1 widens it (adds fields);
    these core fields must remain."""
    from game.systems.protocol import SystemContext
    import dataclasses
    names = {f.name for f in dataclasses.fields(SystemContext)}
    for required in ("heroes", "enemies", "buildings", "world", "economy", "event_bus"):
        assert required in names


def test_combat_buff_waveevent_systems_expose_update_ctx():
    """These three are already driven via update(ctx, dt) today and must stay so."""
    from game.systems.combat import CombatSystem
    from game.systems.buffs import BuffSystem
    from game.systems.wave_events import WaveEventSystem
    for cls in (CombatSystem, BuffSystem, WaveEventSystem):
        assert hasattr(cls, "update")
```

Add one stability test that runs ~120 ticks and asserts the engine stays healthy (no exceptions, hero/enemy lists remain lists). This catches ordering regressions from the runner change:

```python
def test_engine_stable_over_120_ticks():
    engine = GameEngine(headless=True)
    try:
        for _ in range(120):
            engine.update(1.0 / 30.0)
        assert isinstance(engine.sim.heroes, list)
        assert isinstance(engine.sim.enemies, list)
    finally:
        pygame.quit()
```

### Verification (Wave 0)

```powershell
python -m pytest tests/test_wk64_ai_contracts.py tests/test_wk64_system_runner.py -x -v
python -m pytest tests/ -x -q
```

All Wave-0 tests must PASS against current code. The `test_contracts_module_round_trips_when_present` test will skip (that's expected until Wave 1).

---

## Wave 1A — `ai/contracts.py` (Agent 06)

**Owner:** Agent 06 (AI) · **Intelligence:** HIGH (defines the contract every behavior will use)

### Overview

Create **one new file**, `ai/contracts.py`. It introduces the typed `TargetType` enum and `HeroTask` dataclass plus the dict bridge. **This wave changes zero behavior** — no existing file is edited. You are only adding the vocabulary that Wave 2 will use.

**Files you may create:** `ai/contracts.py`
**Files you must NOT edit:** everything else (no behaviors, no `hero.py`, no `sim_engine.py`).

### Why this design (read carefully)

- `TargetType` subclasses `str` so that `TargetType.SHOPPING == "shopping"` is `True`. This guarantees that existing code comparing `target.get("type") == "shopping"` keeps working even though the enum value is stored. We use `(str, Enum)` rather than `StrEnum` for compatibility with Python 3.8+.
- The enum values **must exactly equal** the legacy magic strings currently used as `hero.target["type"]`. I have enumerated every one of them from the codebase below — do not rename, drop, or invent values.
- `HeroTask.payload` holds the type-specific extra keys the legacy dict carried (e.g. `food_stand`, `marketplace`, `blacksmith`, `shop_building`, `item`). `to_dict()` flattens `payload` back into the dict so arrival handlers read the same keys as today.

### Task — write exactly this file

```python
"""Typed AI task contracts (WK64, audit item 15).

Replaces the stringly-typed ``hero.target`` dict with a typed ``HeroTask``
dataclass and a ``TargetType`` enum. During WK64 these COEXIST with the legacy
dict shape:

  * Behaviors CONSTRUCT a HeroTask (type-safe, validated) and then call
    ``assign_hero_task(hero, task)``, which stores ``hero.target = task.to_dict()``.
    ``hero.target`` therefore stays a plain dict everywhere -- no existing
    reader breaks.
  * Arrival handlers CONSUME via ``coerce_task(hero.target)`` to recover a typed
    HeroTask from the dict, then read ``task.payload[...]``.

Critical rule: NEVER store a HeroTask object on ``hero.target``. ~30 call sites
do ``isinstance(hero.target, dict)`` and would silently misbehave. The dict is
the single source of truth; HeroTask is a transient view at the construction
and consumption boundaries.

DO NOT remove the dict compatibility path in this sprint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TargetType(str, Enum):
    """Canonical hero task/target kinds.

    Values MUST equal the legacy ``hero.target["type"]`` strings so ``to_dict``/
    ``from_dict`` round-trip without changing any consumer that still reads the
    dict. This is the complete set found in the WK64 codebase audit -- do not
    rename or remove values.
    """

    BOUNTY = "bounty"
    DIRECT_PROMPT = "direct_prompt"
    VISIT_POI = "visit_poi"
    GOING_HOME = "going_home"
    SHOPPING = "shopping"
    REST_INN = "rest_inn"
    GET_DRINK = "get_drink"
    BUY_MEAL = "buy_meal"
    PATROL = "patrol"
    EXPLORE_FRONTIER = "explore_frontier"
    DEFEND_CASTLE = "defend_castle"
    DEFEND_NEUTRAL = "defend_neutral"
    JOURNEY_EXPLORE = "journey_explore"

    @classmethod
    def from_str(cls, value: str) -> Optional["TargetType"]:
        """Return the matching member, or None if ``value`` is unknown."""
        try:
            return cls(value)
        except ValueError:
            return None


@dataclass(slots=True)
class HeroTask:
    """Typed hero task. Coexists with the legacy dict shape during WK64.

    Attributes:
        type: the TargetType.
        target_id: stable id of the target entity if applicable (else None).
        target_ref: best-effort live object reference (headless tests / fallback).
        started_ms: sim time the task started (0 if the legacy dict omitted it).
        payload: all type-specific extra keys the legacy dict carried, verbatim.
                 e.g. BUY_MEAL -> {"food_stand": <building>}
                      SHOPPING -> {"item", "marketplace", "blacksmith", "shop_building"}
    """

    type: TargetType
    target_id: str | int | None = None
    target_ref: object | None = None
    started_ms: int = 0
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Render to the legacy dict shape that existing consumers read."""
        d: dict[str, Any] = {"type": self.type.value}
        if self.started_ms:
            d["started_ms"] = int(self.started_ms)
        # payload carries the type-specific keys exactly as the old dict did.
        d.update(self.payload)
        return d

    @classmethod
    def from_dict(cls, d: Any) -> "HeroTask | None":
        """Build a HeroTask from a legacy dict. Returns None for non-task input."""
        if not isinstance(d, dict):
            return None
        tt = TargetType.from_str(str(d.get("type", "")))
        if tt is None:
            return None
        payload = {k: v for k, v in d.items() if k not in ("type", "started_ms")}
        return cls(
            type=tt,
            started_ms=int(d.get("started_ms", 0) or 0),
            payload=payload,
        )


def coerce_task(target: Any) -> HeroTask | None:
    """Normalize whatever is on ``hero.target`` into a HeroTask, or None.

    Returns:
        * a HeroTask if ``target`` is already a HeroTask, or a legacy task dict.
        * None if ``target`` is None, or a live entity object (enemy / lair /
          building) -- those are combat targets, NOT tasks, and must be handled
          by the combat path, not the arrival registry.
    """
    if isinstance(target, HeroTask):
        return target
    if isinstance(target, dict):
        return HeroTask.from_dict(target)
    return None


def assign_hero_task(hero: Any, task: HeroTask) -> None:
    """Store a typed task on the hero as the legacy dict (single source of truth).

    This is the ONLY sanctioned way to put a HeroTask onto a hero. It deliberately
    serializes to a dict so every existing ``isinstance(hero.target, dict)`` reader
    keeps working.
    """
    hero.target = task.to_dict()
```

### Verification (Wave 1A)

```powershell
python -c "from ai.contracts import TargetType, HeroTask, coerce_task, assign_hero_task; print(len(list(TargetType)), 'target types')"
python -m pytest tests/test_wk64_ai_contracts.py -x -v
python -m pytest tests/ -x -q
```

Acceptance:
- Import succeeds; `len(list(TargetType)) == 13`.
- `test_contracts_module_round_trips_when_present` now PASSES (no longer skips).
- Full suite still green (you added a new file; nothing should regress).

**DO NOT COMMIT.** Report results and stop.

---

## Wave 1B — Expand `SystemContext` + ordered `SystemRunner` (Agent 05)

**Owner:** Agent 05 (Gameplay) · **Intelligence:** HIGH (cross-system equivalence reasoning)

### Overview

1. Widen `SystemContext` with new defaulted fields.
2. Have `SimEngine._build_system_context()` populate them.
3. Add a `SystemRunner` and wire **only** the systems whose `update(ctx, dt)` you have **proven equivalent** to their current bespoke call, preserving the exact current order. Everything else stays bespoke and is documented as an exception.

**Files you may edit:** `game/systems/protocol.py`, `game/sim_engine.py`; create `game/sim/system_runner.py`.
**Files you must NOT edit:** `ai/**`, `game/engine.py`, `game/entities/**`, `game/graphics/**`, `game/ui/**`, `config.py`.

### Task 1 (DO THIS FIRST) — equivalence audit

Open `game/sim_engine.py` and read `update()` (starts ~line 600). For each system, compare what `SimEngine.update()` calls today against that system's own `update(ctx, dt)` method. Produce a short written table in your final report like:

| System | Current call in sim_engine.update() | Has update(ctx,dt)? | Equivalent? | Action |
|--------|--------------------------------------|---------------------|-------------|--------|

What I already know from the audit (verify each before trusting it):
- `buff_system.update(system_ctx, dt)` — **already** called via update(ctx). SAFE to put in runner.
- `wave_event_system.update(system_ctx, dt)` — **already** called via update(ctx). SAFE to put in runner.
- `combat_system.update(system_ctx, dt)` — **already** called via update(ctx), BUT it is immediately followed by `get_emitted_events()` + `_route_combat_events()` and the `enemy_ranged_events` batch. Combat is **NOT** fire-and-forget. Keep combat's call where it is (with its event routing) — do **not** absorb it into the runner this sprint. Document as an exception.
- `nature_system.tick(dt, self.trees, world=..., buildings=...)` — uses `.tick()`, not `.update()`, and is wrapped in tree-tile bookkeeping. Exception — leave bespoke.
- `neutral_building_system.tick(dt, buildings, heroes, peasants, castle)` — has an `update(ctx,dt)` (line ~177) that is **not currently wired**. You MUST read both and confirm they do the same work before migrating. If not identical, leave bespoke and document.
- `spawner` / `lair_system` — called via `.spawn()` / `.spawn_enemies()` inside a slot-capping block. Their `update(ctx)` exists but the capping logic lives in `sim_engine`. Leave bespoke unless you can prove the `update()` reproduces the cap behavior exactly (it almost certainly does not). Document as exception.
- `bounty_system` — called via `check_claims()` + `cleanup()` with HUD-message side effects. Has `update(ctx)` but it is not equivalent to the claim/HUD logic. Leave bespoke, document.
- `poi_interaction_system` — two bespoke methods (`tick_cooldowns`, `check_interactions`). Leave bespoke, document.

**Conclusion you should expect:** the only systems safe to drive through the runner this sprint are the ones already called via `update(ctx, dt)` *and* with no surrounding post-processing — i.e. `buff_system` and `wave_event_system`. That is a small but real win and it establishes the pattern. Do not force-migrate the others; correctness beats line count. If your audit finds more that are genuinely equivalent, include them — but the burden of proof is on the diff.

### Task 2 — widen `SystemContext`

Edit `game/systems/protocol.py`. Append new fields **with defaults** (defaults are mandatory — existing construction sites and tests build `SystemContext` positionally with the original 6 fields and must keep working):

```python
"""
Shared protocol and context contract for tick-driven systems.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from game.events import EventBus


@dataclass
class SystemContext:
    heroes: list
    enemies: list
    buildings: list
    world: object
    economy: object
    event_bus: EventBus
    # WK64 (audit item 22): widened so all systems can share one context instead
    # of bespoke tick() signatures. All new fields are defaulted so existing
    # SystemContext(...) call sites and tests keep working unchanged.
    peasants: list = field(default_factory=list)
    guards: list = field(default_factory=list)
    bounties: list = field(default_factory=list)
    pois: list = field(default_factory=list)
    rubble_records: list = field(default_factory=list)
    lairs: list = field(default_factory=list)
    castle: object | None = None


class GameSystem(Protocol):
    def update(self, ctx: SystemContext, dt: float) -> None:
        ...
```

### Task 3 — populate the new fields in `SimEngine._build_system_context()`

Edit `_build_system_context()` (~line 342). Populate the new fields from the sim's existing data. Use `getattr` for anything that may be absent in some construction paths:

```python
def _build_system_context(self) -> SystemContext:
    castle = next(
        (b for b in self.buildings if getattr(b, "building_type", None) == "castle"),
        None,
    )
    return SystemContext(
        heroes=self.heroes,
        enemies=self.enemies,
        buildings=self.buildings,
        world=self.world,
        economy=self.economy,
        event_bus=self.event_bus,
        peasants=self.peasants,
        guards=self.guards,
        bounties=self.bounty_system.get_unclaimed_bounties(),
        pois=list(getattr(self, "pois", []) or []),
        rubble_records=list(getattr(self, "rubble_records", []) or []),
        lairs=list(getattr(self.lair_system, "lairs", []) or []),
        castle=castle,
    )
```

**Note on `bounties`:** `get_unclaimed_bounties()` returns a fresh list each call; that's fine for read-only system use. Do not have systems mutate `ctx.bounties` expecting it to write back to the bounty system this sprint.

### Task 4 — create `game/sim/system_runner.py`

```python
"""Ordered system runner (WK64, audit item 22).

Drives a fixed-order tuple of game systems through the shared SystemContext +
``update(ctx, dt)`` protocol. Only systems whose ``update`` is proven equivalent
to their previous bespoke call live here; systems with surrounding orchestration
(combat event routing, spawn capping, bounty/HUD side effects, nature tile
bookkeeping, POI's two-method tick) remain called directly in SimEngine.update()
and are documented exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from game.systems.protocol import GameSystem, SystemContext


@dataclass(slots=True)
class SystemRunner:
    systems: Sequence[GameSystem]

    def update_all(self, ctx: SystemContext, dt: float) -> None:
        for system in self.systems:
            system.update(ctx, dt)
```

### Task 5 — wire the runner into `SimEngine`

In `SimEngine.__init__` (after the systems it will hold are constructed — i.e. after `self.buff_system` / `self.wave_event_system` exist, ~line 115+), build the runner. **Use the exact membership your Task-1 audit proved equivalent** (expected: buff + wave_event, in their current relative order):

```python
from game.sim.system_runner import SystemRunner
# WK64: only proven fire-and-forget update(ctx,dt) systems. See system_runner.py
# docstring + wk64 plan Gate 2 for the documented exceptions kept bespoke.
self._ordered_systems = SystemRunner((self.buff_system, self.wave_event_system))
```

Then, in `SimEngine.update()`, **replace the individual `.update(system_ctx, dt)` calls for exactly those systems with one `update_all` call placed at the same point in the sequence the LAST of them currently occupies — but only if their current call sites are adjacent or order-equivalent.**

Look at the current order: `buff_system.update` is at ~line 668 (early, after fog), `wave_event_system.update` is at ~line 720 (later, before separation). They are **not adjacent**, and other logic runs between them. **Do not reorder gameplay.** Therefore, for THIS sprint, choose the conservative wiring:

- Keep each system's call at its current position, but route it through the runner one system at a time is pointless. Instead, the honest minimal change is: introduce the `SystemRunner` abstraction and the widened context (the real structural win), and have the runner hold the candidate systems, but **only collapse calls that are genuinely adjacent**. If buff and wave_event are not adjacent, keep them as direct `self.buff_system.update(system_ctx, dt)` / `self.wave_event_system.update(system_ctx, dt)` calls for now and document that the runner is seeded for future adjacency-driven consolidation.

**Decision rule for Agent 05:** Preserve the exact current execution order at all costs. If collapsing into `update_all` would change the order of any side-effecting work, DO NOT collapse — leave the direct calls and note it. The deliverables that matter and are non-negotiable are: (a) widened `SystemContext` populated correctly, (b) the `SystemRunner` class exists and is constructed, (c) the equivalence-audit table in your report. Collapsing call sites is a bonus only where provably order-safe.

> Rationale I want you to internalize: this codebase is in active playtest tuning. A subtle reordering of when buffs vs. wave events vs. separation run can change combat outcomes and break determinism. The structural scaffolding (context + runner) is the durable value; aggressive call-site collapsing is not worth a gameplay regression. When in doubt, keep the order and document.

### Verification (Wave 1B)

```powershell
python -m pytest tests/test_wk64_system_runner.py -x -v
python -m pytest tests/ -x -q
python tools/determinism_guard.py
python tools/qa_smoke.py --quick
```

Acceptance:
- `SystemContext` has all 7 new fields, each defaulted; `test_system_context_has_core_fields_today` still passes.
- `_build_system_context()` populates them (spot-check by importing and printing field values from a headless engine in a scratch `python -c`).
- `SystemRunner` exists and is constructed in `SimEngine.__init__`.
- `determinism_guard.py` PASSES (proves you did not reorder side effects).
- Full suite + qa_smoke green.

**DO NOT COMMIT.** Report results, the equivalence-audit table, and the final runner membership, then stop.

---

## Gate 1 — Agent 11 verifies Wave 1

**Owner:** Agent 11 · **Intelligence:** MEDIUM

```powershell
python -m pytest tests/ -x -q
python tools/determinism_guard.py
python tools/qa_smoke.py --quick
```

Grep-verify:
- `ai/contracts.py` exists; `TargetType` has 13 members; `HeroTask`, `coerce_task`, `assign_hero_task` are defined.
- `SystemContext` includes `peasants`, `guards`, `bounties`, `pois`, `rubble_records`, `lairs`, `castle`.
- `game/sim/system_runner.py` exists and `SystemRunner` is referenced in `game/sim_engine.py`.
- No behavior file (`ai/behaviors/**`, `bounty_pursuit.py`) was modified in Wave 1 (those belong to Wave 2).

If anything fails, return the failing output to the PM. Do not fix it yourself.

---

## Wave 2 — Extract arrival handlers + convert hunger & shopping (Agent 06)

**Owner:** Agent 06 (AI) · **Intelligence:** HIGH (subtle behavior-preserving refactor)

### Overview

Two coupled changes:
1. Create `ai/arrival_handlers.py` — a `TargetType`-keyed registry of arrival handlers extracted from `bounty_pursuit.handle_moving()`'s reached-destination block.
2. Convert `hunger.py` and `shopping.py` to author their tasks via `HeroTask` + `assign_hero_task` (the live-conversion proof). All other behaviors keep emitting dicts.

**This must be behavior-preserving.** The Wave-0 characterization tests are your contract: they must stay green.

**Files you may create:** `ai/arrival_handlers.py`
**Files you may edit:** `ai/behaviors/bounty_pursuit.py`, `ai/behaviors/hunger.py`, `ai/behaviors/shopping.py`, `ai/basic_ai.py` (only if a delegation line needs touching — likely not).
**Files you must NOT edit:** `game/sim_engine.py`, `game/systems/**`, `game/engine.py`, `ai/contracts.py` (it's done), `game/entities/**`.

### Background: what `handle_moving` does today

Read `ai/behaviors/bounty_pursuit.py::handle_moving` (lines 281–586) in full first. Its structure:
1. `_seed_direct_prompt_explore_bearing(hero)` — keep.
2. **En-route** bounty claim/abandon while walking (lines 287–359) — keep in `bounty_pursuit.py`. NOT arrival.
3. **Reached-destination dispatch** (lines 361–542): `if hero.target_position:` then `if dist <= TILE_SIZE * 1.5:` then a long if/elif over `hero.target` dict `type` / direct-prompt sub-intents. **THIS block moves to `arrival_handlers.py`.**
4. **Combat re-engage gating** (lines 544–585) — keep in `bounty_pursuit.py`. NOT arrival.

So you are extracting **only** the reached-destination dispatch (step 3), and only the parts of it keyed by the task types `direct_prompt`, `visit_poi`, `going_home`, `shopping`, `rest_inn`, `buy_meal`, `get_drink`. The `bounty` arrival (the claim logic) stays in `bounty_pursuit.py` because it is interleaved with the en-route walk logic (step 2) and is the file's actual job.

### Task 1 — create `ai/arrival_handlers.py`

Each handler has the signature `(ai, hero, task: HeroTask, game_state) -> bool` and returns `True` if it fully handled the arrival (caller should `return`). Move the existing code blocks verbatim into the matching handler — **do not rewrite the logic**, only relocate it and read the task via the typed view where convenient. Example skeleton (fill every handler from the real code):

```python
"""Arrival handler registry (WK64, audit item 17).

Extracted from ``bounty_pursuit.handle_moving``'s reached-destination dispatch.
Each handler runs when a hero reaches its task waypoint. Handlers return True
when they fully handle the arrival (caller then returns).

Dispatch is keyed by TargetType via ARRIVAL_HANDLERS. The 'bounty' arrival stays
in bounty_pursuit.py because it is interleaved with en-route claim/abandon logic.
"""

from __future__ import annotations

from typing import Any, Callable

from ai.contracts import HeroTask, TargetType, coerce_task
# ... import the same helpers the old code used: HeroState, get_rng,
#     roll_duration_seconds, resolve_explore_direction_target,
#     _find_safety_building_for_arrival, _pick_building_at_arrival,
#     _clear_direct_prompt_explore_meta, _compass_from_vec, DIRECT_PROMPT_TARGET_TYPE, etc.
#     Some of these are module-private in bounty_pursuit.py -- see Task 2 for how to share them.


def handle_buy_meal_arrival(ai: Any, hero: Any, task: HeroTask, game_state: dict) -> bool:
    # Delegates to the hunger behavior, exactly as the old code did (bounty_pursuit.py:521-524).
    hunger_behavior = getattr(ai, "hunger_behavior", None)
    if hunger_behavior is not None and hunger_behavior.handle_meal_arrival(ai, hero, game_state):
        return True
    return False


def handle_shopping_arrival(ai: Any, hero: Any, task: HeroTask, game_state: dict) -> bool:
    # Move lines 488-505 here verbatim, but read keys from task.payload (which
    # equals the old dict keys): task.payload.get("marketplace"), etc.
    ...
    return True


# ... handle_rest_inn_arrival, handle_get_drink_arrival, handle_going_home_arrival,
#     handle_visit_poi_arrival, handle_direct_prompt_arrival (with all its sub_intents)


ARRIVAL_HANDLERS: dict[TargetType, Callable[[Any, Any, HeroTask, dict], bool]] = {
    TargetType.DIRECT_PROMPT: handle_direct_prompt_arrival,
    TargetType.VISIT_POI: handle_visit_poi_arrival,
    TargetType.GOING_HOME: handle_going_home_arrival,
    TargetType.SHOPPING: handle_shopping_arrival,
    TargetType.REST_INN: handle_rest_inn_arrival,
    TargetType.BUY_MEAL: handle_buy_meal_arrival,
    TargetType.GET_DRINK: handle_get_drink_arrival,
}


def dispatch_arrival(ai: Any, hero: Any, game_state: dict) -> bool:
    """Look up and run the arrival handler for the hero's current task.

    Returns True if a handler ran and handled it. Returns False if there is no
    task, no matching handler, or the target is a live entity (combat) -- in
    which case the caller falls through to its default 'arrived, go IDLE' logic.
    """
    task = coerce_task(getattr(hero, "target", None))
    if task is None:
        return False
    handler = ARRIVAL_HANDLERS.get(task.type)
    if handler is None:
        return False
    return handler(ai, hero, task, game_state)
```

**On sharing the private helpers:** `handle_direct_prompt_arrival` needs `_find_safety_building_for_arrival`, `_pick_building_at_arrival`, `_clear_direct_prompt_explore_meta`, `_compass_from_vec`, the explore-extension constants, etc. Two acceptable approaches — pick the lower-risk one:
- **(Preferred)** Move those helper functions from `bounty_pursuit.py` into `arrival_handlers.py` (since the direct-prompt arrival logic is moving there anyway), and have `bounty_pursuit.py` import any it still needs from `arrival_handlers`. Check what `bounty_pursuit.py` still uses after extraction (`_seed_direct_prompt_explore_bearing` uses `DIRECT_PROMPT_TARGET_TYPE` only; the combat-gating section uses none of them).
- **(Fallback)** Keep the helpers in `bounty_pursuit.py` and import them into `arrival_handlers.py`. Risk: a future circular import if `bounty_pursuit` imports from `arrival_handlers`. The preferred approach avoids this because the dependency points one way (`bounty_pursuit` → `arrival_handlers`).

Whichever you choose, ensure no circular import: `arrival_handlers` may import from `ai.contracts` and `game.*`; `bounty_pursuit` imports from `arrival_handlers`, never the reverse.

### Task 2 — slim down `bounty_pursuit.handle_moving`

Replace the reached-destination dispatch block (lines 361–542) with a call to `dispatch_arrival`. The new shape of that block:

```python
    # Check if reached destination.
    if hero.target_position:
        dist = hero.distance_to(hero.target_position[0], hero.target_position[1])
        if dist <= TILE_SIZE * 1.5:
            # WK64: arrival dispatch extracted to ai/arrival_handlers.py.
            from ai.arrival_handlers import dispatch_arrival
            if dispatch_arrival(ai, hero, game_state):
                return
            # Default: arrived with no special handler -> go idle.
            hero.target_position = None
            hero.state = HeroState.IDLE
            return
```

**Be careful with the bounty arrival:** the bounty claim logic (lines 287–359) runs BEFORE the `if hero.target_position:` block and already `return`s on claim/abandon/timeout. It is NOT part of the extracted block, so leave it exactly where it is. The extracted block was everything from line 361 (`# Check if reached destination.`) through line 542 (the final `hero.state = HeroState.IDLE; return`). Verify by diffing against the Wave-0 characterization tests.

**Edge case to preserve:** in the old code, when `hero.target` is a dict whose `type` is `bounty` and we reach the `if hero.target_position:` block (rare, since bounty usually returns earlier), the old fall-through set IDLE. With `dispatch_arrival`, `coerce_task` returns a `BOUNTY` task but there is no `BOUNTY` handler in the registry, so `dispatch_arrival` returns `False` and the caller falls through to "go idle" — **same behavior.** Good. Confirm this with a quick reasoning check, and if unsure, add a Wave-0 test for it.

### Task 3 — convert `hunger.py` to author via HeroTask

In `ai/behaviors/hunger.py`, the only place that constructs the target is `go_to_food_stand` (line 92):

```python
# OLD:
hero.target = {"type": "buy_meal", "food_stand": food_stand}

# NEW:
from ai.contracts import HeroTask, TargetType, assign_hero_task
task = HeroTask(type=TargetType.BUY_MEAL, target_ref=food_stand, payload={"food_stand": food_stand})
assign_hero_task(hero, task)
```

`to_dict()` produces `{"type": "buy_meal", "food_stand": food_stand}` — byte-for-byte the same dict the old code stored. Every reader (`handle_meal_arrival`, `maybe_redirect_for_meal`'s `target.get("type")`, etc.) keeps working. Leave `handle_meal_arrival` reading the dict (`target.get("food_stand")`) — it still receives a dict.

Put the import at the top of the file with the other imports, not inside the function.

### Task 4 — convert `shopping.py` to author via HeroTask

In `ai/behaviors/shopping.py`, `go_shopping` (lines 62–68):

```python
# OLD:
hero.target = {
    "type": "shopping",
    "item": item_name,
    "marketplace": target_building if target_building.building_type == "marketplace" else None,
    "blacksmith": target_building if target_building.building_type == "blacksmith" else None,
    "shop_building": target_building,
}

# NEW:
from ai.contracts import HeroTask, TargetType, assign_hero_task
task = HeroTask(
    type=TargetType.SHOPPING,
    target_ref=target_building,
    payload={
        "item": item_name,
        "marketplace": target_building if target_building.building_type == "marketplace" else None,
        "blacksmith": target_building if target_building.building_type == "blacksmith" else None,
        "shop_building": target_building,
    },
)
assign_hero_task(hero, task)
```

`to_dict()` reproduces the identical dict, so `handle_shopping_arrival` (which reads `marketplace`/`blacksmith`) is unaffected.

> Note: `exploration.py` also creates `{"type": "shopping", ...}` dicts (lines 230, 253) — **leave those as dicts** this sprint. Only `shopping.py` and `hunger.py` are converted. The point is to prove the typed path works in production for two behaviors, not to convert everything. Other behaviors interoperate fine because the registry consumes via `coerce_task`, which reads either form.

### Verification (Wave 2)

```powershell
python -m pytest tests/test_wk64_ai_contracts.py -x -v
python -m pytest tests/test_ai_shopping.py tests/test_ai_bounty.py tests/test_ai_exploration.py tests/test_ai_poi_awareness.py tests/test_wk61_r10_hunger_ai.py tests/test_wk61_r11_hunger_live_path.py tests/test_bounty.py tests/test_combat.py -x -v
python -m pytest tests/ -x -q
python tools/determinism_guard.py
python tools/qa_smoke.py --quick
```

Acceptance:
- All Wave-0 characterization tests still PASS (behavior preserved).
- All existing AI/hunger/shopping/bounty tests PASS.
- `determinism_guard.py` PASSES.
- `bounty_pursuit.py` is meaningfully shorter; the arrival dispatch lives in `arrival_handlers.py`.
- `hunger.py` and `shopping.py` import and use `HeroTask` + `assign_hero_task`.

**DO NOT COMMIT.** Report results and stop.

---

## Gate 2 — Final verification (Agent 11 + Agent 04)

### Agent 11 — regression + visual (Intelligence: MEDIUM)

```powershell
python -m pytest tests/ -x -q
python tools/determinism_guard.py
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report
```

**Screenshot verification (REQUIRED — hero shopping/eating is visible behavior).**
Capture a base-overview run long enough for heroes to shop and eat, both before (from the committed WK63 baseline) and after WK64, and compare:

```powershell
python tools/capture_screenshots.py --scenario base_overview --seed 3 --out docs/screenshots/wk64_ai_contracts_after --size 1920x1080 --ticks 600
```

Then VIEW the captured PNGs and give an explicit visual verdict against this checklist (do not rubber-stamp):
1. Heroes still path to and enter marketplaces/food stands (look for heroes clustered at/inside shop buildings, "shopping" intent labels).
2. No heroes frozen at a building entrance or oscillating in place (would indicate a broken arrival handler).
3. HP/intent labels render normally; no heroes stuck in MOVING with no destination.
4. Compare against the committed WK63 baseline screenshots — overall scene composition (unit counts, building states) should be equivalent at the same seed/ticks.

If the `base_overview` scenario does not reliably produce shopping/eating at seed 3, list the alternative observe scenario you used and why. Report the verdict with the screenshot paths inline.

Grep-verify:
- `ai/arrival_handlers.py` exists; `ARRIVAL_HANDLERS` maps at least the 7 task types; `dispatch_arrival` is called from `bounty_pursuit.py`.
- `hunger.py` and `shopping.py` reference `assign_hero_task`.
- `hero.target` is never assigned a `HeroTask` object anywhere (grep for `hero.target = HeroTask` / `\.target = task\b` and confirm only `assign_hero_task` is used). This protects the critical design rule.

### Agent 04 — determinism (Intelligence: LOW)

```powershell
python tools/determinism_guard.py
```
- Confirm the system-runner change did not reorder side effects (the guard catches divergence).
- Confirm no wall-clock or `id(obj)` ordering crept into the new arrival registry (dispatch is keyed by `TargetType`, deterministic).
- Review Agent 05's equivalence-audit table and confirm the runner membership matches it.

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Storing a `HeroTask` object on `hero.target` breaks ~30 `isinstance(dict)` readers | `assign_hero_task` always stores `to_dict()`; Gate 2 greps for any direct `HeroTask` assignment |
| Arrival extraction subtly changes behavior | Wave-0 characterization tests pin each arrival type; they must stay green |
| Circular import between `bounty_pursuit` and `arrival_handlers` | One-way dependency: `bounty_pursuit` → `arrival_handlers` only; helpers move *into* `arrival_handlers` |
| System-runner reorders gameplay side effects → determinism break | Agent 05 preserves exact order; only collapses provably-adjacent calls; `determinism_guard` gates |
| `SystemContext` new fields break positional construction in tests/tools | All new fields are defaulted; Wave-0 `test_system_context_has_core_fields_today` guards core shape |
| WK63 pathfinding budget starves paths → heroes stuck / no bounty response | **Phase A** fixes it (defer instead of `[]`); gated by qa_smoke 0.25x + 30-hero stuck-events check before the baseline commit |
| Phase A defer change keeps a *stale* path too long | Heroes still replan when path empties or the goal tile changes; on defer they retry next frame (no rate-limit stamp), so a fresh path lands within a frame or two |
| Phase A only band-aids via caps | Step A3's 30-hero/1.0x stuck-events gate proves the defer logic (not the caps) carries the fix |
| Converting only 2 behaviors leaves mixed dict/HeroTask world | Intentional; `coerce_task` consumes both forms; documented as expected interop |

## Sprint Success Criteria

- [ ] **Phase A:** `compute_path_worldpoints` returns `None` on budget exhaustion; callers keep their path on defer; path-less heroes direct-steer on defer (A2.1); `qa_smoke --quick` green incl. `speed_scaling 0.25x`; 30-hero/1.0x `stuck_events` ≤ 30 (≈27 crowding baseline); WK63 + fix committed as the baseline.
- [ ] `python -m pytest tests/ -x -q` PASS
- [ ] `python tools/determinism_guard.py` PASS
- [ ] `python tools/qa_smoke.py --quick` PASS
- [ ] `ai/contracts.py`: `TargetType` (13), `HeroTask`, `to_dict`/`from_dict`/`coerce_task`/`assign_hero_task`
- [ ] `ai/arrival_handlers.py`: registry + `dispatch_arrival`; `bounty_pursuit.handle_moving` delegates
- [ ] hunger + shopping author via `HeroTask`; `hero.target` still a dict everywhere
- [ ] `SystemContext` widened (7 new defaulted fields), populated in `_build_system_context()`
- [ ] `SystemRunner` exists, constructed in `SimEngine`, membership = proven-equivalent systems only
- [ ] Agent 05 equivalence-audit table delivered; documented exceptions listed
- [ ] Gate-2 screenshots show no visible hero-behavior regression

---

## Follow-Up Backlog After This Sprint

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 18 | Replace `BasicAI` priority ladder with task router | P2 | Now unblocked by `HeroTask` + arrival handlers |
| 15+ | Convert remaining behaviors (bounty, direct_prompt, POI, defense, journey) to `HeroTask` | P2 | Incremental; `coerce_task` already bridges |
| 22+ | Migrate more systems into `SystemRunner` as their `update(ctx)` is proven equivalent | P2 | Combat needs event-routing redesign first |
| 12 | Split `SimEngine` into services | P1 | Builds on widened `SystemContext` + runner |
| 6 | Split snapshot into sim/presentation/UI DTOs | P1 | Builds on SelectionState + FrameContext |
| 19 | Split LLM context into JSON slices | P2 | Independent |
| 20 | Split `Hero` into services | P2 | After AI contracts stabilize |
| 21 | Centralize attacks and projectile events | P2 | Combat event routing; unblocks more runner migration |
| 8+ / 9+ | Deeper HUD / UrsinaRenderer splits | P1 | Continues WK62 work |
| 13 / 14 / 16 | Building / visual-spec / audio+prefab registries | P2 | Independent |
| 24–29 | Perf caching (panels, chat, VFX, flipped frames, path pop(0)) | P2 | Small items, batchable |
| 30–33 | Tool splits, test reorg, orchestrator refactor, docs | P3 | Lowest urgency |
