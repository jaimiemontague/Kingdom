# WK65 Sprint Plan — Round 0: De-Slop Foundation (Delete-First · Observability · Characterization Net)

**Sprint id:** `wk65_round0_deslop_foundation`
**Date planned:** 2026-05-29 · **Author:** Agent 01 (ExecutiveProducer_PM) · **Model/effort for all agents:** `claude-opus-4-8[1m]`, max
**Source docs (read these, do not re-derive):**
- `.cursor/plans/GPT 5.5 Codebase Improvements Recommendations.md` (v2 audit — the synthesized plan; see §"Round 0" of the Sequenced Roadmap and §"Dead code")
- `.cursor/plans/codebase_audit_2026-05-28_finding_inventory.md` (the raw 187-finding dataset with `file:line`)
- This plan is the **executable Round 0**. Rounds A–E are scoped in the roadmap and listed in §Follow-Up Backlog.

---

## Why This Sprint (read first)

The v2 audit (47-agent parallel audit + adversarial verification, 2026-05-28, produced **after** WK64 closed) found the codebase is **overgrown, not broken**: 187 findings, but the 24 adversarially-verified ones were almost all down-graded high→medium because they are *maintainability/structure hazards, not live runtime or determinism bugs.* The audit sequences the fix into six dependency-ordered rounds (0 → A → B → C → D → E) and its single loudest instruction is:

> **"Round 0 first, always."** Deleting ~1,000+ LOC of dead code, adding logging, and writing the characterization net is low-risk, immediately shrinks the god-files, and is the **precondition** for everything else.

WK65 is that Round 0. It is deliberately **subtractive + observability + safety-net** work. It does **not** start the risky boundary/DTO chain (Round A) or the god-file splits (Round B) — those depend on the very test net this sprint builds. Jaimie confirmed scope on 2026-05-29: *Round 0 only; delete all verified-dead with shims; include the hygiene/tool-correctness track.*

### What this sprint is NOT (hard non-goals — defer, do not touch)
- **No boundary/DTO work** (Round A): do not introduce `RenderDTO`/`AiGameView`/`HeroCommand`; do not remove `"sim"`/`world`/`economy`/`engine` from `get_game_state()`; do not touch `SimStateSnapshot` shape.
- **No god-file splits** (Round B): do not split `hud.py`/`ursina_renderer.py`/`engine.py`/`sim_engine.py`/`hero.py`/etc. (We only *delete dead code inside* a couple of them.)
- **No registries/dedup** (Round C): do not build `BuildingDef`/`BUILDING_SPECS`, `visual_specs` adoption, `RangedAttackMixin`, `ResearchableMixin`, audio `contract.py`, `route_to_building`, etc.
- **No AI router** (Round D): do not touch the `BasicAI` priority ladder / `TaskRouter`.
- **Do not grow or delete the `SystemRunner`** (that is Round B Move 9). Do not delete `SimEngine.selected_*` stubs (that rides with the Round A `get_game_state` split).
- **No behavior changes of any kind.** If removing something changes an observable behavior or any test outcome, it is **not dead** — STOP and report it as a finding. (This is exactly why `get_ranged_spec`/`_last_ranged_events` were pulled from this sprint — see §Scope Corrections.)
- **No version bump, no commit, no push** by any worker agent.

### Scope corrections made during planning (PM due-diligence — agents do NOT need to re-investigate)
- **`get_ranged_spec` + `_last_ranged_events` (plural) → DEFERRED to Round C.** Planning greps found `get_ranged_spec` is implemented by a test double (`tests/conftest.py:76`) and probed in `combat.py:184,291` + `enemy.py:345`, and `_last_ranged_events` is entangled with guardhouse multi-arrow event emission (`defensive.py:81-96`). It is **not** pure dead code; the `RangedAttackMixin` extraction in Round C is the correct home. **Keep the singular `_last_ranged_event`** (live: read at `sim_engine.py:720-722, 998-1000`; asserted by `tests/test_enemy.py:118-121`).
- **Per-god-file characterization is scoped to the foundational pins** (snapshot no-mutation, sim/engine/hero digests, AI decision pins, visual baselines). Writing characterization for *every* oversized file (~32) is infeasible in one sprint and unnecessary now; each later round writes the pins for the files **it** splits, just-in-time. Round 0 builds the cross-cutting net + the Round-A/B-critical pins only.

---

## Goals (Definition of Done)

A. **Dead code deleted** (verified-dead only, behind grep-confirm gates), ~700–1,000 LOC removed across `ai/`, `game/engine.py`, `config.py`, `game/graphics/ursina_renderer.py`, `game/systems/poi_interaction.py`, `game/audio/audio_system.py`.
B. **A logging facility exists** (`game/logging.py`) and the worst silent VFX `except: pass` swallows now log (behavior otherwise unchanged).
C. **A characterization safety net exists and is GREEN** on both pre- and post-deletion code: snapshot-no-mutation guard, deterministic sim/engine/hero digest pins, AI decision pins, and full before/after visual baselines.
D. **Tool correctness fixed**: `determinism_guard.py` (3 bugs) + `observe_sync.py` dual-clock, each with focused unit tests; dead one-off `tools/` scripts archived; the `.claude/worktrees/` shadow copy resolved.
E. **All gates green**: `python -m pytest` · `python tools/determinism_guard.py` · `python tools/qa_smoke.py --quick` · `python tools/validate_assets.py --report` (errors=0; the 46 `missing_model_file` warns are the known baseline) — and **before/after screenshots are visually identical** for every render/UI path touched.
F. Every worker updated **its own log** with evidence and wrote a completion receipt. No commits/pushes by workers.

