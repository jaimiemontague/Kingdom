# WK92 Sprint Plan — Round B-9: extract ursina_unit_sync.py (the 5 unit-sync methods)

**Author:** Agent 01 (PM) · **Date:** 2026-05-31 · **Goal:** all tests pass; the 5 per-unit-kind sync methods extracted from ursina_renderer.py into game/graphics/ursina_unit_sync.py; render visually unchanged. This is the last big chunk of the ursina_renderer split.
**Predecessors:** WK87-91 (building_ui/frustum/anim/misc_props/building_sync). **Roadmap:** Round B — ursina_renderer.py (1068 LOC) split. Audit module: `ursina_unit_sync.py (~420)`.

## 0. TL;DR
The 5 unit-render-sync methods — `_sync_snapshot_heroes` (891-993), `_sync_snapshot_enemies` (994-1064), `_sync_snapshot_peasants` (1065-1125), `_sync_snapshot_guards` (1126-1181), `_sync_snapshot_tax_collector` (1182-1243) — are ~350 LOC of per-kind DTO→billboard sync. Their heavy dependencies are already extracted (anim → ursina_units_anim WK89; frustum `_entity_in_view` WK88; the entity-creation collab), so they now call wrappers + the collab. WK92 moves the 5 into `game/graphics/ursina_unit_sync.py` as functions taking the renderer (`r`) + args, behind 1-line delegating wrappers on UrsinaRenderer (the update() pipeline keeps calling `self._sync_snapshot_heroes(...)` etc.; the `_entities`/collab/anim-state stay on the renderer). Pure VERBATIM move, screenshot-verified (base + combat — all unit kinds). After this, ursina_renderer.py is ~720 LOC (mostly orchestration + setup). The WK67 digest (headless) is unaffected. PM writes no code.

## 1. Scope
**IN:** create `game/graphics/ursina_unit_sync.py`; move VERBATIM (self.->r.):
- `_sync_snapshot_heroes(self, snapshot, active_ids, HeroClass)` -> `sync_snapshot_heroes(r, snapshot, active_ids, HeroClass)`
- `_sync_snapshot_enemies(self, snapshot, world, active_ids)` -> `sync_snapshot_enemies(r, snapshot, world, active_ids)`
- `_sync_snapshot_peasants(self, snapshot, active_ids)` -> `sync_snapshot_peasants(r, snapshot, active_ids)`
- `_sync_snapshot_guards(self, snapshot, active_ids)` -> `sync_snapshot_guards(r, snapshot, active_ids)`
- `_sync_snapshot_tax_collector(self, snapshot, active_ids)` -> `sync_snapshot_tax_collector(r, snapshot, active_ids)`
Leave 1-line delegating wrappers on UrsinaRenderer (same names + signatures) so the update() call sites are UNCHANGED. The renderer state (r._entities, r._entity_render collab, r._unit_anim_state/_unit_facing_state, unit-scale constants) stays on the renderer; calls to `_compute_anim_frame`/`_facing_from_dto` (WK89 wrappers) + `_entity_in_view` (WK88 wrapper) resolve via `r.<wrapper>` exactly as today.
**OUT:** any behavior/visual change; the remaining orchestration (update() / setup / _destroy_removed_entities — stay). **Move VERBATIM.**

## 2. Pattern (WK87-91, verbatim)
`ursina_unit_sync.py` imports the leaf deps the methods use (ursina, config, the UNIT_BILLBOARD_SCALE/ENEMY_SCALE/etc. constants — import from ursina_renderer if they stay there, or note they're module-level; the UnitDTO fields; color helpers). Imports UrsinaRenderer only under TYPE_CHECKING. NO cycle (wrappers import the module lazily; module never imports ursina_renderer at top — for the scale constants, either import them lazily/leaf or pass via r). Move VERBATIM.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **883 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green.
- **E.** the 5 fns in ursina_unit_sync.py; UrsinaRenderer keeps the 5 wrapper names+signatures; update() call sites unchanged; renderer state stays on the renderer; ursina_renderer.py smaller (~1068 → ~730); no import cycle.
- **F.** BEFORE/AFTER Ursina screenshots — base_overview + ursina_melee_combat — visually identical (heroes, enemies, peasants, guards, tax-collector all render the same: positions, billboards, anim frame, facing, scale, labels, HP bars).
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 09):** extract the 5 fns + wrappers. Before/after screenshots (base + combat). Verify suite + digest.
- **W2 (Agent 11):** seam test (5 fns exist + 5 wrappers delegate + no cycle) + full DoD + view before/after screenshots.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A unit-sync references renderer state/constant that doesn't move cleanly (scales, collab, anim wrappers, layer gate) | Med | take `r`; read r.* exactly as self.*; scales import leaf/lazy or via r; suite + before/after combat screenshot catch a missed ref |
| A unit kind renders wrong/missing | Med | move VERBATIM; before/after base+combat must show ALL kinds identically (heroes/enemies/peasants/guards/tax) |
| Import cycle (unit_sync needs scale constants from ursina_renderer) | Med | if the scale constants live in ursina_renderer, lazy-import them inside the fns OR move them to a shared/leaf module; verify fresh import both orders |

## 6. Success
The 5 unit-sync methods live in `game/graphics/ursina_unit_sync.py` behind delegating wrappers, all unit kinds render identically, and ursina_renderer.py is now a ~730-LOC orchestrator — proven by 883+ green tests, clean determinism guard, unchanged digest, and identical before/after Ursina base+combat screenshots.

## 7. Kickoff
Roster: 09 ArtDirector (W1), 11 (verify + DoD + screenshot review W2), 10 (consult). Order: 09 W1 → PM gate (suite + digest + base+combat screenshots) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE, keep wrapper names+signatures + renderer state on the renderer, TYPE_CHECKING-only import, handle the scale constants cycle-free; before/after base+combat MUST match (all unit kinds); own log; DO NOT COMMIT.
Follow-ups: ursina_renderer is then ~730 LOC (orchestrator) -- optional further trim; hud.py(2477) split; ursina_terrain_fog_collab/ursina_app; Move 9; world.py fog; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter; config package; clusters 3/4; Round E; zombie purge.
