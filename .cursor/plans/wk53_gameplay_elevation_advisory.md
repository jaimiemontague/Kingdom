# WK53 Gameplay Elevation Advisory

**Status:** Consulting advisory — no implementation this sprint  
**Prepared by:** Agent 05 (GameplaySystemsDesigner)  
**For:** WK53 r1 terrain elevation architecture phase  
**Implementation scope:** Future sprints (post-WK53)

---

## Summary

Terrain elevation is a visual-only feature in WK53, but the data model must support four key gameplay systems in future sprints:

1. **Building placement restrictions** on slopes
2. **Movement cost scaling** on hills and impassability on cliffs
3. **Combat elevation advantages** (damage, range)
4. **Resource placement** (economy building site requirements)

This advisory establishes design parameters and API requirements so Agent 03's heightmap system is built to support these gameplay features without rework. **All recommendations are marked "future sprint implementation."**

---

## 1. Building Placement on Slopes

### Design Rationale

Kingdom Sim has **10 building types** in active rotation: 4 guilds (Warrior/Ranger/Rogue/Wizard), 4 economic (Marketplace, Blacksmith, Inn, Trading Post), Castle, and Guardhouse. Most are 2×2 footprints; a few are 3×3 or 3×4.

Buildings have visual footprints (prefabs in Ursina) that assume level ground. A 2×2 building placed on a hillside would lean or clip visually. Gameplay-wise, this matters for:
- **Defensive buildings** (Guardhouse, towers) benefit from high ground
- **Economic buildings** (Farms, Food Stands) physically need flat ground
- **Guild halls** are placement-flexible but look better level

### Slope Threshold Recommendation

**Future implementation:** Restrict building placement to slopes ≤ **10 degrees** (measured as maximum height delta across the footprint).

**Rationale:** A 2×2 building is ~64 world units. A 10° slope = ~11 units vertical rise — visually acceptable, looks like gentle rolling terrain. 20° (23 units for 2×2) looks tilted; 30° and steeper are unplayable.

**API requirement:** Heightmap must provide `get_slope_at_footprint(center_x, center_z, footprint_w, footprint_h) -> float` returning max slope angle in degrees.

### Building-Type Restrictions (Future Sprint)

| Building | Current placement | Recommended future gate |
|----------|---|---|
| Castle | Manually placed at start | Keep flat — design the starting zone to have elevation ≤ 5° |
| Guilds (4×) | Player-placeable | Slope ≤ 10° |
| Marketplace | Player-placeable | Slope ≤ 10° |
| Blacksmith | Player-placeable | Slope ≤ 10° |
| Inn | Player-placeable | Slope ≤ 10° |
| Trading Post | Player-placeable | Slope ≤ 10° (or allow it on higher ground for advantage) |
| Guardhouse | Player-placeable | **Slope ≤ 15°** — allow modest height bonus; defensive structures benefit from elevation |
| House (neutral auto-spawn) | Map gen | Slope ≤ 5° — keep settlements level |
| Farm (neutral auto-spawn) | Map gen | **Slope ≤ 5°** — farms need flat land; future growth rate penalty on slopes > 5° |
| Food Stand (neutral auto-spawn) | Map gen | Slope ≤ 5° |

**Stretch goal (visual only this sprint):** If a building is placed on a slope, flatten a small circular area (radius ≈ 2 tiles) around the footprint so the geometry looks leveled. This is optional but improves visual cohesion.

---

## 2. Movement Cost on Hills

### Design Rationale

Heroes and units move on a tile grid (32px tiles). Elevation adds a Z dimension but doesn't change pathfinding logic (that's flat). However, actual movement time should be slower uphill and blocked on cliffs.

Current speeds:
- **Heroes:** 2 tiles/sec (from `HERO_SPEED = 2`)
- **Peasants:** ~1.5 tiles/sec
- **Enemies (varied):** 1.1 - 2.3 tiles/sec depending on type

### Movement Cost Scaling (Future Sprint)

**Uphill penalty:** Add **+20% movement time per 10° of slope** (up to +100% at steep grades).

