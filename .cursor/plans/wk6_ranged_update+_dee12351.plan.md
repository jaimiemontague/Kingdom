---
name: WK6 Ranged Update+
overview: Add an audio pipeline with CC0 SFX/ambient, improve Build UI with clickable building list, make bounties visible/targetable even in black fog, and enhance Ranger exploration behavior with XP for revealing black fog—keeping QA gates and determinism principles intact.
todos:
  - id: wk6-audio-system
    content: Implement AudioSystem + CC0 audio asset structure + event hooks + attribution validation
    status: completed
  - id: wk6-build-menu
    content: Add clickable Build menu list; unify hotkey and click selection into one path
    status: completed
  - id: wk6-fog-bounties
    content: Render bounties in black fog and ensure Rangers can path/respond to those bounties
    status: completed
  - id: wk6-explore-xp
    content: Bias Ranger exploration toward black fog and award XP for revealing new tiles deterministically
    status: completed
  - id: wk6-snapshots-qa
    content: Add/adjust snapshot scenarios + QA checklist; keep qa_smoke and validate_assets green
    status: completed
    dependencies:
      - wk6-audio-system
      - wk6-build-menu
      - wk6-fog-bounties
      - wk6-explore-xp
---

# WK6 —

Audio + Build Menu + Fog Bounties + Ranger Exploration XP

## Scope

- **Audio**: Integrate **CC0/permissive** sound effects + ambient background loop(s), with an attribution-aware asset structure.
- **Build UI**: Clicking **Build** opens a **clickable list** of buildings; clicking an item behaves exactly like pressing its hotkey (enters placement mode, mouse places).
- **Bounties in black fog**: Bounty markers are **visible even in solid-black fog**, and **Rangers will path to the bounty coordinates** even if unrevealed.
- **Ranger exploration + XP**: Baseline AI makes Rangers more likely to explore black fog; Rangers gain **small XP** for revealing new black-fog tiles.

## Key design/tech decisions (locked)

- **Audio asset source**: CC0/permissive packs committed to repo.
- **Black fog bounty policy**: Marker visible in black fog and Rangers can path directly to its target coordinates.

## Implementation plan

### Audio (SFX + ambient)

- **Add a lightweight `AudioSystem`** (no sim coupling):
- Initialize `pygame.mixer` safely; allow disable via config flag.
- Provide `play_sfx(name, volume=...)`, `set_ambient(track, volume=...)`, `stop_ambient()`.
- Trigger SFX from *events* (not from deep sim code) to preserve determinism-friendly separation.
- **Event hooks (minimal)**
- Emit/consume sound-trigger events for:
    - building placed
    - building demolished/destroyed
    - bounty placed
    - ranged attack “twang” / “release” (Ranger + SkeletonArcher)
    - optional UI clicks
- **Assets + attribution**
- Add `assets/audio/sfx/*.wav` and `assets/audio/ambient/*.ogg` (or `.wav`) plus attribution entries.
- Extend tooling to validate audio structure + attribution (same philosophy as sprites).

**Likely files**

- [`game/engine.py`](game/engine.py) (own `AudioSystem`, feed it events)
- [`game/graphics/vfx.py`](game/graphics/vfx.py) (may emit sound triggers alongside VFX events if needed)
- [`tools/assets_manifest.json`](tools/assets_manifest.json) + [`tools/validate_assets.py`](tools/validate_assets.py) (new `audio` section)
- New: `game/audio/audio_system.py` (or similar)

### Build UI: clickable build list

- **UI behavior**
- Clicking **Build** toggles a panel listing available buildings.
- Each row shows: icon/name + cost + hotkey.
- Clicking a row calls the same selection path as hotkey presses (no duplicated logic).
- ESC cancels placement; clicking outside panel closes.
- **Implementation**
- Refactor existing build hotkey selection into a single `select_building(building_type)` method.
- UI panel calls that method.

**Likely files**

- [`game/ui/widgets.py`](game/ui/widgets.py) (list component)
- Existing build UI module(s) (likely `game/ui/...` depending on current implementation)
- [`game/engine.py`](game/engine.py) (unified build selection + placement mode)

### Bounties visible in black fog + Rangers path to them

- **Rendering**
- Ensure bounty markers draw **even when tile visibility is BLACK**, not just gray.
- Keep marker readable on black (outline/plate).
- **Pathing/AI**
- Ensure pathfinding can plan to an unrevealed coordinate:
    - Either treat unknown tiles as traversable for planning, or allow “direct steering” until near.
- Ensure bounty responder selection does not filter out targets in black fog.

**Likely files**

- [`game/world.py`](game/world.py) (visibility model)
- [`game/engine.py`](game/engine.py) or bounty render layer
- [`ai/basic_ai.py`](ai/basic_ai.py) (bounty targeting rules)
- [`game/systems/navigation.py`](game/systems/navigation.py) (pathing behavior with unknown tiles)

### Ranger exploration + XP for black fog reveal

- **Exploration drive**
- When idle/no bounty: Rangers pick frontier targets biased toward black fog boundary.
- Keep deterministic selection: stable ordering + seeded RNG stream.
- **XP award**
- Track revealed tiles per Ranger (set of coords or a compact bloom/bitset-like approach).
- When a tile transitions BLACK→(GRAY/VISIBLE), award small XP (e.g. 1 XP per N tiles).

**Likely files**

- [`ai/basic_ai.py`](ai/basic_ai.py) (Ranger exploration policy)
- [`game/engine.py`](game/engine.py) or world visibility update path (emit “tile_revealed” events)
- [`game/entities/hero.py`](game/entities/hero.py) (XP award + per-hero reveal tracking)

## QA + Visual Snapshot updates

- Add deterministic snapshot scenarios:
- `bounty_in_black_fog` (marker visible on solid-black)
- `building_menu_open` (build list panel)
- `building_debris` already exists; keep
- Gates must remain green:
- `python tools/qa_smoke.py --quick`
- `python tools/validate_assets.py --strict --check-attribution`

## Agent assignments (minimal)

- **Agent 03 (Architecture)**: audio system integration approach + event routing; fog bounty/pathing contract; XP tracking approach.
- **Agent 08 (UX/UI)**: build list panel UX + wiring to the same hotkey selection path.
- **Agent 06 (AI Behavior)**: ranger exploration bias + bounty-in-black targeting behavior.
- **Agent 12 (Tools/DevEx)**: audio asset structure + attribution/validator updates + snapshot scenarios.
- **Agent 11 (QA)**: add verification checklist + any deterministic assertions.
- **New: Agent 14 (SoundDirector)**: choose CC0 packs, define sound map (event→file), loudness guidelines.

## Universal prompt (copy/paste)

- Create `wk6_r1` entries under:
- `sprints["wk6-audio-buildmenu-fogbounties-explorexp"].rounds["wk6_r1"]`