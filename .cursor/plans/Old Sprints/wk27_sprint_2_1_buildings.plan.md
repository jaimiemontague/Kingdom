> ## [DEPRECATED — superseded by WK28/WK29, kept for history only]
>
> **Status (as of 2026-04-16): this plan is obsolete as written and was NEVER executed in this form.**
>
> The approach below assumed we would drop single pre-made mesh files (`castle.glb`, `house.glb`, `lair.glb`) into `assets/models/environment/` and swap billboards for `Entity(model=...)` one-to-one. We did not use that approach. No such single-file meshes exist and we are not authoring them from thin air.
>
> **What we actually did instead (WK28 + WK29, pre-v1.5):**
> - **WK28 (`wk28-assembler-spike`)** — Stood up Agent 15 (ModelAssembler / KitbashLead), shipped `tools/model_assembler_kenney.py` and `assets/prefabs/schema.md` v0.1 (Kenney `.glb` kit pieces kitbashed into JSON prefabs).
> - **WK29 (`wk29-first-house-playtest`)** — Kitbashed the first real prefab `assets/prefabs/buildings/peasant_house_small_v1.json` and added a **gated** prefab loader to `game/graphics/ursina_renderer.py` (`_load_prefab_instance`, `_use_wk29_prefab_house`) behind `KINGDOM_URSINA_PREFAB_TEST=1` for building type `house` only.
>
> **Authoritative path forward:** Kenney kit prefabs + loader, per:
> - `.cursor/plans/master_plan_3d_graphics_v1_5.md` (amended 2026-04-16 — see "Pipeline pivot" subsection in §4 Phase 2).
> - `.cursor/plans/wk28_assembler_spike_41c2daeb.plan.md` — tooling + schema that shipped.
> - `.cursor/plans/wk29_first_house_playtest.plan.md` — first-house end-to-end validation that shipped.
> - `.cursor/plans/wk30_buildings_pipeline.plan.md` — next sprint: generalize loader + assemble more prefabs.
> - `assets/prefabs/schema.md` — prefab JSON contract.
> - `.cursor/plans/kenney_gltf_ursina_integration_guide.md` — two-path shader classifier.
>
> **Do not implement the body below as written.** No sprint should reopen this plan. The WK27 intent (castle + house + lair in 3D) is now owned by WK30 onward, reframed as prefabs + generalized loader + footprint/QA reconciliation.
>
> The rest of this file is preserved unedited purely for history so everyone can move on.

---

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
