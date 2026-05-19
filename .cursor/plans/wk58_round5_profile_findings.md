# WK58 Round 5 — Deep Profile Findings (Agent 10)

**Sprint:** `wk58_ursina_entities_overload`  
**Round:** `wk58_w5_deep_profile_agent10`  
**Owner:** Agent 10 (PerformanceStability_Lead)  
**Status:** Diagnosis only — NO code fixes this wave  
**Profile data:** `.cursor/plans/agent_logs/wk58_round5_stage_profile.txt`,
`.cursor/plans/agent_logs/wk58_round5_stage_profile_full.txt`

---

## TL;DR (one paragraph)

After Waves 1-4, the **entity-count side of the problem is fixed** (tracked_props
10,504 → 1,018; enabled_props 10,504 → 193; visible_chunks 225 → 48). FPS is
still 18-19 post-reveal because three CPU-side hot spots inside
`renderer.update()` consume ~22ms / frame and another ~28ms goes to the Panda3D
draw pipeline (mostly the heightmap-displaced ground mesh + the per-fragment
fog/cave shader running over the full screen). The single biggest CPU spend
post-reveal is **`ensure_fog_overlay` at 19.0ms p50** — it runs its full
62,500-iteration Python tile-loop + GPU texture upload **every frame** because
the early-out gate (`_fog_entity is not None`) is broken on the WK53 heightmap
shader path. Fixing only that single gate (one-line change) is expected to
return ~16-18ms / frame and lift post-reveal FPS from 18 to roughly 32-38 by
itself, depending on Panda3D draw pipeline interactions. The second and third
spots together add another ~3ms of cheap mitigations.

---

## Methodology

1. **Per-substage timers** added to `game/graphics/ursina_renderer.py:update()`
   gated behind `KINGDOM_URSINA_STAGE_PROFILE=1` env var (default off — no
   change to production behavior).
2. **Benchmark plumbing**: extended `tools/perf_render_benchmark.py` to harvest
   `renderer._stage_ms_samples` at exit and split them into BEFORE / AFTER
   reveal windows, dropping the first 2-3 post-reveal frames so the
   one-time full-mask re-apply doesn't pollute steady-state numbers.
3. **Profile session**: `python tools/perf_render_benchmark.py --warmup 8 --measure 15`
   with `KINGDOM_URSINA_STAGE_PROFILE=1` + `KINGDOM_URSINA_INSTANCED_TREES=1`
   (default). Two consecutive runs confirm reproducibility.
4. **Cross-check** against Agent 03's prior measurements (Wave 4 close):
   `renderer.update()` total ≈ 24.4ms mean / 27.9ms p90, full frame ~57ms.

### Run results (warm BAM cache)

| Phase | Window | Samples | avg FPS | p50 FPS | p90 FPS | min FPS |
|---|---|---|---|---|---|---|
| BEFORE reveal | 15s | 486-529 | 47-49 | 50-52 | 57-58 | 0.1 (boot) |
| AFTER reveal | 15s | 263-265 | 18.3-18.5 | 19.6-19.8 | 20.9-21.0 | 2.9 |

Entity counts after reveal (confirms Wave 1-4 invariants): tracked_props=1018,
tree_entities=2082, static_batches=1017, chunks=256, enabled_props=193,
enabled_outside_visible_chunks=0, visible_chunks=48.

---

## (a) Ranked Top-5 Hot Spots — AFTER reveal, post-warmup

Costs are p50 / p90 ms per frame from the AFTER-reveal stage profile
(post-warmup, 295-300 sample frames each).

### 1. `ensure_fog_overlay` — 19.0ms p50 / 20.4ms p90 / max 49.8ms

**File:** `game/graphics/ursina_terrain_fog_collab.py:202-353`  
**Called from:** `game/graphics/ursina_renderer.py:820`

**Why so expensive:** the function has an early-out at lines 213-215:

```python
if int(fog_revision) == my_rev and self._r._fog_entity is not None:
    return
```

