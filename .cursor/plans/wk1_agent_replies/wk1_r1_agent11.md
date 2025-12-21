### Status
**Agent 11 (QA_TestEngineering_Lead)** — I reviewed the Week 1 sprint plan and implemented the **QA workstream P0**: expand automated smoke to cover bounty + intent paths, and ensure the “QA gate” (`qa_smoke --quick`) is stable and deterministic-friendly.

### Deliverables
- **Smoke coverage extended (per plan P0)**
  - `tools/observe_sync.py` now supports `--qa` assertions:
    - **Bounty exists** (when bounties/scenario enabled)
    - **At least one bounty responder/claim happens** (robust even if the bounty is claimed before warmup)
    - **Hero intent non-empty** after warmup (uses `hero.intent` if present)
  - Deterministic sim-time is driven in the headless runner via `game.sim.timebase.set_sim_now_ms(...)` so cooldown-based logic works without `--realtime`.
- **QA gate unblocked + determinism guard passing**
  - Fixed determinism guard violations:
    - `ai/basic_ai.py`: removed `time.time()` usage in debug throttling (uses sim-time).
    - `ai/providers/mock_provider.py`: replaced `random.random()` with seeded `get_rng("mock_provider")`.
  - Fixed crashers from partially-integrated intent/decision plumbing in `ai/basic_ai.py` by adding small helper methods that delegate to the hero’s contract (`hero._update_intent_and_decision`, `hero.record_decision`).
- **QA docs updated**
  - `QA_TEST_PLAN.md` includes new regression bullets for intent + bounty responders.

### Questions (blockers only)
- None.

### Next actions
- Run the sprint gate exactly as specified in the plan:

```bash
python tools/qa_smoke.py --quick
```

### Handoff checklist
- **Files changed**
  - `tools/observe_sync.py` (QA assertions + deterministic sim-time)
  - `ai/basic_ai.py` (intent/decision helpers + sim-time log throttle fix)
  - `ai/providers/mock_provider.py` (seeded RNG)
  - `QA_TEST_PLAN.md` (new regression bullets)
- **How to test**
  - `python tools/qa_smoke.py --quick` → should end with **DONE: PASS**
- **Gotchas / future cleanup**
  - Headless runs still warn about `pkg_resources` deprecation (Pygame dependency warning) — not a functional failure, but worth pinning/cleaning later if it becomes noisy.



