# WK86 Sprint Plan — Round B-3: world.py worldgen extraction

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the one-shot terrain/heightmap generation extracted from world.py into game/worldgen.py behind delegating wrappers; behavior byte-identical (digest `b73961…` unchanged).
**Predecessors:** WK66 (already moved World.render/render_fog out — L10 closed), WK68-85. **Roadmap:** Round B — audit's world.py split (world tiles/queries + worldgen + fog).

## 0. TL;DR
`game/world.py` (483 LOC) still mixes one-shot world GENERATION (`generate_terrain` ~74-167, `generate_heightmap` ~168-278; ~200 LOC) with the live tile-data/query/fog core. WK86 moves the generation into `game/worldgen.py` as functions taking the `World` (`world`), behind 1-line delegating wrappers on `World` (so `setup_initial_state`'s `world.generate_terrain()` / `world.generate_heightmap()` calls are unchanged). Pure-move, headless, **digest-guarded** (worldgen produces the seeded world that the 300-tick digest scenario runs on — any change to generation shifts the world → hero decisions → digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`). PM writes no code.

## 1. Scope
**IN:** create `game/worldgen.py`; move `generate_terrain` (world.py:74-167) and `generate_heightmap` (168-278) into it as `def generate_terrain(world) -> None:` / `def generate_heightmap(world) -> None:` (bodies VERBATIM, self.->world.). Leave 1-line delegating wrappers on `World`:
```python
def generate_terrain(self):
    from game.worldgen import generate_terrain as _gt
    return _gt(self)
```
If `flatten_building_footprints` (279-300) is part of generation (called during setup) and cleanly co-locates, optionally move it too — else leave it. Keep the wrappers' names (setup_initial_state + any tool/test calls `world.generate_terrain`/`generate_heightmap`).

**OUT:** the fog/FogOfWar state-machine extraction (reveal/update_visibility — more entangled, defer); the tile-query methods (stay on World); `_currently_visible` type fix; any behavior/generation change. **Move the generation bodies VERBATIM.**

## 2. Pattern (WK69/75-79, verbatim)
`worldgen.py` imports its leaf deps (config, the `terrain_height` module, `get_rng`/random, math, numpy if used) — read the generation bodies for what they reference; imports `World` only under TYPE_CHECKING; no cycle (wrapper imports worldgen lazily; worldgen never imports world at top). Preserve the EXACT generation (same RNG calls/order, same heightmap passes, same terrain_height writes) so the seeded world is byte-identical.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **825 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` (the seeded world is part of the deterministic scenario — generation drift breaks it).
- **D.** `qa_smoke.py --quick` green.
- **E.** `game/worldgen.py` exists with generate_terrain/generate_heightmap; `World.generate_terrain`/`generate_heightmap` are delegating wrappers (same names); world.py smaller (~483 → ~290); no import cycle.
- **F.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 03):** extract worldgen.py + wrappers. Verify suite + digest + qa_smoke.
- **W2 (Agent 11):** seam test (worldgen fns exist + wrappers delegate + a fresh World generates the same grid/heightmap as a snapshot) + full DoD.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A generation reference (terrain_height, a config const, an RNG call) breaks/reorders → world differs | Med | move VERBATIM; the digest is a strong guard (seeded world is in the scenario); preserve RNG call order exactly |
| Import cycle (worldgen ↔ world) | Med | TYPE_CHECKING-only World import; lazy wrapper import (proven WK69+) |
| heightmap dual-storage (World.heightmap + terrain_height module) handled wrong | Med | the generation writes BOTH today — keep both writes verbatim; W2 snapshots the generated grid+heightmap |

## 6. Success
World generation lives in `game/worldgen.py` behind delegating wrappers, the seeded world is byte-identical — proven by 825+ green tests, clean determinism guard, the unchanged `b73961…` digest, and a generated-world snapshot pin.

## 7. Kickoff
Roster: 03 (extraction W1), 11 (verify + world-snapshot pin W2), 09 (consult on terrain/heightmap). Order: 03 W1 → PM gate (suite + digest + qa_smoke) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE MOVE, keep wrapper names, TYPE_CHECKING-only World import, preserve RNG order; digest must stay byte-identical; NO screenshots; own log; DO NOT COMMIT.
Follow-ups: world.py fog/FogOfWar state-machine extraction + _currently_visible type fix; the BIG presentation splits (hud/ursina_renderer body/ursina_app/terrain_fog_collab); Move 9; config package; context_builder/direct_prompt_validator; ai/vocab.py + TaskRouter; clusters 3/4; Round E audit; zombie purge.