The condition `self._r._fog_entity is not None` was correct for the legacy
flat-terrain path where a dedicated fog quad existed. **The WK53 heightmap
shader path destroys `_fog_entity` at line 344-351** and uploads the fog
texture as a shader uniform on the terrain mesh instead. After the first
heightmap-path execution, `_fog_entity` stays `None` forever, so the early-out
condition `_fog_entity is not None` always evaluates `False`, so the function
runs its **full body every frame** regardless of `fog_revision` advancing.

Per-frame work being repeated:

- Allocates / re-fills a 250*250*4 = 250,000-byte buffer (62,500 Python loop
  iterations populating tile color from `world.visibility`).
- `pygame.image.frombuffer()` builds an RGBA surface.
- `TerrainTextureBridge.refresh_surface_texture()` uploads it to GPU.
- Sets the `fog_texture` shader input on the terrain entity (cheap, but on
  every frame).

The before/after delta (4.2ms → 19.0ms p50) is the same gate failure under
heavier GPU contention — at 47 FPS pre-reveal the GPU pipeline absorbs the
upload in flight; at 18 FPS post-reveal it has to serialize against the
heightmap-mesh draw.

**Expected FPS gain when fixed:** ~16-18 ms / frame → 18 FPS post-reveal
becomes ~32-38 FPS (gate fix alone). This is the single largest lever in the
sprint.

---

### 2. `_sync_snapshot_buildings` — 2.7ms p50 / 3.3ms p90 / max 18.8ms

**File:** `game/graphics/ursina_renderer.py:885-1100` (definition);
called from `:847`

**Why so expensive:** Iterates `snapshot.buildings` every frame (~50-150
buildings in steady state including POIs, lairs, plots). For each visible
building:

- Resolves the prefab path (`_resolve_prefab_path` → string lookups + dict
  fallbacks).
- `_resolve_construction_staged_prefab` re-evaluates construction state.
- `sync_prefab_building_entity` re-applies scale (dirty-checked), but
  **`ent.position` is set unconditionally** every frame
  (`ursina_entity_render_collab.py:249`), and **`ent.color`** is also reset
  every frame (`:250-255`).
- `_sync_building_worldspace_ui` syncs label / HP bar / gold display per
  building.
- `_apply_poi_mystery_state` is a no-op stub but is still called.
- `_entity_in_view` frustum check fires per building, which is cheap.

Setting `ent.position` in Panda3D updates the NodePath transform even when
the value is unchanged — that triggers scene-graph dirty propagation and
bounding-volume invalidation in the cull pass.

**Expected FPS gain when fixed:** position/color dirty checks + skipping
`_apply_poi_mystery_state` no-op + caching prefab path lookup ≈ ~1.5-2ms /
frame → +0.5-0.7 FPS.

---

### 3. `_sync_snapshot_heroes` — 0.56ms p50 / 0.74ms p90

**File:** `game/graphics/ursina_renderer.py:1229-1354`  
**Called from:** `:852`

**Why so expensive:** even with 0 heroes in the benchmark scenario, the
function still runs 0.56ms per frame. With the standard scenario (1-10
heroes), this rises proportionally. Per hero, the atlas-billboard path
(`_sync_unit_atlas_billboard`) does a per-frame `terrain_y` lookup
(bilinear interp via `get_terrain_height`), HP-bar entity sync, and child
entity show/hide. The atlas appearance key dirty-check already prevents the
texture/UV stomps, but **`ent.position` and the HP bar entities are touched
unconditionally**.

**Expected FPS gain when fixed:** ~0.2-0.5ms / frame for typical hero count.
Small lever in the perf benchmark (no heroes), bigger in real gameplay
with 5-10 heroes.

---

### 4. The heightmap-displaced ground mesh draw + terrain_fog_shader fragment cost

**Files:** `game/graphics/ursina_terrain_fog_collab.py:1180-1335`,
`game/graphics/terrain_fog_shader.py:1-101`

**Why so expensive:** this cost is **not** in `renderer.update()` — it shows
up as ~25-30ms / frame in the Panda3D draw pipeline (the gap between
renderer.update total ~22ms and the ~50ms full frame).

- The mesh has 62,500 vertices and ~124,002 triangles, rendered double-sided
  with `terrain_fog_shader`. Vertex throughput is not the issue; modern
  hardware shrugs it off.
