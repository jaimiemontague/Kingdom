# WK87 Sprint Plan — Round B-4: extract ursina_building_ui.py (tax overlay + building world-space UI)

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the tax-overlay + building world-space UI module functions extracted from ursina_renderer.py into game/graphics/ursina_building_ui.py; render visually unchanged.
**Predecessors:** WK68-86. **Roadmap:** Round B — the audit: "Tax-overlay public API + building world-space UI live in the renderer module (wrong home) → move to game/graphics/ursina_building_ui.py (alongside ursina_unit_overlays.py). Re-export the 3 public names for back-compat." First slice of the ursina_renderer.py (1959 LOC) split.

## 0. TL;DR
ursina_renderer.py carries a cohesive cluster of MODULE-LEVEL functions that are building-UI, not core renderer: the tax-overlay public API (`set_tax_gold_overlay_held`/`is_tax_gold_overlay_held`), `building_tax_overlay_snapshot`, the overlay-Y helpers (`_building_gold_overlay_y`/`_building_gold_overlay_world_y`), `_sync_building_worldspace_ui`, `_maybe_log_tax_overlay_debug`, + the debug state. WK87 moves them VERBATIM into `game/graphics/ursina_building_ui.py` and RE-EXPORTS the public names from ursina_renderer (ursina_app + engine lifecycle call `set_tax_gold_overlay_held`). The building-sync call sites (`_sync_building_worldspace_ui(...)` at ~1294/1329/1381, `_maybe_log_tax_overlay_debug(...)` at ~1386) import from the new module. Pure-move of module functions, screenshot-verified (tax overlay + building labels). PM writes no code.

## 1. Scope
**IN:** create `game/graphics/ursina_building_ui.py`; move VERBATIM the building-UI module functions:
- `set_tax_gold_overlay_held` (154), `is_tax_gold_overlay_held` (159) + the `_debug_tax_overlay`/`_tax_overlay_debug_last_print` module state they/the debug use.
- `building_tax_overlay_snapshot` (169), `_building_gold_overlay_y` (218), `_building_gold_overlay_world_y` (227), `_sync_building_worldspace_ui` (266-352), `_maybe_log_tax_overlay_debug` (353-385).
Re-export `set_tax_gold_overlay_held`/`is_tax_gold_overlay_held` (and `building_tax_overlay_snapshot` if anything imports it) from ursina_renderer (`from game.graphics.ursina_building_ui import set_tax_gold_overlay_held, is_tax_gold_overlay_held`) so ursina_app/engine-lifecycle callers are unchanged. Update ursina_renderer's building-sync call sites to call the functions via the new module (or the re-exported names).
**SHARED HELPERS:** `_prefab_local_top_y`, `_configure_ks_overlay`, `_sync_ks_facing_overlay`, `_ensure_ks_name_label` are shared with UNIT rendering — do NOT move them unless they're building-only (grep their callers). If `_sync_building_worldspace_ui` calls them, the new module imports them from ursina_renderer (leaf/lazy) OR they move to the existing `ursina_unit_overlays.py` if that's their natural home — Agent 09 picks the cycle-free cut (prefer: leave shared chrome helpers where they are, import what's needed).

**OUT:** the rest of the ursina_renderer split (unit-sync/building-sync/frustum/anim modules — later sprints); any behavior/visual change. **Move VERBATIM.**

## 2. Pattern
Pure-move of module-level functions + re-export. `ursina_building_ui.py` imports its leaf deps (ursina, config, the shared overlay helpers from ursina_renderer or ursina_unit_overlays). NO cycle (it must not import ursina_renderer at module top for anything ursina_renderer needs back before defining it — use lazy/leaf imports; verify fresh import). The functions take `ent`/`b`/`world`/`buildings` params (no renderer-instance state), so they move cleanly.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **834 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green.
- **E.** `game/graphics/ursina_building_ui.py` exists with the moved functions; `set_tax_gold_overlay_held`/`is_tax_gold_overlay_held` still importable from ursina_renderer (re-export); building-sync call sites resolve; ursina_renderer.py smaller; no import cycle.
- **F.** BEFORE/AFTER Ursina screenshots — `wk61_hold_g_tax_overlay` (the $N tax overlay) AND base_overview (building name labels) — visually identical.
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 09):** extract ursina_building_ui.py + re-export + update call sites. Before/after screenshots. Verify suite + digest.
- **W2 (Agent 11):** seam test (module exists + re-exports importable from ursina_renderer + no cycle) + full DoD + independently view the before/after screenshots.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A shared overlay helper moved/broken → unit OR building labels regress | Med | grep helper callers; leave shared chrome where it is; before/after screenshots of BOTH tax overlay + base labels |
| Import cycle (ursina_building_ui ↔ ursina_renderer) | Med | functions take params (no renderer state); lazy/leaf imports; verify fresh import |
| Tax overlay / label position shifts | Low | move VERBATIM; before/after tax-overlay screenshot must match |
| A re-export consumer (ursina_app set_tax_gold_overlay_held) breaks | Low | re-export the public names from ursina_renderer; grep callers |

## 6. Success
The tax-overlay + building world-space UI live in `game/graphics/ursina_building_ui.py`, the tax overlay + building labels render identically — proven by 834+ green tests, clean determinism guard, unchanged digest, and identical before/after Ursina screenshots (tax overlay + base labels).

## 7. Kickoff
Roster: 09 ArtDirector (extraction W1), 11 (verify + DoD + screenshot review W2), 03 (consult on cycle). Order: 09 W1 → PM gate (suite + digest + screenshots) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE MOVE, re-export the public names, do NOT move shared unit-overlay chrome, lazy/leaf imports to avoid cycle; before/after Ursina screenshots (tax overlay + base labels) must match; own log; DO NOT COMMIT.
Follow-ups: the rest of the ursina_renderer.py split (unit-sync/building-sync/frustum/anim/misc-props modules); hud.py split; ursina_terrain_fog_collab/ursina_app splits; Move 9; world.py fog; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter; config package; clusters 3/4; Round E; zombie purge.