Example: A unit moving up a 20° slope takes 1.4× normal time; a 30° slope takes 1.6× time.

**Rationale:** Keeps heroes viable but makes hills tactically interesting. Enemies fleeing uphill are easier to intercept. Heroes flanking around slopes (instead of climbing) have a strategic choice.

**API requirement:** Heightmap must provide `get_slope_between_points(x1, z1, x2, z2) -> float` so pathfinding AI can query movement cost before deciding routes.

### Cliff Impassability (Future Sprint)

**Definition:** Slopes ≥ 45° are cliffs and are **completely impassable** to units.

**Rationale:** 45° is ~1:1 vertical:horizontal ratio — visual steepness that makes sense as a barrier without being unrealistic.

**Gameplay impact:** Cliffs become natural chokepoints. Players place defensive buildings at cliff tops. Enemies spawned on the other side must route around. Creates asymmetric map zones.

**API requirement:** Heightmap must provide `is_cliff(x, z) -> bool` for pathfinding exclusion.

### Pathfinding Preference (Future Sprint)

**AI behavior:** Route-finding should include slope cost in the heuristic. Prefer flatter routes when equally distant.

**Rationale:** This is Agent 06's domain (AI behavior), but the heightmap must expose slope queries per-edge so the pathfinding graph can weight terrain difficulty.

**API requirement:** Heightmap must support `get_terrain_cost(x1, z1, x2, z2) -> float` where cost is a multiplier (1.0 = normal, 1.2 = 20% slower, ∞ = impassable).

---

## 3. Combat Elevation Advantages

### Design Rationale

High ground is a classic defensive advantage. Kingdom Sim units don't have armor or deflection mechanics, only HP and attack. Elevation advantage should manifest as:
- **Damage bonus** for units on high ground (offensive)
- **Range extension** for ranged units (tactical advantage)

This is tightly coupled to combat balance. Current combat constants:
- **Base hero attack:** 10 damage
- **Base enemy attacks:** 4–7 damage
- **Hero HP:** 100
- **Enemy HP:** 22–55
- **Skeleton Archer range:** 6.0 tiles (longest ranged unit currently)

### Elevation Bonus (Future Sprint)

**Height-tier system:** Divide elevation into 3 tiers based on local terrain:
- **Tier 0 (low):** Below average elevation
- **Tier 1 (mid):** At average elevation
- **Tier 2 (high):** Above average elevation (≥ +10 units from local center)

**Damage bonus:** Tier 2 units deal **+15% damage** vs. Tier 0 units; no bonus Tier 0 vs. Tier 1.

**Rationale:** At a glance, +15% = ~1.5 extra damage for a 10-damage hero, or ~0.6 extra for a skeleton archer. This is meaningful but not dominant. Stacks with other buffs.

**Range bonus:** Ranged units on Tier 2 ground gain **+1 tile attack range** (e.g., Skeleton Archer goes 6.0 → 7.0 tiles).

**Rationale:** Makes high ground positions tactically distinct. A tower on a ridge can cover more territory.

### API Requirement (Future Sprint)

Heightmap must provide `get_elevation_tier(x, z) -> int` (0, 1, or 2) so combat resolution can query a unit's elevation and apply bonuses.

### Balance Notes

