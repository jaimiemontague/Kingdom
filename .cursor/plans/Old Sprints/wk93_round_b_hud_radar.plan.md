# WK93 Sprint Plan — Round B-10: extract hud_radar.py (radar minimap) — first hud.py slice

**Author:** Agent 01 (PM) · **Date:** 2026-05-31 · **Goal:** all tests pass; the radar-minimap rendering extracted from hud.py into game/ui/hud_radar.py; render visually unchanged.
**Predecessors:** WK87-92 (ursina_renderer split, now complete). **Roadmap:** Round B — the audit's #1 split: hud.py (2477 LOC). This is the first bounded slice (radar/minimap), using the proven pure-move-behind-wrappers pattern.

## 0. TL;DR
hud.py (2477 LOC) is the biggest god-file. WK93 extracts the radar-minimap cluster — `world_to_radar` (module fn, :59), `_ensure_radar_terrain_surface` (:1502-1558, cached terrain underlay), `_render_radar_minimap` (:1559-~1650, entity/POI dot overlay) — into `game/ui/hud_radar.py` as functions taking the HUD (`hud`), behind 1-line delegating wrappers on HUD (the render path keeps calling `self._render_radar_minimap(...)`; the `_radar_terrain_cache_key`/`_radar_terrain_surface` cache state stays on the HUD). `world_to_radar` moves as a module fn (re-export from hud if imported elsewhere). Pure VERBATIM move, screenshot-verified (pygame minimap always visible in base_overview/ui_panels). The WK67 digest (headless) is unaffected. PM writes no code.

## 1. Scope
**IN:** create `game/ui/hud_radar.py`; move VERBATIM:
- `world_to_radar(...)` (hud.py:59, module fn) -> `world_to_radar(...)` in hud_radar.py. Re-export from hud.py (`from game.ui.hud_radar import world_to_radar`) if any other module/test imports `hud.world_to_radar`.
- `_ensure_radar_terrain_surface(self, inner, world)` -> `ensure_radar_terrain_surface(hud, inner, world)` (reads/writes hud._radar_terrain_cache_key / hud._radar_terrain_surface).
- `_render_radar_minimap(self, ...)` -> `render_radar_minimap(hud, ...)` (calls ensure_radar_terrain_surface + world_to_radar; reads hud state, draws entity/POI dots).
Leave 1-line delegating wrappers on HUD (same names) so the HUD.render call site is UNCHANGED. The cache state (`_radar_terrain_cache_key`, `_radar_terrain_surface`) STAYS on the HUD (set in __init__) — accessed via hud.
**OUT:** the rest of hud.py (toasts/watch_card/selection_panels/input_router — later slices); any behavior/visual change. **Move VERBATIM.**

## 2. Pattern (WK87-92, verbatim)
`hud_radar.py` imports the leaf deps the fns use (pygame, config RADAR_MINIMAP_W/H + colors, world_to_grid/TileType, the POI/entity DTO fields). Imports HUD only under TYPE_CHECKING. NO cycle (wrapper imports the module lazily; module never imports hud at top). Move VERBATIM.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **897 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green.
- **E.** the 3 fns in hud_radar.py; HUD keeps the `_render_radar_minimap`/`_ensure_radar_terrain_surface` wrappers (+ world_to_radar re-export if needed); render call site unchanged; cache state stays on HUD; hud.py smaller (~2477 → ~2330); no import cycle.
- **F.** BEFORE/AFTER pygame screenshots — base_overview + ui_panels — the radar minimap (corner) renders identically (terrain underlay + entity/POI dots).
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 08):** extract + wrappers. Before/after pygame screenshots (base_overview + ui_panels). Verify suite + digest.
- **W2 (Agent 11):** seam test (3 fns exist + wrappers delegate + no cycle) + full DoD + view before/after minimap screenshots.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A radar fn references HUD state/helper that doesn't move cleanly (cache fields, world_to_radar, world_to_grid, colors) | Med | take `hud`; read hud.* exactly as self.*; cache state stays on HUD; before/after minimap screenshot catches a regression |
| Import cycle (hud_radar ↔ hud) | Low | TYPE_CHECKING-only HUD import; lazy wrapper (proven WK87-92) |
| world_to_radar imported elsewhere breaks | Low | grep importers; re-export from hud.py |

## 6. Success
The radar-minimap rendering lives in `game/ui/hud_radar.py` behind delegating wrappers, the minimap renders identically — proven by 897+ green tests, clean determinism guard, unchanged digest, and identical before/after pygame minimap screenshots. (First hud.py slice; more to follow.)

## 7. Kickoff
Roster: 08 UX/UI (W1), 11 (verify + DoD + screenshot review W2), 09 (consult). Order: 08 W1 → PM gate (suite + digest + minimap screenshots) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE, keep wrapper names + cache state on the HUD, TYPE_CHECKING-only import; before/after pygame minimap MUST match; own log; DO NOT COMMIT.
Follow-ups: more hud.py slices (toasts/ToastManager, watch_card, selection_panels, messages, input_router); ursina_terrain_fog_collab/ursina_app splits; Move 9; world.py fog; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter; config package; clusters 3/4; Round E; zombie purge.
