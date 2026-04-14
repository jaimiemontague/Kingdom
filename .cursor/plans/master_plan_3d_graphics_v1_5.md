# Master Plan: 3D Graphics Integration (Target v1.5)

**Kenney glTF / Ursina integration (pitfalls, unlit vs PBR, baseColorFactor):** see [kenney_gltf_ursina_integration_guide.md](./kenney_gltf_ursina_integration_guide.md). Apply those lessons when wiring `Entity(model=…)` and materials in `game/graphics/ursina_renderer.py`.

## 1. Mission Statement
> "Transition the Kingdom project to a fully 3D, low-poly stylized aesthetic suitable for a $15-$20 commercial Steam release. Emphasize visual cohesion, prioritize high-performance flat-shaded geometry over complex textures, and establish a scalable pipeline for importing static and animated 3D assets using Ursina."

## 2. Versioning & Commit Protocol
* **Target Release Version:** v1.5 (Once the 3D transition is completely stable and full parity is implemented).
* **Commit Convention:** All commits for these upcoming sprints must use the naming convention: `"3D Graphics Phase #.#"` (e.g., `3D Graphics Phase 1.0`, `3D Graphics Phase 1.1`, progressing naturally as milestones are hit).

## 3. Core Rules & Pipeline Overhaul
Before changing how meshes are loaded or shaded, read **[kenney_gltf_ursina_integration_guide.md](./kenney_gltf_ursina_integration_guide.md)** (defaults entity shader, `baseColorFactor`-only materials, why naive `setShaderAuto` breaks scenes).

To support this massive visual overhaul properly, we will delegate the structural pipeline updates to the Directors:

* **Update Core Rules:** **Agent 09 (Art Director)** must rewrite `07-asset-conventions.txt` to explicitly deprecate 2D `.png` sprite rules. They will establish the new standard: `.obj` or `.gltf` for static environment/buildings, and `.gltf` exclusively for animated units (to utilize embedded rigging/animations).
* **Tooling Overhaul:** **Agent 12 (Tools Director)** must update `tools/assets_manifest.json` and `tools/validate_assets.py` to track and validate 3D meshes and their associated texture files. This will replace the older logic that iterated through PNG frame sequences.
* **Renderer Update:** **Agent 09 (Art)** and **Agent 03 (Tech Director)** must update `game/graphics/ursina_renderer.py` to completely remove 2D sprite billboarding logic and replace it with standard 3D entity loading (`Entity(model=...))`). They must also hook up Ursina's Actor or FrameAnimation3d logic for unit state changes (Idle, Walk, Attack).
* **Scale & Collision:** **Agent 05 (Gameplay Director)** and **Agent 03 (Tech)** must recalculate grid interactions. The new 3D models will produce different physical footprints than the legacy 2D tiles. They will ensure simulation logic spacing and physical bounding boxes align so buildings fit the grid seamlessly and units do not clip through them.

## 4. Implementation Phases (High-Level Roadmap)
We will tackle this transition in sequential phases to avoid breaking the core game loop. Detailed sprint plans will be created one by one based on this document, allowing us to pivot if we encounter engine limitations. Do not touch animated units until the static 3D world loads perfectly.

### Phase 1: Static Environments & Asset Pipeline Foundations
* **Goal:** Build the 3D tooling foundation, update the rules, and successfully load/render static environments (terrain floor, trees, basic walls) before touching complex buildings or animated units.
* **Lighting/Shaders Guideline:** **Agent 09** is instructed to rely exclusively on Ursina's basic lighting and flat shading. Avoid complex PBR materials to ensure the low-poly aesthetic remains clean and performant. If you must adjust materials, follow **[kenney_gltf_ursina_integration_guide.md](./kenney_gltf_ursina_integration_guide.md)** so factor-only and vertex-colored glTF assets do not render white or black incorrectly.

**Sprints Outline:**
- **Sprint 1.1 (Tooling & Rules):** Agent 12 updates `assets_manifest.json` and `validate_assets.py` to support `.gltf`/`.obj`. Agent 09 updates `07-asset-conventions.txt`.
- **Sprint 1.2 (Base Terrain):** Agent 09 & Agent 03 replace the tile ground quads with 3D terrain meshes (Grass, Path). Verify scaling.
- **Sprint 1.3 (Static Environment Props):** Introduce 3D trees and rocks replacing 2D billboards. Connect flat shading.

**Success Criteria:**
- `qa_smoke.py --quick` and `validate_assets.py` pass with the new 3D rules.
- The Ursina renderer successfully draws the 3D ground plane and static environmental props (trees, rocks) without crashing or massive FPS drops. No 2D environment sprites remain.

> **Tasks for the Human (Jaimie):**
> - [ ] **Clean the workspace:** Go into `assets/models` and physically delete all non-compatible file formats (e.g., delete `.blend`, `.fbx`, `.dae`, `.stl`). We only want `.gltf` and `.obj` formats.
> - [ ] **Select Models:** Review the remaining packs and select specific `.obj` or `.gltf` models for the core terrain primitives (e.g., `grass.glb`, `tree_pineSmallA.glb`, `rock_smallA.glb`). Reply to me with your exact chosen filenames.
> - [ ] **Playtest & Verify (Visual Checklist):** Open the terminal and run `python main.py --renderer ursina`. Look exactly for the following:
>    - Is the ground perfectly flat with no gaps between the grass tiles?
>    - Do the 3D trees and rocks look like solid models, not flat pieces of paper (billboards) that rotate when the camera moves?
>    - Does the shading look smooth and simple, or are there broken textures (e.g., pink/black checkers, pitch black items)? If you see visual garbage or massive FPS lag, reject the sprint and tell me immediately.

