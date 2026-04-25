---
name: ""
overview: ""
todos: []
isProject: false
---

# Kenney `assets/models` folder map

**Implementing `.glb` / `.gltf` in Ursina or the game renderer?** Read **[kenney_gltf_ursina_integration_guide.md](./kenney_gltf_ursina_integration_guide.md)** first (default unlit shader vs `baseColorFactor`, textures, vertex colors, lighting pitfalls, and the `model_viewer_kenney` reference implementation).

**Need to improve weak Kenney surface reads without editing source GLBs?** Read **[prefab_texture_override_standard.md](./prefab_texture_override_standard.md)**. It documents the WK32 Inn v2 success path: generated low-res textures under `assets/textures/`, per-piece `texture_override` metadata, recursive texture-state cleanup, object-space texture mapping for atlas-swatch UVs, and screenshot acceptance gates.

This document maps **what lives where** under `assets/models`. Paths and pack names below are anchored to the **unmerged** Kenney downloads kept in-repo for reference.

**Reference folder (exact paths, clean separation):**

`assets/models/Models/Kenny raw downloads (for exact paths)/`

*(Folder name uses “Kenny”; pack directories use Kenney’s `kenney_*` naming.)*

Each pack under that folder keeps Kenney’s normal layout: `License.txt` at the pack root, then `Models/<Format>/` for exports.

**Since WK31 round-2 (2026-04-18), every model file and the shared atlas for the Fantasy Town Kit and Graveyard Kit carry a pack suffix in their filename** (see §3). This applies in both the raw-tree and the merged tree:

- `cart.glb` → `cart-fantasy-town.glb` (Fantasy Town)
- `altar-stone.glb` → `altar-stone-graveyard.glb` (Graveyard)
- Each pack's `Textures/colormap.png` → `Textures/colormap-fantasy-town.png` / `Textures/colormap-graveyard.png`
- Each GLB's internal `images[].uri` + each OBJ/MTL reference were rewritten to match.

Retro Fantasy, Survival, Nature, Blocky Characters, and Cursor Pixel Pack are **not** suffixed — their filenames never collided.

The **working game library** is the merged tree at `assets/models/Models/GLB format/` (one flat folder + one shared `Textures/` sibling) and `assets/models/Models/GLTF format/` (Nature Kit exports — despite the folder name, these are `.glb` files). The merged OBJ tree at `assets/models/Models/OBJ format/` is the parallel legacy path kept in sync for reference.

---

## 1. Kenney packs in `Kenny raw downloads (for exact paths)`

| Folder | Official title | Version | `Models/GLB format/*.glb` count | `Models/OBJ format/*.obj` count | Filename suffix |
|--------|----------------|---------|-------------------------------:|--------------------------------:|-----------------|
| `kenney_blocky-characters_20`  | Blocky Characters    | 2.0 | 18  | 18  | — |
| `kenney_cursor-pixel-pack`     | Cursor Pixel Pack    | 1.0 | 0   | 0 *(2D tilesheet only)* | — |
| `kenney_fantasy-town-kit_2.0`  | Fantasy Town Kit     | 2.0 | 167 | 167 | **`-fantasy-town`** |
| `kenney_graveyard-kit_5.0`     | Graveyard Kit        | 5.0 | 91  | 91  | **`-graveyard`** |
| `kenney_nature-kit`            | Nature Kit           | 2.1 | 0 *(ships as split glTF under `GLTF format/`; 329 `.glb` live in the merged tree)* | 329 | — |
| `kenney_retro-fantasy-kit`     | Retro Fantasy Kit    | 2.0 | 105 | 105 | — |
| `kenney_survival-kit`          | Survival Kit         | 2.0 | 80  | 80  | — |

All packs use **Creative Commons Zero (CC0)** per their respective `License.txt` files.

**Cursor Pixel Pack** — Only `License.txt`, `Tilesheet.txt`, and shortcut URLs; **no `Models/`**. Use for UI / 2D cursors, not for the 3D pipelines.

The two most recent additions (April 2026) are:

- **Fantasy Town Kit (2.0)** — Kenney, dated 2025-08-03. Civic / village kitbash pieces: walls, roofs, stairs, banners, carts, fountains, hedges, chimneys, market stalls, windmill / watermill, road / paving tiles, trees, rocks, statues. All filenames suffixed `-fantasy-town`.
- **Graveyard Kit (5.0)** — Kenney, dated 2025-10-17. Gothic cemetery + small crypt kit: altars, benches, crypts (several sizes), coffins, candles, crosses, fences, gravestones (many variants), lanterns, iron fences, pumpkins, pines, plus **5 Halloween-themed characters** (`character-ghost-graveyard`, `character-keeper-graveyard`, `character-skeleton-graveyard`, `character-vampire-graveyard`, `character-zombie-graveyard`). These characters are rigged like Blocky Characters (separate limb meshes under a `root` node) and are useful as enemy placeholders. All filenames suffixed `-graveyard`.

