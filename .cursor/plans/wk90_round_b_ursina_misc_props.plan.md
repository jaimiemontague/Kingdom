# WK90 Sprint Plan — Round B-7: extract ursina_misc_props_sync.py (bounties + rubble + projectiles)

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the bounty/rubble/projectile sync methods extracted from ursina_renderer.py into game/graphics/ursina_misc_props_sync.py; render visually unchanged.
**Predecessors:** WK87 (building_ui), WK88 (frustum), WK89 (anim). **Roadmap:** Round B — ursina_renderer.py (1461 LOC) split. Audit module: `ursina_misc_props_sync.py (~170) bounties + rubble`.

## 0. TL;DR
ursina_renderer.py has 3 isolated per-frame "misc prop" sync methods: `_sync_snapshot_projectiles` (1244-~1293), `_sync_snapshot_bounties` (1294-~1371), `_sync_snapshot_rubble` (1372-~1430) — ~184 LOC. WK90 moves them into `game/graphics/ursina_misc_props_sync.py` as functions taking the renderer (`r`) + args, behind 1-line delegating wrappers on UrsinaRenderer (the update() pipeline keeps calling `self._sync_snapshot_projectiles/bounties/rubble`; the `_entities`/`_bounty_*`/`_rubble_*` state + entity-creation collab stay on the renderer). Pure VERBATIM move, low-risk. Screenshot-verified (base + combat confirm no regression). The WK67 digest (headless) is unaffected. PM writes no code.

## 1. Scope
**IN:** create `game/graphics/ursina_misc_props_sync.py`; move VERBATIM (self.->r.):
- `_sync_snapshot_projectiles` -> `sync_snapshot_projectiles(r, snapshot, active_ids)`
- `_sync_snapshot_bounties` -> `sync_snapshot_bounties(r, snapshot, active_ids)`
- `_sync_snapshot_rubble` -> `sync_snapshot_rubble(r, snapshot)`
Leave 1-line delegating wrappers on UrsinaRenderer (same names) so the update() call sites are UNCHANGED. The renderer state these read/write (`r._entities`, `r._bounty_*`, `r._rubble_*`, active_ids set, the entity-creation collab, prefab loaders) stays on the renderer — accessed via `r.`.

**OUT:** the unit-sync methods (_sync_snapshot_heroes/enemies/peasants/guards/tax_collector — the biggest cluster, a later slice); the building-sync; any behavior/visual change. **Move VERBATIM.**

## 2. Pattern (WK87-89, verbatim)
`ursina_misc_props_sync.py` imports the leaf deps the methods use (ursina destroy/Entity/Text/color, config, the bounty/rubble DTO fields, prefab loaders). Imports UrsinaRenderer only under TYPE_CHECKING. NO cycle (wrapper imports the module lazily; module never imports ursina_renderer at top). Move VERBATIM.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **867 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green.
- **E.** the 3 fns live in ursina_misc_props_sync.py; UrsinaRenderer keeps the 3 wrapper names; update() call sites unchanged; renderer state stays on the renderer; ursina_renderer.py smaller (~1461 → ~1290); no import cycle.
- **F.** BEFORE/AFTER Ursina screenshots — base_overview + ursina_melee_combat (projectile/strike) — visually identical (no crash, scene unchanged). (Bounties/rubble may not be visible in these scenarios; the pure-VERBATIM move + suite + scene-unchanged screenshot is the guard.)
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 09):** extract the module + wrappers. Before/after screenshots. Verify suite + digest.
- **W2 (Agent 11):** seam test (3 fns exist + wrappers delegate + no cycle) + full DoD + view before/after screenshots.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A method references renderer state that doesn't move cleanly (_entities, _bounty_*, _rubble_*, collab) | Med | take `r`; read r.* exactly as self.*; state stays on the renderer; suite catches a missed ref |
| Import cycle | Low | TYPE_CHECKING-only import; lazy wrapper (proven WK87-89) |
| Weak prop-visibility screenshot coverage (bounties/rubble not shown in base/combat) | Med | pure-VERBATIM move is inherently low-risk; suite + scene-unchanged screenshot + the verbatim diff are the guard; note this in the report |

## 6. Success
Bounty/rubble/projectile sync lives in `game/graphics/ursina_misc_props_sync.py` behind delegating wrappers, the render is unchanged — proven by 867+ green tests, clean determinism guard, unchanged digest, and identical before/after Ursina base+combat screenshots.

## 7. Kickoff
Roster: 09 ArtDirector (W1), 11 (verify + DoD + screenshot review W2), 10 (consult). Order: 09 W1 → PM gate (suite + digest + screenshots) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM MOVE, keep wrapper names + renderer state on the renderer, TYPE_CHECKING-only import; before/after base+combat screenshots must match; own log; DO NOT COMMIT.
Follow-ups: ursina_renderer unit-sync + building-sync slices; hud.py; ursina_terrain_fog_collab/ursina_app; Move 9; world.py fog; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter; config package; clusters 3/4; Round E; zombie purge.
