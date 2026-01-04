# wk1_r1 — Agent 9 (ArtDirector_Pixel_Animation_VFX)

## Prompt
“Suggest ultra-light icons/shapes for bounty type + attractiveness tiers that remain readable over fog-of-war.”

## Status
Ready to integrate: **a minimal, pixel-crisp icon language** for bounty markers + attractiveness tiers that stays readable on grass/path/water and under fog-of-war (dark overlays).

## Deliverables (P0, low-risk)
### 1) Procedural icon pack (no external art required)
I implemented a procedural icon module so UI can ship now without waiting for PNGs:
- `game/graphics/ui_icons.py`

It provides:
- `get_bounty_type_icon(bounty_type, size=16)`
  - `explore`: diamond/compass
  - `attack_lair`: crossed swords (simplified)
  - `defend_building`: shield
  - `hunt_enemy_type`: target reticle
- `get_attractiveness_icon(tier, size=16)`
  - `low`: 1 chevron
  - `med`: 2 chevrons
  - `high`: 3 chevrons
- `get_bounty_badge(bounty_type, attractiveness_tier, size=20)`
  - Composite: **backing plate + 1px outline + type icon + tier chevrons**
  - Intended for world overlays (bounty marker UI) and tooltips

Design intent:
- **Shape-first** (survives zoom, colorblindness, and fog)
- **High-value ink** with **near-black outline**
- Small **dark translucent plate** behind the icon for contrast
- Cached surfaces to avoid per-frame allocations

### 2) Overlay readability rules for fog-of-war
Fog-of-war currently applies a dark overlay (unseen: opaque black; seen: semi-transparent black). To ensure icons remain legible, I added the following rules to the style guide:
- Plate behind icons/text
- 1px outline on light shapes
- Prefer shapes over text
- Prioritize value contrast over hue

Doc updated:
- `docs/art/pixel_style_guide.md` (new “Overlay readability” section)

### 3) Reserved folder for future hand-drawn UI icons (optional)
If/when we replace procedural icons with real pixel art, this is the intended home:
- `assets/sprites/ui/README.md` (+ `.gitkeep`)

This is purely future-proofing and does not block Build A.

## Recommended icon language (what UI should display)
### Bounty type
Display **one symbol** near the bounty marker:
- Explore: diamond/compass
- Attack lair: crossed swords
- Defend building: shield
- Hunt enemy: reticle

### Attractiveness tier
Display **one tier badge**:
- Low / Med / High as 1 / 2 / 3 chevrons

### Composite badge (preferred)
Use `get_bounty_badge()` to show both at once in a compact 20px square with a backing plate.

## Acceptance criteria (for Build A UI integration)
- A bounty marker can display:
  - type icon and tier icon (or composite badge)
  - remains readable over grass/path/water and on fogged tiles (SEEN/UNSEEN)
- No new external assets required to ship Build A
- No heavy allocations per frame (icons cached)

## Risks
- If UI draws icons directly on terrain without a backing plate, they’ll get lost on busy tiles and under fog; **always use a plate** (provided in composite badge).
- If icons are scaled with smoothing, they’ll blur; scaling should be **nearest-neighbor** (engine already updated to non-smooth scaling for sprite frames).

## Dependencies
- UI workstream (Agent 8) to decide:
  - always-visible vs hover/selection visibility for bounty badges
  - exact placement relative to bounty marker and text ($reward, responders)

## Questions back to PM (pick defaults if no time)
1) Tier color language: keep **blue/gold/orange** (cool→warm), or switch to **green/yellow/red**?
2) Visibility policy: badges **always visible** vs **only on hover/selection** (reduces clutter)?
3) Should type icons emphasize **action** (sword/shield/compass) or **target** (lair/building/enemy) if we later add more bounty types?

## Recommended next actions
- Agent 8: integrate `get_bounty_badge()` into bounty overlay rendering (world-space UI) and/or bounty tooltip panel.
- Agent 3/5/6: once attractiveness tiers are defined (low/med/high), feed tier strings to the badge.
- After Build A: replace procedural shapes with real PNG icons only if desired; the contract can stay the same.







