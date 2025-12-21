## Status

MP readiness checklist for features landing in the single-player codebase.

## Checklist (feature must pass to be “MP-ready”)

### Simulation boundaries

- **Sim state is explicit**: data required to reproduce the feature is stored in the sim state (not hidden in UI or globals).
- **Inputs are explicit**: the feature can be driven via discrete player inputs/commands (not “read mouse position inside sim”).
- **No IO inside sim**: no filesystem/network calls in simulation update paths.

### Determinism

- **RNG**: uses `game.sim.determinism.get_rng(...)` only.
- **Time**: uses `game.sim.timebase.now_ms()` or passed-in sim time, never wall-clock.
- **Iteration order**: no outcome-affecting iteration over `set`/unordered dicts; sort if needed.
- **No Python `hash()` for seeds/IDs**: use stable hashing (e.g. CRC32) if needed.

### Serialization (future)

- **State can be serialized**: define what must be saved/loaded for the feature.
- **IDs are stable**: entities referenced across frames have stable IDs (not object identity).

### Debuggability

- **Event loggable**: important outcomes can be logged as deterministic events (tick, type, entity ids, params).
- **Repro scenario**: there’s a minimal scenario described to validate correctness (seed + steps).

## Current project knobs

- `DETERMINISTIC_SIM=1`: fixed dt sim stepping.
- `SIM_SEED=<int>`: seeded gameplay RNG base.
- `SIM_TICK_HZ=<int>`: tick rate for deterministic stepping.


