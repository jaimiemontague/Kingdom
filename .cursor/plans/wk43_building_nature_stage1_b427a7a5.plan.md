---
name: wk43_building_nature_stage1
overview: "Kick off the Building & Nature refactor by shipping Stage 1: neutral buildings spawn as unconstructed plots and a dedicated BuilderPeasant constructs them, with minimal renderer differentiation and regression-safe gates."
todos:
  - id: wk43-plan-scope
    content: Confirm WK43 scope = Stage 1 only, Ursina as primary manual smoke target
    status: completed
  - id: wk43-pm-hub-kickoff
    content: Draft PM hub sprint/round entries + per-agent prompts + send order for wk43-building-nature-stage1
    status: pending
  - id: wk43-runbook
    content: Add Jaimie-friendly manual smoke instructions + exact commands to the sprint plan
    status: pending
isProject: false
---

# WK43 Sprint Plan — Building & Nature Refactor (Stage 1)

## Sprint goal (player-facing)
- Neutral buildings (House, Food Stand, Farm) **no longer appear instantly**. They spawn as low-HP **construction plots**, and a **Builder Peasant** spawns from the Castle to walk over and build them to completion.

## Scope (defaults chosen)
- **In-scope**: Stage 1 from `[.cursor/plans/master_plan_building_nature_sprints.md](.cursor/plans/master_plan_building_nature_sprints.md)`.
- **Required for WK43**: **Construction stage prefabs** using the 0%/20%/50% convention (at minimum **Food Stand** + **Farm**; optionally House if aligned with the same pipeline).
- **Out-of-scope for WK43**: Stage 2 dynamic tree growth and Stage 3 lumberjack economy (tree chopping/wood inventory).
- **Manual renderer validation focus**: Ursina (`python main.py --renderer ursina --no-llm`). Pygame smoke is **optional** and should be run **once at the end of the sprint** for regression coverage.

## Definition of Done (must be true to close)
- Neutral buildings (House/FoodStand/Farm) can spawn as **plots** with `is_constructed == False` and `hp == 1`.
- Neutral buildings show **construction stage visuals** (0%/20%/50%) during the build-up phase (Ursina path at minimum).
- A **BuilderPeasant** spawns and completes the plot (building ends as `is_constructed == True`).
- BuilderPeasant **returns to the Castle** after completing its assigned building and then **despawns** (is removed from sim lists) when it reaches the Castle area.
- Fog-of-war includes **peasant LoS radius 6 tiles** (per master plan).
- Gates PASS:
  - `python tools/determinism_guard.py`
  - `python -m pytest tests/`
  - `python tools/qa_smoke.py --quick`
  - `python tools/validate_assets.py --report` (should remain 0 errors; no asset changes expected)

## Work breakdown by file / owner
- **Prefab construction stages (Agent 15 primary; Agent 12 consult if validator requires manifest updates)**
  - `assets/prefabs/buildings/`: add/update neutral-building prefab JSONs for **0%**, **20%**, **50%** construction stages.
    - Minimum set: **Food Stand** and **Farm** stage variants.
  - `[tools/assets_manifest.json](tools/assets_manifest.json)`: update only if `validate_assets` requires explicit listing of new prefab files (Agent 12).

- **Gameplay systems & entities (Agent 05 primary)**
  - `[game/systems/neutral_buildings.py](game/systems/neutral_buildings.py)`: change `tick(...)` signature to accept `peasants` list and spawn BuilderPeasant into sim.
    - Master-plan required signature: `tick(self, dt: float, buildings: list, heroes: list, peasants: list, castle)`.
  - `[game/entities/builder_peasant.py](game/entities/builder_peasant.py)` (new): implement BuilderPeasant state machine (recommended inheritance from `Peasant`).
    - Required lifecycle: `MOVE_TO_PLOT` → `BUILDING` → `RETURN_TO_CASTLE` → `DESPAWN`.
    - Despawn rule: when within a small radius of the Castle (e.g., 1–2 tiles), remove the BuilderPeasant from the sim’s peasant collection.
  - `[game/entities/neutral_buildings.py](game/entities/neutral_buildings.py)`: House/FoodStand/Farm constructors accept `is_constructed: bool = True`; when false set `hp = 1` and `is_constructed = False`.
  - (If needed) `[game/entities/buildings/base.py](game/entities/buildings/base.py)`: ensure `is_constructed` is respected for “usable” state / interactions.
  - **Test**: `[tests/test_builder_lifecycle.py](tests/test_builder_lifecycle.py)` (new) per master plan.

