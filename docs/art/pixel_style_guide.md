# Pixel Art Style Guide (Kingdom Sim)

## Scope
This guide defines the visual rules for **sprites + tiles + VFX** so the game stays readable at a distance and consistent across contributors.

## Core constraints (from the current code)
- **Tile size**: `32x32` (`TILE_SIZE = 32` in `config.py`)
- **Hero/Enemy sprite size**: typically **`32x32`** frames
- **Buildings**: sized in tile units (e.g. 2x2 → `64x64`, 3x3 → `96x96`)

## Readability rules (the non-negotiables)
- **Silhouette first**: each unit/building must read in 1–2 seconds at max zoom-out.
- **High value contrast**: units should pop against grass/path/water; avoid mid-value-on-mid-value.
- **Controlled noise**: reserve dithering/texture for large surfaces (buildings), keep units cleaner.
- **Consistent light**: assume a soft **top-left** light with a 3-step ramp (shadow/mid/highlight).

## Linework & outlines
- **1px outline recommended** on characters/enemies (dark, not pure black).
- **Selective outline**: lighten/remove outline on the light-facing edges to avoid “sticker” look.
- **Interior lines**: use sparingly; prefer shape changes over extra line detail.

## Palette & materials
- **Limited ramps**: 3 shades per material (shadow/mid/highlight) is enough.
- **Avoid pure black/white**: use near-black / near-white to keep a softer pixel look.
- **Hue shifting**: shadows slightly cooler; highlights slightly warmer (subtle).

## Faction / class color language
Heroes should be identifiable by a **primary accent** (cloak/trim), not full-body paint.
- **Warrior**: blue accent
- **Ranger**: green accent
- **Rogue**: desaturated steel/grey accent
- **Wizard**: purple accent

Enemies should have **type-first** reads:
- **Goblin**: warm leather/brown + a sharp contrasting detail (eyes/teeth)
- **Wolf**: grey ramp with strong silhouette (snout/tail)
- **Skeleton**: bone ramp (off-white) + dark gaps (rib/eye sockets)

## Ground / world readability
The game currently uses simple procedural tiles; when replacing with real tiles:
- Keep **grass** mid-value and low-contrast.
- Keep **paths** slightly higher contrast than grass but not brighter than units.
- Keep **water** saturated and darker; units should still read when crossing bridges/shore.

## Export rules (pixel integrity)
- Use **PNG (RGBA)**.
- Disable any anti-aliasing; no subpixel blur.
- If you need to scale sprites, do it with **nearest-neighbor**.

## Overlay readability (fog-of-war + UI badges)
Fog-of-war applies a dark overlay across the world. To keep UI markers readable:
- **Use a plate**: a small dark translucent backing behind icons/text (prevents “lost on grass”).
- **Outline everything**: 1px near-black outline around light shapes.
- **Prefer shapes over text**: at small sizes, icons survive zoom better than words.
- **Value > hue**: ensure the icon is high-value even if the accent color changes.


