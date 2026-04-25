## Attribution (Third-Party Assets)

This file tracks all CC0 / open-license assets included in `assets/` (sprites, UI, etc.).
If `assets/third_party/<pack_name>/` exists, this file must exist and be kept up to date.

---

## Credits / Attribution format (required fields)

For each pack:
- **Pack name**:
- **Author / publisher**:
- **License**: (exact license name, e.g., CC0-1.0 / CC-BY-4.0)
- **Source**: (URL)
- **Retrieved**: (YYYY-MM-DD)
- **Modifications**: (e.g., resized to 32×32, palette adjustment, re-exported frames)
- **Used for**: (heroes / enemies / buildings / UI)
- **File locations**:
  - `assets/sprites/...` (list directories)
  - `assets/ui/...` (list directories, if any)

### Pack: <pack_name>
- **Author / publisher**:
- **License**:
- **Source**:
- **Retrieved**:
- **Modifications**:
- **Used for**:
- **File locations**:

### Pack: Kenney (curated subset, CC0)
- **Author / publisher**: Kenney (`https://kenney.nl/`)
- **License**: CC0 1.0 Universal (see `assets/third_party/kenney_cc0/LICENSE_CC0-1.0.txt`)
- **Source**: `https://kenney.nl/assets`
- **Retrieved**: 2025-12-21
- **Modifications**:
  - curated subset only (avoid repo bloat)
  - normalized to 32×32 alignment; nearest-neighbor only
  - where needed for validator coverage, a single `frame_000.png` may be duplicated across required action/state folders as an initial placeholder
- **Used for**: heroes, enemies, buildings
- **File locations**:
  - `assets/sprites/heroes/<warrior|ranger|rogue|wizard>/{idle,walk,attack,hurt,inside}/frame_###.png`
  - `assets/sprites/enemies/<goblin|wolf|skeleton>/{idle,walk,attack,hurt,dead}/frame_###.png`
  - `assets/sprites/buildings/<building_type>/{built,construction,damaged}/frame_###.png`

---

## Steam patch notes “Credits / Attribution” bullets (copy/paste)

Use this exact bullet structure (one bullet per pack):
- `<Pack Name>` by `<Author>` — License: `<License>` — Source: `<URL>` — Used for: `<heroes/enemies/buildings/ui>`

---

### Pack: Kenney Retro Fantasy Kit (3D models, CC0)
- **Author / publisher**: Kenney (`https://kenney.nl/`)
- **License**: CC0 1.0 Universal (see `assets/models/Models/Kenny raw downloads (for exact paths)/kenney_retro-fantasy-kit/License.txt`)
- **Source**: `https://kenney.nl/assets/retro-fantasy-kit`
- **Retrieved**: 2026-04-16
- **Modifications**: none (GLB pieces referenced by path from building prefabs)
- **Used for**: 3D building prefabs (walls, roofs, floors, doors) kitbashed via `tools/model_assembler_kenney.py`
- **File locations**:
  - `assets/models/Models/GLB format/*.glb` (merged pass-through tree; the piece picker reads from here)
  - `assets/models/Models/Kenny raw downloads (for exact paths)/kenney_retro-fantasy-kit/Models/GLB format/*.glb` (raw)
  - Referenced by `assets/prefabs/buildings/*.json` via `pieces[].model` (prefab attribution: `kenney_retro-fantasy-kit`)

---

