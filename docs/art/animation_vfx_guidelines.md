# Animation + VFX Guidelines (Kingdom Sim)

## What the engine expects today (folder + actions)
### Heroes
If present, hero frames are loaded from:

`assets/sprites/heroes/<hero_class>/<action>/*.png`

Actions currently used by the engine:
- `idle` (loop)
- `walk` (loop)
- `attack` (non-loop)
- `hurt` (non-loop)
- `inside` (loop; “inside building” bubble)

### Enemies
If present, enemy frames are loaded from:

`assets/sprites/enemies/<enemy_type>/<action>/*.png`

Actions currently used by the engine:
- `idle` (loop)
- `walk` (loop)
- `attack` (non-loop)
- `hurt` (non-loop)
- `dead` (non-loop)

### Buildings
If present, building frames are loaded from:

`assets/sprites/buildings/<building_type>/<state>/*.png`

States currently used by the engine:
- `built`
- `construction`
- `damaged`

## Pixel animation principles (top-down sim readability)
- **Exaggerate motion**: small sprites need bigger readability beats (arm swing, cloak flutter).
- **Hold the key pose**: keep the “contact” or “hit” frame on-screen long enough to read.
- **Prioritize clarity over smoothness**: fewer frames with stronger poses > many mushy frames.
- **Avoid subpixel drift**: move in whole pixels whenever possible to prevent shimmer.

## Recommended frame counts (match current engine timings)
These align with current default frame times so your animations “feel right” immediately:

- **Hero idle**: 6 frames (subtle bob/breath)
- **Hero walk**: 8 frames (clear step cycle, small bob)
- **Hero attack**: 6 frames (anticipation → strike → recover)
- **Hero hurt**: 4 frames (quick flinch)
- **Hero inside**: 6 frames (bubble/icon loop)

- **Enemy idle**: 6 frames
- **Enemy walk**: 8 frames
- **Enemy attack**: 6 frames
- **Enemy hurt**: 4 frames
- **Enemy dead**: 1–6 frames (either a single “down” frame or a short collapse)

## Attack timing (micro-spec)
- **Anticipation**: 1–2 frames (weapon back / body lean)
- **Strike**: 1 frame (biggest silhouette + brightest highlight)
- **Recover**: 2–3 frames (return to neutral)

## Hurt / death readability
- **Hurt**: use a strong silhouette change + a highlight flash (not motion blur).
- **Dead**: pick a stable final pose that remains readable under other units/VFX.

## VFX direction (current system)
The current VFX is “pixel-square particles” intended for combat readability:
- **Hit**: short-lived warm spark burst
- **Kill**: slightly larger grey burst
- **Lair cleared**: larger celebratory burst (gold/orange)

Guidelines:
- **Color language**:
  - warm yellow/orange = impact / success
  - cool/grey = death / neutral debris
  - avoid red bursts unless it clearly indicates “damage taken”
- **Size discipline**: keep particles **2–3 px** to match the pixel grid.
- **Density discipline**: prefer short bursts over sustained noise.

## Export + alignment checklist (sprites)
These rules prevent jitter and keep sprites crisp:
- **Canvas**: 32x32 per frame for heroes/enemies (buildings are tile multiples)
- **Format**: PNG (RGBA)
- **Scaling**: nearest-neighbor only (no smoothing / filtered scaling)
- **Pixel grid**: keep key features on whole pixels; avoid subpixel drift
- **Consistent anchor**: keep “feet/contact” aligned across frames (don’t vertically shift sprites unless the motion is intentional and readable)
- **Filename sorting**: use `frame_000.png`, `frame_001.png`, ... (engine loads filename-sorted)

## WK2 hero sprite set (Build B) — required folders
The engine will load frames if present under:
`assets/sprites/heroes/<hero_class>/<action>/*.png`

Required for WK2:
- Classes: `warrior`, `ranger`, `rogue`, `wizard`
- Actions: `idle`, `walk`, `attack`, `hurt`, `inside`


