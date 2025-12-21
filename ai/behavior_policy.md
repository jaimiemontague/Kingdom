# AI Behavior Policy (LLM-Assisted)

This doc defines the **contract** between the simulation and the LLM, plus the guardrails that keep behavior **debuggable** and **determinism-friendly**.

## Goals

- Keep heroes readable and "Majesty-like": heroes act autonomously but in ways the player can predict.
- Ensure LLM output is safe: malformed output must never break the sim.
- Support future determinism work: all behavior should have clear fallbacks and stable identifiers.

## Decision Contract

### Input

The LLM receives:

- `system_prompt`: high-level role + rules
- `user_prompt`: a situation summary built from structured context (`ContextBuilder`)

### Output (strict)

The LLM must respond with **only** a single JSON object:

- `action` (string): one of
  - `fight`
  - `retreat`
  - `buy_item`
  - `use_potion`
  - `explore`
- `target` (string): optional, depends on action
- `reasoning` (string): short, for debugging/telemetry

Any missing/invalid fields are treated as parse failure and trigger a fallback decision.

## Guardrails (Current)

- `LLMBrain._parse_response` extracts JSON and validates:
  - `action` must be in `VALID_ACTIONS`
  - `target` and `reasoning` must be strings (otherwise coerced to empty)
- On parse failure/timeout/provider errors: `get_fallback_decision(context)` is used.

## Determinism Notes

The sim currently uses randomness in multiple places (patrol zones, wandering, bounty scoring).
For future multiplayer determinism, we should route all randomness through a **seeded RNG** owned by the simulation tick/state (not `random.*` or wall-clock time).

## Debuggability Notes

When debugging hero decisions, we want:

- the context snapshot that led to the decision (structured)
- the LLM output (raw + parsed)
- the applied action in-engine

This can be extended later with an on-screen debug overlay or structured log sink.