### Pack: Kenney Fantasy Town Kit 2.0 (3D models, CC0)
- **Author / publisher**: Kenney (`https://kenney.nl/`)
- **License**: CC0 1.0 Universal (see `assets/models/Models/Kenny raw downloads (for exact paths)/kenney_fantasy-town-kit_2.0/License.txt`)
- **Source**: `https://kenney.nl/assets/fantasy-town-kit`
- **Retrieved**: 2026-04-18
- **Modifications**: All 167 `.glb` + 167 `.obj` + 167 `.mtl` files renamed with the `-fantasy-town` suffix (e.g. `cart.glb` → `cart-fantasy-town.glb`). The shared atlas `Textures/colormap.png` was renamed to `Textures/colormap-fantasy-town.png`, and every GLB's internal `images[].uri` + every OBJ `mtllib` + every MTL `map_Kd` was rewritten to match. Rationale: remove the `Textures/colormap.png` filename collision with Survival Kit + Graveyard Kit in the merged tree, and embed the pack id into each filename for easier identification in the model viewer / assembler. See `.cursor/plans/kenney_assets_models_mapping.plan.md` §3.
- **Used for**: 3D civic / village building prefabs — walls, roofs, stairs, chimneys, banners, carts, fountains, hedges, fences, stalls, road / paving tiles, windmill / watermill, trees, rocks. Planned use: economy buildings (inn, farm, food stand, marketplace) in WK31 Part B.
- **File locations**:
  - `assets/models/Models/GLB format/*-fantasy-town.glb` (canonical merged path for prefab `model` fields)
  - `assets/models/Models/GLB format/Textures/colormap-fantasy-town.png` (shared atlas)
  - `assets/models/Models/OBJ format/*-fantasy-town.{obj,mtl}` (parallel legacy tree, kept in sync)
  - `assets/models/Models/Kenny raw downloads (for exact paths)/kenney_fantasy-town-kit_2.0/Models/{GLB,OBJ} format/*` (raw source of truth, identical byte-for-byte to the merged copies)
  - Referenced by `assets/prefabs/buildings/*.json` via `pieces[].model` (prefab attribution: `kenney_fantasy-town-kit_2.0`)

---

### Pack: Kenney Graveyard Kit 5.0 (3D models, CC0)
- **Author / publisher**: Kenney (`https://kenney.nl/`)
- **License**: CC0 1.0 Universal (see `assets/models/Models/Kenny raw downloads (for exact paths)/kenney_graveyard-kit_5.0/License.txt`)
- **Source**: `https://kenney.nl/assets/graveyard-kit`
- **Retrieved**: 2026-04-18
- **Modifications**: All 91 `.glb` + 91 `.obj` + 91 `.mtl` files renamed with the `-graveyard` suffix (e.g. `altar-stone.glb` → `altar-stone-graveyard.glb`). The shared atlas `Textures/colormap.png` was renamed to `Textures/colormap-graveyard.png`, and every GLB's internal `images[].uri` + every OBJ `mtllib` + every MTL `map_Kd` was rewritten to match. Rationale: same as Fantasy Town — remove the `Textures/colormap.png` filename collision and embed the pack id into each filename. See `.cursor/plans/kenney_assets_models_mapping.plan.md` §3.
- **Used for**: 3D gothic / cemetery props (altars, crypts, coffins, gravestones, iron fences, lanterns, pumpkins, pines) plus **5 animated-ready characters** (`character-ghost-graveyard`, `character-keeper-graveyard`, `character-skeleton-graveyard`, `character-vampire-graveyard`, `character-zombie-graveyard`) usable as enemy placeholders. Planned use: enemy lairs (skeleton_crypt, bandit_camp, etc.) and atmospheric prop dressing.
- **File locations**:
  - `assets/models/Models/GLB format/*-graveyard.glb` (canonical merged path for prefab `model` fields)
  - `assets/models/Models/GLB format/Textures/colormap-graveyard.png` (shared atlas)
  - `assets/models/Models/OBJ format/*-graveyard.{obj,mtl}` (parallel legacy tree, kept in sync)
  - `assets/models/Models/Kenny raw downloads (for exact paths)/kenney_graveyard-kit_5.0/Models/{GLB,OBJ} format/*` (raw source of truth, identical byte-for-byte to the merged copies)
  - Referenced by `assets/prefabs/buildings/*.json` via `pieces[].model` (prefab attribution: `kenney_graveyard-kit_5.0`)

