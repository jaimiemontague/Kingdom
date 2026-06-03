# WK108 Round B — FOG/B-2: extract build_3d_terrain + _batch_static_terrain_for_chunks

**Sprint key:** `wk108_round_b_ursina_terrain_build`
**Plan author:** Agent 01 (Executive Producer / PM)
**Predecessor:** WK107 (`9893836`, ground-mesh helpers → ursina_terrain_ground_mesh.py).
**Verification class:** ursina render → **deferred-screenshot model** (headless gates + PM verbatim-diff + DEFERRED live captures). Memory `feedback_ursina_deferred_screenshots`.

---

## 0. ONE-PARAGRAPH SUMMARY

Second/final FOG/B sub-slice. Extract the terrain-CONSTRUCTION cluster — **`_batch_static_terrain_for_chunks` (L386–536) and `build_3d_terrain` (L629–885)** — from `game/graphics/ursina_terrain_fog_collab.py` into a NEW leaf module `game/graphics/ursina_terrain_build.py`, via the same pure-move-behind-wrappers pattern shipped 15× this marathon (WK93–107). This is the LARGEST single move (~408 LOC) and the most test-coupled. The hard part is the `tests/test_terrain_perf.py` patch retarget (§5) — **get the §5.2 class-method retarget right or a test passes-but-wrongly.** This is behavior-preserving — NOT a redesign. Move byte-for-byte; change ONLY receiver tokens (`self.` → `owner.`) and the one intra-slice call.

---

## 1. THE CLUSTER (2 methods; move both together into ONE module)

| Method | Current lines | Signature |
|--------|---------------|-----------|
| `_batch_static_terrain_for_chunks` | 386–536 | `(self, root, tw: int, th: int) -> None` |
| `build_3d_terrain` | 629–885 | `(self, world, buildings) -> None` |

**Coupling (one-way, confirmed):** `build_3d_terrain` calls `self._batch_static_terrain_for_chunks(root, tw, th)` at **L873**. `_batch_static_terrain_for_chunks` calls NO `self.<method>`. So after the move, the L873 call becomes a DIRECT module-function call `_batch_static_terrain_for_chunks(owner, root, tw, th)` (both co-resident in the new module — no wrapper round-trip). Define `_batch_static_terrain_for_chunks` FIRST then `build_3d_terrain` in the new module (matches class order; avoids any forward-reference confusion).

**Sole external caller:** `ursina_renderer.py:572` `self._terrain_fog.build_3d_terrain(world, ...)` → hits the new wrapper, unchanged.

---

## 2. OWNER ATTRIBUTE MAP (precise — from grounding)

### `build_3d_terrain` — every `self.X`:
- `self._r._terrain_entity` (read L636 guard; write L868 `= root`) → `owner._r._terrain_entity`
- `self._r._tree_entities` (write L805, L823) → `owner._r._tree_entities`
- `self._instanced_trees_on` (read L775, L878) → `owner._instanced_trees_on` *(own slot)*
- `self._tree_instance_ids` (write L786) → `owner._tree_instance_ids` *(own slot)*
- `self._instanced_nature_renderer` (read L879 `is not None`) → `owner._instanced_nature_renderer` *(own slot)*
- **Calls that STAY as `owner.<wrapper>(...)`** (these are WK106/WK107 wrappers still on the class):
  - `self._build_terrain_ground_mesh(...)` (L682) → `owner._build_terrain_ground_mesh(...)`
  - `self.track_visibility_gated_terrain(...)` (L709, 725, 764, 822, 851, 866) → `owner.track_visibility_gated_terrain(...)`
  - `self._ensure_instanced_nature_renderer()` (L776) → `owner._ensure_instanced_nature_renderer()`
  - `self._build_terrain_chunks()` (L874) → `owner._build_terrain_chunks()`
- **The ONE intra-slice call → DIRECT module fn:**
  - `self._batch_static_terrain_for_chunks(root, tw, th)` (L873) → `_batch_static_terrain_for_chunks(owner, root, tw, th)`

### `_batch_static_terrain_for_chunks` — every `self.X`:
- `self._r._visibility_gated_terrain` (read L410, write L518) → `owner._r._visibility_gated_terrain`
- `self._r._visibility_gated_terrain_by_tile` (write L519) → `owner._r._visibility_gated_terrain_by_tile`
- `self._static_batch_fog_size` (read L406) → `owner._static_batch_fog_size` *(own slot)*
- `self._static_terrain_batches` (write L412, L520) → `owner._static_terrain_batches` *(own slot)*
- `self._static_batch_flatten_level` (write L413, 522, 524, 526, 536) → `owner._static_batch_flatten_level` *(own slot)*
- NO `self.<method>` calls.

