# WK109 Round B — FOG/C: extract ensure_fog_overlay + ensure_grid_debug_overlay (god-file finale)

**Sprint key:** `wk109_round_b_ursina_fog_overlay`
**Plan author:** Agent 01 (Executive Producer / PM)
**Predecessor:** WK108 (`0eaf55f`, terrain construction → ursina_terrain_build.py).
**Verification class:** ursina render → **deferred-screenshot model**. Memory `feedback_ursina_deferred_screenshots`.

---

## 0. SUMMARY — the last real-body methods leave the god-file

Move the two remaining real-body methods — **`ensure_fog_overlay` (L96–320, ~225 LOC) and `ensure_grid_debug_overlay` (L364–453, ~90 LOC)** — out of `game/graphics/ursina_terrain_fog_collab.py` into a NEW leaf module `game/graphics/ursina_fog_overlay.py`, via the same pure-move-behind-wrappers pattern (16× this marathon). After this, `UrsinaTerrainFogCollab` = `__init__` + delegating wrappers only — a deliberate **stateful facade / state-container** (its `__slots__` hold the `_r` + chunk/instanced/batch state that the moved module-functions read/write via `owner.*`; `ursina_renderer.py` constructs it and calls its public methods). The class STAYS; it is the intentional end-state of the refactor, not further reducible. **Behavior-preserving pure-move — NOT a redesign.** The two methods are the EASIEST move of the whole series: they touch ONLY `self._r.*` (zero own-slots), make ZERO intra-class calls, and don't call each other.

---

## 1. THE CLUSTER (2 independent methods → ONE module)

| Method | Current lines | Signature | `self.X` surface |
|--------|---------------|-----------|------------------|
| `ensure_fog_overlay` | 96–320 | `(self, world, fog_revision: int) -> None` | only `self._r.*` (`_terrain_entity`, `_fog_revision_seen`, `_terrain_ground_entity`, `_fog_entity`, `_fog_tile_buf`, `_fog_full_surf`, `_fog_texture_stage`, `_geomip_terrain_handle`) — several via `getattr(self._r, "...")` comma-forms |
| `ensure_grid_debug_overlay` | 364–453 | `(self, world, buildings) -> None` | only `self._r._grid_debug_entity` |

- **Zero own-slots** (only `self._r`). **Zero intra-class method calls** (neither calls the other or any wrapper). → both become free functions `def ensure_fog_overlay(owner, world, fog_revision)` / `def ensure_grid_debug_overlay(owner, world, buildings)` with NO `owner.<wrapper>(...)` calls — every `self._r.X` → `owner._r.X` and every `getattr(self._r, ...)` → `getattr(owner._r, ...)`. Nothing else changes.
- Sole external callers (hit the wrappers, unchanged): `ursina_renderer.py:584` `self._terrain_fog.ensure_fog_overlay(...)`, `ursina_renderer.py:591` `self._terrain_fog.ensure_grid_debug_overlay(...)`.

---

## 2. THE NEW MODULE — `game/graphics/ursina_fog_overlay.py`

Header + top-level imports VERBATIM as below. The constant `FOG_TEX_BRIDGE_KEY` MOVES here (its only consumer is `ensure_fog_overlay`). **Keep function-local imports function-local** (verbatim, at their current positions): in `ensure_fog_overlay` — `from panda3d.core import TransparencyAttrib` (L194), `from panda3d.core import SamplerState` (L213; carry verbatim even though unused), `from panda3d.core import TextureStage` (L220), `import ursina as u` (L275); in `ensure_grid_debug_overlay` — `import ursina as u` (L376), `from ursina import Mesh` (L386), `from panda3d.core import TransparencyAttrib` (L446).

```python
"""Fog-of-war overlay + grid-debug overlay for the Ursina terrain renderer (WK109 slice of ursina_terrain_fog_collab.py).

Extracted VERBATIM from game/graphics/ursina_terrain_fog_collab.py:
ensure_fog_overlay (per-frame fog texture build + GPU upload; heightmap-shader-uniform
path + legacy fog-quad fallback) and ensure_grid_debug_overlay (KINGDOM_URSINA_GRID_DEBUG
visualization) — as owner-arg module functions. The owner is UrsinaTerrainFogCollab,
reached EXCLUSIVELY via owner._r.* (parent UrsinaRenderer state). Neither function reads
or writes any owner __slots__ member other than owner._r, and they make no intra-class
calls. UrsinaTerrainFogCollab keeps 1-line delegating wrappers (same names+signatures) so
ursina_renderer.py:584/591 are unchanged.

Acyclic: imports leaf graphics/config/world modules + ursina/ursina.shaders + pygame at
top (panda3d kept function-local); imports UrsinaTerrainFogCollab ONLY under TYPE_CHECKING.
ursina_terrain_fog_collab.py imports THIS module LAZILY inside the 2 wrapper bodies.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pygame
import config
from ursina import Entity, Vec2, color
from ursina.shaders import unlit_shader

from game.graphics.terrain_texture_bridge import TerrainTextureBridge
from game.graphics.ursina_coords import SCALE, sim_px_to_world_xz
from game.world import Visibility

if TYPE_CHECKING:
    from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab

FOG_TEX_BRIDGE_KEY = "kingdom_ursina_fog_overlay"
```

