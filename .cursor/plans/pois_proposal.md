# POIs Proposal: Points of Interest for the Kingdom Map

> **Purpose:** Detailed implementation proposal for adding Points of Interest to the Kingdom game.
> **Source ideas:** `.cursor/plans/future_hero_development_ideas.md` (Gemini brainstorm)
> **Status:** PROPOSAL — awaiting review

---

## Summary

The POIs proposal is written at .cursor/plans/pois_proposal.md. Here's a summary of what it covers:

  Map & Zones — A ring+sector zone system (Castle Town, Darkwood Forest, Bone Wastes, Thornmarsh, Ember Peaks,
  Frostmere, Sunken Depths) overlaid on the existing 150×150 map, with per-zone terrain biases for vegetation density,
  rock scatter, and elevation profile. Option to expand to 250×250 later if density requires it.

  17 POI types across four size classes:
  - Small (1×1-2×2): Shrine, Treasure Cache, Hermit Hut, Mysterious Well, Overgrown Gravestone — simple 3-8 piece
  prefabs using existing Kenney models
  - Medium (2×2-3×3): Abandoned Camp, Druid Grove, Ruined Outpost, Wizard's Tower, Windmill Ruin — 10-20 piece composed
  prefabs
  - Large (4×4-6×6): Overgrown Graveyard, Ancient Ruins, Bandit Fortress — 30-80 pieces, needs a new compound prefab
  system with mesh merging for performance
  - Special: Cave/Mine/Dragon Cave entrances, Demon Portal — gateway POIs that connect to underground content

  Underground/Mines — three approaches ranked by effort:
  1. Interior Overlay (Phase 1): Reuse the existing building interior system with dungeon-themed procedural layouts.
  Mines get a side-view resource gathering minigame. Zero renderer changes.
  2. Layer Culling (Phase 2): Add a layer property to entities, cull by active layer, separate underground terrain mesh.
   Heroes walk around underground in 3D.
  3. Vertical Stacking (Phase 3+): Physical underground geometry below Y=0 with cutaway rendering. Most impressive but
  most expensive.

  Key architectural pieces: POI entity class extending Building, compound prefab schema v0.6 with sub-prefab references,
   procedural placement system using zone palettes + rarity weights, fog-of-war discovery with silhouette rendering for
  undiscovered POIs, and LLM integration with personality-driven POI decisions.

  3-phase roadmap: Foundation (simple POIs + zones), Depth (underground + large prefabs), Polish (items/quests/bosses
  integration).

---

## Table of Contents

