# Sprint WK54 — Map Expansion, Zones & POI Foundation

> **Status:** DRAFT — awaiting Jaimie review
> **Version target:** v1.6.0 (after v1.5.6)
> **Theme:** Expand the world to 250×250, add biome zones, lay POI architecture foundation
> **Roadmap:** `.cursor/plans/pois_multisprint_roadmap.md` (Sprint 1 of 5)

---

## Goal

Transform the 150×150 flat-difficulty map into a 250×250 world with 3 distinct biome zones radiating from Castle Town. Lay the full POI entity architecture so POIs can be procedurally placed (with placeholder visuals — real prefabs arrive in WK55). Add a terrain flattening mechanism so buildings and future POIs don't clip through hills.

## Player-Facing Changes (What Jaimie Will See)

1. **Bigger world:** The map is now 250×250 tiles (was 150×150). ~2.8× more area to explore. Camera zoom range adjusted to compensate.
2. **Three biome zones:** Walking south from the castle, dense forest begins ~24 tiles out (Darkwood). North, rocky mountain terrain rises ~20 tiles out (Mountains). East, barren canyon formations start ~22 tiles out (Canyon Land). Each zone has distinct terrain feel via vegetation density, rock scatter, and elevation profile.
3. **Flat building foundations:** Buildings and lairs sit on flattened terrain — no more buildings perched awkwardly on hillsides or clipping through slopes.
4. **POI placeholders:** Small colored markers appear in zones where POIs will eventually render (shrine, cache, camp, etc.). These are development scaffolding — real models come in WK55.

## Current State (What Exists Today)

| Element | Current | Key Files |
|---------|---------|-----------|
| Map size | 150×150 tiles, 32px each | `config.py` (`MapConfig`) |
| Heightmap | 301×301 grid (2× sub-tile), Perlin noise 3 octaves | `game/graphics/terrain_height.py` |
| Terrain gen | Flat probability for trees/rocks, no zone concept | `game/world.py` |
| Fog of war | 150×150 texture, 3-state, shader-on-terrain | `game/graphics/ursina_terrain_fog_collab.py` |
| Buildings | Grid-placed, prefab JSON, BuildingFactory registry | `game/building_factory.py`, `config.py` |
| Lairs | 5 types, min 18 tiles from castle, ring placement | `game/entities/lair.py`, `game/systems/lairs.py` |
| Zones | None — no biome/region system | — |
| POIs | None — no POI entity type | — |
| Terrain flatten | None — entities sample heightmap as-is | — |

## Scope

### In scope
- Map expansion to 250×250 (heightmap 501×501, fog 250×250, config update)
- Zone system with 4 zones: Castle Town (safe center), Darkwood (south), Mountains (north), Canyon Land (east)
- Zone-influenced terrain generation: per-zone biases for tree density, rock density, elevation amplitude
- Terrain flattening: mechanism to flatten heightmap within any building/POI footprint + blending margin
- POI entity class (`PointOfInterest` extending `Building`) + `POIDefinition` dataclass
- 12 POI type definitions registered in config (`BUILDING_SIZES`, `BUILDING_COSTS`, `BUILDING_COLORS`)
- POI placement system: zone-aware, constraint-based, deterministic
- Renderer integration Option A: POIs invisible until hero within discovery range
- Camera zoom re-tune for the larger map
- Lair placement updated for 250×250 distances
- Pathfinding performance validation at new scale

