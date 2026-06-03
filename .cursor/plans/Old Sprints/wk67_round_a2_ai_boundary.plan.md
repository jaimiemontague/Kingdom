# WK67 Sprint Plan — Round A-2: AI Boundary (AiGameView · HeroCommand · Frame-State Split · L9 · Determinism)

**Sprint id:** `wk67_round_a2_ai_boundary`
**Date planned:** 2026-05-29 · **Author:** Agent 01 (ExecutiveProducer_PM) · **Model/effort for all agents:** `claude-opus-4-8[1m]`, max
**Execution mode:** **Claude Code Agent-tool subagents** (NOT the Cursor SDK orchestrator). Each worker is spawned as its studio role on model `claude-opus-4-8`, onboards via `.cursor/rules/01-studio-onboarding.mdc` + its `agent-NN-*.mdc`, then follows its `pm_agent_prompts[NN]` in the PM hub + its section in this plan. Agent 01 (parent) evaluates each wave by running the gates and viewing screenshots, and loops fixes back to the owning agent until the Definition of Done holds.
**Source docs (read these, do not re-derive):**
- `.cursor/plans/GPT 5.5 Codebase Improvements Recommendations.md` (v2 audit — see Moves 4/5/6, leaks L3/L3b/L6/L9, §"Round A", §"Boundary-leak map").
- `.cursor/plans/codebase_audit_2026-05-28_finding_inventory.md` (the raw 187-finding dataset with `file:line`).
- `.cursor/plans/wk66_round_a1_render_boundary.plan.md` (the just-closed Round A-1 — built the render DTOs + the L2 write-back closure this sprint builds on, and DEFERRED Move 4 to here).

---

## Why This Sprint (read first)

WK66 (Round A-1) closed the **render** half of the boundary: it added frozen render DTOs (`UnitDTO`/`BuildingDTO`/`BountyDTO`), migrated the pygame render paths to them, and — the keystone — **stopped the renderer writing back onto sim state** (zero `setattr` onto sim entities; sim now owns discovery/anim-trigger). WK66 deliberately **deferred Move 4** (the snapshot split) because the clean form (a DTO-only `RenderSnapshot`) needed the full renderer DTO migration first.

WK67 (Round A-2) closes the **AI** half of the boundary and the cheap structural half of Move 4. The v2 audit's L3/L3b leaks are: `get_game_state()` ships the **live, mutable** `world`/`economy`/`sim`/`engine` into the AI, and AI behaviors **mutate sim state through that dict**. The audit calls the DTO/`AiGameView`/`HeroCommand` chain the **structural keystone** — it's what makes future replay/save-load/multiplayer possible and every later AI-file split safe.

Per the PM scope decision (confirmed with Jaimie 2026-05-29), WK67 is the **AI-boundary contracts** sprint and is verified primarily by **determinism pins + behavior digests** (it is mostly invisible to the player), with screenshot verification only on the few render-touching pieces (the Move-4 renderer-signature change, L9 material rendering, and the new combat-capture scenario). The full Ursina-renderer DTO read-migration (deleting the live entity tuples) is **explicitly deferred** to the render/Round-B sprint — see Non-goals.

### The leaks WK67 closes (each a located, concrete problem — verified in code 2026-05-29)

- **L6 — presentation state injected into the sim snapshot** (Move 4, cheap half). `SimEngine.build_snapshot` (`sim_engine.py:445-462`) still takes 11 presentation kwargs (`camera_x/camera_y/zoom/default_zoom/paused/running/pause_menu_visible/screen_w/screen_h/selected_hero/selected_building`) and stuffs them into the 64-field `SimStateSnapshot` (`snapshot.py:14-94`, presentation fields at lines 58-74). Camera/zoom/pause/selection are **presentation**, not sim truth. **No `PresentationFrameState` exists yet** (WK66 deferred it).
- **L3 — `get_game_state()` ships live `world`/`economy`/`sim`/`engine` into the AI** (Move 5 read side). `sim_engine.py:430` (`"economy": self.economy`), `:431` (`"world": self.world`), `:433` (`"sim": self`); `engine.py:1484` (`gs["engine"] = self`). The AI reads `world` at **16 sites**, `sim` at a few, `castle` at 5 — all read-only queries today, but it holds the **live mutable objects** through an untyped dict.
- **L3b — AI behaviors mutate sim state through the dict** (Move 6 write side). `ai/behaviors/shopping.py:97,107,118,129` call `economy.hero_purchase(...)` (a write across the boundary) alongside `hero.buy_item(...)`. (`game/entities/builder_peasant.py:288,315` call `sim.chop_tree_at`/`harvest_log_at` via `game_state.get("sim")` — same anti-pattern, handled via a typed sim accessor, not a full command.)
- **L9 — `game/graphics` imports `tools.*` at runtime.** `ursina_app.py:39-40` (module-top: `tools.ursina_input_debug`, `tools.ursina_screenshot`), `:249` (lazy `tools.ursina_screenshot`); `ursina_environment.py:238` (`tools.model_viewer_kenney._apply_gltf_color_and_shading`), `:254` (`tools.kenney_pack_scale.apply_kenney_pack_color_tint_to_entity`); `ursina_prefabs.py:225-226` (both). A packaged/frozen build would need the dev `tools/` tree to render. **No `game/graphics/kenney_material.py` exists yet** (verified).
- **Three determinism/capture items triaged here** (from WK66 follow-ups):
  - Pygame/Ursina **anim frames use wall-clock time** (`ursina_renderer.py:571` `time.perf_counter()`; `instanced_unit_renderer.py:238` `time.time()`), so dynamic-scene captures jitter ~3% on identical code. Fix: under `DETERMINISTIC_SIM`/capture, derive the within-clip frame index from the **sim tick counter**.
  - **`_fog_revision` drifts ±1** across in-process `GameEngine` builds (`sim_engine.py:152` init, `:1317` increment, `:490` into snapshot).
  - **No registered Ursina melee-combat capture scenario** (`screenshot_scenarios.py:1563-1601` lists 18 scenarios; only `ranged_projectiles` is combat-ish) — the unit-render/anim boundary on the primary renderer has thin visual coverage.

### Two facts that make this lower-risk than it sounds

1. **WK66 already closed the write-back keystone (L2).** The renderer no longer mutates the sim, and WK66 proved out the "additive → migrate → remove" pattern behind the characterization net + determinism guard. WK67 reuses that exact discipline on the AI side.
2. **The AI does not actually write `world` today.** The 16 `world` reads are all read-only (visibility/`world_to_grid`/`best_adjacent_tile`/width/height — verified). So `AiGameView` wrapping `world` in a read-only `WorldView` is a **mechanical source-swap with zero behavior change**; it makes the read-only contract explicit and removes the mutation *capability*. The only real cross-boundary **writes** are the 4 shopping `economy.hero_purchase` calls.

### What this sprint is NOT (hard non-goals — defer, do not touch)

- **No full Ursina-renderer DTO read-migration.** The Ursina renderer + `instanced_unit_renderer` still read live `snapshot.heroes/enemies/peasants/guards/tax_collector/buildings/bounties` tuples (verified). **Leave them.** Do NOT delete the live entity tuples from `build_snapshot`/`RenderSnapshot` — they are still consumed. Enriching `UnitDTO`/`BuildingDTO` and migrating the Ursina read paths is the **render/Round-B sprint** (pairs with the `ursina_renderer.py` split, where "split modules consume DTOs"). Move 4 in WK67 is the **presentation-split only** (L6), keeping both live + DTO tuples in the render snapshot.
- **No UI/HUD restructure.** `get_game_state()`'s dict stays the **UI-facing** contract. It may still carry `engine` (HUD command-mode at `hud.py:2208`, audio at `hud.py:475`) and `sim.event_bus` (`hud.py:489`) — those are presentation-to-presentation, not the AI leak. Splitting `UiGameView` cleanly out of the HUD is the HUD-split sprint (Round B). WK67 introduces `AiGameView` for the **AI consumer path only** and leaves the UI dict in place.
- **No AI router / behavior-file splits (Round D).** Do not build `TaskRouter`/`ai/vocab.py` or split `basic_ai.py`/`context_builder.py`. Move 6 is the *minimal* HeroCommand on the shopping write only.
- **No sim-engine god-file split, no registries (Rounds B/C).** Do not extract `FogService`/`SnapshotBuilder`/etc., do not build `BuildingDef`. (We add small new modules — `ai_view.py`, `hero_commands.py`, `kenney_material.py` — that is creation, not a god-file split.)
- **No behavior changes of any kind.** The single measurable outcome is *"the AI can no longer mutate the sim through the game-state dict, and presentation state is out of the sim snapshot — the game plays byte-for-byte identically."* A changed AI-decision digest, a flipped determinism check, or a changed pixel means the change was not inert — STOP and report.
- **No version bump, no commit, no push** by any worker agent.

### PM scope corrections made during planning (agents do NOT need to re-investigate)

