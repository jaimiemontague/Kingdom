## Agent 13 — SteamRelease_Ops_Marketing (wk1_r1)

### Assignment
Draft patch notes for **Build A (Midweek)** and **Build B (Endweek)** using `docs/release/patch_notes_template.md`, highlighting 3 key bullets per build plus known issues, aligned to the Week 1 “broad sweep” plan.

---

## Build A (Midweek) — Patch Notes Draft

### Title
**Kingdom Sim — Week 1 Broad Sweep (Build A / Midweek)**

### Highlights
- **Hero clarity**: Hero panel now exposes **Current intent** + **Last decision** (action + short reason + age).
- **Bounty clarity**: Bounties show **Responders: N** and a deterministic **Attractiveness** tier (Low/Med/High).
- **Debuggability**: Added safe instrumentation/logging so you can answer “why did that hero do that?” without guesswork.

### Gameplay & Balance
- (If shipped) Minor bounty cost/reward adjustments to improve early leverage without destabilizing pacing.

### AI Behavior
- Introduced/standardized intent labels (e.g., `idle`, `pursuing_bounty`, `shopping`, `returning_to_safety`, `engaging_enemy`, `defending_building`, `attacking_lair`).
- Last-decision record now stores a short reason string and a sim-time “age” value (works in **LLM**, **mock**, and **--no-llm**).

### UI/UX
- Hero panel: shows **Intent** and **Last decision** with a safe placeholder when none exists yet.
- Bounty overlay/UI: shows **Responders** and **Attractiveness** in a compact, non-spammy format.

### Visuals
- (Optional) Small iconography/shape language for bounty attractiveness tiers (placeholder-friendly).

### Performance & Stability
- No new crashes/softlocks in `--no-llm` and `--provider mock`.
- Guardrail: new “age/time since decision” uses **sim-time/ticks**, not wall-clock.

### Known Issues (draft — update as QA runs)
- (If observed) UI overlap at small resolutions when multiple bounties are clustered.
- (If observed) Some heroes may show “No decision yet” briefly after spawn (expected).

### How to test (quick)
- `python tools/qa_smoke.py --quick`
- Manual 10-minute smoke: boot → place a building → observe peasants build → hire a hero → place a bounty → confirm responders + intent/decision fields update → pause/resume → quit.

---

## Build B (Endweek) — Patch Notes Draft

### Title
**Kingdom Sim — Week 1 Broad Sweep (Build B / Endweek)**

### Highlights
- **Early pacing guardrail**: within ~3 minutes, the game surfaces at least one clear decision prompt (without a difficulty spike).
- **Balance polish**: early wave pressure + bounty reward bands tuned to feel active but fair.
- **Stability/perf pass**: reduced overhead from new overlays/scans; expanded smoke coverage for new features.

### Gameplay & Balance
- Early-game pacing adjusted (warmup/pressure) to reduce dead air while staying recoverable.
- Bounty costs/rewards refined so bounties feel like a reliable lever across low/med/high targets.
- (If shipped) Lair-related payouts/costs sanity-checked to avoid runaway snowballing.

### AI Behavior
- Intent and last-decision tracking polished for consistency and readability.
- Bounty attractiveness scoring confirmed deterministic (no RNG / wall-clock dependencies).

### UI/UX
- Clarity polish: reduced UI spam/overlap; tightened copy for intent and decision reasons.
- Debug panel (if enabled) includes intent/decision fields for quick triage.

### Performance & Stability
- Reduced per-frame allocations in overlays (cached formatting where possible).
- Prevented O(N_heroes * N_bounties) behavior via caps/short-circuiting (as applicable).
- Expanded `tools/qa_smoke.py --quick` assertions around:
  - bounty responder updates
  - non-empty hero intent after a short runtime
  - no exceptions in mock/no-LLM paths

### Known Issues (draft — update at ship)
- (If observed) Some edge cases where responder count lags for 1–2 ticks after retargeting.
- (If observed) Rare UI jitter when rapidly panning camera over dense overlays.

### How to test (quick)
- `python tools/qa_smoke.py --quick`
- Manual 10-minute smoke: boot → build → peasants construct → hire hero → place bounty → verify responders/attractiveness → observe 1–2 waves → pause/resume → quit.

---

## Questions back to PM (to finalize announcements)
- Naming: do we label these as `Prototype v1.2.1 (Build A)` / `v1.2.2 (Build B)` or “Week 1 Build A/Build B” only?
- Any “must-mention” bullets for either build once they land (e.g., a particular crash fix, perf target, or tuning headline)?