---

## 2. What each pack contributes (high level)

### Blocky Characters (`kenney_blocky-characters_20`)

- **Meshes:** `character-a` … `character-r` (18 files) under `Models/GLB format/` and `Models/OBJ format/`.
- **Also at repo root:** `assets/models/License.txt` and `assets/models/Overview.html` match this pack.
- **Textures:** `texture-a.png` … `texture-r.png` (one per character). GLBs use `KHR_materials_unlit` + `KHR_texture_transform`.
- **Merged names:** unchanged (no collision risk).

### Retro Fantasy Kit (`kenney_retro-fantasy-kit`)

- **Meshes:** Modular fantasy/medieval pieces — `wall-*`, `wall-pane-*`, `wall-fortified-*`, `tower-*`, `roof-*`, `wood-floor-*`, `tree-large`, `tree-shrub`, `water`, many `structure-*` and building-adjacent props.
- **Textures:** Shared **named maps** — `planks.png`, `cobblestone.png`, `cobblestoneAlternative.png`, `cobblestonePainted.png`, `roof.png`, `barrel.png`, `fence.png`, `tree.png`, `water.png`, `details.png`. No `colormap.png`.
- **Merged names:** unchanged. Canonical source for the following names that also exist in newer packs but are referenced by existing prefabs: `fence`, `overhang`, `roof`, `roof-corner`, `stairs-stone`, `stairs-wood`, `wall`, `wall-door`, `wall-half`.

### Survival Kit (`kenney_survival-kit`)

- **Meshes:** Survival/crafting flavor — `tool-*`, `workbench-*`, `tree`, `tree-tall`, `tree-log*`, `rock-flat`, `campfire-*`, `tent-*`, `bedroll-*`, `structure-canvas`, `structure-metal-*`, `barrel*`, `box*`, `bottle*`, `bucket`, docks, signs, etc.
- **Textures:** Single shared `Textures/colormap.png`. All Survival pieces sample from this atlas via `baseColorTexture` with `KHR_texture_transform`.
- **Merged names:** unchanged. This pack’s `colormap.png` lives in the merged `Models/GLB format/Textures/` folder, unchanged, so Survival pieces in existing prefabs continue to render correctly. Canonical source for the following names: `floor`, `structure`, `tree` (among others).

### Nature Kit (`kenney_nature-kit`)

- **Meshes:** Outdoor terrain and biome pieces — `ground_*` (grass, paths, rivers), `cliff_*`, `plant_*`, `flower_*`, `mushroom_*`, `crop_*`, `rock_*`, `stone_*`, `tree_pine*`, bridges, statues, etc. In the repo these live under the (mis-named) `Models/GLTF format/` merged folder but are actually 329 `.glb` files.
- **Textures:** **None.** Materials use `baseColorFactor` only (no images, no vertex colors). This is the **factor-only** branch that requires the custom `factor_lit_shader` documented in [kenney_gltf_ursina_integration_guide.md](./kenney_gltf_ursina_integration_guide.md) §5.
- **Note:** Nature Kit also ships a small clump `grass.obj`; the **game** terrain tile uses **`ground_grass.obj`** (see §5).

### Fantasy Town Kit (`kenney_fantasy-town-kit_2.0`) — NEW (WK31)

