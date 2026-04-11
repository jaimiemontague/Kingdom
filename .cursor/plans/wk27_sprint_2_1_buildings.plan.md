# WK27 Sprint 2.1: 3D Castles & Peasant Houses

This sprint initiates the actual replacement of the initial 2D building billboards with static 3D meshes for Castles, Houses, and enemy Lairs.

## Objective
Convert `castle`, `house` (Peasant House), and Lair building types from 2D billboards to full untextured 3D geometry in the Ursina renderer.

## Agent Instructions

### Agent 03 (Tech Director)
1. In `game/graphics/ursina_renderer.py`, adjust the `_sync_buildings` loop (inside the `update` method).
2. Intercept building configurations where the building type is `castle`, `house`, or when the building evaluates to `is_lair`.
3. Instead of constructing a billboard 2D quad, use `Entity(model=...)'` mapped to their environment meshes. 
   - Castle -> `assets/models/environment/castle.glb` (or `.obj`)
   - House -> `assets/models/environment/house.glb` (or `.obj`)
   - Lair -> `assets/models/environment/lair.glb` (or `.obj`)
4. Disable billboard configurations for these specific elements. Let them use the exact XZ coordinates on the ground (`y=0.0`).
5. Run `python tools/qa_smoke.py --quick` to confirm deterministic game state remains completely unaffected by these rendering changes.

### Agent 09 (Art Director)
1. Verify the exact coordinate placement and scaling of the new 3D buildings. Use the master plan footprints standard to ensure they fit correctly over the existing physical space without creating visual clipping for walking units. Adjust the model sizes manually inside `ursina_renderer.py` using `scale=(...)` to make sure they align cleanly with the py game 2D grid logic footprints.
2. Make sure they react nicely with the `lit_with_shadows` shading configuration from previous rounds, and not the `sprite_unlit_shader`. You want them to look like massive 3D structures casting shadows.
3. Review the building footprint sizes: Castle should comfortably sit on its multi-tile grid space. Houses should cleanly sit onto a 1x1 space or visually scale so multiple can fit side-by-side gracefully without overlapping meshes.

## Definition of Done
- `python main.py --renderer ursina` successfully loads `castle`, `house`, and `lair` 3D elements inside the ground plane without crashing.
- Fog of war appropriately darkens/hides them using the master plan standards.
- QA script `python tools/qa_smoke.py --quick` stays GREEN.
