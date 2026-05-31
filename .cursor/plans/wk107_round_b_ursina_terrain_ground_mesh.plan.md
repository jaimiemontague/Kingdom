# WK107 Round B — FOG/B-1: extract ground-mesh + grass-texture + cave-shader helpers

**Sprint key:** `wk107_round_b_ursina_terrain_ground_mesh`
**Plan author:** Agent 01 (Executive Producer / PM)
**Roadmap source:** `.cursor/plans/GPT 5.5 Codebase Improvements Recommendations.md` (#1 god-file decomposition) + `.cursor/plans/codebase_audit_2026-05-28_finding_inventory.md`
**Predecessor:** WK106 (`29590e8`, FOG/A visibility/cull/instanced-fog → ursina_terrain_fog_visibility.py).
**Verification class:** ursina render → **deferred-screenshot model** (headless gates + PM verbatim-diff + DEFERRED live captures). See memory `feedback_ursina_deferred_screenshots`.

---

## 0. ONE-PARAGRAPH SUMMARY (read first)

This is the FIRST of two FOG/B sub-slices. We extract the 3 **ground-surface** helper methods — `_build_terrain_ground_mesh`, `update_cave_entrance_shader`, `_apply_grass_texture` (currently `ursina_terrain_fog_collab.py` L889–L1177, ~286 LOC) — into a NEW leaf module `game/graphics/ursina_terrain_ground_mesh.py`, using the same **pure-move-behind-wrappers** pattern shipped 14× this marathon (WK93–106). `build_3d_terrain` and `_batch_static_terrain_for_chunks` STAY in the class this sprint (they are heavily test-coupled and become WK108). **Because `build_3d_terrain` stays and keeps calling `self._build_terrain_ground_mesh(...)`, the existing `tests/test_terrain_perf.py` characterization harness needs NO changes — its `patch.object(UrsinaTerrainFogCollab, "_build_terrain_ground_mesh", ...)` patches the new wrapper, and the wrapper is what `build_3d_terrain` calls. This is a behavior-preserving refactor — NOT a redesign. Move byte-for-byte; change ONLY `self._r.` → `owner._r.` and the one intra-cluster call.**

---

## 1. THE CLUSTER (3 methods, exact current line ranges in `ursina_terrain_fog_collab.py`)

| # | Method | Lines | Externally called? | `self.X` accesses |
|---|--------|-------|--------------------|-------------------|
| 1 | `_build_terrain_ground_mesh(self, root, world, tw, th, ts, w_world, d_world, has_heightmap)` | 889–1091 | build_3d_terrain L684 (stays→wrapper); test patches it on the class | `self._r._terrain_ground_entity`, `setattr(self._r, "_geomip_terrain_handle", ...)`, `self._apply_grass_texture(...)` (×2) |
| 2 | `update_cave_entrance_shader(self, pois, map_width, map_height)` | 1093–1141 | none static (public; feature-gated, returns immediately at L1101) | `getattr(self._r, '_terrain_ground_entity', None)` |
| 3 | `_apply_grass_texture(self, ground_ent, tw, th, use_texture_scale=True)` | 1143–1177 | `_build_terrain_ground_mesh` (intra) | `getattr(self._r, "_ks_ground_tex", None)`, `self._r._ks_ground_tex` |

**No owner-own-slots are touched** by any of these 3 methods — every `self.X` is either `self._r.X` (parent UrsinaRenderer) or the single intra-cluster call `self._apply_grass_texture`. There is NO `self.<own-slot>` in this cluster.

**Intra-cluster call** (becomes a DIRECT module-function call):
- `self._apply_grass_texture(ground_ent, tw, th)` (L976) → `_apply_grass_texture(owner, ground_ent, tw, th)`
- `self._apply_grass_texture(ground_ent, tw, th, use_texture_scale=False)` (L1080) → `_apply_grass_texture(owner, ground_ent, tw, th, use_texture_scale=False)`

**One-way coupling:** these 3 are LEAVES of `build_3d_terrain` (it calls them; they never call `build_3d_terrain` or `_batch_static_terrain_for_chunks`). `update_cave_entrance_shader` calls nothing in the class. `_apply_grass_texture` calls nothing in the class.

---

## 2. OWNER ATTRIBUTE MAP

Every `self.X` in these 3 methods → exactly one of:
- `self._r.<attr>` → `owner._r.<attr>` (parent renderer): `_terrain_ground_entity`, `_geomip_terrain_handle` (set via `setattr`), `_ks_ground_tex`.
- `getattr(self._r, ...)` → `getattr(owner._r, ...)` — TWO comma-forms: `getattr(self._r, '_terrain_ground_entity', None)` (L1103) and `getattr(self._r, "_ks_ground_tex", None)` (L1149).
- `setattr(self._r, "_geomip_terrain_handle", handle)` (L955) → `setattr(owner._r, "_geomip_terrain_handle", handle)`.
- intra-call `self._apply_grass_texture(...)` → `_apply_grass_texture(owner, ...)`.

After the move, `grep -n "self" game/graphics/ursina_terrain_ground_mesh.py` MUST return ZERO matches.

---

## 3. THE NEW MODULE — `game/graphics/ursina_terrain_ground_mesh.py`

Model it on the WK104/WK106 siblings (`ursina_terrain_growth_sync.py`, `ursina_terrain_fog_visibility.py`). Header + top-level imports VERBATIM as below. **CRITICAL: keep the function-local imports function-local** — `from ursina import Mesh` (inside a `try/except ImportError: return`), `from ursina import Texture` + `from PIL import Image` (inside a `try/except`), `import math as _math`, `from game.graphics.terrain_height import get_terrain_height`, `from game.graphics.terrain_geomipterrain import ...`, and `from config import UNDERGROUND_HOLE_RADIUS_TILES, UNDERGROUND_HOLE_EDGE_TILES` are ALL function-local in the originals and MUST stay exactly where they are (they guard optional-dependency fallbacks; hoisting them would change behavior). Carry the apparently-unused `from game.graphics.terrain_height import get_terrain_height` (L913) VERBATIM — this is a faithful move, not a de-slop pass.

```python
"""Terrain ground-surface mesh, grass texture, and cave-entrance shader for the Ursina renderer (WK107 slice of ursina_terrain_fog_collab.py).

Extracted VERBATIM from game/graphics/ursina_terrain_fog_collab.py:
_build_terrain_ground_mesh (heightmap-displaced mesh / GeoMipTerrain LOD / flat
fallback), update_cave_entrance_shader (feature-gated, early-returns), and
_apply_grass_texture (albedo load + tiling) — as owner-arg module functions. The
owner is UrsinaTerrainFogCollab, reached via owner._r.* (parent UrsinaRenderer
state: _terrain_ground_entity, _geomip_terrain_handle, _ks_ground_tex).
UrsinaTerrainFogCollab keeps 1-line delegating wrappers (same names+signatures) so
build_3d_terrain's `self._build_terrain_ground_mesh(...)` call and any external
`update_cave_entrance_shader` caller are unchanged.

Acyclic: imports only leaf graphics/config modules + ursina/ursina.shaders at top;
imports UrsinaTerrainFogCollab ONLY under TYPE_CHECKING. ursina_terrain_fog_collab.py
imports THIS module LAZILY inside the wrapper bodies (one-way edge).
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

import config
from ursina import Entity, Vec2, color
from ursina.shaders import unlit_shader

from game.graphics.terrain_fog_shader import terrain_fog_shader
from game.graphics.ursina_coords import sim_px_to_world_xz
from game.graphics.ursina_environment import PROJECT_ROOT

if TYPE_CHECKING:
    from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab
```

Then the 3 functions, in source order, converted from `def name(self, ...)` to `def name(owner, ...)`, applying §2. Worked example for the intra-call (the flat-fallback branch of `_build_terrain_ground_mesh`):
```python
        ground_ent = Entity(
            parent=root,
            model="quad",
            color=color.white,
            scale=(w_world, d_world, 1),
            rotation=(90, 0, 0),
            position=(base_wx, -0.05, base_wz),
            collision=False,
            double_sided=True,
            shader=unlit_shader,
            add_to_scene_entities=False,
        )
        _apply_grass_texture(owner, ground_ent, tw, th)   # was: self._apply_grass_texture(ground_ent, tw, th)
        return
```
And the `_r` writes:
```python
                        owner._r._terrain_ground_entity = handle.wrap_entity   # was self._r._...
                        setattr(owner._r, "_geomip_terrain_handle", handle)    # was setattr(self._r, ...)
...
        owner._r._terrain_ground_entity = ground_ent   # was self._r._terrain_ground_entity = ground_ent
```
`update_cave_entrance_shader`: the body returns immediately at the first line (`return` at L1101 — feature gate). Carry the ENTIRE method VERBATIM including all dead code after the `return` (do NOT delete it; faithful move). Convert `getattr(self._r, '_terrain_ground_entity', None)` → `getattr(owner._r, ...)`.
`_apply_grass_texture`: convert `getattr(self._r, "_ks_ground_tex", None)` → `getattr(owner._r, ...)`, `self._r._ks_ground_tex` → `owner._r._ks_ground_tex`. Keep `from ursina import Texture` + `from PIL import Image` function-local inside the `try`.

---

## 4. EDIT `ursina_terrain_fog_collab.py` — delete 3 method bodies, insert 3 wrappers

Delete L889–1177 (the 3 methods, from `def _build_terrain_ground_mesh` through the end of `_apply_grass_texture` at the line `            pass`). These sit between `build_3d_terrain` (ends L888) and `sync_dynamic_trees` (L1178). Replace IN PLACE with the 3 wrappers (model on the WK104/WK106 wrapper form):

```python
    def _build_terrain_ground_mesh(
        self, root, world, tw: int, th: int, ts: int,
        w_world: float, d_world: float, has_heightmap: bool,
    ) -> None:
        from game.graphics import ursina_terrain_ground_mesh
        return ursina_terrain_ground_mesh._build_terrain_ground_mesh(
            self, root, world, tw, th, ts, w_world, d_world, has_heightmap
        )

    def update_cave_entrance_shader(self, pois, map_width, map_height):
        from game.graphics import ursina_terrain_ground_mesh
        return ursina_terrain_ground_mesh.update_cave_entrance_shader(self, pois, map_width, map_height)

    def _apply_grass_texture(self, ground_ent, tw: int, th: int, use_texture_scale: bool = True) -> None:
        from game.graphics import ursina_terrain_ground_mesh
        return ursina_terrain_ground_mesh._apply_grass_texture(self, ground_ent, tw, th, use_texture_scale=use_texture_scale)
```

Signatures match the originals byte-for-byte (note `_build_terrain_ground_mesh`'s multi-line signature with `ts: int` etc.; `_apply_grass_texture`'s `use_texture_scale: bool = True` default). DO NOT touch any other method (`build_3d_terrain`, `_batch_static_terrain_for_chunks`, `ensure_fog_overlay`, `ensure_grid_debug_overlay` all stay verbatim). DO NOT touch the import block at the top (all those names are still used by staying code: `terrain_fog_shader`, `unlit_shader`, `sim_px_to_world_xz`, `PROJECT_ROOT`, `Entity`, `Vec2`, `color`, `config`, `os` — build_3d_terrain and the other staying methods use them).

**NOTE on `terrain_fog_shader` / `unlit_shader` / `sim_px_to_world_xz` / `PROJECT_ROOT` imports in fog_collab:** verify they are STILL referenced by staying code before assuming. They are (build_3d_terrain and ensure_fog_overlay use them). Do NOT remove any top-level import from fog_collab in this sprint unless a `grep` proves zero staying references — and report any you find.

---

## 5. AGENT TASKS

### Agent 09 (ArtDirector) — W1: the extraction
**Onboard:** `.cursor/rules/agent-09-artdirector-onboarding.mdc`; you are Agent 09. Read this plan + PM hub sprint `wk107_round_b_ursina_terrain_ground_mesh` + the WK106 sibling `game/graphics/ursina_terrain_fog_visibility.py` (shape reference).
**Do:** §3 (create `game/graphics/ursina_terrain_ground_mesh.py`) + §4 (edit fog_collab.py).
**Self-verify (run ALL; paste output to log):**
- `python -c "import game.graphics.ursina_terrain_ground_mesh"` → no error
- `python -c "import game.graphics.ursina_terrain_fog_collab"` → no error
- both fresh-subprocess orders: `python -c "import game.graphics.ursina_terrain_fog_collab; import game.graphics.ursina_terrain_ground_mesh; print('A ok')"` and the reverse → both ok
- `grep -n "self" game/graphics/ursina_terrain_ground_mesh.py` → ZERO matches
- `python -m pytest tests/test_terrain_perf.py -q` → MUST stay all-green (7 passed) WITHOUT any test edit. If it fails, STOP and report (do NOT edit the test).
**DO NOT COMMIT. DO NOT edit any test file. Touch ONLY the new module + fog_collab.py.** Update `agent_09_ArtDirector_Pixel_Animation_VFX.json`, then STOP.

### Agent 11 (QA) — W2: seam test + DoD
**Onboard:** `.cursor/rules/agent-11-qa-onboarding.mdc`; you are Agent 11. Read this plan + PM hub sprint + sibling `tests/test_wk106_ursina_terrain_fog_visibility.py`.
**Do:** create `tests/test_wk107_ursina_terrain_ground_mesh.py` (mirror test_wk106). The 3 fn names: `_build_terrain_ground_mesh`, `update_cave_entrance_shader`, `_apply_grass_texture`. Cover:
1. **fn-exists** (3 module-level functions in `ursina_terrain_ground_mesh`).
2. **owner-first signature** (first param named `owner`).
3. **wrapper-delegation** (monkeypatch each module fn to a sentinel-recording stub; call the wrapper on `object.__new__(UrsinaTerrainFogCollab)` with dummy args matching each signature; assert sentinel returned + arg0 is the instance). For `_build_terrain_ground_mesh` pass the 8 positional dummies; for `_apply_grass_texture` exercise both the positional form and the `use_texture_scale=` keyword form.
4. **AST no-`self`** (read new module `utf-8-sig`; no `ast.Name` id `self`).
5. **AST no-cycle**: read `ursina_terrain_fog_collab.py` `utf-8-sig`; assert NO module-top-level import of `ursina_terrain_ground_mesh` (only lazy `from game.graphics import ursina_terrain_ground_mesh` inside function bodies). Assert the new module imports `UrsinaTerrainFogCollab` ONLY under `if TYPE_CHECKING:`.
6. **function-local-import guard**: assert the new module source contains `from ursina import Mesh` and `from PIL import Image` and `from config import UNDERGROUND_HOLE_RADIUS_TILES` (i.e. they were carried), AND that these do NOT appear at module-top-level (parse AST `tree.body`, assert none of those imports is a top-level node — they must be nested in functions).
7. **fresh-subprocess both orders** (subprocess returncode 0).
Set `SDL_VIDEODRIVER/SDL_AUDIODRIVER=dummy` at top.
**Then run the full DoD gate (§6); paste output to log. DO NOT COMMIT. Touch ONLY the new test file** (no edit to test_terrain_perf.py is needed this sprint — confirm it stays green). Update `agent_11_QA_TestEngineering_Lead.json`, then STOP.

---

## 6. DEFINITION OF DONE (Agent 11 runs; Agent 01 re-verifies)
1. `python -m pytest -q` → ALL pass (~1276 after +~4; 0 failed). `test_terrain_perf.py` GREEN with NO edit.
2. `python tools/determinism_guard.py` → clean.
3. `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q` → pass (digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`).
4. `python tools/qa_smoke.py --quick` → green.
5. import smoke + both fresh-subprocess orders; `grep self` new module = 0.
6. New seam test passes.
7. **Agent 01 PM verbatim-diff gate**: canonicalize `self`/`owner`→`@`, diff each of the 3 methods HEAD-vs-new; the ONLY allowed diffs are the 2 intra-cluster `_apply_grass_texture` call-site rewrites. Any other diff = defect → bounce to Agent 09.
8. **Live before/after Ursina screenshots: DEFERRED to Jaimie's end-of-marathon test pass.** Flag in commit + PM closeout.

LOC target: fog_collab.py 1184 → ~915 (−~270). New module ~290 LOC.

---

## 7. COMMIT (Agent 01 only) — scoped add ONLY; NEVER `git add -A`; NEVER the 2 root user PNGs.

## 8. FOLLOW-UPS
- **WK108 = FOG/B-2**: `build_3d_terrain` (L631–888) + `_batch_static_terrain_for_chunks` (L388–539) → new module (e.g. `ursina_terrain_build.py`). This one DOES need the `tests/test_terrain_perf.py` 8-patch retarget analysis: `patch.object(tfc, "Entity"/"_finalize_kenney_scatter_entity"/"_environment_grass_and_doodad_model_lists"/"_environment_tree_model_list"/"_environment_model_path"/"_building_occupied_tiles")` must retarget to the new module (build resolves those there); the `patch.object(UrsinaTerrainFogCollab, "_build_terrain_ground_mesh"/"_batch_static_terrain_for_chunks")` class-method patches stay as-is IF those remain wrappers/methods on the class (after WK107 `_build_terrain_ground_mesh` is a wrapper; `_batch_static` moves in WK108 so its patch must retarget to the new module fn). Plus `test_terrain_perf.py:552 collab._batch_static_terrain_for_chunks(...)` direct call → wrapper (unchanged). Scope carefully.
- **WK109**: `ensure_fog_overlay` (L124–349) + `ensure_grid_debug_overlay` (L540–630) → consider folding into renderer or a `ursina_fog_overlay.py`.
- Then: ursina_app HUD/env cluster; the deferred `handle_click` redesign (hud.py); de-slop dead `WATCH_MINIMAP_SIZE`; non-render headless roadmap (config split, ai/vocab.py + TaskRouter, world.py fog state-machine, WK34 zombie purge, context_builder/direct_prompt_validator, Move 9 SystemRunner).
