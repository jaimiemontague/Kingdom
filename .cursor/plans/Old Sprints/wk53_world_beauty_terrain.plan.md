# Sprint WK53 — World Beauty & Terrain Elevation

> **Status:** DRAFT — awaiting Jaimie review  
> **Version target:** TBD (after v1.5.5)  
> **Theme:** Make the world prettier — blue sky, misty fog, and elevation (hills, mountains, cliffs)

---

## Goal

Transform the flat, dark-edged game world into a visually rich environment with a blue sky, atmospheric mist fog-of-war, and terrain elevation that gives the map hills, mountains, and cliffs.

## Player-Facing Changes (What Jaimie Will See)

1. **Blue sky:** The background color is sky blue instead of near-black. When the camera tilts toward the horizon or looks past the map edge, the player sees sky, not void.
2. **Misty fog of war:** Unexplored areas fade into a soft grey mist (not hard black tiles). The transition from visible → fog is a smooth gradient, not a pixel-sharp tile edge. Fully explored-but-not-visible tiles show a lighter mist tint (currently semi-transparent black).
3. **Terrain elevation:** The map is no longer flat. Gentle hills roll across the landscape, rocky mountains rise at the map edges or in specific zones, and cliffs create natural barriers. Buildings, trees, heroes, and enemies sit at the correct height on the terrain.

## Current State (What Exists Today)

| Element | Current implementation | File |
|---|---|---|
| Background/sky | Solid dark gray-blue (`0.06, 0.07, 0.09`) | `game/graphics/ursina_app.py:79-84` |
| Fog of war | 2D quad overlay on ground (Y=0.12), 1px-per-tile texture, nearest-neighbor filtering. Black for UNSEEN (alpha 0xFF), semi-transparent black for SEEN, transparent for VISIBLE. Hard tile edges. | `game/graphics/ursina_terrain_fog_collab.py:49-162` |
| Off-map area | No geometry — clear color shows through | Same as background |
| Terrain | Flat ground plane with tiled grass texture (`floor_ground_grass.png`). Discrete `.glb` meshes for paths, water. Props (trees, rocks, grass clumps) scattered on flat plane. | `game/graphics/ursina_terrain_fog_collab.py:326-541` |
| Atmospheric fog | Explicitly cleared (`scene.clearFog()`) — was causing horizontal banding artifacts with lit_with_shadows_shader | `game/graphics/ursina_app.py:73` |
| Camera | Perspective (42° FOV), EditorCamera orbit/pan, near=0.1 far=10000 | `game/graphics/ursina_app.py:94-96, 266-435` |

## Scope

### In scope
- Sky-blue clear color
- Fog-of-war visual rework: grey mist color, smooth gradient edges (bilinear or blur), atmospheric distance fog layered on top
- Heightmap-based terrain mesh replacing the flat ground plane
- Perlin noise (or similar) height generation integrated into map generation
- Hills (gentle slopes), mountains (steep, tall), cliffs (near-vertical faces)
- All entities (buildings, trees, units, props) placed at correct Y based on heightmap
- Fog-of-war quad adjusted to follow terrain elevation (or rendered in a way that works with non-flat terrain)
- Performance must remain playable (terrain mesh within budget)

### Out of scope (future sprints)
- Gameplay effects of elevation (pathfinding cost, combat advantages, building placement restrictions) — consult only this sprint, implementation later
- Biome-specific textures per region (grass → rock → snow blending) — stretch goal only
- Water bodies / rivers shaped by elevation
- Cave/tunnel systems
- Elevation-aware fog of war (LOS blocked by mountains) — game-mechanic fog stays tile-based for now

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Terrain mesh too heavy for perf budget | Frame drops, especially in frozen .exe | Agent 03 uses LOD or GeoMipTerrain; Agent 10 benchmarks. Keep vertex count bounded. |
| Fog-of-war quad doesn't work on non-flat terrain | Visual artifacts — fog floating above valleys, clipping through hills | Two options: (a) project fog as a shader effect on the terrain mesh itself, or (b) use a conforming fog mesh that follows the heightmap. Agent 03 decides. |
| Atmospheric fog re-introduces banding artifacts | Horizontal bands when combined with lit_with_shadows_shader | Agent 03 must test atmospheric fog carefully. If banding returns, use exponential fog or fragment-shader distance fog instead of Panda3D linear fog. |
| Entity Y-placement jitter | Buildings/units snapping to wrong height, floating, or sinking | Heightmap sample function must be precise; Agent 03 provides a single `get_terrain_height(world_x, world_z) -> float` API that all placement code uses. |
| Steep terrain breaks building footprints | A 2×2 building placed on a cliff slope looks wrong | This sprint: buildings only place on "flat enough" terrain (slope check). Full gameplay gating is out-of-scope but the data is available. |

