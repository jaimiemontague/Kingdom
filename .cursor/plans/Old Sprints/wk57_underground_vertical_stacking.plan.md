# Sprint WK57 — Underground Vertical Stacking (Full Approach C)

> **Status:** ACTIVE
> **Version target:** TBD (Jaimie decides)
> **Theme:** Physical underground geometry below Y=0, cave entrance holes via shader discard, cutaway camera, procedural cave terrain, underground lighting and fog, layer-aware pathfinding
> **Roadmap:** `.cursor/plans/pois_multisprint_roadmap.md` (Sprint 4 of 5)
> **Depends on:** WK54-56 (zones, POI entity/placement/interactions, underground data model all exist)
> **Plan doc:** `.cursor/plans/pois_proposal.md` Section 5.3 (Approach C)

---

## Goal

Underground terrain rendered as physical 3D space below the surface. Cave/mine entrance POIs create visible holes in the surface terrain via fragment shader discard. Camera supports smooth layer transitions. Underground has procedurally generated cave terrain (Perlin noise floor, stalactites), its own lighting (dark ambient + torch point lights), and separate fog of war. Heroes navigate between surface and underground via layer-aware pathfinding. AI-driven and player-directed cave exploration based on hero personality.

---

## Architecture Overview

### Surface Cave Holes — Shader Discard (NOT Dynamic Vertex Removal)

The surface terrain is a single Ursina Mesh entity using `terrain_fog_shader` (file: `game/graphics/terrain_fog_shader.py`). Instead of modifying the mesh geometry to create holes (fragile, complex), we extend the fragment shader to **discard fragments** within a radius of each cave entrance. This creates clean visual holes with zero mesh modification.

The shader already has `v_fog_uv` which maps `[0,1]` across the full map extent. Cave entrance positions are converted to this same UV space and passed as shader uniforms. Unused entrance slots default to `(99.0, 99.0)` — far outside the valid UV range — so the distance check is always large and never triggers discard.

### Underground Terrain Mesh — Separate Entity Below Surface

Each `UndergroundArea` (attached to cave/mine POIs) generates its own 3D terrain mesh positioned at Y < 0, visible through the surface holes. Cave floor uses Perlin noise for natural-looking bumpy terrain. Stalactite/stalagmite entities (rotated Kenney rock models) provide decoration. Each mesh is a single Ursina Entity with a rock/stone texture.

### Camera Layer System — Smooth Transition

Camera tracks `active_layer` (0 = surface, -1 = underground). When a hero enters a cave, the camera smoothly descends through the surface hole to underground level. Underground ambient is darker; torch point lights provide warm illumination. Camera controls (WASD + zoom) work identically underground.

### Layer-Aware Pathfinding — Extended A*

The existing A* pathfinder (`game/systems/pathfinding.py`) is extended with a layer dimension. Path nodes become `(x, y, layer)`. Cave entrance tiles provide transition edges between layer 0 and layer -1. Underground walkability grids are derived from the chamber layout.

### Underground Fog of War — Per-Area Visibility Grid

Each `UndergroundArea` has its own visibility grid (sized to its chamber extents). Heroes reveal underground fog as they explore chambers, independent of surface fog.

---

## Scope

### In scope
- Surface cave hole shader (fragment discard at cave entrance positions)
- Procedural underground terrain mesh (Perlin noise floor per UndergroundArea)
- Stalactite/stalagmite decoration entities (Kenney rock models rotated)
- Camera layer transition (smooth descent/ascent with ambient change)
- Underground lighting (dark ambient + torch PointLights at chamber locations)
- Underground fog of war (per-area visibility grid with hero reveal)
- Layer-aware A* pathfinding (surface ↔ underground transitions at cave entrances)
- Hero descent/ascent state machine at cave entrance POIs
- Underground enemy spawning from chamber data
- AI-driven cave exploration (personality-based autonomous entry)
- Player-directed cave entry via direct prompt
- Test suite for all underground mechanics
- Performance verification

### Out of scope
- Full dungeon room generation (procedural layouts) — future
- Boss encounters inside underground — WK58
- Mine-specific resource gathering minigame — future
- Underground-specific prefab models beyond rock/stalactite reuse — future
- Multi-floor underground (single layer -1 only this sprint)

---

## Risk & Fallback

**Primary risk:** Shader discard may interact poorly with the fog overlay on some GPUs, or the underground mesh may cause z-fighting artifacts near the cave hole boundary.

**Fallback:** If the shader-based cave holes don't render correctly, downgrade to the layer-culling approach (camera fade-to-black → switch layer visibility → fade-in). This removes the "see through the surface" effect but keeps all other underground features functional.

**Performance risk:** Rendering a second terrain mesh doubles vertex count. Mitigation: underground meshes are small (only cover chamber extents, not the full map) and only rendered when a hero is underground or the camera is near a cave entrance.

---

## Config Constants (New — add to `config.py`)

Agent 03 adds these in Wave 1. All are in the `# Underground / WK57` section, placed after the existing terrain constants.

```python
# ---------- Underground / Vertical Stacking (WK57) ----------
UNDERGROUND_DEPTH = 10.0
UNDERGROUND_CEILING_Y = -2.0
UNDERGROUND_CAVE_NOISE_AMP = 1.5
UNDERGROUND_CAVE_NOISE_FREQ = 0.3
UNDERGROUND_HOLE_RADIUS_TILES = 2.5
UNDERGROUND_HOLE_EDGE_TILES = 1.0
UNDERGROUND_TORCH_COLOR = (1.0, 0.75, 0.4)
UNDERGROUND_TORCH_INTENSITY = 0.8
UNDERGROUND_TORCH_ATTENUATION = (1.0, 0.22, 0.08)
UNDERGROUND_AMBIENT_COLOR = (0.08, 0.06, 0.1)
UNDERGROUND_AMBIENT_ALPHA = 1.0
UNDERGROUND_FOG_DENSITY = 0.015
UNDERGROUND_CAMERA_TRANSITION_SPEED = 8.0
UNDERGROUND_MAX_ENTRANCES_SHADER = 8
UNDERGROUND_HERO_DESCENT_SPEED = 4.0
UNDERGROUND_CHAMBER_SPACING = 3
UNDERGROUND_CORRIDOR_WIDTH = 2
UNDERGROUND_ROCK_TEXTURE = "assets/textures/rock_ground.png"
```

---

## Wave 1 — Data Model Extension + Config + Surface Hole Shader

**Agent:** 03 (TechnicalDirector)
**Intelligence:** HIGH
**Purpose:** Extend the underground data model with world coordinates, add config constants, and implement the surface terrain cave hole shader.

### Files to Read First
- `game/underground.py` (99 lines) — current data model
- `game/graphics/terrain_fog_shader.py` (64 lines) — the shader you will extend
- `game/graphics/ursina_terrain_fog_collab.py` lines 688-835 — terrain mesh creation + shader input pipeline
- `game/sim_engine.py` lines 278-290 — underground area generation during world init
- `config.py` — search for `TERRAIN_HEIGHT_SCALE` to find the terrain constants section
- `game/entities/poi.py` — POIDefinition, PointOfInterest class

### Task 1A: Extend `game/underground.py`

Add world coordinate fields to `UndergroundChamber` and a layout generator to `UndergroundArea`.

