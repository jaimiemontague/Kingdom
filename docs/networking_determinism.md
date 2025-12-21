## Status

This doc is the **Networking / Determinism guardrail** for Kingdom Sim (future multiplayer enablement).

It is written for a **single-player-first** codebase that wants to avoid rewrites later.

## Directional multiplayer approach (recommended)

- **Near-term goal**: make the simulation *lockstep-ready* (deterministic tick + seeded RNG + serializable state), without implementing multiplayer yet.
- **Later MP implementation options**:
  - **Lockstep (deterministic)**: each client sends inputs per tick; all peers simulate identically.
  - **Server-authoritative**: server simulates and replicates snapshots/deltas; clients predict for feel.

For this style of game (Majesty-like, many agents), **lockstep-ready simulation boundaries** are a strong investment even if you eventually choose server-authoritative, because it improves replay/debugging, save/load stability, and regression testing.

## The “network-ready simulation boundary”

### What is inside the boundary (must be deterministic)

- **Tick-driven state updates**: entities/systems, spawns, combat resolution, path decisions, AI decisions that affect sim state.
- **RNG**: all gameplay randomness must come from a seeded RNG (never `random` module directly).
- **Time**: all gameplay timing must come from the simulation clock (never wall-clock time).
- **Iteration order**: anything that could affect outcomes must iterate deterministically (avoid `set` iteration; sort keys).

### What is outside the boundary (can be non-deterministic)

- Rendering, VFX, sound, UI animation
- Perf profiling / `perf_counter`
- Debug logging and telemetry (as long as it doesn’t feed back into sim decisions)

## Guardrails we are enforcing (incrementally)

### RNG

- **Rule**: gameplay code must use `game.sim.determinism.get_rng(...)` (seeded).
- **Why**: global `random` calls break replays and lockstep.
- **Pattern**:
  - System-wide stream: `self.rng = get_rng("enemy_spawner")`
  - Per-object stream: `get_rng(f"lair:{type}:{x}:{y}")`

### Time

- **Rule**: gameplay code must use `game.sim.timebase.now_ms()` (or be passed `now_ms`).
- **Engine owns time** and can drive it from a deterministic fixed tick when `DETERMINISTIC_SIM=1`.

### Tick

- **Rule**: simulation should be stepped with a fixed dt (tick-based), not variable frame dt.
- **Current implementation**: `DETERMINISTIC_SIM=1` runs `dt = 1 / SIM_TICK_HZ` every loop.

### Python gotchas

- **Never use `hash()` for determinism**. Python salts the hash per process.
- **Avoid set/dict iteration affecting outcomes**; if order matters, sort keys or use lists.
- **Floating point**: fixed dt reduces divergence, but strict cross-platform bit-perfect determinism may still require fixed-point math later.

## How to run deterministically (today)

- Set environment variables:
  - `DETERMINISTIC_SIM=1`
  - `SIM_SEED=1` (any integer)
  - `SIM_TICK_HZ=60` (usually same as FPS)

This makes world gen + spawns + lair behavior + gameplay timers reproducible for a given input sequence.

## Determinism guard (QA gate)

Run:
- `python tools/determinism_guard.py`

It statically scans simulation code and fails if it finds new wall-clock time usage (e.g. `pygame.time.get_ticks()`, `time.time()`) or unseeded RNG (`random.*`).