---

### Pack: Kenney Nature Kit 2.1 (3D models, CC0)
- **Author / publisher**: Kenney (`https://kenney.nl/`)
- **License**: CC0 1.0 Universal (see `assets/models/Models/Kenny raw downloads (for exact paths)/kenney_nature-kit/License.txt`)
- **Source**: `https://kenney.nl/assets/nature-kit`
- **Retrieved**: 2026-04-18
- **Modifications**: Selected `.glb` meshes copied into `assets/models/environment/` under stable names (e.g. `grass_tuft_a.glb` ← `Models/GLTF format/grass.glb`) for WK32 grass variety + nature doodad scatter sourcing; originals remain under `Models/GLTF format/`.
- **Used for**: Terrain scatter (grass tufts, flowers, rocks, bushes, logs, stumps, mushrooms) alongside existing `environment/grass.obj` path; building prefab accents (logs, rocks) where referenced from prefab JSON.
- **File locations**:
  - `assets/models/Models/GLTF format/*.glb` (merged Nature Kit — factor-only shader path in tools/game)
  - `assets/models/environment/grass_tuft_a.glb`, `grass_tuft_b.glb`, `grass_flower_red.glb`, `grass_flower_yellow.glb` (Nature Kit GLB copies; names match `ursina_renderer._environment_grass_and_doodad_model_lists` tokens)
  - `assets/models/environment/bush_small.glb`, `bush_large.glb`, `rock_small_a.glb`, `rock_small_b.glb`, `rock_small_c.glb`, `log_wide.glb`, `stump_round.glb`, `mushroom_tan.glb` (scanner prefixes: `bush` / `rock` / `log` / `stump` / `mushroom`)
  - `assets/models/environment/rock_gy_cluster.obj`, `rock_gy_tall.obj` (promoted from Kenney Graveyard Kit OBJ exports + `rocks-graveyard.mtl` / `rocks-tall-graveyard.mtl` in the same folder)
  - `assets/models/environment/log_survival.obj`, `log_small.obj` (promoted from Kenney Survival Kit `tree-log.obj` / `tree-log-small.obj` + `tree-log.mtl` sidecars)
  - Referenced by `assets/prefabs/buildings/*.json` via `pieces[].model` where applicable (prefab attribution: `kenney_nature-kit`)

---

### Pack: kingdomsim_cc0_placeholders
- **Author / publisher**: Kingdom Sim (Jaimie Montague + AI-assisted tooling)
- **License**: CC0-1.0
- **Source**: Generated in-repo (see `assets/third_party/kingdomsim_cc0_placeholders/README.txt`)
- **Retrieved**: 2025-12-21
- **Modifications**: N/A (generated directly as 32x32, pixel-aligned)
- **Used for**: heroes / enemies / buildings (initial placeholder PNG coverage to replace procedural shapes/letters)
- **File locations**:
  - `assets/sprites/heroes/*/*/frame_000.png`
  - `assets/sprites/enemies/*/*/frame_000.png`
  - `assets/sprites/buildings/*/*/frame_000.png`

---

### Pack: kingdomsim_ui_cc0
- **Author / publisher**: Kingdom Sim (Jaimie Montague + AI-assisted tooling)
- **License**: CC0-1.0 (see `assets/third_party/kingdomsim_ui_cc0/LICENSE_CC0-1.0.txt`)
- **Source**: Generated in-repo (see `assets/third_party/kingdomsim_ui_cc0/README.txt`)
- **Retrieved**: 2026-01-18
- **Modifications**: N/A (generated directly as pixel-aligned UI textures/icons)
- **Used for**: UI panels, buttons, and icons
- **File locations**:
  - `assets/ui/kingdomsim_ui_cc0/panels/*.png`
  - `assets/ui/kingdomsim_ui_cc0/buttons/*.png`
  - `assets/ui/kingdomsim_ui_cc0/icons/*.png`

