# Fog of War — Visibility Radii and Rules (WK17)

This document defines visibility radii and rules for **auto-spawned buildings** and **Guards** so the engine can register them as vision sources and clear fog of war dynamically. Agent 03 implements the hooks in Round 2; this spec is the source of truth.

## Existing Contract (unchanged)

- **Revealers** are a list of `(world_x: float, world_y: float, radius_tiles: int)`.
- The engine calls `world.update_visibility(revealers, ...)` once per frame. Each revealer reveals a **circle** of tiles centered at `(world_x, world_y)` with radius `radius_tiles` (tile units).
- **Existing sources** (in `game/engine.py` `_update_fog_of_war()`):
  - **Castle**: `(castle.center_x, castle.center_y, 10)` — 10 tile radius.
  - **Living heroes**: `(hero.x, hero.y, 7)` — 7 tile radius per hero.

All new sources must follow the same contract: append `(world_x, world_y, radius_tiles)` to the same `revealers` list (or equivalent) before calling `update_visibility`.

---

## New Vision Sources

### 1. Auto-spawned (neutral) buildings

**Building types:** `house`, `farm`, `food_stand`.

- **Spawned by:** `NeutralBuildingSystem` (see `game/systems/neutral_buildings.py`). They are added to `engine.buildings` and are always created as fully constructed (`is_constructed = True`).
- **Position:** Use **world center** of the building: `building.center_x`, `building.center_y` (from `game/entities/buildings/base.py`). All buildings expose this.
- **When to include:** Include only if the building is **constructed** and **alive**:
  - `getattr(building, "is_constructed", True) == True`
  - `getattr(building, "hp", 1) > 0`
- **How to identify:** Building type string is `building.building_type`. Include only when `building_type in ("house", "farm", "food_stand")`. Optionally use `getattr(building, "is_neutral", False)` to match `NeutralBuilding` subclasses.

**Visibility radii (tile radius):**

| Building type  | Footprint (config) | Suggested radius (tiles) | Rationale |
|----------------|--------------------|--------------------------|-----------|
| `house`        | 1×1                | **3**                    | Small dwelling; modest sight. |
| `farm`         | 2×2                | **5**                    | Larger footprint; more open area. |
| `food_stand`   | 1×1                | **3**                    | Same as house. |

These are intentionally smaller than the castle (10) and heroes (7) so that player-built and hero presence remain the primary vision; neutral buildings just prevent their immediate area from being swallowed by fog.

---

### 2. Guards

**Entity:** `Guard` (see `game/entities/guard.py`). Spawned by guardhouses (and palace); they move and fight.

- **Position:** Use **current world position**: `guard.x`, `guard.y` (floats, in world/pixel coordinates). The engine must convert to grid for `update_visibility`; same as heroes, so use `(guard.x, guard.y, radius_tiles)`.
- **When to include:** Only if the guard is **alive**: `getattr(guard, "is_alive", True)` (which is `guard.hp > 0`). Do not add revealers for dead guards.
- **List:** Guards live in `engine.guards` (list of `Guard` instances).

**Visibility radius (tile radius):**

| Entity | Suggested radius (tiles) | Rationale |
|--------|---------------------------|-----------|
| Guard  | **6**                     | Defenders; slightly less than hero (7) but enough to clear fog around patrol/engagement. |

No need for different radii by state (IDLE / MOVING / ATTACKING); a single radius per living guard is sufficient and keeps implementation and performance simple.

---

## Implementation Notes for Agent 03

1. **Where to add revealers:** In `game/engine.py`, inside `_update_fog_of_war()`, after building the list for castle and heroes, append:
   - For each building in `self.buildings`: if type is `house` / `farm` / `food_stand`, constructed, and hp > 0, append `(building.center_x, building.center_y, radius)` with radius from the table above.
   - For each guard in `self.guards`: if `guard.is_alive`, append `(guard.x, guard.y, 6)`.

2. **Performance:** The existing `update_visibility` already iterates revealers and does a circle fill per revealer. Adding on the order of tens of buildings and a few guards is the same pattern as adding more heroes. No new systems required; only the construction of the `revealers` list changes.

3. **Determinism:** Building and guard positions are simulation state; no wall-clock or unseeded RNG is involved. Fog updates are already called every frame from the sim tick path.

4. **Constants:** Radii can be defined as named constants (e.g. in `config.py` or next to `CASTLE_VISION_TILES` / `HERO_VISION_TILES`) so tuning stays in one place. Suggested names: `NEUTRAL_BUILDING_VISION_RADIUS` (if using one value for all three) or per-type constants; `GUARD_VISION_TILES = 6`.

---

## Summary Table (copy-paste reference)

| Source           | Position              | Radius (tiles) | Include when                          |
|------------------|-----------------------|----------------|----------------------------------------|
| Castle           | center_x, center_y    | 10             | (existing)                             |
| Hero             | x, y                  | 7              | is_alive (existing)                    |
| house            | center_x, center_y    | 3              | is_constructed, hp > 0                 |
| farm             | center_x, center_y   | 5              | is_constructed, hp > 0                 |
| food_stand       | center_x, center_y   | 3              | is_constructed, hp > 0                 |
| Guard            | x, y                  | 6              | is_alive (hp > 0)                      |

---

*Authored by Agent 05 (GameplaySystemsDesigner) for WK17 Round 1. Agent 03 implements in Round 2.*