- **Fragment shader cost** is the real spend. The fragment shader runs
  per-screen-pixel for every fragment the mesh covers (which is most of the
  screen). Per fragment it does:
  - 2 texture samples (grass albedo + fog texture).
  - **8 separate `distance(v_fog_uv, cave_entrance_N)` calls**
    (`terrain_fog_shader.py:63-71`).
  - A `min(min(...))` chain to find the closest cave entrance.
  - A `mix(terrain.rgb, fog.rgb, fog.a)` blend.
  - `discard` and edge-fade math for cave holes.
- At 1920×1080 the mesh covers ~80-90% of the screen → ~1.6M fragments /
  frame each running 8 distance() + min() chains. On an integrated GPU this
  is the dominant fragment workload.
- The cave-entrance code is **dead** anyway: `update_cave_entrance_shader`
  (terrain_fog_collab.py:1337-1345) has been disabled by an early `return`;
  the defaults pin all 8 entrances at `(99, 99)` (off the [0,1] UV range)
  and `cave_hole_radius=0`. The shader still does the math every fragment.

**Expected FPS gain when fixed:** removing the dead cave-entrance code path
from the fragment shader is **almost free** (compile-time conditional or
literal-folding of constants). Expected ~3-6 ms / frame off the fragment
budget on an integrated GPU.

---

### 5. `sync_dynamic_trees` p90 spike — 1.1ms p90 / 2.6ms max (low p50 of 0.002ms)

**File:** `game/graphics/ursina_terrain_fog_collab.py:1422-1585`  
**Called from:** `game/graphics/ursina_renderer.py:816`

**Why this is on the list:** the median is fine (0.002ms — the function
throttles to every 4th tick at line 1437). But the p90 is 1.1ms and the
"dirty growth dict" comparison at line 1545 (`growth_by_tile == last_growth`)
walks all ~2,083 entries every 4th frame. The max of 2.6ms shows the
worst-case shape.

This is a **lower priority** spot than 1-4 above, but a cheap pre-check
(compare lengths / use an int hash of the growth dict) would flatten the
p90 spike. Not a needle-moving fix alone, but a quality-of-life smoothing.

**Expected FPS gain when fixed:** ~0.1-0.3ms / frame smoothing (does not
change avg FPS materially).

---

### Why "GPU draw" is in slot 4 and not slot 1

`ensure_fog_overlay` at 19ms p50 dwarfs the GPU draw cost. The GPU draw is
the remaining ceiling AFTER the Python-side regression is fixed. If we
ranked by total cost the order would be:

1. `ensure_fog_overlay` (CPU + GPU upload): 19.0ms
2. GPU draw pipeline (incl. heightmap mesh + fog/cave shader): ~25-30ms 
3. `_sync_snapshot_buildings` (CPU): 2.7ms
4. `_sync_snapshot_heroes` (CPU): 0.5ms (more with heroes)
5. `sync_dynamic_trees` p90: 1.1ms

But the GPU draw is harder to attack and depends on hardware. The
`ensure_fog_overlay` gate is a one-line fix with a huge return. **Always
fix the cheap-effort big-win lever first.**

---

## (b) Candidate Mitigations Per Spot

Conventions: **S** = ≤1 wave, **M** = 1-2 waves, **L** = 3+ waves / spike;
**LOW** / **MED** / **HIGH** risk; FPS gain is rough estimate at this
profile point.

### Spot 1: `ensure_fog_overlay` runs every frame (post-reveal 19ms p50)

#### 1.A — Fix the early-out gate to recognise the heightmap path (**RECOMMENDED**)

- **Description:** change the early-out at
  `ursina_terrain_fog_collab.py:213-215` from
  `_fog_entity is not None` to `_fog_entity is not None or _terrain_ground_entity is not None`.
  After the first heightmap-path run, `_terrain_ground_entity` is set and
  the gate correctly skips rebuilds when `fog_revision` is stable.
- **Effort:** **S** (one line + comment update + manual fog screenshot
  verification).