- **Move 4 here = the presentation-split half only (L6).** Create `PresentationFrameState` (engine-built) and a `RenderSnapshot` that carries sim truth **including the existing live entity tuples AND the WK66 DTO tuples**. Drop the presentation kwargs from `build_snapshot`. Do **not** delete the live tuples (still consumed by Ursina). **Rationale:** the high-value win (presentation out of the sim DTO) does not require finishing the render DTO migration; decoupling them keeps WK67 sized and the render last-mile lands with the renderer split.
- **Move 5 = the AI consumer path only.** `AiGameView` is built by the sim and consumed by `BasicAI` + `ai/behaviors/*`. It drops `economy`/`sim`/`engine` entirely and wraps `world` in a read-only `WorldView`. **Entity lists stay live** (AI-side DTOs are deferred, exactly like the render live tuples). The UI `get_game_state()` dict is untouched. The dead `SimEngine.selected_*` stubs (`sim_engine.py:137-140`) are deleted as part of this (they are read only by the dict path the AI no longer uses; the live selection lives in `presentation/selection_state.py`).
- **Move 6 = establish the pattern on the real write leak.** `HeroCommand` covers the shopping purchase (`economy.hero_purchase` + `hero.buy_item`). The applier is **sim-owned** and applies **synchronously when proposed** (the multi-item shopping logic reads `hero.gold` between purchases — see Agent 03/06 tasks — so deferred/batched application would change behavior). Builder-peasant's `sim.chop_tree_at/harvest_log_at` is rehomed onto a **typed sim accessor** (not a command — it is a sim entity, not AI). Full command-ification of the peasant loop is out of scope.
- **L9 = sever every `game/graphics → tools` runtime import.** Move the render-path material/scale helpers into a new `game/graphics/kenney_material.py`; move (or guard) the `ursina_app.py` module-top debug/screenshot imports too (they are module-top, so a frozen build needs them). After this, `rg "from tools|import tools" game/graphics` returns **zero** (or only dev-guarded lazy imports inside `if KINGDOM_*_DEBUG` blocks). `tools/` re-imports the moved helpers from `game.graphics` (tools→game is the allowed direction; no circular risk — verified).

---

## Goals (Definition of Done)

A. **Presentation state is out of the sim snapshot (L6 closed).** A new `PresentationFrameState` (camera/zoom/screen/paused/running/pause_menu_visible/blend/tick/selection) is built by `GameEngine`; `RenderSnapshot` holds sim truth (live tuples + DTO tuples + world/fog/etc.); `SimEngine.build_snapshot` no longer takes any presentation kwargs. Both renderers' `update()` accept `(render_snapshot, frame)`.
B. **The AI no longer holds live mutable sim services (L3 read side closed).** `BasicAI.update` + every `ai/behaviors/*` consumer reads an `AiGameView` that exposes a read-only `WorldView` and immutable facts (`player_gold`, `pois`, read-only `castle`), and carries **no** `economy`/`sim`/`engine`. Verified by grep: `rg -n "game_state.get\(.economy.|game_state.get\(.sim.|game_state\[.engine.\]" ai/` returns zero (the `sim`/`economy` reads in `ai/` are gone). The dead `SimEngine.selected_*` stubs are deleted.
C. **The AI no longer writes sim state through the dict (L3b write side closed).** `ai/behaviors/shopping.py` proposes a `HeroCommand`; the sim applies it (`economy.hero_purchase` + `hero.buy_item` happen inside a sim-owned applier). `rg -n "economy.hero_purchase|\.buy_item\(" ai/` returns zero. Builder-peasant uses a typed sim accessor (no `game_state.get("sim")` in `builder_peasant.py`).
D. **`game/graphics` has zero runtime `tools.*` imports (L9 closed).** A `game/graphics/kenney_material.py` owns the moved render-path helpers; `ursina_environment`/`ursina_prefabs`/`ursina_app` import from `game.graphics`; `tools/` re-imports from `game.graphics`. `rg -n "from tools|import tools" game/graphics` returns zero non-dev-guarded hits. `python -c "import game.graphics.ursina_app"` works without `tools/` on the path (or note any dev-guarded exception).
E. **Determinism/capture items landed:** anim frame index is sim-tick-derived under `DETERMINISTIC_SIM`/capture (byte-reproducible dynamic captures); `_fog_revision` is stable across in-process rebuilds; a registered Ursina melee-combat capture scenario exists with a headless anim-boundary test.
F. **The characterization net is GREEN before AND after**, extended with: an **AI-decision digest** (the keystone), a **shopping-purchase parity** pin, an **AiGameView-purity** pin, a **frame-state** pin, and the determinism digests (anim-frame reproducibility, fog-revision stability).
G. **All gates green** and the few render-touching paths are **screenshot-identical** (Move-4 signature change, L9 material rendering, base overview); the new combat scenario captures **byte-stable across two runs**.
H. Every worker updated **its own log** with evidence (grep outputs, digests, screenshot verdicts, gate results) and a completion receipt. No commits/pushes by workers.

---

## Critical Design Rules (every agent reads these before any edit)

1. **Behavior-preserving only.** This sprint changes *how data crosses the AI/render boundary*, never *what the game does*. Every wave must keep the full suite, `determinism_guard`, `qa_smoke --quick`, the characterization pins, and the **AI-decision digest** byte-identical, and screenshots identical on render-touching paths. A red pin / changed digest / changed pixel means the change was not inert — revert and report.
2. **The AI-decision digest is the keystone guardrail.** With `DETERMINISTIC_SIM=1`, seed 3, a fixed tick count, the digest of per-hero (target, intent, state, position, gold) + economy transaction log MUST be byte-identical before AND after Move 5 and Move 6. If it changes, you changed behavior — STOP.
3. **No AI code may hold or mutate a live sim service.** After Move 5, `ai/` must not read `economy`/`sim`/`engine` from the game-state, and after Move 6 must not call `economy.hero_purchase`/`hero.buy_item`. The AI reads `world` only through the read-only `WorldView`.
4. **HeroCommand applies synchronously, in the same tick, in the same order** as the code it replaces. The shopping loop reads `hero.gold` between purchases — the applier must mutate immediately when a command is proposed, not batch at end-of-tick. (See Agent 03/06 tasks.)
5. **`AiGameView`/`WorldView`/`HeroCommand` are typed value/wrapper objects.** `WorldView` wraps the live `World` privately and exposes only the read methods/attrs the AI + navigation helpers call (enumerated in the Agent 03 task) so it is a drop-in for `world` wherever it was passed. `HeroCommand` is a frozen dataclass modeled on `HeroTask` (`ai/contracts.py:61-103`).
6. **Additive first, then migrate, then remove.** Wave 1 adds `PresentationFrameState` alongside the snapshot fields. Wave 2 adds `AiGameView` and switches AI consumers. Wave 3 adds `HeroCommand` and switches the writer. Never delete the old path until the new one is proven green (the dead `selected_*` stubs and the `economy`/`sim` dict keys for AI are removed only after their last reader migrates).
7. **Render/UI changes require before/after screenshots + an explicit verdict** ("identical / not identical"), checking **alignment & layering first**, then content — but only on the render-touching pieces (Move-4 signature change, L9 material, combat scenario). Ursina is the shipping renderer (`main.py:49 default="ursina"`) → P0 screenshot path; pygame captured where the Move-4 entry changed.
8. **Stay in your lane (file ownership below).** 03 owns sim/snapshot/engine/contracts + the new `ai_view.py`/`hero_commands.py` (sim-built contracts) + `builder_peasant.py`. 06 owns `ai/**` consumers. 10 owns `game/graphics/**`. 12 owns `tools/**`. The only shared symbols are `game/sim/ai_view.py` + `game/sim/hero_commands.py` (03 authors; 06 imports read-only) and `game/graphics/kenney_material.py` (10 authors; 12 imports).
9. **Determinism guardrail.** Move 5/6 touch the sim↔AI boundary and the tick. Agent 04 signs off `determinism_guard` repo-wide and confirms the AI-decision digest is byte-identical at every AI gate. If improved code surfaces a **pre-existing** nondeterminism, **record it for PM** — do not mask it.
10. **DO NOT COMMIT. DO NOT PUSH.** Update your own agent log, run your gates, write your completion receipt, then report. Git is a human gate.

---

## Wave Structure (orchestrator DAG — executed via subagents, PM-gated)