- **Official title:** `Fantasy Town Kit (2.0)` — Kenney, retrieved 2026-04-18.
- **License:** CC0 1.0 Universal (`kenney_fantasy-town-kit_2.0/License.txt`).
- **Filename suffix:** `-fantasy-town` (all `.glb` / `.obj` / `.mtl` + `Textures/colormap-fantasy-town.png`).
- **Meshes (167 `.glb`, all suffixed):**
  - **Walls** — `wall-fantasy-town`, `wall-half-fantasy-town`, `wall-broken-fantasy-town`, `wall-arch*-fantasy-town`, `wall-block*-fantasy-town`, `wall-corner*-fantasy-town`, `wall-curved-fantasy-town`, `wall-detail-*-fantasy-town` (cross / diagonal / horizontal), `wall-diagonal-fantasy-town`, `wall-door-fantasy-town`, `wall-doorway-*-fantasy-town`, `wall-rounded-fantasy-town`, `wall-side-fantasy-town`, `wall-slope-fantasy-town`, `wall-window-*-fantasy-town`, plus the full `wall-wood-*-fantasy-town` mirror set.
  - **Roofs** — `roof-fantasy-town`, `roof-flat-fantasy-town`, `roof-corner*-fantasy-town`, `roof-gable*-fantasy-town`, `roof-high*-fantasy-town` (incl. `roof-high-window-fantasy-town`), `roof-left-fantasy-town`, `roof-right-fantasy-town`, `roof-point-fantasy-town`, `roof-window-fantasy-town`.
  - **Stairs** — `stairs-full*-fantasy-town`, `stairs-stone*-fantasy-town`, `stairs-wide-*-fantasy-town`, `stairs-wood*-fantasy-town`, plus handrail variants.
  - **Street / public furniture** — `fence-fantasy-town`, `fence-broken-fantasy-town`, `fence-curved-fantasy-town`, `fence-gate-fantasy-town`, `fountain-*-fantasy-town`, `hedge-*-fantasy-town`, `lantern-fantasy-town`, `cart-fantasy-town`, `cart-high-fantasy-town`, `wheel-fantasy-town`, `banner-green-fantasy-town`, `banner-red-fantasy-town`.
  - **Market / stall** — `stall-fantasy-town`, `stall-bench-fantasy-town`, `stall-green-fantasy-town`, `stall-red-fantasy-town`, `stall-stool-fantasy-town`.
  - **Industry landmarks** — `windmill-fantasy-town`, `watermill-fantasy-town`, `watermill-wide-fantasy-town`.
  - **Road pieces** — `road-fantasy-town`, `road-bend-fantasy-town`, `road-corner-fantasy-town`, `road-corner-inner-fantasy-town`, `road-curb-fantasy-town`, `road-curb-end-fantasy-town`, `road-edge-fantasy-town`, `road-edge-slope-fantasy-town`, `road-slope-fantasy-town`.
  - **Masonry / construction** — `planks-fantasy-town`, `planks-half-fantasy-town`, `planks-opening-fantasy-town`, `poles-fantasy-town`, `poles-horizontal-fantasy-town`, `pillar-stone-fantasy-town`, `pillar-wood-fantasy-town`, `blade-fantasy-town`, `chimney-fantasy-town`, `chimney-base-fantasy-town`, `chimney-top-fantasy-town`, `overhang-fantasy-town`, `balcony-wall-fantasy-town`, `balcony-wall-fence-fantasy-town`.
  - **Rocks / trees** — `rock-large-fantasy-town`, `rock-small-fantasy-town`, `rock-wide-fantasy-town`, `tree-fantasy-town`, `tree-crooked-fantasy-town`, `tree-high-fantasy-town`, `tree-high-crooked-fantasy-town`, `tree-high-round-fantasy-town`.
- **Atlas texture:** `Textures/colormap-fantasy-town.png` (11 143 bytes). Each GLB’s `images[0].uri` references this pack-suffixed filename, so merged-tree loads resolve the correct atlas.
- **WK32 texture-override note:** Fantasy Town pieces often sample tiny regions of the shared atlas. If their flat brown/grey/teal reads do not match nearby Retro Fantasy buildings, do **not** mutate the Kenney GLBs. Use prefab-scoped `texture_override` PNGs plus the object-space override shader documented in [prefab_texture_override_standard.md](./prefab_texture_override_standard.md). `inn_v2` is the reference implementation.

### Graveyard Kit (`kenney_graveyard-kit_5.0`) — NEW (WK31)

