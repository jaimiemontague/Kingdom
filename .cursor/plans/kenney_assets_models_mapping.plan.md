---
name: ""
overview: ""
todos: []
isProject: false
---

# Kenney `assets/models` folder map

**Implementing `.glb` / `.gltf` in Ursina or the game renderer?** Read **[kenney_gltf_ursina_integration_guide.md](./kenney_gltf_ursina_integration_guide.md)** first (default unlit shader vs `baseColorFactor`, textures, vertex colors, lighting pitfalls, and the `model_viewer_kenney` reference implementation).

This document maps **what lives where** under `assets/models` after non-Kenney packs were removed. Paths and pack names below are anchored to the **unmerged** Kenney downloads kept in-repo for reference.

**Reference folder (exact paths, clean separation):**

`assets/models/Models/Kenny raw downloads (for exact paths)/`

*(Folder name uses “Kenny”; pack directories use Kenney’s `kenney_*` naming.)*

Each pack under that folder keeps Kenney’s normal layout: `License.txt` at the pack root, then `Models/<Format>/` for exports. For OBJ, materials expect textures beside the MTL, typically:

`<pack>/Models/OBJ format/Textures/*.png`

The **working game library** is still the **merged** tree at `assets/models/Models/OBJ format/` (one flat folder + one shared `Textures/`). The reference tree is the source of truth for **which asset came from which download** and **correct relative paths** before the merge.

---

## 1. Kenney packs in `Kenny raw downloads (for exact paths)`

| Folder | Official title (from `License.txt`) | Version | `Models/OBJ format/*.obj` count |
|--------|-------------------------------------|---------|----------------------------------|
| `kenney_blocky-characters_20` | Blocky Characters | 2.0 | 18 |
| `kenney_cursor-pixel-pack` | Cursor Pixel Pack | 1.0 | 0 (2D / tilesheet only) |
| `kenney_nature-kit` | Nature Kit | 2.1 | 329 |
| `kenney_retro-fantasy-kit` | Retro Fantasy Kit | 2.0 | 105 |
| `kenney_survival-kit` | Survival Kit | 2.0 | 80 |

All of the above use **Creative Commons Zero (CC0)** in their respective `License.txt` files.

**Cursor Pixel Pack** — Only `License.txt`, `Tilesheet.txt`, and shortcut URLs; **no `Models/`**. Use for UI / 2D cursors, not for the 3D OBJ merge.

---

## 2. What each pack contributes (high level)

### Blocky Characters (`kenney_blocky-characters_20`)

- **Meshes:** `character-a` … `character-r` (18 files) under `Models/OBJ format/`.
- **Also at repo root:** `assets/models/License.txt` and `assets/models/Overview.html` match this pack (same Blocky Characters 2.0 text as `kenney_blocky-characters_20/License.txt`).
- **Textures:** `map_Kd Textures/texture-*.png` → resolve under `.../kenney_blocky-characters_20/Models/OBJ format/Textures/`.

### Retro Fantasy Kit (`kenney_retro-fantasy-kit`)

- **Meshes:** Modular fantasy/medieval pieces — e.g. `wall-*`, `wall-pane-*`, `wall-fortified-*`, `tower-*`, `roof-*`, `wood-floor-*`, `tree-large`, `tree-shrub`, `water`, many `structure-*` and building-adjacent props that fit the retro-fantasy building set.
- **Textures:** Shared kit maps (e.g. `planks.png`, `cobblestone.png`) live under `.../kenney_retro-fantasy-kit/Models/OBJ format/Textures/` in a clean download.

### Survival Kit (`kenney_survival-kit`)

- **Meshes:** Survival/crafting flavor — e.g. `tool-*`, `workbench-*`, `tree` / `tree-tall` / `tree-log*`, `rock-flat`, `campfire-*`, `tent-*`, `bedroll-*`, `structure-canvas`, `structure-metal-*`, barrels/boxes/chests, docks, signs, etc. (see pack folder for the full list).
- **Textures:** `.../kenney_survival-kit/Models/OBJ format/Textures/` (same relative pattern as other packs).

### Nature Kit (`kenney_nature-kit`)

- **Meshes:** Outdoor terrain and biome pieces — `ground_*` (grass, paths, rivers), `cliff_*`, `plant_*`, `flower_*`, `mushroom_*`, `crop_*`, `rock_*`, `stone_*`, `tree_pine*`, bridges, statues, etc.
- **Note:** Nature Kit also ships a small clump `grass.obj`; the **game** terrain tile uses **`ground_grass.obj`** (see §4).

---

## 3. Merged `Models/` vs reference packs

| Location | Role |
|----------|------|
| **`assets/models/Models/OBJ format/`** | **Single merged** copy of OBJ from Blocky Characters + Retro Fantasy + Survival + Nature (flat namespace). File count is ~528 `.obj` (minor drift vs sum of parts if you add/remove files). |
| **`assets/models/Models/OBJ format/Textures/`** | **One combined** texture bundle used at runtime next to the merged MTLs (18 character skins + shared maps such as cobblestone/planks/water/tree). |
| **`assets/models/Models/GLB format/`** and **`GLTF format/`** | Parallel exports (same broad asset set; GLB includes its own `Textures/` subfolder). |
| **`assets/models/Models/Textures/`** (parent of `OBJ format`) | Not the main OBJ bundle — only stray files such as **`variation-a.png`** in a typical checkout. **Do not** point loaders here by default. |

