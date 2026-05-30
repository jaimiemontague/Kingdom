# WK69 Sprint Plan — Round B-1: SimEngine decomposition (Moves 7 + 8)

**Author:** Agent 01 (ExecutiveProducer_PM)
**Date:** 2026-05-30
**Sprint goal (DoD gate):** all tests pass; `sim_engine.py` shrinks substantially by extracting its inlined services into `game/sim/` modules behind **delegating wrappers**; behavior byte-identical (WK67 AI-decision digest `b73961…` unchanged).
**Predecessor:** WK68 (Round A complete — boundary chain killed L1/L2/L6/L9/L10).
**Roadmap:** Round B (god-file splits, Moves 7-9 + presentation splits). This is **Round B-1: the sim-engine half.** Defers Move 9 (grow `SystemRunner`) and all presentation splits to WK70+.
**Reference docs:** `.cursor/plans/GPT 5.5 Codebase Improvements Recommendations.md` (§"Oversized-file blueprints" → sim_engine.py 7-module split; Moves 7-9), `.cursor/plans/codebase_audit_2026-05-28_finding_inventory.md` (sim-engine area).

---

## 0. TL;DR for the next Agent 01 (your replacement PM)

`game/sim_engine.py` is a 1527-LOC god-module that mixes orchestration with fog-of-war, entity separation, the tree/lumber economy, POI discovery, building destruction/cleanup, and early-pacing. WK69 **extracts those five inlined services into focused `game/sim/` modules**, leaving `SimEngine` a thinner orchestrator. The split is a **mechanical move behind delegating wrappers**: each extracted module exposes a free function that takes the live `SimEngine` (`sim`) and does exactly what the method did; the original method on `SimEngine` becomes a one-line `return module.fn(self, …)` shim so every caller and test keeps working **unchanged**.