- Do **not** extend this to Peasants (they're non-combatants).
- High ground advantage should **not** completely dominate play. The bonus is modest.
- Cliffs (impassable slopes) act as implicit terrain advantage because attackers must route around — that's enough asymmetry for this sprint.

---

## 4. Resource Placement & Economy

### Design Rationale

Economy buildings (Farms, Food Stands, etc.) are auto-spawned by the map generator. They need to be placed on flat land that makes sense:
- **Farms** need fertile, flat terrain
- **Food Stands** should be in accessible areas
- **Houses** cluster in settlements (naturally leveled)

**Future consideration:** Could mountains yield stone/ore resources, or valleys trap water for mills. Out of scope for WK53 but the heightmap must expose elevation data for future resource type decisions.

### Placement Constraints (Future Sprint)

| Building | Rule | Rationale |
|----------|------|-----------|
| Farm | Slope ≤ 5° (flat) | Agricultural viability |
| Food Stand | Slope ≤ 10° (gentle) | Accessibility |
| House (settlement) | Slope ≤ 5° | Village clustering |
| Tree spawn | No restriction; OK on slopes | Forests grow on hillsides |
| Rock/grass prop spawn | No restriction; OK on slopes | Natural scatter |

### Economy Impact (Future Sprint)

**Optional (stretch):** If a farm is placed on a slope > 5°, apply a **-10% gold output** penalty. This makes flat farmland more valuable strategically.

**Rationale:** Encourages players to defend good farm sites. Adds emergent strategy (if enemies camp near a valley farm, it hurts player gold output).

**API requirement:** Heightmap must support `get_slope_at_point(x, z) -> float` for economy building initialization.

---

## 5. Heightmap API Requirements

For **Agent 03** to design the heightmap system, the following public API must be exposed (in `game/graphics/ursina_coords.py` or similar):

### Core Functions (Required)

```python
def get_terrain_height(world_x: float, world_z: float) -> float:
    """
    Sample the heightmap at (world_x, world_z).
    Returns Y coordinate (elevation in world units).
    Used for entity placement (buildings, units, props).
    """
    pass

def get_slope_at_point(world_x: float, world_z: float, 
                       sample_radius: float = 1.0) -> float:
    """
    Return slope angle in degrees at a point.
    sample_radius: how far to sample neighbors for slope calculation.
    Returns: 0–90 degrees.
    Used for building placement checks, economy penalties.
    """
    pass

def get_slope_between_points(x1: float, z1: float, 
                              x2: float, z2: float) -> float:
    """
    Return slope angle when moving from point A to point B.
    Returns: angle in degrees (positive = uphill, negative = downhill).
    Used for movement cost calculation in pathfinding.
    """
    pass

def get_max_slope_at_footprint(center_x: float, center_z: float,
                                footprint_width: float, 
                                footprint_height: float) -> float:
    """
    Return the maximum slope across a building footprint.
    Used to gate placement: reject if > slope_threshold.
    """
    pass

def is_cliff(world_x: float, world_z: float) -> bool:
    """
    Return True if the terrain at (world_x, world_z) is a cliff (slope >= 45°).
    Used to mark impassable cliffs in pathfinding.
    """
    pass

def get_elevation_tier(world_x: float, world_z: float) -> int:
    """
    Return elevation tier: 0 (low), 1 (mid), 2 (high).
    Tiers are computed relative to local terrain average.
    Used for combat elevation bonuses.
    """
    pass

def get_terrain_cost_multiplier(x1: float, z1: float, 
                                  x2: float, z2: float) -> float:
    """
    Return movement cost multiplier for traveling from A to B.
    1.0 = normal speed, 1.2 = 20% slower, inf = impassable.
    Used for AI pathfinding heuristic.
    """
    pass
```

### Implementation Guidance

- **Heightmap resolution:** At least 1 sample per tile (32px). Recommend 2–4× for smooth slopes.
- **Performance:** Cache elevation lookups where possible. Pathfinding will call `get_terrain_cost_multiplier()` frequently.
- **Cliffs:** Detect dynamically in `is_cliff()` or pre-compute at generation time.
- **Elevation tiers:** Compute tiers at initialization by sampling the heightmap and dividing into quantiles. Store as a second texture/array for O(1) lookup.
- **Boundary handling:** Clamp or reflect heightmap samples near the map edge to avoid edge artifacts.

---

## Recommended Config Constants (for WK53 Wave 2 or later)

Add to `config.py` once gameplay features ship:

```python
# Terrain elevation gameplay (future sprint)
TERRAIN_HEIGHT_SCALE = 20  # Max elevation in world units
TERRAIN_SLOPE_THRESHOLD_DEGREES = 10  # Max slope for building placement
TERRAIN_CLIFF_THRESHOLD_DEGREES = 45  # Slope that counts as impassable cliff
TERRAIN_GUARDIAN_SLOPE_THRESHOLD = 15  # Max slope for defensive buildings
TERRAIN_FARM_SLOPE_THRESHOLD = 5  # Max slope for flat farm placement

# Movement cost scaling
TERRAIN_UPHILL_COST_PER_DEGREE = 0.02  # +2% time per degree (max +100% at 50°)
TERRAIN_ELEVATION_TIER_HEIGHT_DELTA = 10.0  # Height threshold for tier calculation (units)

# Combat elevation bonuses
COMBAT_ELEVATION_BONUS_DAMAGE_PERCENT = 15  # +15% damage on high ground
COMBAT_ELEVATION_BONUS_RANGED_RANGE_TILES = 1.0  # +1 tile range
COMBAT_ELEVATION_TIER_COUNT = 3  # 0=low, 1=mid, 2=high

# Economy penalties (optional stretch)
FARM_SLOPE_PENALTY_THRESHOLD = 5.0  # Slope >= this triggers gold penalty
FARM_SLOPE_PENALTY_GOLD_PERCENT = 10  # -10% output if slope too steep
```

---

## Summary Table

| Feature | Threshold / Value | Reason | Future Sprint | API Needed |
|---------|---|---|---|---|
| **Building placement** | ≤ 10° slope (Guardhouse: ≤ 15°) | Visual/UX readability | WK54+ | `get_max_slope_at_footprint()` |
| **Uphill movement cost** | +20% per 10° slope | Tactical depth, not punitive | WK54+ | `get_slope_between_points()`, `get_terrain_cost_multiplier()` |
| **Cliff impassability** | ≥ 45° = impassable | Natural barrier | WK54+ | `is_cliff()` |
| **Damage bonus (high ground)** | +15% for Tier 2 vs. Tier 0 | Balanced advantage | WK55+ | `get_elevation_tier()` |
| **Range bonus (ranged units)** | +1 tile on high ground | Tactical variety | WK55+ | `get_elevation_tier()` |
| **Farm output penalty** | -10% if slope > 5° | Economic strategy | WK56+ (stretch) | `get_slope_at_point()` |
| **Heightmap resolution** | 2–4× per tile minimum | Performance + smoothness | WK53 (Wave 2) | All functions |

---

## Risks & Dependencies

| Risk | Mitigation |
|------|-----------|
| Heightmap API underspecified → Agent 03 must rework later | **Mitigated:** This advisory defines 7 public functions with clear use cases. Agent 03 can design around this API contract. |
| Uphill cost makes map edges inaccessible | Test with actual map layouts. May need to adjust TERRAIN_UPHILL_COST_PER_DEGREE down. Cliffs are the real gating mechanism. |
| Elevation tier calculation is jittery (units oscillate tiers) | Cache tier lookups. Do not recalculate every frame. Terrain doesn't change mid-game. |
| Combat elevation bonus trivializes certain matchups | Keep the bonus modest (+15%). Test with existing economy (enemy spawning, bounty balance). If needed, cap bonus to specific unit types (exclude Tier 0 peasants). |
| Map generation doesn't smooth the castle spawn area | Smoothing algorithm must reduce elevation ≤ 5° within castle radius (~5 tiles). Add this to Agent 03's heightmap generation contract. |

---

## Next Steps

1. **Agent 03** reads this advisory and incorporates API contract into Wave 0 architecture doc.
2. **Agent 03 Wave 2** implements heightmap generation + terrain mesh + entity Y-placement.
3. **Agent 05 (future sprint)** implements gameplay systems (movement cost, building restrictions, combat bonuses) using the heightmap API.
4. **Agent 02** (GameDirector) reviews the elevation impact on game feel and calls for balance tuning if needed.

---

## References

- Config: `config.py` — building costs, sizes, enemy stats, hero stats
- Sprint plan: `.cursor/plans/wk53_world_beauty_terrain.plan.md`
- Agent 03 Wave 0 architecture doc (forthcoming)