Then the 2 functions (source order: `ensure_fog_overlay` then `ensure_grid_debug_overlay`), converted `self._r.`→`owner._r.` (incl. all `getattr(self._r, ...)` comma-forms). All docstrings/comments/blank-lines/try-except: VERBATIM.

**`grep "self"` will show docstring text only; the AST gate (`ast.Name id self == 0`) is the real check.**

---

## 3. EDIT `ursina_terrain_fog_collab.py`

### 3.1 Delete the 2 method bodies (L96–320, L364–453); insert 2 wrappers IN PLACE
```python
    def ensure_fog_overlay(self, world, fog_revision: int) -> None:
        from game.graphics import ursina_fog_overlay
        return ursina_fog_overlay.ensure_fog_overlay(self, world, fog_revision)
```
```python
    def ensure_grid_debug_overlay(self, world, buildings) -> None:
        from game.graphics import ursina_fog_overlay
        return ursina_fog_overlay.ensure_grid_debug_overlay(self, world, buildings)
```
Place `ensure_fog_overlay`'s wrapper where the body was (top of the wrapper cluster, after `__init__`); place `ensure_grid_debug_overlay`'s wrapper where ITS body was (between the WK108 `_batch_static_terrain_for_chunks` wrapper and the `build_3d_terrain` wrapper). Signatures byte-identical.

### 3.2 Orphan-import sweep (grep-proven; this completes the god-file decomposition)
After the move, fog_collab = `__init__` + wrappers. `__init__` uses `os` (L69) + a function-local import. The wrappers use NO top-level imports. So:
- **REMOVE** (grep-prove zero staying refs first): `import pygame` (L7); `import config` (L8); `from ursina import Entity, Vec2, color` (L9); `from game.graphics.terrain_texture_bridge import TerrainTextureBridge` (L11); `from game.graphics.ursina_coords import SCALE, sim_px_to_world_xz` (L12); `from game.world import Visibility` (L13); `from ursina.shaders import unlit_shader` (L14); the constant `FOG_TEX_BRIDGE_KEY = "kingdom_ursina_fog_overlay"` (L16 — moved to the new module; grep-confirm nothing else references it).
- **KEEP**: `from __future__ import annotations` (L3); `import os` (L5 — `__init__` L69); `TERRAIN_CHUNK_SIZE = 16` (L18 — `tests/test_terrain_perf.py` imports it + WK106 module mirrors it).
- Before removing each name, grep the repo for `from game.graphics.ursina_terrain_fog_collab import <name>` (no external re-export importer expected except `TERRAIN_CHUNK_SIZE`/`UrsinaTerrainFogCollab`).
- Optional cosmetic: the module docstring L1 (`"""Terrain, fog overlay, grid debug ..."""`) is now stale — update to reflect that the class is the state-container/facade and the behavior lives in the `ursina_terrain_*`/`ursina_fog_overlay` modules. (Cosmetic; do if trivial.)
- REPORT the exact removed-list and kept-list with the staying consumer for each kept name.

---

## 4. EDIT `tests/test_terrain_perf.py` — retarget the 2 shared-object patches (Agent 11)

Because §3.2 sweeps `pygame` and `TerrainTextureBridge` out of fog_collab, the test's `tfc.pygame` / `tfc.TerrainTextureBridge` handles would AttributeError. Retarget them to the new module (which keeps those imports). These patch SHARED objects, so retargeting the HANDLE (not the semantics) is all that's needed:
1. Add (near the other aliases, ~after L53): `import game.graphics.ursina_fog_overlay as ufo`.
2. At the `with patch.object(...)` block (~L719–720) in `TestFogOverlayPerf::test_ensure_fog_overlay_early_out_post_heightmap`:
   - `patch.object(tfc.pygame.image, "frombuffer", _spy_frombuffer)` → `patch.object(ufo.pygame.image, "frombuffer", _spy_frombuffer)`
   - `patch.object(tfc.TerrainTextureBridge, "refresh_surface_texture", _spy_refresh)` → `patch.object(ufo.TerrainTextureBridge, "refresh_surface_texture", _spy_refresh)`
3. The direct calls `collab.ensure_fog_overlay(world, fog_revision=...)` (~L725–726) hit the wrappers — UNCHANGED. The `from ...fog_collab import (TERRAIN_CHUNK_SIZE, UrsinaTerrainFogCollab)` import — UNCHANGED. The `import ...fog_collab as tfc` — keep (still used for `UrsinaTerrainFogCollab`/`TERRAIN_CHUNK_SIZE`-adjacent refs; verify `tfc` is still referenced — if the ONLY remaining `tfc.` uses were these two patches, you may keep the import for the `as tfc` of the `from` line, but check).
4. Verify: `python -m pytest tests/test_terrain_perf.py -q` → all-green.

---

## 5. AGENT TASKS

