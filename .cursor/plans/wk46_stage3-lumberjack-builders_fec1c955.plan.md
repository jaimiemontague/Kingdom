---
name: stage3-lumberjack-builders
overview: "Implement Stage 3: Builder peasants must gather local wood by chopping visible/seen trees (not UNSEEN fog), spawning a scaled `log_stackLarge` visual pile while chopping/harvesting, then constructing their assigned plot once they have enough wood (House/FoodStand=10, Farm=20)."
todos:
  - id: stage3-scope-decisions
    content: "Lock Stage 3 rules: SEEN/VISIBLE chopping only; yields/costs; 5s/5s timers; runtime model path under assets/models/environment."
    status: pending
  - id: stage3-sim-helpers
    content: Add SimEngine helpers to find/chop/harvest trees and maintain log_stacks list; expose via game_state.
    status: pending
  - id: stage3-builder-state-machine
    content: Extend BuilderPeasant to gather wood locally before building; add tests for yield + build gating.
    status: pending
  - id: stage3-ursina-log-render
    content: Render log_stackLarge.glb as visibility-gated prop keyed by tile; sync from snapshot.log_stacks; scale by growth.
    status: pending
  - id: stage3-qa-evidence
    content: Run qa_smoke --quick and validate_assets --report; capture screenshots or short manual check for log pile lifecycle.
    status: pending
isProject: false
---

# Stage 3 — Builders Start as Lumberjacks (robust implementation plan)

## Goal (player-facing)
- When a **House / Food Stand / Farm plot** auto-spawns, the spawned **BuilderPeasant** first gathers **local wood** by chopping nearby trees, then builds.
- **Wood is per-peasant only** (shown when selecting the peasant), not a player resource.
- **Chopping respects fog-of-war**: peasants may chop only trees on tiles that are **Visibility.SEEN or Visibility.VISIBLE** (never UNSEEN).

## Key decisions (locked from you)
- **Durations**: 5s to chop tree → tree turns into a **log pile model**, then 5s to harvest log pile → log pile disappears.
- **Costs**: House=10 wood, FoodStand=10, Farm=20.
- **Yields by tree growth**:
  - growth ≥ 1.00 → yield 10, log pile scale 1.00
  - growth ≥ 0.75 → yield 7,  log pile scale 0.75
  - growth ≥ 0.50 → yield 5,  log pile scale 0.50
  - growth < 0.50 → cannot chop
- **If no eligible trees are available**: the BuilderPeasant goes to/stands on the assigned plot.

## Architectural approach (minimizes risk + matches existing code)

### 1) Keep “logs” **virtual in sim**, but **rendered in 3D**
- We will **not** make logs a blocking sim entity.
- We **will** keep a tiny, deterministic list in SimEngine like `self.log_stacks` (each has `grid_x, grid_y, scale, expires/active`) purely so renderers can sync without event wiring.
- Ursina will render log piles using the Kenney `log_stackLarge.glb`, keyed by tile like the dynamic tree entities.

### 2) BuilderPeasant becomes a simple state machine
Extend `game/entities/builder_peasant.py` phases to:
- `MOVE_TO_PLOT` (existing)
- `NEED_WOOD` (new: decide next action)
- `MOVE_TO_TREE` (new)
- `CHOPPING` (new: 5s timer)
- `HARVESTING` (new: 5s timer; gain wood; remove log)
- `BUILDING` (existing)
- `RETURN_TO_CASTLE` / `DESPAWN` (existing)

### 3) Tree search + chopping uses world visibility and sim helpers
We add deterministic helpers on `SimEngine` so BuilderPeasant does **not** need to mutate internal dicts directly:
- `SimEngine.find_nearest_choppable_tree_for_builder(from_tx, from_ty) -> (tx,ty,growth)|None`
  - filters by: tile has Tree entity, growth≥0.5, visibility != UNSEEN
  - distance metric: **Manhattan** or **Chebyshev** (pick one and keep consistent; Chebyshev matches a grid feel)
- `SimEngine.chop_tree_at(tx,ty) -> growth`:
  - removes Tree entity from `self.trees`
  - clears world tile from `TileType.TREE` to `TileType.GRASS`
  - updates `_tree_growth_by_tile` immediately
  - creates a `LogStack` record in `self.log_stacks` with `scale=growth`
- `SimEngine.harvest_log_at(tx,ty) -> wood_amount`:
  - removes the `LogStack` record
  - returns yield based on the growth scale

This mirrors how WK45 implemented `remove_trees_in_footprint` to keep world + lookup consistent.

## Concrete file-by-file plan (what to change)

### Agent 05 (Gameplay / systems & entities) — main implementer
**Files to edit**
- `game/entities/builder_peasant.py`
- `game/entities/nature.py` (add a small `LogStack` dataclass/struct)
- `config.py` (add Stage3 constants)

**What to implement**
- Add constants:
  - `BUILDER_CHOP_DURATION_S = 5.0`
  - `BUILDER_HARVEST_DURATION_S = 5.0`
  - `BUILDER_WOOD_COST_HOUSE = 10`, `...FOOD_STAND = 10`, `...FARM = 20`
  - optional: `BUILDER_MIN_CHOP_GROWTH = 0.50`
- Update `BuilderPeasant` to hold:
  - `wood_inventory: int`
  - `required_wood: int` derived from `target_building.building_type`
  - `target_tree_tile: (tx,ty)|None`
  - `action_timer_s: float`
