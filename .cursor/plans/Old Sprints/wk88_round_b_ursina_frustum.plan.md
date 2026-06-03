# WK88 Sprint Plan — Round B-5: extract ursina_frustum.py (camera frustum-culling math)

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the camera frustum-culling math extracted from ursina_renderer.py into game/graphics/ursina_frustum.py; render visually unchanged.
**Predecessors:** WK87 (extracted ursina_building_ui). **Roadmap:** Round B — continuing the ursina_renderer.py (1780 LOC) split. Audit module: `ursina_frustum.py (~190) culling math`.

## 0. TL;DR
ursina_renderer.py has a ~230-LOC pure-camera-math cluster: `_get_visible_tile_rect` (654-831, the visible-tile-rect lens query) + `_entity_in_view` (832-882). WK88 moves them into `game/graphics/ursina_frustum.py` as functions taking the renderer (`r`), behind 1-line delegating wrappers on UrsinaRenderer (the per-frame `_frame_visible_rect` cache stays on the renderer, set via the wrapper at update() ~884; the sync methods keep calling `self._entity_in_view(...)`). Pure-move, screenshot-verified (culling is invisible if preserved — same units render in the same positions). The WK67 digest (headless) is unaffected. PM writes no code.

## 1. Scope
**IN:** create `game/graphics/ursina_frustum.py`; move `_get_visible_tile_rect` (654-831) and `_entity_in_view` (832-882) into it as `def get_visible_tile_rect(r) -> tuple[int,int,int,int]:` and `def entity_in_view(r, sim_x, sim_y) -> bool:` (bodies VERBATIM, self.->r.). Leave 1-line delegating wrappers on UrsinaRenderer (same names):
```python
def _get_visible_tile_rect(self):
    from game.graphics import ursina_frustum
    return ursina_frustum.get_visible_tile_rect(self)
def _entity_in_view(self, sim_x, sim_y):
    from game.graphics import ursina_frustum
    return ursina_frustum.entity_in_view(self, sim_x, sim_y)
```
The update() call `self._frame_visible_rect = self._get_visible_tile_rect()` (~884) and the sync-method `self._entity_in_view(...)` calls (~1025/1228/1336/1401/1460 etc.) are UNCHANGED (they call the wrappers).

**OUT:** the anim helpers (_compute_anim_frame/_facing_from_dto/_base_clip_from_dto — defer to WK89); the unit/building sync methods; any behavior/culling-threshold change. **Move VERBATIM.**

## 2. Pattern (WK69/87, verbatim)
`ursina_frustum.py` imports leaf deps the functions use (ursina `camera`/`scene`/`Vec3`/`window`, config, math). Imports UrsinaRenderer only under TYPE_CHECKING. NO cycle (wrapper imports ursina_frustum lazily; ursina_frustum never imports ursina_renderer at top). The functions read `r._camera_*`/`r._frame_visible_rect`/etc. exactly as the methods read `self.*`.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **849 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green.
- **E.** `game/graphics/ursina_frustum.py` exists with get_visible_tile_rect + entity_in_view; UrsinaRenderer keeps the 2 wrapper names; update()/sync call sites unchanged; ursina_renderer.py smaller (~1780 → ~1560); no import cycle.
- **F.** BEFORE/AFTER Ursina base_overview screenshots visually identical (same units/buildings visible — culling preserved).
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 09):** extract ursina_frustum.py + wrappers. Before/after screenshots. Verify suite + digest.
- **W2 (Agent 11):** seam test (module fns exist + wrappers delegate + no cycle) + full DoD + independently view before/after screenshots.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A camera-state reference (r._camera_*, scene, Vec3) breaks → wrong cull → entities vanish/appear | Med | move VERBATIM; before/after base_overview screenshot must show the SAME visible entities |
| Import cycle | Med | TYPE_CHECKING-only renderer import; lazy wrapper (proven WK87) |
| _frame_visible_rect cache wiring | Low | leave the cache field + its update() assignment on the renderer; only the rect-COMPUTE moves |

## 6. Success
The camera frustum-culling math lives in `game/graphics/ursina_frustum.py` behind delegating wrappers, the same entities are culled/visible — proven by 849+ green tests, clean determinism guard, unchanged digest, and identical before/after Ursina base_overview screenshots.

## 7. Kickoff
Roster: 09 ArtDirector (W1), 11 (verify + DoD + screenshot review W2), 10 (consult on culling/perf). Order: 09 W1 → PM gate (suite + digest + screenshots) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE MOVE, keep wrapper names + the _frame_visible_rect cache on the renderer, TYPE_CHECKING-only import; before/after base_overview must match; own log; DO NOT COMMIT.
Follow-ups: ursina_anim extraction (WK89); rest of ursina_renderer split (unit/building/misc-props sync); hud.py; ursina_terrain_fog_collab/ursina_app; Move 9; world.py fog; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter; config package; clusters 3/4; Round E; zombie purge.