```python
@dataclass
class UndergroundChamber:
    chamber_id: str
    name: str
    depth_level: int
    width: int   # tiles
    height: int  # tiles
    enemies: list = field(default_factory=list)
    loot_gold: int = 0
    is_explored: bool = False
    is_cleared: bool = False
    connections: list[str] = field(default_factory=list)
    # --- NEW WK57 fields ---
    world_offset_x: int = 0   # tile offset from entrance (within underground area)
    world_offset_z: int = 0   # tile offset from entrance (deeper = larger z)


@dataclass
class UndergroundArea:
    area_id: str
    entrance_poi_type: str
    entrance_grid_x: int
    entrance_grid_y: int
    chambers: list[UndergroundChamber] = field(default_factory=list)
    max_depth: int = 3
    difficulty_tier: int = 3
    is_generated: bool = False
    # --- NEW WK57 fields ---
    total_width: int = 0     # bounding box width in tiles
    total_height: int = 0    # bounding box height in tiles
    walkability: list[list[bool]] = field(default_factory=list)  # True=walkable
    floor_heightmap: list[list[float]] = field(default_factory=list)  # Perlin noise cave floor
```

Add a method `compute_layout()` to `UndergroundArea` that assigns `world_offset_x/z` to each chamber and builds the walkability grid + floor heightmap:

```python
def compute_layout(self, rng=None):
    """Assign world offsets to chambers and build walkability + floor heightmap.
    
    Layout: chambers stacked vertically (deeper = larger z offset).
    Each chamber is centered on x=0 relative to entrance.
    Corridors connect adjacent chambers vertically.
    """
    from config import (
        UNDERGROUND_CHAMBER_SPACING,
        UNDERGROUND_CORRIDOR_WIDTH,
        UNDERGROUND_CAVE_NOISE_AMP,
        UNDERGROUND_CAVE_NOISE_FREQ,
        UNDERGROUND_DEPTH,
    )
    if rng is None:
        from game.sim.determinism import get_rng
        rng = get_rng("underground_layout")
    
    # 1. Assign chamber positions (vertical stack, centered on x=0)
    max_w = 0
    z_cursor = 0
    for ch in self.chambers:
        ch.world_offset_x = -(ch.width // 2)  # center horizontally
        ch.world_offset_z = z_cursor
        z_cursor += ch.height + UNDERGROUND_CHAMBER_SPACING
        max_w = max(max_w, ch.width)
    
    self.total_width = max_w + 4  # padding
    self.total_height = z_cursor + 2  # padding
    
    # 2. Build walkability grid (True = walkable tile)
    self.walkability = [
        [False for _ in range(self.total_width)]
        for _ in range(self.total_height)
    ]
    # Center offset so x=0 maps to grid center
    cx = self.total_width // 2
    
    for ch in self.chambers:
        for dz in range(ch.height):
            for dx in range(ch.width):
                gx = cx + ch.world_offset_x + dx
                gz = ch.world_offset_z + dz
                if 0 <= gx < self.total_width and 0 <= gz < self.total_height:
                    self.walkability[gz][gx] = True
    
    # Mark corridors between connected chambers
    for i, ch in enumerate(self.chambers):
        if i + 1 < len(self.chambers):
            next_ch = self.chambers[i + 1]
            corridor_start_z = ch.world_offset_z + ch.height
            corridor_end_z = next_ch.world_offset_z
            for gz in range(corridor_start_z, corridor_end_z):
                for dx in range(UNDERGROUND_CORRIDOR_WIDTH):
                    gx = cx - UNDERGROUND_CORRIDOR_WIDTH // 2 + dx
                    if 0 <= gx < self.total_width and 0 <= gz < self.total_height:
                        self.walkability[gz][gx] = True
    
    # 3. Build floor heightmap (Perlin noise for bumpy cave floor)
    try:
        from noise import pnoise2
    except ImportError:
        pnoise2 = None
    
    self.floor_heightmap = []
    for gz in range(self.total_height):
        row = []
        for gx in range(self.total_width):
            if pnoise2 is not None:
                n = pnoise2(
                    gx * UNDERGROUND_CAVE_NOISE_FREQ,
                    gz * UNDERGROUND_CAVE_NOISE_FREQ,
                    octaves=2,
                    base=hash(self.area_id) % 1000,
                )
                h = -UNDERGROUND_DEPTH + (n + 1.0) * 0.5 * UNDERGROUND_CAVE_NOISE_AMP
            else:
                h = -UNDERGROUND_DEPTH
            row.append(h)
        self.floor_heightmap.append(row)
    
    return self
```

Update `generate_underground_area()` to call `compute_layout()` at the end before returning:
```python
    area.is_generated = True
    area.compute_layout(rng)
    return area
```

### Task 1B: Add Config Constants

Add the constants listed in the "Config Constants" section above to `config.py`, in a new section after the existing terrain constants (search for `TERRAIN_CASTLE_FLAT_RADIUS` to find the right location).

### Task 1C: Extend the Terrain Shader with Cave Hole Discard

Modify `game/graphics/terrain_fog_shader.py`. The shader currently has:
- Vertex: passes `uvs` (tiled grass UV) and `v_fog_uv` (map-wide [0,1] UV)
- Fragment: samples grass and fog textures, alpha-blends

Add 8 cave entrance uniform slots + radius/edge uniforms. The fragment shader checks distance from each entrance in fog UV space and discards close fragments.

**IMPORTANT**: Use `v_fog_uv` for distance calculations since it maps [0,1] across the full map. Cave entrance positions will be in the same space. Default unused entrances to `vec2(99.0, 99.0)` so they never trigger discard.

Here is the exact new shader code — replace the entire `terrain_fog_shader` definition:

```python
terrain_fog_shader = Shader(
    name="terrain_fog_shader",
    language=Shader.GLSL,
    vertex="""#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 uvs;
out vec2 v_fog_uv;
uniform vec2 texture_scale;
uniform vec2 texture_offset;
uniform vec2 fog_uv_scale;
uniform vec2 fog_uv_offset;
in vec4 p3d_Color;
out vec4 vertex_color;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    uvs = (p3d_MultiTexCoord0 * texture_scale) + texture_offset;
    v_fog_uv = p3d_MultiTexCoord0 * fog_uv_scale + fog_uv_offset;
    vertex_color = p3d_Color;
}
""",
    fragment="""#version 140
uniform sampler2D p3d_Texture0;
uniform sampler2D fog_texture;
uniform vec4 p3d_ColorScale;
in vec2 uvs;
in vec2 v_fog_uv;
out vec4 fragColor;
in vec4 vertex_color;

uniform vec2 cave_entrance_0;
uniform vec2 cave_entrance_1;
uniform vec2 cave_entrance_2;
uniform vec2 cave_entrance_3;
uniform vec2 cave_entrance_4;
uniform vec2 cave_entrance_5;
uniform vec2 cave_entrance_6;
uniform vec2 cave_entrance_7;
uniform float cave_hole_radius;
uniform float cave_edge_width;

void main() {
    vec4 terrain = texture(p3d_Texture0, uvs) * p3d_ColorScale * vertex_color;
    vec4 fog = texture(fog_texture, v_fog_uv);

    float d0 = distance(v_fog_uv, cave_entrance_0);
    float d1 = distance(v_fog_uv, cave_entrance_1);
    float d2 = distance(v_fog_uv, cave_entrance_2);
    float d3 = distance(v_fog_uv, cave_entrance_3);
    float d4 = distance(v_fog_uv, cave_entrance_4);
    float d5 = distance(v_fog_uv, cave_entrance_5);
    float d6 = distance(v_fog_uv, cave_entrance_6);
    float d7 = distance(v_fog_uv, cave_entrance_7);
    float min_d = min(min(min(d0, d1), min(d2, d3)), min(min(d4, d5), min(d6, d7)));

    if (min_d < cave_hole_radius) discard;

    float cave_edge = 1.0;
    if (cave_edge_width > 0.0 && min_d < cave_hole_radius + cave_edge_width) {
        cave_edge = (min_d - cave_hole_radius) / cave_edge_width;
    }

    vec3 final_rgb = mix(terrain.rgb, fog.rgb, fog.a);
    final_rgb *= cave_edge;
    fragColor = vec4(final_rgb, 1.0);
}
""",
    default_input={
        "texture_scale": Vec2(1, 1),
        "texture_offset": Vec2(0.0, 0.0),
        "fog_uv_scale": Vec2(1, 1),
        "fog_uv_offset": Vec2(0.0, 0.0),
        "cave_entrance_0": Vec2(99.0, 99.0),
        "cave_entrance_1": Vec2(99.0, 99.0),
        "cave_entrance_2": Vec2(99.0, 99.0),
        "cave_entrance_3": Vec2(99.0, 99.0),
        "cave_entrance_4": Vec2(99.0, 99.0),
        "cave_entrance_5": Vec2(99.0, 99.0),
        "cave_entrance_6": Vec2(99.0, 99.0),
        "cave_entrance_7": Vec2(99.0, 99.0),
        "cave_hole_radius": 0.0,
        "cave_edge_width": 0.0,
    },
)
```

