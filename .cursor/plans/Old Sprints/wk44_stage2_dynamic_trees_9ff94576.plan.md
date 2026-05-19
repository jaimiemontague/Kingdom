---
name: wk44_stage2_dynamic_trees
overview: "Implement Stage 2 of the Building & Nature master plan: dynamic tree entities that grow over time, clustered forest generation, and Ursina renderer syncing tree scale to growth (while keeping TileType.TREE on the world grid)."
todos:
  - id: wk44-pm-hub-kickoff
    content: Create wk44 sprint entry in PM hub with send order + per-agent prompts referencing this plan
    status: pending
  - id: wk44-stage2-sim
    content: Implement Tree entity + NatureSystem + deterministic growth + tests (Agent 05)
    status: pending
  - id: wk44-stage2-render
    content: Wire snapshot trees + Ursina tree entity map + sync scales + world blocking rule (Agent 03)
    status: pending
  - id: wk44-gates
    content: Run qa_smoke --quick and validate_assets --report after integration (Agent 11)
    status: pending
isProject: false
---

# WK44 Sprint Plan — Building & Nature Refactor (Stage 2: Dynamic Tree Growth)

## Sprint goal (player-facing)
- The map’s trees become a **living system**: forests spawn in clusters and trees **grow over time** (25% → 50% → 75% → 100% over ~6 minutes).
- In Ursina, trees visually **scale with growth** so the world feels like it changes as the run progresses.

## Scope decisions (locked for this sprint)
- **World representation**: Keep `TileType.TREE` on the terrain grid, but also maintain a parallel **`sim.trees` entity list** for growth + rendering.
- **Blocking rule**: Trees become **blocking at growth ≥ 75%** (25%/50% are non-blocking; 75%/100% block movement/building).
- **Out of scope**: Stage 3 lumberjack economy (chopping/wood inventory), no log entities.

## Definition of Done
- **Nature simulation**:
  - `NatureSystem` exists and advances `Tree.growth_percentage` deterministically.
  - Growth stages hit **0.25/0.5/0.75/1.0** over ~6 minutes simulated time.
- **World generation**:
  - `game/world.py` terrain generation produces **clustered forests** (not per-tile independent noise).
- **Sim snapshot contract**:
  - `SimStateSnapshot` includes a `trees: tuple` field populated from `SimEngine.build_snapshot()`.
- **Renderer (Ursina)**:
  - `UrsinaTerrainFogCollab` retains per-tree `Entity` references keyed by `(tx, ty)`.
  - Each update syncs tree scales based on snapshot `trees` growth.
- **Blocking**:
  - A tree tile is treated as blocking iff its corresponding `Tree.growth_percentage >= 0.75`.
  - `World.is_walkable()` / `World.is_buildable()` respect that rule.
- **Gates PASS**:
  - `python tools/qa_smoke.py --quick`
  - `python tools/validate_assets.py --report` (expected unchanged; still 0 errors)

## Key files (planned changes)
- `[game/systems/nature.py](game/systems/nature.py)` **(new)**
  - Owns deterministic ticking of growth for `sim.trees`.
- `[game/entities/nature.py](game/entities/nature.py)` **(new)**
  - Defines `Tree(grid_x, grid_y, growth_percentage, growth_ms_accum, ...)` (exact fields up to implementer; must be deterministic and snapshot-friendly).
- `[game/sim_engine.py](game/sim_engine.py)`
  - Add `self.trees` list.
  - Tick `NatureSystem` each update.
  - Include `trees=tuple(self.trees)` in `build_snapshot()`.
- `[game/sim/snapshot.py](game/sim/snapshot.py)`
  - Add `trees: tuple` to `SimStateSnapshot`.
- `[game/world.py](game/world.py)`
  - Update `generate_terrain()` to produce **forest clusters**.
  - Update walk/build blocking to use the **growth≥0.75** rule (likely via a world→sim lookup; see “Friction points”).
- `[game/graphics/ursina_terrain_fog_collab.py](game/graphics/ursina_terrain_fog_collab.py)`
  - Store tree entities in a dict: `renderer._tree_entities[(tx, ty)] = ent`.
  - Add `sync_dynamic_trees(snapshot_trees)` to scale each entity to growth.
- `[game/graphics/ursina_renderer.py](game/graphics/ursina_renderer.py)`
  - Call `self._terrain_fog.sync_dynamic_trees(snapshot.trees)` each update.

## Friction points & how we’ll resolve them
- **Tile grid vs entity growth**: We keep `TileType.TREE` for placement/visibility, but blocking depends on growth.
  - Implementation approach: world remains the owner of the tile grid, but it must have access to the current growth for a given `(tx,ty)`.
  - Two viable ways (pick one during implementation; do not invent a third):
    - **A (preferred)**: World gets a lightweight callback/lookup injected from SimEngine (e.g. `world.tree_growth_lookup = lambda tx,ty: ...`).
    - **B**: World stores `self.tree_growth[(tx,ty)] = growth` updated by NatureSystem.

## Tests to add (minimum)
- `[tests/test_nature_growth.py](tests/test_nature_growth.py)` (new)
  - Create a `Tree` at 0.25, tick NatureSystem by 6 minutes simulated time, assert it reaches 1.0 and hits intermediate steps.
- Update/add a small world-gen test if existing harness supports it (optional if too brittle).

## Manual smoke (Jaimie)
Run:

```powershell
python main.py --renderer ursina --no-llm
```

Do this (5–10 minutes):
- Start a run and pan camera to a forested area.
- Let the game run for a couple minutes.
- Observe trees noticeably scaling up over time.

Verify:
- No crashes.
- Trees scale changes are visible.
- Pathing/building respects the rule that small trees don’t block but larger trees do (≥75%).

If it fails:
- Screenshot the location.
- Copy/paste the last ~30 terminal lines.

## Integration order (parallelized)
1. **Agent 05 (core sim)**: add `Tree` entity + `NatureSystem` + sim list; write `test_nature_growth.py`.
2. **Agent 03 (engine/snapshot/world plumbing + Ursina call site)**: snapshot contract (`trees`), tick wiring, world blocking rule hook, call `sync_dynamic_trees` from Ursina update.
3. **Agent 09 (consult-only, medium if needed)**: quick visual sanity on growth scaling multipliers (only if trees look wrong in 3D).
4. **Agent 11 (QA)**: `python tools/qa_smoke.py --quick` and `python tools/validate_assets.py --report`.

## Minimal send list (with intelligence)
- **Agent 05 — GameplaySystemsDesigner (HIGH intelligence)**: new system + entity + deterministic growth + tests.
- **Agent 03 — TechnicalDirector_Architecture (HIGH intelligence)**: snapshot contract change + world blocking hookup + Ursina terrain collab wiring.
- **Agent 11 — QA_TestEngineering_Lead (LOW intelligence)**: run gates + report.
- **Optional consult**: **Agent 09 (MEDIUM intelligence)** if visual scaling needs art judgement.
- **Do NOT send**: 02, 04, 06, 07, 08, 10, 12, 13, 14, 15 (unless a blocker appears).