### Agent 09 (ArtDirector) — W1: extraction + orphan sweep
Onboard `.cursor/rules/agent-09-artdirector-onboarding.mdc`. Read §1–3 + PM hub sprint + a prior sibling (`ursina_terrain_ground_mesh.py`). Create `game/graphics/ursina_fog_overlay.py` (§2); edit fog_collab.py (§3: 2 wrappers + grep-proven orphan sweep incl. moving FOG_TEX_BRIDGE_KEY). Self-verify:
- `python -c "import game.graphics.ursina_fog_overlay"` → ok
- `python -c "import game.graphics.ursina_terrain_fog_collab"` → ok
- both fresh-subprocess orders → ok
- AST self-id check on new module → `self_ids= 0`
- `grep -nE "\bpygame\b|TerrainTextureBridge|FOG_TEX_BRIDGE_KEY|\bconfig\b|\bVisibility\b|unlit_shader|\bSCALE\b|sim_px_to_world_xz" game/graphics/ursina_terrain_fog_collab.py` → only `TERRAIN_CHUNK_SIZE`-unrelated zero matches for the swept names (os/TERRAIN_CHUNK_SIZE remain)
- `python -m pytest tests/test_terrain_perf.py -q` → will FAIL on `test_ensure_fog_overlay_early_out_post_heightmap` until Agent 11 retargets §4 (tfc.pygame/tfc.TerrainTextureBridge AttributeError). NOTE it; do NOT edit tests.
**DO NOT COMMIT. DO NOT edit tests.** Report new/old LOC, removed/kept import lists, the verification outputs.

### Agent 11 (QA) — W2: §4 retarget + seam test + DoD
Onboard `.cursor/rules/agent-11-qa-onboarding.mdc`. Read §4–6 + PM hub + sibling `tests/test_wk108_ursina_terrain_build.py`.
1. Apply §4 to `tests/test_terrain_perf.py` (add `ufo` alias; retarget the 2 patches). Then `pytest tests/test_terrain_perf.py -q` → all-green.
2. Create `tests/test_wk109_ursina_fog_overlay.py` (mirror test_wk108): fn-exists (2), owner-first sig, wrapper-delegation (2: `ensure_fog_overlay(world, fog_revision)` → `inst.ensure_fog_overlay(object(), 0)`; `ensure_grid_debug_overlay(world, buildings)` → `inst.ensure_grid_debug_overlay(object(), ())`), AST no-`self`, AST no-cycle (no module-top import of `ursina_fog_overlay` in fog_collab; collab TYPE_CHECKING-only in new module), function-local-import guard (`from panda3d.core import TransparencyAttrib` and `from ursina import Mesh` present in new-module source but NOT top-level nodes), constant check (`ursina_fog_overlay.FOG_TEX_BRIDGE_KEY == "kingdom_ursina_fog_overlay"`), fresh-subprocess both orders. SDL dummy at top.
3. Full DoD (§6).
**DO NOT COMMIT.** Update agent_11 log.

---

## 6. DEFINITION OF DONE
1. `python -m pytest -q` → ALL pass, 0 failed (report N passed). test_terrain_perf.py GREEN.
2. `python tools/determinism_guard.py` → clean.
3. `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q` → pass (digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`).
4. `python tools/qa_smoke.py --quick` → green.
5. import smoke + both fresh-subprocess orders; AST `self`-id in new module = 0.
6. New seam test passes.
7. **Agent 01 PM verbatim-diff gate**: canonicalize `self`/`owner`→`@`; diff each method HEAD-vs-new. EXPECT **zero diffs** (both methods only have `self._r.`→`owner._r.` which canonicalizes identically, and NO intra-call rewrites since there are none). Any diff at all = investigate. (This is the cleanest gate of the series.)
8. **Live before/after Ursina screenshots: DEFERRED to Jaimie's end-of-marathon test pass.**

LOC target: fog_collab.py 482 → ~165 (−~317; just `__init__` + wrappers + the docstring/`__future__`/`os`/`TERRAIN_CHUNK_SIZE` header). New module ~325 LOC. **MILESTONE: ursina_terrain_fog_collab.py 1783 (pre-WK104) → ~165 — the #1 audit god-file fully decomposed into 5 focused modules (growth_sync, fog_visibility, ground_mesh, terrain_build, fog_overlay) + a thin stateful facade.**

---

## 7. COMMIT (Agent 01 only) — scoped add; NEVER `git add -A`; NEVER the 2 root user PNGs.

## 8. FOLLOW-UPS
- After WK109 the fog_collab god-file is done. Next major target: **`game/graphics/ursina_app.py`** (the other large render file; WK105 already pulled the debug probe). Scope its HUD/env cluster carefully (hot-path).
- The deferred **`handle_click` redesign** (hud.py:1058 — NOT a pure move).
- De-slop: dead `WATCH_MINIMAP_SIZE` (hud.py:57); the unused `from panda3d.core import SamplerState` carried into ursina_fog_overlay (a later de-slop, not now).
- **Non-render headless roadmap** (fully verifiable): config package split, ai/vocab.py + TaskRouter, world.py fog state-machine, WK34 zombie-type purge (21 files), context_builder/direct_prompt_validator, Move 9 SystemRunner (RISKY). Consider pivoting to these after the render god-files, since they are headlessly screenshot-free and lower-risk.