```
Wave 0          Wave 1                Wave 2                 Wave 3                Wave 4            Wave 5 (final)
┌───────────┐   ┌──────────────┐      ┌──────────────┐       ┌──────────────┐     ┌────────────┐   ┌──────────────┐
│ 11 baseline│  │ Move 4: L6   │      │ Move 5:      │       │ Move 6:      │     │ L9: invert │   │ Determinism: │
│ + extend   │  │ presentation │      │ AiGameView + │       │ HeroCommand  │     │ graphics→  │   │ anim→tick,   │
│ char net   │  │ split        │      │ WorldView    │       │ (shopping)   │     │ tools      │   │ fog_rev,     │
│ (AI digest,│  │ 03 snapshot/ │      │ 03 authors   │       │ 03 applier + │     │ 10 game-   │   │ combat scene │
│ shopping   │  │ engine; 10   │      │ view; 06     │       │ builder accr;│     │ side; 12   │   │ 10/12/03;    │
│ parity,…)  │  │ renderer sig │      │ migrates ai/ │       │ 06 shopping  │     │ tools-side │   │ 06/05 cons.  │
└───────────┘   └──────────────┘      └──────────────┘       └──────────────┘     └────────────┘   └──────────────┘
   Gate 0          Gate 1                Gate 2                 Gate 3 (escape       Gate 4            Gate 5
 11 net green    11+09+04:             11+04+06:              hatch here)          11+09:            11+04+09:
 on current      suite/det/qa +        suite/det + AI         11+04+05:            import smoke +     full suite/det/
 code; baseline  screenshot diff       digest IDENTICAL +     suite/det + AI       suite + ursina    qa/assets +
 captured        IDENTICAL             purity pin GREEN       digest + shopping    screenshot        combat capture
                                                              parity IDENTICAL     IDENTICAL         byte-stable ×2
```

**Why this order:**
- **Wave 0** captures BEFORE baselines for the render-touching paths and writes the AI-decision digest + parity pins the whole sprint leans on. Green-on-current is the precondition.
- **Wave 1 (Move 4)** is the structural snapshot split — it is mechanical, screenshot-verifiable, and touches `build_snapshot`/`snapshot.py` *before* Move 5 touches the adjacent `get_game_state`/`sim_engine`, so the sim-engine edits stay coherent and reviewable in sequence.
- **Wave 2 (Move 5)** introduces `AiGameView` and migrates the AI reads — no visible change, gated on the AI-decision digest.
- **Wave 3 (Move 6)** flips the one real write (shopping) to the command pattern — the most behavior-fragile wave, with the escape hatch.
- **Waves 4 (L9) + 5 (determinism)** are **independent of the AI boundary** and may be scheduled in parallel with Waves 1-3 *if* Jaimie activates 10/12 alongside 03/06 — with the caveat that Agent 10 touches `ursina_renderer.py` in both Move 4 (entry) and the anim-frame fix (`_compute_anim_frame`), so those two 10-tasks must be sequenced, not run as two simultaneous chats.

---

## File Ownership (no write-collisions within a wave)

| Agent | Wave | Files it may EDIT/CREATE |
|---|---|---|
| 11 | W0 | **new** `tests/test_wk67_ai_boundary.py`; capture-only into `docs/screenshots/wk67_baseline/**` (no production code) |
| 03 | W1 | `game/sim/snapshot.py` (define `RenderSnapshot` + `PresentationFrameState`; keep `SimStateSnapshot` alias if any non-renderer consumer remains), `game/sim_engine.py` (`build_snapshot` drops presentation kwargs, returns `RenderSnapshot`), `game/engine.py` (build `PresentationFrameState`; pass `(render_snapshot, frame)` to renderer `update()`) |
| 10 | W1 | `game/graphics/ursina_renderer.py` (`update()` entry only — read the split shape), `game/graphics/pygame_renderer.py` (entry), `game/graphics/render_coordinator.py` (if it forwards the snapshot) — **entry signature only, no draw-logic change** |
| 11/09/04 | G1 | gates + screenshot diff; no production code |
| 03 | W2 | **new** `game/sim/ai_view.py` (`AiGameView` + `WorldView` + `build_ai_view`), `game/sim_engine.py` (add `build_ai_view`; delete dead `selected_*` stubs `:137-140` + their reads in `get_game_state`) |
| 06 | W2 | `ai/basic_ai.py`, `ai/behaviors/*.py`, `ai/arrival_handlers.py`, `game/entities/hero.py` (only the `game_state.get("world")` read sites `:897,:913` → `WorldView`) — migrate AI consumers to `AiGameView`/`WorldView` |
| 11/04/06 | G2 | gates + AI digest; no production code |
| 03 | W3 | **new** `game/sim/hero_commands.py` (`HeroCommand` DTO + sim applier), `game/sim_engine.py` (wire applier; expose typed lumber accessor), `game/entities/builder_peasant.py` (use typed accessor, drop `game_state.get("sim")`) |
| 06 | W3 | `ai/behaviors/shopping.py` (propose command, drop `economy.hero_purchase`/`hero.buy_item`), `ai/basic_ai.py` (route proposed commands to the sim applier synchronously) |
| 11/04/05 | G3 | gates + AI digest + shopping parity; no production code |
| 10 | W4 | **new** `game/graphics/kenney_material.py`, `game/graphics/ursina_environment.py` (`:238,:254` imports), `game/graphics/ursina_prefabs.py` (`:225-226`), `game/graphics/ursina_app.py` (`:39-40,:249` imports) |
| 12 | W4 | `tools/model_viewer_kenney.py` (re-export `_apply_gltf_color_and_shading` from `game.graphics.kenney_material`), `tools/kenney_pack_scale.py` (re-export the moved helpers), `tools/ursina_input_debug.py` + `tools/ursina_screenshot.py` (only if 10 chooses to move them here vs. dev-guard) |
| 11/09 | G4 | import smoke + gates + ursina screenshot; no production code |
| 10 | W5 | `game/graphics/ursina_renderer.py` (`_compute_anim_frame` `:554-608`), `game/graphics/instanced_unit_renderer.py` (`:214-275` anim timing) — anim-frame → sim tick |
| 12 | W5 | `tools/run_ursina_capture_once.py` (capture-mode flag if needed), `tools/screenshot_scenarios.py` (register `ursina_melee_combat` scenario) |
| 03 | W5 | `game/sim_engine.py` (`_fog_revision` determinism `:152,:1317`) |
| 11 | W5 | `tests/test_wk67_ai_boundary.py` (add anim-boundary + fog-rev + combat-capture-stability tests) |
| 04/09 | G5 | determinism repo-wide + final cohesion; no production code |

