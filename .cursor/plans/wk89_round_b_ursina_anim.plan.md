# WK89 Sprint Plan — Round B-6: consolidate unit-anim computation into ursina_units_anim.py

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the unit-animation-frame computation moved from ursina_renderer.py into the existing ursina_units_anim.py; render visually unchanged.
**Predecessors:** WK87 (building_ui), WK88 (frustum). **Roadmap:** Round B — ursina_renderer.py (1602 LOC) split. Audit module: `ursina_anim.py (~90)`. (We use the EXISTING `ursina_units_anim.py` as the anim home rather than a new file.)

## 0. TL;DR
ursina_renderer.py still holds the per-frame unit-animation-frame computation — `_compute_anim_frame` (485-~614), `_facing_from_dto` (453), and the module fn `_base_clip_from_dto` (272) — while the anim primitives (`anim_clock_seconds`, `_frame_index_for_clip`, the `*_base_clip` fns) already live in `game/graphics/ursina_units_anim.py`. WK89 moves the three computation functions into `ursina_units_anim.py` as functions taking the renderer (`r`) + dto, behind 1-line delegating wrappers on UrsinaRenderer (the per-entity `_unit_anim_state` FSM dict + `_frame_tick_id` STAY on the renderer; the call sites at ~616/1089/1183 keep calling `self._compute_anim_frame`/`self._facing_from_dto`). Pure-move, screenshot-verified (units animate identically — the combat scenario shows the attack clip). The WK67 anim-tick determinism tests + the digest guard it. PM writes no code.

## 1. Scope
**IN:** move into `game/graphics/ursina_units_anim.py`:
- `_base_clip_from_dto` (ursina_renderer.py:272, module fn) -> `base_clip_from_dto(dto)` (it dispatches to the existing `_hero/_enemy/...base_clip` in this module — natural home).
- `_facing_from_dto` (453, method) -> `facing_from_dto(r, dto)`.
- `_compute_anim_frame` (485-614, method) -> `compute_anim_frame(r, obj_id, entity, unit_type, class_key, base_clip_fn=None)` (reads `r._unit_anim_state`, `r._frame_tick_id`, the clips; calls the in-module `anim_clock_seconds`/`_frame_index_for_clip`/`base_clip_from_dto`).
Leave 1-line delegating wrappers on UrsinaRenderer (same names) so the call sites (~616 `self._compute_anim_frame(...)`, ~1089/1183 `self._facing_from_dto(...)`) are UNCHANGED:
```python
def _compute_anim_frame(self, obj_id, entity, unit_type, class_key, base_clip_fn=None):
    from game.graphics import ursina_units_anim
    return ursina_units_anim.compute_anim_frame(self, obj_id, entity, unit_type, class_key, base_clip_fn)
def _facing_from_dto(self, dto):
    from game.graphics import ursina_units_anim
    return ursina_units_anim.facing_from_dto(self, dto)
```
Keep `_base_clip_from_dto` importable from ursina_renderer (re-export) if any test imports it from there.

**OUT:** the per-entity anim-state dict (`_unit_anim_state`) + `_frame_tick_id` — stay on the renderer; the unit-sync methods; any anim-timing change. **Move VERBATIM.** (NOTE: the WK67 sim-tick-derived anim clock under DETERMINISTIC_SIM must be preserved exactly — `compute_anim_frame` still uses `r._frame_tick_id` via `anim_clock_seconds`.)

## 2. Pattern (WK87/88, verbatim)
`ursina_units_anim.py` is already a leaf anim module that ursina_renderer imports (one-directional). Add the 3 functions; they take `r` (no new import of ursina_renderer — TYPE_CHECKING only if a hint is needed). No new cycle. Move VERBATIM.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **857 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`; the WK67 anim-tick determinism tests still pass.
- **D.** `qa_smoke.py --quick` green.
- **E.** the 3 fns live in ursina_units_anim.py; UrsinaRenderer keeps `_compute_anim_frame`/`_facing_from_dto` wrappers (+ `_base_clip_from_dto` re-export if needed); call sites unchanged; `_unit_anim_state`/`_frame_tick_id` stay on the renderer; ursina_renderer.py smaller (~1602 → ~1450); no import cycle.
- **F.** BEFORE/AFTER Ursina screenshots — `ursina_melee_combat` (attack animation) AND base_overview — visually identical.
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 09):** move the 3 fns + wrappers. Before/after screenshots (combat + base). Verify suite + digest + anim-tick tests.
- **W2 (Agent 11):** seam test (fns exist in ursina_units_anim + wrappers delegate + no cycle) + full DoD + independently view before/after screenshots.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Anim-frame computation references a renderer field that doesn't move cleanly (clips, _unit_anim_state, _frame_tick_id) | Med | take `r`; read r._unit_anim_state/_frame_tick_id exactly as self.*; the anim-state stays on the renderer |
| Anim timing/clip drift | Low-Med | move VERBATIM; preserve the WK67 sim-tick anim clock; before/after COMBAT screenshot must match (shows the attack clip frame) |
| Import cycle | Low | ursina_units_anim is already a leaf imported by the renderer; the new fns take `r`; no reverse import |

## 6. Success
Unit-animation computation lives in `ursina_units_anim.py` alongside the anim primitives, units animate identically — proven by 857+ green tests (incl. the WK67 anim-tick determinism pins), clean determinism guard, unchanged digest, and identical before/after Ursina combat + base screenshots.

## 7. Kickoff
Roster: 09 ArtDirector (W1), 11 (verify + DoD + screenshot review W2), 10 (consult — did the WK68 instanced anim FSM). Order: 09 W1 → PM gate (suite + digest + combat screenshot) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE MOVE, keep wrapper names + anim-state on the renderer + the WK67 sim-tick anim clock; before/after combat+base screenshots must match; own log; DO NOT COMMIT.
Follow-ups: rest of ursina_renderer split (unit/building/misc-props sync); hud.py; ursina_terrain_fog_collab/ursina_app; Move 9; world.py fog; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter; config package; clusters 3/4; Round E; zombie purge.
