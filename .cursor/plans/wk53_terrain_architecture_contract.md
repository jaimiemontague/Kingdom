# WK53 Terrain Elevation Architecture Contract

> **Author:** Agent 03 (TechnicalDirector_Architecture)
> **Sprint:** wk53_world_beauty_terrain
> **Round:** wk53_r1_sky_fog_architecture (Wave 0)
> **Status:** LOCKED — Wave 2 implementation follows this contract

---

## 1. Heightmap Data Model

### Resolution
- **Sub-tile resolution: 2x per tile** — each tile contributes a 2x2 patch of height samples. For a 50x50 tile map this yields a 101x101 heightmap grid (vertices at tile corners and midpoints). For 100x100 tiles: 201x201 grid.
- This provides enough resolution for gentle hill slopes without excessive vertex count. Steep cliff faces still read correctly because the mesh is displaced per-vertex.
- The heightmap stores height values at grid intersections (fence-post pattern: `(tile_count * 2) + 1` samples per axis).

### Storage Format
- **In-memory:** Python `list[list[float]]` (2D array), indexed as `heightmap[gz][gx]` where `gx, gz` are grid indices (0..grid_width-1, 0..grid_height-1).
- **Persistent:** Not serialized to disk this sprint. The heightmap is generated deterministically from the map seed at world creation time, so it can be regenerated on load. If save/load is added later, store as a flat binary blob (2 bytes per sample, unsigned 16-bit, with a known scale factor).
- **Value range:** `[0.0, TERRAIN_HEIGHT_SCALE]` where `TERRAIN_HEIGHT_SCALE` is a config constant (default: 8.0 world units). Zero is the current flat ground plane; maximum is the tallest peak.

### Generation Algorithm
- **Perlin noise (layered octaves)** via the `noise` PyPI package (`from noise import pnoise2`).
  - **Octave 1 (hills):** frequency ~0.04, amplitude 1.0 — large rolling hills across the map.
  - **Octave 2 (ridges):** frequency ~0.10, amplitude 0.4 — medium mountain ridges.
  - **Octave 3 (detail):** frequency ~0.25, amplitude 0.15 — small rocky detail for texture.
- **Castle flattening:** Within a radius of ~5 tiles around the castle center, heights are smoothed toward a flat plateau (lerp toward the castle center height with a cosine falloff). This guarantees the starting area is buildable.
- **Map edge mountains (optional/stretch):** Apply a radial falloff that raises elevation near map edges, framing the world with natural mountain borders.
- **Seed:** Use the existing `MAP.seed` (config) so heightmap is deterministic across sessions.

### Integration with Map Generation
- Heightmap generation runs **after** `World.generate_terrain()` completes (tile types are already assigned). The heightmap is a post-processing step that adds Y-displacement to the existing flat tile grid.
- Stored on `World` as `world.heightmap: list[list[float]]` and `world.heightmap_grid_w: int`, `world.heightmap_grid_h: int`.
- Water tiles are clamped to a fixed "water level" height (e.g., `TERRAIN_WATER_LEVEL = 1.0`).

---

## 2. Terrain Mesh Approach

### Options Evaluated