### Task 1D: Pipeline Cave Entrance Positions to Shader

In `game/graphics/ursina_terrain_fog_collab.py`, add a method to upload cave entrance positions as shader uniforms. This should be called after terrain mesh creation and whenever POIs are discovered.

Find the method that stores the terrain ground entity reference (around line 837, after `ground_ent.set_shader_input("fog_uv_offset", ...)`). Add:

```python
def update_cave_entrance_shader(self, pois, map_width, map_height):
    """Upload discovered cave/mine entrance positions to the terrain shader.
    
    Converts POI grid positions to fog UV space [0,1] and sets shader uniforms.
    Call this whenever POI discovery state changes.
    """
    ground_ent = getattr(self, '_terrain_ground_ent', None)
    if ground_ent is None:
        return
    
    from config import UNDERGROUND_HOLE_RADIUS_TILES, UNDERGROUND_HOLE_EDGE_TILES
    
    entrances = []
    for poi in pois:
        poi_def = getattr(poi, 'poi_def', None)
        if poi_def is None:
            continue
        if poi_def.interaction_type != 'dungeon':
            continue
        if not getattr(poi, 'is_discovered', False):
            continue
        size = poi_def.size
        cx = poi.grid_x + size[0] / 2.0
        cy = poi.grid_y + size[1] / 2.0
        # Convert to fog UV space: x/map_width, 1 - y/map_height (Y is flipped)
        uv_x = cx / map_width
        uv_y = 1.0 - (cy / map_height)
        entrances.append((uv_x, uv_y))
        if len(entrances) >= 8:
            break
    
    for i in range(8):
        if i < len(entrances):
            ground_ent.set_shader_input(f"cave_entrance_{i}", Vec2(*entrances[i]))
        else:
            ground_ent.set_shader_input(f"cave_entrance_{i}", Vec2(99.0, 99.0))
    
    if entrances:
        hole_r = UNDERGROUND_HOLE_RADIUS_TILES / max(map_width, map_height)
        edge_w = UNDERGROUND_HOLE_EDGE_TILES / max(map_width, map_height)
        ground_ent.set_shader_input("cave_hole_radius", hole_r)
        ground_ent.set_shader_input("cave_edge_width", edge_w)
    else:
        ground_ent.set_shader_input("cave_hole_radius", 0.0)
        ground_ent.set_shader_input("cave_edge_width", 0.0)
```

Also store the terrain ground entity reference by adding `self._terrain_ground_ent = ground_ent` after the entity is created (around line 826).

### Task 1E: Add `layer` Property to Entity Base Classes

In `game/entities/hero.py`, add a `layer` field (default `0`) to the `Hero` class `__init__`:
```python
self.layer = 0  # 0 = surface, -1 = underground
```

In `game/entities/enemy.py`, add the same field to `Enemy.__init__`:
```python
self.layer = 0
```

### Verification Steps (Wave 1)

1. **Tests pass**: `python tools/qa_smoke.py --quick` — must PASS (307+ tests)
2. **Shader compiles**: Launch `python main.py --provider mock` — game must boot without shader compilation errors. Look for errors mentioning `terrain_fog_shader` in the console.
3. **Surface looks unchanged**: With no cave POIs discovered, the surface terrain should look identical to before (all cave entrance uniforms default to (99,99) and hole_radius=0).
4. **Data model**: Run a quick Python test:
   ```python
   python -c "from game.underground import generate_underground_area; from game.entities.poi import PointOfInterest, POI_DEFINITIONS; poi = PointOfInterest(50, 50, POI_DEFINITIONS['poi_cave_entrance']); area = generate_underground_area(poi); print(f'chambers={len(area.chambers)}, total={area.total_width}x{area.total_height}, walkable_cells={sum(sum(r) for r in area.walkability)}')"
   ```
   This must print reasonable values (3-5 chambers, non-zero walkable cells).

---

## Wave 2 — Underground Terrain Mesh Generation + Rendering

**Agent:** 03 (TechnicalDirector)
**Intelligence:** HIGH
**Purpose:** Generate and render the underground cave floor mesh in 3D, visible through the surface holes. Add stalactite/stalagmite decoration.

### Files to Read First
- `game/underground.py` (after Wave 1 updates) — chamber layout, walkability, floor heightmap
- `game/graphics/ursina_terrain_fog_collab.py` lines 726-836 — how surface terrain mesh is built (follow the same pattern)
- `game/graphics/ursina_renderer.py` lines 700-735 — POI rendering, debug flags
- `game/sim_engine.py` lines 278-290 — where underground_areas are stored
- `config.py` — new UNDERGROUND_* constants from Wave 1

### Task 2A: Create `game/graphics/underground_terrain.py` (NEW FILE)

This module generates and manages underground terrain meshes. Create it with:

