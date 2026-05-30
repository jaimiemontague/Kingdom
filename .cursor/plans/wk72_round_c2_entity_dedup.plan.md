# WK72 Sprint Plan — Round C-2: entities-units dedup helpers

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; two high-frequency duplicated blocks consolidated into single helpers; behavior byte-identical (digest `b73961…` unchanged).
**Predecessors:** WK68-71. **Roadmap:** Round C dedup / single-source-of-truth (de-duplication map).

## 0. TL;DR
The audit's biggest slop class is duplication. WK72 kills two of the worst entity/systems duplications with **behavior-preserving extractions** (extract the shared block into one helper, call it from every site). Headless, digest-guarded (these blocks drive enemy movement + combat scaling, which the 300-tick digest exercises), no screenshots. The WK67 AI-decision digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` MUST stay byte-identical. PM writes no code.

## 1. Scope
**IN — two dedups:**
1. **`DifficultySystem.apply_to_enemy(enemy)`** — the HP/damage scaling on a freshly-spawned enemy is triplicated:
   - `game/systems/spawner.py:~189-197` (`hp_mult`/`dmg_mult` via `self.difficulty.get_multiplier("enemy_hp"/"enemy_damage")`, then `enemy.max_hp = max(1, round(max_hp*hp_mult)); enemy.hp = enemy.max_hp` + the damage scaling).
   - `game/systems/lairs.py:~144-153` (same scaling on lair-spawned enemies).
   - `game/systems/wave_events.py:~254-259` (same on wave-event enemies).
   → Add `DifficultySystem.apply_to_enemy(self, enemy) -> None` performing the EXACT current scaling once, and replace all 3 sites with `difficulty.apply_to_enemy(enemy)` (guarded by the same `if difficulty is not None`). The 3 control-flow shapes must end up behaviorally identical — read all 3 and reproduce each one's exact effect (including any damage-scaling lines below the HP lines).
2. **`navigation.advance_along_path_to(entity, world, buildings, goal_x, goal_y, dt, ...)`** — the path-replan-and-follow block is copy-pasted in:
   - `game/entities/enemy.py` (TWO sites — the Enemy.update path-follow ~289-320 and the SkeletonArcher.update path-follow ~562-589).
   - `game/entities/guard.py` (~159-180).
   → Extract ONE helper in `game/systems/navigation.py` that reproduces the block EXACTLY, and call it from those 3 sites. **SCOPE: enemy + guard ONLY.** Do NOT touch hero.py (its crc32 stagger + fog guards differ) or tax_collector.py (its replan has a deliberate enrichment — a gated behavior change, out of scope). Before extracting, DIFF the 3 blocks; if they are not identical, parameterize the helper to cover the exact differences (do not change any site's behavior). If a site differs in a way that can't be cleanly parameterized, leave that site alone and report it.

**OUT:** the ENEMY_STATS table / 7-subclass collapse (riskier, separate sprint); tax_collector/hero path-replan; `defense.engage`/`route_to_building` ai-behavior dedups (Round D); any behavior change.

## 2. Pattern
Extract the duplicated statements verbatim into a function with the entity (and whatever locals it reads: world, buildings, dt, goal coords) as parameters; the call sites become a single call. No logic/threshold/order change. The digest is the guard — verify it after each dedup.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **654 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green.
- **E.** `DifficultySystem.apply_to_enemy` exists and is the sole HP/damage spawn-scaling implementation (3 call sites use it; no inline copy remains). `navigation.advance_along_path_to` exists and is called by enemy (×2) + guard (no inline copy remains at those sites). hero/tax_collector untouched.
- **F.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 05):** `DifficultySystem.apply_to_enemy` + wire the 3 sites. Verify digest + suite.
- **W2 (Agent 05):** `navigation.advance_along_path_to` + wire enemy(×2)+guard. Verify digest + suite. (Sequential after W1; both Agent 05.)
- **W3 (Agent 11):** dedup-regression tests (apply_to_enemy scales as before for each difficulty; the 3 spawn paths produce identical enemy stats; a path-follow smoke test) + full DoD gate.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| The 3 difficulty blocks differ subtly (e.g. one also scales gold/speed) | Med | read ALL 3 verbatim; apply_to_enemy reproduces each exact effect; W3 asserts per-path stats; digest guards |
| The 3 path-replan blocks have drifted | Med | DIFF them first; parameterize or leave-and-report a divergent site; digest guards enemy movement |
| Digest drift from a reordered statement | Low-Med | verify digest after EACH dedup; if it drifts, the helper altered behavior — fix |

## 6. Success
Two duplicated blocks become single helpers, enemies spawn/scale/path identically — proven by 654+ green tests, clean determinism guard, unchanged `b73961…` digest.

## 7. Kickoff
Roster: 05 (both dedups, sequential), 11 (regression + DoD), 06 (consult if a path block touches ai). Order: 05 W1 → PM gate → 05 W2 → PM gate → 11 W3 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; behavior-preserving, digest unchanged; NO screenshots; own log; DO NOT COMMIT.
Follow-ups: ENEMY_STATS table; defense.engage + route_to_building (Round D); ranged/research mixins; hud/ursina_renderer/engine/input_handler splits; Move 9; zombie purge.