**Collision audit:** W1 → 03 = sim/snapshot/engine; 10 = graphics entries (different files). W2 → 03 = sim only; 06 = ai/* + `hero.py` world-reads (03 does not touch `hero.py` this wave). W3 → 03 = sim + `hero_commands.py` + `builder_peasant.py`; 06 = `shopping.py` + `basic_ai.py` (03 does not touch `ai/`). W4 → 10 = graphics; 12 = tools (10 creates `kenney_material.py` FIRST, then 12 repoints tools — sequence within the wave). W5 → 10 = `ursina_renderer.py`/`instanced_unit_renderer.py`; 03 = `sim_engine.py`; 12 = tools; 11 = tests — different files. **No file is written by two agents in the same wave.** Note across waves: `sim_engine.py` is 03-only throughout (W1/W2/W3/W5 sequential); `ursina_renderer.py` is 10-only (W1 entry, W5 anim — sequential).

---

# Wave 0 — Baseline + safety net (no production code)

## Agent 11 (QA) — before-baseline + extend the characterization net (Intelligence: HIGH)

**Why:** the AI-decision digest is the keystone that proves Moves 5/6 are inert; the render-touching diffs need a baseline captured *before any change*.

**Task 1 — capture the BEFORE baseline** of the render-touching paths into `docs/screenshots/wk67_baseline/`. Enumerate scenarios first (`python tools/run_ursina_capture_once.py --help`, `python tools/capture_screenshots.py --help`), record the list in your log. At minimum:
```powershell
python tools/run_ursina_capture_once.py --scenario base_overview --ticks 480 --out docs/screenshots/wk67_baseline/ursina_base --no-llm
# + a scenario that exercises Kenney material/tint rendering (buildings/props), for the L9 gate.
python tools/capture_screenshots.py --scenario base_overview --seed 3 --out docs/screenshots/wk67_baseline/pyg_base --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario ui_panels      --seed 3 --out docs/screenshots/wk67_baseline/pyg_panels --size 1920x1080 --ticks 480
```

**Task 2 — `tests/test_wk67_ai_boundary.py`** (new). Reuse `tests/conftest.py` fixtures; mirror `tests/test_engine.py` style (`GameEngine(headless=True)`, `engine.update(1/60)` loops). Set `DETERMINISTIC_SIM=1` + a fixed seed for digest tests. Write these pins:

- **AI-decision digest (THE keystone — GREEN on current code).** Build a headless `GameEngine`, seed 3, `DETERMINISTIC_SIM=1`, advance a fixed tick count (e.g. 300). Each tick (or at the end), compute a stable digest over **every hero**: `(hero_id, round(x,3), round(y,3), str(state), intent_label, target_type_str, int(gold))` plus `len(economy.transaction_log)` and `economy.total_spent_by_heroes` and `wave`. Hash the per-tick tuples into one digest string. This digest MUST be byte-identical before AND after Move 5 + Move 6.
  ```python
  def _ai_digest(engine, ticks=300):
      import hashlib
      h = hashlib.sha256()
      for _ in range(ticks):
          engine.update(1/60)
          for hero in sorted(engine.sim.heroes, key=lambda x: getattr(x, "hero_id", "")):
              t = getattr(hero, "target", None)
              ttype = t.get("type") if isinstance(t, dict) else str(t)
              h.update(repr((getattr(hero,"hero_id",""), round(hero.x,3), round(hero.y,3),
                             str(getattr(hero,"state",None)), str(getattr(hero,"current_intent","")),
                             str(ttype), int(getattr(hero,"gold",0)))).encode())
          econ = engine.sim.economy
          h.update(repr((len(econ.transaction_log), econ.total_spent_by_heroes,
                         engine.sim.spawner.wave_number)).encode())
      return h.hexdigest()
  # Record the current digest as a module constant; assert equality. (03/06 must keep it identical.)
  ```
- **Shopping-purchase parity (pins Move 6 — GREEN on current code).** Construct a hero with known gold next to a shop with known items (or drive `do_shopping`/`handle_shopping` directly). Record the resulting `hero.gold`, potions/weapon/armor, the `economy.transaction_log` entries (hero/item/price/tax), and `economy.total_spent_by_heroes`. Assert they equal a reference. This is the contract Move 6 must preserve exactly (including multi-item gold gating).
- **AiGameView-purity (pins Move 5 — written to go GREEN AFTER Move 5; mark `xfail`/skip on current code with a comment).** After Move 5, the object the sim hands the AI must (a) have no `economy`/`sim`/`engine` attribute, (b) expose `world` as a `WorldView` (not the live `World`), (c) be constructible without a live engine. Write the assertions now; mark them expected-fail until Wave 2, then 03/06 flip them green.
- **Frame-state (pins Move 4 — GREEN after Wave 1).** Assert that after `build_snapshot()` drops presentation kwargs, the `RenderSnapshot` exposes entity tuples + DTO tuples and the `PresentationFrameState` exposes camera/zoom/paused/selection. Write a placeholder that imports the (post-W1) names; mark expected-fail until Wave 1.
- **Snapshot-no-mutation (extend WK66).** Confirm the WK66 `test_wk66_render_boundary.py` / `test_wk65_snapshot_no_mutation.py` still pass after the split (run them; do not duplicate).

**Verify:** `python -m pytest tests/test_wk67_ai_boundary.py -q` (parity + digest GREEN on current code; purity/frame-state marked xfail) · `python -m pytest tests/test_wk66_render_boundary.py tests/test_wk65_snapshot_no_mutation.py -q` (still GREEN). Record the baseline scenario list + commands + the recorded digest/parity reference values in your log. **DO NOT COMMIT.**

### Gate 0 — Agent 11 confirms the net is green on current code (digest + parity GREEN; purity/frame-state xfail-as-designed) and the baseline is captured. If a "GREEN-on-current" pin can't go green, the pin is wrong — fix the pin to describe *current* behavior, not the code.

---

# Wave 1 — Move 4: presentation-split (L6), no behavior change

## Agent 03 (TechnicalDirector) — split `PresentationFrameState` out of the sim snapshot (Intelligence: HIGH)

**Files you own:** `game/sim/snapshot.py`, `game/sim_engine.py` (`build_snapshot` only this wave), `game/engine.py` (the `build_snapshot` wrapper `:1487-1518`). **Do not touch `game/graphics/**`** (Agent 10's entry change) beyond confirming the contract.

**Task 1 — define the two dataclasses in `snapshot.py`.** Keep `SimStateSnapshot`'s current 64 fields as the basis. Create:
- `RenderSnapshot` — **sim truth**: the existing live entity tuples (`buildings/heroes/enemies/peasants/guards/bounties/pois/trees/log_stacks`), the WK66 DTO tuples (`hero_dtos/enemy_dtos/peasant_dtos/guard_dtos/tax_collector_dto/building_dtos/bounty_dtos`), `world`, `fog_revision`, `gold`, `wave`, `buildings_construction_progress`, `castle`, `tax_collector`, `vfx_projectiles`, `underground_areas`, `rubble_records`, `sim_blend_fraction`, `sim_tick_id`. **(Keep the live tuples — Ursina still reads them. This is NOT the DTO-finish.)**
- `PresentationFrameState` — **engine-built presentation**: `camera_x`, `camera_y`, `zoom`, `default_zoom`, `screen_w`, `screen_h`, `paused`, `running`, `pause_menu_visible`, `selected_hero`, `selected_building`.
  ```python
  @dataclass(frozen=True)
  class PresentationFrameState:
      camera_x: float = 0.0
      camera_y: float = 0.0
      zoom: float = 1.0
      default_zoom: float = 1.0
      screen_w: int = 1920
      screen_h: int = 1080
      paused: bool = False
      running: bool = True
      pause_menu_visible: bool = False
      selected_hero: object | None = None
      selected_building: object | None = None
  ```
- Grep first: `rg -n "SimStateSnapshot" game ai tools tests`. If anything **other than** the two renderer entries (10 updates this wave) + tests (11) imports it, keep `SimStateSnapshot` as a thin back-compat alias/subclass that composes both (so non-renderer consumers don't break). Otherwise replace it with `RenderSnapshot`. Record the grep + your decision in your log.

**Task 2 — `SimEngine.build_snapshot` drops presentation kwargs, returns `RenderSnapshot`.** Remove `screen_w/screen_h/camera_x/camera_y/zoom/default_zoom/paused/running/pause_menu_visible/selected_hero/selected_building` from the signature (`sim_engine.py:445-462`). Keep `vfx_projectiles`, `sim_blend_fraction`, `sim_tick_id` (these are passed-in frame data the sim doesn't own but the snapshot carries — coordinate: `sim_blend_fraction`/`sim_tick_id` are presentation timing, so they move to `PresentationFrameState`; `vfx_projectiles` is sim-effect data and stays on `RenderSnapshot`). The sim does not know about cameras, pause, screen size, or selection. Populate `RenderSnapshot` with the entity/DTO tuples exactly as today (`:479-532`).

**Task 3 — `GameEngine` builds `PresentationFrameState` and passes both.** In `engine.py` (the `build_snapshot` wrapper `:1487-1518`): build `PresentationFrameState` from engine-owned camera/window/pause/selection state, call `self.sim.build_snapshot(vfx_projectiles=..., sim_tick_id=...)` for the `RenderSnapshot`, and pass **both** to the renderer's `update()`. Coordinate the exact signature with Agent 10: the contract is `renderer.update(render_snapshot: RenderSnapshot, frame: PresentationFrameState)`. Selection (`gs["selected_hero"]`/`selected_building`) for presentation comes from `self.selected_*` (the ID-resolved `SelectionState`), exactly as the dict path does today (`engine.py:1471-1481`).

**Verify (Wave 1):**
```powershell
rg -n "SimStateSnapshot" game ai tools tests            # confirm only intended references remain
python -c "import game.sim.snapshot; import game.sim_engine; import game.engine"
python -m pytest tests/test_wk67_ai_boundary.py -q       # frame-state pin now GREEN; AI digest unchanged
python -m pytest -q                                      # full suite GREEN
python tools/determinism_guard.py --paths game/sim_engine.py game/sim/snapshot.py game/engine.py
python tools/qa_smoke.py --quick
```
Update your log with the split field lists, the `SimStateSnapshot` grep + decision, and gate results. **DO NOT COMMIT.**

## Agent 10 (PerformanceStability) — adapt the renderer entries to the split snapshot (Intelligence: MEDIUM)

**Files you own:** `game/graphics/ursina_renderer.py` (the `update()` entry only), `game/graphics/pygame_renderer.py` (entry), `game/graphics/render_coordinator.py` (only if it forwards the snapshot to a renderer).
- Change each renderer `update()` to accept `(render_snapshot, frame: PresentationFrameState)` per Agent 03 Task 3. Read camera/zoom/paused/screen/selection from `frame`; read entities/DTOs/world/fog from `render_snapshot`. This is a **mechanical read-site change** — wherever the renderer read `snapshot.camera_x`/`snapshot.paused`/`snapshot.selected_hero`/`snapshot.screen_w`, read `frame.*`; everything else stays `render_snapshot.*`. **Do not alter any draw logic.** Do not migrate any live tuple to a DTO this wave (that is the deferred render last-mile).
- Grep your read sites first: `rg -n "snapshot\.(camera_x|camera_y|zoom|default_zoom|paused|running|pause_menu_visible|screen_w|screen_h|selected_hero|selected_building)" game/graphics`. Every hit moves to `frame.`.

**Screenshot verification (MANDATORY — this is a render-touching wave).** Re-capture every Wave-0 path into `docs/screenshots/wk67_after_w1/` and compare to `docs/screenshots/wk67_baseline/`. Per-path verdict (alignment/layering first, then content): **base overview identical; UI panels identical; units/buildings/fog identical.**
```powershell
python tools/run_ursina_capture_once.py --scenario base_overview --ticks 480 --out docs/screenshots/wk67_after_w1/ursina_base --no-llm
python tools/capture_screenshots.py --scenario base_overview --seed 3 --out docs/screenshots/wk67_after_w1/pyg_base --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario ui_panels --seed 3 --out docs/screenshots/wk67_after_w1/pyg_panels --size 1920x1080 --ticks 480
```
If anything differs, revert and report — do not "fix" by changing behavior.

**Verify:** `python -m pytest -q` · `python tools/qa_smoke.py --quick`. Update your log with the read-site grep + per-path screenshot verdict. **DO NOT COMMIT.**

### Gate 1 — Agent 11 + 09 + 04 (Intelligence: 11 HIGH, 09 LOW, 04 MEDIUM)
- 11: full suite GREEN · frame-state pin GREEN · AI-decision digest **unchanged** · `determinism_guard` PASS · `qa_smoke --quick` PASS · diff every render-touching path vs baseline — verdict per path. Any diff → report, do not pass.
- 09: independent visual cohesion verdict on the Wave-1 screenshots.
- 04: `determinism_guard` repo-wide PASS; confirm AI digest byte-identical. **DO NOT COMMIT.**

---

# Wave 2 — Move 5: `AiGameView` + read-only `WorldView` (L3 read side)

## Agent 03 (TechnicalDirector) — author the AI view + builder; delete dead stubs (Intelligence: HIGH)

**Files you own:** `game/sim/ai_view.py` (new), `game/sim_engine.py` (add `build_ai_view`; delete `selected_*` stubs). **Do not touch `ai/**`** (Agent 10... → Agent 06's lane).

**Task 1 — `game/sim/ai_view.py` (new).** Define a read-only `WorldView` and a frozen `AiGameView`. The `WorldView` must expose exactly what the AI + the navigation helpers call (enumerated from the 16 `world` read sites + `best_adjacent_tile`'s usage). The verified read surface is: `width`, `height`, `world_to_grid(wx,wy)`, `grid_to_world(gx,gy)`, `is_walkable(gx,gy)`, `is_buildable(gx,gy)`, the visibility grid (read), and being acceptable as the `world` arg to `navigation.best_adjacent_tile(world, ...)` (which duck-types `world.is_walkable`/`world_to_grid`/etc.).
```python
"""WK67 Round A-2: read-only AI views. The sim builds these; ai/ consumes them.
The AI MUST NOT be able to mutate sim state through this — WorldView wraps the
live World privately and exposes only reads; AiGameView carries NO economy/sim/engine."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

class WorldView:
    """Read-only facade over the live World for AI navigation/visibility.
    Drop-in for `world` wherever the AI passed it (navigation helpers duck-type these)."""
    __slots__ = ("_world", "width", "height")
    def __init__(self, world: Any):
        self._world = world
        self.width = world.width
        self.height = world.height
    @property
    def visibility(self):              # read-only grid access (AI never writes it today)
        return self._world.visibility
    def world_to_grid(self, wx, wy):   return self._world.world_to_grid(wx, wy)
    def grid_to_world(self, gx, gy):   return self._world.grid_to_world(gx, gy)
    def is_walkable(self, gx, gy):     return self._world.is_walkable(gx, gy)
    def is_buildable(self, gx, gy):    return self._world.is_buildable(gx, gy)
    # Add EXACTLY the other read methods the grep below shows the AI/nav helpers calling — no more.

@dataclass(frozen=True)
class AiGameView:
    world: WorldView
    heroes: tuple              # live entities (AI-side DTOs deferred; AI reads, never writes)
    enemies: tuple
    buildings: tuple
    bounties: tuple
    pois: tuple
    player_gold: int           # immutable fact (was the live economy)
    castle: Any                # read-only; consider a small frozen CastleFacts if the AI only reads scalar fields
    wave: int
    # NOTE: NO economy, NO sim, NO engine.
```
Before finalizing `WorldView`'s method list, **grep the exact call surface** so you neither under- nor over-expose: `rg -n "world\.[a-z_]+\(|world\.visibility|world\.width|world\.height" ai game/entities/hero.py` and `rg -n "def best_adjacent_tile|def step_towards|def compute_path" game/systems/navigation.py` (read what `best_adjacent_tile` reads off `world`). Paste the surface into your log; `WorldView` exposes that set and nothing else.

**Task 2 — `SimEngine.build_ai_view()` (new) in `sim_engine.py`.** Returns an `AiGameView` built from sim state — `WorldView(self.world)`, `tuple(self.heroes)`, etc., `player_gold=self.economy.player_gold`, `castle=<castle>`, `pois=...`, `wave=self.spawner.wave_number`. This is the AI-facing builder; it is **separate** from `get_game_state()` (which stays the UI dict). Do **not** put camera/screen/selection on it.

**Task 3 — delete the dead `selected_*` stubs.** Remove `self.selected_building/selected_peasant/selected_hero/selected_enemy` from `SimEngine.__init__` (`:137-140`) and the selection reads from `get_game_state()` (`:402,:424,:427,:428`) — the live selection is owned by `presentation/selection_state.py` and the `GameEngine` wrapper already overrides those keys (`engine.py:1471-1481`). Grep `rg -n "\.selected_(hero|building|peasant|enemy)" game/sim_engine.py game/sim` to confirm no sim-internal reader remains. (The audit confirms these are dead: WK66 left them only because they tied to this Move 5.)

**Coordinate with Agent 06:** the `AiGameView` field names + `WorldView` method names are the contract 06 codes against. Lock them in your log before 06 starts (or 06 reads this section).

**Verify (Wave 2):**
```powershell
python -c "import game.sim.ai_view; import game.sim_engine"
python -m pytest tests/test_wk67_ai_boundary.py -q       # purity pin GREEN once 06 migrates; digest unchanged
python -m pytest -q
python tools/determinism_guard.py --paths game/sim_engine.py game/sim/ai_view.py
python tools/qa_smoke.py --quick
```
Update your log with the `WorldView` surface grep, the `AiGameView` field list, and the `selected_*` removal grep. **DO NOT COMMIT.**

## Agent 06 (AIBehaviorDirector) — migrate AI consumers to `AiGameView`/`WorldView` (Intelligence: HIGH)

**Files you own:** `ai/basic_ai.py`, `ai/behaviors/*.py`, `ai/arrival_handlers.py`, and the **two** `game_state.get("world")` read sites in `game/entities/hero.py` (`:897,:913`). **Import `game.sim.ai_view` read-only; do not edit it.**

**Task 1 — change the AI entry to take `AiGameView`.** `BasicAI.update(self, dt, heroes, game_state)` (`basic_ai.py:189`) — the sim already calls this; change the sim's call site (coordinate with 03: the sim passes `build_ai_view()` instead of the dict to the AI). Inside `update`/`update_hero`, replace `game_state` with the typed `view`. Thread `view` down into every behavior.

**Task 2 — migrate the dict reads (verified sites).** For each, swap the source from the dict to the view; the read semantics are identical:
- `game_state.get("world")` → `view.world` (a `WorldView`). Sites: `arrival_handlers.py:181`, `bounty_pursuit.py:88,189,271`, `exploration.py:142,217,240,294`, `journey.py:99,152`, `poi_awareness.py:111`, `hunger.py:79`, `stuck_recovery.py:115`, `hero.py:897,913`. Reads like `world.visibility[gy][gx]` keep working via `WorldView.visibility`; `best_adjacent_tile(world, ...)` accepts the `WorldView` (duck-typed).
- `game_state.get("castle")` → `view.castle`. Sites: `basic_ai.py:206,230`, `exploration.py:37`.
- `game_state.get("sim")` → **remove**. The only AI reader is `poi_awareness.py:334` (`sim.pois`) → `view.pois`. (The `sim` reads in `builder_peasant.py`/`peasant.py` are sim entities, not AI — handled in Wave 3 / left as sim-internal.)
- `game_state.get("buildings")/("enemies")/("heroes")/("bounties")/("gold")` → `view.buildings/enemies/heroes/bounties/player_gold`.
- **Do NOT** touch `game_state.get("economy")` here — that is the Move-6 write path (Wave 3). (If the read of `economy` for a balance check exists, replace with `view.player_gold`; the *writes* wait for Wave 3.)

**Task 3 — confirm zero live-service reads remain in `ai/`.**
```powershell
rg -n "game_state\.get\(.world.\)|game_state\.get\(.sim.\)|game_state\.get\(.engine.\)|game_state\[.engine.\]" ai/   # zero
rg -n "game_state\.get\(.economy.\)" ai/                                                                            # only shopping.py (Wave 3)
```

**Verify (Wave 2):**
```powershell
python -m pytest tests/test_wk67_ai_boundary.py -q       # AI-decision digest IDENTICAL; purity pin GREEN
python -m pytest -q                                      # full suite GREEN (esp. tests/test_ai_*.py)
python tools/determinism_guard.py
python tools/qa_smoke.py --quick
```
The **AI-decision digest must be byte-identical** to Wave 0. If it changed, you altered behavior — revert the offending site and report. Update your log with the per-site migration list + the two greps + the digest verdict. **DO NOT COMMIT.**

### Gate 2 — Agent 11 + 04 + 06 (Intelligence: 11 HIGH, 04 MEDIUM, 06 HIGH)
- 11: full suite GREEN · **AI-decision digest IDENTICAL** to Wave 0 · AiGameView-purity pin GREEN · `determinism_guard` PASS · `qa_smoke --quick` PASS. (No screenshot diff — no visible change; if AI behavior changed it is a bug.)
- 04: `determinism_guard` repo-wide PASS; confirm the AI digest is byte-identical; sign off no nondeterminism introduced by the view swap.
- 06: confirm the two greps return the expected (zero / shopping-only) results. **DO NOT COMMIT.**

---

# Wave 3 — Move 6: `HeroCommand` on the shopping write (L3b write side)

> The shopping loop buys multiple items in priority order and reads `hero.gold` between purchases — so the command applier MUST mutate **synchronously when a command is proposed**, not batch at end-of-tick, or the multi-item gating changes. This is the central correctness constraint of this wave.

## Agent 03 (TechnicalDirector) — `HeroCommand` DTO + sim-owned applier + builder accessor (Intelligence: HIGH)

**Files you own:** `game/sim/hero_commands.py` (new), `game/sim_engine.py` (wire applier + expose a typed lumber accessor), `game/entities/builder_peasant.py` (use the typed accessor). **Do not touch `ai/**`** (Agent 06).

**Task 1 — `game/sim/hero_commands.py` (new).** Model on `HeroTask` (`ai/contracts.py:61-103`) and the direct-prompt applier pattern (`game/sim/direct_prompt_exec.py:52-163`, which is the existing "AI decides → sim commits the mutation" precedent). Define a frozen command + a sim-owned applier + a synchronous sink:
```python
"""WK67 Round A-2: HeroCommand — AI proposes, the sim applies. Closes the L3b write
leak where ai/behaviors/shopping.py mutated economy/hero directly across the boundary."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol

@dataclass(frozen=True)
class HeroPurchaseCommand:
    hero_id: str
    item: dict          # the shop item dict do_shopping currently passes to hero.buy_item
    # (item carries name/price/type; keep it a dict to mirror the current buy_item contract exactly)

class CommandSink(Protocol):
    def propose(self, command: object) -> bool: ...   # returns True if applied successfully

def apply_hero_command(sim: Any, command: object) -> bool:
    """The ONLY place hero purchases mutate state. Mirrors do_shopping's current effect EXACTLY."""
    if isinstance(command, HeroPurchaseCommand):
        hero = sim.find_hero_by_id(command.hero_id)   # add this lookup if absent (by hero_id)
        if hero is None:
            return False
        if hero.buy_item(command.item):               # same call do_shopping made (hero.py:742-779)
            sim.economy.hero_purchase(hero.name, command.item["name"], command.item["price"])  # economy.py:49-62
            return True
    return False
```

**Task 2 — a synchronous `CommandSink` the sim owns, exposed to the AI view.** Add the sink so the AI proposes and the sim applies **immediately**:
```python
class SimCommandSink:
    def __init__(self, sim):
        self._sim = sim
    def propose(self, command) -> bool:
        return apply_hero_command(self._sim, command)   # synchronous: applies now, returns success
```
Add `commands: CommandSink` to `AiGameView` (coordinate with the Wave-2 `ai_view.py`; if Wave 2 already shipped, add the field now) and populate it in `build_ai_view()` with `SimCommandSink(self)`. **Synchronous application is mandatory** (Critical Rule 4).

**Task 3 — typed lumber accessor for builder-peasant.** Replace `builder_peasant.py`'s `game_state.get("sim")` (`:205,:288,:315`) usage. Expose a tiny typed facade on the sim and pass it to the peasant through the sim-internal entity context (NOT the UI dict):
```python
class LumberOps(Protocol):
    def chop_tree_at(self, tx: int, ty: int) -> Any: ...
    def harvest_log_at(self, tx: int, ty: int) -> Any: ...
# SimEngine already implements these methods; expose `self` (or a thin wrapper) as `lumber_ops`
# and hand it to builder_peasant via its update context, replacing game_state.get("sim").
```
In `builder_peasant.py`, call `lumber_ops.chop_tree_at(...)` / `.harvest_log_at(...)` from the typed accessor instead of fishing `sim` out of the dict. Grep after: `rg -n "game_state.get\(.sim.\)" game/entities/builder_peasant.py` → zero.

**Verify (Wave 3):**
```powershell
python -c "import game.sim.hero_commands; import game.sim_engine"
python -m pytest tests/test_wk67_ai_boundary.py -q       # shopping parity + AI digest IDENTICAL
python -m pytest -q
python tools/determinism_guard.py --paths game/sim_engine.py game/sim/hero_commands.py game/entities/builder_peasant.py
python tools/qa_smoke.py --quick
```
Update your log with the applier shape, the sink wiring, and the builder-accessor grep. **DO NOT COMMIT.**

## Agent 06 (AIBehaviorDirector) — shopping proposes a command, not a write (Intelligence: HIGH)

**Files you own:** `ai/behaviors/shopping.py`, `ai/basic_ai.py` (only the wiring needed to reach the sink). **Import `hero_commands` types read-only.**

**Task — convert `do_shopping` (`shopping.py:81-133`).** Today each priority branch does `hero.buy_item(item)` then `economy.hero_purchase(...)` (`:97,:107,:118,:129`). Replace **both** with a single proposal to the sim command sink, preserving the exact priority order and the between-purchase gold gating (the sink applies synchronously, so `hero.gold` updates before the next branch's check — identical behavior):
```python
# BEFORE (shopping.py ~:90-98):
#   if hero.buy_item(item):
#       purchased_types.add("potion")
#       if economy: economy.hero_purchase(hero.name, item["name"], item["price"])
# AFTER:
from game.sim.hero_commands import HeroPurchaseCommand
#   if view.commands.propose(HeroPurchaseCommand(hero.hero_id, item)):
#       purchased_types.add("potion")
```
Remove the `economy = game_state.get("economy")` line and all four `economy.hero_purchase` calls and the direct `hero.buy_item` calls. `do_shopping` now takes the `view` (with `view.commands`) instead of `game_state`. After: `rg -n "economy.hero_purchase|\.buy_item\(" ai/` → zero.

**Verify (Wave 3):**
```powershell
python -m pytest tests/test_wk67_ai_boundary.py -q       # shopping parity GREEN; AI-decision digest IDENTICAL
python -m pytest -q                                      # full suite GREEN (esp. tests/test_ai_shopping*/economy tests)
python tools/determinism_guard.py
python tools/qa_smoke.py --quick
```
The **AI-decision digest AND the shopping-parity pin must be byte-identical** to the recorded references. Any change = revert + report. Update your log with the before/after of `do_shopping` + the two greps + the digest/parity verdicts. **DO NOT COMMIT.**

### Gate 3 — Agent 11 + 04 + 05 (Intelligence: 11 HIGH, 04 MEDIUM, 05 MEDIUM)
- 11: full suite GREEN · **AI-decision digest IDENTICAL** · **shopping-parity pin IDENTICAL** · `determinism_guard` PASS · `qa_smoke --quick` PASS. Any change → report, do not pass.
- 04: `determinism_guard` repo-wide PASS; confirm the digest + parity are byte-identical; spot-run `qa_smoke --quick` twice with seed 3 for identical verdicts. Sign off that synchronous command application preserved tick order.
- 05: review the applier — confirm `economy.hero_purchase` + `hero.buy_item` semantics (tax, gold, inventory) are unchanged vs. the original `do_shopping`. **DO NOT COMMIT.**

> **PM checkpoint (escape hatch):** L3 (read side) is closed at Gate 2 (the bigger structural win). If Gate 3 surfaces a determinism/parity change in Move 6 that can't be resolved quickly, PM may **bank Waves 0-2 + L9 + determinism and defer Move 6 to a follow-up** — a PM call here, not a worker decision.

---

# Wave 4 — L9: invert `game/graphics → tools` runtime imports

## Agent 10 (PerformanceStability) — game-side: create the runtime material module (Intelligence: MEDIUM)

**Files you own:** `game/graphics/kenney_material.py` (new), `game/graphics/ursina_environment.py`, `game/graphics/ursina_prefabs.py`, `game/graphics/ursina_app.py`.

**Task 1 — `game/graphics/kenney_material.py` (new).** Move the render-path helpers here **verbatim** (these are load-bearing at runtime — verified):
- `_apply_gltf_color_and_shading` (from `tools/model_viewer_kenney.py:292-433`) + its sibling helper `_get_factor_lit_shader` + the `_FACTOR_LIT_VERT`/`_FACTOR_LIT_FRAG` shader strings + the `MaterialDebugStats` dataclass it uses. Deps are Panda3D only (no `game.*`, no other `tools.*`) — clean move.
- `apply_kenney_pack_color_tint_to_entity` (`tools/kenney_pack_scale.py:265-275`) + `pack_extent_multiplier_for_rel` (`:162-181`) + their helpers `pack_color_multiplier_for_rel` (`:210-262`), `_norm_rel` (`:144-158`), `_load_merged_survival_only_basenames` (`:104-140`), and the module-level dicts (`_PACK_EXTENT_MULTIPLIER_BY_FOLDER:51-59`, `_PACK_COLOR_MULTIPLIER_BY_FOLDER:64-72`, `_ENV_TREE_COLOR_MULTIPLIER_DEFAULT:77`, `_MERGED_GLB_DEFAULT_MULTIPLIER`). Deps are `ursina.color` (lazy) + stdlib — clean.
**Task 2 — repoint the graphics importers** to the new module:
- `ursina_environment.py:238` → `from game.graphics.kenney_material import _apply_gltf_color_and_shading`
- `ursina_environment.py:254` + `ursina_prefabs.py:225-226` → `from game.graphics.kenney_material import apply_kenney_pack_color_tint_to_entity, pack_extent_multiplier_for_rel`
**Task 3 — the `ursina_app.py` module-top tools imports (`:39-40`).** These are debug/F12 (`tools.ursina_input_debug`, `tools.ursina_screenshot`) but **module-top**, so a frozen build needs them. Two acceptable options (pick the smaller; record which):
- (a) Move `is_ursina_debug_input_enabled`/`print_wk20_input_line` and `save_ursina_window_screenshot`/`next_auto_screenshot_path` into `game/graphics/` (e.g. `game/graphics/ursina_input_debug.py` + `game/graphics/ursina_screenshot.py`) and import from there; have `tools/` re-export (Agent 12).
- (b) Make the imports **lazy + dev-guarded** (inside `if config.DEV_MODE:` or the F12 handler) so a packaged build never imports `tools`. (Simplest if these are only used in debug paths.)

**Verify:**
```powershell
rg -n "from tools|import tools" game/graphics            # zero non-dev-guarded hits
python -c "import game.graphics.kenney_material; import game.graphics.ursina_environment; import game.graphics.ursina_prefabs"
python -m pytest -q
```
Re-capture the Kenney-material scene + base overview into `docs/screenshots/wk67_after_w4/` and confirm **identical** to baseline (the material/tint must render exactly the same). Update your log with the moved-symbol list + the grep + screenshot verdict. **DO NOT COMMIT.** (Sequence: finish this BEFORE Agent 12 repoints tools.)

## Agent 12 (ToolsDevEx) — tools-side: re-import the moved helpers from game (Intelligence: MEDIUM)

**Files you own:** `tools/model_viewer_kenney.py`, `tools/kenney_pack_scale.py`, and (if 10 chose option (a)) `tools/ursina_input_debug.py` + `tools/ursina_screenshot.py`.
- Replace the **definitions** that moved with thin re-exports from `game.graphics.kenney_material` so any other `tools/` caller keeps working: e.g. in `tools/kenney_pack_scale.py`, `from game.graphics.kenney_material import apply_kenney_pack_color_tint_to_entity, pack_extent_multiplier_for_rel, pack_color_multiplier_for_rel  # re-export`. (tools→game is the allowed direction; `tools/model_viewer_kenney.py` already imports `game.graphics.prefab_texture_overrides` at `:458,:744`, so this is consistent and non-circular — verified.)
- Confirm `tools/model_viewer_kenney.py` still runs as a viewer (it calls `_apply_gltf_color_and_shading` — now from game): `python tools/model_viewer_kenney.py --help` (or its smoke entry).

