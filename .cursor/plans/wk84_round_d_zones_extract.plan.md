# WK84 Sprint Plan — Round D-4: extract patrol-zone logic to ai/behaviors/zones.py

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; `assign_patrol_zone` (and its dedicated helpers) extracted from exploration.py into a shared `ai/behaviors/zones.py`; behavior byte-identical (digest `b73961…` unchanged).
**Predecessors:** WK68-83. **Roadmap:** Round D — the audit: "zones.py (~50) patrol-zone assignment (consumed by stuck_recovery + bounty_pursuit too)."

## 0. TL;DR
`ai/behaviors/exploration.py` (322 LOC) holds `assign_patrol_zone` (33-69), which per the audit is also consumed by stuck_recovery + bounty_pursuit — i.e. it's shared zone logic mis-homed in exploration. WK84 moves it (+ any helper used ONLY by it) into a new `ai/behaviors/zones.py` and updates all importers to `from ai.behaviors.zones import assign_patrol_zone`. Pure-move of whole functions, headless, **perfectly digest-guarded** (patrol/zone assignment drives hero idle/explore decisions the 300-tick digest hashes). Defers the `handle_idle` predicate-step restructure (riskier). PM writes no code.

## 1. Scope
**IN:**
- Create `ai/behaviors/zones.py`; move `assign_patrol_zone` (exploration.py:33-69) into it VERBATIM. If `_find_black_fog_frontier_tiles` (70-138) and/or `_is_live_enemy_target` (24-32) are used ONLY by assign_patrol_zone, move them too; if SHARED with `explore`/`handle_idle` (likely for the frontier finder), LEAVE them in exploration.py and have zones.py import them LAZILY (or, if cleaner and cycle-free, move the frontier finder to zones.py and have exploration import it back) — Agent 06 picks the cohesive cut that avoids a cycle.
- Update ALL importers of `assign_patrol_zone` (grep `assign_patrol_zone` across ai/ — exploration.py itself, stuck_recovery.py, bounty_pursuit.py, basic_ai.py, anywhere) to import from `ai.behaviors.zones`. Optionally keep a re-export in exploration.py for back-compat, but prefer updating the importers (cleaner single home).

**OUT:** the `handle_idle` god-function predicate-step restructure (defer — riskier); changing zone-assignment logic; any behavior change. **Move whole functions VERBATIM.**

## 2. Pattern
Whole-function pure move + import-site updates. zones.py imports its leaf deps (config, navigation, etc.); if it needs a frontier helper that stays in exploration, lazy-import to avoid a cycle (exploration imports zones for assign_patrol_zone; zones lazy-imports exploration's helper). TYPE_CHECKING for any type-only hints. Verify fresh imports of zones + exploration both succeed.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **800 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` (PERFECT guard — zone/patrol assignment drives idle/explore decisions).
- **D.** `qa_smoke.py --quick` green.
- **E.** `ai/behaviors/zones.py` exists with `assign_patrol_zone`; all importers updated (grep: zero importers still get it from exploration, unless a back-compat re-export is intentionally kept); exploration.py smaller; no import cycle.
- **F.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 06):** create zones.py + move + update importers. Verify suite + digest + qa_smoke.
- **W2 (Agent 11):** seam test (zones.assign_patrol_zone exists + importers resolve + no cycle) + full DoD.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Shared helper (frontier finder) creates a cycle when moved | Med | Agent 06 picks the cohesive cut; lazy-import the shared helper; verify fresh imports |
| An importer missed → ImportError | Med | grep ALL `assign_patrol_zone` importers; full suite catches a miss |
| Behavior drift in zone assignment | Low | move VERBATIM; the digest is a PERFECT guard |

## 6. Success
Patrol-zone logic has a single home in `ai/behaviors/zones.py`, hero patrol/explore plays identically — proven by 800+ green tests, clean determinism guard, and the unchanged `b73961…` digest.

## 7. Kickoff
Roster: 06 (W1), 11 (verify W2), 05 (consult). Order: 06 W1 → PM gate (suite + digest + qa_smoke) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE MOVE whole functions, update all importers, lazy-import to avoid cycles; digest must stay byte-identical; NO screenshots; own log; DO NOT COMMIT.
Follow-ups: exploration handle_idle restructure; context_builder/direct_prompt_validator splits + ai/vocab.py + TaskRouter; the BIG presentation splits (hud/ursina_renderer body/ursina_app); Move 9; world.py; config package; clusters 3/4; Round E audit; zombie purge.
