---
name: WK42 renderer dedupe + collaborator wire-in
overview: >
  Finish WK41. The new helper modules (ursina_environment, ursina_prefabs, ursina_coords,
  ursina_units_anim) and collaborator classes (UrsinaTerrainFogCollab, UrsinaEntityRenderCollab)
  were created in WK41 but were never wired — ursina_renderer.py still carries 100% of the
  original code in parallel. This sprint deletes all duplicates and wires the collaborators
  as the live implementation path. No gameplay or behavior change. Target: ursina_renderer.py
  drops from 2,094 lines to ~700 lines.
todos:
  - id: preflight-diff
    content: "Agent 03: Before writing any code, diff each new module function against its counterpart in ursina_renderer.py. If any diverged during WK41, update the module file to match the renderer version (renderer is the working copy). Log findings."
    status: pending
  - id: track-a-module-block-replace
    content: "Agent 03 R1: Delete lines 119-819 (35 module-level functions) from ursina_renderer.py. Replace with import statements from ursina_environment, ursina_prefabs, ursina_units_anim, ursina_coords. Run gates."
    status: pending
  - id: track-a-gate
    content: "Agent 11 R1: Full gate stack after Track A lands."
    status: pending
  - id: track-b-terrain-collab
    content: "Agent 03 R2: Instantiate UrsinaTerrainFogCollab in UrsinaRenderer.__init__. Replace 6 terrain/fog method bodies with self._terrain_fog.* delegation calls. Delete the 6 methods from UrsinaRenderer. Run gates."
    status: pending
  - id: track-b-gate
    content: "Agent 11 R2: Full gate stack. Agent 10 (consult): Ursina FPS spot-check."
    status: pending
  - id: track-c-entity-collab
    content: "Agent 03 R3: Instantiate UrsinaEntityRenderCollab in UrsinaRenderer.__init__. Replace 11 entity-render method bodies with self._entity_render.* delegation. Delete the 11 methods. Run gates."
    status: pending
  - id: track-c-gate
    content: "Agent 11 R3: Full gate stack. Agent 10 (consult): Ursina FPS spot-check. Jaimie manual smokes."
    status: pending
isProject: false
---

# WK42 — Renderer Dedupe + Collaborator Wire-In

## Context

WK41 audit (2026-04-27, Agent 01) found:

- **35 module-level functions** in `ursina_renderer.py` lines 119–819 are exact copies of
  functions that also exist in `ursina_environment.py`, `ursina_prefabs.py`,
  `ursina_units_anim.py`, and `ursina_coords.py`. Neither file imports the other.
- **`UrsinaTerrainFogCollab`** (516 lines) covers 6 UrsinaRenderer methods but is never
  imported or instantiated anywhere.
- **`UrsinaEntityRenderCollab`** (248 lines) covers 11 UrsinaRenderer methods but is never
  imported or instantiated anywhere.
- **`engine_facades/`** is correctly wired — engine.py delegates to `EngineCameraDisplay` +
  `EngineRenderCoordinator`. That work is done and does not need to change.

## Authority

- **Implementer:** Agent 03 (Technical Director) — sole owner of ursina_renderer.py and
  the graphics package.
- **QA:** Agent 11 — full gate stack after each track.
- **Perf consult:** Agent 10 — brief Ursina FPS smoke after R2 and R3.
- **Silent:** all other agents.

## Gate Stack (every round)

```
python tools/determinism_guard.py
python -m pytest tests/
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report   # errors=0; warns baseline OK
```

**End-of-sprint manual (after R3 gates pass — Jaimie):**
```
python main.py --renderer ursina --no-llm     # 5–10 min
python main.py --renderer pygame --no-llm     # 5 min
```

---

## Round WK42-R1 — Track A: Delete module-level duplicate block

**Agent 03 — MEDIUM intelligence**

### Pre-flight (do before any edits)

