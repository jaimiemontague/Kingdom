# WK74 Sprint Plan — Round C-2b: AI-behavior dedup helpers

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; two of the most-duplicated AI behavior blocks ("route hero to a building", "engage enemy") consolidated into single helpers; behavior byte-identical (digest `b73961…` unchanged).
**Predecessors:** WK68-73. **Roadmap:** Round C dedup map (ai-behaviors area).

## 0. TL;DR
The audit's de-dup map flags two AI blocks copy-pasted many times: **"route hero to a building"** (best_adjacent_tile → set target_position to adj-center else building-center) appears ~11× across exploration/shopping/hunger/journey/bounty/basic_ai; **"engage enemy"** (set target + commit window + FIGHTING/set_target_position) appears ~8× in defense.py. WK74 extracts each into one helper and calls it everywhere. **The digest is a PERFECT guard here** — it hashes the AI's 300-tick decisions, so any drift in these helpers shows up immediately as a digest change. Headless, no screenshots. Digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` MUST stay byte-identical.

## 1. Scope
**IN:**
1. **`route_to_building(hero, world, buildings, building)`** in a new `ai/behaviors/movement.py`: reproduce the EXACT block — `adj = best_adjacent_tile(world, buildings, building, hero.x, hero.y); if adj: hero.target_position = (<adj world-center>) else: hero.target_position = (building.center_x, building.center_y)`. Read the canonical instance (exploration.py:224-233 marketplace) for the exact adj→world-center math. Replace every IDENTICAL occurrence (exploration.py marketplace/blacksmith/inn ~224-310, and the same pattern in shopping.py / hunger.py / journey.py / bounty_pursuit.py / basic_ai.py — grep for `best_adjacent_tile`). If a site differs (extra logic), leave it or parameterize — do NOT change behavior.
2. **`engage(hero, enemy, now_ms)`** + **`_commit_until_ms(now_ms)`** in defense.py (or `ai/behaviors/combat_targeting.py`): reproduce `hero.target = enemy; hero._target_commit_until_ms = int(now_ms + int(float(TARGET_COMMIT_WINDOW_S)*1000.0)); hero.set_target_position(enemy.x, enemy.y)`. Some sites ALSO set `hero.state = HeroState.FIGHTING` — handle that variant (e.g. `engage(hero, enemy, now_ms, *, set_fighting=False)` or set FIGHTING at the call site). Replace the ~8 defense.py occurrences EXACTLY.

**OUT:** the broader `bounty_goal_xy`/compass helpers, the `bounty_pursuit.handle_moving` rename/split, the basic_ai handler extraction, ai/vocab.py, the TaskRouter (Round D). Any behavior change.

## 2. Pattern
Extract the duplicated statements verbatim into a helper; call sites become one call. Parameterize ONLY where sites genuinely differ (e.g. set_fighting). The digest is the guard — verify after each helper. If a site can't be unified without changing behavior, leave it inline and report.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **703 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` (the perfect guard — verify after EACH helper).
- **D.** `qa_smoke.py --quick` green.
- **E.** `route_to_building` exists in `ai/behaviors/movement.py` and is called at all unified sites (no inline copy remains at those sites); `engage`/`_commit_until_ms` exist and replace the defense.py copies. Any site left inline is reported with a reason.
- **F.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 06):** `route_to_building` + wire all identical sites. Verify digest + suite.
- **W2 (Agent 06):** `engage` + `_commit_until_ms` + wire defense.py sites. Verify digest + suite.
- **W3 (Agent 11):** a small behavior test (route_to_building sets the same target_position as the old inline math for a sample building with/without a valid adj tile; engage sets target+commit+position) + full DoD gate. (qa_smoke's observe_sync AI scenarios + the digest are the real guards.)

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A "route" site differs subtly (extra guard / different fallback) | Med | the digest catches ANY drift; diff each site vs the canonical; leave-and-report divergent sites |
| An "engage" site sets FIGHTING and another doesn't | Med | parameterize set_fighting or set it at the call site; digest guards |
| Digest drift | Low (perfect guard) | verify after EACH helper; if it drifts, a site wasn't byte-identical — fix or revert that site |

## 6. Success
"Route to building" and "engage enemy" each become one helper, AI plays identically — proven by 703+ green tests, clean determinism guard, and the unchanged `b73961…` digest (the definitive proof for AI behavior).

## 7. Kickoff
Roster: 06 (both dedups, sequential), 11 (behavior test + DoD), 05 (consult). Order: 06 W1 → PM gate (digest+suite) → 06 W2 → PM gate → 11 W3 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; behavior-preserving, digest unchanged (verify after each helper); NO screenshots; own log; DO NOT COMMIT.
Follow-ups: bounty_pursuit/movement split + basic_ai handlers + ai/vocab.py + TaskRouter (Round D); engine/input_handler/hud/ursina_renderer presentation splits; Move 9; world.py; config package; zombie purge.