- **Official title:** `Graveyard Kit (5.0)` — Kenney, retrieved 2026-04-18.
- **License:** CC0 1.0 Universal (`kenney_graveyard-kit_5.0/License.txt`).
- **Filename suffix:** `-graveyard` (all `.glb` / `.obj` / `.mtl` + `Textures/colormap-graveyard.png`).
- **Meshes (91 `.glb`, all suffixed):**
  - **Characters (5, animated-ready rig; same skeleton family as Blocky Characters):**
    - `character-ghost-graveyard` — translucent spirit, useful for apparition enemies.
    - `character-keeper-graveyard` — groundskeeper / gravedigger.
    - `character-skeleton-graveyard` — classic skeleton enemy.
    - `character-vampire-graveyard` — vampire / boss silhouette.
    - `character-zombie-graveyard` — zombie enemy.
  - **Crypts / structures** — `crypt-graveyard`, `crypt-a-graveyard`, `crypt-b-graveyard`, `crypt-door-graveyard`, `crypt-small-graveyard`, `crypt-small-roof-graveyard`, `crypt-large-graveyard`, `crypt-large-door-graveyard`, `crypt-large-roof-graveyard`.
  - **Graves / stones** — `grave-graveyard`, `grave-border-graveyard`, `gravestone-bevel-graveyard`, `gravestone-broken-graveyard`, `gravestone-cross-graveyard`, `gravestone-cross-large-graveyard`, `gravestone-debris-graveyard`, `gravestone-decorative-graveyard`, `gravestone-roof-graveyard`, `gravestone-round-graveyard`, `gravestone-wide-graveyard`, `coffin-graveyard`, `coffin-old-graveyard`, `cross-graveyard`, `cross-column-graveyard`, `cross-wood-graveyard`.
  - **Altars / ritual props** — `altar-stone-graveyard`, `altar-wood-graveyard`, `candle-graveyard`, `candle-multiple-graveyard`, `detail-bowl-graveyard`, `detail-chalice-graveyard`, `detail-plate-graveyard`, `urn-round-graveyard`, `urn-square-graveyard`.
  - **Brick / stone walls & fences** — `brick-wall-graveyard`, `brick-wall-end-graveyard`, `brick-wall-curve-graveyard`, `brick-wall-curve-small-graveyard`, `stone-wall-graveyard`, `stone-wall-curve-graveyard`, `stone-wall-column-graveyard`, `stone-wall-damaged-graveyard`, `fence-graveyard`, `fence-damaged-graveyard`, `fence-gate-graveyard`, `iron-fence-graveyard`, `iron-fence-bar-graveyard`, `iron-fence-curve-graveyard`, `iron-fence-damaged-graveyard`, `iron-fence-border-graveyard`, `iron-fence-border-column-graveyard`, `iron-fence-border-curve-graveyard`, `iron-fence-border-gate-graveyard`.
  - **Pillars / columns** — `pillar-small-graveyard`, `pillar-large-graveyard`, `pillar-square-graveyard`, `pillar-obelisk-graveyard`, `column-large-graveyard`, `border-pillar-graveyard`.
  - **Lighting** — `lantern-candle-graveyard`, `lantern-glass-graveyard`, `lightpost-single-graveyard`, `lightpost-double-graveyard`, `lightpost-all-graveyard`, `fire-basket-graveyard`.
  - **Benches / pumpkins / debris / trees** — `bench-graveyard`, `bench-damaged-graveyard`, `pumpkin-graveyard`, `pumpkin-carved-graveyard`, `pumpkin-tall-graveyard`, `pumpkin-tall-carved-graveyard`, `debris-graveyard`, `debris-wood-graveyard`, `hay-bale-graveyard`, `hay-bale-bundled-graveyard`, `pine-graveyard`, `pine-crooked-graveyard`, `pine-fall-graveyard`, `pine-fall-crooked-graveyard`, `trunk-graveyard`, `trunk-long-graveyard`, `rocks-graveyard`, `rocks-tall-graveyard`.
  - **Tools / road** — `shovel-graveyard`, `shovel-dirt-graveyard`, `road-graveyard`.
- **Atlas texture:** `Textures/colormap-graveyard.png` (10 965 bytes). Each GLB’s `images[0].uri` references this pack-suffixed filename, so merged-tree loads resolve the correct atlas.

---

## 3. Merged tree, the WK31 rename, and collisions

### 3.1 Directory layout

| Location | Role |
|----------|------|
| **`assets/models/Models/GLB format/`** | Primary merged library for kitbash. **458 `.glb`** — Retro Fantasy 105 + Survival 80 + Blocky Characters 18 + Fantasy Town 167 + Graveyard 91, with 3 Retro–Survival filename overlaps (`fence.glb`, `floor.glb`, `structure.glb`) counted once. Flat namespace, no collisions. |
| **`assets/models/Models/GLB format/Textures/`** | Merged texture bundle. Retro Fantasy's named maps (`planks.png`, `cobblestone*.png`, `roof.png`, `barrel.png`, `tree.png`, `water.png`, `details.png`, `fence.png`), Blocky Characters' per-character atlases (`texture-a.png` … `texture-r.png`), Survival Kit's `colormap.png`, and the pack-suffixed atlases **`colormap-fantasy-town.png`** + **`colormap-graveyard.png`**. |
| **`assets/models/Models/GLTF format/`** | Nature Kit's 329 `.glb` exports (factor-only; no `Textures/` sibling because there are no images). |
| **`assets/models/Models/OBJ format/`** | Parallel OBJ merge with its own `Textures/` sibling. Kept in sync (FT/Graveyard files + MTLs suffixed identically, pack colormaps in `Textures/`), but **not used at runtime** — GLB is the canonical runtime format. |
| **`assets/models/Models/Kenny raw downloads (for exact paths)/kenney_*/`** | Per-pack source of truth. Each pack has `Models/GLB format/*.glb` + `Models/GLB format/Textures/*.png`. After the WK31 rename, the two new packs' files are already pack-suffixed at rest in the raw tree (they are identical byte-for-byte to the merged copies). |
| **`assets/models/environment/`** | Promoted canonical runtime meshes used by `ursina_renderer.py` (see §5). |
| **`assets/models/Models/Textures/`** (parent of `OBJ format`) | Not the main texture bundle — only stray files (e.g. `variation-a.png`). Do not point loaders here. |

### 3.2 `colormap.png` no longer collides

Kenney ships `Textures/colormap.png` (same generic filename) in three different packs (Survival / Fantasy Town / Graveyard), each with its own palette atlas:

