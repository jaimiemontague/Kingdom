---
name: WK37 Stage2 SimEngine Split
overview: "Stage 2 kickoff: split the God-object `GameEngine` into a headless `SimEngine` plus a `PresentationLayer` wrapper (kept in `game/engine.py` for backwards compatibility), while keeping both Pygame and Ursina paths working and all gates passing."
todos:
  - id: wk37-r1-simengine-scaffold
    content: "R1: add `game/sim_engine.py`, move sim-owned initialization into SimEngine, and wire PresentationLayer to own `self.sim` with property forwarding."
    status: pending
  - id: wk37-r2-move-update-loop
    content: "R2: move update loop + fog-of-war + get_game_state/build_snapshot into SimEngine; replace HUD direct calls with EventBus HUD_MESSAGE + presentation subscription."
    status: pending
  - id: wk37-qa-perf-checks
    content: "Post-round validation: Agent 11 gate re-runs after each round; Agent 10 FPS sanity after R2."
    status: pending
isProject: false
---

# WK37 Sprint Plan — Refactor Stage 2: SimEngine + PresentationLayer Split

## Goal
Implement **Stage 2** from `.cursor/plans/master_plan_architecture_refactor.md`: decompose `GameEngine` into:
- **`SimEngine`**: pure simulation core (no UI/camera/display/audio/VFX)
- **`PresentationLayer`**: wraps a `SimEngine` and owns camera/display/UI/render/audio/VFX

Keep **backward compatibility** so existing imports/usages of `GameEngine` still work.

## Non-goals (scope locks)
- No Stage 3 input handler decoupling.
- No renderer extraction (Stage 4).
- No simulation behavior changes (only moving code + adapting message plumbing).

## Definition of Done (acceptance)
- **Sim core**:
  - `SimEngine` can be instantiated and ticked without UI/display/audio.
  - `SimEngine` owns systems + entity lists + sim update loop + fog-of-war update.
  - `SimEngine.get_game_state()` and `SimEngine.build_snapshot()` exist and match current expectations.
- **Presentation**:
  - `PresentationLayer` creates `SimEngine` and then sets up camera/display/UI/audio/VFX.
  - `PresentationLayer.tick_simulation(dt)` delegates to `self.sim.update(dt)` (plus any event flush/presentation chores).
  - Existing `python main.py` and `python main.py --renderer ursina --no-llm` both work.
- **Backward compat**:
  - Existing code that reads `engine.buildings`, `engine.heroes`, etc. continues to work via property forwarding to `self.sim`.
- **Gates**:
  - `python -m pytest tests/` PASS.
  - `python tools/qa_smoke.py --quick` PASS.
  - `python tools/validate_assets.py --report` exits 0.

## Key files (expected to change)
- `[game/sim_engine.py](c:/Users/Jaimie Montague/OneDrive/Documents/Kingdom/game/sim_engine.py)` (new)
- `[game/engine.py](c:/Users/Jaimie Montague/OneDrive/Documents/Kingdom/game/engine.py)` (major refactor)
- Potential small wiring tweaks in:
  - `[main.py](c:/Users/Jaimie Montague/OneDrive/Documents/Kingdom/main.py)`
  - `[game/graphics/ursina_app.py](c:/Users/Jaimie Montague/OneDrive/Documents/Kingdom/game/graphics/ursina_app.py)` (if it should construct/use `SimEngine` directly per master plan note)

## Architecture sketch

```mermaid
flowchart TD
  mainPy[main.py] -->|pygame_path| PresentationLayer
  mainPy -->|ursina_path| UrsinaApp

  PresentationLayer -->|owns| CameraAndUI[Camera_Display_UI_Audio_VFX]
  PresentationLayer -->|owns| SimEngine

  UrsinaApp -->|drives| SimEngine
  UrsinaApp -->|build_snapshot| SimStateSnapshot
  UrsinaApp -->|update(snapshot)| UrsinaRenderer
```

## Execution strategy (two rounds to reduce risk)
Stage 2 is high-risk, so we’ll execute in two sequential rounds, keeping each round shippable.

### Round WK37-R1 — Introduce `SimEngine` and move constructor state
**Owner: Agent 03 (HIGH intelligence)**

