# WK1 Broad Sweep — Acceptance Checklist (Majesty Feel + Low Bug Risk)

Owner: **GameDirector_ProductOwner (Agent 2)**  
Applies to: **Build A (Midweek)** and **Build B (Endweek)** in `.cursor/plans/wk1-broad-sweep-midweek-endweek_3ca65814.plan.md`

## Goal (what we’re proving this week)
Players get the “Majesty feel” through **indirect control + readable incentives + early aliveness**, without adding risky new systems.

## Pass/Fail gates (must be true)

### 0) Stability gate (hard fail if broken)
- [ ] No crashes/softlocks in `--no-llm` and `--provider mock`.
- [ ] Manual smoke (10 min) passes: boot → place building → peasants construct → hire hero → place bounty → observe fight → pause/resume → quit.
- [ ] Any new UI elements degrade gracefully (missing data shows safe placeholders; no exceptions).

### 1) “Why did they do that?” gate (FS-1)
**Player-facing requirement:** selecting a hero answers “what are they trying to do?” and “what did they decide recently?”

- [ ] Hero UI shows **Current intent** (single line, consistent labels).
- [ ] Hero UI shows **Last decision**: action + short reason + age (or a neutral placeholder if none).
- [ ] Works in LLM + mock + no-LLM; no dependency on external API availability.

### 2) Bounties as a reliable lever gate (FS-2)
**Player-facing requirement:** bounties clearly communicate who is responding and how attractive they are.

- [ ] Each bounty displays **Responders: N** (0..N).
- [ ] Each bounty displays **Attractiveness: Low/Med/High** (or equivalent iconography).
- [ ] If no heroes exist, UI remains valid (Responders stays at 0; no spam/errors).

### 3) Early aliveness gate (FS-3 / P1 in plan)
**Player-facing requirement:** within the first 3 minutes, there is at least one clear decision/prompt.

- [ ] New game: within **3 minutes**, the HUD/log surfaces at least one clear, actionable prompt (build/hire/bounty/defense).
- [ ] The prompt is not a “gotcha” difficulty spike; a reasonable player can recover.

### 4) Determinism guardrail (review gate)
Not implementing multiplayer, but we keep the sim future-friendly.

- [ ] Bounty attractiveness scoring uses **no RNG** and **no wall-clock time**.
- [ ] Any “age since decision” uses sim-time or accumulated ticks, not wall-clock time.
- [ ] If randomness is needed anywhere new, it is **seeded** and lives behind a single source.

## Build-specific focus (so scope stays tight)

### Build A (Midweek) must prove
- [ ] Gates 0, 1, 2 pass (stability + intent/decision inspect + bounty legibility).
- [ ] `python tools/qa_smoke.py --quick` passes (includes determinism guard).
- [ ] Manual smoke (10 min) passes in **mock/no-LLM** modes.

### Build B (Endweek) must prove
- [ ] Gates 0, 1, 2 still pass after changes.
- [ ] Gate 3 passes (early pacing/aliveness).
- [ ] Minor tuning/polish does not reduce clarity.
- [ ] `python tools/qa_smoke.py --quick` passes (includes determinism guard).
- [ ] Manual smoke (10 min) passes in **mock/no-LLM** modes.

## Notes (what to cut immediately if it risks the week)
- If a change adds cross-system coupling, large refactors, or increases bug surface area: **cut/defer**.
- Prefer “good defaults + clear UI” over new mechanics.