```python
"""Underground terrain mesh generation and rendering (WK57).

For each UndergroundArea, generates:
- A cave floor mesh (Perlin noise heightmap at Y < 0)
- Stalactite/stalagmite decoration entities
- A dark rock ground texture
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.underground import UndergroundArea

from ursina import Entity, Mesh, Vec2, Vec3, color
from ursina.shaders import unlit_shader

from config import (
    TILE_SIZE,
    UNDERGROUND_DEPTH,
    UNDERGROUND_CEILING_Y,
    UNDERGROUND_CAVE_NOISE_AMP,
)


def sim_px_to_world_xz(px: float, py: float) -> tuple[float, float]:
    """Convert sim pixel coords to Ursina world (x, z). Import from ursina_app if available."""
    from game.graphics.ursina_app import sim_px_to_world_xz as _conv
    return _conv(px, py)


class UndergroundTerrainManager:
    """Creates and manages Ursina entities for underground cave meshes."""

    def __init__(self):
        self._area_entities: dict[str, list[Entity]] = {}  # area_id -> [floor_ent, decorations...]

    def create_underground_mesh(self, area: UndergroundArea, root_parent) -> Entity | None:
        """Build and return a cave floor mesh entity for the given underground area.
        
        The mesh is positioned at the area's entrance POI location, offset downward.
        Each vertex Y comes from area.floor_heightmap (Perlin noise at Y < 0).
        """
        if not area.is_generated or not area.floor_heightmap:
            return None

        gw = area.total_width
        gh = area.total_height

        # World position of the entrance POI
        entrance_px = area.entrance_grid_x * TILE_SIZE + TILE_SIZE
        entrance_py = area.entrance_grid_y * TILE_SIZE + TILE_SIZE
        base_wx, base_wz = sim_px_to_world_xz(entrance_px, entrance_py)

        # Tile-to-world scale
        from config import MAP_WIDTH, MAP_HEIGHT
        from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab
        # Each tile = TILE_SIZE sim pixels. In world coords, the full map width is
        # MAP_WIDTH * TILE_SIZE / SCALE. We can compute dx_world per tile:
        # The surface terrain mesh covers MAP_WIDTH tiles across w_world world units.
        # For underground, each tile should be the same world-space size.
        # From the surface mesh: dx_world = w_world / (heightmap_grid_w - 1)
        # Simplified: each tile is approximately 1.0 world unit (TILE_SIZE/TILE_SIZE)
        # Actually: world_x = sim_px / SCALE where SCALE = TILE_SIZE
        tile_world = 1.0  # 1 world unit per tile (TILE_SIZE / TILE_SIZE)

        verts = []
        uvs = []
        norms = []

        for gz in range(gh):
            for gx in range(gw):
                # Position relative to entrance, then offset to world
                # Center the mesh on the entrance
                cx_offset = gx - gw // 2
                cz_offset = gz  # deeper chambers go further in z

                wx = cx_offset * tile_world
                wz = -cz_offset * tile_world  # negative z = "forward" in world
                wy = area.floor_heightmap[gz][gx]

                # Only generate vertices for walkable areas + 1-tile border
                # (non-walkable areas get very low Y to create natural walls)
                if not area.walkability[gz][gx]:
                    wy = UNDERGROUND_CEILING_Y  # push to ceiling height = invisible wall

                verts.append((wx, wy, wz))
                uvs.append((gx / max(1, gw - 1), gz / max(1, gh - 1)))

        # Compute normals (same as surface terrain approach)
        for gz in range(gh):
            for gx in range(gw):
                gx0 = max(0, gx - 1)
                gx1 = min(gw - 1, gx + 1)
                gz0 = max(0, gz - 1)
                gz1 = min(gh - 1, gz + 1)
                idx = lambda _gz, _gx: _gz * gw + _gx
                hL = verts[idx(gz, gx0)][1]
                hR = verts[idx(gz, gx1)][1]
                hD = verts[idx(gz0, gx)][1]
                hU = verts[idx(gz1, gx)][1]
                nx = -(hR - hL)
                ny = 2.0
                nz = -(hU - hD)
                ln = math.sqrt(nx * nx + ny * ny + nz * nz)
                if ln > 1e-8:
                    nx /= ln; ny /= ln; nz /= ln
                else:
                    nx, ny, nz = 0.0, 1.0, 0.0
                norms.append((nx, ny, nz))

        # Build triangle indices
        triangles = []
        for gz in range(gh - 1):
            for gx in range(gw - 1):
                i00 = gz * gw + gx
                i10 = gz * gw + gx + 1
                i01 = (gz + 1) * gw + gx
                i11 = (gz + 1) * gw + gx + 1
                triangles.extend([i00, i01, i10])
                triangles.extend([i10, i01, i11])

        cave_mesh = Mesh(
            vertices=verts,
            triangles=triangles,
            uvs=uvs,
            normals=norms,
            mode="triangle",
        )

        cave_ent = Entity(
            parent=root_parent,
            model=cave_mesh,
            color=color.rgb(0.35, 0.28, 0.22),  # dark brown rock
            position=Vec3(base_wx, 0, base_wz),
            collision=False,
            double_sided=True,
            shader=unlit_shader,
            add_to_scene_entities=False,
        )

        entities = [cave_ent]
        self._area_entities[area.area_id] = entities
        return cave_ent

    def create_stalactites(self, area: UndergroundArea, root_parent, rng=None):
        """Place stalactite decoration entities at random positions in walkable chambers."""
        if rng is None:
            from game.sim.determinism import get_rng
            rng = get_rng("underground_deco")

        entrance_px = area.entrance_grid_x * TILE_SIZE + TILE_SIZE
        entrance_py = area.entrance_grid_y * TILE_SIZE + TILE_SIZE
        base_wx, base_wz = sim_px_to_world_xz(entrance_px, entrance_py)
        cx = area.total_width // 2

        for ch in area.chambers:
            num_stalactites = rng.randint(2, max(3, ch.width))
            for _ in range(num_stalactites):
                dx = rng.randint(0, ch.width - 1)
                dz = rng.randint(0, ch.height - 1)
                gx = cx + ch.world_offset_x + dx
                gz = ch.world_offset_z + dz

                if not (0 <= gx < area.total_width and 0 <= gz < area.total_height):
                    continue
                if not area.walkability[gz][gx]:
                    continue

                wx = (gx - cx) * 1.0 + base_wx
                wz = -gz * 1.0 + base_wz

                # Stalactite: a scaled cone-like rock model hanging from ceiling
                try:
                    stalactite = Entity(
                        parent=root_parent,
                        model="cone",
                        color=color.rgb(0.3, 0.25, 0.2),
                        scale=(0.15, 0.4 + rng.random() * 0.3, 0.15),
                        position=Vec3(wx, UNDERGROUND_CEILING_Y, wz),
                        rotation=(180, rng.randint(0, 360), 0),
                        add_to_scene_entities=False,
                    )
                    if area.area_id in self._area_entities:
                        self._area_entities[area.area_id].append(stalactite)
                except Exception:
                    pass

    def set_underground_visible(self, area_id: str, visible: bool):
        """Show or hide all entities for an underground area."""
        for ent in self._area_entities.get(area_id, []):
            ent.enabled = visible

    def destroy_all(self):
        """Clean up all underground entities."""
        for entities in self._area_entities.values():
            for ent in entities:
                try:
                    ent.enabled = False
                    from ursina import destroy
                    destroy(ent)
                except Exception:
                    pass
        self._area_entities.clear()
```

### Task 2B: Integrate Underground Mesh into Renderer

In `game/graphics/ursina_renderer.py`, add underground mesh creation during the building sync pass. When a cave/mine POI is discovered and has an underground area, create its mesh.

Add an instance of `UndergroundTerrainManager` to `UrsinaRenderer.__init__`:
```python
from game.graphics.underground_terrain import UndergroundTerrainManager
self._underground_mgr = UndergroundTerrainManager()
```

In the POI rendering section (around line 727, the building sync method), after a dungeon POI is first rendered (discovered), check if its underground mesh exists. If not, create it:

```python
# After POI is rendered for the first time (is_discovered and dungeon type)
poi_def = getattr(b, 'poi_def', None)
if poi_def and poi_def.interaction_type == 'dungeon':
    area_id = f"underground_{b.grid_x}_{b.grid_y}"
    if area_id not in self._underground_mgr._area_entities:
        # Find the matching underground area
        ug_areas = getattr(self._sim_engine, 'underground_areas', {})
        area = ug_areas.get(area_id)
        if area and area.is_generated:
            self._underground_mgr.create_underground_mesh(area, scene)
            self._underground_mgr.create_stalactites(area, scene)
```

**IMPORTANT**: You need access to `self._sim_engine` or pass underground_areas through the snapshot. Check how `UrsinaRenderer` receives game state (likely via a snapshot object or direct reference).

### Verification Steps (Wave 2)

1. **Tests pass**: `python tools/qa_smoke.py --quick` — must PASS
2. **Visual check**: Launch `python main.py --provider mock`. Set env var `KINGDOM_DEBUG_SHOW_ALL_POIS=1` to force-discover all POIs. Look for:
   - Cave entrance POIs should have visible holes in the surface terrain (dark circles where fragments are discarded)
   - Underground mesh should be visible through the holes (dark brownish cave floor below)
   - Stalactites should hang from ceiling level
3. **Screenshot capture**: Take a screenshot near a cave entrance showing the hole + underground below:
   ```
   python tools/run_ursina_capture_once.py --seconds 10 --subdir wk57_wave2 --stem cave_hole --no-llm
   ```
4. **No crash on maps without caves**: If no cave POIs exist (or none discovered), the game should run identically to before.

---

## Wave 3 — Camera Layer System + Underground Lighting

**Agent:** 03 (TechnicalDirector)
**Intelligence:** HIGH
**Purpose:** Camera transitions between surface and underground layers. Underground has dark ambient + torch lights.

### Files to Read First
- `game/graphics/ursina_app.py` — camera setup (lines 133-135), camera controls, `sim_px_to_world_xz`
- `game/graphics/ursina_renderer.py` lines 330-351 — current lighting (AmbientLight + DirectionalLight)
- `game/underground.py` (after Wave 1/2) — chamber positions for torch placement
- `config.py` — UNDERGROUND_* constants

### Task 3A: Camera Layer Awareness in `game/graphics/ursina_app.py`

Add layer tracking to the UrsinaApp camera controller. The camera has an `active_layer` state (0=surface, -1=underground). Add these instance variables and methods:

```python
# In __init__ or camera setup:
self._camera_active_layer = 0
self._camera_transitioning = False
self._camera_transition_target_y = None
self._camera_transition_speed = 0.0
self._camera_surface_y = None  # stored when descending
```

Add a public method for other systems to trigger layer transitions:
```python
def begin_camera_underground_transition(self, target_y: float):
    """Start smooth camera descent to underground level."""
    from config import UNDERGROUND_CAMERA_TRANSITION_SPEED
    self._camera_surface_y = camera.y
    self._camera_transition_target_y = target_y
    self._camera_transition_speed = UNDERGROUND_CAMERA_TRANSITION_SPEED
    self._camera_transitioning = True
    self._camera_active_layer = -1

def begin_camera_surface_transition(self):
    """Start smooth camera ascent back to surface."""
    from config import UNDERGROUND_CAMERA_TRANSITION_SPEED
    if self._camera_surface_y is not None:
        self._camera_transition_target_y = self._camera_surface_y
    else:
        self._camera_transition_target_y = 30.0  # reasonable default
    self._camera_transition_speed = UNDERGROUND_CAMERA_TRANSITION_SPEED
    self._camera_transitioning = True
    self._camera_active_layer = 0
```

In the camera update method (wherever camera position is updated each frame), add transition lerp:
```python
if self._camera_transitioning and self._camera_transition_target_y is not None:
    dy = self._camera_transition_target_y - camera.y
    if abs(dy) < 0.5:
        camera.y = self._camera_transition_target_y
        self._camera_transitioning = False
        self._camera_transition_target_y = None
    else:
        step = self._camera_transition_speed * time.dt
        camera.y += step if dy > 0 else -step

@property
def camera_active_layer(self) -> int:
    return self._camera_active_layer
```

### Task 3B: Underground Lighting in `game/graphics/ursina_renderer.py`

Add torch point lights and ambient adjustment for underground areas. In `UrsinaRenderer.__init__`, add:

```python
self._underground_lights: list = []  # Panda3D PointLight NodePaths
self._underground_ambient = None
self._surface_ambient_color = None  # store original to restore
```

Add methods to create/destroy underground lighting:

```python
def _create_underground_lighting(self, area, base_wx, base_wz):
    """Create dark ambient + torch point lights for an underground area."""
    from panda3d.core import PointLight as PandaPointLight, Vec4, Vec3
    from config import (
        UNDERGROUND_TORCH_COLOR, UNDERGROUND_TORCH_INTENSITY,
        UNDERGROUND_TORCH_ATTENUATION, UNDERGROUND_DEPTH,
    )
    
    cx = area.total_width // 2
    for ch in area.chambers:
        # Place a torch at the center of each chamber
        gx = cx + ch.world_offset_x + ch.width // 2
        gz = ch.world_offset_z + ch.height // 2
        
        wx = (gx - cx) * 1.0 + base_wx
        wz = -gz * 1.0 + base_wz
        wy = -UNDERGROUND_DEPTH + 3.0  # torch height above cave floor
        
        pl = PandaPointLight(f"torch_{area.area_id}_{ch.chamber_id}")
        r, g, b = UNDERGROUND_TORCH_COLOR
        pl.setColor(Vec4(r * UNDERGROUND_TORCH_INTENSITY,
                         g * UNDERGROUND_TORCH_INTENSITY,
                         b * UNDERGROUND_TORCH_INTENSITY, 1.0))
        a1, a2, a3 = UNDERGROUND_TORCH_ATTENUATION
        pl.setAttenuation(Vec3(a1, a2, a3))
        
        plnp = render.attachNewNode(pl)
        plnp.setPos(wx, wy, wz)
        render.setLight(plnp)
        self._underground_lights.append(plnp)

def _remove_underground_lighting(self):
    """Remove all torch lights."""
    for plnp in self._underground_lights:
        render.clearLight(plnp)
        plnp.removeNode()
    self._underground_lights.clear()
```

### Task 3C: Layer-Aware Entity Visibility

In the renderer's entity sync methods (hero sync, enemy sync, building sync), add a layer check: only render entities whose `layer` matches the camera's active layer.

```python
# In hero sync loop:
hero_layer = getattr(hero_data, 'layer', 0)
if hero_layer != self._app.camera_active_layer:
    # Hide this hero entity
    if ent:
        ent.enabled = False
    continue
```

Apply the same pattern to enemy sync, peasant sync, building sync, etc. Surface buildings should be hidden when camera is underground; underground entities should be hidden when camera is on surface.

### Verification Steps (Wave 3)

1. **Tests pass**: `python tools/qa_smoke.py --quick`
2. **Visual check**: Launch the game with `KINGDOM_DEBUG_SHOW_ALL_POIS=1`. Verify:
   - Surface looks normal (same lighting as before)
   - When triggering an underground transition (may need to temporarily hardcode a test trigger), the camera descends smoothly
   - Underground is darker with warm torch lights at chamber positions
   - Surface entities disappear while camera is underground
3. **No light leaks**: Surface ambient light should not illuminate underground mesh. Underground torches should not illuminate surface.

