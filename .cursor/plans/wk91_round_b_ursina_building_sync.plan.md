# WK91 Sprint Plan — Round B-8: extract ursina_building_sync.py

**Author:** Agent 01 (PM) · **Date:** 2026-05-31 · **Goal:** all tests pass; `_sync_snapshot_buildings` extracted from ursina_renderer.py into game/graphics/ursina_building_sync.py; render visually unchanged.
**Predecessors:** WK87 (building_ui), WK88 (frustum), WK89 (anim), WK90 (misc-props). **Roadmap:** Round B — ursina_renderer.py (1306 LOC) split. Audit module: `ursina_building_sync.py (~260)`.

## 0. TL;DR
`_sync_snapshot_buildings` (ursina_renderer.py:648-890, ~242 LOC) is the per-frame building render-sync (billboards vs lit 3D meshes for castle/house/lair, cave/lair tint, POI gating, frustum cull, world-space UI). WK91 moves it into `game/graphics/ursina_building_sync.py` as `sync_snapshot_buildings(r, snapshot, world, active_ids)`, behind a 1-line delegating wrapper on UrsinaRenderer (the update() pipeline keeps calling `self._sync_snapshot_buildings`; the `_entities`/entity-creation collab/prefab loaders stay on the renderer; it calls the already-extracted `_sync_building_worldspace_ui` (WK87 ursina_building_ui) + `_entity_in_view` (WK88 wrapper)). Pure VERBATIM move, screenshot-verified (base_overview shows all buildings). The WK67 digest (headless) is unaffected. PM writes no code.

## 1. Scope
**IN:** create `game/graphics/ursina_building_sync.py`; move `_sync_snapshot_buildings` VERBATIM (self.->r.) -> `def sync_snapshot_buildings(r, snapshot, world, active_ids) -> None:`. Leave a 1-line delegating wrapper on UrsinaRenderer (same name) so the update() call site is UNCHANGED. The renderer state (r._entities, r._entity_render collab, prefab loaders, etc.) stays on the renderer; calls to `_sync_building_worldspace_ui` / `_entity_in_view` resolve via the renderer/already-extracted modules (use r.<wrapper> or the module function as the current code does).
**OUT:** the 5 unit-sync methods (heroes/enemies/peasants/guards/tax_collector — WK92); any behavior/visual change. **Move VERBATIM.**

## 2. Pattern (WK87-90, verbatim)
`ursina_building_sync.py` imports its leaf deps (ursina, config, building DTO fields, prefab/material helpers, ursina_building_ui for the world-space UI fn if called directly). Imports UrsinaRenderer only under TYPE_CHECKING. NO cycle (wrapper imports the module lazily; module never imports ursina_renderer at top). Move VERBATIM.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **877 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green.
- **E.** `sync_snapshot_buildings` in ursina_building_sync.py; UrsinaRenderer keeps the `_sync_snapshot_buildings` wrapper; update() call site unchanged; renderer state stays on the renderer; ursina_renderer.py smaller (~1306 → ~1070); no import cycle.
- **F.** BEFORE/AFTER Ursina base_overview screenshots visually identical (all buildings render the same — castle/houses/guilds/market/etc., correct meshes/billboards/tints).
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 09):** extract + wrapper. Before/after base_overview screenshots. Verify suite + digest.
- **W2 (Agent 11):** seam test (fn exists + wrapper delegates + no cycle) + full DoD + view before/after screenshots.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A reference (entity collab, prefab loader, _sync_building_worldspace_ui, _entity_in_view, a building-type branch) breaks → a building renders wrong/missing | Med | move VERBATIM; before/after base_overview must show ALL the same buildings (castle 3D mesh, houses, guilds, market, etc.) with the same meshes/tints |
| Import cycle | Low | TYPE_CHECKING-only import; lazy wrapper (proven WK87-90) |

## 6. Success
Building render-sync lives in `game/graphics/ursina_building_sync.py` behind a delegating wrapper, all buildings render identically — proven by 877+ green tests, clean determinism guard, unchanged digest, and identical before/after Ursina base_overview screenshots.

## 7. Kickoff
Roster: 09 ArtDirector (W1), 11 (verify + DoD + screenshot review W2), 10 (consult). Order: 09 W1 → PM gate (suite + digest + screenshots) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE, keep wrapper name + renderer state on the renderer, TYPE_CHECKING-only import; before/after base_overview MUST match (all buildings); own log; DO NOT COMMIT.
Follow-ups: ursina_renderer unit-sync slice (WK92, the last big chunk -> ~300 orchestrator); hud.py; ursina_terrain_fog_collab/ursina_app; Move 9; world.py fog; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter; config package; clusters 3/4; Round E; zombie purge.