- **Risk:** **LOW** — pre-WK53 fallback path (flat terrain) is untouched;
  shader-path skips correctly because rev numbers advance only when actual
  visibility changes (sim_engine.py:1108 dirty-check on revealer movement).
- **Estimated FPS gain:** **+16-18ms / frame** → 18 FPS → ~32-38 FPS
  post-reveal.

#### 1.B — Lazy fog texture refresh on dirty-mask only

- **Description:** instead of rebuilding the whole 250×250 byte buffer when
  `fog_revision` advances, track a `_dirty_tiles: set[(tx, ty)]` and write
  only those bytes into the existing buffer.
- **Effort:** **M** (~1 wave for the dirty-tile plumbing + tests for fog
  edges).
- **Risk:** **MED** — fog-of-war is a high-visibility system; off-by-one
  errors in dirty-tracking can leave permanent stale tiles.
- **Estimated FPS gain:** +1-3ms / frame on top of 1.A (only matters during
  active fog flips; idle gameplay has zero extra benefit). **Skip unless
  1.A doesn't close the gap.**

#### 1.C — Pre-pack the SEEN/UNSEEN row bytes into a numpy array

- **Description:** move the 62,500-iteration Python tile loop
  (`for ty: for tx: buf[o:o+4] = px`) into a numpy vectorised path using
  `numpy.choose` or LUT slicing.
- **Effort:** **S** (~half a wave).
- **Risk:** **LOW**.
- **Estimated FPS gain:** modest — without 1.A it's still being called
  every frame so saves ~1-2ms; with 1.A it almost never runs so saves zero.
  **Skip unless 1.B is being implemented anyway.**

---

### Spot 2: `_sync_snapshot_buildings` (2.7ms p50)

#### 2.A — Position/color dirty checks (**RECOMMENDED**)

- **Description:** in `ursina_entity_render_collab.py:249` and `:250-255`,
  add `_ks_last_position` and `_ks_last_color` caches (parallel to the
  existing `_ks_last_scale` cache at :245). Skip the assignment when the
  value is unchanged.
- **Effort:** **S** (a few lines per setter).
- **Risk:** **LOW** — same pattern already used for scale at
  `_ks_last_scale`.
- **Estimated FPS gain:** ~1.5-2ms / frame off `_sync_snapshot_buildings`
  → +0.5-0.7 FPS.

#### 2.B — Cache `_resolve_prefab_path(bts, b)` per `(bts, construction_state)` for the frame

- **Description:** the prefab path resolver is called per-building per
  frame. For most buildings the path is stable. A dict on the renderer
  instance scoped to the frame would short-circuit redundant lookups.
- **Effort:** **S**.
- **Risk:** **LOW** — cache invalidates naturally on next tick.
- **Estimated FPS gain:** ~0.3-0.5ms / frame.

#### 2.C — Skip iteration entirely for off-screen buildings

- **Description:** currently every building gets the POI checks, frustum
  check, etc. even though only the in-frustum ones do real work.
  Pre-compute the visible-rect → buildings list once per frame (e.g. via
  a tile bucket).
- **Effort:** **M** (touches `_entities` lifecycle; needs care for
  building destroy).
- **Risk:** **MED** — risk of leaving stale enabled flags on
  newly-out-of-frustum buildings.
- **Estimated FPS gain:** ~0.5-1ms / frame in a populated kingdom.
  **Defer until 2.A is in.**

---

### Spot 3: `_sync_snapshot_heroes` (0.56ms p50 with 0 heroes)

#### 3.A — Position dirty check on heroes / HP-bar gating (**RECOMMENDED**)

- **Description:** parallel to 2.A. The atlas path already dirty-checks
  appearance via `_ks_last_appearance_key`; extend that to position
  (`_ks_last_pos`) and to HP-bar child entity updates (only touch when
  hp/max_hp changes).
- **Effort:** **S**.
- **Risk:** **LOW**.
- **Estimated FPS gain:** ~0.2-0.5ms / frame at 5-10 heroes.

#### 3.B — Cache `get_terrain_height(wx, wz)` per (wx, wz) tile cell

