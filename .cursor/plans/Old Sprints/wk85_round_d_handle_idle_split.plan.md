# WK85 Sprint Plan — Round D-5: exploration.handle_idle decomposition

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the 128-LOC `handle_idle` god-function decomposed into ordered, named sub-steps; behavior byte-identical (digest `b73961…` unchanged).
**Predecessors:** WK68-84. **Roadmap:** Round D — audit: "exploration.handle_idle is a 160-line god-function" (now ~128 after WK74's route_to_building extraction).

## 0. TL;DR
`ai/behaviors/exploration.py` `handle_idle(ai, hero, view)` (lines 194-322, ~128 LOC) is a sequential god-function: an ordered series of "should the idle hero do X?" checks (rest / shop / eat / pursue bounty / explore / patrol). WK85 decomposes it into named ordered sub-step functions (each a `def _idle_step_<name>(ai, hero, view) -> bool` returning True if it handled the hero, else False), with `handle_idle` becoming a thin ordered driver that calls them in the SAME order with the SAME short-circuit semantics. **This is the SAFEST remaining refactor**: `handle_idle` IS the idle hero decisions the 300-tick digest hashes, so the digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` is a PERFECT guard — any behavior change breaks it. Headless, no screenshots. PM writes no code.

## 1. Scope
**IN:** in `ai/behaviors/exploration.py`, refactor `handle_idle` from one 128-line body into:
- A set of ordered private step functions (module-level `def _idle_<step>(ai, hero, view) -> bool`), each containing ONE of the current sequential branches VERBATIM, returning True iff it took an action (mirroring the current early-return/return points).
- A thin `handle_idle(ai, hero, view)` that calls the steps IN THE SAME ORDER, returning as soon as one returns True (preserving the exact short-circuit/fall-through behavior). The net control flow must be IDENTICAL to today.
Keep `handle_idle`'s signature + name (basic_ai dispatch calls it).

**OUT:** moving handle_idle to another module; changing the order/conditions/effects of any branch; touching explore/assign_patrol_zone/the helpers; any behavior change. **This is a behavior-preserving decomposition — same branches, same order, same effects.**

## 2. Approach
Read `handle_idle` (194-322) and identify the sequential decision points (each `if <cond>: <do X>; return` or fall-through block). Lift each into a `_idle_<name>(ai, hero, view) -> bool` that performs the SAME body and returns True iff the original would have returned/taken the action there. Then:
```python
def handle_idle(ai, hero, view) -> None:
    for step in (_idle_<a>, _idle_<b>, ...):   # SAME order as the original sequence
        if step(ai, hero, view):
            return
    # any final fall-through behavior preserved
```
(If the branches share locals computed once at the top — e.g. `world = view.world`, nearest-X — either recompute in each step exactly as cheap, or pass via a small local; the digest catches any divergence. Prefer recomputing exactly as the original did so behavior is identical.) Keep everything in exploration.py (no new module needed).

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **807 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` (PERFECT guard — handle_idle IS the idle decisions).
- **D.** `qa_smoke.py --quick` green.
- **E.** `handle_idle` is now a thin ordered driver over named `_idle_*` step functions; same signature/name; net behavior identical; exploration.py readable (no LOC bloat target — this is a clarity refactor).
- **F.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 06):** decompose handle_idle. Verify suite + digest + qa_smoke.
- **W2 (Agent 11):** a behavior pin (the step driver returns on the first True; an integration tick test that an idle hero in a known state takes the same action) + full DoD.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Decomposition changes the order or a short-circuit → behavior drift | Med | the digest is a PERFECT guard (handle_idle IS the hashed idle decisions); any drift caught immediately; preserve order + return points exactly |
| A shared local computed once now recomputed per step with a subtle difference | Med | recompute EXACTLY as the original; digest catches any divergence |
| Over-refactor (merging/reordering branches) | Low | scope: SAME branches, SAME order, SAME effects — a pure decomposition, not a logic change |

## 6. Success
`handle_idle` reads as a clear ordered list of idle steps, idle hero behavior is byte-identical — proven by 807+ green tests, clean determinism guard, and the unchanged `b73961…` digest (definitive for idle decisions).

## 7. Kickoff
Roster: 06 (W1), 11 (verify W2), 05 (consult). Order: 06 W1 → PM gate (suite + digest + qa_smoke) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; behavior-preserving DECOMPOSITION (same branches/order/effects), keep handle_idle's name+signature; digest must stay byte-identical; NO screenshots; own log; DO NOT COMMIT.
Follow-ups: context_builder/direct_prompt_validator splits + ai/vocab.py + TaskRouter; the BIG presentation splits (hud/ursina_renderer body/ursina_app — screenshot-heavy, fresh-context); Move 9; world.py; config package; clusters 3/4; Round E audit; 21-file zombie purge.