**Verify:** `python -m pytest -q` · `rg -n "def _apply_gltf_color_and_shading|def apply_kenney_pack_color_tint_to_entity" tools` (should show only re-export imports, not duplicate defs). Update your log. **DO NOT COMMIT.**

### Gate 4 — Agent 11 + 09 (Intelligence: 11 MEDIUM, 09 LOW)
- 11: `rg -n "from tools|import tools" game/graphics` = zero (non-dev-guarded) · `python -c "import game.graphics.ursina_app"` works · full suite GREEN · `qa_smoke --quick` + `validate_assets --report` (errors=0) · Ursina material screenshot IDENTICAL to baseline.
- 09: cohesion verdict on the material/tint screenshots (buildings/props tint unchanged). **DO NOT COMMIT.**

---

# Wave 5 — Determinism / capture items

> May overlap Waves 1-4 (different files), but Agent 10's anim-frame work touches `ursina_renderer.py` which Wave 1 also touched — sequence them (Wave-1 entry change first, then this).

## Agent 10 (PerformanceStability) — anim frame index from the sim tick (Intelligence: HIGH) — 04 consult
**Files:** `game/graphics/ursina_renderer.py` (`_compute_anim_frame` `:554-608`), `game/graphics/instanced_unit_renderer.py` (`:214-275`).
- Today the within-clip frame index uses wall-clock: `ursina_renderer.py:571` `now = time.perf_counter()`; `instanced_unit_renderer.py:238` `st["t0"] = time.time()`, `:275` `elapsed = time.time() - st["t0"]`. Under `DETERMINISTIC_SIM` (read at `config.py:123`; the sim already exposes a tick clock via `sim.timebase.now_ms()` / the sim tick counter), derive the elapsed-within-clip from the **sim tick** instead of wall-clock, so a given sim tick always selects the same frame index.
- Keep the wall-clock path for normal (non-deterministic) play (so live animation stays smooth); switch to tick-derived **only** when `DETERMINISTIC_SIM`/capture mode is on. Pass the sim tick into the renderer via the `RenderSnapshot.sim_tick_id` / `PresentationFrameState` already available (Wave 1).
**Verify:** with `DETERMINISTIC_SIM=1`, the anim-frame pin (Agent 11) is reproducible across two runs; without it, live capture still animates. `python -m pytest -q`. Screenshot the combat scene twice and confirm byte-identical (after Agent 12 registers it). Update log. **DO NOT COMMIT.**