## Waves

### Wave 0 — Design & Contracts (no game code)

**Agents:** 03 (TechnicalDirector), 05 (GameplaySystemsDesigner)

**Agent 03 — Terrain elevation architecture contract:**
- Design the heightmap data model: resolution (per-tile? sub-tile?), storage format, generation algorithm (Perlin noise recommended), and how it integrates with existing `MapGenerator`.
- Define the terrain mesh approach: Panda3D `GeoMipTerrain`, custom vertex mesh, or Ursina `Mesh` with heightmap-sampled vertices. Evaluate each for this project's scale and recommend one.
- Define the public API: `get_terrain_height(world_x, world_z) -> float` for all entity placement. Single source of truth.
- Define how fog-of-war will work on non-flat terrain (shader-based on terrain mesh vs. conforming overlay mesh).
- Define how atmospheric distance fog will be configured without re-introducing the banding artifact that caused `scene.clearFog()`.
- Output: Architecture doc with data model, API signatures, file ownership, and a "this is how entities get their Y coordinate" diagram.

**Agent 05 — Gameplay implications consult (no code):**
- Review terrain elevation design for gameplay impact: Which building types should be restricted to flat ground? Should hills slow movement? Should elevation give combat advantage?
- Output: Short advisory doc with recommendations. Mark everything as "future sprint" — no gameplay code this sprint, just awareness so the data model supports it later.

### Wave 1 — Sky & Fog Atmosphere (quick visual wins)

**Agents:** 03 (TechnicalDirector)

**Depends on:** Wave 0 (need the atmospheric fog approach from the architecture doc)

**Agent 03 — Sky color + atmospheric fog + fog-of-war mist rework:**

Three changes, all in the rendering layer:

**1a. Sky-blue clear color:**
- Change `base.setBackgroundColor()` in `ursina_app.py` from `(0.06, 0.07, 0.09)` to a pleasant sky blue (suggested starting point: `(0.53, 0.72, 0.88)` — adjust to taste).
- Update `window.color` to match.
- This immediately fixes off-map areas appearing as void.

**1b. Atmospheric distance fog:**
- Re-introduce scene fog carefully. Use **exponential** fog (not linear — linear caused the banding) with a sky-blue fog color matching the clear color.
- The effect: distant terrain and objects fade into blue haze at the horizon, blending into the sky. This replaces the hard "edge of the world" with natural atmospheric perspective.
- If exponential fog still bands with `lit_with_shadows_shader`, fall back to a custom fragment-shader distance fade (compute distance from camera in the fragment shader, lerp toward fog color).
- Tune fog density so the nearest ~60% of the map is clear, the far ~40% fades gradually.

**1c. Fog-of-war mist rework:**
- Change the UNSEEN fog color from **black** (`0, 0, 0, 0xFF`) to **grey mist** (`0.6, 0.6, 0.65, 0xFF` — soft cool grey). This is the color players see for unexplored territory.
- Change the SEEN overlay from semi-transparent black to a lighter grey tint (`0.5, 0.5, 0.55, 0.4` — subtle mist over explored areas).
- Switch the fog texture filtering from **nearest-neighbor to bilinear**. This one change turns the hard tile edges into smooth gradients. The fog quad is already 1px-per-tile, so bilinear interpolation across tile boundaries creates natural feathering.
- Optionally: apply a small Gaussian blur pass to the fog texture before upload for even softer edges. This is a stretch — bilinear alone may be sufficient.

**Verification:**
- Launch `python main.py --provider mock`
- Pan camera to map edge — sky is blue, not dark void
- Distant objects fade into blue haze
- Fog of war is grey mist, not black. Edges between visible and fog are smooth, not pixelated
- Capture screenshots from multiple angles (top-down, angled, near-horizon)

