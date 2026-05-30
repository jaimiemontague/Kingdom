# WK83 Sprint Plan — Round D-3: move handle_moving into ai/behaviors/movement.py

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the global MOVING-state dispatcher `handle_moving` relocated from bounty_pursuit.py into movement.py; behavior byte-identical (digest `b73961…` unchanged).
**Predecessors:** WK74 (created movement.py), WK82. **Roadmap:** Round D — the audit: "bounty_pursuit.handle_moving is the de-facto global MOVING-state dispatcher, not bounty code — create ai/behaviors/movement.py owning handle_moving."

## 0. TL;DR
`ai/behaviors/bounty_pursuit.py` (368 LOC) ends with `handle_moving(ai, hero, view)` (lines 227-368, ~140 LOC) — the per-frame MOVING-state dispatcher (it routes bounty/journey/arrival, not just bounty logic). WK83 moves it into `ai/behaviors/movement.py` (created in WK74) as `handle_moving(ai, hero, view)`, and leaves a 1-line shim `bounty_pursuit.handle_moving` delegating to it (so `basic_ai`'s `self.bounty_behavior.handle_moving(self, hero, view)` caller is unchanged). Pure-move, headless, **perfectly digest-guarded** (the MOVING dispatch IS the hero movement decisions the 300-tick digest hashes). PM writes no code.

## 1. Scope
**IN:**
- Move `handle_moving` (bounty_pursuit.py:227-368) into `ai/behaviors/movement.py` as `def handle_moving(ai, hero, view) -> None:` (body verbatim). It references bounty_pursuit helpers (`start_bounty_pursuit`/`score_bounty`/`maybe_take_bounty`/`_resolve_bounty_from_target`/`_seed_direct_prompt_explore_bearing`) + arrival_handlers + journey + route_to_building — import what it needs (LAZILY where needed to avoid a cycle, see Rules).
- Leave a 1-line shim in bounty_pursuit.py: `def handle_moving(ai, hero, view): from ai.behaviors import movement; return movement.handle_moving(ai, hero, view)` — so `basic_ai.py:341` (`self.bounty_behavior.handle_moving(self, hero, view)`) is UNCHANGED.

**OUT:** further splitting handle_moving's internal dispatch (later); changing the MOVING dispatch logic; touching the bounty scoring/pursuit helpers (they stay in bounty_pursuit); any behavior change. **Move the body VERBATIM.**

## 2. Cycle note (critical)
Currently neither imports the other. After the move, `movement.handle_moving` needs bounty_pursuit's helpers AND bounty_pursuit's shim needs movement. To avoid a module-top cycle:
- `movement.py` imports the bounty_pursuit helpers it calls **LAZILY inside `handle_moving`** (`from ai.behaviors import bounty_pursuit` at the top of the function), OR keeps the existing top-level leaf imports (arrival_handlers/journey/route_to_building) and only the bounty_pursuit ones lazy.
- `bounty_pursuit.handle_moving` shim imports movement LAZILY (inside the shim body).
- Result: no module-load cycle. Verify with a fresh `import ai.behaviors.movement` + `import ai.behaviors.bounty_pursuit`.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **793 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` (PERFECT guard — MOVING dispatch drives the digest).
- **D.** `qa_smoke.py --quick` green.
- **E.** `movement.handle_moving` exists; `bounty_pursuit.handle_moving` is a delegating shim; `basic_ai` caller unchanged; bounty_pursuit.py smaller (~368 → ~235); no import cycle.
- **F.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 06):** move handle_moving + shim. Verify suite + digest + qa_smoke.
- **W2 (Agent 11):** seam test (movement.handle_moving exists + bounty_pursuit shim delegates + no cycle) + full DoD.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Import cycle (movement ↔ bounty_pursuit) | **Med-High** | lazy imports both ways (§2); verify fresh imports |
| A reference inside handle_moving breaks (a bounty helper / arrival / journey) | Med | move VERBATIM; the digest is a PERFECT guard; copy/lazy-import all referenced names |
| Behavior drift in the MOVING dispatch | Low | the digest hashes movement decisions — any drift caught |

## 6. Success
`handle_moving` lives in movement.py as the global MOVING dispatcher, hero movement plays identically — proven by 793+ green tests, clean determinism guard, and the unchanged `b73961…` digest.

## 7. Kickoff
Roster: 06 AIBehaviorDirector (W1), 11 (verify W2), 05 (consult). Order: 06 W1 → PM gate (suite + digest + qa_smoke) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE MOVE, keep the bounty_pursuit.handle_moving shim so the caller is unchanged, LAZY imports to avoid the cycle; digest must stay byte-identical; NO screenshots; own log; DO NOT COMMIT.
Follow-ups: context_builder/direct_prompt_validator/exploration splits + ai/vocab.py + TaskRouter (rest of Round D); the BIG presentation splits (hud/ursina_renderer body/ursina_app); Move 9; world.py; config package; clusters 3/4; Round E audit; zombie purge.
