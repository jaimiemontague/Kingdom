# Sprint 1.1: Tooling & Rules Redesign (Phase 1)

**Sprint Target:** Core Tooling Overhaul for 3D Graphics Integration
**Agents Involved:** Agent 12 (Tools Director), Agent 09 (Art Director)
**QA Gate:** `python tools/validate_assets.py --report`

## Mission Statement
This sprint is the preparatory logic phase for the 3D graphics transition. We are moving away from 2D `.png` sprite parsing. Animated 3D models contain their rigging and animations inside their single `.glb` file, which fundamentally breaks our old folder structure of `assets/sprites/<entity>/<state>/frame_NNN.png`. We must update our rules and tooling to validate these new extensions before we can import any base terrain.

---

## Technical Specifications & Agent Assignments

### Agent 12 (Tools Director)
**Goal:** Modify `assets_manifest.json` schema to remove obsolete "states" mappings and rewrite `validate_assets.py` to validate single 3D files instead of PNG frame sequences.

**Explicit Reasoning & Code Examples for Agent 12:**
1. **The Manifest Issue:** The current `assets_manifest.json` expects sub-dictionaries with `states` (e.g., `"idle"`, `"walk"`). For 3D, `.glb` models embed these animations automatically. 
   - **Action:** Open `tools/assets_manifest.json`. Update the `schema_version` to `"1.5"` and change `notes` to reflect the 3D transition. Completely **delete** the `"states"` array from `heroes`, `enemies`, `buildings`, and `workers`. Add a new root-level dictionary for `"environment"` to handle static props: `"environment": {"types": ["grass", "path", "rock", "tree_pine"]}`
2. **The Script Issue:** `validate_assets.py` currently looks inside `assets/sprites/` and uses regex (`FRAME_RE`) to parse `.png` frames inside state subfolders. 
   - **Action:** Open `tools/validate_assets.py`. Rename the tree logic from `_validate_sprite_tree` to `_validate_model_tree`. Direct it to scan the `assets/models/` directory instead of `assets/sprites/`. 
   - **Action:** Remove usage of `_list_png_frames` and `_has_sortable_frames`. Instead, simply check if the file `<category>/<kind>.glb` or `<category>/<kind>.obj` exists. 
   - **Code Hint:** Replace the previous frame validation loop with a cleaner file extension check, such as: `allowed_exts = {".glb", ".gltf", ".obj"}`. If the model file exists matching the manifest key, report it as valid. Do not look for `<state>` subfolders anymore!

### Agent 09 (Art Director)
**Goal:** Rewrite `.cursor/rules/07-asset-conventions.mdc` to deprecate 2D methods and explicitly mandate the new 3D folder structures and extensions.

**Explicit Reasoning & Formatting for Agent 09:**
1. **The Deprecation Issue:** Our developers will default to 2D math unless the rules explicitly forbid it. 
   - **Action:** Open `.cursor/rules/07-asset-conventions.mdc`. In the `Folder Structure` section, rename `assets/sprites/` to `assets/models/`. Flatten the directory tree in the documentation so it shows `<class>.glb` instead of nesting into `<state>/frame_NNN.png`.
2. **The Type Issue:** We need strict guidelines for Animated vs Static meshes.
   - **Action:** State explicitly: "No more 2D sprites or frame sequences". State that animated entities (Heroes, Workers, Enemies) MUST be `.glb` (or `.gltf`) files because they require embedded rigging. State that static environment items and buildings can be `.obj` or `.glb` files.
3. **The Scale Issue:** We are no longer using "nearest-neighbor 32x32".
   - **Action:** Replace the `Sprite Size Rules` with `Scale Rules`. Outline that we prioritize "flat-shaded, low poly mesh aesthetics" and that 1 standard engine-grid unit generally = 1 mesh grid unit.

---

## Master Success Criteria
- [ ] `assets_manifest.json` contains no `"states"` arrays.
- [ ] `validate_assets.py` successfully runs and passes QA without searching for `.png` files.
- [ ] `07-asset-conventions.mdc` cleanly details standard `.glb`/`.obj` ingestion rules.