| Approach | Pros | Cons |
|---|---|---|
| **Panda3D GeoMipTerrain** | Built-in LOD, handles large terrains efficiently, auto-generates from PNMImage heightmap | API complexity; LOD transitions can create seams; texture mapping is less flexible; mixing with Ursina Entity system requires manual wiring |
| **Custom Ursina `Mesh`** with heightmap-displaced vertices | Full control over vertex layout, UV mapping, and material; integrates natively with Ursina Entity/shader system; simple to implement for our scale | No built-in LOD (but at 50-100 tiles we don't need it); manual vertex generation code |
| **Multiple flat quads per tile, displaced** | Simplest code | Tile seams visible on slopes; no smooth interpolation; poor visual quality |

### Recommendation: Custom Ursina `Mesh` with heightmap-displaced vertices

**Rationale:**
- At 50x50 to 100x100 tiles with 2x sub-tile resolution, the mesh is 101x101 to 201x201 vertices. That is 10K-40K vertices — trivially within budget for any modern GPU.
- GeoMipTerrain's LOD is unnecessary at this scale and adds API complexity (PNMImage conversion, bruteForce mode for small maps, manual updates).
- Ursina `Mesh` integrates cleanly with the existing `Entity(model=mesh, ...)` pattern used for the terrain root.
- We keep full control over UV mapping (tiled grass texture) and can add per-vertex color for cliff/slope tinting later.

### Mesh Generation Details
- Generate a triangle-strip or indexed-triangle mesh covering the full map extent.
- Vertex positions: `(world_x, height, world_z)` sampled from the heightmap at each grid point.
- UV coordinates: tile the grass texture using `(gx / tiles_per_repeat, gz / tiles_per_repeat)`, matching the current ground plane's `texture_scale`.
- Normals: compute per-vertex normals from adjacent height samples (cross product of tangent vectors) for correct lighting on slopes.

---

## 3. Public API: `get_terrain_height(world_x, world_z) -> float`

### Function Signature
```python
def get_terrain_height(world_x: float, world_z: float) -> float:
    """Return the terrain elevation at the given world X/Z position.

    Uses bilinear interpolation between the four nearest heightmap grid points
    for smooth height values between grid samples.

    Returns 0.0 if the heightmap is not initialized or coords are out of bounds.
    """
```

### Location
- **New module: `game/graphics/terrain_height.py`**
- This module owns the heightmap data reference and the interpolation logic.
- It is imported by `ursina_terrain_fog_collab.py` (terrain mesh generation), `ursina_renderer.py` (entity Y-placement), `ursina_units_anim.py` (unit Y each frame), and `ursina_prefabs.py` (building Y-placement).
- The module holds a module-level reference to the active heightmap (set during terrain init, cleared on map change).

### Why not `ursina_coords.py`?
- `ursina_coords.py` is a pure math module (scale/flip transforms). Terrain height requires access to the heightmap data array and bilinear interpolation state. A separate module keeps concerns clean.

### How Entities Call It
```python
from game.graphics.terrain_height import get_terrain_height

# Buildings: sample once at placement
y = get_terrain_height(world_x, world_z)
entity.y = y

# Units: sample every frame (or on position change)
y = get_terrain_height(entity.x, entity.z)
entity.y = y
```

### Interpolation
- Convert `(world_x, world_z)` to heightmap grid coordinates using the inverse of the world-to-grid mapping.
- Bilinear interpolation between the four enclosing grid points.
- Out-of-bounds positions clamp to the nearest edge sample.

---

## 4. Fog-of-War on Non-Flat Terrain

### Options Evaluated

| Approach | Pros | Cons |
|---|---|---|
| **(a) Shader-based fog on terrain mesh** | Perfect surface conformance; no z-fighting; single draw call; fog is part of terrain rendering | Requires custom terrain fragment shader; fog texture sampling in shader adds complexity; harder to maintain for non-shader-experienced agents |
| **(b) Conforming fog mesh** that follows the heightmap at Y offset | Reuses existing fog-quad Entity pattern; fog texture is a separate overlay; easier to reason about | Z-fighting risk on steep slopes; requires generating a second mesh; double vertex memory |

### Recommendation: **(a) Shader-based fog on the terrain mesh itself**

**Rationale:**
- Z-fighting with a conforming overlay mesh is a real problem on steep slopes and would require per-frame offset tuning.
- The terrain mesh already needs a custom fragment shader for normal-mapped lighting. Adding fog-texture sampling is a single `texture2D()` call in the fragment shader with alpha blending.
- The fog texture (1px-per-tile, bilinear filtered) is already uploaded as a GPU texture. The terrain shader samples it using the tile-space UV coordinates and blends the fog color over the terrain albedo.
- This guarantees pixel-perfect fog conformance with zero additional geometry.

### Implementation Sketch
```glsl
// In terrain fragment shader:
uniform sampler2D fog_texture;  // 1px-per-tile fog overlay
varying vec2 v_tile_uv;        // UV in tile-space (0..1 across map)

void main() {
    vec4 terrain_color = texture2D(p3d_Texture0, v_uv);
    vec4 fog_sample = texture2D(fog_texture, v_tile_uv);
    // Pre-multiplied alpha blend: fog over terrain
    vec3 final_rgb = mix(terrain_color.rgb, fog_sample.rgb, fog_sample.a);
    gl_FragColor = vec4(final_rgb, 1.0);
}
```

### Transition Plan
- **This sprint (flat terrain):** Fog quad at Y=0.12 continues to work because terrain is flat. Bilinear filtering + grey mist colors are applied in R1.
- **Wave 2 (terrain mesh):** Replace fog quad with shader-based fog on the terrain mesh. The fog texture upload path (`TerrainTextureBridge.refresh_surface_texture`) stays the same; only the consumer changes from a separate Entity to a shader uniform.

---

## 5. Atmospheric Distance Fog

### History
- `scene.clearFog()` was introduced in SPRINT-BUG-008 because Panda3D's default **linear** fog combined with `lit_with_shadows_shader` caused horizontal banding artifacts.
- The banding was caused by the linear fog's per-vertex interpolation interacting with the shader's lighting pass — vertices at the same depth but different screen-Y received different fog factors.

### Recommendation: Panda3D **Exponential** Fog

**Implementation (done in R1):**
```python
from panda3d.core import Fog as PandaFog
fog = PandaFog("atmospheric_distance_fog")
fog.setColor(sky_r, sky_g, sky_b, 1.0)
fog.setExpDensity(0.008)
base.render.setFog(fog)
```

**Why exponential works where linear failed:**
- Exponential fog computes `fog_factor = exp(-density * distance)` which is purely distance-based. Unlike linear fog (which interpolates between near/far planes), exponential fog has no "near plane" that can create a sharp boundary — the factor is a smooth monotonic curve.
- The per-vertex interpolation artifacts that caused banding with linear fog are eliminated because the exponential curve is smooth and continuous.
- Density 0.008 is tuned so that at the typical camera distance for 60% of the map (~120 world units) the fog factor is ~0.38 (38% fogged), and at the far edge (~300 world units) it reaches ~0.91 (91% fogged). This gives clear terrain nearby with a natural atmospheric fade.

### Fallback: Fragment-Shader Distance Fade
If exponential fog re-introduces banding on specific GPU drivers (not observed in testing):
```glsl
// Per-fragment distance fog (compute in fragment shader, not vertex)
float dist = length(v_world_pos - camera_pos);
float fog_factor = 1.0 - exp(-fog_density * dist);
final_color = mix(fragment_color, fog_color, fog_factor);
```
This computes fog per-pixel instead of per-vertex, eliminating any interpolation artifacts. It requires a custom shader on all scene objects, so it is the fallback, not the default.

### Testing Notes
- R1 implements exponential fog with density 0.008 and sky-blue color (0.53, 0.72, 0.88).
- If banding is reported during Jaimie's visual review (Wave 1 human gate), switch to fragment-shader approach.
- The `scene.clearFog()` call is preserved as the error-handling fallback in `ursina_app.py`.

---

## 6. File Ownership Map (Wave 2 Terrain Implementation)

| File | Action | Owner | Description |
|---|---|---|---|
| `game/graphics/terrain_height.py` | **CREATE** | Agent 03 | Heightmap data model, `get_terrain_height()` API, bilinear interpolation |
| `game/world.py` | MODIFY | Agent 03 | Add heightmap generation after `generate_terrain()`, store `self.heightmap` |
| `game/graphics/ursina_terrain_fog_collab.py` | MODIFY | Agent 03 | Replace flat ground plane with heightmap-displaced mesh; terrain shader with fog-texture sampling |
| `game/graphics/ursina_renderer.py` | MODIFY | Agent 03 | Wire `get_terrain_height()` into entity Y-placement for buildings, units, props |
| `game/graphics/ursina_units_anim.py` | MODIFY | Agent 03 | Unit Y-placement per frame using `get_terrain_height()` |
| `game/graphics/ursina_prefabs.py` | MODIFY | Agent 03 | Building prefab Y-placement at construction |
| `game/graphics/ursina_environment.py` | MODIFY | Agent 03 | Prop (tree/rock/grass) Y-placement at terrain build time |
| `config.py` | MODIFY | Agent 03 | Add `TERRAIN_HEIGHT_SCALE`, `TERRAIN_HILL_FREQUENCY`, `TERRAIN_MOUNTAIN_FREQUENCY`, `TERRAIN_CLIFF_THRESHOLD`, `TERRAIN_WATER_LEVEL` |
| `requirements.txt` | MODIFY | Agent 03 | Add `noise` package for Perlin noise generation |

### Files NOT Touched
- `game/entities/**` — Entity logic stays flat; elevation is render-only
- `game/sim_engine.py` — Simulation stays 2D
- `game/ui/**` — No UI changes
- `game/ai/**` — No AI changes
- `assets/prefabs/**` — No prefab edits

---

## Appendix: Entity Y-Placement Diagram

```
                    +--------------------------+
                    |   World.generate_terrain  |
                    |   (tile types: grass,     |
                    |    water, tree, path)     |
                    +-----------+--------------+
                                |
                    +-----------v--------------+
                    |   World.generate_heightmap |
                    |   (Perlin noise octaves,  |
                    |    castle flattening)     |
                    +-----------+--------------+
                                |
                    +-----------v--------------+
                    |   terrain_height.py       |
                    |   _heightmap = world.hm   |
                    |   get_terrain_height(x,z) |
                    +-----------+--------------+
                          |     |     |
              +-----------+     |     +-------------+
              |                 |                    |
    +---------v------+  +------v--------+  +--------v--------+
    | ursina_terrain_ |  | ursina_       |  | ursina_units_   |
    | fog_collab.py   |  | renderer.py   |  | anim.py         |
    | (terrain mesh   |  | (building +   |  | (unit Y each    |
    |  + fog shader)  |  |  prop Y)      |  |  frame)         |
    +-----------------+  +---------------+  +-----------------+
```

Every entity that needs a world-Y coordinate calls `get_terrain_height(world_x, world_z)`. There is exactly one source of truth for terrain elevation.
