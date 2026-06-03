# WK106 Round B — FOG/A: extract visibility-gating + chunk-culling + instanced-fog cluster

**Sprint key:** `wk106_round_b_ursina_terrain_fog_visibility`
**Plan author:** Agent 01 (Executive Producer / PM)
**Roadmap source:** `.cursor/plans/GPT 5.5 Codebase Improvements Recommendations.md` (#1 god-file decomposition) + `.cursor/plans/codebase_audit_2026-05-28_finding_inventory.md`
**Predecessor:** WK105 (`f649a5c`, ursina_app debug/FPS probe → ursina_app_debug_probe.py). WK104 (`6909891`, first ursina slice → ursina_terrain_growth_sync.py).
**Verification class:** ursina render code → **deferred-screenshot model** (headless gates + PM verbatim-diff + DEFERRED live captures). See memory `feedback_ursina_deferred_screenshots`.

---

## 0. ONE-PARAGRAPH SUMMARY (read this first)

`game/graphics/ursina_terrain_fog_collab.py` is still ~1454 LOC. We are extracting the **9-method visibility/cull/instanced-fog cluster** (current lines **L351–L656**) into a NEW leaf module `game/graphics/ursina_terrain_fog_visibility.py` using the **pure-move-behind-wrappers** pattern that has shipped 13 times this marathon (WK93–105) and twice for ursina (WK104 growth_sync, WK105 debug_probe). Each moved method becomes a module-level `def fn(owner, ...)` function (the `owner` is a `UrsinaTerrainFogCollab` instance); the class keeps a 1-line lazy-delegating wrapper with the EXACT original name+signature so every external caller is unchanged. **This is a behavior-preserving refactor — NOT a redesign. Do not "improve", rename, reorder, or reformat any moved logic. Move it byte-for-byte, changing ONLY `self.` → `owner.` (and the `getattr(self, ...)` comma-form) and intra-cluster method calls → direct module-function calls.**

---

## 1. THE CLUSTER (9 methods, exact current line ranges in `ursina_terrain_fog_collab.py`)

| # | Method | Lines | Externally called? | `self._r.*` used? | Owner slots used |
|---|--------|-------|--------------------|--------------------|------------------|
| 1 | `_apply_prop_visibility_state(self, ent, *, fog_visible=None, chunk_visible=None)` | 351–378 | No (intra only) | No | none (touches only `ent`) |
| 2 | `track_visibility_gated_terrain(self, ent, tx, ty)` | 380–392 | YES (build_3d_terrain, growth_sync, test) | `_visibility_gated_terrain`, `_visibility_gated_terrain_by_tile` | none |
| 3 | `untrack_visibility_gated_terrain(self, ent)` | 394–413 | YES (growth_sync) | `_visibility_gated_terrain`, `_visibility_gated_terrain_by_tile` | none |
| 4 | `sync_terrain_prop_tile_visibility(self, ent, vis)` | 415–425 | YES (growth_sync) + intra | No | none |
| 5 | `sync_visibility_gated_terrain(self, world, fog_revision)` | 427–478 | YES (ursina_renderer:586, test) | `_terrain_visibility_revision_seen`, `_visibility_gated_terrain`, `_terrain_visible_tiles_seen`, `_visibility_gated_terrain_by_tile` | none |
| 6 | `_build_terrain_chunks(self)` | 480–509 | YES (build_3d_terrain:1146, test:291) | `_visibility_gated_terrain`, `_tree_entities` | `_terrain_chunks`, `_visible_chunks`, `_chunks_built` |
| 7 | `cull_terrain_chunks(self, visible_rect, world)` | 511–601 | YES (ursina_renderer:588, test) | `_terrain_visibility_revision_seen` (incl. getattr comma-form) | `_chunks_built`, `_terrain_chunks`, `_visible_chunks`, `_last_cull_fog_revision`, `_instanced_trees_on`, `_instanced_nature_renderer`, `_instanced_trees_last_fog_rev` (getattr comma-form) |
| 8 | `_ensure_instanced_nature_renderer(self)` | 603–619 | YES (build_3d_terrain:1048, growth_sync:182) | No | `_instanced_nature_renderer` |
| 9 | `_sync_instanced_trees_fog(self, world, fog_revision)` | 621–656 | No (intra only) | No | `_instanced_trees_on`, `_instanced_nature_renderer`, `_instanced_trees_last_fog_rev`, `_tree_instance_ids` |

**Intra-cluster calls** (all become DIRECT module-function calls `fn(owner, ...)`, NOT `owner.fn(...)`):
- `self._apply_prop_visibility_state(...)` → `_apply_prop_visibility_state(owner, ...)` (called from #4, #5, #7)
- `self.sync_terrain_prop_tile_visibility(...)` → `sync_terrain_prop_tile_visibility(owner, ...)` (called from #5)
- `self._sync_instanced_trees_fog(...)` → `_sync_instanced_trees_fog(owner, ...)` (called from #5)

**One-way coupling (CONFIRMED, do not re-verify):** FOG/A is a *leaf*. Nothing in L351–656 calls `build_3d_terrain`, `_batch_static_terrain_for_chunks`, `ensure_fog_overlay`, `_apply_grass_texture`, or any other FOG/B method. FOG/B's `build_3d_terrain` calls INTO FOG/A (`self.track_visibility_gated_terrain`, `self._build_terrain_chunks`, `self._ensure_instanced_nature_renderer`) — after the move these hit the wrappers, unchanged.

---

## 2. OWNER ATTRIBUTE MAP (memorize — every `self.X` becomes one of these)

**Owner slots → `owner.X`** (these ARE in `UrsinaTerrainFogCollab.__slots__`, confirmed L53–65):
```
_terrain_chunks   _visible_chunks   _chunks_built   _last_cull_fog_revision
_instanced_trees_on   _instanced_nature_renderer   _tree_instance_ids   _instanced_trees_last_fog_rev
```

**Parent-renderer state → `owner._r.X`** (these live on the UrsinaRenderer, reached via `self._r`):
```
_visibility_gated_terrain   _visibility_gated_terrain_by_tile
_terrain_visibility_revision_seen   _terrain_visible_tiles_seen   _tree_entities
```

**RULE:** In the moved code, `self._r.<anything>` → `owner._r.<anything>`. Every OTHER `self.<slot>` (from the owner-slots list above) → `owner.<slot>`. There is NO `self.X` in this cluster that is neither an owner slot nor `self._r.X` — if you find one, STOP and flag it.

**Comma-form `getattr` — DO NOT MISS THESE** (the regex-blind cases):
- L524 `getattr(self, '_chunks_built', False)` → `getattr(owner, '_chunks_built', False)`
- L547 `getattr(self._r, "_terrain_visibility_revision_seen", -1)` → `getattr(owner._r, "_terrain_visibility_revision_seen", -1)`
- L594 `getattr(self._r, "_terrain_visibility_revision_seen", -1)` → `getattr(owner._r, ...)`
- L595 `getattr(self, "_instanced_trees_last_fog_rev", -1)` → `getattr(owner, ...)`

After the move, **`grep -n "self" game/graphics/ursina_terrain_fog_visibility.py` must return ZERO matches** (no `self.`, no `self,`, no `(self`, no bare `self`).

---

## 3. THE NEW MODULE — `game/graphics/ursina_terrain_fog_visibility.py`

Model it EXACTLY on the WK104 sibling `game/graphics/ursina_terrain_growth_sync.py` (header → imports → TYPE_CHECKING → `TERRAIN_CHUNK_SIZE` mirror → functions). Header + imports VERBATIM as below:

```python
"""Visibility-gating + frustum chunk-culling + instanced-tree fog for the Ursina terrain renderer (WK106 slice of ursina_terrain_fog_collab.py).

Extracted VERBATIM from game/graphics/ursina_terrain_fog_collab.py: the 9-method
visibility/cull/instanced-fog cluster (_apply_prop_visibility_state,
track_visibility_gated_terrain, untrack_visibility_gated_terrain,
sync_terrain_prop_tile_visibility, sync_visibility_gated_terrain,
_build_terrain_chunks, cull_terrain_chunks, _ensure_instanced_nature_renderer,
_sync_instanced_trees_fog) as owner-arg module functions. The owner is
UrsinaTerrainFogCollab, reached via owner.* (own slots) / owner._r.* (parent
UrsinaRenderer). UrsinaTerrainFogCollab keeps 1-line delegating wrappers (same
names + signatures) so build_3d_terrain / ursina_renderer.py / growth_sync /
test_terrain_perf call sites are unchanged.

Acyclic: imports only leaf graphics/config/world modules + ursina_environment
(_set_static_prop_fog_tint) + ursina_terrain_growth_sync (_InstancedTreeStub,
one-way edge); imports UrsinaTerrainFogCollab ONLY under TYPE_CHECKING.
ursina_terrain_fog_collab.py imports THIS module LAZILY inside the wrapper
bodies (one-way edge: fog_collab -> fog_visibility at call time only).
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

import config
from game.graphics.ursina_environment import _set_static_prop_fog_tint
from game.graphics.ursina_terrain_growth_sync import _InstancedTreeStub
from game.world import Visibility

if TYPE_CHECKING:
    from ursina import Entity
    from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab

TERRAIN_CHUNK_SIZE = 16  # MIRROR of ursina_terrain_fog_collab.TERRAIN_CHUNK_SIZE (L47); do NOT back-import (cycle). Keep in sync.
```

Then the 9 functions, in the SAME ORDER as the source, each converted from `def name(self, ...)` to `def name(owner, ...)`. **Type annotations:** keep them; `Entity` annotation is fine because `from __future__ import annotations` makes all annotations lazy strings (never evaluated at runtime), so the TYPE_CHECKING-only `Entity` import is sufficient. Use `owner: UrsinaTerrainFogCollab` and `ent: Entity` in signatures (string-lazy, no runtime cost).

### 3.1 Worked example — function #1 (`_apply_prop_visibility_state`)

Source (L351–378) → new module (note: body uses NO `self`/`owner`; `owner` param kept for signature uniformity with the seam-test "owner-first" assertion — DO NOT drop it):
```python
def _apply_prop_visibility_state(
    owner,
    ent: Entity,
    *,
    fog_visible: bool | None = None,
    chunk_visible: bool | None = None,
) -> None:
    """WK58 Phase 1 Fix 1A: compose fog and chunk visibility into ent.enabled.
    ...(docstring VERBATIM)...
    """
    if fog_visible is not None:
        ent._ks_fog_visible = bool(fog_visible)
    if chunk_visible is not None:
        ent._ks_chunk_visible = bool(chunk_visible)
    should_enable = bool(getattr(ent, "_ks_fog_visible", True)) and bool(
        getattr(ent, "_ks_chunk_visible", True)
    )
    if getattr(ent, "_ks_prop_enabled", None) is not should_enable:
        try:
            ent.enabled = should_enable
        except (AssertionError, Exception):
            pass
        ent._ks_prop_enabled = should_enable
```

### 3.2 Worked example — function #4 (`sync_terrain_prop_tile_visibility`) — shows intra-cluster direct call

Source (L415–425) → new module (note `self._apply_prop_visibility_state(...)` → `_apply_prop_visibility_state(owner, ...)`):
```python
def sync_terrain_prop_tile_visibility(owner, ent: Entity, vis: Visibility) -> None:
    # WK58 Phase 1 Fix 1A: write only the fog bit; chunk visibility is owned
    # by ``cull_terrain_chunks`` and composed via ``_apply_prop_visibility_state``.
    is_visible = vis != Visibility.UNSEEN
    _apply_prop_visibility_state(owner, ent, fog_visible=is_visible)
    if is_visible:
        try:
            seen_mult = float(getattr(config, "URSINA_SEEN_PROP_FOG_MULT", 0.5))
        except Exception:
            seen_mult = 0.5
        _set_static_prop_fog_tint(ent, seen_mult if vis == Visibility.SEEN else 1.0)
```

### 3.3 The remaining 7 functions

Apply the same mechanical conversion to #2, #3, #5, #6, #7, #8, #9 using the **Owner Attribute Map (§2)**:
- Every `self._r.X` → `owner._r.X`
- Every `self.<owner-slot>` → `owner.<owner-slot>`
- Every `self._apply_prop_visibility_state(...)` → `_apply_prop_visibility_state(owner, ...)`
- Every `self.sync_terrain_prop_tile_visibility(...)` → `sync_terrain_prop_tile_visibility(owner, ...)`
- Every `self._sync_instanced_trees_fog(...)` → `_sync_instanced_trees_fog(owner, ...)`
- The 4 `getattr` comma-forms in §2
- `isinstance(ent, _InstancedTreeStub)` (L497 in #6) — `_InstancedTreeStub` resolves to the back-import at the top of the new module. UNCHANGED.
- `os.environ.get(...)` (L593 in #7) — `os` is imported at top. UNCHANGED.
- All docstrings, comments, blank lines, `try/except` shapes: VERBATIM.

---

## 4. EDITS TO `ursina_terrain_fog_collab.py`

### 4.1 Remove ONE now-unused import name
In the `from game.graphics.ursina_environment import (...)` block (L15–35), DELETE the single line:
```python
    _set_static_prop_fog_tint,
```
**Keep every other name in that block** (they are used by staying FOG/B code). After deletion, `grep -n "_set_static_prop_fog_tint" game/graphics/ursina_terrain_fog_collab.py` must return ZERO matches (it was only used at L425/L448, both moving).

### 4.2 KEEP (do NOT touch):
- `TERRAIN_CHUNK_SIZE = 16` at L47 — `test_terrain_perf.py:54` imports it from this module. It stays the canonical definition.
- The `_InstancedTreeStub` back-import at L43 — staying `build_3d_terrain` constructs `_InstancedTreeStub(...)` at L1071. STILL NEEDED.

### 4.3 Delete the 9 method bodies (L351–656) and replace with 9 wrappers
Delete the entire block from `def _apply_prop_visibility_state` (L351) through the end of `_sync_instanced_trees_fog` (L656, the line `self._instanced_trees_last_fog_rev = engine_rev`). Replace with the following 9 wrappers, placed at the SAME location (so `_batch_static_terrain_for_chunks` at L658 still follows them). Model the wrapper form EXACTLY on the WK104 wrappers at L1448–1454:

```python
    def _apply_prop_visibility_state(self, ent, *, fog_visible=None, chunk_visible=None) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility._apply_prop_visibility_state(
            self, ent, fog_visible=fog_visible, chunk_visible=chunk_visible
        )

    def track_visibility_gated_terrain(self, ent, tx: int, ty: int) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility.track_visibility_gated_terrain(self, ent, tx, ty)

    def untrack_visibility_gated_terrain(self, ent) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility.untrack_visibility_gated_terrain(self, ent)

    def sync_terrain_prop_tile_visibility(self, ent, vis) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility.sync_terrain_prop_tile_visibility(self, ent, vis)

    def sync_visibility_gated_terrain(self, world, fog_revision: int) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility.sync_visibility_gated_terrain(self, world, fog_revision)

    def _build_terrain_chunks(self) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility._build_terrain_chunks(self)

    def cull_terrain_chunks(self, visible_rect, world) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility.cull_terrain_chunks(self, visible_rect, world)

    def _ensure_instanced_nature_renderer(self):
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility._ensure_instanced_nature_renderer(self)

    def _sync_instanced_trees_fog(self, world, fog_revision: int) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility._sync_instanced_trees_fog(self, world, fog_revision)
```

**Wrapper rules:** signatures must match the ORIGINAL method signatures byte-for-byte (so `cull_terrain_chunks(self, visible_rect, world)` keeps positional params; `_apply_prop_visibility_state` keeps the `*, fog_visible=None, chunk_visible=None` keyword-only form). The lazy `from game.graphics import ursina_terrain_fog_visibility` INSIDE each body is what keeps the edge one-way (no top-level import of the new module in fog_collab → no cycle).

---

## 5. EDIT TO `tests/test_terrain_perf.py` (the patch-retarget HAZARD — Agent 11 owns this)

This is an EXISTING headless characterization harness that drives FOG/A directly. After the move it still passes ONLY if the `_set_static_prop_fog_tint` patch is retargeted to where the moved code now resolves that name.

**Why:** `test_culling_reapplies_after_fog_change` (L300) does `with patch.object(tfc, "_set_static_prop_fog_tint", lambda *a, **kw: None):` then calls `collab.sync_visibility_gated_terrain(...)`. After WK106, `sync_visibility_gated_terrain` (and the `sync_terrain_prop_tile_visibility` it calls) live in `ursina_terrain_fog_visibility` and resolve `_set_static_prop_fog_tint` in THAT module's globals. Patching `tfc._set_static_prop_fog_tint` (the old module) would no longer intercept the call → the test would try the real tint helper on a `_FakeEntity` and behavior would diverge.

**Exact edits:**
1. After L52 (`import game.graphics.ursina_terrain_fog_collab as tfc`), ADD:
   ```python
   import game.graphics.ursina_terrain_fog_visibility as tfv
   ```
2. Change L300 from:
   ```python
           with patch.object(tfc, "_set_static_prop_fog_tint", lambda *a, **kw: None):
   ```
   to:
   ```python
           with patch.object(tfv, "_set_static_prop_fog_tint", lambda *a, **kw: None):
   ```

**DO NOT touch** the other `tfc.` references at L717–718 (`tfc.pygame.image.frombuffer`, `tfc.TerrainTextureBridge.refresh_surface_texture`) — those patch `ensure_fog_overlay`, which STAYS in fog_collab. Leave the `from ...ursina_terrain_fog_collab import (TERRAIN_CHUNK_SIZE, UrsinaTerrainFogCollab)` (L53–56) UNCHANGED — `TERRAIN_CHUNK_SIZE` still lives in fog_collab.

---

## 6. AGENT TASKS

### Agent 09 (ArtDirector / Pixel-Animation-VFX) — W1: the extraction
**Onboarding:** read `.cursor/rules/agent-09-artdirector-onboarding.mdc`; you are Agent 09. Then read this plan + the PM hub sprint `wk106_round_b_ursina_terrain_fog_visibility`.
**Reference sibling:** open `game/graphics/ursina_terrain_growth_sync.py` (WK104) — your new module must mirror its shape exactly.
**Do:**
1. Create `game/graphics/ursina_terrain_fog_visibility.py` per §3 (header+imports verbatim; 9 functions converted per §2/§3).
2. Edit `ursina_terrain_fog_collab.py` per §4 (remove the one import line; delete L351–656; insert the 9 wrappers).
**Self-verification (run ALL, paste output into your log):**
- `python -c "import game.graphics.ursina_terrain_fog_visibility"` → no error.
- `python -c "import game.graphics.ursina_terrain_fog_collab"` → no error.
- Fresh-subprocess BOTH import orders (no cycle):
  - `python -c "import game.graphics.ursina_terrain_fog_collab; import game.graphics.ursina_terrain_fog_visibility; print('order A ok')"`
  - `python -c "import game.graphics.ursina_terrain_fog_visibility; import game.graphics.ursina_terrain_fog_collab; print('order B ok')"`
- `grep -n "self" game/graphics/ursina_terrain_fog_visibility.py` → ZERO matches (no `self` anywhere).
- `grep -n "_set_static_prop_fog_tint" game/graphics/ursina_terrain_fog_collab.py` → ZERO matches.
- `python -m pytest tests/test_terrain_perf.py -q` → run it; it MAY have 1 failure in `test_culling_reapplies_after_fog_change` UNTIL Agent 11 retargets the patch (§5). Note that in your log; do NOT edit the test yourself.
- `python -m pytest tests/test_wk104_ursina_terrain_growth_sync.py -q` → must still pass (you touched the back-import neighbor).
**DO NOT COMMIT. DO NOT run git add/commit/push. DO NOT edit any test file. Update `agent_09_ArtDirector_Pixel_Animation_VFX.json` with a WK106 entry when done.**

### Agent 11 (QA / Test-Engineering Lead) — W2: seam test + patch retarget + DoD
**Onboarding:** read `.cursor/rules/agent-11-qa-onboarding.mdc`; you are Agent 11. Then read this plan + the PM hub sprint.
**Reference sibling:** open `tests/test_wk104_ursina_terrain_growth_sync.py` — your new seam test mirrors its structure.
**Do:**
1. Edit `tests/test_terrain_perf.py` per §5 (add the `tfv` import; retarget the L300 patch). This is the critical hazard fix.
2. Create `tests/test_wk106_ursina_terrain_fog_visibility.py` — an import-only headless seam test (NO Ursina window). Mirror the WK104 test. Cover:
   - **fn-exists:** all 9 names are module-level functions in `ursina_terrain_fog_visibility`.
   - **owner-first signature:** each function's first parameter is named `owner` (use `inspect.signature`).
   - **wrapper-delegation:** for each of the 9, monkeypatch the module function to a sentinel-recording stub, then call the corresponding method on `object.__new__(UrsinaTerrainFogCollab)` (bypass `__init__`; for methods that read attrs, set just enough — but delegation tests only need to assert the wrapper forwards `self` as `owner` arg 1 and passes the other args through; the stub returns a sentinel and records args). Assert the wrapper returned the sentinel and arg[0] is the instance.
   - **AST no-`self`:** parse `ursina_terrain_fog_visibility.py` (read with `encoding="utf-8-sig"`) and assert no `ast.Name` with id `self` appears anywhere.
   - **AST no-cycle:** assert `ursina_terrain_fog_collab.py` (read `utf-8-sig`) does NOT contain a top-level/module-level `import ursina_terrain_fog_visibility` (the only references must be the lazy `from game.graphics import ursina_terrain_fog_visibility` INSIDE function bodies). Assert `ursina_terrain_fog_visibility.py` imports `UrsinaTerrainFogCollab` ONLY under `if TYPE_CHECKING:`.
   - **back-import source guard:** assert `ursina_terrain_fog_visibility.py` contains `from game.graphics.ursina_terrain_growth_sync import _InstancedTreeStub` (single source for the stub) and does NOT define its own `class _InstancedTreeStub`.
   - **constant mirror:** assert `ursina_terrain_fog_visibility.TERRAIN_CHUNK_SIZE == ursina_terrain_fog_collab.TERRAIN_CHUNK_SIZE == 16`.
   - **fresh-subprocess both-orders** (use `subprocess.run([sys.executable, "-c", ...])`, assert returncode 0) — both import orders.
3. Run the FULL DoD gate suite (see §7) and paste all output into your log.
**DO NOT COMMIT. Update `agent_11_QA_TestEngineering_Lead.json` with a WK106 entry when done.**

---

## 7. DEFINITION OF DONE (Agent 11 runs; Agent 01 re-verifies independently)

1. `python -m pytest -q` → ALL pass (expect ~1268 passed after +30; 0 failed). `test_terrain_perf.py` GREEN (patch retarget landed).
2. `python tools/determinism_guard.py` → clean (note: it EXCLUDES `game/graphics/**`, so this slice is out of its scope — it must still pass for the rest).
3. **WK67 keystone digest byte-identical:** `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q` → pass (digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`). (Do NOT use `python -m tests.test_wk67_ai_boundary` — it prints a different live value by design.)
4. `python tools/qa_smoke.py --quick` → green.
5. Headless import smoke + fresh-subprocess BOTH orders → no cycle (per §6).
6. `grep "self" ursina_terrain_fog_visibility.py` → zero.
7. New seam test `tests/test_wk106_ursina_terrain_fog_visibility.py` passes.
8. **Agent 01 PM verbatim-diff gate:** extract each of the 9 methods from HEAD (`git show HEAD:game/graphics/ursina_terrain_fog_collab.py`), normalize `self.`→`owner.`, `getattr(self,`→`getattr(owner,`, `getattr(self._r,`→`getattr(owner._r,`, and intra-cluster `self.<fn>(`→`<fn>(owner, ` ; diff against the new module. Expect ONLY: signature line (`self`→`owner`), the 3 intra-cluster direct-call rewrites, the 4 getattr comma-forms. Any OTHER diff = a defect → bounce to Agent 09.
9. **Live before/after Ursina screenshots: DEFERRED to Jaimie's end-of-marathon test pass** (headless agents have no GPU; `tools/run_ursina_capture_once.py` scenarios `wk61_hold_g_tax_overlay` / `ursina_melee_combat` cannot run in-agent). Flag DEFERRED in the commit body + PM closeout. Per memory `feedback_ursina_deferred_screenshots`.

LOC target: `ursina_terrain_fog_collab.py` 1454 → ~1150 (−~300). New module ~340 LOC.

---

## 8. COMMIT (Agent 01 only, after DoD green)
Scoped add ONLY (NEVER `git add -A`): the new module, the 2 edited source/test files, the new seam test, the plan doc, the PM hub, agent logs. **NEVER add the 2 root user PNGs** ("13 Hours…", "9.5 Hours…").
Commit message notes: ursina render slice, deferred live screenshots, digest byte-identical, suite count.

---

## 9. FOLLOW-UPS (next sprints, in order)
- **WK107 = FOG/B** (~640 LOC: `build_3d_terrain` + `_build_terrain_ground_mesh` + `_apply_grass_texture` + `_batch_static_terrain_for_chunks` + the cave-entrance shader-input block). After WK106, FOG/B's calls into the visibility cluster are already wrappers → clean. Split further if a single move is too large; consider a `ursina_terrain_build.py`. Same deferred-screenshot model.
- Then: ursina_app HUD/env cluster (hot-path, scope carefully).
- The deferred `handle_click` redesign (hud.py — NOT a pure move).
- De-slop: delete dead `WATCH_MINIMAP_SIZE` (hud.py:57, zero consumers; flip `tests/test_wk101_hud_hero_menu_layout.py` assert-present→assert-absent).
- Non-render headless roadmap: config package split, ai/vocab.py + TaskRouter, world.py fog state-machine, WK34 zombie-type purge, context_builder/direct_prompt_validator, Move 9 SystemRunner (RISKY).
