# Ursina Entities Overload Solution — Master Plan

**Date:** 2026-05-18
**Target:** 45-60 FPS with full map revealed (`/revealmap`), with 60 FPS as the stretch target
**Format:** Two staged implementation rounds plus an optional tree-instancing spike
**Current baseline:** ~29-43 FPS (fog active) → ~6-15 FPS (full reveal)
**Root cause:** ~13,000 individual Ursina Entity objects for terrain props

---

## TABLE OF CONTENTS

1. [Diagnosis Summary](#1-diagnosis-summary)
2. [Agent Roster & Responsibilities](#2-agent-roster--responsibilities)
3. [Test Tooling (Build First)](#3-test-tooling-build-first)
4. [Phase 1: Fix Culling/Visibility Composition](#4-phase-1-fix-cullingvisibility-composition)
5. [Phase 2: Tighten Camera Frustum Rect](#5-phase-2-tighten-camera-frustum-rect)
6. [Round 1 Stop/Go Gate](#6-round-1-stopgo-gate)
7. [Phase 3: Static Terrain Chunk Batching](#7-phase-3-static-terrain-chunk-batching)
8. [Phase 4: Optional Tree Instancing Spike](#8-phase-4-optional-tree-instancing-spike)
9. [Phase 5: Final Polish & Validation](#9-phase-5-final-polish--validation)
10. [Definition of Done](#10-definition-of-done)
11. [Risk Register](#11-risk-register)

---

## 1. DIAGNOSIS SUMMARY

### What happens when the player explores / reveals the map

The 250x250 map (62,500 tiles) has `build_3d_terrain()` in `game/graphics/ursina_terrain_fog_collab.py` (line 488) creating individual Ursina Entity objects for every terrain prop at startup:

| Entity type | Count | Tracked in visibility system? |
|---|---|---|
| Tree entities | ~2,083 | YES |
| Grass scatter clumps | ~6,400 | YES |
| Water quads | ~1,875 | YES |
| Doodad entities (rocks/bushes) | ~1,300 | YES |
| Path stone entities | **~996** | **NO (BUG)** |
| Sparse rocks | ~28 | YES |
| **TOTAL** | **~12,700** | |

With fog active, only ~44 of these are enabled. After `/revealmap`, all ~10,506 tracked entities (plus ~996 untracked path stones) become enabled simultaneously.

### Three compounding bugs that make it worse than it should be

**Bug 1 — Culling/visibility composition failure:**
In `ursina_renderer.py:671-672`, `sync_visibility_gated_terrain()` runs first and enables entities based on fog alone. Then `cull_terrain_chunks()` runs second but only processes **delta** (chunks that *changed* visibility). If the camera didn't move between frames, the chunk set hasn't changed, so `became_hidden` and `became_visible` are both empty sets, and **no entities get re-hidden**. After `/revealmap`, all 10,506 entities stay enabled even though only ~500 are in the camera view.

**Bug 2 — Camera visible rect is too generous:**
In `ursina_renderer.py:629`, the formula `view_radius = max(int(cam_y * 1.8), 30)` produces a rect covering 225 out of 256 chunks (88% of the map) at normal camera height. The chunk culler barely hides anything.

**Bug 3 — Path stones bypass culling entirely:**
In `ursina_terrain_fog_collab.py:552-563`, path entities are created but never registered via `track_visibility_gated_terrain()`. They are always enabled, always rendered, and never culled.

### Why each proposed fix matters

```
Current state (full reveal):              ~6-15 FPS
Round 1 / Phase 1 (culling composition):  correctness fix; modest FPS gain until Phase 2
Round 1 / Phase 2 (tighter frustum):      ~30-45 FPS combined with Phase 1 (estimated)
Round 2 / Phase 3 (static batching):      ~45-60 FPS (estimated)
Later spike / Phase 4 (tree instancing):  only if still needed after Phase 3
```

---

## 2. AGENT ROSTER & RESPONSIBILITIES

| Agent | Role | Scope |
|---|---|---|
| **Agent 10** (Perf Lead) | Build test tooling first. Validate FPS and enabled terrain counts before/after each round. Owns benchmark harness. | `tools/perf_render_benchmark.py`, FPS probe runs |
| **Agent 03** (Tech Director) | Round 1: implement culling composition + frustum fix. Round 2, only if approved: static terrain batching. | `game/graphics/ursina_terrain_fog_collab.py`, `game/graphics/ursina_renderer.py` |
| **Agent 11** (QA Lead) | Write pytest assertions for entity counts, chunk counts, visibility state. Run regression tests. | `tests/test_terrain_perf.py` |

**Execution order:**
1. Agent 10 builds test tooling (Phase 0)
2. Agent 11 writes regression tests for Round 1 behavior
3. Agent 03 implements Phase 1 and Phase 2 only
4. Agent 10 validates Round 1 and reports stop/go metrics
5. PM/Jaimie approves Round 2 only if Round 1 does not reach target
6. Agent 03 implements Phase 3 static batching if approved
7. Tree instancing is deferred to a later spike unless Phase 3 still misses the target

---

## 3. TEST TOOLING (BUILD FIRST)

> **Owner: Agent 10 (PerformanceStability_Lead)**
> This section must be completed BEFORE any code changes begin. All other agents depend on these tools to validate their work.

### Tool 1: `tools/perf_render_benchmark.py`

**Purpose:** Automated Ursina rendering benchmark that measures FPS before and after `/revealmap`, with entity count reporting. This is the primary validation tool for this entire sprint.

**Requirements:**
- Launch the game in Ursina mode with `--no-llm`
- Measure steady-state FPS for 8 seconds (fog active, baseline)
- Execute `/revealmap` programmatically
- Measure post-reveal FPS for 8 seconds
- Report: avg/min/p10/p50/p90 FPS for both states, plus entity counts
- Exit automatically and print results to stdout
- Support `--csv <path>` for appending results to a CSV file

**Implementation guidance:**

The tool should be a Python script that lives at `tools/perf_render_benchmark.py`. It must run from the project root directory (not from `tools/`) so that Ursina finds assets correctly. The existing `tools/run_ursina_capture_once.py` shows the pattern for launching the game with auto-exit.

The tool should work by monkeypatching the engine's `tick_simulation` method to inject reveal logic at the right time, similar to how the FPS probe system works. Here is the exact pattern to follow:

```python
"""
Rendering performance benchmark: FPS before and after /revealmap.

Usage:
    cd Kingdom                          # MUST be in project root
    python tools/perf_render_benchmark.py
    python tools/perf_render_benchmark.py --csv perf_render.csv
    python tools/perf_render_benchmark.py --warmup 5 --measure 10
"""
import os, sys, time as pytime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.chdir(str(PROJECT_ROOT))                     # Ursina asset resolution needs this
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["SDL_VIDEODRIVER"] = "dummy"         # Pygame headless (Ursina still renders)

import pygame
pygame.init()

from ai.basic_ai import BasicAI
from game.graphics.ursina_app import UrsinaApp

# --- Configuration ---
WARMUP_SEC   = 5.0    # seconds before first measurement (terrain build settles)
MEASURE_SEC  = 8.0    # seconds to measure each state
REVEAL_AT    = WARMUP_SEC + MEASURE_SEC          # when to reveal
EXIT_AT      = REVEAL_AT + MEASURE_SEC + 2.0     # when to exit

# --- State ---
_state = {
    "phase": "warmup",
    "elapsed": 0.0,
    "before_samples": [],     # list of instantaneous FPS values
    "after_samples": [],
}
```

The tool hooks into `tick_simulation` to accumulate `time.dt` and collect FPS samples. At `WARMUP_SEC`, it starts collecting "before" samples. At `REVEAL_AT`, it executes the reveal logic (same as `/revealmap` in `game/engine.py:318-330`). Then it collects "after" samples. At `EXIT_AT`, it prints the report and quits.

**Entity count reporting:** After the reveal, the tool must also print:
```
[perf-render] Terrain props tracked: {len(renderer._visibility_gated_terrain)}
[perf-render] Tree entities: {len(renderer._tree_entities)}
[perf-render] Terrain chunks: {len(terrain_fog._terrain_chunks)}
[perf-render] Enabled props: {count of ent.enabled == True in _visibility_gated_terrain}
[perf-render] Visible chunks: {len(terrain_fog._visible_chunks)}
[perf-render] Enabled props outside visible chunks: {count enabled while chunk not visible}
[perf-render] Static batches: {count of batched static parent entities, if Phase 3 is enabled}
```

Access the renderer via `viewer.renderer` and the terrain fog collab via `viewer.renderer._terrain_fog`.

**The reveal logic to inject** (copy this exactly from `game/engine.py:318-330`):
```python
from game.world import Visibility
eng = viewer.engine
world = eng.world
world.fog_disabled = True
for ty in range(world.height):
    for tx in range(world.width):
        world.visibility[ty][tx] = Visibility.VISIBLE
world._currently_visible = []
sim = getattr(eng, "sim", eng)
sim._fog_revealers_snapshot = None
eng._fog_revision = getattr(eng, "_fog_revision", 0) + 100
for poi in getattr(sim, "pois", []):
    if not getattr(poi, "is_discovered", False):
        poi.is_discovered = True
```

**Output format (must match exactly for parsing):**
```
[perf-render] === BEFORE REVEAL ===
[perf-render] samples=N avg_fps=XX.X min_fps=XX.X p10=XX.X p50=XX.X p90=XX.X
[perf-render] === AFTER REVEAL ===
[perf-render] samples=N avg_fps=XX.X min_fps=XX.X p10=XX.X p50=XX.X p90=XX.X
[perf-render] === ENTITY COUNTS ===
[perf-render] tracked_props=NNNN tree_entities=NNNN static_batches=NNNN chunks=NNN enabled_props=NNNN enabled_outside_visible_chunks=NNN visible_chunks=NNN
[perf-render] === RESULT: PASS/FAIL (target: 45 FPS post-reveal, stretch: 55 FPS) ===
```

**CSV output** (when `--csv` is given): append one row with columns:
`timestamp,before_avg,before_min,before_p50,after_avg,after_min,after_p50,tracked_props,tree_entities,static_batches,enabled_props,enabled_outside_visible_chunks,visible_chunks`

### Tool 2: `tests/test_terrain_perf.py`

> **Owner: Agent 11 (QA Lead)**

**Purpose:** Regression tests that verify terrain entity counts, visibility tracking, and chunk composition are correct. Some tests can use fakes, but terrain-build tests may need a minimal Ursina/Panda3D context because `build_3d_terrain()` creates real `Entity`/`NodePath` objects.

**Requirements:**
- Test that ALL terrain entity types are registered in `_visibility_gated_terrain` (including path stones — currently a bug)
- Test that `cull_terrain_chunks()` correctly disables entities outside the visible rect even if fog just enabled them
- Test that the camera visible rect calculation produces a sensible range (not 88% of the map)
- Test entity counts match expected ranges for a 250x250 map

**Implementation guidance:**

These tests should prefer a small test world and verify data structures. They do not need a full game window, but they may still need to initialize Ursina/Panda3D if real `Entity` objects are used. Use fakes for pure logic tests and a small integration test only where needed.

```python
"""Tests for terrain entity management, visibility tracking, and chunk culling."""
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pytest
import pygame
pygame.init()

from game.world import World, TileType, Visibility


class TestTerrainEntityTracking:
    """Verify all terrain entity types are registered in the visibility system."""

    def test_path_entities_are_tracked(self):
        """Path stone entities must be registered in _visibility_gated_terrain.
        
        Bug context: build_3d_terrain() creates path entities (line 553) but
        does NOT call track_visibility_gated_terrain(). They bypass all culling.
        After the fix, this test should pass.
        """
        # This test verifies the fix for the path tracking bug.
        # Implementation: create a small world with path tiles, build terrain,
        # check that path entities appear in _visibility_gated_terrain_by_tile.
        pass  # Agent 11: implement with a 10x10 test world

    def test_culling_reapplies_after_fog_change(self):
        """After fog enables entities, chunk culling must re-hide out-of-view entities.
        
        Bug context: cull_terrain_chunks() only processes delta (became_hidden/became_visible).
        If camera didn't move, no delta exists, and fog-enabled entities stay visible.
        After the fix, culling must re-apply its mask when fog_revision changes.
        """
        pass  # Agent 11: implement

    def test_visible_rect_reasonable_at_default_camera(self):
        """Camera visible rect should cover <50% of chunks at default zoom.
        
        Bug context: view_radius = max(int(cam_y * 1.8), 30) covers 88% of chunks.
        After the fix, the rect should be tighter.
        """
        pass  # Agent 11: implement


class TestTerrainChunkBatching:
    """Verify that after Phase 3, static terrain is batched per chunk."""

    def test_static_entity_count_reduced(self):
        """After batching, individual grass/doodad/path entities should be
        merged into chunk meshes. The count of Ursina Entities in
        _visibility_gated_terrain should be significantly lower than the
        pre-batching count (~10,500 → ~500 or fewer).
        """
        pass  # Agent 11: implement after Phase 3 is done
```

**Note for Agent 11:** These tests will initially FAIL (they test for the fixed behavior). That's intentional — Agent 03 implements the fixes, then these tests should pass. Write the tests with clear docstrings explaining what bug they validate.

### Tool 3: Extend `run_ursina_capture_once.py` with `--reveal-map` flag

> **Owner: Agent 10**

Add a `--reveal-map` flag to `tools/run_ursina_capture_once.py` that triggers `/revealmap` after warmup, before the screenshot is taken. This lets anyone capture a screenshot showing the full map state.

**Implementation:** Add argument parsing for `--reveal-map`, set env var `KINGDOM_URSINA_REVEAL_ON_START=1`. In `game/graphics/ursina_app.py`, check this env var inside the `update()` closure after `self.renderer.update(snapshot)` has run at least once, then call `self.engine.process_command("/revealmap")`. Guard it with `_auto_reveal_done` so it only fires once.

**The code shape to add in `ursina_app.py`** (inside the `update()` closure, after `self.renderer.update(snapshot)`):
```python
# Auto-reveal for benchmarking (perf_render_benchmark.py / --reveal-map)
if (
    not getattr(self, "_auto_reveal_done", False)
    and os.environ.get("KINGDOM_URSINA_REVEAL_ON_START", "").strip() == "1"
):
    self._auto_reveal_done = True
    self.engine.process_command("/revealmap")
```

---

## 4. PHASE 1: FIX CULLING/VISIBILITY COMPOSITION

> **Owner: Agent 03 (TechnicalDirector)**
> **File:** `game/graphics/ursina_terrain_fog_collab.py`
> **Estimated FPS gain:** modest by itself; unlocks Phase 2 culling gains

### Problem

Three bugs compound to make culling ineffective after map reveal:

1. `sync_visibility_gated_terrain()` (line 292) enables entities based on fog alone
2. `cull_terrain_chunks()` (line 353) only processes chunk set delta — if camera didn't move, nothing happens
3. Path entities (line 552) are never registered in the visibility system

### Fix 1A: Compose fog visibility and chunk visibility through one helper

**Current broken logic** in `cull_terrain_chunks()` (lines 373-395):
```python
became_hidden = self._visible_chunks - new_visible
became_visible = new_visible - self._visible_chunks
# If camera didn't move: both sets are empty, loop body never runs
```

**Required change:** Do not let fog sync and chunk culling independently write `ent.enabled`. They represent two different constraints and must be composed:

```python
ent.enabled = ent._ks_fog_visible and ent._ks_chunk_visible
```

This is stronger than a one-frame `_fog_changed_since_last_cull` patch because it prevents the two systems from fighting again later.

**Specific implementation instructions for Agent 03:**

Step 1: Add a small helper to `UrsinaTerrainFogCollab`:
```python
def _apply_prop_visibility_state(
    self,
    ent: Entity,
    *,
    fog_visible: bool | None = None,
    chunk_visible: bool | None = None,
) -> None:
    if fog_visible is not None:
        ent._ks_fog_visible = bool(fog_visible)
    if chunk_visible is not None:
        ent._ks_chunk_visible = bool(chunk_visible)
    should_enable = bool(getattr(ent, "_ks_fog_visible", True)) and bool(
        getattr(ent, "_ks_chunk_visible", True)
    )
    if getattr(ent, "_ks_prop_enabled", None) is not should_enable:
        ent.enabled = should_enable
        ent._ks_prop_enabled = should_enable
```

Step 2: In `track_visibility_gated_terrain()`, initialize both state bits. Default `chunk_visible=True` is safe until the first chunk cull runs:
```python
ent._ks_fog_visible = False
ent._ks_chunk_visible = True
```

Step 3: Change `sync_terrain_prop_tile_visibility()` so it updates **fog state**, not final enabled state:
```python
is_visible = vis != Visibility.UNSEEN
self._apply_prop_visibility_state(ent, fog_visible=is_visible)
if is_visible:
    # Keep existing seen/visible tint behavior here.
```

Step 4: Change `cull_terrain_chunks()` so it updates **chunk state**, not final enabled state:
```python
for chunk_key in became_hidden:
    for ent, tx, ty in self._terrain_chunks[chunk_key]:
        self._apply_prop_visibility_state(ent, chunk_visible=False)

for chunk_key in became_visible:
    for ent, tx, ty in self._terrain_chunks[chunk_key]:
        self._apply_prop_visibility_state(ent, chunk_visible=True)
```

Step 5: Re-apply the full chunk mask when terrain is first built and when fog revision advances. This can be implemented by tracking `_last_cull_fog_revision` and, when it changes, iterating all chunks once to set `chunk_visible=(chunk_key in new_visible)`. The important invariant is that after `/revealmap`, fog can mark all props fog-visible, but out-of-frustum chunks still remain disabled.

This ensures that after `/revealmap`, the next frame re-hides all entities outside the camera frustum and future fog updates cannot accidentally re-enable them.

**Implementation note:** `UrsinaTerrainFogCollab` uses `__slots__`. If Agent 03 adds new instance fields such as `_last_cull_fog_revision` or static-batch counters, update `__slots__` in the same file.

### Fix 1B: Register path entities in visibility tracking

**Current code** (`build_3d_terrain`, lines 552-563):
```python
if tile == TileType.PATH:
    path_ent = Entity(
        parent=root,
        model=path_model,
        position=(wx, prop_y, wz),
        scale=(m, m, m),
        color=color.white,
        collision=False,
        double_sided=True,
        add_to_scene_entities=False,
    )
    _finalize_kenney_scatter_entity(path_ent, path_model)
    # BUG: no track_visibility_gated_terrain() call here
```

**Fix:** Add `self.track_visibility_gated_terrain(path_ent, tx, ty)` after the `_finalize_kenney_scatter_entity` call on line 563. This is a one-line addition:

```python
    _finalize_kenney_scatter_entity(path_ent, path_model)
    self.track_visibility_gated_terrain(path_ent, tx, ty)  # NEW: register for culling
```

### Validation (Agent 10 runs after this phase)

Run `python tools/perf_render_benchmark.py` and verify:
- `enabled_props_outside_visible_chunks` is zero or near-zero after reveal
- `enabled_props` may still be high until Phase 2 because the current visible rect covers most of the map
- `after_avg` FPS is not worse than baseline
- `tracked_props` increased by ~996 (the newly tracked path entities)

---

## 5. PHASE 2: TIGHTEN CAMERA FRUSTUM RECT

> **Owner: Agent 03 (TechnicalDirector)**
> **File:** `game/graphics/ursina_renderer.py`
> **Estimated FPS gain:** +5-10 FPS on top of Phase 1

### Problem

In `_get_visible_tile_rect()` (line 629):
```python
view_radius = max(int(cam_y * 1.8), 30)
```

At typical camera height (~60-80 units), this produces `view_radius = 108-144`, covering a 216-288 tile diameter. The map is only 250 tiles wide. This means the "frustum" covers 88% of the map, making chunk culling nearly useless.

### Fix: Use real lens frustum ground intersections, with empirical screenshot validation

Replace the single-radius heuristic with a real camera/lens query if Panda3D exposes the needed APIs in this Ursina version. The preferred approach is:

1. Get the active Panda3D camera lens from `base.camLens`.
2. Use lens extrusion for the four normalized screen corners.
3. Transform those rays into world space.
4. Intersect each ray with the terrain plane (`y=0` for the current surface renderer).
5. Convert the hit points to tile coordinates and return the bounding rect plus a margin.

This avoids relying on hand-rolled FOV trigonometry that may not match Ursina/Panda3D's actual lens behavior.

**Implementation guidance for Agent 03:**

- Prefer Panda3D lens APIs over an approximate formula.
- Keep a 5-8 tile safety margin at first.
- If any corner ray fails to hit the ground plane, fall back to the previous full-map rect for that frame.
- Log or benchmark the computed rect in the perf tool so Agent 10 can verify the result.
- Do not merge this change until screenshots prove there is no prop pop-in while panning and zooming.

**Fallback approach:** If lens extrusion is unreliable in this environment, keep a simple heuristic, but tune it from measurements rather than `cam_y * 1.8`. The target is roughly the actual screen area plus margin, not most of the map.

**Important:** The current proposed FOV-based approximation is not enough on its own. It can be used as a fallback, but it must be empirically validated because camera orbit, camera pitch, EditorCamera parenting, and Ursina lens settings can make the math drift.

### Validation (Agent 10 runs after this phase)

Run `python tools/perf_render_benchmark.py` and verify:
- `visible_chunks` after reveal is ~30-60 (not ~225)
- `enabled_props` is proportionally lower
- `after_avg` FPS improved further
- Screenshot set shows no prop pop-in at default camera, panned north/south/east/west, zoomed in, and zoomed out

---

## 6. ROUND 1 STOP/GO GATE

> **Owner: Agent 10 + PM/Jaimie**

After Phases 1-2, stop and measure before approving batching work.

### Round 1 validation command

```powershell
python tools/perf_render_benchmark.py
python tools/run_ursina_capture_once.py --seconds 12 --subdir perf_round1 --stem revealed --no-llm --fps-probe --reveal-map
```

### Round 1 success criteria

- `after_avg` is at least 30 FPS, with a target of 40+ FPS.
- `enabled_props` after reveal is far lower than `tracked_props`.
- `enabled_props_outside_visible_chunks` is zero or near-zero.
- `visible_chunks` at default camera is below 80.
- Screenshot evidence shows no terrain pop-in or missing path/water props.

### Stop/go decision

- If Round 1 reaches stable 45+ FPS and screenshots look good, skip Phase 3 for now and close the sprint.
- If Round 1 is below 45 FPS, proceed to Phase 3 static terrain batching.

---

## 7. PHASE 3: STATIC TERRAIN CHUNK BATCHING

> **Owner: Agent 03 (TechnicalDirector)**
> **File:** `game/graphics/ursina_terrain_fog_collab.py`
> **Estimated FPS gain:** +10-15 FPS on top of Phases 1-2

### Problem

Even with correct culling, each visible chunk contains ~40-80 individual Entity objects (grass clumps, doodads, path stones, water quads). Panda3D traverses each one individually. At 30-60 visible chunks, that's still 1,200-4,800 active entities.

### Fix: Merge static entities into material-safe chunk batches

After `build_3d_terrain()` creates all entities, group the STATIC ones (grass, doodads, path stones, water, rocks) into chunk batches and merge them where Panda3D can safely preserve their appearance. Do **not** assume one giant mixed-material chunk will work.

**What to batch:** Grass clumps, doodad entities (rocks, bushes, stumps, mushrooms, logs), path stones, water quads, sparse rocks. These are all static — they never move, scale, or change color after initial setup.

**What NOT to batch:** Trees. Trees have dynamic growth scaling (`sync_dynamic_trees` changes their scale) and can be chopped (replaced by log stacks). Keep trees as individual entities.

**Batching granularity:**

- Use 16x16 chunks for camera culling.
- Use 8x8 fog batches for static terrain if 16x16 fog transitions look too coarse.
- Within each fog batch, group by model/material/tint class before flattening. This reduces the risk that `flatten_strong()` loses per-entity color or material state.

**Specific implementation for Agent 03:**

After `build_3d_terrain()` finishes creating all entities (line 680: `self._r._terrain_entity = root`) but before `_build_terrain_chunks()` (line 681), add a new method call:

```python
self._r._terrain_entity = root
self._batch_static_terrain_for_chunks(root, tw, th)  # NEW
self._build_terrain_chunks()
```

The new method:

```python
def _batch_static_terrain_for_chunks(self, root, tw: int, th: int) -> None:
    """Merge static terrain props (grass, doodads, paths, water, rocks) into fog/cull batches.
    
    Trees are excluded because they have dynamic growth scaling.
    Camera culling can still use 16x16 chunks, but static fog batches should start
    at 8x8 to avoid ugly 512px-wide fog transitions.
    """
    from ursina import Entity
    
    # Group visibility-gated entities by fog batch and render signature, separating trees.
    fog_batch_size = 8
    batch_statics: dict[tuple, list] = {}
    new_vgt: list[tuple] = []  # replacement for _visibility_gated_terrain
    new_vgt_by_tile: dict[tuple[int, int], list] = {}

    for entry in self._r._visibility_gated_terrain:
        ent, tx, ty = entry
        # Trees have _ks_tree_base_scale — keep them individual
        if hasattr(ent, '_ks_tree_base_scale'):
            new_vgt.append(entry)
            new_vgt_by_tile.setdefault((tx, ty), []).append(ent)
            continue

        # Static prop — group by fog batch + model/material/tint signature.
        bx = tx // fog_batch_size
        by = ty // fog_batch_size
        model_key = str(getattr(ent, "model", ""))
        shader_key = str(getattr(ent, "shader", ""))
        color_key = getattr(ent, "color", None)
        bkey = (bx, by, model_key, shader_key, str(color_key))
        batch_statics.setdefault(bkey, []).append(entry)

    # For each batch, create a parent Entity, reparent statics, flatten if safe.
    for bkey, entries in batch_statics.items():
        if not entries:
            continue

        bx, by, _model_key, _shader_key, _color_key = bkey
        batch_parent = Entity(
            parent=root,
            name=f"static_batch_{bx}_{by}",
            add_to_scene_entities=False,
        )

        for ent, tx, ty in entries:
            try:
                ent.reparent_to(batch_parent)
            except Exception:
                pass

        # Prefer flatten_strong for node reduction, but keep a visual fallback.
        try:
            batch_parent.flatten_strong()
        except Exception:
            try:
                batch_parent.flatten_medium()
            except Exception:
                pass

        # Track the batch parent as a single entity in visibility system.
        # Use the fog batch center tile for fog lookup.
        center_tx = bx * fog_batch_size + fog_batch_size // 2
        center_ty = by * fog_batch_size + fog_batch_size // 2
        center_tx = min(center_tx, tw - 1)
        center_ty = min(center_ty, th - 1)
        new_vgt.append((batch_parent, center_tx, center_ty))
        new_vgt_by_tile.setdefault((center_tx, center_ty), []).append(batch_parent)

    self._r._visibility_gated_terrain = new_vgt
    self._r._visibility_gated_terrain_by_tile = new_vgt_by_tile
```

**Critical implementation note:** `flatten_strong()` merges children below a node. After flattening, you can no longer toggle individual grass/path/water entities — you toggle the whole static batch. This is why the first batching attempt should use 8x8 fog batches and visual screenshot validation. If 8x8 still looks too coarse at fog edges, reduce to 4x4 before attempting more complex per-tile material tricks.

**Visibility sync adjustment:** After batching, `sync_visibility_gated_terrain()` will look up the batch parent's center tile for fog state. Fog transitions are therefore batch-granular for static props. Trees remain per-tile because they stay individual.

**Material/tint validation:** Agent 03 must compare before/after reveal screenshots. If static prop colors or water/path materials break:

1. Group more narrowly by render signature.
2. Try `flatten_medium()` instead of `flatten_strong()`.
3. If flattening still breaks appearance, keep parent batching/culling without flattening and report the measured result.

**Metrics note:** If Agent 03 adds explicit batch counters such as `_static_terrain_batches`, update `__slots__` and expose those counts through `perf_render_benchmark.py`.

### Validation (Agent 10 runs after this phase)

Run `python tools/perf_render_benchmark.py` and verify:
- Static tracked props are reduced sharply; trees remain counted separately.
- Expected total tracked entries after batching is approximately: `tree_entities (~2,083) + static_batches`.
- `static_batches` should be roughly hundreds, not thousands, depending on 8x8 batch count and material grouping.
- `enabled_static_batches` in the camera view is low and proportional to visible chunks.
- `after_avg` FPS is ~45-55

---

## 8. PHASE 4: OPTIONAL TREE INSTANCING SPIKE

> **Owner: Agent 03 (TechnicalDirector)**
> **Files:** New file `game/graphics/instanced_nature_renderer.py`, modifications to `ursina_terrain_fog_collab.py`
> **Estimated FPS gain:** +5-10 FPS on top of Phase 3

### Problem

After Phase 3, trees are still ~2,083 individual entities. Each tree with the same model (e.g., `tree_pineRoundA.glb`) could share one instanced draw call.

### Fix: Hardware-instanced tree rendering, only if Phase 3 still misses target

Create `game/graphics/instanced_nature_renderer.py` that groups trees by model and renders them using Panda3D instancing with per-instance transforms. This is a later spike, not required Round 1 or Round 2 scope.

**Why this is different from `instanced_unit_renderer.py`:**
- Units use atlas billboards (2D sprites). Trees use 3D meshes.
- Units have animation (UV offset per frame). Trees are static meshes with per-instance position/scale.
- Trees use `lit_with_shadows_shader` or `unlit_shader`, not the custom `instanced_unit_shader`.

**Important complexity note for Agent 03:**

`NodePath.set_instance_count()` is not enough by itself if every instance needs a different world transform. A shader or other Panda3D-supported per-instance transform path is required. This makes 3D tree instancing materially harder than the existing unit instancer.

The key pattern from `instanced_unit_renderer.py` is still useful for buffer textures and instance counts:

```python
# 1. Create a buffer texture for instance data
instance_buffer = Texture("tree_instance_data")
instance_buffer.setup_buffer_texture(
    max_instances * 1,         # 1 texel per instance (x, y, z, scale)
    Texture.T_float,
    Texture.F_rgba32,
    GeomEnums.UH_dynamic,
)

# 2. Create one GeomNode per tree model
# Each GeomNode is a single quad/mesh that will be instanced
np = NodePath(geom_node)
np.reparent_to(render)
np.set_instance_count(active_count)
np.set_shader_input("instanceData", instance_buffer)

# 3. Each frame, update the buffer texture with current tree positions/scales
# (positions are static, but scale changes with growth)
```

**Recommended decision rule:**

Only attempt this spike if all of the following are true:

- Phase 3 has passed visual validation.
- Full reveal is still below 45 FPS, or below 55 FPS and Jaimie specifically wants to chase 60 FPS now.
- Agent 03 can prototype the shader path behind an environment flag without destabilizing the default renderer.

If writing a custom instancing shader is too complex, skip Phase 4 and rely on Phases 1-3. The remaining gap can also be addressed by:
- Reducing `URSINA_TERRAIN_SCATTER_STRIDE` from 2 to 3 (fewer grass entities)
- Reducing tree density cap from 1000 saplings to 500
- These are config knobs, not code changes

**If Phase 4 is attempted**, the instanced nature renderer should:
1. Group trees by model path (e.g., all `tree_pineRoundA.glb` instances together)
2. Create one instanced GeomNode per model (~13 models = ~13 draw calls)
3. Maintain a buffer texture with `(world_x, world_y, world_z, scale)` per tree
4. Update the buffer when `sync_dynamic_trees()` detects growth changes
5. Disable the individual tree Entity objects and use the instanced path instead
6. Respect fog visibility (only include trees in visible+seen tiles in the instance buffer)

### Validation

Run `python tools/perf_render_benchmark.py` and verify:
- `after_avg` FPS is at or above 55 FPS
- Trees are still visible and correctly sized
- Tree growth animation still works (saplings grow)
- The feature can be disabled by env flag if visual issues appear

---

## 9. PHASE 5: FINAL POLISH & VALIDATION

> **Owner: Agent 10 (PerformanceStability_Lead)**

### Full validation checklist

Run these commands and verify all pass:

```powershell
# 1. Unit tests (must all pass)
python -m pytest tests/ -x -q

# 2. Rendering benchmark (must show 45+ FPS post-reveal; 55+ target)
python tools/perf_render_benchmark.py

# 3. Terrain perf tests (new tests from Agent 11)
python -m pytest tests/test_terrain_perf.py -v

# 4. Visual regression: capture screenshots before and after reveal
python tools/run_ursina_capture_once.py --seconds 8 --subdir perf_final --stem normal --no-llm --fps-probe
python tools/run_ursina_capture_once.py --seconds 12 --subdir perf_final --stem revealed --no-llm --fps-probe --reveal-map

# 5. Verify fog-of-war still works (no visual regression)
# Manual: launch game, verify fog darkens explored tiles, trees appear/disappear correctly
python main.py --renderer ursina --no-llm
```

### Visual checks (Agent 10 must screenshot-verify)

1. Fog of war still darkens unexplored tiles (not broken by chunk batching)
2. Trees still grow from saplings (not broken by batching/instancing)
3. No visible "popping" of terrain props when panning camera
4. Path stones and water tiles render correctly
5. Building placement still removes trees in footprint

### Performance regression checks

Compare `perf_render_benchmark.py` output against these baselines:

| Metric | Before fix | After fix (target) |
|---|---|---|
| Before-reveal avg FPS | ~29-43 | >= 40 (no regression) |
| After-reveal avg FPS | ~6-15 | **>= 45 required, >= 55 target** |
| Tracked props (after batching) | ~10,506 | `tree_entities + static_batches` |
| Tree entities | ~2,083 | unchanged unless Phase 4 lands |
| Static batches | n/a | hundreds, not thousands |
| Enabled props/static batches (after reveal) | ~10,506 | proportional to visible chunks |
| Visible chunks (at default zoom) | ~225 | ~30-60 |

---

## 10. DEFINITION OF DONE

All of the following must be true:

- [ ] `python tools/perf_render_benchmark.py` shows `after_avg >= 45` FPS; `>=55` FPS remains the stretch target
- [ ] `python -m pytest tests/ -x -q` — all tests pass (including new `test_terrain_perf.py`)
- [ ] `enabled_props_outside_visible_chunks` is zero or near-zero after reveal
- [ ] `enabled_static_batches` after reveal is proportional to visible chunks
- [ ] `visible_chunks` at default zoom is < 80
- [ ] Fog of war visually works: unexplored area is dark, explored area is tinted, visible area is bright
- [ ] Tree growth works: saplings spawn and grow through 4 stages
- [ ] No visual artifacts: no terrain popping, no missing chunks, no z-fighting
- [ ] Building placement still removes trees from footprint
- [ ] Screenshots captured showing before/after FPS in `docs/screenshots/perf_final/`

---

## 11. RISK REGISTER

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `flatten_strong()` breaks fog tinting on individual tiles | MEDIUM | HIGH | Start with 8x8 fog batches, group by render signature, and reduce to 4x4 if edges look bad. |
| Tree instancing shader is too complex to write | MEDIUM | LOW | Defer Phase 4 as an optional spike; rely on Phases 1-3 first. Tune scatter density config knobs instead. |
| Camera frustum math is wrong, causing pop-in | LOW | MEDIUM | Keep 5-tile margin. Fallback to full_rect on any math error. |
| `flatten_strong()` doesn't work with mixed models/materials | MEDIUM | HIGH | Group by model/material/tint first. If flatten fails, fall back to `flatten_medium()` or reparenting without flatten and measure. |
| Phase 1/2 alone gets to 45+ FPS, making batching unnecessary now | MEDIUM | POSITIVE | Stop after Round 1, validate screenshots, and defer Phase 3 to a later hardening sprint. |
| Sapling spawn creates individual entities post-batch | LOW | LOW | New saplings become individual trees until next terrain rebuild. Cap is 1000, manageable. |

---

## APPENDIX A: FILE REFERENCE

| File | Lines | What it does |
|---|---|---|
| `game/graphics/ursina_terrain_fog_collab.py` | 488-681 | `build_3d_terrain()` — creates all terrain entities |
| `game/graphics/ursina_terrain_fog_collab.py` | 292-326 | `sync_visibility_gated_terrain()` — fog-based enable/disable |
| `game/graphics/ursina_terrain_fog_collab.py` | 353-395 | `cull_terrain_chunks()` — frustum-based chunk culling |
| `game/graphics/ursina_terrain_fog_collab.py` | 328-351 | `_build_terrain_chunks()` — chunk data structure |
| `game/graphics/ursina_terrain_fog_collab.py` | 250-278 | `track/untrack_visibility_gated_terrain()` |
| `game/graphics/ursina_terrain_fog_collab.py` | 925-1008 | `sync_dynamic_trees()` — tree growth + sapling spawn |
| `game/graphics/ursina_renderer.py` | 592-639 | `_get_visible_tile_rect()` — camera frustum to tile rect |
| `game/graphics/ursina_renderer.py` | 649-703 | `update()` — per-frame call order |
| `game/graphics/ursina_environment.py` | 1-307 | Environment model helpers, fog tint |
| `game/graphics/instanced_unit_renderer.py` | 1-160 | Reference: how unit instancing works |
| `game/engine.py` | 318-340 | `/revealmap` command handler |
| `config.py` | 32-33 | Map dimensions (250x250) |
| `config.py` | 527 | `URSINA_TERRAIN_SCATTER_STRIDE = 2` |

## APPENDIX B: AGENT PROMPT TEMPLATE

When dispatching agents for this sprint, the PM (Agent 01) should include this context in every agent prompt:

```
Sprint: Ursina Entities Overload Solution
Plan location: .cursor/plans/Ursina Entities Overload Solution.md
Target: 45+ FPS required with full map revealed (/revealmap), 55+ target, 60 FPS stretch

Current problem: ~13,000 individual Ursina Entity objects for terrain props
cause 6-15 FPS when the map is fully revealed. Three bugs compound:
1. Chunk culling doesn't re-apply after fog changes (composition bug)
2. Camera visible rect covers 88% of the map (too generous)
3. Path stone entities (~996) bypass culling entirely

Your assignment: [AGENT-SPECIFIC SECTION]

DO NOT COMMIT code changes. Report your changes and test results.
Run the benchmark after your changes: python tools/perf_render_benchmark.py
```
