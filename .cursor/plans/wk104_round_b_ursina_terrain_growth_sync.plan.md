# WK104 Sprint Plan — Round B-21: extract ursina_terrain_growth_sync.py (dynamic-tree + log-stack sync) — first ursina god-file slice

**Author:** Agent 01 (PM) · **Date:** 2026-05-31 · **Goal:** all tests pass; the dynamic-growth sync cluster (`sync_dynamic_trees`, `sync_log_stacks`, `_InstancedTreeStub`) extracted from `game/graphics/ursina_terrain_fog_collab.py` (1783 LOC) into a NEW `game/graphics/ursina_terrain_growth_sync.py`; terrain tree/log-pile rendering behaves identically.
**Predecessors:** WK87–92 (ursina renderer slices — the PROVEN ursina pure-move + headless-seam-test pattern), WK93–103 (hud.py slices). **Roadmap:** Round B — pivot to the ursina god-files (now larger than hud.py). First ursina slice; chosen + de-risked by the WK104 ursina grounding workflow.

## 0. TL;DR
hud.py is done (1160 LOC, 11 slices). The two largest remaining god-files are ursina renderer code: `ursina_terrain_fog_collab.py` (1783) and `ursina_app.py` (1525). WK104 takes the safest, most self-contained ursina sub-slice: the **dynamic-growth sync cluster** — `sync_dynamic_trees` (scale existing 3D tree entities from sim `Tree.growth_percentage`, spawn saplings, destroy removed trees), `sync_log_stacks` (render chopped-tree log piles), and `_InstancedTreeStub` (the tile-keyed DTO the instanced tree path uses) — into a NEW `game/graphics/ursina_terrain_growth_sync.py`, using the WK87–92 **owner-arg pure-move** pattern: module functions `def fn(owner, ...)` (every `self.`→`owner.`) behind 1-line delegating wrappers on the `UrsinaTerrainFogCollab` class. ~258 LOC leaves the file.

**VERIFICATION NOTE (read first):** ursina render code is NOT covered by the pygame WK67 digest, `determinism_guard` (which excludes `game/graphics/**`), or the pygame screenshot tool. The headless gates (import smoke + a new WK92-style seam test + full suite + qa_smoke) prove the module IMPORTS, the wrappers DELEGATE, and there's NO cycle — but give ZERO render-fidelity coverage. Per Jaimie's 2026-05-31 decision ("proceed, defer screenshots to me"), this slice ships on headless gates + a **meticulous line-by-line PM verbatim-diff review**, with the live before/after Ursina captures (`run_ursina_capture_once.py`) **DEFERRED to Jaimie's end-of-marathon test pass** (they need a real GPU/window the headless agents lack). See [[feedback_ursina_deferred_screenshots]]. The pure-move is behavior-preserving by construction; the PM diff review is the primary safety net.

## 1. Scope
**IN:** create `game/graphics/ursina_terrain_growth_sync.py`; move VERBATIM these 3 members out of `game/graphics/ursina_terrain_fog_collab.py`:

| Member | current lines | → in new module | Notes |
|---|---|---|---|
| `class _InstancedTreeStub` | 44–124 (~81 LOC) | `class _InstancedTreeStub` (UNCHANGED) | Self-contained DTO: takes `renderer_ref` as a ctor param, uses only own `__slots__` + `self._renderer_ref`. NO owner/`_r` ref → moves byte-identical, NO `self.`→`owner.` rewrite. |
| `sync_dynamic_trees(self, world, snapshot_trees)` | 1525–1688 | `def sync_dynamic_trees(owner, world, snapshot_trees) -> None` | Every `self.`→`owner.` |
| `sync_log_stacks(self, world, snapshot_log_stacks)` | 1690–1783 | `def sync_log_stacks(owner, world, snapshot_log_stacks) -> None` | Every `self.`→`owner.` |