## Agent 03 (TechnicalDirector) — `_fog_revision` determinism (Intelligence: MEDIUM)
**File:** `game/sim_engine.py` (`:152` init, `:1317` increment). Make `_fog_revision` deterministic across in-process `GameEngine` builds with the same seed (it should increment only on actual visibility-grid change; eliminate the ±1 cross-instance drift — likely a build-order or observer-timing sensitivity). Pair the investigation note with the WK65 `test_spawner` global-rebind carry-item if same root cause; if it is a genuinely separate cause, record it.
**Verify:** Agent 11's fog-revision pin (two in-process builds, same seed → identical `_fog_revision` sequence) GREEN. `python tools/determinism_guard.py`. Update log. **DO NOT COMMIT.**

## Agent 12 (ToolsDevEx) — registered Ursina melee-combat capture scenario (Intelligence: MEDIUM) — 06/05 consult
**Files:** `tools/screenshot_scenarios.py` (register `ursina_melee_combat` in the `get_scenario` dispatch `:1563-1601` + a `scenario_*` builder), `tools/run_ursina_capture_once.py` (a capture-mode flag if the anim path needs one). Build a scenario that spawns a hero + an enemy **adjacent**, forces an attack tick (consult 05/06 for the correct way to trigger the strike + hurt one-shots), and captures the strike + hurt frame. This is the missing primary-renderer combat coverage that guards the unit-render/anim boundary.
**Verify:** `python tools/run_ursina_capture_once.py --scenario ursina_melee_combat --ticks <n> --out docs/screenshots/wk67_combat --no-llm` produces a strike/hurt frame; run twice with `DETERMINISTIC_SIM=1` → byte-identical. Update log. **DO NOT COMMIT.**