**This is behavior-preserving.** No gameplay, no rendering, no AI change. The keystone guardrail is the same as WK66-68: **the WK67 AI-decision digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` MUST stay byte-identical** after every extraction. No screenshots are needed (no render change) — verification is the full suite + determinism_guard + the digest + qa_smoke.

**You (PM) write no code.** Dispatch role-onboarded `claude-opus-4-8` subagents, gate each wave (run the digest + suite yourself), loop fixes.

---

## 1. Why this sprint

The audit's #2 structural problem is "files are too large," and `sim_engine.py` is the second-worst god-file (after the UI/render ones). It carries the sim's *authoritative state* AND six unrelated services inline, so every gameplay change risks the whole sim. Round A made the sim's *outputs* clean (typed DTOs/views); Round B makes the sim's *internals* navigable. Extracting the services:
- Shrinks `sim_engine.py` toward the audit's ~700-LOC orchestrator target.
- Makes each service independently readable/testable (fog, lumber, separation, etc.).
- Is the safest possible refactor: a pure move guarded by a deterministic digest and a green suite.
- Unblocks Move 9 (growing `SystemRunner` into the real ordered pipeline) in a later sprint, because the services it will sequence now exist as discrete units.

We do the **sim side first** (this sprint) because it needs no screenshots and is guarded by the strongest net we have (the digest). The presentation god-file splits (hud.py, ursina_renderer.py, …) are screenshot-heavy and come in WK70+.

---

## 2. Scope — IN and OUT

**IN (WK69) — extract these 5 services from `game/sim_engine.py` into `game/sim/` modules behind delegating wrappers:**

| Service | Methods to move (current line ranges) | New module |
|---|---|---|
| **Fog of war** | `_update_fog_of_war` (1379-1510) + its inner `_tile_currently_visible` helper | `game/sim/fog.py` |
| **Entity separation** | `_apply_entity_separation` (1200-1269) | `game/sim/separation.py` |
| **Lumber/tree economy** | `chop_tree_at` (753-789), `harvest_log_at` (790-805), `find_nearest_choppable_tree_for_builder` (700-752), `_wood_yield_for_growth` (690-699), `remove_trees_in_footprint` (267-306), `_init_trees_from_world` (248-262), `_tree_growth_lookup` (263-266) | `game/sim/lumber.py` |
| **POI discovery** | `_check_poi_discovery` (1019-1059) | `game/sim/poi_discovery.py` |
| **Early pacing** | `_maybe_apply_early_pacing_nudge` (1318-1362) + `_nearest_lair_to` (1363-1378) | `game/sim/early_pacing.py` |
| **Building lifecycle (Move 7 core)** | `_cleanup_destroyed_buildings` (1060-1154) | `game/sim/building_lifecycle.py` |

**OUT (deferred — do NOT do these here):**
- **Move 9 — grow `SystemRunner` to the real ordered pipeline.** Risky side-effect reorder; the audit warns "Don't reorder `SimEngine.update()` side effects." → WK70.
- **Extracting `build_snapshot` → `snapshot_builder.py`.** It was just heavily rewritten in WK68 (DTOs); leave it stable one more sprint. → WK70.
- **Extracting `_update_buildings` → `building_tick.py` / fixing the stringly-typed building dispatch.** That's a behavior-shaping change (Move per buildings area), not a pure move. → Round B-2 / Round C.
- **Retiring the `CleanupManager` parallel path** (the rest of Move 7). WK69 only extracts `_cleanup_destroyed_buildings` behind a shim; collapsing the two destruction paths is a follow-up. → WK70.
- **The `_build_system_context` / `get_game_state` / `update` orchestration bodies.** Leave the orchestrator methods in place; only the 6 services move.
- All presentation/UI/AI/tool files. This sprint touches **only** `game/sim_engine.py` and the new `game/sim/*.py` modules (+ tests).

---

## 3. Definition of Done

- **A.** `python -m pytest` → all pass (baseline **618 passed / 4 skipped / 0 failed**; any new characterization tests add to "passed").
- **B.** `python tools/determinism_guard.py` → clean.
- **C.** WK67 AI-decision digest **byte-identical** = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` (verify after EVERY extraction, not just at the end).
- **D.** `python tools/qa_smoke.py --quick` → green.
- **E.** Each of the 5 new modules exists under `game/sim/`, and `sim_engine.py` is materially smaller (target: from 1527 LOC down toward ~1050-1100 — i.e. ~400-450 LOC moved out). The 6 method names still exist on `SimEngine` as **one-line delegating wrappers** (so external callers + tests that reference `sim._update_fog_of_war` / `sim._apply_entity_separation` / `sim.chop_tree_at` / `sim._cleanup_destroyed_buildings` keep working).
- **F.** No new `import` cycles (the new `game/sim/*` modules import from `game/` leaf modules, never from `sim_engine` at module top — they take `sim` as a parameter; see §5).
- **G.** Each participating agent updated its own department log; PM hub records the close.

---

## 4. Critical design rules

1. **Mechanical move, pass `sim`.** Each extracted function takes the live `SimEngine` instance as its first parameter and reads/writes `sim.world`, `sim.heroes`, `sim.buildings`, etc. **exactly as the method did via `self`.** Do NOT "improve" the signature to explicit inputs this sprint — a pure move minimizes risk and keeps the digest identical. (Purity/explicit-inputs is a later polish.)
2. **Keep a delegating wrapper for every moved method.** Tests and internal callers reference these by name. Example below (§5). Do not delete or rename the `SimEngine` methods — turn each into a 1-line shim.
3. **Preserve order and call sites.** `SimEngine.update()` (806-1018) still calls `self._update_fog_of_war()`, `self._apply_entity_separation(dt)`, `self._check_poi_discovery()`, `self._cleanup_destroyed_buildings()`, `self._maybe_apply_early_pacing_nudge(...)` in the SAME order, at the SAME points. You're only changing what those methods' BODIES live in, never when they run.
4. **No import cycles.** The new modules must not `import game.sim_engine` at top level. They take `sim` as a parameter (duck-typed) and import only the leaf helpers the original code used (e.g. `from game.systems... import ...`, `from game.sim.timebase import now_ms`). If a type hint needs `SimEngine`, use `from __future__ import annotations` + a `TYPE_CHECKING` import.
5. **Determinism is sacred.** No change to iteration order, RNG call order, or `now_ms()` usage. Verify the digest after EACH extraction so a regression is caught at the exact module that caused it.
6. **One file, sequential.** All six extractions edit `sim_engine.py`, so they are done **sequentially by one agent (03)** in two gated batches — never in parallel (parallel edits to `sim_engine.py` would collide).

---

## 5. The extraction pattern (uniform — give this to Agent 03 verbatim)

For each service, e.g. fog:

**Before** (`game/sim_engine.py`):
```python
class SimEngine:
    ...
    def _update_fog_of_war(self) -> None:
        # ~130 lines reading self.world, self.heroes, self.buildings, ...
        ...
```

**After** — new `game/sim/fog.py`:
```python
"""WK69 Round B-1: fog-of-war service extracted from SimEngine (behavior-preserving move).

Takes the live SimEngine as ``sim`` and reads/writes its state exactly as the
former ``SimEngine._update_fog_of_war`` method did. SimEngine keeps a one-line
delegating wrapper so callers/tests are unchanged.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
# ... the SAME leaf imports the method used ...
if TYPE_CHECKING:
    from game.sim_engine import SimEngine


def update_fog_of_war(sim: "SimEngine") -> None:
    # EXACT body of the old method, with every `self.` replaced by `sim.`,
    # including the inner `_tile_currently_visible` helper (keep it nested or
    # make it a module-private `_tile_currently_visible(sim, gx, gy)`).
    ...
```

**After** — `game/sim_engine.py` (the wrapper stays):
```python
    def _update_fog_of_war(self) -> None:
        from game.sim import fog
        fog.update_fog_of_war(self)
```
(Import inside the wrapper, or at module top if no cycle — top is fine since `game.sim.fog` doesn't import `sim_engine` at module level. Prefer a top-level `from game.sim import fog, separation, lumber, poi_discovery, early_pacing, building_lifecycle` once it's verified cycle-free.)

**Notes per service:**
- **lumber.py** holds the whole tree/log cluster. `_init_trees_from_world` and `_tree_growth_lookup` are called from `setup_initial_state` / construction — keep their wrappers. `chop_tree_at` / `harvest_log_at` are called by `game/entities/builder_peasant.py` via the typed `LumberOps` accessor (WK67) — verify that path still resolves (the `lumber_ops` property at 575 and `find_hero_by_id` stay on SimEngine; only the tree methods move).
- **building_lifecycle.py** (`_cleanup_destroyed_buildings`): this emits HUD messages + events and clears references. Move the body; keep the wrapper. Do NOT also touch `CleanupManager` (deferred).
- **early_pacing.py**: `_maybe_apply_early_pacing_nudge` takes `(dt, castle)`; `_nearest_lair_to` takes `(x, y)`. Both move together (the nudge calls the nearest-lair helper). Wrappers: `def _maybe_apply_early_pacing_nudge(self, dt, castle): return early_pacing.maybe_apply_early_pacing_nudge(self, dt, castle)`.
- **fog.py**: the inner `_tile_currently_visible` closure (1511) must move with it.

---

## 6. Waves

```
W1 (Agent 03): extract fog + separation + lumber  → gate (PM: digest + suite)
W2 (Agent 03): extract poi_discovery + early_pacing + building_lifecycle → gate
W3 (Agent 11): characterization-test sweep + final DoD gate (suite + digest + determinism + qa_smoke + LOC check)
   (Agent 05 GameplaySystems: on-call consult for fog/lumber/poi semantics if a digest drift appears)
```

- **W1 and W2 are sequential** (same file). After W1, PM runs the digest + suite before W2.
- **W3** runs after W2. Agent 11 confirms the existing sim characterization tests still pass and adds a light "module exists + wrapper delegates" test per service if useful, then runs the full DoD gate.

---

## 7. Per-wave tasks

### Wave W1 — extract fog, separation, lumber (Agent 03)
- Create `game/sim/fog.py`, `game/sim/separation.py`, `game/sim/lumber.py` per the §5 pattern.
- Move the bodies; replace `self.` → `sim.`; leave 1-line delegating wrappers on `SimEngine`.
- Verify after EACH of the three: `python -m pytest tests/test_wk67_ai_boundary.py -q` (digest `b73961…`), then after all three: `python -m pytest -q` + `python tools/determinism_guard.py`.
- Report: new files, the wrapper diffs, LOC removed from sim_engine.py, digest value, suite totals.

### Wave W2 — extract poi_discovery, early_pacing, building_lifecycle (Agent 03, after W1 gated)
- Create `game/sim/poi_discovery.py`, `game/sim/early_pacing.py`, `game/sim/building_lifecycle.py`.
- Same pattern + wrappers. `_cleanup_destroyed_buildings` keeps emitting the same HUD messages/events (it's behavior-sensitive — verify the digest is unchanged, since destruction affects sim state).
- Verify the digest after each; full suite + determinism_guard + qa_smoke at the end.
- Report same shape as W1, plus the final `sim_engine.py` LOC.

### Wave W3 — verification sweep (Agent 11)
- Confirm the sim characterization tests (test_wk65_*characterization*, test_wk67_ai_boundary digest, snapshot/contract tests) all pass.
- Optionally add `tests/test_wk69_simengine_extraction.py`: for each service, assert the new module's function exists and that `SimEngine.<wrapper>` delegates to it (e.g. monkeypatch the module fn, call the wrapper, assert it was invoked) — locks the seam.
- Run the full DoD gate (A-F) and report a one-page verdict to PM: suite totals, digest value, determinism/qa_smoke results, and the sim_engine.py before/after LOC.

---

## 8. Risk assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| A `self.`→`sim.` replacement misses a reference → AttributeError | Med | Per-service digest+suite gate catches it immediately; the move is small per service |
| Import cycle (new module ↔ sim_engine) | Med | Modules take `sim` as a param + `TYPE_CHECKING` import only; wrapper imports the module, not vice-versa (rule §4) |
| Digest drift from a subtle reorder (esp. fog/cleanup, which mutate sim state) | Low-Med | Verify digest after EACH extraction; if it drifts, that single service is the culprit — revert+redo that one |
| Nested helper (`_tile_currently_visible`) lost in the move | Low | Explicitly called out (§5) |
| OneDrive transient file-lock PermissionError during full-suite subprocess runs | Low | Known (WK68); re-run rather than treating as a real failure |

---

## 9. Success criteria (one-liner)

WK69 succeeds when `sim_engine.py` is ~400 LOC lighter, the five services live in their own `game/sim/` modules behind delegating wrappers, and **everything plays byte-identically** — proven by 618+ green tests, a clean determinism guard, and the unchanged `b73961…` digest.

---

## 10. Follow-up backlog (WK70+)

- **Move 9:** grow `SystemRunner` into the real ordered pipeline (fold the now-extracted services into it in fixed order). Deferred (risky reorder).
- **Move 7 remainder:** retire the `CleanupManager` parallel destruction path; have on-demand demolish call `building_lifecycle`.
- Extract `build_snapshot` → `snapshot_builder.py`; `_update_buildings` → `building_tick.py` (data-driven dispatch, kills the stringly-typed ladder).
- **Presentation splits (Round B-2):** `hud.py` (2477) → package; `ursina_renderer.py` (1985) → modules (also delete the dead `_unit_facing_direction` + its import flagged in WK68); `ursina_terrain_fog_collab.py`; `ursina_app.py`; `engine.py`; `hero.py`; `input_handler.py`.
- **Round C:** `BuildingDef` registry (Move 10) + dedup clusters.

---

## 11. Kickoff appendix

**Roster:** 03 TechnicalDirector (W1+W2 extractions, sequential), 11 QA (W3 verification + DoD gate), 05 GameplaySystems (on-call consult for service semantics).
**Dispatch order:** 03 W1 → PM gate (digest+suite) → 03 W2 → PM gate → 11 W3 → PM final gate → commit+push.
**Universal reminders:** onboard via `.cursor/rules` for your agent #; read your PM-hub task + this plan; `claude-opus-4-8`; behavior-preserving — digest `b73961…` must stay byte-identical (verify after each extraction); NO screenshots needed (no render change); update your own department log; **DO NOT COMMIT**; do not iterate after `status=done`.