---

## Critical Design Rules (every agent reads these before any edit)

1. **DELETE-ONLY where verified-dead.** Before deleting any symbol, run the grep-confirm in your task and paste the result into your log. "Verified-dead" = **zero live call sites in `game/`, `ai/`, `tools/`, `tests/`** (matches in `.cursor/`, `docs/`, comments, or this plan do **not** count as callers). **If any live caller exists, STOP and report — do not delete.**
2. **Keep all shims/aliases/live duplicates.** Explicitly preserve: the singular `_last_ranged_event`; the **sim** copies `SimEngine._build_system_context` / `_maybe_apply_early_pacing_nudge` / `_nearest_lair_to`; the `engine._early_nudge_*` property forwarders (`engine.py:639-668`); the `config.py` flat module-level aliases (what ~152 files import) and `DifficultyConfig`/`WaveEventConfig`.
3. **No behavior changes.** Round 0 = subtraction + observability only. Logging additions must not alter control flow (still swallow where it swallowed; just log too).
4. **Characterization pins must be GREEN before AND after.** If a deletion turns a pin red, the code was not dead — revert and report.
5. **Render/UI deletions require before/after screenshots + an explicit visual verdict** ("identical / not identical"). Check **alignment & layering first** (left edges flush, no overlap/offset), then content. Cover **every** changed visual path, not one narrow scene.
6. **Stay in your lane (file ownership below).** Do not touch files owned by another agent in your wave. Do not touch the Round A/B/C/D surface listed in Non-Goals.
7. **`determinism_guard` fix must not MASK violations.** If the improved guard surfaces a pre-existing hidden nondeterminism, **record it for PM** — do not weaken the matcher to hide it and do not fix the violation here (it becomes its own ticket).
8. **DO NOT COMMIT. DO NOT PUSH.** Update your own agent log, run your gates, write your completion receipt, then report. Git is a human gate.

---

## Wave Structure (orchestrator DAG)

```
Wave 0  (parallel)         Wave 1 (parallel)            Gate 1     Wave 2 (parallel)               Gate 2
┌─────────────────┐        ┌───────────────────┐                  ┌──────────────────────────┐
│ 12 tool fixes   │        │ 03 logging.py +   │                  │ 03 engine+config deletes │
│    + unit tests │   ─►   │    engine/sim/hero│   ─► 11 verify ─► │ 06 legacy-prompt deletes │  ─► 11 + 04
│ 11 full visual  │        │    char pins      │      pins green   │ 05 poi_interaction del   │      final gate
│    baseline +   │        │ 05 buildings/sys  │      + tooling     │ 10 ursina_renderer del   │      (suite, det,
│    snapshot     │        │    char pins      │      green         │    + vfx/pyg logging     │       qa, assets,
│    no-mutation  │        │ 06 AI char pins   │                  │ 14 audio del             │       screenshot
│    guard        │        └───────────────────┘                  │ 12 hygiene (archive+wt)  │       diff)
└─────────────────┘                                               └──────────────────────────┘
```