- **Description:** heroes call `get_terrain_height` every frame even when
  stationary. A simple {(tile_x, tile_y) → height} cache invalidated only
  when the heightmap changes (rare) would skip the bilinear interp.
- **Effort:** **S**.
- **Risk:** **LOW** — heightmap is generated once at world boot and
  flattened at building placements (cache invalidation is per-event).
- **Estimated FPS gain:** ~0.1-0.2ms / frame at 5-10 heroes.

---

### Spot 4: Heightmap ground mesh fragment shader (GPU ~25-30ms / frame)

#### 4.A — Strip dead cave-entrance code from `terrain_fog_shader` (**RECOMMENDED**)

- **Description:** `update_cave_entrance_shader` (terrain_fog_collab.py
  :1345) has an early `return` and the shader defaults pin all entrances
  off-screen. Replace the 8-call distance + min chain with a single
  `if (cave_hole_radius > 0.0)` guard so the GPU compiler can fold out
  the dead path. Or remove the cave-entrance uniforms entirely and bring
  them back only when the underground feature ships.
- **Effort:** **S** (one shader edit; visual regression test against
  current screenshots).
- **Risk:** **LOW** — the path is already dead.
- **Estimated FPS gain:** ~3-6ms / frame on integrated GPUs; smaller on
  discrete.

#### 4.B — Drop fragment shader to a simpler one-texture-multiply path

- **Description:** since the fog texture is now part of every frame, the
  shader is doing two samples + a blend. A single-pass shader that does
  the blend in the texture (CPU side) would let us use Panda3D's default
  shader and the existing static-batch fast path.
- **Effort:** **M** (touches both shader and the texture pipeline in
  `ensure_fog_overlay`).
- **Risk:** **MED** — fog tinting must remain visually identical.
- **Estimated FPS gain:** ~2-4ms / frame.

#### 4.C — Replace ground mesh with `GeoMipTerrain` LOD

- **Description:** swap the 62,500-vert custom mesh for Panda3D's
  `GeoMipTerrain` with mipmap LOD. Reduces vertex count by ~4-16× at
  distance.
- **Effort:** **L** (large rewrite of mesh building + verifying that all
  prop Y-placement queries still match).
- **Risk:** **HIGH** — `get_terrain_height()` is shared with prop / unit
  / building positioning; LOD-driven height changes can cause prop
  hovering or sinking. WK53 deliberately chose the non-LOD path to keep
  this simple.
- **Estimated FPS gain:** ~2-5ms / frame on vertex side. **Not worth the
  risk now.**

---

### Spot 5: `sync_dynamic_trees` p90 spike (1.1ms p90)

#### 5.A — Length + sum hash pre-check before full dict equality

- **Description:** at `ursina_terrain_fog_collab.py:1545`, before
  `growth_by_tile == last_growth`, compare `len()` and a cheap hash
  (sum of values rounded to 2 decimals). Bypass the full dict walk in the
  common case.
- **Effort:** **S**.
- **Risk:** **LOW**.
- **Estimated FPS gain:** smoothing only; no avg FPS movement.

#### 5.B — Move growth check inside the sapling-spawn loop (no separate dict)

- **Description:** the function already walks `snapshot_trees` once; the
  second `for key, ent in list(ents.items())` walk is for cleanup. Merge
  the dirty detection into a single pass with a sentinel.
- **Effort:** **M**.
- **Risk:** **LOW**.
- **Estimated FPS gain:** ~0.1-0.2ms / frame smoothing.

---

## (c) Recommended Wave 6 Plan

Ranked by **FPS gain per effort**:

### Wave 6 fix-list (in order)

1. **Spot 1.A — Fix `ensure_fog_overlay` early-out gate.**
   **Owner: Agent 03 (TechnicalDirector).**
   - File: `game/graphics/ursina_terrain_fog_collab.py:213-215`.
   - One-line change + comment update.
   - **Acceptance:** post-reveal `ensure_fog_overlay` stage profile p50
     drops from 19.0ms to <0.05ms in steady state; benchmark `after_avg`
     FPS jumps from ~18 to **~32-38 FPS**. New unit test in
     `tests/test_terrain_perf.py` confirms the gate skips when
     `fog_revision == _fog_revision_seen` regardless of
     `_fog_entity` state.
   - **Stop/go after this fix only:** if FPS lands at ≥30 the wave is on
     track; if it lands at ≥45 the wave is **done** and items 2-4 are
     deferred.