| Pack | Filename on disk (after WK31 rename) | MD5 | Bytes |
|------|---------------------------------------|-----|------:|
| Survival Kit             | `colormap.png`               | `8aa3d8b5a7ce10fad67e7ba1011689eb` | 7 440 |
| Fantasy Town Kit (2.0)   | `colormap-fantasy-town.png`  | `4526ace57f13a8aafd664aca2baff539` | 11 143 |
| Graveyard Kit (5.0)      | `colormap-graveyard.png`     | `485dedc9b20157a1274434407a7d0241` | 10 965 |

Retro Fantasy uses **named textures** — it has no `colormap.png`, so it never participated in the collision.

The WK31 round-2 rename resolves the collision permanently. **Every Fantasy Town and Graveyard `.glb`, `.obj`, and `.mtl` now carries a pack suffix, and every internal reference** (GLB `images[].uri`, OBJ `mtllib`, MTL `map_Kd`) was rewritten to match:

- `cart.glb` → `cart-fantasy-town.glb` (GLB internal URI: `Textures/colormap.png` → `Textures/colormap-fantasy-town.png`).
- `altar-stone.glb` → `altar-stone-graveyard.glb` (GLB internal URI: `Textures/colormap.png` → `Textures/colormap-graveyard.png`).
- OBJ + MTL pairs are suffixed in lockstep and their `mtllib` / `map_Kd` lines updated.

All three atlases now coexist side-by-side in `Models/GLB format/Textures/` and each piece resolves its own. Survival Kit pieces still use the unsuffixed `colormap.png` exactly as before — no regression for existing prefabs.

### 3.3 Geometry filename collisions

Before the rename there were **14 `.glb` filename collisions** across packs. After the rename only the three cross-older-pack collisions remain (all inside Retro Fantasy + Survival, which is historical and well-understood):

- `fence.glb`  (Retro Fantasy vs Survival) — merged copy is **Retro Fantasy's** (WK31 round-2 restored).
- `floor.glb`  (Retro Fantasy vs Survival) — merged copy is **Survival's** (historical, pre-dates WK31).
- `structure.glb` (Retro Fantasy vs Survival) — merged copy is **Survival's** (used by `ranger_guild_v1`).

The 11 new-pack collisions (`fence-gate`, `overhang`, `road`, `roof`, `roof-corner`, `stairs-stone`, `stairs-wood`, `tree`, `wall`, `wall-door`, `wall-half`) no longer exist in the merged tree under those plain names — every FT / Graveyard variant carries its pack suffix, so e.g. `roof.glb` is uniquely the Retro Fantasy version and `roof-fantasy-town.glb` is the FT version. Both coexist peacefully.

The 8 files restored to their Retro Fantasy source in WK31 round-1 (`overhang`, `roof`, `roof-corner`, `stairs-stone`, `stairs-wood`, `wall`, `wall-door`, `wall-half`) stay on Retro Fantasy after the round-2 rename. `fence.glb` was additionally restored to Retro Fantasy in round-2. `tree.glb` was additionally restored to Survival in round-2.

### 3.4 OBJ / MTL pathing

In each raw pack, `map_Kd Textures/foo.png` is relative to the `.mtl` file, i.e. `.../<pack>/Models/OBJ format/Textures/foo.png`. After the merge, the same filenames are expected under `assets/models/Models/OBJ format/Textures/`. The OBJ pipeline is **not** used at runtime today (GLB is the canonical runtime format), but the OBJ merged tree is kept in sync with the rename (FT/Graveyard OBJs + MTLs suffixed identically, pack-suffixed colormaps added to `Models/OBJ format/Textures/`).

---

## 4. Tools: how the viewer and assembler see this tree

### 4.1 Viewer — `tools/model_viewer_kenney.py`

- Scans `environment/` + each `Kenny raw downloads (for exact paths)/kenney_*/` pack directly. **Never reads from merged `Models/GLB format` / `Models/GLTF format`.** Each pack's pieces appear in their own grid column with their own textures (the pack-suffixed `colormap-*.png` lives next to each pack's GLBs in the raw tree).
- Pack order (`KENNEY_PACKS_ORDERED` tuple) — one grid column per pack:
  1. Blocky Characters
  2. Nature Kit
  3. Retro Fantasy Kit
  4. Survival Kit
  5. **Fantasy Town Kit** — grid tiles show the pack-suffixed file names (e.g. `cart-fantasy-town.glb`).
  6. **Graveyard Kit** — grid tiles show the pack-suffixed file names (e.g. `altar-stone-graveyard.glb`).
  7. Cursor Pixel Pack (empty — 2D tilesheet only)