**Why this order:**
- **Wave 0 fixes the tools first** because every later gate calls `determinism_guard` and `qa_smoke` (which runs `observe_sync`); the `--paths` crash fix is load-bearing because Wave-2 agents run scoped guard checks. Agent 11 captures the "before" baseline **before any code changes** so the Wave-2 diffs are valid.
- **Wave 1 writes the safety net green on current code** (the precondition for Rounds A/B, and the bracket proving Round 0's deletions are inert). `game/logging.py` is created here (additive, low-risk) so Wave-2 logging adoption can import it.
- **Gate 1** confirms the net is green + tools are healthy before any deletion.
- **Wave 2 deletes** (each area's pins from Wave 1 must stay green); hygiene runs in parallel (independent files).
- **Gate 2** runs the full suite + determinism + qa + assets and diffs all screenshots vs the Wave-0 baseline; Agent 04 signs off determinism.

---

## File Ownership (no write-collisions within a wave)

| Agent | Wave | Files it may EDIT/CREATE |
|---|---|---|
| 12 | W0 | `tools/determinism_guard.py`, `tools/observe_sync.py`, **new** `tests/test_wk65_tooling.py` |
| 11 | W0 | **new** `tests/test_wk65_snapshot_no_mutation.py`; capture-only into `docs/screenshots/wk65_baseline/**` (no production code) |
| 03 | W1 | **new** `game/logging.py`; **new** `tests/test_wk65_engine_sim_hero_characterization.py` |
| 05 | W1 | **new** `tests/test_wk65_buildings_systems_characterization.py` |
| 06 | W1 | **new** `tests/test_wk65_ai_characterization.py` |
| 03 | W2 | `game/engine.py`, `tests/test_engine.py`, `config.py` |
| 06 | W2 | `ai/llm_brain.py`, `ai/prompt_templates.py`, `ai/context_builder.py`, `ai/basic_ai.py` |
| 05 | W2 | `game/systems/poi_interaction.py` |
| 10 | W2 | `game/graphics/ursina_renderer.py`, `game/graphics/pygame_renderer.py`, `game/graphics/vfx.py` (imports `game/logging.py`, does not edit it) |
| 14 | W2 | `game/audio/audio_system.py` |
| 12 | W2 | `tools/**` archival moves into `tools/archive/`; `.claude/worktrees/` removal (git) |
| 11 | G1,G2 | capture into `docs/screenshots/wk65_after/**`; runs gates (no production code) |
| 04 | G2 | runs `determinism_guard` repo-wide; review only (no production code) |

No two agents write the same file in the same wave. `game/logging.py` is created by 03 in W1 and only *imported* by 10/03 in W2.

---

# Wave 0 — Tool correctness + baseline

## Agent 12 (ToolsDevEx) — fix the QA tools FIRST (Intelligence: MEDIUM)

**Why:** these tools gate every other agent's verification. Bugs here mean unreliable gates. Source: inventory §tools-qa.

**Task 1 — `tools/determinism_guard.py` (3 fixes):**
- **(a) `--paths` outside `PROJECT_ROOT` crash** (`:106` and `:126`, `file.relative_to(PROJECT_ROOT)` raises `ValueError`). Add a helper that falls back to the raw path string when `relative_to` fails, and resolve input roots to absolute before scanning. This matters *this sprint* because Wave-2 agents run `determinism_guard --paths <their files>`.
  ```python
  def _display_path(p):
      try:
          return str(p.relative_to(PROJECT_ROOT))
      except ValueError:
          return str(p)
  ```
- **(b) Separate parse-errors from violations** (`:122-131`, `:228-235`): collect parse errors in their own list, print under a distinct header, and do not let a parse error alone produce the same FAIL/exit-1 as a real determinism violation. (Keep exit-1 for real violations.)
- **(c) Aliased imports missed** (`:89-101`, `:144-201`): build an alias map from `ast.Import`/`ast.ImportFrom` (e.g. `import time as t`, `from random import random`) and normalize the attribute chain before matching.

**Task 2 — `tools/observe_sync.py` dual-clock** (`:582` vs `:537`): delete `now_ms_val = int((t * 1000) / 60)` and read the single authoritative clock via `game.sim.timebase.now_ms()` (already the project's single-owner pattern). This fixes `max_stuck_ms` under a speed multiplier.

**Task 3 — `tests/test_wk65_tooling.py`** (new): focused unit tests so these fixes are pinned. At minimum:
- `determinism_guard.scan_file` on tiny source snippets: positive (`random.random()`, `import random as r; r.random()`, `time.time()`) → flagged; negative (`rng.random()` where `rng` is a passed-in object) → not flagged.
- `--paths` pointed at a path outside the repo does not raise (returns a clean result).
- A parse-error snippet is reported as a parse error, not a determinism violation.

**Mandatory — do NOT mask:** after the fix, run `python tools/determinism_guard.py` repo-wide. If the improved (alias-aware) matcher now surfaces a **pre-existing** violation that was hidden before, **do not** weaken the matcher and **do not** fix the violation — record it verbatim in your log under `questions_back_to_pm` for triage. (Round 0 doesn't add sim code, so a green result is expected.)

**Verify:**
```powershell
python -m pytest tests/test_wk65_tooling.py -q          # new tests pass
python tools/determinism_guard.py                        # PASS (report any newly-surfaced finding to PM, do not mask)
python tools/qa_smoke.py --quick                         # PASS (exercises observe_sync; confirm speed-scaling path)
python tools/observe_sync.py --seconds 24 --heroes 20 --seed 3 --log-every 9999 --qa --bounty   # [qa] PASS
```
Update your log. **DO NOT COMMIT.**

## Agent 11 (QA) — full visual baseline + snapshot-no-mutation guard (Intelligence: HIGH)

**Task 1 — capture the BEFORE baseline of every visual path** (before any code change), into `docs/screenshots/wk65_baseline/`. First enumerate available scenarios (`python tools/capture_screenshots.py --help` and `python tools/run_ursina_capture_once.py --help`), then capture the full visual-relevant set. At minimum:
```powershell
python tools/capture_screenshots.py --scenario base_overview   --seed 3 --out docs/screenshots/wk65_baseline/pyg_base       --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario ui_panels       --seed 3 --out docs/screenshots/wk65_baseline/pyg_ui_panels  --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario ui_pause_menu   --seed 3 --out docs/screenshots/wk65_baseline/pyg_pause      --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario ui_build_catalog --seed 3 --out docs/screenshots/wk65_baseline/pyg_catalog   --size 1920x1080 --ticks 480
python tools/run_ursina_capture_once.py --scenario base_overview --ticks 480 --out docs/screenshots/wk65_baseline/ursina_base --no-llm
```
Also capture any scenario that exercises **units in combat** and **a mountain/underground POI** (these are the paths Agent 10's deletions touch). If no such named scenario exists, note that and capture the closest available. Record the exact commands + the scenario list you found in your log.

**Task 2 — `tests/test_wk65_snapshot_no_mutation.py`** (new): pin that building a snapshot does not mutate sim entities. Pattern (adapt to the real API — inspect `game/sim/snapshot.py` and `tests/test_renderer_snapshot_contract.py`):
```python
def test_build_snapshot_does_not_mutate_entities():
    engine = GameEngine(headless=True)
    try:
        before = _digest_entities(engine)          # positions, hp, flags for heroes/enemies/buildings
        snap = engine.sim.build_snapshot()          # or engine.build_snapshot() — use the real entry point
        _ = [ (e.x, e.y) for e in snap.heroes ]     # touch the snapshot like a renderer would (read-only)
        after = _digest_entities(engine)
        assert before == after
    finally:
        pygame.quit()
```
Confirm it is **GREEN on current code** (run before Wave 1 deletions exist). This guard is the Round-A precondition; in Round 0 it also proves the render code we delete wasn't writing back.

**Verify:** `python -m pytest tests/test_wk65_snapshot_no_mutation.py -q` (PASS). Update your log. **DO NOT COMMIT.**

---

# Wave 1 — Characterization pins (green on current code) + logging facility

> All three test files must be **GREEN on the current, unmodified code**. They pin observable behavior so the Wave-2 deletions (and future rounds) are provably safe. Reuse existing `tests/conftest.py` fixtures; mirror the style of `tests/test_engine.py` (`GameEngine(headless=True)`, `engine.update(1/60)` loops). Set `DETERMINISTIC_SIM=1` + a fixed seed for digest tests.

## Agent 03 (TechnicalDirector) — logging facility + engine/sim/hero pins (Intelligence: HIGH)

**Task 1 — create `game/logging.py`** (additive; Wave-2 adopts it):
```python
"""WK65 Round 0: minimal stdlib logging facade. Replaces silent `except: pass`
swallows with observable logs. Default level WARNING so normal play is quiet."""
import logging
import os

_CONFIGURED = False

def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = os.getenv("KINGDOM_LOG_LEVEL", "WARNING").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.WARNING),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    _CONFIGURED = True

def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(name)
```
Do **not** add logging calls to any hot sim path (no behavior/determinism impact). Logging goes to stderr; it does not affect exit codes or gate parsing.

**Task 2 — `tests/test_wk65_engine_sim_hero_characterization.py`** (new). Pin the behavior Rounds A/B will refactor:
- **Deterministic sim digest:** with `DETERMINISTIC_SIM=1`, seed 3, run a headless `GameEngine` for a fixed tick count (e.g. 600) and assert an exact digest (total gold, hero/enemy/building counts, and a rounded position tuple for the first few heroes). This pins `SimEngine.update` for the Round-B sim extraction.
- **Selection mutual-exclusion invariant:** after `try_select_hero(h)`, exactly one selection slot is set and the others are cleared (pins the engine selection facade Round B will extract).
- **Console:** `engine.process_command("/revealmap")` and 1–2 other known cheats produce their documented effect (pins `process_command` for the Round-B `console.py` extraction).
- **Hero methods:** pin outputs of a couple of cohesive hero methods slated for the Round-B mixin split (e.g. rest/loiter-fee and intent derivation) for a constructed hero + fixed inputs.

**Verify:** `python -m pytest tests/test_wk65_engine_sim_hero_characterization.py -q` (GREEN on current code) · `python tools/determinism_guard.py --paths game/logging.py`. Update your log. **DO NOT COMMIT.**

## Agent 05 (GameplaySystems) — buildings/systems pins (Intelligence: MEDIUM)

**`tests/test_wk65_buildings_systems_characterization.py`** (new). Pin behavior Round C will dedup:
- **Ranged-tower fire cadence:** construct a Guardhouse/Ballista with an enemy in range; tick; assert it sets `_last_ranged_event` (singular) with the expected fields and respects cooldown. (Do **not** assert on `_last_ranged_events` plural — that's deferred to Round C.)
- **Building `update()` dispatch:** for the building types that have an `update()` path, pin one observable outcome each (e.g. marketplace research progress advances; guard spawn happens). This pins the stringly-typed dispatch ladder Round B/C will replace.
- **Difficulty scaling:** `DifficultySystem` applied to a fresh enemy yields the expected hp/damage at a couple of difficulty levels (pins the triplicated scaling Round C unifies).

**Verify:** `python -m pytest tests/test_wk65_buildings_systems_characterization.py -q` (GREEN) · `python tools/qa_smoke.py --quick`. Update your log. **DO NOT COMMIT.**

## Agent 06 (AIBehaviorDirector) — AI decision pins (Intelligence: HIGH)

**`tests/test_wk65_ai_characterization.py`** (new). Pin AI behavior so the Wave-2 legacy-prompt deletion is provably inert and Round D is safe:
- **Autonomous decision path:** with the mock provider, run a hero consult through the **live** autonomous path (`_process_autonomous_decision_request`) for a fixed context and assert the resulting decision dict shape/keys (this is the path that survives; the legacy path you delete in Wave 2 must not change this).
- **`get_fallback_decision`:** for a context with no/invalid LLM response, assert the fallback decision is returned and well-formed.
- **`build_hero_context` keys:** assert the context dict has its expected top-level keys for a constructed hero+game_state (pins `context_builder` for Round D).
- **`validate_direct_prompt_output`:** pin verdicts for 2–3 canonical inputs incl. the deferred-combat early-return and a critical-health redirect (these are explicitly fragile per the audit).

**Verify:** `python -m pytest tests/test_wk65_ai_characterization.py -q` (GREEN on current code) · `python tools/qa_smoke.py --quick`. Update your log. **DO NOT COMMIT.**

---

## Gate 1 — Agent 11 verifies the net (Intelligence: HIGH)

Run and record in your log:
```powershell
python -m pytest -q                       # full suite GREEN (517 + new wk65 tests)
python tools/determinism_guard.py         # PASS
python tools/qa_smoke.py --quick          # PASS
```
Confirm all four new `tests/test_wk65_*.py` files exist and pass. Confirm Agent 12 reported no masked determinism finding. If anything is red, **stop the sprint and report to PM** (do not proceed to deletions). **DO NOT COMMIT.**

---

# Wave 2 — Dead-code deletion + logging adoption + hygiene

> **Every deletion below is gated by a grep-confirm.** Run the grep, paste the result into your log, and only delete if there are **zero live callers** (matches in `.cursor/`, `docs/`, comments don't count). After deleting, re-run your Wave-1 pins — they must stay GREEN.

## Agent 03 (TechnicalDirector) — engine dead methods + config dataclass layer (Intelligence: HIGH)

**Task 1 — delete 3 dead `GameEngine` methods** (`game/engine.py`):
- `_nearest_lair_to` (`1103-1119`), `_maybe_apply_early_pacing_nudge` (`1121-1180`), `_build_system_context` (`1285-1294`).
- **Grep-confirm first:** `rg -n "_maybe_apply_early_pacing_nudge|_nearest_lair_to" game ai tools tests` — the only `game/` hits should be the definitions (gone after delete) + the **live sim copies** (`sim_engine.py:693,1122,1150,1167`) which you **keep**, + the test monkeypatch you fix in Task 2. For `_build_system_context`, confirm the only live caller is `sim_engine.py:641` (the **sim** copy, line `354`) and `tests/perf_stress_test.py:133` (also the sim copy) — both keep; delete only the engine copy at `1285`.
- **Keep** the `engine._early_nudge_*` property forwarders (`engine.py:639-668`) — they forward to `sim` and are out of Round 0 scope.

**Task 2 — repoint the test** (`tests/test_engine.py:129`). The monkeypatch currently patches the **dead** engine copy (a no-op); repoint it to the **live sim** method so the test's intent (suppress the pacing nudge during the build-loop regression) actually holds:
```python
# OLD (line 129): patches a dead no-op on the engine
monkeypatch.setattr(engine, "_maybe_apply_early_pacing_nudge", lambda dt, castle: None)
# NEW: patch the LIVE SimEngine method (signature-agnostic)
monkeypatch.setattr(engine.sim, "_maybe_apply_early_pacing_nudge", lambda *a, **k: None)
```
Run `tests/test_engine.py` and confirm `test_engine_spawns_peasant_and_builds_new_structure` still passes.

**Task 3 — delete the vestigial config dataclass layer** (`config.py`) — *highest blast-radius item; follow exactly.*
- **Grep-confirm first (gating):** `rg -n "from config import (WINDOW|SIM|MAP|CAMERA|HERO|ENEMY|LAIR|BOUNTY|ECONOMY|LLM|RANGER)\b" game ai tools tests` and `rg -n "config\.(WINDOW|SIM|MAP|CAMERA|HERO|ENEMY|LAIR|BOUNTY|ECONOMY|LLM|RANGER)\b" game ai tools tests`. Importers use the **flat aliases** (`WINDOW_WIDTH`, `FPS`, …), not the objects. **If any module outside `config.py` references an object (e.g. `config.HERO.base_hp`), STOP and report** — do not delete that object.
- Delete the 11 frozen dataclasses `WindowConfig`..`RangerConfig` (`config.py:11-118`) and their instances `WINDOW`..`RANGER` (`220-242`).
- **Keep `DifficultyConfig`/`WaveEventConfig`** (consumed as objects elsewhere).
- **Redefine every flat alias directly.** For pure-default ones this is mechanical (`WINDOW_WIDTH = 1920`). **For `SIM` and `LLM` you must inline the `os.getenv` reads** they performed at construction. Example:
  ```python
  # was: SIM = SimConfig(deterministic_sim=os.getenv("DETERMINISTIC_SIM","0")=="1", ...)
  #      then flat aliases derived from SIM.*
  # now: define the flat constants directly, preserving env-reading EXACTLY:
  DETERMINISTIC_SIM = os.getenv("DETERMINISTIC_SIM", "0") == "1"
  SIM_TICK_HZ       = int(os.getenv("SIM_TICK_HZ", str(FPS)))
  SIM_SEED          = int(os.getenv("SIM_SEED", "1"))
  EARLY_PACING_NUDGE_MODE = os.getenv("EARLY_PACING_NUDGE_MODE", "auto")
  LLM_PROVIDER      = os.getenv("LLM_PROVIDER", "openai")
  # ... same for the api-key / model flat aliases LLM previously produced
  ```
  Match the **existing flat-alias names** that importers already use — grep the alias block at `config.py:248+` and the importers to get the exact names. Do not rename anything.
- **Import smoke (gating):** `python -c "import config; print(config.WINDOW_WIDTH, config.FPS, config.DETERMINISTIC_SIM)"` must succeed, then `python -m pytest -q` must be fully green.

**Task 4 — adopt logging in one engine VFX swallow** (`game/engine.py:1380-1384`, the `except Exception: pass` around vfx update/render): import `from game.logging import get_logger`, and log instead of silently passing (still swallow):
```python
except Exception:
    get_logger(__name__).exception("VFX update/render failed")  # behavior unchanged; now observable
```

**Verify (all):**
```powershell
python -c "import config; print(config.WINDOW_WIDTH, config.FPS)"   # import smoke
python -m pytest -q                                                 # full suite GREEN
python -m pytest tests/test_wk65_engine_sim_hero_characterization.py tests/test_engine.py -q
python tools/determinism_guard.py --paths game/engine.py config.py game/logging.py
python tools/qa_smoke.py --quick
```
Update your log with the grep-confirm outputs + LOC removed. **DO NOT COMMIT.**

## Agent 06 (AIBehaviorDirector) — delete the legacy LLM prompt path (Intelligence: HIGH)

The decision-prompt and conversation-template paths are superseded (autonomous path + `prompt_packs` are live). Delete only after grep-confirming.

**Grep-confirm first (gating):**
```
rg -n "build_summary|build_decision_prompt|build_conversation_prompt|SYSTEM_PROMPT|DECISION_PROMPT|CONVERSATION_SYSTEM_PROMPT|CONVERSATION_USER_PROMPT" game ai tools tests
```
Expected live references are only inside the files you're about to edit (`llm_brain.py`, `prompt_templates.py`, `context_builder.py`). Plans/logs/docs don't count. Confirm `_process_conversation` (the live conversation method) does **not** reference `CONVERSATION_SYSTEM_PROMPT`/`build_conversation_prompt` (it uses `prompt_packs`). If anything live references these, STOP and report.

**Deletions:**
- `ai/llm_brain.py`: collapse `_process_request` (`155-201`) to the autonomous-only form, and remove the now-unused imports `SYSTEM_PROMPT` (`:19`) and `build_decision_prompt` (`:23`):
  ```python
  def _process_request(self, hero_key, context: dict) -> dict:
      """Process a single LLM request. WK65: legacy non-autonomous decision-prompt
      path removed (llm_bridge always sets wk50_autonomous); fall back safely if absent."""
      aut = context.get("wk50_autonomous")
      if isinstance(aut, dict):
          return self._process_autonomous_decision_request(hero_key, context, aut)
      return get_fallback_decision(context)
  ```
  (Confirm `get_fallback_decision` is already imported — it is used at `:197,201,209,241`.)
- `ai/context_builder.py`: delete `build_summary` (the `@staticmethod` at `:320`, ~95 LOC through its end). Confirm no other caller.
- `ai/prompt_templates.py`: delete `SYSTEM_PROMPT` (`27`), `DECISION_PROMPT` (`106`), `build_decision_prompt` (`178`), `CONVERSATION_SYSTEM_PROMPT` (`72`), `CONVERSATION_USER_PROMPT` (`95`), `build_conversation_prompt` (`124`). **Keep** `VALID_ACTIONS`, `TOOL_ACTIONS`, `OBEY_DEFY_VALUES`, `AUTONOMOUS_SYSTEM_PROMPT`, `build_autonomous_user_prompt`, and anything the autonomous path / `prompt_packs` import.
- `ai/basic_ai.py`: delete `_get_nearest_undepleted_poi` (`:34`) after grep-confirming zero callers.

**Verify:**
```powershell
python -m pytest tests/test_wk65_ai_characterization.py -q          # pins still GREEN (proves deletion inert)
python -m pytest -q                                                 # full suite GREEN
python tools/qa_smoke.py --quick                                    # PASS (incl. conversation + direct_prompt scenarios)
python tools/determinism_guard.py --paths ai
```
Update your log with grep-confirm outputs + LOC removed. **DO NOT COMMIT.**

## Agent 05 (GameplaySystems) — delete dead underground spawner (Intelligence: MEDIUM)

**`game/systems/poi_interaction.py`:** delete the module-level function `_spawn_underground_enemies` (`445-491`) and its only (commented-out) reference (`:376`).
- **Grep-confirm first:** `rg -n "_spawn_underground_enemies" game ai tools tests` — the only `game/` hits should be the definition + the commented call at `:376`. **Do not touch any other underground/dungeon logic** — underground is live on mountain maps; only this spawner is dead (`_handle_dungeon`, `begin_descent`, fog reveal all stay).

**Verify:**
```powershell
python -m pytest tests/test_wk65_buildings_systems_characterization.py -q   # still GREEN
python -m pytest tests/ -q -k "poi"                                          # POI tests GREEN
python -m pytest -q
python tools/qa_smoke.py --quick
python tools/determinism_guard.py --paths game/systems/poi_interaction.py
```
Update your log. **DO NOT COMMIT.**

## Agent 10 (PerformanceStability) — delete dead Ursina render code + adopt logging (Intelligence: MEDIUM)

> **Render deletions — screenshot verification is mandatory.** Two of these have a doc-contradiction trap; trust the grep + the screenshots, not the stale docs.

**Grep-confirm each before deleting** (`rg -n "<symbol>" game ai tools tests`); a "live caller" = a *call*, not a comment/doc:
- `_unit_anim_surface` (`ursina_renderer.py:543-614`). **Trap:** stale docs (`docs/art/tiny_rpg_character_pipeline.md`, `.cursor/plans/master_guide_unit_sprite_updates.md`) call this the live billboard path — it is **not**. The grep must show **zero call sites in `game/`** (only the definition + comments in `instanced_unit_renderer.py:111,221` and `guard.py:83`). `_compute_anim_frame` is the live path. Delete the method; update the 3 referencing comments to point at `_compute_anim_frame`.
- The **Ursina underground render subsystem** behind the unconditional early return (`ursina_renderer.py:1320-1441`, plus the gated block `1320-1378`). Delete the dead render block. **Do not** touch the sim-side dungeon entry (`poi_interaction._handle_dungeon`) — only the render is dead.
- `_apply_poi_mystery_state` (method `1071-1074`) **and all 3 call sites** (`1219`, `1254`, `1307`). It's a documented no-op; POI visibility is handled inline at `1119-1132`.
- The 5 dead env scale constants (`ursina_renderer.py:82-91`). Grep-confirm the renderer copies are unused (the live source is `ursina_environment.py:15-19`); delete the renderer copies only.

**Logging adoption** (import `from game.logging import get_logger`; behavior unchanged — still swallow, now log):
- `game/graphics/pygame_renderer.py:117-121` (the `except Exception: pass` around vfx).
- `game/graphics/vfx.py` — the worst bare `except: pass` swallow(s) around update/render.

**Screenshot verification (mandatory):** after deleting, re-capture the **same** scenarios Agent 11 baselined and the unit/underground scenarios, into `docs/screenshots/wk65_after/ursina_*`, and compare to `docs/screenshots/wk65_baseline/`. Give an explicit verdict in your log: **units animate identically; buildings/POIs render identically; surface + underground/mountain views identical.** Check alignment/layering first. If anything differs, revert and report.
```powershell
python tools/run_ursina_capture_once.py --scenario base_overview --ticks 480 --out docs/screenshots/wk65_after/ursina_base --no-llm
# + the unit-combat and mountain/underground scenarios Agent 11 used
```
**Verify:** `python -m pytest -q` · `python tools/qa_smoke.py --quick` · `python tools/determinism_guard.py --paths game/graphics/ursina_renderer.py game/graphics/pygame_renderer.py game/graphics/vfx.py`. Update your log with grep outputs, LOC removed, screenshot verdict. **DO NOT COMMIT.**

## Agent 14 (SoundDirector) — delete dead audio method (Intelligence: LOW)

**`game/audio/audio_system.py`:** delete `emit_from_events` (`234-252`).
- **Grep-confirm first:** `rg -n "emit_from_events" game ai tools tests` — the `game/audio/audio_system.py` definition should be the only live hit (the many other matches are `VFXSystem.emit_from_events`, a different class, and docs/logs — do **not** touch those). `on_event` is the live audio path.

**Verify:** `python -m pytest -q` · `python tools/qa_smoke.py --quick`. Update your log. **DO NOT COMMIT.**

## Agent 12 (ToolsDevEx) — repo hygiene (Intelligence: MEDIUM)

> Independent of the deletions; runs in parallel. Everything here is **reversible** (git mv / git worktree).

**Task 1 — archive dead one-off `tools/` scripts.** Candidates: codemods `tools/patch_*.py`, PM-hub updaters `tools/update_pm_hub_wk*.py`, and one-off capture patches. **For each candidate, grep-confirm it is not imported or referenced** by any live code/CI/`.mdc`: `rg -n "<scriptname>" game ai tools tests .cursor` (ignore the file itself and historical agent-log entries). Move confirmed-dead scripts with `git mv <script> tools/archive/` (the dir already exists). **Log the exact list moved** (no silent truncation).

**Task 2 — resolve the `.claude/worktrees/` shadow copy** (the audit flags a full second repo copy under `.claude/worktrees/quirky-roentgen-e15808/` that doubles every grep). Safely:
```powershell
git worktree list                 # identify the worktree + confirm it is NOT the main checkout
git -C ".claude/worktrees/quirky-roentgen-e15808" status   # confirm clean (no uncommitted work)
```
Only if it is a stale, clean, non-main worktree: `git worktree remove ".claude/worktrees/quirky-roentgen-e15808"` (add `--force` only if clean-but-locked). **If it has uncommitted changes or is the active checkout, STOP and report — do not remove.**

**Verify:** `python -m pytest -q` (unaffected) · `python tools/qa_smoke.py --quick`. Update your log with the archived list + worktree outcome. **DO NOT COMMIT.**

---

## Gate 2 — final verification (Agent 11 + Agent 04)

### Agent 11 — full regression + visual diff (Intelligence: HIGH)
```powershell
python -m pytest -q                                  # full suite GREEN (incl. all wk65 tests)
python tools/determinism_guard.py                    # PASS
python tools/qa_smoke.py --quick                     # PASS
python tools/validate_assets.py --report             # errors=0 (46 missing_model_file warns = known baseline)
```
Re-capture every baseline scenario into `docs/screenshots/wk65_after/` and **compare against `docs/screenshots/wk65_baseline/`**. Verdict per path (alignment/layering first, then content): **identical / not identical.** Cover every visual path — pygame HUD/panels/pause/catalog/base + Ursina base/units/underground. Any diff → report, do not close. Update your log.

### Agent 04 (NetworkingDeterminism) — determinism sign-off (Intelligence: MEDIUM)
- Run `python tools/determinism_guard.py` repo-wide and confirm PASS.
- Confirm Agent 12 surfaced no masked finding; if a pre-existing violation was surfaced by the improved guard, record your assessment (real sim-determinism risk vs false positive) for PM — it becomes a Round-A/B ticket, not a Round-0 blocker.
- Spot-run a determinism A/B: `python tools/qa_smoke.py --quick` twice with seed 3 and confirm identical QA verdicts. Update your log. **DO NOT COMMIT.**

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| `config.py` flatten breaks an importer (152 files) | Med | Grep-confirm no object-importers + inline env reads exactly + `import config` smoke + full pytest before proceeding; reversible via git. |
| Deleting "dead" code that's actually live | Low | Every deletion gated by grep-confirm (zero live callers) + Wave-1 pins stay green; `get_ranged_spec` already pulled for this reason. |
| Render deletion changes a frame | Low | Before/after screenshot diff per path + explicit visual verdict; `_unit_anim_surface` trap called out explicitly. |
| `determinism_guard` alias fix newly-fails the build | Low-Med | Report-don't-mask; Round 0 adds no sim code so a surfaced finding is pre-existing and triaged separately, not a blocker. |
| Logging output breaks a gate | Very Low | Default level WARNING, logs to stderr, gates check exit codes not stdout. |
| Worktree removal deletes live work | Low | Inspect `git worktree list` + `status` first; only remove if stale/clean/non-main. |

## Sprint Success Criteria
- [ ] ~700–1,000 LOC dead code removed; every deletion has a logged grep-confirm.
- [ ] `game/logging.py` exists; VFX swallows in engine/pygame_renderer/vfx now log.
- [ ] 4 new `tests/test_wk65_*` files + tooling tests, all GREEN before and after deletions.
- [ ] `determinism_guard` + `observe_sync` fixed with unit tests; dead tools archived; worktree shadow resolved.
- [ ] Full suite + determinism + qa_smoke + validate_assets all green; all screenshot diffs verdict = identical.
- [ ] Every worker log updated with evidence + receipt; no commits/pushes by workers.

## Follow-Up Backlog (after WK65 — maps to the audit roadmap)
- **Round A (WK66):** the boundary/DTO chain — Moves 1–6 (stop render write-back → render DTOs → split frame DTOs → `AiGameView` → `HeroCommand`), + invert `graphics→tools` (L9), move `World.render` out (L10). MED-HIGH risk; needs this sprint's net.
- **Round B:** god-file splits (Moves 7–9, 11) behind compat shims — `BuildingLifecycleSystem`, extract sim services, grow `SystemRunner`, split `hud.py`/`ursina_renderer.py`/`engine.py`/`sim_engine.py`/`hero.py`/`input_handler.py`. Write per-file characterization just-in-time.
- **Round C:** registries/dedup — `BuildingDef`/`BUILDING_SPECS`, `visual_specs` adoption, `HERO_CLASS_COLORS`, audio `contract.py`, `RangedAttackMixin` (**incl. the deferred `get_ranged_spec`/`_last_ranged_events` cleanup**), `ResearchableMixin`, `route_to_building`/`engage`/`advance_along_path_to` helpers, purge the ~17 "WK34 REMOVED" zombie building keys. Also the **deferred** building-panel `research()`-arity logging.
- **Round D:** `TaskRouter` + AI file splits.
- **Round E:** classify `studio_gateway/` + `tools/ai_studio_orchestrator/`; audit the ~6,000 LOC asset/model tooling + the `tests/` suite itself; repo-hygiene (docs/.cursor size, perf-harness duplication).

---

## Kickoff Appendix (ready for Mode-2 transcription)

**`pm_send_list_minimal` (waves):**
```
Wave 0 (parallel):  12 (MEDIUM), 11 (HIGH)
Wave 1 (parallel):  03 (HIGH), 05 (MEDIUM), 06 (HIGH)
Gate 1:             11 (HIGH)
Wave 2 (parallel):  03 (HIGH), 06 (HIGH), 05 (MEDIUM), 10 (MEDIUM), 14 (LOW), 12 (MEDIUM)
Gate 2:             11 (HIGH), 04 (MEDIUM)
Do NOT send:        02, 07, 08, 09, 13, 15
```
**Intelligence rationale:** 03/06/11 high (config-152-importer surgery / LLM control-flow collapse / novel characterization + visual regression). 05/10/12/04 medium (spec-following deletions, render deletion + screenshot verify, tool-correctness reasoning, determinism sign-off). 14 low (single grep-confirmed deletion).
*Optional:* add Agent 09 (LOW, consult) as a second pair of eyes on the Wave-2/Gate-2 render screenshot diffs if you want extra visual coverage.

**Universal prompt (template):**
```
You are being activated for the wk65_round0_deslop_foundation sprint (Round 0: de-slop foundation).
Read your assignment in the PM hub:
.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json
 → sprints["wk65_round0_deslop_foundation"].rounds[<the round named in your activation>]
Your full task, code examples, and exact verification commands are in:
.cursor/plans/wk65_round0_deslop_foundation.plan.md  (find your agent's section)
Read the "Critical Design Rules" first. Every deletion is gated by a grep-confirm (zero LIVE callers).
After completing your work: (1) update your agent log with evidence (grep outputs, LOC removed, gate results,
screenshot verdicts); (2) run your verification gates; (3) write your completion receipt; (4) report status.
DO NOT COMMIT. DO NOT PUSH.
```
**Orchestrator (Local-to-Cloud) live command** (per `ai_studio_automation_contract.md`):
```
... run --sprint wk65_round0_deslop_foundation --cloud-repo-url https://github.com/jaimiemontague/Kingdom.git --auto-push --mode auto_until_human_gate
```
Human gates this sprint: Gate-1 stop-if-red, Gate-2 visual approval, and the final commit/push (PM/Jaimie only).