2. **Spot 4.A — Remove dead cave-entrance fragment-shader code.**
   **Owner: Agent 03 (TechnicalDirector)** (shader + dead-code removal).
   - Files: `game/graphics/terrain_fog_shader.py:42-83`, optional
     follow-up in `ursina_terrain_fog_collab.py:1337-1345`.
   - Wrap cave-entrance distance/min/discard in
     `if (cave_hole_radius > 0.0) { ... }` so the GPU compiler can fold
     it out, OR strip the uniforms and re-introduce them only when the
     underground feature actually ships.
   - **Acceptance:** screenshot parity with current build (fog edges,
     tile coverage, grass colour unchanged); after_avg FPS gain
     +3-6 FPS measurable in the benchmark.

3. **Spot 2.A — Add position/color dirty checks to `sync_prefab_building_entity`.**
   **Owner: Agent 03 (TechnicalDirector)** (file is under Agent 09's
   art-direction lane but the change is a pure perf refactor that 03
   already touched in WK57; coordinate with 09 if any visual sync
   regression appears).
   - File: `game/graphics/ursina_entity_render_collab.py:249, :250-255`,
     mirror the `_ks_last_scale` pattern at `:245`.
   - **Acceptance:** `_sync_snapshot_buildings` stage p50 drops from
     ~2.7ms to ~0.8-1.0ms. Building label / HP bar / color states still
     correct after damage / construction / repair.

4. **Spot 3.A — Add position dirty check to hero / enemy / peasant / guard atlas billboards.**
   **Owner: Agent 03 (TechnicalDirector)** (same pattern; same lane).
   - File: `game/graphics/ursina_renderer.py:549-551` (already has dirty
     check), extend the same check to non-atlas paths and HP-bar child
     entities at `:1295-1354`.
   - **Acceptance:** at 5-10 heroes, `_sync_snapshot_heroes` stage p50
     stays <0.3ms post-fix.

### Order of operations

- **Step 1 (must do first):** ship and measure 1 by itself. The expected
  gain is so large that the rest of the plan changes shape based on the
  actual measurement.
- **Step 2-4 (do if step 1 lands at <45 FPS):** ship 4.A + 2.A + 3.A as a
  single follow-up package; each is small and they don't interfere.
- **Defer:** 1.B, 1.C, 2.B, 2.C, 3.B, 4.B, 4.C, 5.A, 5.B. Re-measure
  before authorising any of them.

### Stop / go criteria for Wave 6 close

- **GO:** benchmark after_avg ≥ 45 FPS, all 4 pytest tests in
  `tests/test_terrain_perf.py` still PASS, no visual regression in
  `docs/screenshots/perf_round6_*` (capture before/after for fog edges,
  building tinting, hero rendering, tree growth).
- **STOP if:** the fog gate fix changes fog-of-war visibility behaviour
  (e.g. revealed tiles fail to update). In that case revert and switch
  to 1.B (dirty-mask refresh) as the path forward — risk is higher but
  semantics are guaranteed.
- **Hard constraint preserved:** no tree-density cuts, no scatter-stride
  changes. Per Jaimie's WK58 directive.

### Suggested file lanes for the Wave 6 dispatch

- **Agent 03** owns all four fixes; they are all in `game/graphics/`
  and touch architecture-level paths (shader, prefab sync, perf path).
- **Agent 09 (Art Director)** consults on 4.A screenshot parity.
- **Agent 10 (me)** re-runs `python tools/perf_render_benchmark.py
  --warmup 8 --measure 15` with `KINGDOM_URSINA_STAGE_PROFILE=1` after
  each fix lands and reports the new top-5 stage profile.
- **Agent 11** updates `tests/test_terrain_perf.py` to lock the fog
  gate invariant (a new test that asserts
  `_fog_revision_seen` advances exactly once per actual revealer-tile
  move on the heightmap path).