- Behavior rules:
  - If `wood_inventory >= required_wood`: proceed to `MOVE_TO_PLOT`/`BUILDING`.
  - Else: request nearest choppable tree from `game_state["sim"].find_nearest_choppable_tree_for_builder(...)` (see Agent 03 wiring below), or from a callable in `game_state`.
  - If no tree: move to plot and idle (state WORKING/IDLE is fine).
  - When CHOP completes: call sim helper `chop_tree_at(tx,ty)` which spawns a log stack record.
  - When HARVEST completes: call sim helper `harvest_log_at(tx,ty)` and add to `wood_inventory`.

**Unit tests to add (Agent 05)**
- `tests/test_builder_lumberjack_house.py`
  - Set up a SimEngine-like minimal context or directly instantiate BuilderPeasant with a mock `sim` that provides `find_nearest...`, `chop_tree_at`, `harvest_log_at`.
  - Assert: builder does not enter BUILDING until wood >= 10.
- `tests/test_wood_yield_by_growth.py`
  - Verify yields for 0.5/0.75/1.0 growth.

**How Agent 05 verifies**
```powershell
python tools/determinism_guard.py
python -m pytest tests/test_builder_lumberjack_house.py tests/test_wood_yield_by_growth.py
```

### Agent 03 (Tech / engine & renderer wiring) — integration + Ursina visuals
**Files to edit**
- `game/sim_engine.py`
- `game/sim/snapshot.py`
- `game/graphics/ursina_renderer.py` and/or `game/graphics/ursina_terrain_fog_collab.py`
- `game/ui/hud.py` (tiny UI tweak to show wood when peasant selected)

**What to implement in SimEngine**
- Add `self.log_stacks: list[LogStack] = []`.
- Expose sim into peasant update without circular imports:
  - Easiest: include `"sim": self` inside the `game_state` dict returned by `get_game_state()`.
    - This is pragmatic and keeps BuilderPeasant code simple.
- Add the three helper methods (nearest tree, chop, harvest) as described above.
- Ensure `get_game_state()` includes `"trees": self.trees` if needed for UI/debug (optional).
- Ensure `build_snapshot()` (wherever it is) copies `log_stacks` into snapshot as a tuple.

**What to implement in snapshot**
- Add `log_stacks: tuple = ()` to `SimStateSnapshot`.

**Ursina rendering**
- Add a `_log_entities_by_tile: dict[(tx,ty)]->Entity` similar to `_tree_entities`.
- In the terrain collaborator, add `sync_log_stacks(snapshot.log_stacks, world.visibility)`:
  - Create entity at tile center using model path **under `assets/models/environment/`**.
  - Scale = `base_log_scale * log.scale`.
  - Visibility gating: like other vertical props, **enabled only if visibility != UNSEEN**; apply fog tint multiplier when SEEN.
  - Destroy entities for tiles no longer present.

**Important: model path hygiene**
- Do **not** reference the raw “Kenny downloads” path at runtime.
- Instead, copy the user-provided file into:
  - `assets/models/environment/log_stackLarge.glb`
  - This allows `_environment_model_path("log_stackLarge")` to resolve it.

**HUD update**
- In `HUD._render_peasant_summary`, show wood if present:
  - “Wood: X / required” using `getattr(peasant, "wood_inventory", None)`.

**How Agent 03 verifies**
```powershell
python -m pytest tests/
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report
```

**Visual verification (screenshots)**
- Add a screenshot scenario (Agent 12 can help, but Agent 03 can do it if comfortable):
```powershell
python tools/capture_screenshots.py --scenario base_overview --seed 3 --out docs/screenshots/stage3_before --size 1920x1080 --ticks 0
python tools/capture_screenshots.py --scenario base_overview --seed 3 --out docs/screenshots/stage3_after --size 1920x1080 --ticks 1200
```
- Manual run (2–4 minutes):
```powershell
python main.py --renderer ursina --no-llm
```
Verify you can watch a builder: walk to a visible/seen tree, wait ~5s, log pile appears, wait ~5s, log pile disappears, then builder builds plot.

### Agent 09 (Art / visual integration consult) — optional but helpful
- Confirm the log stack scale looks right at 0.5/0.75/1.0.
- If the GLB’s pivot/height is odd, recommend a safe scale multiplier tweak (config constant) rather than re-exporting.

**How Agent 09 verifies**
- Use the same `python main.py --renderer ursina --no-llm` manual check; no code changes required unless asked.

### Agent 11 (QA) — gate validation
**Commands**
```powershell
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report
```
Report exit codes + any flakiness.

## Known risks / pushback (so we don’t get surprised)
- **Raw asset path has spaces** and is meant for archival; runtime should use `assets/models/environment/`.
- Putting `"sim": self` into `game_state` is a pragmatic shortcut; if you’d rather keep sim fully hidden, we can instead pass callables (`find_tree`, `chop`, `harvest`) in the dict.
- **Pathing to “closest tree”**: peasants currently use simple steering; if they get stuck, we’ll need a fallback (e.g., re-pick tree every N seconds).

## Suggested sprint naming (new sprint)
- `wk46-stage3-lumberjack-builders`

## Send list recommendation (so lower-intelligence agents don’t guess)
- Agent 05 — **HIGH intelligence** (state machine + yields + tests)
- Agent 03 — **HIGH intelligence** (SimEngine helpers + snapshot + Ursina log rendering)
- Agent 11 — **LOW intelligence** (run gates)
- Agent 09 — **LOW intelligence (consult)** (visual scale sanity)
