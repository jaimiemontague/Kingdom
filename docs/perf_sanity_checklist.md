## Perf sanity checklist (wk1 broad sweep)

- **Overlay / UI allocations**: perf overlays and debug panels should not allocate new `pygame.Surface` objects every frame; cache panels and only re-render text on a timer or when values change.
- **Hot loops stay linear**: anything that runs every tick should be \(O(N)\) over entities, not \(O(N^2)\) without explicit caps.
- **Bounties scan caps**: avoid unbounded `N_heroes * N_bounties` scoring every tick; prefer a small cadence (e.g. every 0.25–1.0s) and/or capping candidates per hero/bounty.
- **Pathfinding backpressure**: A* replans must be rate-limited (cache goals, keep “no-path” backoff) and have an expansion cap.
- **Entity counts on screen**: in playtesting, note ms/tick as heroes/enemies/peasants increase; keep a rough “safe budget” for Early Access.

### How to run quick perf checks

- **In-game**: press `F2` to toggle the perf overlay; watch loop ms and PF counters.
- **Headless benchmark**: `python tools/perf_benchmark.py --seconds 12 --heroes 20 --enemies 20 --seed 3`