---

## Wave 4 — Layer-Aware Pathfinding + Underground Fog

**Agent:** 05 (GameplaySystemsDesigner)
**Intelligence:** HIGH
**Purpose:** Extend A* pathfinding to support layer transitions at cave entrances. Add per-area underground fog of war.

### Files to Read First
- `game/systems/pathfinding.py` (214 lines) — current A* implementation
- `game/world.py` — `Visibility` enum, `visibility` grid, `_reveal_circle()`, fog management
- `game/underground.py` (after Wave 1) — `UndergroundArea.walkability` grid, chamber layout
- `game/sim_engine.py` — `self.underground_areas` dict
- `config.py` — `POI_DISCOVERY_RANGE_TILES`, UNDERGROUND_* constants

### Task 4A: Layer-Aware A* in `game/systems/pathfinding.py`

The current pathfinder uses `(x, y)` tuples as nodes. Extend to `(x, y, layer)` where layer=0 is surface and layer=-1 is underground.

**Key changes:**

1. The path cache key must include layer: `(start_x, start_y, start_layer, goal_x, goal_y, goal_layer)`.

2. The `_neighbors()` function must:
   - For surface nodes (layer=0): return normal 8-directional surface neighbors + cave entrance transition nodes
   - For underground nodes (layer=-1): return underground walkability-grid neighbors + ascent transition at entrance chamber

3. The `_is_walkable()` function must:
   - For layer=0: use existing `world.is_walkable(x, y)` (unchanged)
   - For layer=-1: use `underground_area.walkability[z][x]` where (x, z) are relative to the area origin

4. Cave entrance transition: when the pathfinder is at a surface tile that overlaps a cave entrance POI, add a neighbor `(entrance_x, entrance_y, -1)` representing descent. From the underground entrance chamber tile, add a neighbor `(entrance_x, entrance_y, 0)` representing ascent.

**Implementation approach — add a `LayerPathfinder` wrapper that delegates to the existing pathfinder for same-layer paths and handles cross-layer routing:**

```python
class LayerPathfinder:
    """Layer-aware pathfinding wrapper.
    
    For same-layer paths, delegates to the existing find_path().
    For cross-layer paths (surface to underground), routes through
    the nearest cave entrance.
    """
    
    def __init__(self, world, underground_areas: dict):
        self._world = world
        self._underground_areas = underground_areas
        self._cave_entrances = {}  # (grid_x, grid_y) -> area_id
        
        for area_id, area in underground_areas.items():
            self._cave_entrances[(area.entrance_grid_x, area.entrance_grid_y)] = area_id
    
    def find_path(self, start_x, start_y, start_layer, goal_x, goal_y, goal_layer):
        """Find path between any two points, potentially across layers.
        
        Returns list of (x, y, layer) tuples, or empty list if no path.
        """
        if start_layer == goal_layer == 0:
            # Pure surface path — delegate to existing pathfinder
            from game.systems.pathfinding import find_path
            path = find_path(self._world, start_x, start_y, goal_x, goal_y)
            return [(x, y, 0) for x, y in path] if path else []
        
        if start_layer == goal_layer == -1:
            # Pure underground path within same area
            return self._find_underground_path(start_x, start_y, goal_x, goal_y)
        
        if start_layer == 0 and goal_layer == -1:
            # Surface to underground: route to cave entrance, then descend, then underground path
            # Find which cave entrance connects to the goal's underground area
            area = self._find_area_for_underground_pos(goal_x, goal_y)
            if area is None:
                return []
            entrance = (area.entrance_grid_x, area.entrance_grid_y)
            
            # Surface path to entrance
            from game.systems.pathfinding import find_path
            surface_path = find_path(self._world, start_x, start_y, entrance[0], entrance[1])
            if not surface_path:
                return []
            
            # Underground path from entrance to goal
            ug_path = self._find_underground_path(entrance[0], entrance[1], goal_x, goal_y)
            
            result = [(x, y, 0) for x, y in surface_path]
            result.extend(ug_path)
            return result
        
        if start_layer == -1 and goal_layer == 0:
            # Underground to surface: underground path to entrance, ascend, then surface path
            area = self._find_area_for_underground_pos(start_x, start_y)
            if area is None:
                return []
            entrance = (area.entrance_grid_x, area.entrance_grid_y)
            
            ug_path = self._find_underground_path(start_x, start_y, entrance[0], entrance[1])
            
            from game.systems.pathfinding import find_path
            surface_path = find_path(self._world, entrance[0], entrance[1], goal_x, goal_y)
            if not surface_path:
                return ug_path  # at least get to entrance
            
            result = list(ug_path)
            result.extend([(x, y, 0) for x, y in surface_path])
            return result
        
        return []
    
    def _find_underground_path(self, start_x, start_y, goal_x, goal_y):
        """A* pathfinding within an underground area using the walkability grid."""
        # Find which area these coords belong to
        area = self._find_area_for_underground_pos(start_x, start_y)
        if area is None:
            area = self._find_area_for_underground_pos(goal_x, goal_y)
        if area is None:
            return []
        
        # Convert world grid coords to underground local coords
        cx = area.total_width // 2
        
        def to_local(gx, gy):
            return (gx - area.entrance_grid_x + cx, gy - area.entrance_grid_y)
        
        def to_world(lx, lz):
            return (lx - cx + area.entrance_grid_x, lz + area.entrance_grid_y)
        
        sx, sz = to_local(start_x, start_y)
        gx, gz = to_local(goal_x, goal_y)
        
        # Simple A* on the walkability grid
        import heapq
        
        def heuristic(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
        
        start = (sx, sz)
        goal = (gx, gz)
        
        open_set = [(heuristic(start, goal), 0, start)]
        came_from = {}
        g_score = {start: 0}
        
        while open_set:
            _, _, current = heapq.heappop(open_set)
            
            if current == goal:
                # Reconstruct path
                path = []
                while current in came_from:
                    wx, wy = to_world(*current)
                    path.append((wx, wy, -1))
                    current = came_from[current]
                wx, wy = to_world(*current)
                path.append((wx, wy, -1))
                path.reverse()
                return path
            
            for dx, dz in [(-1,0),(1,0),(0,-1),(0,1)]:
                nx, nz = current[0]+dx, current[1]+dz
                if 0 <= nx < area.total_width and 0 <= nz < area.total_height:
                    if not area.walkability[nz][nx]:
                        continue
                    new_g = g_score[current] + 1
                    if (nx, nz) not in g_score or new_g < g_score[(nx, nz)]:
                        g_score[(nx, nz)] = new_g
                        f = new_g + heuristic((nx, nz), goal)
                        heapq.heappush(open_set, (f, new_g, (nx, nz)))
                        came_from[(nx, nz)] = current
        
        return []  # no path found
    
    def _find_area_for_underground_pos(self, world_gx, world_gy):
        """Find which UndergroundArea contains the given world grid position."""
        for area in self._underground_areas.values():
            # Check if pos is within area bounds
            dx = world_gx - area.entrance_grid_x
            dy = world_gy - area.entrance_grid_y
            cx = area.total_width // 2
            lx = dx + cx
            lz = dy
            if 0 <= lx < area.total_width and 0 <= lz < area.total_height:
                if area.walkability[lz][lx]:
                    return area
        return None
```