**Pathing rule:** In each **raw** pack, MTL `map_Kd Textures/foo.png` is relative to the `.mtl` file, i.e. `.../<pack>/Models/OBJ format/Textures/foo.png`. After the merge, the same filenames are expected under **`assets/models/Models/OBJ format/Textures/`**.

---

## 4. `assets/models/environment/` → canonical Kenney sources

These are **promoted** meshes for `game/graphics/ursina_renderer.py` (`_environment_model_path`). Where the runtime name differs from the download (`grass.obj`, `path.obj`, `rock.obj`), the **geometry** matches the file in the **merged** library `assets/models/Models/OBJ format/` (same bytes as the corresponding pack under `Kenny raw downloads (for exact paths)/`).

| Runtime file | Kenney source (same mesh as in `Models/OBJ format/`) | Notes |
|--------------|------------------------------------------------------|--------|
| `grass.obj` | Nature Kit — `ground_grass.obj` | `mtllib grass.mtl`; materials from `ground_grass.mtl` (flat `Kd` grass). |
| `path.obj` | Nature Kit — `ground_pathTile.obj` | `mtllib path.mtl`; materials from `ground_pathTile.mtl` (`grass` / `dirt` / `dirtDark`). |
| `rock.obj` | Survival Kit — `rock-flat.obj` | `mtllib rock.mtl`. **Texture:** the stock MTL references `Textures/colormap.png`; `environment/rock.mtl` instead uses a flat `Kd` gray so the folder stays self-contained (no `environment/Textures/`). |
| `tree_pine.obj` | *(unchanged on purpose)* | **Canonical match in the asset library:** `assets/models/Models/GLB format/tree-tall.glb` (Survival Kit **tree-tall**). The committed `.obj` was not swapped to avoid a visual change here; treat **`tree-tall`** as the reference when choosing materials or comparing formats. |

---

## 5. Filename prefixes → pack (merged `OBJ format/`)

Use this when you need to know **which download to diff against** or which `License.txt` applies. Counts are approximate (from an earlier inventory of the merged folder).

### Blocky Characters only

| Pattern | ~Count | Pack |
|---------|--------|------|
| `character-*` | 18 | `kenney_blocky-characters_20` |

### Mostly Retro Fantasy Kit

| Pattern | ~Count | Notes |
|---------|--------|--------|
| `wall-*` | 39 | Fortified / pane / paint variants, gates, doors, windows |
| `roof-*`, `battlement-*`, `tower-*` | varies | Modular roofs, battlements, towers |
| `floor-*`, `wood-floor-*` | varies | Floors and stairs |
| `water` (mesh) | 1 | Water plane (distinct from Nature Kit **ground** river tiles) |

### Mostly Survival Kit

| Pattern | ~Count | Notes |
|---------|--------|--------|
| `tool-*`, `workbench-*` | 10 each | Tools and benches |
| `campfire-*`, `tent-*`, `bedroll-*` | varies | Camp props |
| `structure-canvas`, `structure-metal-*`, … | varies | Overlaps name with other kits — confirm in **raw** `kenney_survival-kit` if unsure |

### Mostly Nature Kit

| Pattern | Role |
|---------|------|
| `ground_*` | Grass tiles, path/river tiles, banks, corners |
| `cliff_*` | Cliff blocks |
| `plant_*`, `flower_*`, `mushroom_*`, `crops_*`, `crop_*` | Foliage and farming |
| `rock_*`, `stone_*` | Rocks and stones (many variants) |
| `tree_pine*`, other `tree_*` | Pines and assorted trees |

Many **one-off** names (`statue_*`, `bridge_*`, `lily_*`, …) still map cleanly to **one** of the four 3D packs; use the reference folder search when in doubt.

---

## 6. Export formats: what to use when

| Format | When to prefer |
|--------|----------------|
| **OBJ** | Panda/Ursina `loadModel`, quick iteration; paired MTL + `Textures/`. |
| **GLB** | Single-file import; textures often embedded; **preferred** for glTF pipeline work and **`tools/model_viewer_kenney.py`**. |
| **glTF** | Split JSON + buffers; good for glTF tooling; watch external image paths. |

**Canonical for merged content in this repo:** OBJ under `assets/models/Models/OBJ format/`.

**glTF integration pitfalls (unlit vs factors, etc.):** [kenney_gltf_ursina_integration_guide.md](./kenney_gltf_ursina_integration_guide.md).

**Standalone GLB browser (dev):** `python tools/model_viewer_kenney.py` — see the integration guide §9.

---

## 7. License and attribution

| Pack | Read this file |
|------|----------------|
| Blocky Characters | `assets/models/Models/Kenny raw downloads (for exact paths)/kenney_blocky-characters_20/License.txt` (duplicate summary at `assets/models/License.txt`) |
| Retro Fantasy Kit | `.../kenney_retro-fantasy-kit/License.txt` |
| Survival Kit | `.../kenney_survival-kit/License.txt` |
| Nature Kit | `.../kenney_nature-kit/License.txt` |
| Cursor Pixel Pack | `.../kenney_cursor-pixel-pack/License.txt` |

---

## 8. Maintenance checklist

- [ ] If a texture fails to load, compare merged paths to the matching **`Kenney raw downloads/.../Models/OBJ format/Textures/`** file and ensure the same basename exists under **`assets/models/Models/OBJ format/Textures/`**.
- [ ] For legal screens, cite **each** pack you ship assets from (use the five `License.txt` files above).
- [ ] After adding a new Kenney download, either keep it under `Kenney raw downloads (for exact paths)/` or document the new mapping here.