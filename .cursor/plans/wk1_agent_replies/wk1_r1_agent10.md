## Agent 10) PerformanceStability_Lead — wk1_r1 response

### Status
I reviewed the current game loop + existing instrumentation, identified likely hotspots for the wk1 “intent + bounty clarity” changes, and implemented a small set of **measurement + guardrail** improvements that are low-risk for Build A and useful for Build B perf sanity checks.

### Key findings (likely hotspots)
- **Pathfinding / navigation**: `game/systems/navigation.py::compute_path_worldpoints()` already times A* and feeds `game/systems/perf_stats.py`. This will be the first thing to spike when we add more heroes/enemies or increase “scan then pursue” behaviors.
- **Per-frame allocations in overlays**: current perf overlay created a new `pygame.Surface` every frame (and rerendered text every frame). This is a classic “death by allocations” issue during spikes.
- **Cross-product scans**: changes like bounty attractiveness/responder tracking can accidentally become \(O(N_\text{heroes} * N_\text{bounties})\) every tick if computed naïvely; that will scale poorly.
- **Enemy/hero per-tick replanning**: hero movement replans when `path` is empty or goal changes; enemies already have caching/backoff. Any new “intent” UI must not force replans or heavy computations just to display state.

### What I implemented (low-risk mitigations + instrumentation)

#### 1) In-game perf overlay: **no per-frame panel allocations + adds loop timing**
File: `game/engine.py`
- **Mitigation**: cache the overlay panel surface and **only rebuild it** on a short cadence (250ms) or when PF snapshot updates (1s).
- **Instrumentation**: adds loop timing EMA (events/update/render) sampled via `time.perf_counter()` in the main loop. Displayed as:
  - `Loop ms (ema): events=… update=… render=…`
- **Why this matters**: it makes perf regressions visible immediately without adding new heavy overhead.

How to use:
- Toggle overlay: `F2`
- Watch:
  - **Loop ms** (if update spikes, it’s sim; if render spikes, it’s drawing/overlays)
  - **PF calls/s + PF ms/s** (if PF spikes, it’s navigation thrash or too many replans)

#### 2) Headless benchmark runner: **repeatable ms/tick numbers**
File: `tools/perf_benchmark.py`
- Runs a simplified headless sim loop (AI update + entity updates + combat).
- Prints:
  - **ms/tick total**
  - **ms/tick breakdown** (ai/heroes/peasants/enemies/combat)
  - **pathfinding stats** (calls/fails/ms_total + ms/tick)
- Optional `--csv` appends a row for tracking trends.

Examples:
- `python tools/perf_benchmark.py --seconds 12 --heroes 20 --enemies 20 --seed 3`
- `python tools/perf_benchmark.py --seconds 20 --heroes 40 --enemies 60 --seed 3 --csv perf.csv`

### Perf acceptance criteria (for this sprint)
- **No obvious perf regressions from overlays**: perf overlay should not allocate a new panel surface each frame.
- **Bounty/intent computations are capped/cadenced**: avoid doing full rescoring across all heroes and bounties every tick; do it at a cadence (0.25–1.0s) or cap candidates.
- **PF remains bounded**: keep A* replans rate-limited and maintain expansion caps/backoff.

### Risks
- **False confidence from headless**: headless excludes full rendering + fog-of-war; treat it as “sim cost baseline,” not total frame cost.
- **Benchmark workload mismatch**: if future logic is mostly in bounty scoring/intent logging, we should extend the benchmark to include bounties once that code lands.

### Dependencies / coordination needs
- **Agent 8 (UI/UX)**: ensure new hero/bounty UI uses cached text/surfaces and doesn’t rebuild long strings every frame.
- **Agent 3/6 (Architecture/AI)**: ensure intent/decision data is stored as lightweight fields (no heavy serialization per frame) and any attractiveness scoring is computed deterministically on a cadence.

### Questions back to PM
- Do we want to set an explicit **“budget” target** for Build B (e.g., “<= 4ms sim update @ 20 heroes / 20 enemies on reference machine”)? If yes, pick the reference scenario + machine.

### Recommended next actions
- Add a tiny perf section to release checklist: run `tools/perf_benchmark.py` for 2–3 standard profiles and capture the output into notes.
- Once bounty responders/attractiveness lands, optionally extend `tools/perf_benchmark.py` to include a configurable number of bounties and measure scoring cost.







