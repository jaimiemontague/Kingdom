# Unit Instancing Architecture: Strategic Scaffolding

*Note: This document provides the high-level structural scaffolding and technical concepts required to transition Kingdom's unit rendering to a hardware-instanced pipeline. It is designed to be expanded by subsequent AI agents into a formal, sprint-by-sprint master execution plan.*

## 1. Phase 0: Baseline & Profiling
Before altering the architecture, we must establish verifiable metrics.
* **Concepts to flesh out:**
  * Define a headless or auto-running stress test (e.g., spawning 500 units).
  * Record baseline FPS, CPU frame time, and GPU memory usage.
  * Establish the "Definition of Done" (e.g., 500 units @ 60 FPS on target hardware).

## 2. Phase 1: The Asset Pipeline (Texture Atlasing)
Instancing requires all instances to share a single material. We cannot swap textures; we must swap UV coordinates on a single texture.
* **Concepts to flesh out:**
  * **Atlas Generation:** Determine whether to dynamically pack `HeroSpriteLibrary` and `EnemySpriteLibrary` into a `2048x2048` atlas at game boot, or pre-bake the atlas to disk during development.
  * **Metadata Mapping:** Create a dictionary mapping `(unit_class, animation_state, frame_index)` to its specific `(U_start, V_start, U_width, V_height)` bounding box on the atlas.
  * **Texture Settings:** Ensure the atlas disables mip-mapping and uses nearest-neighbor filtering to preserve the crisp pixel-art aesthetic.

## 3. Phase 2: The GPU Pipeline (Custom GLSL Shaders)
Ursina's default shaders do not support instance-specific UV offsets or instanced billboard math.
* **Concepts to flesh out:**
  * **Custom Vertex Shader:** 
    * Read instance-specific data (World Position XYZ, UV Offset, Scale).
    * Perform **GPU Billboard Math**: Calculate the rotation matrix entirely in the vertex shader so the quad always faces the camera, stripping this math out of Python.
  * **Custom Fragment Shader:**
    * Sample the atlas using the modified UVs.
    * Perform **Strict Alpha Testing** (`if (color.a < 0.1) discard;`). This allows the hardware Z-buffer to handle depth sorting without manual CPU sorting, avoiding the dreaded transparent overlap glitch.
    * Apply any global tints (e.g., green for builder peasants, red for damaged units, fog-of-war darkening).

## 4. Phase 3: The Engine Data Bridge (Panda3D Integration)
This is where the massive CPU gains are realized by bypassing Ursina's `Entity` overhead.
* **Concepts to flesh out:**
  * **The Master Mesh:** Create a single Panda3D `GeomNode` containing a simple quad. 
  * **Data Structure:** Define a `GeomVertexData` structure that includes our custom columns (`vertex`, `texcoord`, `instance_pos`, `instance_uv_offset`, `instance_tint`).
  * **Pre-Allocation:** Allocate a fixed-size contiguous memory block (e.g., capacity for 1,000 units) to prevent Python garbage collection spikes and reallocation latency.
  * **The Flush Loop:** In `_sync_snapshot_heroes()`, iterate over the simulation state, pack the byte array with current positions and UV states, call `setNumInstances(count)`, and flush the buffer to the GPU.

## 5. Phase 4: Animation & State Synchronization
The renderer must map simulation states to visual frames without relying on `pygame.Surface` updates.
* **Concepts to flesh out:**
  * **Time-Based Frame Logic:** Since the simulation might run at a different tick rate than the renderer, the renderer must track `animation_start_time` for each unit to calculate which frame of the walk/attack cycle to display.
  * **Trigger Handling:** Intercept simulation triggers (like `_render_anim_trigger`) to swap the base animation clip (e.g., transitioning from `walk` to `attack`).

## 6. Phase 5: "HD-2D" Visual Polish & Scaling
Once the high-performance pipeline is established, we reinvest the reclaimed CPU/GPU budget into premium aesthetics.
* **Concepts to flesh out:**
  * **Sub-Pixel Movement (Lerping):** Units currently snap to the grid or move rigidly. Introduce visual lerping (interpolation) so they glide smoothly between simulation ticks.
  * **Blob Shadows:** Add a secondary instanced draw call for simple, semi-transparent oval shadows underneath units to ground them in the 3D environment.
  * **Environmental Integration:** Ensure the custom shader interacts correctly with the directional light, global ambient light, and Kingdom's specific Fog-of-War overlay logic.

## 7. Phase 6: Edge Cases & Cleanup
* **Concepts to flesh out:**
  * Handling ranged projectiles (arrows) — should they be instanced as well?
  * Cleaning up and deprecating the old `pygame` unit rendering paths and `TerrainTextureBridge` usage for units.
  * Ensuring UI overlays (health bars, name tags, gold bubbles) scale cleanly or are batched separately, as drawing 500 individual text entities will become the *new* bottleneck if left unchecked.