**CRITICAL ORDERING:** `build_3d_terrain` sets `owner._r._terrain_entity = root` (L868) BEFORE the L873 batch call, and the batcher reads/writes `owner._r._visibility_gated_terrain[_by_tile]`. Keep the L868-before-L873 sequence verbatim.

After the move, `grep -n "self" game/graphics/ursina_terrain_build.py` should show only docstring/comment text (the AST gate `ast.Name id self == 0` is the real check). There must be ZERO `self` code identifiers.

---

## 3. THE NEW MODULE — `game/graphics/ursina_terrain_build.py`

Model on the WK107 sibling `ursina_terrain_ground_mesh.py`. **Top-level imports VERBATIM as below** (all referenced by the moved code's un-patched real paths — they MUST resolve). `Vec2`, `TerrainTextureBridge`, `pygame`, `Visibility`, `TERRAIN_CHUNK_SIZE` are NOT used by these 2 methods — do NOT import them. The `terrain_height` import is FUNCTION-LOCAL inside `build_3d_terrain` (carry verbatim at its current L639 position).

```python
"""Terrain construction (3D entity build + static chunk batching) for the Ursina renderer (WK108 slice of ursina_terrain_fog_collab.py).

Extracted VERBATIM from game/graphics/ursina_terrain_fog_collab.py:
_batch_static_terrain_for_chunks (WK58 Phase 3 static-prop fog-batch merge) and
build_3d_terrain (the main terrain/prop/tree/rock/grass/water/path constructor) —
as owner-arg module functions. The owner is UrsinaTerrainFogCollab, reached via
owner._r.* (parent UrsinaRenderer: _terrain_entity, _tree_entities,
_visibility_gated_terrain[_by_tile]) and owner.* (own slots: _instanced_trees_on,
_tree_instance_ids, _instanced_nature_renderer, _static_batch_*). build_3d_terrain
calls the WK106/WK107 wrappers (track_visibility_gated_terrain,
_ensure_instanced_nature_renderer, _build_terrain_chunks, _build_terrain_ground_mesh)
via owner.<wrapper>(...), and calls _batch_static_terrain_for_chunks as a direct
co-resident module function. UrsinaTerrainFogCollab keeps 1-line delegating wrappers
(same names+signatures) so ursina_renderer.py:572 and test_terrain_perf are stable.

Acyclic: imports leaf graphics/config/world modules + ursina/ursina.shaders at top
+ _InstancedTreeStub from ursina_terrain_growth_sync (one-way edge); imports
UrsinaTerrainFogCollab ONLY under TYPE_CHECKING. ursina_terrain_fog_collab.py imports
THIS module LAZILY inside the 2 wrapper bodies (one-way edge).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import config
from ursina import Entity, color
from ursina.shaders import unlit_shader

from game.graphics.ursina_coords import SCALE, px_to_world
from game.graphics.ursina_environment import (
    GROUND_PROP_FLOWER_LOG_MUSHROOM_SCALE,
    GRASS_SCATTER_SCALE_MULTIPLIER,
    ROCK_SCALE_MULTIPLIER,
    TERRAIN_SCALE_MULTIPLIER,
    TREE_SCALE_MULTIPLIER,
    _building_occupied_tiles,
    _environment_grass_and_doodad_model_lists,
    _environment_model_path,
    _environment_tree_model_list,
    _finalize_kenney_scatter_entity,
    _grass_clump_offset,
    _grass_density_budget,
    _grass_scatter_jitter,
    _grass_tile_selected,
    _scatter_model_index,
    _stem_is_flower_ground_scatter,
    _stem_is_log_or_mushroom_ground_scatter,
)
from game.graphics.ursina_terrain_growth_sync import _InstancedTreeStub
from game.world import TileType

if TYPE_CHECKING:
    from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab
```

Then the 2 functions, `_batch_static_terrain_for_chunks(owner, ...)` first then `build_3d_terrain(owner, ...)`, converted per §2. Keep the function-local `from game.graphics.terrain_height import get_terrain_height, init_heightmap, is_initialized` inside `build_3d_terrain` (current L639) exactly where it is. All docstrings/comments/blank-lines/try-except shapes VERBATIM.

---

## 4. EDIT `ursina_terrain_fog_collab.py`

Delete the 2 method bodies (`_batch_static_terrain_for_chunks` L386–536 and `build_3d_terrain` L629–885) and replace each IN PLACE with a wrapper (model on the WK107 wrappers):

```python
    def _batch_static_terrain_for_chunks(self, root, tw: int, th: int) -> None:
        from game.graphics import ursina_terrain_build
        return ursina_terrain_build._batch_static_terrain_for_chunks(self, root, tw, th)
```
```python
    def build_3d_terrain(self, world, buildings) -> None:
        from game.graphics import ursina_terrain_build
        return ursina_terrain_build.build_3d_terrain(self, world, buildings)
```
Do NOT touch any other method (`ensure_fog_overlay`, `ensure_grid_debug_overlay`, and all the WK104/106/107 wrappers STAY). After deleting these 2 bodies, re-check fog_collab top-level imports for NEW orphans (the move removes the last consumers of several `ursina_environment` helpers + `Path`, `px_to_world`, `unlit_shader`, etc.): for EACH top-level import name, `grep` the remaining file; if zero staying references, REMOVE it (this is part of completing the move cleanly, exactly like WK107 removed terrain_fog_shader/PROJECT_ROOT/Vec3). REPORT the full list of removed imports. Names still used by staying code (`ensure_fog_overlay` uses `pygame`, `TerrainTextureBridge`, `Vec2`, `Visibility`, `config`, `SCALE`, `sim_px_to_world_xz`, `Entity`, `color`; `ensure_grid_debug_overlay` uses `Entity`, `color`, etc.; the WK104 back-import `_InstancedTreeStub` is still used by no staying code? — verify: build was its only consumer at L799, so it MAY now be orphaned in fog_collab — but `_build_terrain_chunks`/`cull` moved in WK106 already; CHECK and report) must stay. **Be surgical: only remove a name after grep proves zero staying refs.**

---

## 5. EDIT `tests/test_terrain_perf.py` — THE RETARGET (Agent 11 owns; this is the highest-risk part)

### 5.1 Add the new alias
After L53 (`import game.graphics.ursina_terrain_fog_visibility as tfv`), ADD:
```python
import game.graphics.ursina_terrain_build as ttb
```
Keep `import ...ursina_terrain_fog_collab as tfc` and `from ...ursina_terrain_fog_collab import (TERRAIN_CHUNK_SIZE, UrsinaTerrainFogCollab)` UNCHANGED.

### 5.2 Retarget the module-global patches `tfc → ttb` (7 lines)
The moved `build_3d_terrain`/`_batch_static_terrain_for_chunks` resolve these names in `ursina_terrain_build`'s globals now, so the patches must target `ttb`:
- L218 `patch.object(tfc, "Entity", _FakeEntity)` → `patch.object(ttb, "Entity", _FakeEntity)`
- L219 `patch.object(tfc, "_finalize_kenney_scatter_entity", lambda *a, **kw: None)` → `ttb`
- L221–223 `patch.object(tfc, "_environment_grass_and_doodad_model_lists", ...)` → `ttb`
- L225 `patch.object(tfc, "_environment_tree_model_list", ...)` → `ttb`
- L227 `patch.object(tfc, "_environment_model_path", ...)` → `ttb`
- L229 `patch.object(tfc, "_building_occupied_tiles", ...)` → `ttb`
- L550 `patch.object(tfc, "Entity", _BatchFakeEntity)` (in `test_static_entity_count_reduced`) → `patch.object(ttb, "Entity", _BatchFakeEntity)`

### 5.3 ⚠ THE CRITICAL CLASS-METHOD RETARGET (miss this → test passes-but-wrong)
- L235–238 `patch.object(UrsinaTerrainFogCollab, "_batch_static_terrain_for_chunks", lambda *a, **kw: None)` → **change the target to the module function**: `patch.object(ttb, "_batch_static_terrain_for_chunks", lambda *a, **kw: None)`. Reason: after WK108, `build_3d_terrain` calls `_batch_static_terrain_for_chunks` as a DIRECT module fn (bypassing the class wrapper), so patching the class method no longer intercepts the call from inside build → the real batcher would run on `_FakeEntity`s, rebuild `_visibility_gated_terrain_by_tile` by batch-center tiles, and break the PATH-tile-key assertion (L241–249).

### 5.4 KEEP AS-IS
- L230–234 `patch.object(UrsinaTerrainFogCollab, "_build_terrain_ground_mesh", lambda *a, **kw: None)` — STAYS. `_build_terrain_ground_mesh` is a WK107 wrapper still on the class; moved `build_3d_terrain` calls it via `owner._build_terrain_ground_mesh(...)`, so the class-method patch still intercepts.
- L239 `collab.build_3d_terrain(world, [])` and L552 `collab._batch_static_terrain_for_chunks(...)` — direct test calls hit the new wrappers; UNCHANGED.

### 5.5 No other test file needs code changes
Only docstring mentions exist in test_wk104/106/107 (cosmetic; leave them).

---

## 6. AGENT TASKS

### Agent 09 (ArtDirector) — W1: the extraction + fog_collab orphan-import sweep
Onboard `.cursor/rules/agent-09-artdirector-onboarding.mdc`. Read this plan §1–4 + PM hub sprint + the WK107 sibling module. Create `game/graphics/ursina_terrain_build.py` (§3); edit fog_collab.py (§4: 2 wrappers + grep-proven orphan-import removal). Self-verify:
- `python -c "import game.graphics.ursina_terrain_build"` → ok
- `python -c "import game.graphics.ursina_terrain_fog_collab"` → ok
- both fresh-subprocess orders → ok
- `python -m pytest tests/test_terrain_perf.py -q` → will FAIL until Agent 11 lands §5 retargets; NOTE the failures, do NOT edit tests.
**DO NOT COMMIT. DO NOT edit tests.** Update agent_09 log. Report: new module LOC, fog_collab new LOC, removed-import list (grep-proven), any ambiguous mapping.

### Agent 11 (QA) — W2: §5 test retarget + seam test + DoD
Onboard `.cursor/rules/agent-11-qa-onboarding.mdc`. Read this plan §5–7 + PM hub + sibling `tests/test_wk107_ursina_terrain_ground_mesh.py`.
1. Apply §5 to `tests/test_terrain_perf.py` (add `ttb` alias; 7 module-global retargets §5.2; the ONE class-method retarget §5.3; keep §5.4). Then `python -m pytest tests/test_terrain_perf.py -q` → must be all-green.
2. Create `tests/test_wk108_ursina_terrain_build.py` (mirror test_wk107): fn-exists (2 fns), owner-first sig, wrapper-delegation (2, via `object.__new__(UrsinaTerrainFogCollab)` + sentinel stub; build sig `(world, buildings)`, batch sig `(root, tw, th)`), AST no-`self`, AST no-cycle (no module-top import of `ursina_terrain_build` in fog_collab; collab under TYPE_CHECKING-only in new module), function-local-import guard (`from game.graphics.terrain_height import get_terrain_height` present in source but NOT a top-level node), fresh-subprocess both orders. SDL dummy at top.
3. Full DoD (§7).
**DO NOT COMMIT.** Update agent_11 log.

---

## 7. DEFINITION OF DONE
1. `python -m pytest -q` → ALL pass (~1290+; 0 failed). `test_terrain_perf.py` GREEN (8-point retarget landed).
2. `python tools/determinism_guard.py` → clean.
3. `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q` → pass (digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`).
4. `python tools/qa_smoke.py --quick` → green.
5. import smoke + both fresh-subprocess orders; AST `self`-identifiers in new module = 0.
6. New seam test passes.
7. **Agent 01 PM verbatim-diff gate**: canonicalize `self`/`owner`→`@`; diff each of the 2 methods HEAD-vs-new. Allowed diffs ONLY: the L873 intra-call rewrite (`@._batch_static_terrain_for_chunks(root, tw, th)` → `_batch_static_terrain_for_chunks(@, root, tw, th)`). The wrapper calls (`@._build_terrain_ground_mesh`, `@.track_visibility_gated_terrain`, `@._ensure_instanced_nature_renderer`, `@._build_terrain_chunks`) canonicalize IDENTICALLY (they stay `owner.X`/`self.X` → `@.X`) so they must NOT appear as diffs. Any other diff = defect → bounce to Agent 09.
8. **Live before/after Ursina screenshots: DEFERRED to Jaimie's end-of-marathon test pass.**

LOC target: fog_collab.py 910 → ~510 (−~400 + removed orphan imports). New module ~415 LOC. **After WK108, ursina_terrain_fog_collab.py holds only `__init__` + `ensure_fog_overlay` + `ensure_grid_debug_overlay` + the WK104/106/107/108 wrappers — the god-file is essentially decomposed.**

---

## 8. COMMIT (Agent 01 only) — scoped add; NEVER `git add -A`; NEVER the 2 root user PNGs.

## 9. FOLLOW-UPS
- **WK109**: `ensure_fog_overlay` (L122–347, ~225 LOC) + `ensure_grid_debug_overlay` (L538–628, ~90 LOC) → `ursina_fog_overlay.py` (or fold grid-debug into renderer). After this, fog_collab is just `__init__` + wrappers (~250 LOC) — consider whether the class becomes a thin facade worth keeping or inlining.
- Then: ursina_app HUD/env cluster; the deferred `handle_click` redesign (hud.py); de-slop dead `WATCH_MINIMAP_SIZE` (hud.py:57); the batched orphan-import sweep is now folded into each move.
- **Non-render headless roadmap** (fully verifiable, no deferred screenshots): config package split, ai/vocab.py + TaskRouter, world.py fog state-machine, WK34 zombie-type purge (21 files), context_builder/direct_prompt_validator, Move 9 SystemRunner (RISKY — do not reorder update() side effects).
