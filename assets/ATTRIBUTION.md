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

## Audio Assets

### Pack: Kenney Game Assets: Audio
- **Author / publisher**: Kenney (`https://kenney.nl/`)
- **License**: CC0 1.0 Universal (see `assets/audio/third_party/kenney_audio_cc0/LICENSE_CC0-1.0.txt`)
- **Source**: `https://kenney.nl/assets/audio-pack`
- **Retrieved**: 2026-01-27
- **Modifications**: Curated subset (UI clicks, building placement, building destruction sounds); normalized volume levels
- **Used for**: UI clicks, building placement/destruction sounds
- **File locations**:
  - `assets/audio/sfx/ui_click.wav`
  - `assets/audio/sfx/building_place.wav`
  - `assets/audio/sfx/building_destroy.wav`

### Pack: OpenGameArt CC0 Collections
- **Author / publisher**: rubberduck (opengameart.org) + other CC0 contributors
- **License**: CC0 1.0 Universal
- **Source**: `https://opengameart.org/content/100-cc0-sfx` (and related RPG Sound Pack collections)
- **Retrieved**: 2026-01-27
- **Modifications**: Curated subset (ranged weapon sounds: bow twang, arrow release); normalized volume levels
- **Used for**: Ranged weapon attack sounds (bow release for Ranger, SkeletonArcher, Ballista)
- **File locations**:
  - `assets/audio/sfx/bow_release.wav`

### Pack: Freesound.org CC0 Ambient Loops
- **Author / publisher**: Various CC0 contributors (see `assets/audio/third_party/freesound_cc0/README.txt`)
- **License**: CC0 1.0 Universal
- **Source**: `https://freesound.org` (filtered: CC0 license, "ambient medieval" / "ambient fantasy" / "ambient loop")
- **Retrieved**: 2026-01-27
- **Modifications**: Converted to .ogg format for efficient compression; normalized volume (0.4 baseline)
- **Used for**: Background ambient atmosphere (single neutral loop for Build A)
- **File locations**:
  - `assets/audio/ambient/ambient_loop.ogg`

### Pack: Additional CC0 Sources (Bounty Placement)
- **Author / publisher**: Various CC0 contributors (TBD once assets sourced)
- **License**: CC0 1.0 Universal
- **Source**: TBD (will be updated once assets are sourced)
- **Retrieved**: TBD
- **Modifications**: TBD
- **Used for**: Bounty placement sound
- **File locations**:
  - `assets/audio/sfx/bounty_place.wav`