### Out of scope (future sprints)
- POI prefab models (WK55 — Agent 15 builds, human revises)
- POI discovery fog-of-war interaction / silhouette rendering (WK55)
- Minimap POI icons (WK55)
- Compound prefab system for large POIs (WK56)
- POI interactions / LLM integration (WK56)
- Underground vertical stacking (WK57)
- Zone fog color tinting / ground color overlay (WK58)
- Boss encounters (WK58)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| 250×250 heightmap (501×501) too heavy for GPU | Frame drops, terrain mesh too large | Vertex count ~250K — well within budget. Benchmark in Wave 4. Fallback: reduce to 1× sub-tile (250×250 grid). |
| Pathfinding slow at 250×250 | A* search space 2.8× larger | Profile in Wave 4. Likely fine — A* is bounded by path length not map size. If slow, add hierarchical pathfinding later. |
| Zone terrain biases create ugly boundaries | Sharp visual transitions between zones | Use smooth blending at zone borders (cosine falloff over 8-10 tiles). No hard edges. |
| Terrain flattening creates visible "pancake" patches | Flat circles in otherwise hilly terrain look artificial | Blend flattened area into surrounding terrain over a 2-3 tile margin using cosine interpolation. |
| Fog texture at 250×250 causes GPU issues | Unlikely — 250×250 RGBA is 250KB | Trivial GPU load. No concern. |
| Lair placement breaks with new map size | Lairs too close or too far from castle | Adjust `LAIR_MIN_DISTANCE_FROM_CASTLE_TILES` proportionally. Test with 4 lairs. |

---

## Wave 0 — Design & Contracts (no game code)

**Agents:** 03 (Technical Director), 05 (Gameplay Systems Designer)

### Agent 03 — Map expansion + terrain flattening architecture

Design decisions to document before coding:

**0a. Heightmap scaling:**
- Current: 301×301 grid for 150×150 map (2× sub-tile resolution)
- New: 501×501 grid for 250×250 map (same 2× ratio)
- `generate_heightmap()` uses Perlin noise with fixed frequencies — these are resolution-independent, so the same frequencies produce the same terrain character at larger scale
- Castle flat radius (`TERRAIN_CASTLE_FLAT_RADIUS = 5`) stays the same — the castle area doesn't grow with the map

**0b. Terrain flattening mechanism:**
- Define a `flatten_footprint(heightmap, grid_x, grid_y, size_w, size_h, margin_tiles=2)` function
- Within the footprint: set all heightmap samples to the average height of the footprint center
- Within the margin ring: cosine-interpolate between the flattened height and the natural terrain height
- Called during world generation after heightmap is generated, for every building and lair footprint
- POIs will use the same mechanism when placed in later sprints
- Must be deterministic (same seed = same flattened terrain)

**0c. Zone data model:**
- Define the `Zone` dataclass with fields from the proposal
- 4 zones: Castle Town (ring 0-15 tiles, all angles), Darkwood (south sector, starts 24 tiles), Mountains (north sector, starts 20 tiles), Canyon Land (east sector, starts 22 tiles)
- Unzoned area between Castle Town outer ring and zone start distances = generic frontier (default terrain params)
- Zone resolution function: `get_zone(tile_x, tile_y) -> Zone | None`

**Output:** Architecture doc with data model, API signatures, heightmap scaling rationale, flattening algorithm pseudocode.

### Agent 05 — Zone definitions & POI placement constraints

**0d. Zone parameter tuning:**
- Define the 3 custom zones with concrete parameters:
  - **Darkwood (south):** `tree_density: 2.5`, `rock_density: 0.4`, `elevation_bias: 0.8` (moderate hills), sector 150°-210° (south), starts 24 tiles, extends to map edge
  - **Mountains (north):** `tree_density: 0.3`, `rock_density: 3.0`, `elevation_bias: 2.0` (high peaks), sector 330°-30° (north), starts 20 tiles, extends to map edge
  - **Canyon Land (east):** `tree_density: 0.2`, `rock_density: 2.5`, `elevation_bias: 1.5` (ridges + valleys), sector 60°-120° (east), starts 22 tiles, extends to map edge
  - **Castle Town:** `tree_density: 0.5`, `rock_density: 0.3`, `elevation_bias: 0.3` (flat), ring 0-15 tiles, all angles

