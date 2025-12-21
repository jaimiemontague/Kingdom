## Build B (Endweek) — Patch Notes Draft

### Title
**Kingdom Sim — Prototype v1.2.2 (Build B / Endweek)**

### No API keys required
- Run with mock AI: `python main.py` (default) or `python main.py --provider mock`
- Run without any LLM integration: `python main.py --no-llm`

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