### Phase 2: Static Buildings & Grid Alignment
* **Goal:** Integrate static buildings into the new renderer layout and grid. Ensure scaling footprints match the collision spaces of our Pygame engine perfectly.

**Sprints Outline:**
- **Sprint 2.1 (Castle & Core):** Agents 03 and 09 swap the Castle and Lair 2D sprites for 3D primitives. Agent 05 recalculates physical footprint and collision data if the scale is off.
- **Sprint 2.2 (Economy Buildings):** Swap the Marketplace, Inn, and Farms. Ensure doors/entrances align with the simulation grid.
- **Sprint 2.3 (Military Buildings):** Swap all Guilds and defensive towers.

**Success Criteria:**
- Buildings load as 3D `.gltf`/`.obj` models.
- Pygame Engine building size data matches the physical bounds in the Ursina viewer. 
- Units can navigate between buildings without clipping through mesh geometry.

> **Tasks for the Human (Jaimie):**
> - [ ] **Select Models:** Pick specific `.obj` or `.gltf` files to represent the `Castle`, `Marketplace`, `Inn`, and `Blacksmith`. 
> - [ ] **Playtest & Verify (Visual Checklist):** Open the terminal and run `python main.py --renderer ursina`. Look exactly for the following:
>    - **Scale Check:** Do the buildings look like the right size compared to the trees? Are they impossibly tiny or massive screen-blockers?
>    - **Grid/Floor Alignment:** Do the doors and bases of the buildings line up neatly with the floor tiles, or are they floating in the air / visibly sunk through the ground?
>    - **Clipping:** Watch a hero or peasant walk past the building. Do they walk cleanly *around* the building walls, or do they clip straight through the solid masonry geometry? If they clip through, reject the sprint.

### Phase 3: Animated Units (Entity Rigging)
* **Goal:** Transition dynamic units (Peasants, Heroes, Enemies) to 3D and attach them to Ursina's animation system.
* **Focus:** Seamlessly handling `Idle`, `Walk`, and `Attack` states based on the py engine's entity statemachine.

**Sprints Outline:**
- **Sprint 3.1 (Animation Framework):** Agent 03 writes the boilerplate `Actor` or `FrameAnimation3d` routing in `ursina_renderer.py` to swap animations when a unit's state changes.
- **Sprint 3.2 (Workers):** Agent 09 hooks up 3D meshes and rigging for the Peasant and Tax Collector. Ensure walking traces gracefully across the grid.
- **Sprint 3.3 (Heroes):** Hook up the Warrior, Ranger, Rogue, and Wizard. Connect their attack animations to the combat event bus.
- **Sprint 3.4 (Enemies):** Hook up Goblins, Wolves, and Skeletons. Connect their hit/death animations.

**Success Criteria:**
- 2D billboard logic for entities is entirely removed from `ursina_renderer.py`.
- Entities smoothly transition between `Idle`, `Walk`, and `Attack` loops corresponding to simulation data.
- QA Gates strictly pass.

> **Tasks for the Human (Jaimie):**
> - [ ] **Select Models:** Review the character packs (like `Modular Character Outfits - Fantasy`) and give me the exact `.gltf` file names you want to use for the Peasant and the Warrior.
> - [ ] **Playtest & Verify (Visual Checklist):** Open the terminal and run `python main.py --renderer ursina`. Look exactly for the following:
>    - **Idle vs Walk:** When a peasant stops moving, do their legs stop? When they walk, do their legs actually animate in a walking cycle, or are they sliding across the ground like frozen statues?
>    - **Combat:** When a warrior fights an enemy, do they actually swing their weapon (play the Attack animation)? Or do they just bump into each other?
>    - **Direction:** Do the characters actually face the direction they are walking? If they are moonwalking backwards, reject the sprint.

### Phase 4: Polish, Lighting, & v1.5 Release
* **Goal:** Final lighting passes, shadows, QA, deterministic tests, and removing any lingering reference to old 2D elements.
* **Focus:** Visual parity, making the aesthetics "WOW", and achieving high FPS.

**Sprints Outline:**
- **Sprint 4.1 (Lighting & Atmospherics):** Agent 09 adds directional light, ambient light, and finalizes the Fog of War to correctly overlap the new 3D models.
- **Sprint 4.2 (VFX & Polish):** Add low-poly particle effects for combat hits, leveling up, and building construction/destruction.
- **Sprint 4.3 (Performance Optimization):** Agent 10 profiles Ursina FPS. Consolidate meshes or bake textures where necessary to hit a locked 60+ FPS without breaking deterministic sim rules.

**Success Criteria:**
- The game visually "Wows" the human tester.
- Fog of War correctly hides 3D units and models without visual glitches.
- A steady framerate is maintained through Late-Game scenarios with many units.
- Version is officially bumped to 1.5 in CHANGELOG and codebase.

> **Tasks for the Human (Jaimie):**
> - [ ] **Playtest & Verify (Visual Checklist):** Open the terminal and run `python main.py --renderer ursina`. Look exactly for the following:
>    - **Lighting/VFX:** Does the lighting cast nice, simple shadows that make the buildings pop without overwhelming the screen? Do combat hits spawn clear particle effects instead of graphical noise?
>    - **Fog of War:** Does the black Fog of War smoothly hide models that are far away? Do trees or tall enemies "poke out" of the black fog when they shouldn't?
>    - **Performance:** Does the game feel smooth with the camera zoomed out? (If it feels slower than a slideshow, tell me it failed performance QA).
>    - **The "WOW" Factor:** Does the game currently look cohesive, atmospheric, and worth paying $15 for on Steam? If no, what specifically looks janky? Report the vibes back to me.