## Agent 11 (QA) — determinism pins (Intelligence: HIGH)
Add to `tests/test_wk67_ai_boundary.py`: the **anim-frame reproducibility** pin (tick-derived index identical across two runs under `DETERMINISTIC_SIM`), the **fog-revision stability** pin (two in-process builds → identical sequence), and a **combat-capture byte-stability** check (the combat scenario captures identically across two runs). Run after 10/03/12 land their changes.

### Gate 5 — FINAL (Agent 11 + 04 + 09) (Intelligence: 11 HIGH, 04 MEDIUM, 09 LOW)
- 11: `python -m pytest -q` (full suite + all wk67/wk66/wk65 pins GREEN) · AI-decision digest + shopping parity IDENTICAL · anim-frame + fog-rev pins GREEN · `determinism_guard` PASS · `qa_smoke --quick` PASS · `validate_assets --report` (errors=0) · combat capture byte-stable ×2 · all render-touching screenshots identical to baseline.
- 04: `determinism_guard` repo-wide PASS; sign off the whole AI-boundary + anim-determinism work introduced no nondeterminism; confirm AI digest byte-identical end-to-end.
- 09: final cohesion verdict (Move-4 signature, L9 material, combat scene).

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| Move 5 view swap changes an AI read subtly → AI-decision digest drifts | Med | `WorldView` exposes the exact grepped read surface; AI-decision digest byte-identical at Gate 2; per-site migration list in 06's log. |
| Move 6 deferred/batched command application changes multi-item shopping gating | **High if naive** | Critical Rule 4: applier is **synchronous** (mutates on `propose`), so `hero.gold` updates between purchases exactly as today; shopping-parity pin byte-identical at Gate 3. |
| Move 6 surfaces a determinism regression that can't be resolved | Med | Escape hatch: bank Waves 0-2 + L9 + determinism (L3 read side already closed) and defer Move 6 — a PM call at Gate 3. |
| Deleting `selected_*` stubs breaks a hidden sim reader | Low | Grep `sim_engine`/`sim` for `.selected_*` first; the `GameEngine` wrapper already overrides those dict keys; audit confirms dead. |
| Move 4 renderer-signature change breaks a read site (camera/paused) | Med | 10 greps every `snapshot.<presentation field>` site; mechanical move to `frame.`; screenshot diff at Gate 1. |
| L9 move changes Kenney material/tint rendering | Low | Verbatim move (Panda3D/ursina-only deps, no circular risk verified); material screenshot identical at Gate 4. |
| anim→tick change makes live animation stutter | Low-Med | Tick-derived path is gated to `DETERMINISTIC_SIM`/capture only; wall-clock path unchanged for normal play. |
| `WorldView` under-exposes a method nav helpers need → crash | Low | 03 greps the exact `world.*` call surface before finalizing; full suite + `qa_smoke` exercise nav. |