Register the `LayerPathfinder` in `sim_engine.py` after underground areas are generated:
```python
from game.systems.pathfinding import LayerPathfinder
self.layer_pathfinder = LayerPathfinder(self.world, self.underground_areas)
```

### Task 4B: Underground Fog of War in `game/world.py`

Add a per-underground-area visibility grid to World:

```python
# In World.__init__:
self.underground_visibility: dict[str, list[list[int]]] = {}
# area_id -> 2D grid of Visibility values (UNSEEN/SEEN/VISIBLE)
```

Add methods:
```python
def init_underground_fog(self, area):
    """Create a fresh UNSEEN visibility grid for an underground area."""
    grid = [[Visibility.UNSEEN for _ in range(area.total_width)]
            for _ in range(area.total_height)]
    self.underground_visibility[area.area_id] = grid

def reveal_underground_circle(self, area_id, local_x, local_z, radius):
    """Reveal underground fog in a circle around (local_x, local_z)."""
    grid = self.underground_visibility.get(area_id)
    if grid is None:
        return
    h = len(grid)
    w = len(grid[0]) if h > 0 else 0
    r2 = radius * radius
    for dz in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dz * dz <= r2:
                gz = local_z + dz
                gx = local_x + dx
                if 0 <= gz < h and 0 <= gx < w:
                    grid[gz][gx] = Visibility.VISIBLE
```

In `sim_engine.py`, after generating underground areas, init their fog:
```python
for area_id, area in self.underground_areas.items():
    self.world.init_underground_fog(area)
```

### Verification Steps (Wave 4)