- **Engine/world + renderer wiring (Agent 03 primary)**
  - `[game/sim_engine.py](game/sim_engine.py)`: update call site to pass peasants to NeutralBuildingSystem tick; ensure BuilderPeasant list is updated each tick.
  - `[game/sim_engine.py](game/sim_engine.py)`: update `_update_fog_of_war` to include peasants with radius `r=6` (same structure as hero LoS).
  - `[game/graphics/ursina_renderer.py](game/graphics/ursina_renderer.py)`: map BuilderPeasant to a visually distinct presentation (minimal: green tint / distinct billboard/model selection).

- **Small AI-duration constant add (Agent 06 small patch)**
  - `[ai/behaviors/task_durations.py](ai/behaviors/task_durations.py)`: Stage 1 doesn’t strictly need this, so **skip in WK43** unless BuilderPeasant uses shared duration constants already.

## Integration order (PM send order)
1. **Agent 15 (prefabs)**: deliver 0%/20%/50% construction-stage prefabs for Food Stand + Farm.
2. **Agent 12 (tools, only if needed)**: keep `validate_assets` green if new prefab files require manifest listing.
3. **Agent 05 (implementation, core sim objects)**: BuilderPeasant + plot spawning + **return-to-castle → despawn** lifecycle + tests compile.
4. **Agent 03 (engine + renderer)**: SimEngine tick signature/call-site updates + fog LoS + Ursina visual mapping (green builder) + construction-stage prefab selection during build.
5. **Agent 11 (QA gate run)**: run full gate stack and report exit codes.
6. **Jaimie manual smokes (end-of-sprint)**:

```powershell
python main.py --renderer ursina --no-llm
python main.py --renderer pygame --no-llm
```

## Manual test instructions (Jaimie-friendly)
Run:

```powershell
python main.py --renderer ursina --no-llm
```

Do this:
- Start a new run.
- Watch for a neutral building to appear (House/Food Stand/Farm).
- Confirm it appears as a **plot / under-construction** state (not instantly “finished”).
- Watch for a **Builder Peasant** to walk from the Castle to the plot and construct it.
- After completion, watch the Builder Peasant **walk back to the Castle** and **disappear** (despawn).
- Repeat until you’ve seen at least 2 builds complete.

Verify:
- Plot becomes a completed building without errors.
- No soft-lock (builder doesn’t get stuck permanently).
- Fog reveals slightly around peasants (builder LoS radius feels present).
- During construction, you see **construction-stage visuals** (0%/20%/50%) update at least once before completion (Ursina).

If it fails:
- Copy/paste the last ~30 lines of terminal output.
- Note which building type was being constructed.
- If the peasant gets stuck, screenshot location and say whether the tile was blocked.

(Then once at end):

```powershell
python main.py --renderer pygame --no-llm
```

## Minimal send list (with intelligence)
- **Agent 15 — ModelAssembler_KitbashLead (HIGH intelligence)**: construction-stage prefab JSONs for Food Stand + Farm (0/20/50).
- **Agent 12 — ToolsDevEx_Lead (LOW intelligence)**: update `tools/assets_manifest.json` only if the validator requires explicit listing for new prefab files; keep `validate_assets` green.
- **Agent 05 — GameplaySystemsDesigner (HIGH intelligence)**: BuilderPeasant entity + plot lifecycle + **return-to-castle and despawn** + unit tests.
- **Agent 03 — TechnicalDirector_Architecture (MEDIUM intelligence)**: SimEngine wiring + fog LoS + Ursina mapping for builder tint + construction-stage prefab selection.
- **Agent 11 — QA_TestEngineering_Lead (LOW intelligence)**: run full gate stack and log exit codes.
- **Do NOT send**: 02, 04, 06, 07, 08, 09, 10, 13, 14 (unless a blocker requires them).

## PM hub updates to make at kickoff (Agent 01)
- Add new sprint key: `wk43-building-nature-stage1` to `.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json`.
- Include:
  - `sprint_meta.plan_ref` pointing at this plan.
  - `pm_jaimie_send_order` as above.
  - `pm_agent_prompts["03"|"05"|"11"]` containing the task blocks and required commands.
  - `pm_send_list_minimal.intelligence_by_agent` matching this plan.