## Sprint Success Criteria
- [ ] `PresentationFrameState` exists; `build_snapshot` takes **no** presentation kwargs; renderers take `(render_snapshot, frame)`; screenshots identical (L6 closed).
- [ ] `AiGameView`/`WorldView` consumed by `ai/`; `rg "game_state.get('world'|'sim'|'engine')" ai/` = zero; `selected_*` stubs deleted (L3 read side closed).
- [ ] Shopping proposes `HeroCommand`; `rg "economy.hero_purchase|\.buy_item\(" ai/` = zero; builder-peasant uses a typed accessor (L3b write side closed).
- [ ] `rg "from tools|import tools" game/graphics` = zero (non-dev-guarded); `import game.graphics.ursina_app` works without `tools/` (L9 closed).
- [ ] Anim frame index sim-tick-derived under `DETERMINISTIC_SIM`; `_fog_revision` stable across rebuilds; `ursina_melee_combat` scenario registered + byte-stable.
- [ ] AI-decision digest + shopping-parity pin **byte-identical** before AND after; AiGameView-purity + frame-state pins GREEN; full suite + determinism + qa_smoke + validate_assets green.
- [ ] Every worker log updated with grep outputs + digests + screenshot verdicts + receipt; no commits/pushes by workers.

## Follow-Up Backlog (after WK67)
- **Render last-mile (deferred this sprint):** finish the Ursina-renderer + `instanced_unit_renderer` DTO read-migration (enrich `UnitDTO` with `color`/`is_inside_castle`/`carried_gold`; flatten `building.poi_def` for `BuildingDTO`); then **delete the live entity tuples** from `RenderSnapshot`/`build_snapshot`. Pairs with the `ursina_renderer.py` god-file split (Round B / Move 11 — "split modules consume DTOs").
- **`UiGameView` (deferred):** split the UI-facing `get_game_state()` dict into a typed `UiGameView` and rehome the HUD's `engine` reads (`hud.py:475` audio, `:2208` command-mode) + `sim.event_bus` (`:489`) — pairs with the `hud.py` split (Round B).
- **Sim-internal dict (sim-engine finding):** `SimEngine.update(dt, game_state)` reads the UI dict only for `castle` + forwarding (`sim_engine.py:623,692`); the sim entities (`hero.py`, `peasant.py`) reading `world` via the dict — build a sim-owned `EntityTickContext` and stop threading the UI dict into the sim. (Round B sim-engine extraction.)
- **Full HeroCommand (deferred):** extend the command pattern to the builder-peasant lumber loop and any future AI writes, and add Move 2's "`AiGameView` is JSON-serializable" guard once entity-DTOs land.
- **Round D (AI router):** `TaskRouter`/`TaskProposal`; split `basic_ai.py`/`context_builder.py`/`direct_prompt_validator.py`/`bounty_pursuit.py`/`exploration.py`; `ai/vocab.py`.
- **Carry from WK65/66:** `tests/test_spawner.py` order-dependent global-rebind (pair with fog-rev); presentation wall-clock reads (`render_coordinator.py:236`, `ursina_renderer.py:343`, billboard `perf_counter`).

---

## Kickoff Appendix (ready for Mode-2 transcription — SUBAGENT execution, no orchestrator)

**`pm_send_list_minimal` (waves):**
```
Wave 0:   11 (HIGH)
Gate 0:   11 (HIGH)
Wave 1:   03 (HIGH), 10 (MEDIUM)                       [03 sim/snapshot/engine; 10 renderer entry — different files]
Gate 1:   11 (HIGH), 09 (LOW), 04 (MEDIUM)
Wave 2:   03 (HIGH), 06 (HIGH)                          [03 authors ai_view; 06 migrates ai/* — sequence 03 first]
Gate 2:   11 (HIGH), 04 (MEDIUM), 06 (HIGH)
Wave 3:   03 (HIGH), 06 (HIGH)                          [03 applier+builder; 06 shopping — different files]
Gate 3:   11 (HIGH), 04 (MEDIUM), 05 (MEDIUM)           [ESCAPE HATCH for Move 6]
Wave 4:   10 (MEDIUM) then 12 (MEDIUM)                  [10 creates kenney_material FIRST, then 12 repoints tools]
Gate 4:   11 (MEDIUM), 09 (LOW)
Wave 5:   10 (HIGH), 03 (MEDIUM), 12 (MEDIUM), 11 (HIGH)  [anim→tick / fog_rev / combat scenario — different files]
Gate 5:   11 (HIGH), 04 (MEDIUM), 09 (LOW)
Do NOT send: 02, 07, 08, 13, 14, 15
```
**Intelligence rationale:** 03 high (novel `AiGameView`/`WorldView`/`HeroCommand` contract design, the behavior-sensitive sync-applier, the snapshot split). 06 high (the AI consumer migration + the determinism-fragile shopping rewrite — AI-decision digest must stay byte-identical). 10 medium in Wave 1 (mechanical entry-signature read) and Wave 4 (verbatim helper move), high in Wave 5 (anim-determinism is behavior-sensitive). 11 high throughout (the AI-decision-digest + parity net is the keystone; broad regression). 04 medium (determinism sign-off at every AI gate). 05 medium (economy/shopping semantics review). 09 low (fixed-recipe screenshot cohesion on the few render-touching paths). 12 medium (L9 tools re-export + the new combat scenario).
*Optional:* keep 09 as a standing consult on every screenshot gate for extra visual coverage.

**Universal prompt (template):**
```
You are being activated for the wk67_round_a2_ai_boundary sprint (Round A-2: AI boundary).
Onboard first: read .cursor/rules/01-studio-onboarding.mdc and your agent-NN-*.mdc.
Read your assignment in the PM hub:
.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json
 → sprints["wk67_round_a2_ai_boundary"].rounds[<the round named in your activation>]
Your full task, code-shape examples, and exact verification commands are in:
.cursor/plans/wk67_round_a2_ai_boundary.plan.md  (find your agent's section)
Read the "Critical Design Rules" first. This sprint is BEHAVIOR-PRESERVING: the game must play
identically. The AI-decision digest (DETERMINISTIC_SIM=1, seed 3) MUST stay byte-identical, and the AI
must no longer hold or mutate live sim services (world/economy/sim/engine). HeroCommand applies
SYNCHRONOUSLY when proposed. Additive-first, then migrate, then remove.
After completing your work: (1) update your agent log with evidence (grep outputs, digests, gate results,
screenshot verdicts); (2) run your verification gates; (3) write your completion receipt; (4) report status.
DO NOT COMMIT. DO NOT PUSH.
```
**Execution:** Claude Code Agent-tool subagents on `claude-opus-4-8`, role-onboarded; Agent 01 (parent) evaluates each wave by running the gates (`pytest` / `determinism_guard` / `qa_smoke` / `validate_assets`) and viewing screenshots, and loops fixes back to the owning agent until the Definition of Done holds. **Human gates:** Gate-1/4/5 visual approval, the Gate-3 escape-hatch decision, and the commit/push (PM/Jaimie only).
```
```