---

## Appendix A — Raw stage profile (AFTER reveal, both runs)

Source: `wk58_round5_stage_profile.txt`, `wk58_round5_stage_profile_full.txt`.

| Stage | Run1 p50 / p90 / max ms | Run2 p50 / p90 / max ms |
|---|---|---|
| 06_ensure_fog_overlay | 18.85 / 19.87 / 37.31 | 19.05 / 20.40 / 49.80 |
| 10_sync_snapshot_buildings | 2.66 / 3.35 / 18.79 | 2.71 / 3.28 / 16.55 |
| 12_sync_snapshot_heroes | 0.56 / 0.75 / 1.48 | 0.56 / 0.74 / 1.19 |
| 05_sync_log_stacks | 0.19 / 0.23 / 8.79 | 0.19 / 0.23 / 10.17 |
| 14_sync_snapshot_peasants | 0.17 / 0.24 / 0.58 | 0.17 / 0.24 / 0.54 |
| 13_sync_snapshot_enemies | 0.05 / 0.08 / 0.20 | 0.06 / 0.09 / 0.15 |
| 08_cull_terrain_chunks | 0.05 / 0.07 / 0.19 | 0.05 / 0.07 / 0.17 |
| 02_get_visible_tile_rect | 0.045 / 0.057 / 0.13 | 0.044 / 0.054 / 0.18 |
| 16_sync_snapshot_tax_collector | 0.021 / 0.043 / 0.075 | 0.022 / 0.042 / 0.096 |
| 18_update_debug_status_text | 0.010 / 0.012 / 2.10 | 0.010 / 0.011 / 2.35 |
| 09_ensure_grid_debug_overlay | 0.008 / 0.009 / 0.025 | 0.008 / 0.009 / 0.038 |
| 19_destroy_removed_entities | 0.006 / 0.008 / 0.073 | 0.006 / 0.008 / 0.214 |
| 04_sync_dynamic_trees | 0.002 / 1.115 / 1.854 | 0.002 / 1.111 / 2.570 |
| 07_sync_visibility_gated_terrain | 0.002 / 0.002 / 0.018 | 0.002 / 0.002 / 0.022 |
| 17_sync_snapshot_projectiles | 0.001 / 0.015 / 0.431 | 0.002 / 0.017 / 0.534 |
| 03_build_3d_terrain | 0.001 / 0.002 / 0.004 | 0.001 / 0.002 / 0.015 |
| 01_ensure_shadow_bounds_once | 0.001 / 0.002 / 0.020 | 0.001 / 0.001 / 0.016 |
| 15_sync_snapshot_guards | 0.001 / 0.001 / 0.024 | 0.001 / 0.002 / 0.005 |
| 11_sync_underground_meshes | 0.001 / 0.001 / 0.002 | 0.001 / 0.001 / 0.019 |

**Sum of CPU-side stages (Run 2):** ~22.9ms p50 — matches Agent 03's
prior renderer.update measurement of 24.4ms mean / 27.9ms p90. The
~28ms gap to the ~50ms full frame is Panda3D draw / cull / present
/ swap.

---

## Appendix B — Instrumentation status

- **Added** (still in repo, off by default):
  - `game/graphics/ursina_renderer.py:778-867` — per-substage timers,
    gated by `KINGDOM_URSINA_STAGE_PROFILE=1` env var. Default off.
  - `tools/perf_render_benchmark.py:_print_stage_profile()` +
    BEFORE/AFTER split logic, gated by the same env var. Default off.
- **Default behaviour:** running `python tools/perf_render_benchmark.py`
  without the env var produces byte-identical output to the pre-Wave-5
  benchmark. `qa_smoke --quick` PASS. The instrumentation is a no-op
  when the flag is unset.
- **Removal path:** if the PM prefers the instrumentation removed
  entirely, the `_stage_profile = os.environ.get(...)` block and the
  19 `if _stage_profile:` lines in `renderer.update` can be ripped out
  in a single follow-up commit. They are explicitly tagged with
  `WK58 Wave 5 (Agent 10) — per-stage profiling`.
