# WK119 Round B — resolve Move 9: delete the dead `SystemRunner` wiring

**Author:** Agent 01 (Executive Producer / PM)
**Status:** PLANNED → in execution
**Sprint key (PM hub):** `wk119_round_b_systemrunner_deadwiring`
**Version target:** patch (dead-code removal; behavior-preserving)
**Verification class:** HEADLESS. **WK67-digest-SAFE** (removing never-called code cannot change runtime behavior → digest must stay byte-identical). No screenshots (no UI/render).
**Model for all sub-agents:** `claude-opus-4-8` (opus)

---

## 0. TL;DR + decision rationale

Roadmap **Move 9** ("grow `SystemRunner` to the real ordered pipeline") and the audit's
dead-wiring finding both target `game/sim/system_runner.py`. PM grounding (Explore sweep)
confirmed:
- `SystemRunner` (WK64) is **dead**: `SystemRunner.update_all` is **never called**;
  `self._ordered_systems = SystemRunner((buff_system, wave_event_system))`
  (`game/sim_engine.py:143`) is **constructed but never read**.
- The two held systems are **non-adjacent** in `SimEngine.update()` — `buff_system.update`
  runs at ~L733, `wave_event_system.update` at ~L792, separated by ~6 other update
  phases (pacing, peasants, enemies, guards, spawning). So "growing" the runner into one
  contiguous `update_all` loop **would reorder side effects and break the WK67 digest** —
  the roadmap explicitly warns "Don't reorder `SimEngine.update()` side effects"
  (Recommendations.md:499).

Both the roadmap (line 511: "**delete the dead `SystemRunner` wiring** or actually route
systems through it") and the audit (remedy (a): "delete `_ordered_systems` and the
SystemRunner class **until there is a contiguous run of fire-and-forget systems to host**")
sanction deletion when no safe contiguous run exists — which is the case today. **So WK119
resolves Move 9 by deleting the dead wiring** (digest-safe, removes confirmed slop, closes
the finding). If a future sprint creates a genuine contiguous fire-and-forget run, the
runner can be reintroduced then.

**DO NOT COMMIT** — PM owns the commit.

---

## 1. The change (Agent 05 — single round)

Three edits, all behavior-preserving (removing dead code only):

1. **Delete the file** `game/sim/system_runner.py` (use `git rm game/sim/system_runner.py`).
2. **`game/sim_engine.py:44`** — remove the import line `from game.sim.system_runner import SystemRunner`.
3. **`game/sim_engine.py:134–143`** — remove the WK64 comment block (L134–142) AND the
   construction line `self._ordered_systems = SystemRunner((self.buff_system, self.wave_event_system))`
   (L143). The two systems `self.buff_system` and `self.wave_event_system` are still
   constructed elsewhere and still called directly in `update()` (~L733, ~L792) — leave
   those call sites and the system constructions UNTOUCHED. Only the dead
   `_ordered_systems` aggregation goes.

**Do NOT touch** `SimEngine.update()`'s ordered call sequence in any way — the buff/wave
direct calls stay exactly where they are. This sprint removes ONLY the unused aggregator.

Check for any other reference before finishing:
`grep -rn "SystemRunner\|_ordered_systems\|system_runner\|update_all" game/ tests/ tools/`
— after the edits the ONLY remaining hits allowed are in `tests/test_wk64_system_runner.py`
(its filename + docstring, which is fine) and `.cursor/plans/...` docs. If any PRODUCTION
code still references the removed names, STOP and report.

### `tests/test_wk64_system_runner.py` — light docstring touch only
That test pins the `SystemContext` core fields + that `CombatSystem`/`BuffSystem`/
`WaveEventSystem` expose `update(ctx, dt)` + the 50ms-advance + 120-tick stability — NONE
of which reference `SystemRunner`/`_ordered_systems`/`update_all` in assertions (verified).
So it stays GREEN unchanged. OPTIONAL: update its module docstring line that mentions the
future "Wave-1 ``SystemRunner`` refactor" to note the runner was removed in WK119 (the
characterization pins it still provides remain valid as the SimEngine.update behavior net).
Do NOT change any assertion. If unsure, leave the docstring as-is (harmless).

---

## 2. Verification (Agent 05 — paste raw output; DO NOT COMMIT)

1. `python -c "import game.sim_engine; import game.engine"` → no error (the removed import is gone cleanly).
2. `grep -rn "SystemRunner\|_ordered_systems\|update_all" game/ --include=*.py` → ZERO hits in production code.
3. `python -m pytest -q` → 0 failed (record passed/skipped; expect 1493 passed / 4 skipped — the same as WK118, since nothing behavioral changed).
4. `python tools/determinism_guard.py` → clean PASS.
5. `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q` → digest byte-identical `b73961340c…d148ded`.
6. `python -m pytest tests/test_wk64_system_runner.py -q` → green (the characterization net still passes — proves the SimEngine.update behavior it pins is unchanged).
7. `python tools/qa_smoke.py --quick` → DONE: PASS.

Update the Agent 05 log with the deletion summary + raw verification output.

---

## 3. PM gate + DoD

- [ ] `game/sim/system_runner.py` deleted; the import + `_ordered_systems` construction removed from `sim_engine.py`; the comment block removed.
- [ ] ZERO `SystemRunner`/`_ordered_systems`/`update_all` references remain in production code (grep-proven); buff/wave systems still constructed + called directly at their original `update()` positions (unchanged).
- [ ] full `pytest -q` 0 failed (1493 passed expected — unchanged count); `test_wk64_system_runner.py` green.
- [ ] determinism clean; **WK67 digest byte-identical** (the load-bearing proof that removing the dead aggregator changed nothing).
- [ ] qa_smoke `--quick` DONE: PASS.
- [ ] Agent 05 log updated. PM commits (scoped add/rm: `git rm game/sim/system_runner.py` + `git add game/sim_engine.py` + plan + PM hub + agent log [+ test docstring if touched]) and pushes.

---

## 4. Roadmap status after WK119

With Move 9 resolved, the GPT-5.5 recommendations + audit inventory are **substantially
complete**. Remaining:
- **Move 12 — TaskRouter** (`ai/basic_ai.py update_hero` priority ladder → competitive
  `propose()->TaskProposal` router in `ai/task_router.py`): the LAST roadmap item, rated
  **HIGH risk / determinism-fragile** (the proposal model changes when each behavior runs
  and the `_AI_RNG` draw order, which the WK67 digest is most sensitive to). PM
  recommendation: attempt ONLY as a carefully-staged sprint with a Wave-0 characterization
  expansion, or defer/flag to the Sovereign as the one remaining high-risk item — do NOT
  rush it. (The per-state `handle_*` are already modular via WK82–85; only the ladder
  dispatch itself remains inline.)
- OPTIONAL polish: split `ursina_app.__init__` scene-construction into
  `ursina_app_scene.py::build_scene(owner)` (render-deferred verify; diminishing returns).
- `world.py:60` `_currently_visible: list`→`set` (prove determinism-neutral via the WK67
  fog-revision pin) — small, headless-verifiable.

PM will report the substantially-complete state and the Move-12 risk posture at the next
checkpoint.