1. [Current State Assessment](#1-current-state-assessment)
2. [Map Expansion & Biome Zones](#2-map-expansion--biome-zones)
3. [POI Entity Architecture](#3-poi-entity-architecture)
4. [POI Catalog: Per-Type Implementation](#4-poi-catalog-per-type-implementation)
5. [Underground & Mines: Three Approaches](#5-underground--mines-three-approaches)
6. [Large Prefab Composition (50-100 Model Clusters)](#6-large-prefab-composition-50-100-model-clusters)
7. [Procedural Placement System](#7-procedural-placement-system)
8. [Fog of War & Discovery](#8-fog-of-war--discovery)
9. [LLM Hero Integration](#9-llm-hero-integration)
10. [Phased Delivery Roadmap](#10-phased-delivery-roadmap)

---

## 1. Current State Assessment

### What We Have

| System | State | Key Files |
|--------|-------|-----------|
| **Map** | 150×150 tiles, 32px each (4800×4800 world units). Castle at center. | `game/world.py`, `config.py` |
| **Terrain** | Perlin noise heightmap, 2× sub-tile resolution (301×301 grid). Hills, ridges, detail octaves. Castle-flat plateau. Water clamping. | `game/graphics/terrain_height.py`, `game/world.py` |
| **Fog of War** | 3-state (UNSEEN/SEEN/VISIBLE). Shader-based on terrain mesh. Circular reveal from heroes (7 tiles), castle (10), buildings (3-5). | `game/world.py`, `game/graphics/ursina_terrain_fog_collab.py` |
| **Lairs** | 5 types (GoblinCamp, WolfDen, SkeletonCrypt, SpiderNest, BanditCamp). Extend `Building`. Min 18 tiles from castle. 4 initial count. | `game/entities/lair.py`, `game/systems/lairs.py` |
| **Buildings** | Grid-placed, prefab JSON rendering. `BuildingFactory` registry. 53 prefab JSONs. | `game/building_factory.py`, `assets/prefabs/buildings/` |
| **Renderer** | Ursina 3D (Panda3D). Perspective camera 42° FOV. Exponential fog. Single Y-plane with heightmap displacement. | `game/graphics/ursina_app.py`, `game/graphics/ursina_renderer.py` |
| **Assets** | 787 Kenney GLB models across 6 packs (Graveyard, Fantasy Town, Nature Kit, Retro Fantasy, Survival, Blocky Characters). | `assets/models/Models/GLB format/` |
| **Prefab Tooling** | Model Assembler — interactive kitbash tool. JSON schema v0.5. | `tools/model_assembler_kenney.py` |
| **Interiors** | 2D Pygame overlay modals (not in-world 3D). State machine: OVERVIEW/INTERIOR/QUEST/HERO_FOCUS. | `game/ui/building_interior_overlay.py` |
| **Instancing** | Optional hardware instancing for units (dual buffer). Up to 1024 outside + 128 inside instances. | `game/graphics/instanced_unit_renderer.py` |

### What We Don't Have

- No zone/biome/region system — map is a flat difficulty space
- No underground or layer concept — single Y-plane only
- No POI entity type distinct from buildings/lairs
- No item/loot model — heroes have no inventory
- No multi-model "area prefab" concept — prefabs are per-building, not per-region
- No procedural POI placement system (lairs use simple ring/distance constraints)

---

## 2. Map Expansion & Biome Zones

### 2.1 Map Size Decision

The current 150×150 map is roughly 35 screens across at default zoom. For a meaningful biome system with POI density, we have two options:

**Option A: Keep 150×150, add zones** (Recommended for Phase 1)
- Divide the existing map into concentric rings + compass sectors
- ~5-7 zones fit comfortably. Town center is safe; edges are dangerous
- No engine changes. Heightmap, fog, pathfinding all work as-is
- POIs compete with lairs/buildings for space, which naturally limits clutter
- Risk: outer zones feel cramped if there are many POI types

**Option B: Expand to 250×250 or 300×300** (Phase 2+)
- Heightmap scales linearly (601×601 or 501×501 grid — still <400K vertices)
- Fog texture scales to 250×250 or 300×300 — trivial GPU load
- Perlin noise frequencies stay the same; more terrain variety emerges naturally
- More room for large POI areas (ruins spanning 8×8 tiles, mine complexes)
- Requires: update `MAP.width`/`MAP.height` in config, re-tune camera zoom range, test pathfinding perf at scale, adjust lair min-distance and neutral building radii
- Risk: empty "nothing" space between POIs unless fill density also scales

**Recommendation:** Start with Option A. The 150×150 map has plenty of unexplored frontier beyond the lair ring (18+ tiles from castle). Once we see how POI density feels, expand in a later sprint if needed. The architecture should assume map size is variable.

### 2.2 Zone System Architecture

Divide the map into named regions using two axes: **distance from castle** (rings) and **compass direction** (sectors). This gives natural difficulty gradient + thematic variety.

```
                        N
                   ┌─────────┐
                  /  FROSTMERE \
                /   (Ice/North)  \
        NW    /─────────────────────\    NE
            /   DARKWOOD    │ BONE   \
          /    (Forest/NW)  │WASTES   \
    W   /───────────────────┼──(NE)────\   E
        │     CASTLE TOWN   │          │
        │    ◆ (Safe Zone)  │          │
        \───────────────────┼──────────/
          \  THORNMARSH   │ EMBER    /
            \ (Swamp/SW)  │PEAKS   /
        SW    \───────────│(SE)──/    SE
                \  SUNKEN    /
                 \ DEPTHS  /
                  └───────┘
                      S
```

#### Zone Data Model

New file: `game/world_zones.py`

```python
@dataclass
class Zone:
    name: str                    # "Darkwood Forest"
    zone_id: str                 # "darkwood"
    difficulty_tier: int         # 1 (safe) to 5 (deadly)
    min_distance: float          # inner ring radius (tiles from castle)
    max_distance: float          # outer ring radius
    angle_start: float           # compass sector start (degrees, 0=N)
    angle_end: float             # compass sector end
    enemy_palette: list[str]     # ["wolf", "spider", "treant"]
    poi_palette: list[str]       # ["hidden_grove", "ancient_tree", "druid_shrine"]
    terrain_bias: dict           # {"tree_density": 1.5, "rock_density": 0.8}
    description: str             # LLM context flavor text
    ambient_color_tint: tuple    # optional per-zone fog/color overlay hint
```

#### Zone Resolution

```python
def get_zone(world_x: float, world_y: float, castle_center: tuple) -> Zone:
    dx = world_x - castle_center[0]
    dy = world_y - castle_center[1]
    distance = math.hypot(dx, dy) / TILE_SIZE  # in tiles
    angle = math.degrees(math.atan2(dx, -dy)) % 360  # 0=N, clockwise
    # Match against zone ring + sector definitions
    ...
```

#### Zone Definitions (Config-Driven)

```python
ZONES = [
    # Ring 1: Safe zone (0-12 tiles)
    Zone("Castle Town", "castle_town", difficulty_tier=1,
         min_distance=0, max_distance=12, angle_start=0, angle_end=360,
         enemy_palette=[], poi_palette=["town_well", "market_stall"],
         terrain_bias={"tree_density": 0.3}, 
         description="The heart of the kingdom. Stone paths radiate from the castle."),

    # Ring 2: Frontier (12-35 tiles), split by compass
    Zone("Darkwood Forest", "darkwood", difficulty_tier=2,
         min_distance=12, max_distance=35, angle_start=270, angle_end=360,
         enemy_palette=["wolf", "spider"], poi_palette=["hidden_grove", "druid_shrine", "abandoned_camp"],
         terrain_bias={"tree_density": 2.0, "rock_density": 0.5},
         description="Dense forest. The trees grow thick and wolves hunt in packs."),

    Zone("Bone Wastes", "bone_wastes", difficulty_tier=2,
         min_distance=12, max_distance=35, angle_start=0, angle_end=90,
         enemy_palette=["skeleton", "bandit"], poi_palette=["graveyard", "crypt_entrance", "ruined_outpost"],
         terrain_bias={"tree_density": 0.3, "rock_density": 1.5},
         description="Barren rocky ground littered with old bones. The dead don't rest here."),

    # Ring 3: Dangerous frontier (35-55 tiles)
    Zone("Thornmarsh", "thornmarsh", difficulty_tier=3,
         min_distance=35, max_distance=55, angle_start=180, angle_end=270,
         enemy_palette=["goblin", "spider", "bandit"], poi_palette=["cursed_shrine", "sunken_ruin", "witch_hut"],
         terrain_bias={"tree_density": 0.8, "water_density": 2.0},
         description="Murky swampland where the ground squelches underfoot."),

    Zone("Ember Peaks", "ember_peaks", difficulty_tier=3,
         min_distance=35, max_distance=55, angle_start=90, angle_end=180,
         enemy_palette=["skeleton", "goblin"], poi_palette=["mine_entrance", "dragon_cave", "dwarven_ruin"],
         terrain_bias={"tree_density": 0.2, "rock_density": 3.0, "elevation_bias": 1.5},
         description="Jagged mountain terrain. Ancient mines dot the cliffs."),

    # Ring 4: Edge of the world (55-75 tiles)
    Zone("Frostmere", "frostmere", difficulty_tier=4,
         min_distance=55, max_distance=75, angle_start=315, angle_end=45,
         enemy_palette=["skeleton", "wolf"], poi_palette=["frozen_shrine", "ice_cave", "hermit_tower"],
         terrain_bias={"tree_density": 0.5, "elevation_bias": 2.0},
         description="A frozen expanse where the wind cuts like a blade."),

    Zone("Sunken Depths", "sunken_depths", difficulty_tier=5,
         min_distance=55, max_distance=75, angle_start=135, angle_end=225,
         enemy_palette=["skeleton", "goblin", "spider", "bandit"],
         poi_palette=["demon_portal", "ancient_vault", "boss_arena"],
         terrain_bias={"rock_density": 2.0, "elevation_bias": -1.0},
         description="A cursed lowland where darkness pools. Only the strongest survive."),
]
```

### 2.3 Zone-Influenced Terrain Generation

The existing `generate_terrain()` uses flat probability for tree placement. With zones, we can bias Perlin noise parameters per-zone:

- **Darkwood**: triple tree cluster density, reduce rock spawns
- **Ember Peaks**: boost elevation amplitude by 1.5×, heavy rock scatter, minimal trees
- **Thornmarsh**: lower elevation (valleys), increase water tile chance near zone center
- **Frostmere**: high elevation, sparse pine trees, potential snow texture tint
- **Bone Wastes**: minimal vegetation, scattered rock formations, flat terrain

This requires modifying `World.generate_terrain()` to look up the zone for each tile and apply `terrain_bias` multipliers to the existing noise generators. The heightmap generation in `generate_heightmap()` can similarly read `elevation_bias` per zone.

### 2.4 Visual Zone Distinction

Even without unique textures per biome (which would be a major art undertaking), we can create zone feel through:

1. **Vegetation density** — zones control how many trees/bushes spawn (already feasible via tree cluster params)
2. **Rock density** — scatter more Nature Kit rock models in mountainous zones
3. **Elevation profile** — Perlin noise amplitude multiplier per zone
4. **Fog color tinting** — subtle per-zone atmospheric fog color shift (e.g., greenish in Darkwood, blueish in Frostmere, reddish in Ember Peaks). This is a single `fog.setColor()` lerp based on camera position
5. **Ground color** — the terrain shader could sample a zone-tinted color map overlay (low-effort: multiply terrain albedo by a subtle zone color)

---

## 3. POI Entity Architecture

### 3.1 POI as a Building Subclass

POIs share enough DNA with buildings and lairs that the simplest architecture is:

```
Building (base.py)
├── MonsterLair (lair.py)          — hostile, spawns enemies
├── NeutralBuilding                — passive, generates tax
│   ├── House, Farm, FoodStand
├── PlayerBuilding                 — player-placed functional buildings
│   ├── Inn, Blacksmith, Guilds...
└── PointOfInterest [NEW]          — discoverable map features
    ├── CombatPOI                  — triggers fight on interaction
    ├── LootPOI                    — contains treasure, depletes
    ├── ShrinePOI                  — grants buff, repeatable
    ├── KnowledgePOI               — reveals map/lore
    ├── NPCEncounterPOI            — hermit, merchant, quest-giver
    ├── DungeonEntrancePOI         — gateway to underground/instanced content
    └── BossArenaPOI               — named boss encounter location
```

### 3.2 PointOfInterest Base Class

New file: `game/entities/poi.py`

```python
@dataclass
class POIDefinition:
    poi_type: str              # "hidden_grove", "abandoned_mine", etc.
    display_name: str          # "Hidden Grove"
    building_type: str         # maps to prefab system: "poi_hidden_grove"
    size: tuple[int, int]      # footprint in tiles
    difficulty_tier: int       # 1-5, used for level recommendations
    rarity: str                # "common", "uncommon", "rare", "legendary"
    interaction_type: str      # "combat", "loot", "shrine", "knowledge", "npc", "dungeon", "boss"
    is_persistent: bool        # True = stays after interaction, False = one-time
    vision_radius: int         # how far this POI reveals fog (0 for hidden)
    description: str           # LLM flavor text

class PointOfInterest(Building):
    def __init__(self, grid_x, grid_y, definition: POIDefinition):
        super().__init__(grid_x, grid_y, definition.building_type, definition.size)
        self.poi_def = definition
        self.is_discovered = False       # hidden until hero explores nearby
        self.is_interacted = False       # has any hero triggered this?
        self.is_depleted = False         # for one-time POIs (loot caches)
        self.discoverer_hero_id = None   # first hero to find it
        self.interaction_count = 0
        self.cooldown_remaining = 0.0    # for repeatable POIs (shrines)
        self.is_poi = True               # duck-type flag for renderer
```

### 3.3 Renderer Integration

The existing prefab pipeline auto-resolves by `building_type`. A POI with `building_type="poi_hidden_grove"` will look for `assets/prefabs/buildings/poi_hidden_grove_v1.json`. Undiscovered POIs are hidden by the fog of war system (they exist in UNSEEN tiles). Once discovered (hero walks within fog-reveal range), the prefab renders normally.

For undiscovered-but-SEEN tiles, we have a design choice:
- **Option A**: POI is invisible until a hero is within discovery range (even if terrain is SEEN)
- **Option B**: POI is visible as a mysterious silhouette/shimmer in SEEN tiles, fully revealed when VISIBLE

Option B is more interesting gameplay. Implementation: render the POI prefab with a dark semi-transparent shader when `is_discovered=False` and tile state is SEEN. Switch to full render when discovered.

### 3.4 Registration in BuildingFactory

Add all POI types to `BUILDING_REGISTRY` in `building_factory.py` and `BUILDING_SIZES` in `config.py`. This is the same pattern used for lairs — no new infrastructure needed.

---

## 4. POI Catalog: Per-Type Implementation

### 4.1 Small POIs (1×1 to 2×2 tiles) — Single Prefab

These are simple: one prefab JSON, 3-8 model pieces, assembled in the Model Assembler.

#### Shrine / Altar
- **Size:** 1×1
- **Models:** `altar-stone-graveyard.glb` (centerpiece) + `pillar-small-graveyard.glb` (×2 flanking) + `candle-graveyard.glb` (×4 around base) + `lantern-glass-graveyard.glb` (hanging)
- **Interaction:** Hero prays → receives a temporary buff (heal, strength, speed). Cooldown 5 minutes.
- **Rarity:** Common (1 per zone)
- **Difficulty:** 1 (safe)

#### Treasure Cache
- **Size:** 1×1
- **Models:** `box-large.glb` + `barrel.glb` (×2) + `resource-wood.glb` (scattered) + optional `lantern-candle-graveyard.glb`
- **Interaction:** Hero opens → receives gold + possible item. One-time, then depleted (model swaps to open/empty variant or fades).
- **Rarity:** Common (2-3 per zone)
- **Difficulty:** 1

#### Hermit Hut
- **Size:** 1×1 or 2×1
- **Models:** Small `tent-*.glb` from Survival Kit + `campfire.glb` + `tool-*.glb` (axe, pickaxe scattered) + a tree nearby
- **Interaction:** NPC encounter — hermit offers a quest hook, trade, or cryptic lore. Persistent.
- **Rarity:** Uncommon (1 per 2 zones)
- **Difficulty:** 1

#### Mysterious Well
- **Size:** 1×1
- **Models:** `fountain-round-fantasy-town.glb` re-textured with dark stone + `rock_smallA.glb` ring
- **Interaction:** Hero looks in → random outcome (gold, monster, vision reveal of nearby POI, curse). One-time.
- **Rarity:** Uncommon
- **Difficulty:** 2

#### Overgrown Gravestone
- **Size:** 1×1
- **Models:** `gravestone-graveyard.glb` or `gravestone-broken-graveyard.glb` + `plant_bush*.glb` overgrowth + `flower_*.glb`
- **Interaction:** Knowledge POI — hero reads inscription, reveals lore or nearby hidden POI location.
- **Rarity:** Common
- **Difficulty:** 1

### 4.2 Medium POIs (2×2 to 3×3 tiles) — Composed Prefab

#### Abandoned Camp
- **Size:** 2×2
- **Models:** `tent-*.glb` (×2, different sizes) + `campfire.glb` (extinguished variant via dark texture) + `barrel.glb` + `box.glb` + `fence-*.glb` (partial perimeter) + `tool-*.glb` scattered
- **Interaction:** Loot + possible ambush (50% chance combat encounter spawns bandits). Can be "claimed" as a rest stop after clearing.
- **Rarity:** Common
- **Difficulty:** 2

#### Druid Grove / Hidden Grove
- **Size:** 3×3
- **Models:** 4-6 `tree_oak*.glb` arranged in a circle + `statue_ring.glb` center + `mushroom_*.glb` (×8-10 scattered) + `flower_*.glb` + `plant_*.glb` dense undergrowth
- **Interaction:** Shrine-like healing + nature lore. Persistent. Rangers get extra benefits.
- **Rarity:** Uncommon
- **Difficulty:** 1

#### Ruined Outpost
- **Size:** 3×3
- **Models:** `wall-broken-fantasy-town.glb` (×4-6 forming partial walls) + `wall-fortified-*.glb` (1-2 intact sections) + `debris-*.glb` + `gravestone-debris-graveyard.glb` + `barrel.glb` + `lantern-*.glb` (broken)
- **Interaction:** Combat encounter (bandits/skeletons) + loot cache. Can become a "cleared outpost" that provides permanent vision radius in that area.
- **Rarity:** Uncommon
- **Difficulty:** 2-3

#### Wizard's Tower
- **Size:** 2×2
- **Models:** `tower-base.glb` + `tower.glb` (mid section) + `tower-top.glb` + `battlement.glb` (×4 corners) + `pillar-stone-fantasy-town.glb` (×2 flanking entrance) + `lantern-fantasy-town.glb` (×2)
- **Interaction:** Knowledge POI + possible quest-giver NPC. Wizards get extra benefits. Persistent.
- **Rarity:** Rare (1 per map)
- **Difficulty:** 3

#### Windmill / Watermill Ruin
- **Size:** 2×2
- **Models:** `windmill-fantasy-town.glb` or `watermill-fantasy-town.glb` + `debris-wood-graveyard.glb` scattered + `fence-*.glb` (broken)
- **Interaction:** Can be repaired (quest objective) to become a functional economic building. One-time transform.
- **Rarity:** Rare
- **Difficulty:** 1

### 4.3 Large POIs (4×4 to 6×6 tiles) — Multi-Section Prefab

These require the "large prefab" system described in [Section 6](#6-large-prefab-composition-50-100-model-clusters).

#### Overgrown Graveyard
- **Size:** 4×4
- **Models (30-50 pieces):** `gravestone-*.glb` (×12-15, mix of broken/intact) + `cross-*.glb` (×4-6) + `iron-fence-*.glb` (perimeter, ×12-16) + `iron-fence-gate-*.glb` (×1 entrance) + `crypt-small-graveyard.glb` (centerpiece) + `tree_*.glb` (×2-3 overgrown) + `plant_bush*.glb` (×6-8) + `lantern-*.glb` (×4 at fence posts) + `rocks-graveyard.glb` (×3-4)
- **Interaction:** Multi-phase combat encounter (skeletons rise in waves). Boss variant: named skeleton lord in the central crypt. High-tier loot.
- **Rarity:** Rare
- **Difficulty:** 3-4

#### Ancient Ruins
- **Size:** 5×5
- **Models (40-60 pieces):** `column-large-graveyard.glb` (×6-8 in rows, some toppled) + `pillar-obelisk-graveyard.glb` (×2 flanking entrance) + `stone-wall-damaged-graveyard.glb` (×8-10 forming partial walls) + `altar-stone-graveyard.glb` (center) + `statue_column.glb` (×2) + `debris-graveyard.glb` (×6-8 scattered) + `ground_pathRocks.glb` (floor tiles) + `urn-*.glb` (×4) + `candle-*.glb` (×6) + `plant_*.glb` (×8-10 overgrowth)
- **Interaction:** Knowledge + loot + possible quest location. Multi-phase if used as quest destination. Contains hidden lore that reveals other POI locations.
- **Rarity:** Rare (1-2 per map)
- **Difficulty:** 3-4

#### Bandit Fortress
- **Size:** 5×5 to 6×6
- **Models (50-80 pieces):** `wall-fortified-*.glb` (×20-25 forming walls) + `tower-base.glb` + `tower.glb` (corner towers ×2) + `battlement-*.glb` (×8-10 atop walls) + `wall-fortified-gate.glb` (×1) + `tent-*.glb` (×3-4 inside) + `campfire.glb` (×2) + `barrel.glb` (×6) + `box.glb` (×4) + `stall-*.glb` (×2 inside) + `fence-*.glb` (outer perimeter)
- **Interaction:** Major combat POI. Named boss (Bandit Lord). Multi-phase assault quest: scout → infiltrate/assault → defeat boss → loot armory. Can be "conquered" and turned into a player outpost.
- **Rarity:** Legendary (1 per map)
- **Difficulty:** 4-5

### 4.4 Special POIs (Unique Mechanics)

#### Cave / Crypt Entrance (Gateway POI)
- **Size:** 2×2
- **Models:** `cliff_cave_rock.glb` or `cliff_cave_stone.glb` (cave mouth) + `cliff_block_rock.glb` (×2-4 framing) + `rock_largeA.glb` (×2-3 scatter) + `lantern-glass-graveyard.glb` (×2 flanking) + `iron-fence-gate-graveyard.glb` (gate across mouth, optional)
- **Interaction:** Dungeon entrance — see [Section 5: Underground](#5-underground--mines-three-approaches) for what happens when a hero "enters"
- **Rarity:** Uncommon-Rare
- **Difficulty:** 3-5 (depends on what's inside)

#### Mine Entrance
- **Size:** 2×2
- **Models:** `cliff_cave_stone.glb` (mine shaft opening) + `cliff_block_stone.glb` (×2 supports) + `tool-pickaxe.glb` (leaning against wall) + `barrel.glb` (×2 ore barrels) + `box.glb` (×2 supply crates) + `lantern-candle-graveyard.glb` (×2 inside entrance) + `resource-wood.glb` (support beams, rotated horizontal)
- **Interaction:** Dungeon entrance with resource gathering. See [Section 5](#5-underground--mines-three-approaches).
- **Rarity:** Uncommon (1-2 in mountain zones)
- **Difficulty:** 2-4

#### Dragon Cave
- **Size:** 3×3
- **Models:** `cliff_cave_rock.glb` (large opening) + `cliff_block_rock.glb` (×6-8 dramatic framing) + `rock_tallA-E.glb` (×4-6 scattered) + `fire-basket-graveyard.glb` (×2 smoldering at entrance) + `debris-graveyard.glb` (×3 bone scatter) + `statue_obelisk.glb` (×1 warning marker)
- **Interaction:** Boss arena POI. Named dragon boss. Requires high-level hero or party. Legendary loot. One-time defeat, but cave remains as a knowledge POI after.
- **Rarity:** Legendary (1 per map, always in highest-difficulty zone)
- **Difficulty:** 5

#### Demon Portal
- **Size:** 2×2
- **Models:** `pillar-large-graveyard.glb` (×4 in square formation) + `column-large-graveyard.glb` (×2 inner) + `candle-multiple-graveyard.glb` (×8 circle on ground) + `fire-basket-graveyard.glb` (×4 at pillars, glowing) + `altar-stone-graveyard.glb` (center)
- **Interaction:** Endgame POI. Activates after all other boss POIs are cleared. Spawns escalating waves. Final boss encounter. World event trigger.
- **Rarity:** Legendary (1 per map, in Sunken Depths)
- **Difficulty:** 5+

---

## 5. Underground & Mines: Three Approaches

The biggest architectural question. The current renderer has a single Y-plane with heightmap displacement. True underground requires a layer concept. Here are three approaches ranked by feasibility:

### 5.1 Approach A: Interior Overlay (Lowest Effort, Recommended for Phase 1)

**Concept:** Underground areas use the existing interior overlay system. When a hero "enters" a cave/mine, the game opens a 2D interior view (like entering a building) but with a dungeon-themed procedural layout instead of a building interior.

**Implementation:**
- Extend `BuildingInteriorOverlay` with a `DungeonInteriorOverlay` variant
- Procedurally generate a dungeon layout (grid of rooms + corridors) as a 2D Pygame surface
- Hero navigates the dungeon in the overlay view (could be auto-narrated by LLM or have simple click-to-move)
- Combat, loot, and boss encounters happen within the overlay
- When hero exits, they reappear at the entrance POI on the surface map

**Pros:**
- Zero renderer changes. Uses existing overlay infrastructure
- Dungeon content is isolated — can't break the surface map
- Dungeon layouts can be elaborate without worrying about 3D rendering performance
- LLM narration works perfectly for "text adventure in a dungeon" feel

**Cons:**
- Not visually immersive — you don't see the hero walking underground in 3D
- Breaks the continuous world feel (modal transition)
- Can't have multiple heroes in the same dungeon simultaneously (or need special handling)

**When to use:** Caves, crypts, mine interiors — any enclosed underground space where you don't need to see the surface simultaneously.

### 5.2 Approach B: Layer Culling (Medium Effort, Recommended for Phase 2)

**Concept:** Add a `layer` property to all entities. Layer 0 = surface, Layer -1 = underground. The camera has an `active_layer` state. When viewing underground, surface entities are hidden (culled) and underground entities/terrain are shown. A transition animation (fade to black, camera descend) plays when switching layers.

**Implementation:**
- Add `layer: int = 0` to all entities (buildings, POIs, units)
- Underground terrain: generate a second heightmap for layer -1 (flat cave ceiling, rocky floor) or use a separate smaller tile grid per dungeon
- Visibility gating: in `ursina_renderer.py`, skip entities where `entity.layer != camera.active_layer`
- Underground fog of war: separate `visibility_underground[][]` grid (or per-dungeon)
- Camera transition: animate camera Y downward + fade, then show underground layer
- Dungeon entrance POI links surface layer to underground layer at specific grid coordinates

**Pros:**
- Heroes visually walk around underground in the same 3D engine
- Can have multiple heroes in the same underground area
- Continuous world feel — you're just looking at a different layer

**Cons:**
- Significant renderer work (conditional culling, layer-aware fog, second terrain mesh)
- Dungeon terrain authoring is harder (need underground-specific prefabs/tiles)
- Camera management complexity (preventing accidental layer switches, UI for layer indicator)
- Pathfinding needs layer awareness

**When to use:** If underground exploration becomes a major gameplay feature and the overlay approach feels too limiting.

### 5.3 Approach C: Vertical Stacking (High Effort, Phase 3+)

**Concept:** Underground terrain is rendered physically below the surface terrain in 3D space. The camera can orbit to look "through" a cutaway of the surface to see underground. Think Dwarf Fortress or RimWorld 3D mods.

**Implementation:**
- Surface terrain at Y=0 to Y=TERRAIN_HEIGHT_SCALE
- Underground terrain at Y=-UNDERGROUND_DEPTH to Y=0
- Cave entrance POIs create "holes" in the surface terrain mesh (remove vertices in a radius around the entrance, revealing the underground below)
- Camera can tilt to look into the hole, or a transparency shader makes surface semi-transparent near the cave entrance
- Underground has its own lighting (darker, torchlit)

**Pros:**
- Most visually impressive — continuous 3D world with depth
- Natural cave entrance rendering (hole in the ground)
- Heroes visibly descend into caves

**Cons:**
- Major terrain mesh surgery (dynamic vertex removal for cave holes)
- Complex camera management (clipping through surface when looking underground)
- Lighting complexity (underground needs different ambient + point lights from torches)
- Could be disorienting without careful UX
- Performance: double the terrain vertices when both layers visible

**When to use:** If the game evolves toward a fully explorable 3D world where underground is a core pillar, not just a side feature.

### 5.4 Mine-Specific Recommendation

Mines are the most interesting underground concept because they combine exploration, resource gathering, and combat. For Phase 1:

**Use Approach A (Interior Overlay) with a mine-specific twist:**

1. **Surface:** Mine Entrance POI (2×2, cave mouth with mining props)
2. **Entry:** Hero walks to entrance → modal opens showing mine cross-section view
3. **Mine Interior:** Procedural 2D side-view layout (think Terraria-lite):
   - Grid of chambers connected by tunnels
   - Ore deposits visible on walls (gold, iron, gems)
   - Monsters lurking in deep chambers
   - Hero auto-narrates exploration via LLM: "I found a gold vein! But something is moving deeper in the tunnels..."
4. **Resource Loop:** Hero mines ore → carries it to surface → sells at Marketplace → gold for kingdom
5. **Depth Mechanic:** Deeper chambers = richer ore + harder monsters. Heroes decide how deep to push.

This gives mines their own unique feel without requiring 3D underground rendering. The LLM narration makes it immersive despite being a 2D overlay.

---

## 6. Large Prefab Composition (50-100 Model Clusters)

### 6.1 The Problem

Current prefabs describe single buildings (3-15 pieces). Large POIs like the Graveyard (30-50 pieces) or Bandit Fortress (50-80 pieces) need a different approach because:

- The Model Assembler works fine for placing pieces, but 80-piece prefabs become unwieldy
- Runtime instantiation of 80 individual Ursina Entities per POI is wasteful
- Large POIs need to be placed on procedurally generated maps, so their footprint must be flexible

### 6.2 Solution: Compound Prefab System

Extend the prefab schema to support **compound prefabs** — a prefab that references other prefabs as sub-components plus additional loose pieces.

#### Extended Schema (v0.6)

```json
{
  "prefab_id": "poi_graveyard_v1",
  "building_type": "poi_graveyard",
  "footprint_tiles": [4, 4],
  "ground_anchor_y": 0.0,
  "compound": true,
  "sub_prefabs": [
    {
      "prefab_ref": "graveyard_fence_segment_v1",
      "pos": [0.0, 0.0, 0.0],
      "rot": [0.0, 0.0, 0.0],
      "repeat": {"axis": "x", "count": 4, "spacing": 1.0}
    },
    {
      "prefab_ref": "graveyard_grave_cluster_v1",
      "pos": [1.0, 0.0, 1.0],
      "rot": [0.0, 0.0, 0.0]
    }
  ],
  "pieces": [
    {"model": "Models/GLB format/crypt-small-graveyard.glb", "pos": [2.0, 0.0, 2.0], "rot": [0,0,0], "scale": [1,1,1]}
  ]
}
```

Where `graveyard_fence_segment_v1` is its own prefab with 4-5 fence pieces, and `graveyard_grave_cluster_v1` is a cluster of 5-6 gravestones. The compound prefab composes them with optional repeat patterns.

### 6.3 Runtime Optimization: Merge to Single Mesh

For large prefabs, instantiating 50+ individual Entity objects per POI kills performance if we have 10+ POIs. Solution: at load time, merge all pieces in a compound prefab into a single combined `Mesh`.

```python
def _load_compound_prefab(prefab_data) -> Entity:
    combined_verts = []
    combined_tris = []
    combined_uvs = []
    offset = 0
    
    for piece in all_resolved_pieces:
        mesh_data = load_mesh(piece.model)
        transformed = apply_transform(mesh_data, piece.pos, piece.rot, piece.scale)
        combined_verts.extend(transformed.vertices)
        combined_tris.extend([t + offset for t in transformed.triangles])
        combined_uvs.extend(transformed.uvs)
        offset += len(transformed.vertices)
    
    merged = Mesh(vertices=combined_verts, triangles=combined_tris, uvs=combined_uvs)
    return Entity(model=merged, ...)
```

This gives us a single draw call per large POI instead of 50+. The trade-off is that individual pieces can't be animated or interacted with separately — but POI decorations are static, so that's fine.

### 6.4 Authoring Workflow

1. **Build sub-components** in Model Assembler (fence segment, grave cluster, wall section)
2. **Save as sub-prefab JSONs** (e.g., `graveyard_fence_segment_v1.json`)
3. **Compose compound prefab** referencing sub-prefabs + positioning them on a grid
4. **Test in-game** — the prefab loader handles mesh merging automatically

For procedural generation, the compound prefab system supports **variant slots**: instead of a fixed sub-prefab reference, specify a pool of variants and the placement system picks randomly.

```json
{
  "prefab_ref_pool": ["grave_cluster_a", "grave_cluster_b", "grave_cluster_c"],
  "pos": [1.0, 0.0, 1.0],
  "pick": "random_seeded"
}
```

This means no two graveyards look identical even though they share the same compound prefab template.

---

## 7. Procedural Placement System

### 7.1 POI Placement Pipeline

New file: `game/systems/poi_placement.py`

POI placement runs during world generation, after terrain and lairs are placed. It uses the zone system to determine what POIs can spawn where.

```python
class POIPlacementSystem:
    def generate_pois(self, world, zones, buildings, rng) -> list[PointOfInterest]:
        pois = []
        for zone in zones:
            budget = self._poi_budget(zone)  # based on zone area and difficulty
            palette = zone.poi_palette
            
            for _ in range(budget):
                poi_type = rng.choice(palette, weights=rarity_weights)
                definition = POI_DEFINITIONS[poi_type]
                spot = self._find_valid_spot(world, zone, definition.size, buildings + pois)
                if spot:
                    poi = PointOfInterest(spot.grid_x, spot.grid_y, definition)
                    pois.append(poi)
        
        return pois
```

### 7.2 Placement Constraints

Per-POI placement rules (extending the lair placement logic):

| Constraint | Rule |
|-----------|------|
| **Terrain** | Must be on walkable, buildable tiles (no water, no dense forest for large POIs) |
| **Spacing** | Min 8 tiles from any other POI. Min 5 tiles from any building. |
| **Zone** | POI type must be in the zone's `poi_palette` |
| **Distance from castle** | Must be within the zone's `min_distance` to `max_distance` ring |
| **Elevation** | Cave/mine entrances prefer high-elevation tiles (mountains). Shrines prefer mid-elevation. Camps prefer flat ground. |
| **Water adjacency** | Some POIs (sunken ruins, wells) prefer tiles near water |
| **Edge bias** | Boss arenas and legendary POIs prefer the map edge (high drama, long journey) |
| **Footprint check** | All tiles in the POI's footprint must be valid |

### 7.3 POI Budget Per Zone

Scale with zone area and difficulty tier:

```python
def _poi_budget(self, zone) -> int:
    area = zone_tile_count(zone)  # approximate area in tiles
    base = area // 200            # ~1 POI per 200 tiles
    # Higher difficulty zones get more POIs (more things to discover)
    tier_bonus = zone.difficulty_tier - 1
    return max(1, base + tier_bonus)
```

For a 150×150 map with ~6 zones, expect roughly:
- Castle Town (tier 1): 1-2 POIs (well, market stall)
- Frontier zones (tier 2): 3-4 POIs each
- Dangerous zones (tier 3): 4-5 POIs each
- Edge zones (tier 4-5): 3-4 POIs (fewer but more dramatic)
- **Total: ~20-25 POIs per map**

Plus 1 legendary boss arena and 1 demon portal as fixed spawns.

### 7.4 Deterministic Seeding

All POI placement uses the existing `get_rng("poi_placement")` system for deterministic generation. Same seed = same POI layout = reproducible gameplay.

---

## 8. Fog of War & Discovery

### 8.1 POI Visibility States

POIs interact with fog of war in three states:

| State | Condition | Rendering |
|-------|-----------|-----------|
| **Hidden** | Tile is UNSEEN | POI not rendered at all |
| **Silhouette** | Tile is SEEN but hero hasn't been within discovery range | Dark shadowy version of prefab (reduced alpha, desaturated) + "?" marker icon |
| **Discovered** | Hero has been within `DISCOVERY_RANGE` tiles of the POI | Full prefab render + POI name label + minimap icon |

### 8.2 Discovery Mechanic

```python
DISCOVERY_RANGE = 5  # tiles — slightly less than hero vision range (7)

def check_poi_discovery(hero, pois):
    for poi in pois:
        if poi.is_discovered:
            continue
        dist = hero.distance_to(poi.center_x, poi.center_y) / TILE_SIZE
        if dist <= DISCOVERY_RANGE:
            poi.is_discovered = True
            poi.discoverer_hero_id = hero.id
            event_bus.emit("POI_DISCOVERED", poi=poi, hero=hero)
            # LLM gets notified: "You discovered a Hidden Grove!"
```

### 8.3 Minimap Integration

Discovered POIs show as colored dots on the minimap:
- Combat POIs: red dot
- Loot POIs: gold dot
- Shrine POIs: blue dot
- Knowledge POIs: purple dot
- Dungeon entrances: dark red dot with border
- Boss arenas: large red dot with skull icon

Undiscovered-but-silhouetted POIs show as gray "?" dots.

---

## 9. LLM Hero Integration

### 9.1 POI Context in HeroProfileSnapshot

When a hero is making decisions, nearby POIs are included in the LLM context:

```python
# Added to HeroProfileSnapshot
nearby_pois: list[dict] = [
    {
        "name": "Hidden Grove",
        "type": "shrine",
        "distance": "12 tiles northeast",
        "difficulty": 1,
        "discovered": True,
        "description": "A circle of ancient oaks with a mossy altar at the center.",
        "your_assessment": "Safe to visit. May provide healing."
    },
    {
        "name": "Unknown Structure",  # not yet discovered
        "type": "unknown",
        "distance": "20 tiles east",
        "discovered": False,
        "description": "A shadowy shape in the distance. Could be worth investigating."
    }
]
```

### 9.2 Hero Personality → POI Decisions

The LLM uses hero personality traits to decide POI interactions:

- **Bold/Brave heroes** → seek out dangerous POIs, push deeper into caves
- **Cautious heroes** → avoid POIs above their level, retreat if wounded
- **Curious/Scholar heroes** → prioritize knowledge POIs, investigate mysteries
- **Greedy heroes** → beeline for loot caches, risk danger for gold
- **Pious heroes** → visit shrines regularly, avoid cursed locations
- **Rogues** → drawn to abandoned camps, thief-friendly POIs

### 9.3 POI Interaction Narration

When a hero interacts with a POI, the LLM generates a narration:

```
Hero arrives at POI → LLM receives:
"You have arrived at the Hidden Grove. Ancient oaks form a perfect circle
around a moss-covered stone altar. Soft light filters through the canopy.
The air smells of wildflowers and old magic.
What do you do? [Pray at the altar / Search for treasure / Rest here / Leave]"

LLM responds based on personality:
"Elena kneels before the altar and closes her eyes. She feels a warmth
spread through her body as the grove's magic mends her wounds.
[HP restored to full. Buff: Nature's Blessing (+10% damage for 5 minutes)]"
```

---

## 10. Phased Delivery Roadmap

### Phase 1: Foundation (2-3 sprints)

**Goal:** POIs exist on the map and heroes can discover them.

| Task | Effort | Dependencies |
|------|--------|--------------|
| `PointOfInterest` entity class + `POIDefinition` data model | S | None |
| Zone system (`world_zones.py`) with 5-7 zone definitions | M | None |
| POI placement system (`poi_placement.py`) | M | Zones |
| 5 simple POI prefabs (shrine, treasure cache, hermit hut, well, gravestone) | M | Model Assembler |
| POI rendering in Ursina (reuse building prefab pipeline) | S | POI entity |
| POI discovery mechanic + fog interaction | M | FOW system |
| Minimap POI icons | S | Discovery |
| LLM context for nearby POIs | M | Discovery |
| Basic hero POI interaction (approach, trigger, receive reward) | L | LLM context |

**Deliverable:** Heroes discover and interact with 5 types of simple POIs scattered across a zoned map.

### Phase 2: Depth (2-3 sprints)

**Goal:** Underground content, large POIs, and zone-influenced terrain.

| Task | Effort | Dependencies |
|------|--------|--------------|
| Compound prefab system (sub-prefab composition + mesh merging) | L | Phase 1 |
| 4-5 large POI prefabs (graveyard, ruins, bandit fortress) | L | Compound prefabs |
| Cave/mine entrance POIs (surface prefab) | M | Phase 1 |
| Dungeon interior overlay (Approach A) | L | Interior system |
| Mine-specific interior with resource gathering | L | Dungeon overlay |
| Zone-influenced terrain generation (biome density biases) | M | Zone system |
| POI depletion/respawn mechanics | M | Phase 1 |
| 3-5 medium POI prefabs (abandoned camp, druid grove, ruined outpost, wizard tower) | M | Model Assembler |

**Deliverable:** Rich underground content via overlays, visually impressive large POIs, terrain that feels different per zone.

### Phase 3: Polish & Integration (2-3 sprints)

**Goal:** POIs connect to items, quests, and bosses from the broader roadmap.

| Task | Effort | Dependencies |
|------|--------|--------------|
| Named boss spawning at boss arena POIs | M | Boss system |
| POI-triggered multi-phase quests | L | Quest system |
| Loot tables per POI type (connects to item system) | M | Item system |
| Visual zone distinction (fog tinting, vegetation density) | M | Zone system |
| Silhouette shader for undiscovered POIs | M | Renderer |
| POI interaction UI panel (instead of pure LLM narration) | M | UI system |
| Layer culling system (Approach B) for true underground | XL | Phase 2 overlay proven |
| Map expansion to 250×250 if density requires it | L | Performance testing |

**Deliverable:** POIs are fully integrated with the game's systems — items drop from POIs, quests lead to POIs, bosses guard POIs, and underground is a real gameplay space.

---

## Appendix A: Full POI Type Reference

| POI Type | Size | Interaction | Rarity | Difficulty | Zone Affinity |
|----------|------|-------------|--------|------------|---------------|
| Shrine / Altar | 1×1 | Buff (repeatable) | Common | 1 | All |
| Treasure Cache | 1×1 | Loot (one-time) | Common | 1 | All |
| Hermit Hut | 1×1 | NPC encounter | Uncommon | 1 | Forest, Swamp |
| Mysterious Well | 1×1 | Random outcome | Uncommon | 2 | All |
| Overgrown Gravestone | 1×1 | Knowledge reveal | Common | 1 | Wastes, Swamp |
| Abandoned Camp | 2×2 | Loot + ambush | Common | 2 | Forest, Mountains |
| Druid Grove | 3×3 | Healing shrine | Uncommon | 1 | Forest |
| Ruined Outpost | 3×3 | Combat + vision unlock | Uncommon | 2-3 | Wastes, Mountains |
| Wizard's Tower | 2×2 | Knowledge + quest NPC | Rare | 3 | Any outer zone |
| Windmill Ruin | 2×2 | Repair quest → building | Rare | 1 | Frontier |
| Cave Entrance | 2×2 | Dungeon gateway | Uncommon | 3-5 | Mountains, Wastes |
| Mine Entrance | 2×2 | Resource dungeon | Uncommon | 2-4 | Mountains |
| Overgrown Graveyard | 4×4 | Multi-wave combat | Rare | 3-4 | Wastes, Swamp |
| Ancient Ruins | 5×5 | Knowledge + loot + quest | Rare | 3-4 | Any outer zone |
| Bandit Fortress | 5×5 | Boss + conquest | Legendary | 4-5 | Forest, Mountains |
| Dragon Cave | 3×3 | Boss arena | Legendary | 5 | Mountains |
| Demon Portal | 2×2 | Endgame event | Legendary | 5+ | Deepest zone |

## Appendix B: Kenney Model Quick Reference for POI Authoring

| POI Component | Primary Models | Pack |
|---------------|---------------|------|
| Cave entrance | `cliff_cave_rock.glb`, `cliff_cave_stone.glb` | Nature Kit |
| Cave framing | `cliff_block_rock.glb`, `cliff_blockCave_*.glb` | Nature Kit |
| Tower sections | `tower-base.glb`, `tower.glb`, `tower-top.glb` | Retro Fantasy |
| Altars | `altar-stone-graveyard.glb`, `altar-wood-graveyard.glb` | Graveyard |
| Statues/pillars | `statue_*.glb`, `pillar-*.glb`, `column-*.glb` | Nature Kit, Graveyard |
| Walls (intact) | `wall-fortified-*.glb` | Fantasy Town |
| Walls (ruined) | `wall-broken-*.glb`, `stone-wall-damaged-*.glb` | Fantasy Town, Graveyard |
| Fences | `fence-*.glb`, `iron-fence-*.glb` | Graveyard |
| Gravestones | `gravestone-*.glb`, `cross-*.glb` | Graveyard |
| Debris | `debris-*.glb`, `gravestone-broken-*.glb`, `rocks-*.glb` | Graveyard |
| Camping | `tent-*.glb`, `campfire.glb`, `tool-*.glb` | Survival |
| Containers | `barrel.glb`, `box.glb`, `box-large.glb` | Survival, Fantasy Town |
| Lighting | `lantern-*.glb`, `fire-basket-*.glb`, `candle-*.glb` | Graveyard, Fantasy Town |
| Vegetation | `tree_*.glb`, `plant_*.glb`, `mushroom_*.glb`, `flower_*.glb` | Nature Kit |
| Rocks | `rock_large*.glb`, `rock_tall*.glb`, `rock_small*.glb` | Nature Kit |
| Bridges | `bridge_stone.glb`, `bridge_wood.glb` | Nature Kit |
| Market/industrial | `windmill-*.glb`, `watermill-*.glb`, `stall-*.glb`, `fountain-*.glb` | Fantasy Town |
