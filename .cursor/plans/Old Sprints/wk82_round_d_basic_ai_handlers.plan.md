# WK82 Sprint Plan — Round D-2: basic_ai.py inline-handler extraction

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; BasicAI's inline combat/recovery state-machine handlers extracted into ai/behaviors/ modules behind thin dispatch wrappers; behavior byte-identical (digest `b73961…` unchanged).
**Predecessors:** WK68-81. **Roadmap:** Round D (AI). The audit: "BasicAI mixes coordinator role with ~250 LOC of inline state-machine handlers — move these into ai/behaviors to match the existing seam."

## 0. TL;DR
`ai/basic_ai.py` (515 LOC): `handle_idle`/`handle_moving`/`handle_shopping` already delegate to behavior modules; but `handle_fighting` (+ nested `_chase_goal_unchanged`), `handle_retreating`, and `_finalize_deferred_task` are still inline state-machine bodies. WK82 moves them into `ai/behaviors/combat.py` + `ai/behaviors/recovery.py` as functions taking `(ai, hero, view)`, leaving thin delegating wrappers on BasicAI (so the `state_handlers` dispatch + all callers are unchanged). Pure-move, headless, **perfectly digest-guarded** (these handlers ARE the hero combat/retreat decisions the 300-tick digest hashes). PM writes no code.

## 1. Scope
**IN — move into ai/behaviors/ (functions take `(ai, hero, view)`, BasicAI keeps delegating wrappers):**
- `ai/behaviors/combat.py`: `handle_fighting(ai, hero, view)` ← `BasicAI.handle_fighting` (basic_ai.py:344-405, including the nested `_chase_goal_unchanged`).
- `ai/behaviors/recovery.py`: `handle_retreating(ai, hero, view)` ← `handle_retreating` (406-430); `finalize_deferred_task(ai, hero, view)` ← `_finalize_deferred_task` (431-454).
- BasicAI keeps `handle_fighting`/`handle_retreating`/`_finalize_deferred_task` as 1-line delegating wrappers (same names — `update_hero`'s dispatch + any `state_handlers` map call them unchanged).

**OUT:** the TaskRouter / TaskProposal redesign (Move 12 — bigger, later); touching handle_idle/handle_moving/handle_shopping (already delegate); handle_resting (short, leave); context_builder/direct_prompt_validator (later); any behavior change. **Move bodies VERBATIM (self.->ai.).**

## 2. Pattern (WK75-81, verbatim)
```python
# ai/behaviors/combat.py
from __future__ import annotations
from typing import TYPE_CHECKING
# ... same leaf imports handle_fighting used (defense.engage, HeroState, contracts, etc.) ...
if TYPE_CHECKING:
    from ai.basic_ai import BasicAI

def handle_fighting(ai: "BasicAI", hero, view) -> None:
    # EXACT body, self.->ai.  (nested _chase_goal_unchanged moves with it)
    ...
```
```python
# ai/basic_ai.py
def handle_fighting(self, hero, view):
    from ai.behaviors import combat
    return combat.handle_fighting(self, hero, view)
```
TYPE_CHECKING-only BasicAI import; no cycle (combat/recovery take `ai` as param + import only leaf helpers; the audit warns ai.behaviors.__init__ can pull llm_bridge → keep imports lazy/leaf to avoid the cycle); preserve behavior EXACTLY.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **780 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` (PERFECT guard — combat/retreat decisions drive the digest).
- **D.** `qa_smoke.py --quick` green.
- **E.** `ai/behaviors/combat.py` + `recovery.py` exist with the handlers; BasicAI keeps the 3 wrapper names delegating; basic_ai.py smaller (~515 → ~420); no import cycle.
- **F.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 06):** extract combat.py + recovery.py + wrappers. Verify suite + digest + qa_smoke.
- **W2 (Agent 11):** seam test (modules exist + wrappers delegate) + full DoD.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A handler references a name only imported at basic_ai top → NameError | Med | copy each handler's leaf imports; digest (perfect) + qa_smoke catch it |
| Import cycle via ai.behaviors.__init__ → llm_bridge | Med | combat/recovery take `ai` param; import only leaf helpers; TYPE_CHECKING for BasicAI; if __init__ eagerly imports, keep the wrapper's import lazy |
| Behavior drift in the combat/retreat decision | Low | move VERBATIM; the digest is a PERFECT guard (combat/retreat ARE the hashed decisions) |

## 6. Success
The inline combat/recovery handlers live in ai/behaviors/ behind thin wrappers, hero combat/retreat plays identically — proven by 780+ green tests, clean determinism guard, and the unchanged `b73961…` digest (definitive for AI behavior).

## 7. Kickoff
Roster: 06 AIBehaviorDirector (extraction W1), 11 (verify + DoD W2), 05 (consult). Order: 06 W1 → PM gate (suite + digest + qa_smoke) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE MOVE, keep wrapper names, TYPE_CHECKING-only import, leaf imports only (avoid the ai.behaviors.__init__ cycle); digest must stay byte-identical; NO screenshots; own log; DO NOT COMMIT.
Follow-ups: context_builder/direct_prompt_validator/bounty_pursuit/exploration splits + ai/vocab.py + TaskRouter (rest of Round D); the BIG presentation splits (hud/ursina_renderer body/ursina_app); Move 9; world.py; config package; clusters 3/4; Round E audit; zombie purge.