- **Task 2-A**: Create `game/sim_engine.py`
  - Start with `SimEngine` scaffolding that mirrors what `GameEngine(headless=True)` needs.

- **Task 2-B**: Move “sim-owned” fields from `GameEngine.__init__` into `SimEngine.__init__` (one block at a time)
  - Per master plan “Moves to SimEngine”: world, event bus, entity lists, systems, selection state, AI controller hookpoints, early nudge state, etc.

- **Task 2-C**: In `game/engine.py`, rename/refactor the old class into **PresentationLayer** (or keep class name but internally treat it as PresentationLayer)
  - Add `self.sim = SimEngine(...)`.
  - Add **property forwarding** for key lists/systems so downstream code remains compatible.

**R1 gates:**

```powershell
python -m pytest tests/
if ($LASTEXITCODE -ne 0) { exit 1 }

python tools/qa_smoke.py --quick
if ($LASTEXITCODE -ne 0) { exit 1 }
```

### Round WK37-R2 — Move update loop + de-tangle HUD messages
**Owner: Agent 03 (HIGH intelligence)**

- **Task 2-D**: Move `setup_initial_state()`, `_update_fog_of_war()`, and the full `update()` orchestration (+ `_update_*` helpers) into `SimEngine`
  - This is mostly mechanical migration.

- **Task 2-E (critical)**: Replace sim→HUD direct calls with EventBus events
  - Master plan “Things that will fight Stage 2” highlights these hotspots:
    - `_route_combat_events()` calling `self.hud.add_message()`
    - `try_hire_hero()` calling `self.hud.add_message()`
  - Convert these to an event emission (e.g. `HUD_MESSAGE`) from SimEngine.
  - PresentationLayer subscribes and calls `hud.add_message()`.

- **Task 2-F**: Move `get_game_state()`, `build_snapshot()` into `SimEngine`
  - PresentationLayer should delegate `get_game_state()` to `self.sim.get_game_state()` for compatibility.

- **Task 2-G**: Ursina path decision
  - Preferred per master plan: `UrsinaApp` eventually constructs `SimEngine` directly.
  - For WK37, choose the **lowest-risk wiring**:
    - Option 1 (lowest change): keep `UrsinaApp` using PresentationLayer for now (if it relies on engine flags/UI surface upload).
    - Option 2 (cleaner): switch `UrsinaApp` to construct `SimEngine` directly and remove reliance on `engine.render_pygame()` (likely spills into Stage 4-ish work).

  **Default for this sprint**: Option 1 (keep UrsinaApp wiring stable), unless the code already allows a clean swap with minimal changes.

**R2 gates + manual smoke:**

```powershell
python -m pytest tests/
if ($LASTEXITCODE -ne 0) { exit 1 }

python tools/qa_smoke.py --quick
if ($LASTEXITCODE -ne 0) { exit 1 }

python tools/validate_assets.py --report
if ($LASTEXITCODE -ne 0) { exit 1 }

python main.py --no-llm
python main.py --renderer ursina --no-llm
python main.py --renderer ursina --provider mock
```

## QA support (parallel, low-risk)
- **Agent 11 (LOW intelligence)**: after each round lands, re-run `python tools/qa_smoke.py --quick` and record PASS/FAIL in agent_11 log.
- **Agent 10 (LOW intelligence, consult)**: after R2, do a quick FPS sanity in Ursina (5 minutes) and report whether anything regressed.

## Send list (with intelligence) and order
- **Round 1:**
  - Agent 03 — TechnicalDirector_Architecture (**HIGH intelligence**) implement R1
  - Then Agent 11 — QA (**LOW intelligence**) gate re-run (post-change)

- **Round 2:**
  - Agent 03 — (**HIGH**) implement R2
  - Then **parallel**:
    - Agent 11 — (**LOW**) gate re-run
    - Agent 10 — (**LOW**, consult) FPS sanity

**Do NOT send to**: 02, 04, 05, 06, 07, 08, 09, 12, 13, 14, 15.

## Notes / known risks
- Stage 2 hotspots are explicitly called out in the master plan under “Things that will fight Stage 2”; keep changes tightly scoped to those.
- Maintain compatibility by forwarding properties in PresentationLayer (engine.buildings → sim.buildings) until Stage 3+ removes engine-attribute reads from InputHandler/UI.
