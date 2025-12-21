## Agent 12 — ToolsDevEx_Lead (wk1_r1)

### Status
- Assignment: Propose and implement one deterministic dev flag/command to spawn a mini test setup for **bounties + intent** to speed iteration and strengthen QA gates.
- Outcome: Implemented a deterministic headless scenario preset and extended the automated smoke runner to cover it.

### Deliverables shipped (code + workflow)

#### 1) Deterministic mini-scenario preset (headless)
- Added `--scenario intent_bounty` to `tools/observe_sync.py`.
- Behavior:
  - Places **two deterministic explore bounties** (one close, one farther) relative to the castle.
  - Designed to exercise: bounty existence, hero response/claim, and intent activity quickly.

#### 2) Smoke gate upgraded to cover the new scenario
- Updated `tools/qa_smoke.py --quick` to include a new profile:
  - `"bounty scenario preset (responders/claim)"`
  - Runs: `observe_sync.py --no-enemies --scenario intent_bounty --qa`

#### 3) `observe_sync` closer to live game loop + better triage logs
- `tools/observe_sync.py` now uses `game.systems.bounty.BountySystem` rather than manually managing `Bounty` instances.
- The per-tick `game_state` now includes:
  - `"bounties"` as **unclaimed bounties** (like `GameEngine` does)
  - `"bounty_system"` for future-friendly hooks (responder counting, attractiveness, etc.)
- Determinism guardrail:
  - Drives sim time via `game.sim.timebase.set_sim_now_ms(...)` each tick, so code using `now_ms()` is deterministic-friendly.
- Log format improvements:
  - Each log line includes a compact bounty summary:
    - `bounties_unclaimed=... claimed=... spent=...`

#### 4) QA assertion robustness fix (to match actual bounty lifecycle)
- Problem encountered during verification:
  - In QA mode, bounties can be **claimed before the warmup window**, and claimed bounties are removed from the unclaimed list.
  - The old assertion required an unclaimed bounty to still exist to detect responders → could fail incorrectly.
- Fix:
  - Treat `bounty_system.total_claimed > 0` as sufficient evidence of a responder.

### How to run / test (commands)

#### Required smoke gate (release + local pre-merge)
```bash
python tools/qa_smoke.py --quick
```
Expected: PASS (exit code 0), includes determinism guard + multiple headless profiles + the new bounty scenario preset.

#### Run only the new deterministic scenario
```bash
python tools/observe_sync.py --seconds 12 --seed 3 --heroes 10 --no-enemies --scenario intent_bounty --qa
```

### Acceptance criteria (DevEx for this sprint slice)
- A single command exists to run a deterministic headless setup for bounties + intent: **`observe_sync --scenario intent_bounty`**.
- `python tools/qa_smoke.py --quick` runs the scenario and returns **exit code 0**.
- Output is triage-friendly in CI logs (compact per-tick summary; clear `[qa] PASS/FAIL`).
- No gameplay code paths are riskily modified (changes isolated to `tools/` runner behavior).

### Risks / notes
- Pygame emits a `pkg_resources` deprecation warning under Python 3.13; it does not fail the run, but CI logs will show it.
- The current QA check does not enforce “responders count UI field exists” yet (it logs that as `bounty_responder_attr_present=False`); once responder tracking lands in the bounty system, QA can tighten.

### Dependencies
- `game.systems.bounty.BountySystem` existing and stable.
- `game.sim.timebase.set_sim_now_ms` exists (used for deterministic-friendly time).
- Headless SDL dummy drivers available (`SDL_VIDEODRIVER=dummy`).

### Recommended next actions (for PM/QA/other agents)
- Agent 11 (QA): once bounty responder tracking + hero intent fields are standardized, tighten `observe_sync --qa` to assert:
  - responders count > 0 via explicit field (not inference)
  - intent taxonomy labels are present and non-empty after warmup
- Agent 3/6 (Architecture/AI): when intent/decision contracts land, consider exposing minimal JSON-friendly snapshots for `observe_sync` to log in one line (avoid large prints).

### Files changed
- `tools/observe_sync.py`
- `tools/qa_smoke.py`