For each function that exists in both `ursina_renderer.py` (lines 119–819) and a new module,
run a semantic diff. If they are identical: proceed. If any diverged (e.g. a bug fix landed in
one but not the other during WK41), update the **module file** to match the renderer version
(renderer is the working copy because it is the only version that runs), then proceed.

Functions to diff (module → renderer counterpart):

- `ursina_coords.py`: `sim_px_to_world_xz`, `px_to_world`
- `ursina_environment.py`: all 19 functions
- `ursina_prefabs.py`: all 14 functions
- `ursina_units_anim.py`: `_frame_index_for_clip`, `_hero_base_clip`, `_enemy_base_clip`, `_worker_idle_surface`

### Edit

Delete `ursina_renderer.py` lines 119–819 (the entire 35-function module-level block).

Replace with import block at the top of the file (after the existing stdlib/ursina imports):

```python
# ---------------------------------------------------------------------------
# Helpers imported from focused sub-modules (extracted WK41, wired WK42)
# ---------------------------------------------------------------------------
from game.graphics.ursina_coords import sim_px_to_world_xz, px_to_world
from game.graphics.ursina_environment import (
    PROJECT_ROOT,
    _environment_model_path,
    _grass_scatter_jitter,
    _grass_density_budget,
    _grass_tile_selected,
    _grass_clump_offset,
    _environment_mesh_priority,
    _dedupe_env_rels_by_stem,
    _is_grass_scatter_stem,
    _is_doodad_scatter_stem,
    _stem_is_flower_ground_scatter,
    _stem_is_log_or_mushroom_ground_scatter,
    _environment_grass_and_doodad_model_lists,
    _environment_tree_model_list,
    _scatter_model_index,
    _building_occupied_tiles,
    _apply_kenney_scatter_mesh_shading_only,
    _finalize_kenney_scatter_entity,
    _set_static_prop_fog_tint,
    _visibility_signature,
)
from game.graphics.ursina_prefabs import (
    _building_type_str,
    _footprint_tiles,
    _is_3d_mesh_building,
    _mesh_kind_for_building,
    _building_3d_origin_y,
    _footprint_scale_3d,
    _building_height_y,
    _stage_prefab_path_candidates,
    _plot_prefab_candidates,
    _first_existing,
    _first_existing_groups,
    _resolve_construction_staged_prefab,
    _resolve_prefab_path,
    _load_prefab_instance,
)
from game.graphics.ursina_units_anim import (
    _frame_index_for_clip,
    _hero_base_clip,
    _enemy_base_clip,
    _worker_idle_surface,
)
```

> IMPORTANT: Check that `PROJECT_ROOT` and any other module-level constants that appear in
> lines 119–819 are also exported from the new modules (or move them if missing). Do not
> leave dangling references.

### Gates

Run full gate stack. Expected: all PASS. `ursina_renderer.py` should now be ~1,394 lines.

---

## Round WK42-R2 — Track B: Wire UrsinaTerrainFogCollab

**Agent 03 — MEDIUM intelligence**

### Pre-flight

Check that the 6 methods in `UrsinaTerrainFogCollab` cover the same instance variables that
the corresponding 6 methods in `UrsinaRenderer` set. Specifically look for any `self.XXX = `
assignments inside the 6 methods that are NOT already present in `UrsinaTerrainFogCollab.__init__`
or forwarded through `self.renderer.XXX`. Add any missing ones to the collab before wiring.

The 6 methods to replace (UrsinaRenderer → collab mapping):

| UrsinaRenderer method | UrsinaTerrainFogCollab method |
|---|---|
| `_ensure_fog_overlay(self, world, fog_revision)` | `ensure_fog_overlay(self, world, fog_revision)` |
| `_track_visibility_gated_terrain(self, ent, tx, ty)` | `track_visibility_gated_terrain(self, ent, tx, ty)` |
| `_sync_terrain_prop_tile_visibility(self, ent, vis)` | `sync_terrain_prop_tile_visibility(self, ent, vis)` |
| `_sync_visibility_gated_terrain(self, world, fog_revision)` | `sync_visibility_gated_terrain(self, world, fog_revision)` |
| `_ensure_grid_debug_overlay(self, world, buildings)` | `ensure_grid_debug_overlay(self, world, buildings)` |
| `_build_3d_terrain(self, world, buildings)` | `build_3d_terrain(self, world, buildings)` |