1. **Tests pass**: `python tools/qa_smoke.py --quick`
2. **Pathfinding test**: Add a test to `tests/test_underground.py` (create this file if it doesn't exist):

```python
def test_layer_pathfinder_surface_only():
    """Surface-only path works through LayerPathfinder."""
    # Create minimal world mock, call layer_pathfinder.find_path with layer=0
    # Assert path is non-empty and all nodes have layer=0

def test_layer_pathfinder_cross_layer():
    """Path from surface to underground routes through cave entrance."""
    # Create world with a cave entrance POI + underground area
    # Call find_path(surface_x, surface_y, 0, underground_x, underground_y, -1)
    # Assert path includes layer transition at entrance coords

def test_underground_fog_reveal():
    """Underground fog reveals correctly around hero position."""
    # Create underground area, init fog
    # Call reveal_underground_circle at a position
    # Assert nearby cells are VISIBLE, far cells are UNSEEN
```

Run: `python -m pytest tests/test_underground.py -v`

---

## Wave 5 — Hero Transitions + Underground Spawning + AI Cave Exploration

**Agent:** 05 (GameplaySystemsDesigner)
**Intelligence:** HIGH
**Purpose:** Heroes descend/ascend at cave entrances, enemies spawn underground, AI drives autonomous cave exploration.

### Files to Read First
- `game/entities/hero.py` — Hero class, states, movement
- `game/entities/enemy.py` — Enemy class, spawning
- `game/systems/poi_interaction.py` lines for dungeon handler — currently emits flavor text only
- `ai/behaviors/poi_awareness.py` — `score_poi_for_personality()`, `maybe_visit_poi()`
- `game/underground.py` (after Wave 1) — chamber enemy lists
- `game/sim_engine.py` — entity lifecycle, `underground_areas` dict

### Task 5A: Hero Descent/Ascent State Machine

Add hero states for underground transition. In `game/entities/hero.py`:

```python
# Add to the HeroState enum (or wherever states are defined):
DESCENDING = "descending"
ASCENDING = "ascending"
UNDERGROUND_IDLE = "underground_idle"
UNDERGROUND_MOVING = "underground_moving"
UNDERGROUND_FIGHTING = "underground_fighting"
```

Add underground tracking fields to Hero `__init__`:
```python
self.underground_area_id: str | None = None  # which area hero is in
self.underground_local_x: int = 0  # position in area local coords
self.underground_local_z: int = 0
```

Add transition methods:
```python
def begin_descent(self, area_id: str, entrance_x: int, entrance_y: int):
    """Start descending into an underground area."""
    self.layer = -1
    self.underground_area_id = area_id
    self.underground_local_x = 0  # entrance chamber position
    self.underground_local_z = 0
    # Set state to DESCENDING (transition animation)
    # After animation completes, set to UNDERGROUND_IDLE

def begin_ascent(self):
    """Start ascending back to surface."""
    self.layer = 0
    self.underground_area_id = None
    # Set state to ASCENDING (transition animation)
    # After animation completes, set to IDLE
```

### Task 5B: Wire Cave Entry into POI Interaction System

In `game/systems/poi_interaction.py`, modify the `dungeon` handler. Currently it just emits flavor text. Replace with actual cave entry logic:

```python
def _handle_dungeon(self, hero, poi, world, economy, event_bus):
    """Handle hero entering a dungeon (cave/mine) POI."""
    area_id = f"underground_{poi.grid_x}_{poi.grid_y}"
    
    # Get the underground area from sim_engine
    # (you'll need to pass underground_areas to the interaction system)
    area = self._underground_areas.get(area_id)
    if area is None or not area.is_generated:
        return  # no underground area generated for this POI
    
    if hero.layer == -1:
        return  # already underground
    
    # Begin descent
    hero.begin_descent(area_id, poi.grid_x, poi.grid_y)
    
    # Mark first chamber as explored
    if area.chambers:
        area.chambers[0].is_explored = True
    
    # Reveal underground fog at entrance
    cx = area.total_width // 2
    world.reveal_underground_circle(area_id, cx, 0, 4)
    
    event_bus.emit("hero_entered_underground", hero=hero, area_id=area_id, poi=poi)
```

### Task 5C: Underground Enemy Spawning

When a hero enters an underground area, spawn enemies in unexplored chambers. In the sim tick (or in a new `underground_system.py`):

```python
def spawn_underground_enemies(area, world, enemy_spawner, event_bus):
    """Spawn enemies in underground chambers when hero enters."""
    for ch in area.chambers:
        if ch.is_explored or ch.is_cleared:
            continue
        for enemy_type in ch.enemies:
            # Spawn enemy at chamber center, on layer -1
            cx = area.total_width // 2 + ch.world_offset_x + ch.width // 2
            cz = ch.world_offset_z + ch.height // 2
            # Convert local coords to world grid coords
            world_gx = cx - area.total_width // 2 + area.entrance_grid_x
            world_gy = cz + area.entrance_grid_y
            enemy = enemy_spawner.spawn_enemy(enemy_type, world_gx, world_gy)
            if enemy:
                enemy.layer = -1
```

### Task 5D: AI Cave Exploration

In `ai/behaviors/poi_awareness.py`, modify `score_poi_for_personality()` to give dungeon POIs special scoring:

```python
# In score_poi_for_personality, add handling for dungeon POIs:
if poi_def.interaction_type == "dungeon":
    # Bold heroes are attracted to caves
    if personality_archetype == "aggressive":
        base_score *= 1.5
    # Cautious heroes avoid unless strong
    elif personality_archetype == "cautious":
        if hero.level < poi_def.difficulty_tier * 2:
            base_score *= 0.2  # strongly discourage
        else:
            base_score *= 0.8
    # Don't enter caves when hurt
    if hero.hp < hero.max_hp * 0.7:
        base_score *= 0.1
```

In `maybe_visit_poi()`, when a hero decides to visit a dungeon POI, make sure the movement target is the cave entrance tile (not the interior):

```python
# When hero decides to visit a dungeon POI:
if target_poi.poi_def.interaction_type == "dungeon":
    # Movement target is the entrance tile
    target_x = target_poi.grid_x * TILE_SIZE + TILE_SIZE // 2
    target_y = target_poi.grid_y * TILE_SIZE + TILE_SIZE // 2
    hero.move_to(target_x, target_y)
    # Actual entry happens via poi_interaction when hero arrives
```

### Task 5E: Underground Hero Ascent Trigger

Add logic for heroes to decide to leave the underground. In the underground AI tick:

```python
def check_underground_hero_retreat(hero, area):
    """Check if hero should retreat from underground."""
    if hero.layer != -1 or hero.underground_area_id is None:
        return False
    
    # Retreat if low HP
    if hero.hp < hero.max_hp * 0.3:
        hero.begin_ascent()
        return True
    
    # Retreat if all chambers explored/cleared
    all_cleared = all(ch.is_cleared for ch in area.chambers)
    if all_cleared:
        hero.begin_ascent()
        return True
    
    return False
```

### Verification Steps (Wave 5)

1. **Tests pass**: `python tools/qa_smoke.py --quick`
2. **Unit tests** in `tests/test_underground.py`:

```python
def test_hero_descent_sets_layer():
    hero = create_test_hero()
    assert hero.layer == 0
    hero.begin_descent("test_area", 50, 50)
    assert hero.layer == -1
    assert hero.underground_area_id == "test_area"

def test_hero_ascent_restores_layer():
    hero = create_test_hero()
    hero.begin_descent("test_area", 50, 50)
    hero.begin_ascent()
    assert hero.layer == 0
    assert hero.underground_area_id is None

def test_underground_enemy_spawn():
    # Create area with chambers containing enemies
    # Call spawn_underground_enemies
    # Assert enemies created with layer=-1
```

3. **Integration test**: Launch `python main.py --provider mock` with `KINGDOM_DEBUG_SHOW_ALL_POIS=1`. Walk a hero to a cave entrance (via direct prompt "explore the cave"). Verify:
   - Hero descends (position changes to underground level)
   - Camera follows to underground
   - Underground enemies appear
   - Hero can fight underground enemies
   - Hero retreats when hurt

---

## Wave 6 — QA + Performance Verification

**Agent:** 11 (QA) — runs gates + visual verification
**Agent:** 10 (Performance) — runs perf benchmark
**Intelligence:** LOW for both (well-defined gate runs)

### Agent 10 Tasks

1. **Run perf stress test**: `python -m tests.perf_ursina_stress` (if available)
   - Record FPS with and without underground meshes visible
   - Check that underground terrain doesn't tank FPS below 25 (with 20 heroes)

2. **Memory check**: Note total entity count with underground meshes created vs. without

3. **Report**: Record findings in Agent 10 log

### Agent 11 Tasks

1. **Run full gate stack**:
   ```
   python tools/qa_smoke.py --quick
   python tools/validate_assets.py --report
   ```
   Both must PASS.

2. **Run underground tests**:
   ```
   python -m pytest tests/test_underground.py -v
   ```
   All must PASS.

3. **Visual verification** — capture screenshots:
   ```
   KINGDOM_DEBUG_SHOW_ALL_POIS=1 python tools/run_ursina_capture_once.py --seconds 15 --subdir wk57_final --stem underground --no-llm
   ```
   Check for:
   - Surface terrain has visible holes at cave entrance locations
   - Underground mesh visible through holes
   - No z-fighting or visual artifacts at hole edges
   - Stalactites visible in underground
   - Torch lighting visible when camera is underground

4. **Regression check**:
   - Hero selection works on surface
   - Combat works on surface
   - POI discovery works for non-dungeon POIs
   - Minimap works
   - Building construction works
   - Fog of war works on surface

5. **Report**: Record all pass/fail results + screenshots in Agent 11 log

---

## Definition of Done

All of these must be true:

- [ ] `python tools/qa_smoke.py --quick` PASSES (307+ tests, zero failures)
- [ ] `python tools/validate_assets.py --report` PASSES (zero errors)
- [ ] `python -m pytest tests/test_underground.py -v` PASSES (all underground tests green)
- [ ] Surface terrain has visible cave entrance holes (shader discard working)
- [ ] Underground terrain mesh renders below surface through cave holes
- [ ] Underground has procedural cave terrain (Perlin noise floor, not flat)
- [ ] Stalactite decorations visible in underground
- [ ] Camera smoothly transitions between surface and underground
- [ ] Underground is darker than surface (ambient lighting change)
- [ ] Torch point lights illuminate underground chambers
- [ ] Heroes can descend into caves via POI interaction
- [ ] Heroes can ascend back to surface
- [ ] Layer-aware pathfinding routes through cave entrances
- [ ] Underground has separate fog of war (revealed by hero movement)
- [ ] Underground enemies spawn from chamber data
- [ ] AI-driven heroes can autonomously enter caves (personality-based)
- [ ] No FPS regression below 25 FPS with 20 heroes on surface
- [ ] No visual regressions on surface gameplay (selection, combat, buildings, fog)

---

## Human Gates

1. **Visual approval**: Jaimie reviews cave hole rendering + underground visuals
2. **Manual playtest**: Jaimie directs a hero to explore a cave and observes the experience
3. **Version bump**: If satisfied, Jaimie decides version number
4. **Commit/push**: Agent 01 proposes save-state, Jaimie approves

---

## Integration Order

```
Wave 1 (Agent 03) → Wave 2 (Agent 03) → Wave 3 (Agent 03)
                                              ↓
                                        Wave 4 (Agent 05)
                                              ↓
                                        Wave 5 (Agent 05)
                                              ↓
                                        Wave 6 (Agent 10 + 11, parallel)
```

All waves are strictly sequential except Wave 6 (Agent 10 and 11 run in parallel).

---

## File Change Map

| File | Agent | Wave | Change Type |
|------|-------|------|-------------|
| `config.py` | 03 | 1 | Add UNDERGROUND_* constants |
| `game/underground.py` | 03 | 1 | Extend with world coords + layout |
| `game/graphics/terrain_fog_shader.py` | 03 | 1 | Add cave entrance discard |
| `game/graphics/ursina_terrain_fog_collab.py` | 03 | 1 | Shader uniform pipeline |
| `game/entities/hero.py` | 03 | 1 | Add `layer` field |
| `game/entities/enemy.py` | 03 | 1 | Add `layer` field |
| `game/graphics/underground_terrain.py` | 03 | 2 | NEW — cave mesh generation |
| `game/graphics/ursina_renderer.py` | 03 | 2-3 | Underground mesh integration + layer visibility + lighting |
| `game/graphics/ursina_app.py` | 03 | 3 | Camera layer transitions |
| `game/systems/pathfinding.py` | 05 | 4 | LayerPathfinder wrapper |
| `game/world.py` | 05 | 4 | Underground fog visibility |
| `game/sim_engine.py` | 05 | 4-5 | Underground fog init + pathfinder |
| `game/systems/poi_interaction.py` | 05 | 5 | Dungeon handler → actual cave entry |
| `ai/behaviors/poi_awareness.py` | 05 | 5 | AI cave exploration scoring |
| `tests/test_underground.py` | 05 | 4-5 | NEW — underground test suite |