**Owner-arg rule (WK92 pattern):** in the two moved FUNCTIONS, every `self.<x>` becomes `owner.<x>`. Renderer state stays reached via `owner._r.*` (`owner._r._tree_entities`, `owner._r._terrain_entity`, `owner._r._log_stack_entities`). Collab `__slots__` stay reached via `owner.*` (`owner._tree_sync_tick_counter`, `owner._last_growth_by_tile`, `owner._terrain_chunks`, `owner._chunks_built`, `owner._instanced_trees_on`, `owner._instanced_nature_renderer`, `owner._tree_instance_ids`, `owner._instanced_trees_last_fog_rev`). FOG/A + helper cross-calls stay on the owner (these methods are NOT moved): `owner.track_visibility_gated_terrain(...)` (1630), `owner.untrack_visibility_gated_terrain(...)` (1675), `owner.sync_terrain_prop_tile_visibility(...)` (1771), `owner._ensure_instanced_nature_renderer()` (1590). `_InstancedTreeStub(...)` constructions inside `sync_dynamic_trees` (1601) become a bare module-local class reference (it's now in this module).

**DEFERRED function-local imports — carry VERBATIM inside the moved fns (do NOT hoist to module top):** in `sync_dynamic_trees`: `from game.graphics.terrain_height import get_terrain_height, is_initialized as _hm_ok` (1579) and `import ursina as u` (1673); in `sync_log_stacks`: the same `terrain_height` import (1739) and `import ursina as u` (1777).

**STAYS on `UrsinaTerrainFogCollab`** (DO NOT move): the FOG/A methods (`track/untrack_visibility_gated_terrain`, `sync_terrain_prop_tile_visibility`, `_apply_prop_visibility_state`, `_set_static_prop_fog_tint`), `_ensure_instanced_nature_renderer` (680), `_sync_instanced_trees_fog` (698), `build_3d_terrain`, `cull_terrain_chunks`, `sync_visibility_gated_terrain`, and ALL the owner `__slots__` state. **OUT.**

## 2. Pattern (WK92, verbatim) — the new module + the back-import
`game/graphics/ursina_terrain_growth_sync.py` header:
```python
"""Dynamic tree-growth + log-stack sync for the Ursina terrain renderer (WK104 slice of ursina_terrain_fog_collab.py).

Extracted VERBATIM from game/graphics/ursina_terrain_fog_collab.py: sync_dynamic_trees,
sync_log_stacks (owner-arg module functions; the owner is UrsinaTerrainFogCollab, reached
via owner.* / owner._r.*), and the _InstancedTreeStub DTO (standalone). UrsinaTerrainFogCollab
keeps 1-line delegating wrappers (same names) so ursina_renderer.py's call sites are unchanged.
Acyclic: this module imports only leaf graphics/config/world modules + ursina at top; it
imports UrsinaTerrainFogCollab ONLY under TYPE_CHECKING. ursina_terrain_fog_collab.py re-imports
_InstancedTreeStub from here (one-way edge).
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import config
from ursina import Entity, color   # (+ Vec2/Vec3 ONLY if the moved bodies reference them at module scope — include exactly what is used)
from game.graphics.ursina_coords import SCALE, sim_px_to_world_xz
from game.graphics.ursina_environment import (
    TREE_SCALE_MULTIPLIER,
    _environment_model_path,
    _environment_tree_model_list,
    _finalize_kenney_scatter_entity,
    _scatter_model_index,
)
from game.world import TileType, Visibility
if TYPE_CHECKING:
    from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab

TERRAIN_CHUNK_SIZE = 16  # MIRROR of ursina_terrain_fog_collab.TERRAIN_CHUNK_SIZE (L41); do NOT back-import (cycle). Keep in sync.
```
**W1 MUST trim the module-level import list to EXACTLY the names the two moved bodies reference at module scope** (read the bodies; e.g. if `Vec2`/`Vec3`/`px_to_world`/`pygame` are unused by these two fns, omit them; if a `ursina_environment` helper isn't used, omit it). The deferred `terrain_height`/`import ursina as u` stay function-local. Reference `_InstancedTreeStub` and `TERRAIN_CHUNK_SIZE` bare (module-local).

**THE BACK-IMPORT (critical — invisible to import smoke):** `_InstancedTreeStub` is constructed/checked by STAYING code in `ursina_terrain_fog_collab.py` — `build_3d_terrain` (construct, L1148) and `cull_terrain_chunks` (`isinstance`, L574). After moving the class out, `ursina_terrain_fog_collab.py` MUST add a top-level `from game.graphics.ursina_terrain_growth_sync import _InstancedTreeStub` (one-way edge: fog_collab → growth_sync; growth_sync never imports fog_collab at runtime, so acyclic). WITHOUT this, those staying methods raise `NameError` at call time — which NO headless test catches. The PM verbatim-diff review MUST confirm this line was added.

### Wrappers on `UrsinaTerrainFogCollab` (replace the two moved method bodies; keep EXACT names/signatures):
```python
def sync_dynamic_trees(self, world, snapshot_trees) -> None:
    from game.graphics import ursina_terrain_growth_sync
    return ursina_terrain_growth_sync.sync_dynamic_trees(self, world, snapshot_trees)

def sync_log_stacks(self, world, snapshot_log_stacks) -> None:
    from game.graphics import ursina_terrain_growth_sync
    return ursina_terrain_growth_sync.sync_log_stacks(self, world, snapshot_log_stacks)
```
`ursina_renderer.py:580/582` call `self._terrain_fog.sync_dynamic_trees(...)` / `sync_log_stacks(...)` — UNCHANGED. Move VERBATIM.

## 3. Definition of Done
- **A.** `python -m pytest -q` all pass (baseline **1193 passed / 4 skipped / 0 failed** at WK103 close; +new seam test → expect ~1198+).
- **B.** `python tools/determinism_guard.py` clean (it excludes game/graphics/** — unaffected, but must stay clean).
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` (the pytest assertion `tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable` — NOT the `python -m tests.test_wk67...` printout, which prints a different live value by design). A pure ursina move must not change it.
- **D.** `python tools/qa_smoke.py --quick` green.
- **E.** headless import smoke: `python -c "import game.graphics.ursina_terrain_growth_sync; import game.graphics.ursina_terrain_fog_collab; print('IMPORT_OK')"` prints OK; AND both fresh-subprocess orders succeed.
- **F.** the 3 members live in `game/ui/...` NO — in `game/graphics/ursina_terrain_growth_sync.py`; `UrsinaTerrainFogCollab` keeps the 2 wrapper names (ursina_renderer.py:580/582 unchanged); `ursina_terrain_fog_collab.py` re-imports `_InstancedTreeStub` from the new module; the FOG/A cross-calls + owner `__slots__` stay on the owner; `TERRAIN_CHUNK_SIZE` mirrored locally (NOT back-imported); deferred imports carried verbatim; file smaller (1783 → ~1525); **no import cycle**; ZERO `self.` in the two moved FUNCTIONS (the `_InstancedTreeStub` methods keep their own `self`, that's correct — it's a class).
- **G.** **DEFERRED (Jaimie's end test):** before/after live Ursina screenshots via `python tools/run_ursina_capture_once.py --scenario wk61_hold_g_tax_overlay` (+ `ursina_melee_combat`) — the visible surface is terrain/grass/trees/fog + log piles. Flag in the commit + PM hub as DEFERRED-NEEDS-DISPLAY; NOT run by the headless agents.
- **H.** A new seam test `tests/test_wk104_ursina_terrain_growth_sync.py` (W2). Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 09 ArtDirector OR 08 UX/UI — graphics owner):** create `ursina_terrain_growth_sync.py` (header + the 3 members; `_InstancedTreeStub` byte-identical, the 2 fns `self.`→`owner.`); trim module imports to exactly what's used; add the 2 wrappers on `UrsinaTerrainFogCollab`; add the `_InstancedTreeStub` back-import to `ursina_terrain_fog_collab.py`; mirror `TERRAIN_CHUNK_SIZE` locally. Run: import smoke (both orders), full suite, determinism_guard, WK67 digest (pytest), qa_smoke --quick. Verify ZERO `self.` in the two moved fns + no module-top `ursina_terrain_fog_collab` import in the new module (TYPE_CHECKING-only). DO NOT attempt the live ursina screenshots (no display) — note them as deferred. Update own log. **DO NOT COMMIT.**
- **W2 (Agent 11 QA):** seam test `tests/test_wk104_ursina_terrain_growth_sync.py` — model EXACTLY on `tests/test_wk92_ursina_unit_sync.py` (READ it first): (1) `sync_dynamic_trees`/`sync_log_stacks` exist + callable in the new module with `owner`-first signature; `_InstancedTreeStub` exists in the new module + is importable from `ursina_terrain_fog_collab` (the back-import). (2) the 2 `UrsinaTerrainFogCollab` wrappers delegate — monkeypatch-spy each module fn on a bare `object.__new__(UrsinaTerrainFogCollab)` AND an AST check that each wrapper body calls `ursina_terrain_growth_sync.<fn>(self, ...)`. (3) AST guard: the new module has NO module-top runtime import of `ursina_terrain_fog_collab` (TYPE_CHECKING-only OK). (4) fresh-subprocess `python -c "import a; import b"` in BOTH orders → rc 0 (no cycle). (5) a static check that `ursina_terrain_fog_collab.py` source contains the `from game.graphics.ursina_terrain_growth_sync import _InstancedTreeStub` line (guards the silent-NameError back-edge). Run full DoD A–F + H. Update own log. **DO NOT COMMIT.**
- **PM gate (me):** a meticulous line-by-line VERBATIM-DIFF review (`git diff` of the two moved fns): confirm every `self.`→`owner.` is correct and NOTHING else changed; the back-import line is present; `TERRAIN_CHUNK_SIZE` mirrored; deferred imports carried verbatim; shared `__slots__` not duplicated as module state. This is the primary safety net given the deferred screenshot.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| `_InstancedTreeStub` back-import omitted → `build_3d_terrain`/`cull_terrain_chunks` NameError at call time (invisible to import smoke + seam test) | Med | W2 static-source check for the back-import line; PM diff review explicitly confirms it; flag prominently |
| A `self.`→`owner.` missed in the two moved fns → wrong attribute at runtime (imports fine, renders wrong; NO headless gate catches it) | Med | PM line-by-line verbatim diff is the primary net; grep new fns for `self.` == ZERO; the deferred live screenshot is the final backstop (Jaimie's end test) |
| `TERRAIN_CHUNK_SIZE` back-imported from fog_collab → import cycle (breaks both-orders subprocess) | Low | mirror as local `=16` with a sync comment; W2 both-orders subprocess test |
| Deferred local imports hoisted to module top → import-order surprise | Low | plan says carry verbatim inside the fns; PM diff review |
| Render regression invisible to all headless gates | Med (accepted) | per [[feedback_ursina_deferred_screenshots]]: pure-move + PM diff + WK87-92 precedent; live before/after captures DEFERRED to Jaimie's end test (DoD G) — explicitly flagged, not silently skipped |
| WK67 digest changes | Very Low | ursina move touches zero sim/AI; if it changes, the slice touched something out of scope → STOP |

## 6. Success
The dynamic-growth sync cluster lives in `game/graphics/ursina_terrain_growth_sync.py` behind 2 delegating wrappers (+ the relocated `_InstancedTreeStub` with its back-import) — proven by 1193+ green tests (incl. a new WK92-style seam test), clean determinism guard, unchanged WK67 digest, a clean headless import smoke (both orders), a verified no-cycle, and a meticulous PM verbatim-diff review. Live render fidelity is verified by Jaimie's deferred before/after Ursina captures. `ursina_terrain_fog_collab.py` drops ~258 LOC (1783 → ~1525); first ursina god-file slice.

## 7. Kickoff
Roster: 09 ArtDirector or 08 UX/UI (W1 — graphics owner), 11 QA (W2), PM diff-gate. Order: W1 → PM verbatim-diff gate → W2 → commit+push (with DEFERRED-screenshot flag). Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE (`self.`→`owner.` in the 2 fns; `_InstancedTreeStub` byte-identical); ADD the `_InstancedTreeStub` back-import to fog_collab; mirror `TERRAIN_CHUNK_SIZE` locally; carry deferred imports verbatim; keep the 2 wrapper names + FOG/A cross-calls + owner `__slots__` on the owner; TYPE_CHECKING-only owner import; ZERO `self.` in the 2 moved fns; the live ursina screenshots are DEFERRED to Jaimie (no display in-agent) — do NOT block on them but DO flag them; own log; DO NOT COMMIT.
Follow-ups (ursina, in order, all deferred-screenshot): FOG/A (visibility-gating + chunk-culling, ~480 LOC) + FOG/B (terrain-mesh build, ~640 LOC) — move each as a cohesive unit (they inter-call); ursina_app APP/C (env-gated debug/FPS scaffolding, ~290 LOC — needs a NEW seam test, ursina_app has none today). DEFER: handle_click redesign (hud.py:1058), ursina_app APP/A camera + APP/B input hook (closures/monkeypatch). De-slop: delete dead WATCH_MINIMAP_SIZE (hud.py:57). Also remaining non-render roadmap (fully headless-verifiable): config package split, ai/vocab.py + TaskRouter, world.py fog state-machine, the 21-file WK34 zombie-type purge, context_builder/direct_prompt_validator, Move 9 SystemRunner (RISKY).