- Per-geom classifier (`_apply_gltf_color_and_shading`) routes each piece to unlit (textured) or custom lit (factor-only) — see the integration guide §5.
- WK32 texture override support: `--focus-prefab <prefab_id>` shows the unique model pieces referenced by a prefab and applies any `texture_override` entries for inspection. Automated tool screenshots use `--screenshot-subdir`, `--screenshot-stem`, and `--auto-exit-sec`.

### 4.2 Assembler — `tools/model_assembler_kenney.py`

- **Library scan roots (`PIECE_LIB_SUBDIRS`):**
  1. `Models/GLB format` *(all Retro Fantasy + Survival + Blocky + suffixed Fantasy Town + suffixed Graveyard — one flat list, no collisions)*
  2. `Models/GLTF format` *(Nature Kit — factor-only)*
- No raw-tree scan is needed anymore: the merged tree is collision-free, and every new-pack file's name carries its pack id so humans can tell them apart in the filter.
- **Saved prefab JSON `model` fields** are POSIX paths relative to `assets/models/`. Fantasy Town / Graveyard pieces serialize as plain merged paths with pack-suffixed filenames, e.g. `Models/GLB format/cart-fantasy-town.glb`. The runtime renderer (`game/graphics/ursina_renderer.py`) prepends `assets/models/` and loads directly — no loader change needed.
- **Optional `texture_override` fields** are POSIX paths relative to `assets/`. The assembler mirrors the runtime override display via `game/graphics/prefab_texture_overrides.py`; this is required for visual review parity.
- **Attribution guesser (`_guess_attribution`):**
  1. First checks the **filename suffix** via `FILENAME_SUFFIX_PACK_IDS` — `*-fantasy-town.glb` → `kenney_fantasy-town-kit_2.0`, `*-graveyard.glb` → `kenney_graveyard-kit_5.0`. This is exact (no human trim needed for the two new packs).
  2. Then checks for a `kenney_*` segment in the rel path (via `RAW_TREE_PACK_IDS`) — for the rare case a prefab references a raw-tree path directly.
  3. Falls back to the well-known per-folder pair for merged pieces with no suffix — `Models/GLB format` → Retro Fantasy + Survival (or Blocky Characters for a `character-<a..r>.glb` skin); `Models/GLTF format` → Nature Kit.

### 4.3 Which path to pick when

| Scenario | Preferred path in prefab JSON |
|----------|-------------------------------|
| Retro Fantasy piece (walls / roofs / towers / wood-floor / `fence` / `floor` / `structure` / `tree-*` where `*` is a Retro name) | Merged: `Models/GLB format/<name>.glb` |
| Survival Kit piece (barrels / boxes / tents / `structure` / `tree-tall` / camp props / etc.) | Merged: `Models/GLB format/<name>.glb` |
| Nature Kit piece (`ground_*`, `rock_*`, `tree_pine*`, etc.) | Merged: `Models/GLTF format/<name>.glb` |
| Blocky Characters skin (`character-a` … `character-r`) | Merged: `Models/GLB format/character-<a..r>.glb` |
| **Fantasy Town piece** | **Merged:** `Models/GLB format/<name>-fantasy-town.glb` |
| **Graveyard piece** | **Merged:** `Models/GLB format/<name>-graveyard.glb` |

The library rows in the assembler are the unadorned filename — which for the two new packs already tells you the pack.

---

## 4.4 Prefab texture overrides for weak pack materials

Some Kenney packs are technically correct but stylistically too flat or too atlas-limited for a specific Kingdom Sim building. The WK32 Inn pass proved a safe remediation path:

- Add generated or license-safe texture PNGs under `assets/textures/buildings/<prefab_or_family>/`.
- Add optional `texture_override` fields to only the affected prefab pieces.
- Use `game/graphics/prefab_texture_overrides.py` to cache, bind, and object-space-map those textures.
- Clear source atlas texture state recursively so original pack colors do not bleed through.
- Verify with both automated tool screenshots and in-game screenshots beside the target building family.

Use this for scoped polish only. It does **not** replace the pack import/rename rules above, and it does **not** justify editing raw Kenney GLBs. Full step-by-step standard: [prefab_texture_override_standard.md](./prefab_texture_override_standard.md).

---

## 5. `assets/models/environment/` → canonical Kenney sources

These are **promoted** meshes for `game/graphics/ursina_renderer.py` (`_environment_model_path`). Where the runtime name differs from the download (`grass.obj`, `path.obj`, `rock.obj`), the **geometry** matches the file in the **merged** library `assets/models/Models/OBJ format/` (same bytes as the corresponding pack under `Kenny raw downloads (for exact paths)/`).

