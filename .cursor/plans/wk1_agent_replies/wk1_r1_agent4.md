### Status

Agent 4 (NetworkingDeterminism_Lead) determinism review for wk1 planned changes: **Hero intent + last decision inspect (FS-1)** and **Bounty responders + attractiveness (FS-2)**, plus any supporting tooling/QA updates.

### Summary (high-signal)

- The two wk1 features are **determinism-sensitive** because they touch “decision age”, “time since…”, and any scoring/selection logic around bounties.
- The main risk is accidental use of **wall-clock time** (`pygame.time.get_ticks()`, `time.time()`) or **unseeded RNG** (`random.*`) in *simulation* logic (inside the sim boundary).
- Recommendation: enforce guardrails via (a) code patterns and (b) an automated gate that fails the smoke run if violations are introduced.

### Determinism pitfalls to avoid (for wk1 scope)

- **Bounty attractiveness**:
  - Must not include randomness (no noise/jitter) unless it uses a seeded RNG stream and does not affect sim outcomes unpredictably.
  - Must not depend on wall-clock time (e.g., “bounty decays over real time”).
  - Must not iterate in nondeterministic order (avoid iterating sets/dicts where ordering could affect a “top pick”).

- **“Age” of last decision / time since decision**:
  - Must not use `pygame.time.get_ticks()` directly in sim-critical logic.
  - Must use **sim-time** (or ticks) consistently so replays/lockstep stay stable.
  - UI can display age; but the “source of truth” should be sim-time so it matches saved state and headless tests.

- **Responder tracking**:
  - If responders are computed via scanning heroes each tick, the result is deterministic only if iteration order is deterministic (list order is fine; set iteration is not).
  - If you store responder sets, ensure you only use them for membership checks or you sort them before using in any outcome-affecting way.

- **Python-specific gotchas**:
  - Do not use Python’s `hash()` for any deterministic behavior (process-randomized).
  - If you need stable hashing for IDs or summaries, use a stable method (e.g., `zlib.crc32`) or explicit IDs.

### Required guardrails (concrete rules)

- **Time**:
  - In simulation logic: use `game.sim.timebase.now_ms()` (or pass `now_ms/tick` down from the engine) instead of wall-clock calls.
  - If you need “elapsed time”, prefer tick accumulation / fixed dt semantics.

- **RNG**:
  - In simulation logic: use `game.sim.determinism.get_rng(tag)` for any gameplay randomness.
  - Prefer **per-system** or **per-entity** RNG substreams (tagged) to avoid call-order coupling.

- **Iteration order**:
  - Outcome-affecting logic must not depend on `set` iteration.
  - If you must traverse a set/dict, sort keys/ids first before scoring/picking.

- **Boundary discipline**:
  - Anything inside `game/entities`, `game/systems`, `ai` that changes sim state should follow these rules.
  - UI/graphics can be non-deterministic as long as it doesn’t feed back into sim decisions.

### Recommended implementation / enforcement (low risk)

- Add and maintain a **static determinism guard**:
  - Run `python tools/determinism_guard.py`
  - It should fail if new wall-clock calls or unseeded RNG calls appear in sim code.
  - Wire it into `tools/qa_smoke.py --quick` as a release gate (fail fast).

### Acceptance criteria (for determinism review signoff)

- Bounty attractiveness calculation:
  - **No `random.*`** calls.
  - **No `pygame.time.get_ticks()`** / wall-clock calls.
  - Deterministic ordering for any “top pick” / tie-breaking.

- Hero “last decision age”:
  - Uses **sim-time** or **tick** as the authoritative clock.
  - Safe defaults when no decision exists.

- QA gate:
  - `python tools/qa_smoke.py --quick` fails if determinism guard fails.

### Dependencies / notes to other agents

- Agent 3 (Architecture): define the data structures so timestamps are **sim-time or tick-based**.
- Agent 6 (AI): if you want any variability in intent behavior, make sure it uses a seeded RNG and does not destabilize tests.
- Agent 11/12 (QA/Tools): ensure the smoke runner exercises the new paths and includes the determinism guard.