### Wave 2 — Terrain Elevation Core

**Agents:** 03 (TechnicalDirector)

**Depends on:** Wave 0 (architecture contract), Wave 1 (sky/fog done so terrain can be visually evaluated in context)

**Agent 03 — Heightmap generation + terrain mesh:**

**2a. Heightmap generation:**
- Add heightmap generation to the map generation pipeline (or as a post-processing step).
- Use Perlin noise (or simplex noise) to generate natural-looking elevation. Layer multiple octaves: large-scale rolling hills + medium mountain ridges + small rocky detail.
- Parameters in `config.py` (or a new terrain config section): `TERRAIN_HEIGHT_SCALE` (max elevation), `TERRAIN_HILL_FREQUENCY`, `TERRAIN_MOUNTAIN_FREQUENCY`, `TERRAIN_CLIFF_THRESHOLD` (slope angle that counts as a cliff).
- Store the heightmap as a 2D array accessible via `get_terrain_height(world_x, world_z)`.
- Ensure the castle/starting area is on relatively flat ground (clamp or smooth the heightmap in a radius around the castle position).
- Map edges could have higher elevation (mountain border) to visually frame the world — this is optional but would look great.

**2b. Terrain mesh:**
- Replace the flat ground plane with a mesh whose vertices are displaced by the heightmap.
- Keep the existing grass texture — just deform the geometry underneath it.
- The mesh resolution should be tuned: per-tile vertices at minimum, possibly 2× or 4× for smoother slopes. Agent 03 decides based on performance testing.
- Apply the grass texture with UV mapping that looks correct on slopes (no extreme stretching on steep faces).
- Cliffs (slopes above `TERRAIN_CLIFF_THRESHOLD`): optionally apply a rock texture or darker color to steep faces. Stretch goal — even without this, the geometry alone will read as cliffs.

**2c. Entity Y-placement:**
- All entity creation/placement code must call `get_terrain_height(x, z)` to set the Y coordinate.
- Entities affected: buildings, trees, props (rocks, grass clumps, doodads), units (heroes, enemies, peasants, tax collectors), lairs, scatter objects.
- For buildings: sample the heightmap at the building's footprint center. If the slope across the footprint is too steep, the building should either (a) flatten a small area around itself (terrain conforms to building) or (b) be flagged for future placement restriction. Recommend option (a) for this sprint — it's more forgiving and looks fine for a first pass.
- For units: sample every frame (or on position change) so they follow the terrain as they move. This is critical — heroes walking uphill should visually climb, not float.

**2d. Fog-of-war on terrain:**
- The fog quad currently sits at a fixed Y=0.12. On non-flat terrain it will clip through hills and float above valleys.
- Recommended fix: make the fog a **shader effect on the terrain mesh itself** rather than a separate quad. The fog texture is sampled in the terrain fragment shader and blended on top. This guarantees the fog perfectly follows the terrain surface.
- Alternative: generate a conforming fog mesh that follows the heightmap at a small Y offset. Simpler to implement but may have z-fighting on steep slopes.
- Agent 03 chooses the approach based on their Wave 0 architecture doc.

**Verification:**
- Launch `python main.py --provider mock`
- Terrain has visible hills and elevation changes
- Camera orbit shows mountains/ridges
- Buildings, trees, units sit on the terrain surface (no floating, no sinking)
- Fog of war follows the terrain (no clipping through hills)
- Castle area is relatively flat
- Performance: maintain >30 FPS at default zoom. Agent 10 will benchmark in Wave 3.

### Wave 3 — Visual Polish & Art Review

**Agents:** 09 (ArtDirector), 03 (TechnicalDirector — support only)

**Depends on:** Wave 2

**Agent 09 — Visual cohesion review + polish:**
- Review the terrain elevation visuals for art cohesion with the existing pixel-art/Kenney aesthetic.
- Check: Does the sky blue feel right? Does the mist fog look natural? Do hills/mountains read well from the default camera angle?
- Recommend color/density adjustments for sky, atmospheric fog, and fog-of-war mist.
- If cliff faces look bare, propose a simple visual treatment (rock color, darker grass, edge highlight).
- Check that terrain doesn't clash with existing building prefabs, tree models, or unit sprites.
- Check lighting interaction with terrain slopes — do shadows look correct on hillsides?
- Output: List of specific tweaks with values (hex colors, fog densities, etc.) for Agent 03 to apply. Agent 09 does NOT edit game code.

