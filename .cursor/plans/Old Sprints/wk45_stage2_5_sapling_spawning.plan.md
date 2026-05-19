---
name: wk45_stage2_5_sapling_spawning
overview: "Stage 2.5: NatureSystem spawns new saplings over time (no lumberjack yet). Saplings are non-blocking until growth>=0.75, but occupy TileType.TREE immediately; placing a building on a sapling removes it."
isProject: false
---

# WK45 Sprint Plan — Building & Nature (Stage 2.5: Sapling Spawning)

This sprint extends Stage 2 (dynamic tree growth) by adding **new sapling spawning over time** so growth is actually observable in a run, without starting the lumberjack economy.

## Player-facing goal
- Forests feel **alive**: new saplings appear over time and grow through stages (25% → 50% → 75% → 100%).
- Saplings don’t “trap” players early: they are **non-blocking** until they reach **75%** growth.

## Locked decisions (from Jaimie)
- **Spawn rate**: **Low** — **1 sapling every 30 seconds** (global rate), with a **cap of 50 trees** total.
- **Grid representation**: on spawn, set the tile to **`TileType.TREE` immediately**, but it remains **non-blocking until growth ≥ 0.75** (blocking rule already in `World.is_walkable/is_buildable` via `tree_growth_lookup`).
- **Building placement override**: if the player places a building on a sapling tile, the sapling is **removed** (tile becomes PATH/GRASS as appropriate under the building footprint).
- **Out of scope**: lumberjack economy, chopping, wood inventory, logs.

## Definition of Done
- NatureSystem spawns saplings deterministically at the configured cadence and respects a hard cap.
- Newly spawned saplings:
  - appear in `sim.trees` and in `snapshot.trees`
  - have `growth_percentage=0.25` and progress via the existing growth steps
  - mark the world tile as `TileType.TREE` at spawn time
  - are removed if a building is placed covering their tile
- Ursina shows new saplings (visible at 25%) and they scale over time (existing dynamic tree sync path).
- Gates PASS:
  - `python tools/qa_smoke.py --quick`
  - `python tools/validate_assets.py --report` (expected unchanged; errors=0)

## Implementation notes (do not deviate)

### Determinism
- Use the project’s deterministic RNG (`get_rng("nature")` or similar) for selecting spawn locations.
- Avoid iterating sets/dicts without sorting when picking candidate tiles.

### Spawn location rules (simple + safe MVP)
- Saplings may spawn only on tiles where:
  - base tile is `GRASS` (or currently tree-less)
  - tile is **buildable** for a 1×1 footprint (`World.is_buildable(tx, ty, 1, 1)` must be True)
  - tile is not inside any existing building footprint
- Prefer spawning **near existing forests** (within N tiles of any current Tree entity), but fall back to any valid grass tile if none are found.

### Removal on building placement
- When a building is placed (player build menu), remove any Tree entities whose `(grid_x, grid_y)` are inside the building footprint.
- Update the world tiles under the building footprint as the existing placement code already does (do not introduce a new tile rule beyond removing the Tree).

## Tests (minimum)
- `tests/test_nature_spawns_saplings.py` (new):
  - Initialize `SimEngine` headless, set a small map seed, advance sim by >30 seconds.
  - Assert at least 1 new Tree with growth 0.25 was added (if under cap).
  - Assert world tile at that position is `TileType.TREE`.
- Extend `tests/test_nature_growth.py` (if needed) to ensure spawned saplings still reach 0.75/1.0 at the expected time.
- `tests/test_tree_removed_on_building_place.py` (new or extension):
  - Spawn a sapling at a known tile.
  - Place a building covering that tile (through the same code path used by `Engine.place_building` or a direct SimEngine helper if available).
  - Assert the Tree entity is removed and the tile is no longer considered tree-owned for growth lookup.

## Manual smoke (Jaimie)
Run:

```powershell
python main.py --renderer ursina --no-llm
```

Do this (5–8 minutes):
1) Start a run and locate a forest edge.
2) Let the game run ~2 minutes.
3) Look for **new tiny trees** appearing and scaling up.
4) Try placing a 1×1 building on top of a visible sapling tile; confirm the sapling disappears and the building places cleanly.

Verify:
- No crashes.
- Saplings appear over time.
- Saplings do not block movement/building until they grow to 75% (hard to fully prove manually; “no early frustration” is the heuristic).

If it fails:
- Screenshot the sapling + tile.
- Copy/paste last ~30 lines of terminal output.

## Send list (parallelized, with ownership boundaries)
- **Agent 05 (HIGH)** — Nature spawning logic + tests:
  - Edit: `game/systems/nature.py`, `game/entities/nature.py`, add new tests.
  - Must not edit engine/renderer files.
- **Agent 03 (HIGH)** — Integration + removal-on-build:
  - Edit: `game/sim_engine.py`, `game/world.py`, and the building placement path (likely `game/engine.py place_building`) to remove saplings under footprints.
  - Ensure snapshot remains consistent and Ursina already sees new trees.
- **Agent 11 (LOW)** — Gates after integration:
  - `python tools/qa_smoke.py --quick`
  - `python tools/validate_assets.py --report`

