---
name: WK36 Stage1 Snapshot Decouple
overview: "Kick off Architecture Refactor Stage 1: introduce `SimStateSnapshot` and decouple `UrsinaRenderer` from `GameEngine` by switching to `renderer.update(snapshot)` with zero `self.engine` references in `ursina_renderer.py`."
todos:
  - id: wk36-r1-snapshot
    content: "Stage 1 R1: add `game/sim/snapshot.py`, implement `GameEngine.build_snapshot()`, add snapshot tests (no renderer migration yet)."
    status: pending
  - id: wk36-r2-renderer
    content: "Stage 1 R2: migrate `UrsinaRenderer` to consume `SimStateSnapshot` + update `UrsinaApp` update loop to pass snapshot; ensure `ursina_renderer.py` has zero `self.engine`."
    status: pending
  - id: wk36-pm-hub
    content: Update PM hub JSON with wk36 sprint + 2 rounds, prompts, gates, and send list with intelligence levels.
    status: pending
isProject: false
---

# WK36 Sprint Plan — Refactor Stage 1: SimStateSnapshot + UrsinaRenderer Decoupling

## Goal
Deliver **Stage 1** of `.cursor/plans/master_plan_architecture_refactor.md`: a typed, immutable `SimStateSnapshot` built by the engine and consumed by Ursina rendering.

After this sprint:
- `game/graphics/ursina_renderer.py` has **zero** `self.engine` usage.
- `UrsinaRenderer` is constructed without an engine reference.
- Ursina path calls `engine.build_snapshot()` each frame and passes it into `renderer.update(snapshot)`.

## Scope constraints
- **No simulation behavior changes** (systems/entities/AI are out of scope).
- **No Stage 2 work** (God Object decomposition) in this sprint.

## Definition of Done (acceptance)
- **Renderer decoupling**:
  - `UrsinaRenderer.__init__` no longer takes `engine`.
  - `UrsinaRenderer.update(snapshot)` accepts a `SimStateSnapshot`.
  - `self.engine` does not appear anywhere in `game/graphics/ursina_renderer.py`.
- **Snapshot contract**:
  - New `game/sim/snapshot.py` defines `@dataclass(frozen=True) SimStateSnapshot` with fields needed by the renderer/app.
  - `GameEngine.build_snapshot()` returns a valid `SimStateSnapshot`.
- **Gates**:
  - `python tools/qa_smoke.py --quick` PASS.
  - `python tools/validate_assets.py --report` exits 0.
- **Manual check (Ursina parity)**:
  - `python main.py --renderer ursina --no-llm` looks identical to pre-refactor (terrain, fog, buildings, units, projectiles).

## Implementation plan (two-round sprint inside WK36)
This is one sprint, but executed in two sequential rounds to reduce risk.

### Round WK36-R1 — Snapshot creation + tests
- **Task 1-A (Agent 03, HIGH)**: Create snapshot dataclass
  - Create `[game/sim/snapshot.py](c:/Users/Jaimie Montague/OneDrive/Documents/Kingdom/game/sim/snapshot.py)`.
  - Use the master plan’s Option A frozen dataclass shape (Stage 1 > Task 1-A). Fields must cover what Ursina needs (entity tuples, `world`, `fog_revision`, selection, projectiles, camera/display basics).

- **Task 1-B (Agent 03, HIGH)**: Add `build_snapshot()` to engine
  - Add `build_snapshot()` to `[game/engine.py](c:/Users/Jaimie Montague/OneDrive/Documents/Kingdom/game/engine.py)` per master plan Stage 1 > Task 1-B.
  - Ensure it’s **render-only** (reads state, no side effects).

- **Task 1-E (Agent 11, LOW)**: Extend snapshot tests
  - Update `[tests/test_renderer_snapshot_contract.py](c:/Users/Jaimie Montague/OneDrive/Documents/Kingdom/tests/test_renderer_snapshot_contract.py)` to add:
    - `test_snapshot_is_frozen()`
    - `test_engine_build_snapshot_returns_valid_snapshot()`
  - Keep these **headless/GPU-free**.

**R1 Gate:**