**Agent 03 — Apply art direction tweaks:**
- Implement specific visual adjustments from Agent 09's review.
- Quick iteration: screenshot → Agent 09 feedback → adjust → re-screenshot.

### Wave 4 — Gates & Performance

**Agents:** 10 (PerformanceStability), 11 (QA)

**Depends on:** Wave 3

**Agent 10 — Performance benchmark:**
- Run FPS benchmarks at default zoom and close zoom.
- Compare frame times before and after terrain mesh introduction.
- Check terrain mesh vertex count and draw call impact.
- Flag if any terrain LOD or mesh simplification is needed.
- Report: FPS numbers, frame time breakdown, pass/fail against the perf budget.

**Agent 11 — QA gates + screenshot capture:**
- Run `python tools/qa_smoke.py --quick` — must PASS.
- Run `python tools/validate_assets.py --report` — must PASS.
- Capture comparison screenshots: before (flat terrain) vs. after (elevation + sky + mist).
- Verify: no visual regressions in buildings, units, UI, menus, fog transitions.
- Verify: camera orbit doesn't clip through terrain at extreme angles.

## Human Gates

1. **After Wave 1** — Jaimie reviews sky color and fog mist visuals. Quick "looks good" / "change the blue" before proceeding to terrain work.
2. **After Wave 3** — Jaimie playtests with elevation. Walk the camera around, check that the world feels right. This is the big visual approval gate.

## Files Likely Touched

| File | Owner Agent | Changes |
|---|---|---|
| `game/graphics/ursina_app.py` | 03 | Clear color, atmospheric fog setup |
| `game/graphics/ursina_terrain_fog_collab.py` | 03 | Fog colors, texture filtering, terrain mesh, heightmap, entity Y-placement |
| `game/graphics/ursina_environment.py` | 03 | Terrain generation helpers, prop Y-placement |
| `game/graphics/ursina_renderer.py` | 03 | Wire heightmap to entity placement calls |
| `game/graphics/ursina_coords.py` | 03 | Possibly add `get_terrain_height()` here as the public API |
| `game/graphics/ursina_units_anim.py` | 03 | Unit Y-placement on terrain |
| `game/graphics/ursina_prefabs.py` | 03 | Building prefab Y-placement on terrain |
| `config.py` | 03 | New terrain config constants |
| `game/map_generator.py` (or equivalent) | 03 | Heightmap generation in map gen pipeline |
| `tests/` | 11 | New terrain-related tests |

## Files NOT to Touch

- `game/ui/**` — No UI changes this sprint
- `game/entities/**` — No entity logic changes (elevation is render-only this sprint)
- `game/sim_engine.py` — Simulation stays flat; elevation is visual only for now
- `game/ai/**` — No AI changes
- `assets/prefabs/**` — No prefab edits

## Agent Summary

| Agent | Role this sprint | Intelligence |
|---|---|---|
| 03 | Primary implementer — sky, fog, terrain elevation, entity placement | HIGH |
| 05 | Consult only (Wave 0) — gameplay implications advisory | LOW |
| 09 | Art review & color/density direction (Wave 3) | MEDIUM |
| 10 | Performance benchmark (Wave 4) | LOW |
| 11 | QA gates & screenshots (Wave 4) | LOW |

**Do not send:** 01, 02, 04, 06, 07, 08, 12, 13, 14, 15

## Definition of Done

- [ ] Sky is blue — off-map and horizon show sky color, not dark void
- [ ] Fog of war is grey mist with smooth gradient edges, not hard black tiles
- [ ] Atmospheric distance fog fades distant objects toward sky color
- [ ] Terrain has visible elevation — hills, mountains, and cliffs generated from heightmap
- [ ] Castle/starting area sits on relatively flat ground
- [ ] All entities (buildings, trees, units, props) placed at correct Y on terrain
- [ ] Fog of war follows terrain surface (no clipping/floating)
- [ ] FPS ≥ 30 at default zoom (Agent 10 verified)
- [ ] `qa_smoke.py --quick` PASS
- [ ] `validate_assets.py --report` PASS
- [ ] Jaimie visual approval after Wave 1 and Wave 3