| Runtime file | Kenney source (same mesh as in `Models/OBJ format/`) | Notes |
|--------------|------------------------------------------------------|--------|
| `grass.obj` | Nature Kit — `ground_grass.obj` | `mtllib grass.mtl`; materials from `ground_grass.mtl` (flat `Kd` grass). |
| `path.obj` | Nature Kit — `ground_pathTile.obj` | `mtllib path.mtl`; materials from `ground_pathTile.mtl` (`grass` / `dirt` / `dirtDark`). |
| `rock.obj` | Survival Kit — `rock-flat.obj` | `mtllib rock.mtl`. **Texture:** the stock MTL references `Textures/colormap.png`; `environment/rock.mtl` instead uses a flat `Kd` gray so the folder stays self-contained (no `environment/Textures/`). |
| `tree_pine.obj` | *(unchanged on purpose)* | **Canonical match in the asset library:** `assets/models/Models/GLB format/tree-tall.glb` (Survival Kit **tree-tall**). The committed `.obj` was not swapped to avoid a visual change here; treat **`tree-tall`** as the reference when choosing materials or comparing formats. |

---

## 6. Filename prefixes / suffixes → pack (merged trees)

Use this when you need to know **which download to diff against** or which `License.txt` applies.

### Blocky Characters only (merged `GLB format/`)

| Pattern | ~Count | Pack |
|---------|--------|------|
| `character-a` … `character-r` | 18 | `kenney_blocky-characters_20` |

### Fantasy Town (merged `GLB format/`)

| Pattern | Count | Pack |
|---------|------:|------|
| `*-fantasy-town.glb` | 167 | `kenney_fantasy-town-kit_2.0` |

### Graveyard (merged `GLB format/`)

| Pattern | Count | Pack |
|---------|------:|------|
| `*-graveyard.glb` | 91 | `kenney_graveyard-kit_5.0` |

### Mostly Retro Fantasy Kit (merged `GLB format/`)

| Pattern | ~Count | Notes |
|---------|--------|--------|
| `wall-*`, `wall-paint-*`, `wall-fortified-*`, `wall-pane-*` | 39 | Forts, gates, doors, windows. |
| `roof-*`, `battlement-*`, `tower-*` | varies | Modular roofs, battlements, towers. |
| `floor-*`, `wood-floor-*` | varies | Floors (`floor.glb` is Survival by convention) and stairs. |
| `water` | 1 | Water plane. |

### Mostly Survival Kit (merged `GLB format/`)

| Pattern | ~Count | Notes |
|---------|--------|--------|
| `tool-*`, `workbench-*` | 10 each | Tools and benches. |
| `campfire-*`, `tent-*`, `bedroll-*` | varies | Camp props. |
| `box*`, `bottle*`, `barrel*`, `barrels`, `bucket` | varies | Containers. |
| `structure-canvas`, `structure-metal-*`, `structure`, `tent-canvas`, `tree-tall` | varies | Used by `ranger_guild_v1`. Share `colormap.png` — merged colormap stays pinned to Survival (§3.2). |

### Mostly Nature Kit (merged `GLTF format/`)

| Pattern | Role |
|---------|------|
| `ground_*` | Grass tiles, path/river tiles, banks, corners |
| `cliff_*` | Cliff blocks |
| `plant_*`, `flower_*`, `mushroom_*`, `crops_*`, `crop_*` | Foliage and farming |
| `rock_*`, `stone_*` | Rocks and stones (many variants) |
| `tree_pine*`, other `tree_*` | Pines and assorted trees |
| `bridge_*`, `statue_*`, `lily_*`, `cactus_*`, … | Odds and ends |

---

## 7. Export formats: what to use when

| Format | When to prefer |
|--------|----------------|
| **GLB** | Default runtime format. Single-file import; textures resolved relative to the GLB. Required by `tools/model_viewer_kenney.py` and `tools/model_assembler_kenney.py`. |
| **glTF** (split JSON + buffers / images) | Good for external tooling (Blender, etc.). Not used by the viewer / assembler. |
| **OBJ** | Legacy. Used only by the stashed `assets/models/environment/*.obj` (grass / path / rock / tree_pine) that pre-dates the GLB pipeline; kept for MTL-based texture customization. The merged `Models/OBJ format/` tree stays in sync with GLB for parity / diffing only. |

**Canonical for merged content in this repo:** **GLB** under `assets/models/Models/GLB format/` + `assets/models/Models/GLTF format/`.

**glTF integration pitfalls (unlit vs factors, etc.):** [kenney_gltf_ursina_integration_guide.md](./kenney_gltf_ursina_integration_guide.md).

**Standalone GLB browser (dev):** `python tools/model_viewer_kenney.py` — see the integration guide §9.

---

## 8. License and attribution