### Edit

In `UrsinaRenderer.__init__` (after existing init setup):
```python
from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab
self._terrain_fog = UrsinaTerrainFogCollab(self)
```

Then for each of the 6 methods:
1. Delete the method body from `UrsinaRenderer`.
2. Replace every **call site** in `UrsinaRenderer` with the delegation form:
   - `self._ensure_fog_overlay(...)` → `self._terrain_fog.ensure_fog_overlay(...)`
   - `self._track_visibility_gated_terrain(...)` → `self._terrain_fog.track_visibility_gated_terrain(...)`
   - etc.

### Gates

Run full gate stack. Agent 10 consult: `python main.py --renderer ursina --no-llm` ~5 min FPS check.
Expected: ~929 lines in `ursina_renderer.py`.

---

## Round WK42-R3 — Track C: Wire UrsinaEntityRenderCollab

**Agent 03 — MEDIUM intelligence**

### Pre-flight

Same pattern as R2: verify the 11 collab methods cover the same instance-variable surface as
the 11 UrsinaRenderer methods. Key shared state: `self._entities`, `self._unit_anim_state`,
`self._building_sprites` etc. — these should all be accessed via `self.renderer.XXX` in the
collab. Confirm before deleting.

The 11 methods to replace (UrsinaRenderer → collab mapping):

| UrsinaRenderer method | UrsinaEntityRenderCollab method |
|---|---|
| `_apply_pixel_billboard_settings(ent)` | `apply_pixel_billboard_settings(ent)` |
| `_sync_inside_hero_draw_layer(ent, is_inside)` | `sync_inside_hero_draw_layer(ent, is_inside)` |
| `_set_texture_if_changed(ent, tex)` | `set_texture_if_changed(ent, tex)` |
| `_set_shader_if_changed(ent, sh)` | `set_shader_if_changed(ent, sh)` |
| `_sync_billboard_entity(...)` | `sync_billboard_entity(...)` |
| `_get_or_create_entity(...)` | `get_or_create_entity(...)` |
| `_apply_lit_3d_building_settings(ent)` | `apply_lit_3d_building_settings(ent)` |
| `_get_or_create_3d_building_entity(...)` | `get_or_create_3d_building_entity(...)` |
| `_sync_3d_building_entity(...)` | `sync_3d_building_entity(...)` |
| `_get_or_create_prefab_building_entity(...)` | `get_or_create_prefab_building_entity(...)` |
| `_sync_prefab_building_entity(...)` | `sync_prefab_building_entity(...)` |

### Edit

In `UrsinaRenderer.__init__`:
```python
from game.graphics.ursina_entity_render_collab import UrsinaEntityRenderCollab
self._entity_render = UrsinaEntityRenderCollab(self)
```

Delete the 11 methods and replace all call sites with delegation:
- `self._get_or_create_entity(...)` → `self._entity_render.get_or_create_entity(...)`
- etc.

### Gates

Run full gate stack. Agent 10 consult: FPS spot-check. Then **Jaimie manual smokes** (see top
of this file). Expected final line count: `ursina_renderer.py` ≤ 900 lines (target ~700).

---

## Definition of Done

- `ursina_renderer.py` imports from all 4 new helper modules (no duplicate definitions)
- `UrsinaTerrainFogCollab` and `UrsinaEntityRenderCollab` are imported and instantiated in
  `UrsinaRenderer.__init__`; their methods are the live code path
- `ursina_renderer.py` line count ≤ 900 (target ~700)
- Zero duplicate function definitions across the `game/graphics/` package (verify with grep)
- All gates PASS across all 3 rounds
- Jaimie manual playtest PASS (Ursina + pygame paths)
- No behavior change — game looks and plays identically to pre-WK42
