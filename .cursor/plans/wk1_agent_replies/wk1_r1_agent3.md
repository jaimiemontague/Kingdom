## Agent

`3) TechnicalDirector_Architecture`

## Status

Implementing the **thin, stable data contracts** for:
- **Hero intent + last decision snapshot**
- **Bounty evaluation** (responders + deterministic attractiveness)

These contracts are designed to be:
- **Determinism-friendly** (no wall-clock for sim logic; use sim-time only)
- **Low-coupling** (no cross-system import webs; small dataclasses / dict-like structures)
- **UI + QA friendly** (always present, safe defaults; works in `--no-llm` and mock provider paths)

## Deliverables (this sprint slice)

- **Contract module**: `game/sim/contracts.py`
  - `HeroDecisionRecord` (action, reason, at_ms, optional context)
  - `HeroIntentSnapshot` (intent + optional last decision)
  - `BountyEvalSnapshot` (bounty_id, responders, attractiveness score+tier)
- **Hero fields (standardized)**: add/standardize `hero.intent` + `hero.last_decision`
  - Provide a tiny `hero.get_intent_snapshot()` so UI can consume without importing AI.
- **Bounty fields (standardized)**: add `bounty.responders` + `bounty.attractiveness_{score,tier}`
  - Provide `BountySystem.update_metrics(heroes, game_state)` (or equivalent) to populate these deterministically.
- **Engine wiring**: call bounty metrics update once per sim tick so UI can read stable values.

## What’s already implemented in code (in this workspace)

- **Thin contract module created**:
  - `game/sim/contracts.py` (dataclasses + `to_dict` helpers).
- **Hero intent + last decision (auto-derived, safe defaults)**:
  - `game/entities/hero.py` now includes:
    - `hero.intent: str` (default `"idle"`)
    - `hero.last_decision: HeroDecisionRecord | None`
    - `hero.get_intent_snapshot(now_ms=None) -> dict`
    - Best-effort `_derive_intent()` aligned with the sprint taxonomy:
      - `idle`, `pursuing_bounty`, `shopping`, `returning_to_safety`, `engaging_enemy`, `defending_building`, `attacking_lair`
    - Intent/decision refresh runs inside `Hero.update()` and is **non-blocking** (wrapped in `try/except`), so it does not create new crash surfaces.
  - This means the UI/QA can see intent/decision even when the AI controller is disabled.

## Proposed interfaces / contracts (final shape)

### 1) Hero intent + last decision

- **Hero-owned state** (single source of truth for UI):
  - `hero.intent: str`
  - `hero.last_decision: HeroDecisionRecord | None`
- **UI read path**:
  - `hero.get_intent_snapshot(now_ms=None) -> dict`
    - returns `{ intent, last_decision: { action, reason, at_ms, age_ms, context } }`
- **Write path**:
  - Auto-derived each update from `hero.state` and `hero.target` (no direct dependency on AI/LLM).
  - Optional explicit writes are allowed later (e.g., LLM decisions) via `hero.record_decision(...)`.

### 2) Bounty evaluation (responders + attractiveness)

- **Bounty-owned state** (stable, easy for HUD overlays):
  - `bounty.responders: int` (default 0)
  - `bounty.attractiveness_score: float` (default 0.0)
  - `bounty.attractiveness_tier: str` (default `"low"`)
- **Update function**:
  - `BountySystem.update_metrics(heroes, game_state)`:
    - Compute responders by scanning heroes’ current bounty targets.
    - Compute attractiveness score deterministically from:
      - reward (sublinear), distance proxy (optional), risk (if available), bounty_type bonus, responder penalty
    - Convert score to tier: `low/med/high` using simple stable thresholds.
- **Performance target**:
  - Must be **O(H + B)** per tick, no nested hero*bounty scans.

## Determinism guardrails (for this slice)

- **No wall-clock** in sim logic:
  - Use `game.sim.timebase.now_ms()` for timestamps that need “age”.
  - Never use `time.time()` or Python `hash()` in scoring/keys.
- **No RNG** in attractiveness:
  - Attractiveness score/tier must be a pure function of sim state.
- **Stable identifiers**:
  - Use `bounty.bounty_id` and stable string tags; avoid `id(obj)` for anything user-visible or persisted.

## Acceptance criteria (Architecture)

- Hero panel/debug can show:
  - **Current intent** (always a string, never missing)
  - **Last decision**: action + short reason + age (safe placeholder if None)
  - Works in `--no-llm` and `--provider mock` without exceptions.
- Each bounty exposes:
  - **Responders: N** (0..N)
  - **Attractiveness tier**: low/med/high computed deterministically
- No new import cycles: contracts live under `game/sim/` and are depended on, not depending on systems/entities.

## Risks

- **Perf risk** if responders are computed via nested scans (avoid by counting from hero targets).
- **Coupling risk** if UI starts importing AI modules to read intent/decision (avoid by keeping UI reads on `Hero` and `Bounty` fields).
- **Schema drift** if LLM decision logging later diverges from `HeroDecisionRecord` fields (mitigation: keep `record_decision()` the single helper).

## Dependencies

- UI workstream needs read access to:
  - `hero.get_intent_snapshot()` (or `hero.intent`/`hero.last_decision`)
  - `bounty.responders` and `bounty.attractiveness_tier`
- QA/Tools will likely want a deterministic “mini scenario” flag to make these fields appear quickly (but not required for contract correctness).

## Questions back to PM (blockers)

- Do you want the bounty attractiveness tier to be:
  - A global tier (same for all heroes), or
  - A per-hero tier (depends on hero class/position)?
  - Recommendation: **global tier for Build A** (simple + legible), per-hero can come later.

## Recommended next actions (integration order alignment)

- Finish `BountySystem` responder + attractiveness fields and update call (engine wiring).
- UI (Agent 8) reads hero/bounty fields only; no AI imports.
- QA (Agent 11) adds smoke checks:
  - at least one hero has non-empty intent after a short run
  - bounty responders/tier fields exist and don’t throw in mock/no-llm.


