# Sprint 1.2: Base Terrain (Phase 1)

**Sprint Target:** Deprecate the 2D baked texture map and initialize individual 3D environment instances for base terrain (`grass.glb`, `path.glb`, `rock.glb`, `tree_pine.glb`).
**Agents Involved:** Agent 03 (Tech Director), Agent 09 (Art Director)
**QA Gate:** `python main.py --renderer ursina` successfully visually renders the 3D terrain plane.

## Mission Statement
We are removing the legacy `TileSpriteLibrary` 2D bake logic. Our grid floor and static environmental map blockers must now be instantiated as discrete Ursina `Entity` objects using `.glb` model loading.

---

## Technical Specifications & Agent Assignments

### Agent 03 (Tech Director)
**Goal:** Rip out `_bake_terrain_floor` and `TileSpriteLibrary` usage within `game/graphics/ursina_renderer.py` and replace it with a 3D Entity looping mechanism.

**Explicit Reasoning & Code Changes:**
1. **The Deprecation:** Delete the entire `_bake_terrain_floor` function and the usage of `self._terrain_sheet`. The legacy system pasted pixel art into an atlas to texture a single `quad`. That must go completely.
2. **The 3D Grid Loop:** Create a new initialization method `_build_3d_terrain()`. Loop through the simulation data arrays for the floor (`world.tiles`) and the environmental blockers/features.
   - For every X/Y coordinate in `world.tiles`, spawn an Ursina `Entity(model='environment/grass')` (or `path` depending on the tile type). Set their world positions to align with the core engine logic `px_to_world` conversions.
   - Ensure these instantiated entities are grouped nicely or parented together to maintain performance organization.
   - We must also instantiate `model='environment/rock'` and `model='environment/tree_pine'` where they spawn on the map.
3. **Scale Calibration:** Add a configurable `TERRAIN_SCALE_MULTIPLIER = 1.0` constant at the top of the file in case we need to uniformly scale the untextured meshes up/down to seamlessly cover the `32px` standard grid size.

### Agent 09 (Art Director)
**Goal:** Setup basic Ambient and Directional lighting loops inside `ursina_renderer.py` so the untextured `.glb` primitives pop visually.

**Explicit Reasoning & Code Changes:**
1. **The Lighting Setup:** The old unlit flat quads won't work for 3D geometry; if they lack material definitions, they will just render silhouette-black or totally blown out white without lighting logic.
2. **Action:** During the main Ursina renderer `__init__`, place an `AmbientLight` (dimly gray/blue) and a `DirectionalLight` (pointing downwards at an angle) so our new trees and rocks have simple, flat-shaded dimensionality.
3. **Action:** Turn shadows on for the Directional Light, and ensure the basic environment primitives (trees/rocks) cast shadows onto the grass floor.

---

## Master Success Criteria
- [ ] Environment loads using `Entity(model="environment/grass")` without crashing to missing asset paths.
- [ ] The floor tiles visually tile together endlessly without massive jagged gaps.
- [ ] Trees and rocks load distinctly, casting shadow volumes. 
- [ ] No 2D ground tiles appear.
