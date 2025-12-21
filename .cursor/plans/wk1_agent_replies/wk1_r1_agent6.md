# Agent 6 (AIBehaviorDirector_LLM) — wk1_r1 response

## Status

Deliver **Build A (midweek)** P0: stable hero **intent taxonomy** + consistent **last decision logging** that works in **LLM + mock + no-LLM** modes and is safe for determinism/perf.

## Summary (what I’m proposing)

- Add a small, stable **intent taxonomy** for heroes (string label) that UI and QA can display.
- Add a lightweight **last decision record** on each hero (action, reason, age, compact inputs summary, source) to answer “why did that hero do that?”
- Keep it **low-risk**: no new LLM call sites; no wall-clock time dependencies; no per-frame heavy allocations; fallbacks in no-LLM.

## Intent taxonomy (P0)

The taxonomy is a short set of labels (string), used for display/telemetry only (not as authoritative simulation state):

- `idle`
- `pursuing_bounty`
- `shopping`
- `returning_to_safety`
- `engaging_enemy`
- `defending_building`
- `attacking_lair`

### Where to compute intent

Primary recommendation (most stable, lowest coupling):

- **Derive intent in one place** (preferably the hero entity or a thin “intent resolver”) from current **state + target**.
- `BasicAI` can call a single method (e.g. `hero._update_intent_and_decision(game_state)`) if present; otherwise it falls back to a small local derivation.

This keeps UI/system code from needing to “understand” AI internals while still being easy to incrementally refine.

## Decision logging rules (P0)

We store only the **last** decision per hero (no unbounded buffers), with small bounded strings.

### Required fields

- `action`: string (example: `retreat`, `buy_item`, `pursue_bounty`, `engage_enemy`)
- `reason`: short string (<= ~140 chars; strip newlines)
- `at_ms`: integer sim-time timestamp (no wall-clock)
- `inputs_summary`: compact summary (string or small dict) suitable for UI/debug
- `source`: string (example: `llm`, `fallback`, `heuristic`, `system`)
- (optional) `intent`: the intent label at time of decision

### When to record a decision

Record on meaningful transitions only (avoid per-frame spam):

- When a bounty pursuit begins (and when it transitions into `attacking_lair`)
- When a hero decides to shop / retreat / engage an enemy
- When the system triggers an LLM consult (“request_llm” breadcrumb)
- When an LLM/fallback decision is applied

### Determinism guardrails

- Use sim-time (`sim_now_ms()` / tick-based timebase) for `at_ms` and “age” calculations.
- Do not introduce new `time.time()` / wall-clock checks in simulation decisions.
- Avoid adding new randomness to attractiveness/scoring decisions (those live elsewhere and must be deterministic).

## Mock + no-LLM parity

Goal: **no crashes, no softlocks**, and the hero panel still shows reasonable intent/last decision.

- If no LLM brain is wired and the code reaches an LLM decision point, choose a **deterministic fallback decision** from structured context and record it with `source="fallback"`.
- In mock provider mode, record the applied action with `source="llm"` (or `source="mock"` if you want to differentiate).

## Prompt/schema notes (LLM safety)

- Keep a single shared action whitelist (`VALID_ACTIONS`) and validate parsed LLM output against it.
- Treat invalid/malformed output as parse failure and **fall back**.
- Ensure decision record “reason” is safe to show (short, no multiline).

## Acceptance criteria (agent-level)

- UI/inspection can display `hero.intent` at all times (never empty).
- UI/inspection can display `hero.last_decision` fields:
  - action + reason + age (computed from `at_ms`)
  - safe placeholders if no decision exists yet
- Works in:
  - `--provider mock`
  - no-LLM path (LLM disabled / not wired)
- No new determinism issues (sim-time only, no wall-clock in logic).

## Risks / mitigations

- Risk: logging spam / perf → mitigate by recording only on transitions; keep reasons short; store only last record.
- Risk: intent derivation drift → mitigate by keeping derivation centralized and simple (state/target driven), refine later.
- Risk: typed bounty completion semantics → mitigate by not “auto-claiming” typed bounties via proximity; let their systems resolve completion.

## Dependencies

- Agent 3 (Architecture): confirm/standardize the thin contract shape for `last_decision` so UI and QA don’t churn.
- Agent 8 (UX/UI): define copy/layout for intent + last decision and how “age” should read.
- Agent 11 (QA): add quick assertions that intent is non-empty and last_decision is present after a short run.

## Recommended next actions

- Finalize `HeroDecisionRecord` shape (dataclass or dict) + ensure UI reads it without heavy allocations.
- Wire hero panel to show:
  - `Intent: <label>`
  - `Last: <action> — <reason> (<age>)`
- Extend QA smoke to assert:
  - intent becomes non-empty within N seconds
  - at least one decision record exists within N seconds (in mock and no-LLM)