---

### Pack: kingdomsim_generated_building_textures
- **Author / publisher**: Kingdom Sim (Jaimie Montague + AI-assisted tooling)
- **License**: CC0-1.0
- **Source**: Generated in-repo by `tools/generate_inn_texture_overrides.py`; online low-poly fantasy references used for style only, with no third-party pixels copied.
- **Retrieved**: 2026-04-25
- **Modifications**: N/A (generated directly as 128x128 PNG texture overrides)
- **Used for**: Inn building texture polish (wood planks, stone blocks, roof shingles)
- **File locations**:
  - `assets/textures/buildings/inn/inn_wood_planks.png`
  - `assets/textures/buildings/inn/inn_stone_blocks.png`
  - `assets/textures/buildings/inn/inn_roof_shingles.png`

---

## Audio Assets

### Pack: Kenney Game Assets: Audio
- **Author / publisher**: Kenney (`https://kenney.nl/`)
- **License**: CC0 1.0 Universal (see `assets/audio/third_party/kenney_audio_cc0/LICENSE_CC0-1.0.txt`)
- **Source**: `https://kenney.nl/assets/audio-pack`
- **Retrieved**: 2026-01-27
- **Modifications**: Curated subset (UI clicks, building placement sounds); normalized volume levels
- **Used for**: UI clicks, UI confirm/error, building placement sounds
- **File locations**:
  - `assets/audio/sfx/ui_click.ogg`
  - `assets/audio/sfx/ui_confirm.ogg`
  - `assets/audio/sfx/ui_error.ogg`
  - `assets/audio/sfx/building_place.ogg`

### Pack: OpenGameArt CC0 Collections
- **Author / publisher**: rubberduck (opengameart.org) + other CC0 contributors
- **License**: CC0 1.0 Universal
- **Source**: `https://opengameart.org/content/100-cc0-sfx` (and related RPG Sound Pack collections)
- **Retrieved**: 2026-01-27
- **Modifications**: Curated subset (ranged weapon sounds, building destruction, bounty placement, combat sounds, celebration sounds); normalized volume levels
- **Used for**: Ranged weapon attack sounds (bow release), building destruction, bounty placement/claim, combat sounds (melee hit, enemy death), celebration sounds (lair cleared), hero hire/purchase confirmations
- **File locations**:
  - `assets/audio/sfx/bow_release.ogg`
  - `assets/audio/sfx/building_destroy.ogg`
  - `assets/audio/sfx/bounty_place.ogg`
  - `assets/audio/sfx/bounty_claimed.ogg`
  - `assets/audio/sfx/hero_hired.ogg`
  - `assets/audio/sfx/melee_hit.ogg`
  - `assets/audio/sfx/enemy_death.ogg`
  - `assets/audio/sfx/lair_cleared.ogg`
  - `assets/audio/sfx/purchase.ogg`

### Pack: Freesound.org CC0 Ambient Loops
- **Author / publisher**: neartheatmoshphere (Freesound.org user)
- **License**: CC0 1.0 Universal
- **Source**: `https://freesound.org/people/neartheatmoshphere/sounds/676787/` ("Blinking Forest Acoustic")
- **Retrieved**: 2026-01-27
- **Modifications**: Renamed to `ambient_loop.wav`; normalized volume (0.4 baseline)
- **Used for**: Background ambient atmosphere (single neutral loop for Build A)
- **File locations**:
  - `assets/audio/ambient/ambient_loop.wav`

### wk14: Interior ambient and building-under-attack (optional)

Interior ambient loops (per building type) and the building-under-attack rumble SFX are **optional**. When CC0 assets are added, they will be listed here with pack, license, and file locations. Until then, the game runs without these files (fail silently). Required filenames: see `game/audio/EVENT_CONTRACT.md` (Interior ambient + Interior building-under-attack sections).