| Pack | Read this file |
|------|----------------|
| Blocky Characters | `assets/models/Models/Kenny raw downloads (for exact paths)/kenney_blocky-characters_20/License.txt` (duplicate summary at `assets/models/License.txt`) |
| Retro Fantasy Kit | `.../kenney_retro-fantasy-kit/License.txt` |
| Survival Kit | `.../kenney_survival-kit/License.txt` |
| Nature Kit | `.../kenney_nature-kit/License.txt` |
| **Fantasy Town Kit** | `.../kenney_fantasy-town-kit_2.0/License.txt` |
| **Graveyard Kit** | `.../kenney_graveyard-kit_5.0/License.txt` |
| Cursor Pixel Pack | `.../kenney_cursor-pixel-pack/License.txt` |

All CC0 1.0 Universal. When shipping, cite **each** pack you actually use (mirror the entries in `assets/ATTRIBUTION.md`).

---

## 9. Maintenance checklist

- [ ] **When adding a new Kenney download that ships `Textures/colormap.png`** or otherwise collides with existing filenames, apply the WK31 rename convention: **suffix every model file** (`<stem>-<pack-suffix>.glb` / `.obj` / `.mtl`), **rename the pack's `colormap.png`** to `colormap-<pack-suffix>.png`, and **rewrite each GLB's internal `images[].uri`** + each OBJ `mtllib` + each MTL `map_Kd` to match. A reference implementation lives in the WK31 round-2 commit (one-shot Python script; not kept in the repo). Pack suffix should be short, filesystem-safe, and not overlap an existing pack suffix.
- [ ] **After importing a renamed pack**, copy the suffixed files into `Models/GLB format/` + `Models/GLB format/Textures/<colormap-<suffix>.png>` (and the matching OBJ / MTL / Textures under `Models/OBJ format/`). Delete any stale unsuffixed copies from the merged tree that got introduced by an earlier unrenamed extract.
- [ ] **Tools stay in sync:** `tools/model_viewer_kenney.py` needs the pack added to `KENNEY_PACKS_ORDERED`; `tools/model_assembler_kenney.py` needs the pack's filename suffix added to `FILENAME_SUFFIX_PACK_IDS` (and optionally its folder to `RAW_TREE_PACK_IDS` for raw-tree prefab paths).
- [ ] **If a texture fails to load**, compare merged paths to the matching `Kenney raw downloads/.../Models/GLB format/Textures/` file and confirm the same basename exists under `assets/models/Models/GLB format/Textures/`.
- [ ] **If a source pack texture is visually insufficient but technically loading**, use [prefab_texture_override_standard.md](./prefab_texture_override_standard.md). Do not edit Kenney GLBs; add scoped generated/acquired textures under `assets/textures/`, `texture_override` metadata, attribution, tool captures, and QA evidence.
- [ ] **For legal screens**, cite **each** pack you ship assets from (use the seven `License.txt` files above).
- [ ] **After adding a new Kenney download**, document the new mapping here (§2 pack section + §6 prefix / suffix table + §8 license row).

---

## 10. Revision history

- **v1.0** — Initial map: Blocky Characters, Nature Kit, Retro Fantasy Kit, Survival Kit, Cursor Pixel Pack. Merged `Models/OBJ format/` as canonical. Environment mapping table.
- **v1.1 (WK31 round-1, 2026-04-18)** — Added **Fantasy Town Kit (2.0)** and **Graveyard Kit (5.0)**. Documented the `Textures/colormap.png` collision and the 14 geometry filename collisions; restored 8 merged GLBs to Retro Fantasy sources to keep existing prefabs correct. Viewer adds the two packs to `KENNEY_PACKS_ORDERED`; assembler temporarily adds raw-tree scan roots for the two new packs (tagged `[fantasy-town]` / `[graveyard]` in the library) and extends `_guess_attribution` to handle raw-tree paths via `RAW_TREE_PACK_IDS`.
- **v1.2 (WK31 round-2, 2026-04-18)** — **Pack-suffix rename** (`-fantasy-town` / `-graveyard`) applied to every FT / Graveyard `.glb`, `.obj`, `.mtl`, and the shared `colormap.png` — plus rewriting every GLB `images[].uri`, OBJ `mtllib`, and MTL `map_Kd` reference. Merged tree now collision-free and each piece resolves its own atlas from `Models/GLB format/Textures/`: `colormap.png` (Survival), `colormap-fantasy-town.png`, `colormap-graveyard.png`. Assembler simplified: `PIECE_LIB_SUBDIRS` no longer includes raw-tree scan; `_guess_attribution` prefers filename-suffix attribution via `FILENAME_SUFFIX_PACK_IDS` (exact, no human trim). Round-2 also additionally restored `fence.glb` (to Retro Fantasy) and `tree.glb` (to Survival).
- **v1.3 (WK32 Inn texture override, 2026-04-25)** — Documented prefab-scoped texture overrides for weak Kenney material reads. Added links to the new standard covering generated textures, object-space texture mapping, recursive texture-state cleanup, tool screenshots, and the `inn_v2` reference implementation.