```powershell
python -m pytest tests/
if ($LASTEXITCODE -ne 0) { exit 1 }

python tools/qa_smoke.py --quick
if ($LASTEXITCODE -ne 0) { exit 1 }
```

### Round WK36-R2 — UrsinaRenderer migration
- **Task 1-C (Agent 03, HIGH)**: Migrate `UrsinaRenderer` off engine
  - Update `[game/graphics/ursina_renderer.py](c:/Users/Jaimie Montague/OneDrive/Documents/Kingdom/game/graphics/ursina_renderer.py)`:
    - `__init__(world)` stores `self._world`.
    - `update(snapshot: SimStateSnapshot)`.
    - Replace all sites listed in `docs/refactor/engine_access_inventory.md` (and the master plan’s Stage 1 list) so no `self.engine.*` remains.
    - Fix the known footgun: `_building_occupied_tiles(engine)` must become `_building_occupied_tiles(buildings)`.

- **Task 1-D (Agent 03, HIGH)**: Wire snapshot into `UrsinaApp`
  - Update `[game/graphics/ursina_app.py](c:/Users/Jaimie Montague/OneDrive/Documents/Kingdom/game/graphics/ursina_app.py)`:
    - Construct renderer via `UrsinaRenderer(self.engine.world)`.
    - Each frame: `snapshot = self.engine.build_snapshot(); self.renderer.update(snapshot)`.

- **Task (Agent 10, LOW consult)**: FPS/parity spot check
  - Run Ursina for 5 minutes and confirm no obvious perf regression from snapshot allocation.

**R2 Gates + manual parity:**

```powershell
python -m pytest tests/
if ($LASTEXITCODE -ne 0) { exit 1 }

python tools/qa_smoke.py --quick
if ($LASTEXITCODE -ne 0) { exit 1 }

python tools/validate_assets.py --report
if ($LASTEXITCODE -ne 0) { exit 1 }

python main.py --renderer ursina --no-llm
```

## Ownership / send list (with intelligence)
- **Agent 03 — TechnicalDirector_Architecture (HIGH intelligence)**
  - Owns `game/engine.py`, `game/sim/snapshot.py`, `game/graphics/ursina_renderer.py`, `game/graphics/ursina_app.py` changes.
- **Agent 11 — QA_TestEngineering_Lead (LOW intelligence)**
  - Owns test additions for `SimStateSnapshot` immutability + engine snapshot validity.
- **Agent 10 — PerformanceStability_Lead (LOW intelligence, consult only)**
  - Quick FPS sanity + “no obvious perf regression”.

**Do NOT send to**: 02, 04, 05, 06, 07, 08, 09, 12, 13, 14, 15 (Stage 1 touches engine/renderer/test only).

## PM hub update (what needs to be added)
Add a new sprint entry to `.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json`:
- `sprints["wk36-refactor-stage1-snapshot-decouple"].rounds["wk36_r1_snapshot_and_tests"]`
- `sprints["wk36-refactor-stage1-snapshot-decouple"].rounds["wk36_r2_renderer_migration"]`

Each round should include:
- `pm_status_summary.gates` (commands above)
- `pm_agent_prompts["03"]`, `pm_agent_prompts["11"]`, `pm_agent_prompts["10"]`
- `pm_send_list_minimal` with intelligence-by-agent

## Universal prompt (for Jaimie to paste)

```text
You are being activated for sprint **wk36-refactor-stage1-snapshot-decouple**.

1) Read the master plan first:
   .cursor/plans/master_plan_architecture_refactor.md
   Section: "Stage 1: SimState Snapshot Interface (Renderer Decoupling)"

2) Read your assignment in the PM hub:
   .cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json
   -> sprints["wk36-refactor-stage1-snapshot-decouple"]
   -> rounds["<your round id>"]
   -> pm_agent_prompts[YOUR_AGENT_NUMBER]

3) After completing your work:
   - Update your agent log
   - Run: python tools/qa_smoke.py --quick (must PASS)
   - If you touched assets/manifest: python tools/validate_assets.py --report
   - Report back with files changed + commands + exit codes
```
