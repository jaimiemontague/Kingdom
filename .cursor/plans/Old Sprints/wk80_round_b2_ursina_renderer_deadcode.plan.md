# WK80 Sprint Plan — Round B-2g: ursina_renderer.py dead-code deletion (split prep)

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; confirmed-dead code deleted from ursina_renderer.py (and its dead helper in ursina_units_anim.py); behavior byte-identical, render visually unchanged.
**Predecessors:** WK68 (render DTO migration left `_unit_facing_direction` dead), WK69-79. **Roadmap:** Round B — the audit says "delete ~450 LOC of dead code FIRST" before splitting ursina_renderer.py (1979 LOC). This is that delete-first pass.

## 0. TL;DR
ursina_renderer.py (1979 LOC) carries dead code that should go before the file is eventually split. WK65 already removed `_unit_anim_surface`/`_apply_poi_mystery_state`. Still dead: **(1)** the `_unit_facing_direction` import (ursina_renderer.py:441) + its source function in `ursina_units_anim.py` — dead since WK68's DTO migration (renderers use `_facing_from_dto`/`_facing_for_dto`); **(2)** the **underground render subsystem** (`_sync_underground_meshes` + related, ~250 LOC) which the audit says sits behind an unconditional early return — IF confirmed dead, delete it. **Pure deletion of grep-confirmed-dead code** — low-risk, screenshot-verified (no visual change). The WK67 digest (headless sim) is unaffected. PM writes no code.

## 1. Scope
**IN:**
1. **Delete the dead `_unit_facing_direction` path:** remove the import at `ursina_renderer.py:441`; delete the `_unit_facing_direction` function in `game/graphics/ursina_units_anim.py` (grep-confirm ZERO live callers first — WK68 noted it's dead; the renderers use `_facing_from_dto`/`_facing_for_dto`). Update the comment references (ursina_renderer.py:639, instanced_unit_renderer.py:284-287) if they break.
2. **Underground render subsystem:** READ `_sync_underground_meshes` (ursina_renderer.py:~1396) and any `UrsinaUnderground*`/underground render helpers. Determine if it's behind an unconditional early return / a feature gate that's off (i.e. the body never runs in production). IF confirmed dead, delete the dead body (and the `_sync_underground_meshes` call sites at :1104/:1119 if the whole thing is dead, or leave the call + collapse the method to a documented no-op if the gate is the contract). **CRITICAL:** do NOT touch the SIM-SIDE dungeon entry (`game/systems/poi_interaction.py` `_handle_dungeon` etc.) — only the RENDER is gated/dead; the sim dungeon logic is live. If you cannot CONFIRM the underground render is dead, LEAVE it and report — only delete what's provably unreachable.
3. Any duplicated/dead scale constants that are confirmed unused (grep first).

**OUT:** the actual ursina_renderer.py module split (later sprint); any behavior change; touching the sim-side underground/poi_interaction; the instanced renderer.

## 2. Verification approach
Every deletion is grep-guarded: before deleting a symbol, grep the whole repo for live callers/readers; delete only if zero (excluding comments/the def itself). After deletion: full suite + determinism + digest + qa_smoke + a BEFORE/AFTER Ursina screenshot (base_overview) that must be visually identical (dead code → no visual change).

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **758 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green.
- **E.** The `_unit_facing_direction` dead import + function are gone (grep: zero live callers remained); ursina_renderer.py smaller (target ≥150 LOC removed; more if underground was dead); the sim-side dungeon (`poi_interaction`) is UNTOUCHED.
- **F.** BEFORE/AFTER Ursina `base_overview` screenshots are visually identical (no regression).
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 09):** grep-guarded deletion (facing path + underground-if-dead + dead constants). Capture before/after Ursina screenshots. Verify suite + digest.
- **W2 (Agent 11):** confirm the deletions are clean (no dangling refs) + full DoD + independently view the before/after screenshots.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A "dead" symbol actually has a live caller → break | Med | grep the WHOLE repo before each deletion; delete only zero-caller symbols; full suite + qa_smoke catch it |
| Underground render is NOT actually dead → deleting it changes the render | Med | CONFIRM the early-return/gate makes it unreachable in prod; if uncertain, LEAVE it and report; before/after screenshot is the backstop |
| Accidentally touch the sim-side dungeon | Low | explicit OUT: do not touch poi_interaction; lane = ursina_renderer.py + ursina_units_anim.py only |
| A visual regression slips | Low | before/after Ursina screenshot must be identical (dead code → no change) |

## 6. Success
The confirmed-dead facing path (and the underground render if dead) are removed, ursina_renderer.py is smaller and cleaner for its eventual split, and the render is visually identical — proven by 758+ green tests, clean determinism guard, unchanged digest, and identical before/after Ursina screenshots.

## 7. Kickoff
Roster: 09 ArtDirector (deletion W1), 11 (verify + DoD + screenshot review W2), 03 (consult). Order: 09 W1 → PM gate (suite + digest + screenshots) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; DELETE ONLY grep-confirmed-dead; do NOT touch the sim-side dungeon; before/after Ursina screenshots must match; own log; DO NOT COMMIT.
Follow-ups: the ursina_renderer.py module split (8 modules); hud.py split (2477); ursina_terrain_fog_collab/ursina_app splits; Move 9; world.py; config package; clusters 3/4; Round D AI router/splits; Round E audit; zombie purge.