**0e. POI placement constraints:**
- Min 8 tiles between any two POIs
- Min 5 tiles from any building or lair
- POI type must be in the zone's `poi_palette`
- Must be on walkable, buildable tiles (no water)
- Elevation preference per POI type (caves prefer high terrain, shrines prefer mid, camps prefer flat)
- Deterministic seeding via `get_rng("poi_placement")`

**0f. POI budget per zone:**
- Castle Town: 1-2 POIs (shrine, treasure cache)
- Darkwood: 4-5 POIs (hermit hut, druid grove, abandoned camp, treasure caches)
- Mountains: 4-5 POIs (cave entrance, mine entrance, wizard tower, shrine, treasure cache)
- Canyon Land: 4-5 POIs (graveyard, bandit fortress, abandoned camp, gravestone, demon portal)
- Unzoned frontier: 2-3 POIs (treasure caches, shrines)
- **Total: ~15-20 POIs per map**

**Output:** Zone parameter table, POI palette per zone, placement constraint spec, budget formula.

---

## Wave 1 — Map Expansion (250×250)

**Agents:** 03 (Technical Director)
**Depends on:** Wave 0

### Agent 03 — Config + heightmap + fog scaling

**1a. Config updates:**
- `MapConfig.width = 250`, `MapConfig.height = 250`
- `WindowConfig.prototype_version = "1.6.0"`
- `WindowConfig.game_title` updated to reflect new version
- Adjust `CameraConfig.zoom_min` — the larger map needs the camera to zoom out further. Current min is 0.5; try 0.3 for 250×250. Test what feels right.
- `TERRAIN_CASTLE_FLAT_RADIUS` stays at 5 (castle doesn't grow)

**1b. Heightmap scaling:**
- `terrain_height.py`: heightmap grid becomes 501×501 (2× sub-tile for 250×250)
- Perlin noise frequencies (`TERRAIN_HILL_FREQUENCY`, `TERRAIN_MOUNTAIN_FREQUENCY`, `TERRAIN_DETAIL_FREQUENCY`) stay the same — they're already resolution-independent
- `generate_heightmap()` updated to use `MAP.width * 2 + 1` and `MAP.height * 2 + 1` instead of hardcoded values (if not already)
- `get_terrain_height(world_x, world_z)` continues to work — it converts world coords to heightmap indices, which scales automatically

**1c. Fog texture scaling:**
- Fog texture scales from 150×150 to 250×250 — update any hardcoded dimensions
- No GPU concern — 250×250 RGBA = 250KB

**1d. World generation:**
- `game/world.py`: ensure map generation (tiles, water, trees, paths) uses `MAP.width`/`MAP.height` not hardcoded 150
- Water lake placement: adjust random position range for 250×250
- Path generation: cross-shaped paths from castle — extend to new map edges
- Tree cluster spawning: adjust count proportionally (2.8× more area = ~2.8× more clusters)
- Neutral building spawning: adjust for larger map

**1e. Lair placement:**
- `LAIR_MIN_DISTANCE_FROM_CASTLE_TILES = 18` — this is fine for 250×250, lairs won't be pushed too far out
- Verify 4 lairs still place correctly on the larger map
- Adjust lair max distance if needed (current code may use map edge as implicit max)

**1f. Camera re-tune:**
- Test default camera position on 250×250 — may need to pull back the starting orbit distance
- Verify camera near/far clip planes work at new zoom levels
- Verify atmospheric fog density is appropriate (currently tuned for 150×150 — may need to reduce density for 250×250 so distant terrain isn't fully fogged)

**Verification:**
- `python main.py --provider mock` — game boots on 250×250 map
- Camera can see the full map when zoomed out
- Terrain heightmap looks correct (no stretching, no seams)
- Fog of war works at new scale
- Lairs placed correctly
- Buildings and trees placed correctly
- No obvious perf regression at default zoom
- Capture before/after screenshots

---

## Wave 2 — Zone System & Zone-Influenced Terrain

**Agents:** 03 (Technical Director)
**Depends on:** Wave 0 (zone definitions), Wave 1 (250×250 map working)

### Agent 03 — Zone system + terrain biases

**2a. Zone data model (`game/world_zones.py` — new file):**
- `Zone` dataclass from Wave 0 design
- `ZONES` list with 4 zone definitions (Castle Town, Darkwood, Mountains, Canyon Land)
- `get_zone(tile_x, tile_y, castle_center) -> Zone | None` — returns the zone for a given tile, or None for unzoned frontier
- Zone resolution uses distance-from-castle (rings) + compass angle (sectors)
- Zone boundaries use smooth blending (the `get_zone_blend()` function returns a 0.0-1.0 weight for how deep into a zone a tile is — used for terrain bias interpolation)

**2b. Zone-influenced heightmap:**
- Modify `generate_heightmap()` to query zone for each heightmap sample
- Apply `elevation_bias` multiplier from the zone to the Perlin noise amplitude
- Mountains zone: 2.0× elevation (tall peaks, dramatic terrain)
- Canyon Land: 1.5× elevation (ridges and valleys)
- Darkwood: 0.8× elevation (moderate rolling hills)
- Castle Town: 0.3× elevation (nearly flat)
- Unzoned frontier: 1.0× (default)
- Smooth blend at zone borders (8-10 tile cosine falloff) so there are no sharp elevation discontinuities

**2c. Zone-influenced vegetation:**
- Modify tree cluster spawning in `game/world.py` to read `tree_density` from the zone
- Darkwood (south): 2.5× tree density — thick forest
- Mountains (north): 0.3× tree density — sparse, mostly rock
- Canyon Land (east): 0.2× tree density — barren
- Castle Town: 0.5× — light, maintained

**2d. Zone-influenced rock scatter:**
- Modify rock/stone scatter in terrain generation to read `rock_density` from the zone
- Mountains: 3.0× rock density — heavy boulder scatter
- Canyon Land: 2.5× — rock formations, cliff faces
- Darkwood: 0.4× — few rocks
- Castle Town: 0.3× — minimal

**Verification:**
- Walk south from castle: forest gets dense around 24 tiles out
- Walk north: terrain rises, rocks increase, trees thin out around 20 tiles
- Walk east: barren rocky canyons start around 22 tiles
- Zone transitions are smooth, not jarring
- Castle area is calm and flat
- Capture screenshots from each zone + transitions

---

## Wave 3 — Terrain Flattening

**Agents:** 03 (Technical Director)
**Depends on:** Wave 2 (heightmap with zone biases exists)

### Agent 03 — Footprint flattening system

**3a. Flattening function:**
- New function in `game/graphics/terrain_height.py`:
  ```
  flatten_footprint(heightmap, center_x, center_z, width_tiles, height_tiles, margin_tiles=2)
  ```
- Computes the average height at the footprint center (sample a few points, average them)
- Sets all heightmap samples within the footprint rectangle to that average height
- For the margin ring (2 tiles around the footprint): cosine-interpolate between flattened height and natural terrain height
- This creates a smooth "plateau" under each building with gentle slopes connecting to surrounding terrain

**3b. Integration with world generation:**
- After heightmap generation, iterate all placed buildings and lairs
- Call `flatten_footprint()` for each one
- Order matters: flatten castle first (largest, most important), then player buildings, then lairs
- Must happen BEFORE terrain mesh is built (flatten heightmap data, then mesh reads the flattened data)

**3c. Integration with future POIs:**
- The same function will be called for POIs when they're placed (WK55+)
- POI footprints are defined in `POIDefinition.size` — the flatten function reads that
- Large POIs (4×4, 5×5) get larger flattened plateaus — this is correct and desirable

**3d. Edge cases:**
- Buildings near water: flattened height should not go below `TERRAIN_WATER_LEVEL`
- Buildings near map edge: margin ring may extend past the heightmap — clamp indices
- Overlapping footprints (two buildings close together): later flatten overrides earlier — this is fine, the margin blending handles it gracefully

**Verification:**
- Place a building on a hillside — the terrain under it is flat, with smooth slopes blending into the hill
- Castle sits on its flat plateau as before (castle flat radius already exists, but now other buildings get the same treatment)
- No visible "pancake" artifacts — the margin blending is smooth enough
- Lairs on hills are properly flattened
- Capture close-up screenshots of buildings on slopes

---

## Wave 4 — POI Entity Architecture & Placement

**Agents:** 05 (Gameplay Systems), 03 (Technical Director — support)
**Depends on:** Wave 2 (zone system), Wave 3 (terrain flattening)

### Agent 05 — POI entity + placement system

**4a. POI entity class (`game/entities/poi.py` — new file):**
- `POIDefinition` dataclass with all fields from the proposal:
  - `poi_type`, `display_name`, `building_type`, `size`, `difficulty_tier`, `rarity`
  - `interaction_type` (combat/loot/shrine/knowledge/npc/dungeon/boss)
  - `is_persistent`, `vision_radius`, `description`
  - `zone_affinity` (list of zone_ids where this POI can spawn)
  - `elevation_preference` (high/mid/low/any)
- `PointOfInterest(Building)` class:
  - Inherits grid placement, prefab rendering from Building
  - Adds: `is_discovered`, `is_interacted`, `is_depleted`, `discoverer_hero_id`, `interaction_count`, `cooldown_remaining`
  - `is_poi = True` flag for renderer duck-typing
- `POI_DEFINITIONS` dict mapping `poi_type` → `POIDefinition` for all 12 types

**4b. Config registration:**
- Add all 12 POI types to `BUILDING_SIZES` in `config.py`:
  - `poi_shrine`: (1, 1), `poi_treasure_cache`: (1, 1), `poi_hermit_hut`: (1, 1), `poi_gravestone`: (1, 1)
  - `poi_abandoned_camp`: (2, 2), `poi_druid_grove`: (3, 3), `poi_wizard_tower`: (2, 2)
  - `poi_graveyard`: (4, 4), `poi_bandit_fortress`: (5, 5)
  - `poi_cave_entrance`: (2, 2), `poi_mine_entrance`: (2, 2), `poi_demon_portal`: (2, 2)
- Add to `BUILDING_COSTS` (all 0 — not player-purchasable)
- Add to `BUILDING_COLORS` (color per POI for 2D fallback / minimap placeholder)
- Add to `BUILDING_MAX_OCCUPANTS` where applicable (bandit fortress, wizard tower, cave/mine entrances)

**4c. BuildingFactory registration:**
- Register all 12 POI `building_type` strings in `BuildingFactory`
- For now, prefab JSONs don't exist — the factory should gracefully handle missing prefabs by rendering a placeholder (colored cube or simple marker)

**4d. POI placement system (`game/systems/poi_placement.py` — new file):**
- `POIPlacementSystem` class with:
  - `generate_pois(world, zones, buildings, lairs, rng) -> list[PointOfInterest]`
  - Per-zone: compute budget, select from zone's `poi_palette`, find valid spots
  - `_find_valid_spot()`: checks walkable terrain, spacing constraints, elevation preference, footprint validity
  - Constraint enforcement: min 8 tiles from other POIs, min 5 tiles from buildings/lairs
  - Deterministic via `rng` parameter
- Integration: called from `World.generate()` after buildings and lairs are placed
- Each placed POI gets `flatten_footprint()` called for its footprint

**4e. POI zone palettes:**
```
Castle Town:   [shrine, treasure_cache]
Darkwood:      [hermit_hut, druid_grove, abandoned_camp, treasure_cache, gravestone]
Mountains:     [cave_entrance, mine_entrance, wizard_tower, shrine, treasure_cache]
Canyon Land:   [graveyard, bandit_fortress, abandoned_camp, gravestone, demon_portal]
Frontier:      [shrine, treasure_cache]
```

**4f. Renderer integration (Option A — invisible until discovered):**
- In `ursina_renderer.py`: when iterating entities to render, skip any entity where `hasattr(entity, 'is_poi') and entity.is_poi and not entity.is_discovered`
- This makes POIs completely invisible until a hero walks within discovery range
- Discovery mechanic itself is deferred to WK55 — for now, all POIs start `is_discovered = False` (invisible)
- For development/testing: add a debug toggle that sets all POIs discovered so they render as placeholders

**Verification:**
- `python main.py --provider mock` — game boots with POIs placed
- Toggle debug mode to see POI placeholders — they appear in correct zones
- No POIs overlap buildings, lairs, or each other
- POIs sit on flattened terrain
- POI counts per zone match the budget spec
- `python tools/qa_smoke.py --quick` passes
- Capture overhead map screenshot showing POI distribution

---

## Wave 5 — Gates & Performance

**Agents:** 10 (Performance & Stability), 11 (QA)
**Depends on:** Wave 4

### Agent 10 — Performance benchmark at 250×250

- Compare FPS: 150×150 (previous) vs 250×250 (new) at default zoom and close zoom
- Heightmap 501×501 vertex count and terrain mesh draw call impact
- Pathfinding A* at 250×250: time a hero path from castle to map edge
- Memory footprint: heightmap array + fog texture + tile grid at new size
- Report: FPS numbers, frame time breakdown, memory delta, pass/fail
- If pathfinding is >2× slower, flag for future optimization (hierarchical pathfinding)

### Agent 11 — QA gates + screenshots

- `python tools/qa_smoke.py --quick` — must PASS
- `python tools/validate_assets.py --report` — must PASS (if exists)
- Verify: camera zoom works at new extremes (0.3 min)
- Verify: atmospheric fog looks correct at 250×250 (not over/under fogged)
- Verify: lairs still spawn and function correctly
- Verify: neutral buildings spawn in appropriate density for larger map
- Verify: hero pathfinding works across full map
- Capture comparison screenshots: 150×150 (before) vs 250×250 (after) at same camera angle
- Capture zone screenshots: Darkwood, Mountains, Canyon Land, Castle Town
- Capture terrain flattening screenshots: buildings on slopes

---

## Human Gates

1. **After Wave 2** — Jaimie walks each zone. Do the 3 biomes feel distinct? Are zone transitions smooth? Quick "looks good" / "adjust the tree density" before proceeding.
2. **After Wave 4** — Jaimie reviews POI distribution on the debug overlay. Are POIs in sensible locations? Is the density right? Do the placeholder markers appear where expected?

---

## Files Likely Touched

| File | Change Type | Wave |
|------|------------|------|
| `config.py` | Edit — map size, zoom, POI registrations | W1, W4 |
| `game/world.py` | Edit — map gen, vegetation, rock scatter, POI integration | W1, W2, W4 |
| `game/graphics/terrain_height.py` | Edit — heightmap scaling, zone elevation bias, flatten function | W1, W2, W3 |
| `game/graphics/ursina_terrain_fog_collab.py` | Edit — fog texture size | W1 |
| `game/graphics/ursina_renderer.py` | Edit — POI visibility gating | W4 |
| `game/graphics/ursina_app.py` | Edit — camera zoom, fog density | W1 |
| `game/world_zones.py` | **NEW** — zone dataclass, definitions, resolution | W2 |
| `game/entities/poi.py` | **NEW** — POI entity class, definitions | W4 |
| `game/systems/poi_placement.py` | **NEW** — placement system | W4 |
| `game/building_factory.py` | Edit — POI type registration | W4 |
| `game/systems/lairs.py` | Edit — adjust for 250×250 | W1 |

## Files NOT Touched (ownership boundaries)

- `ai/` — no LLM changes this sprint
- `game/ui/` — no UI changes this sprint
- `assets/prefabs/` — no new prefab JSONs this sprint (WK55)
- `tools/model_assembler_kenney.py` — no assembler changes
- `game/sim/` — no simulation contract changes
