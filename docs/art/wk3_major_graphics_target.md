# WK3 Major Graphics Target (Addendum)

This is the **locked style target** for the Major Graphics Update driven by the Visual Snapshot System. It refines the existing contracts in:
- `docs/art/pixel_style_guide.md`
- `docs/art/animation_vfx_guidelines.md`
- `docs/art/placeholder_sprite_briefs.md`

## 1) Lighting + shadows (locked)
- **Light direction**: soft **top-left**.
- **Sprite shadow**: a small, subtle ground shadow under units/buildings.
  - Units: soft ellipse, low opacity.
  - Buildings: slightly firmer shadow footprint (still subtle).
- **Shadow color**: use a cool near-black (not pure black).

## 2) Outlines (locked)
- **1px outline** on units and buildings for readability.
- **Selective outline**: lighten/remove outline on the light-facing edges (top/left) to avoid “sticker” look.
- **Interior lines**: only where they clarify silhouette/material (doors, windows, roof ridges).

## 3) Palette ramps (locked)
- **3-step ramps** for most materials (shadow/mid/highlight).
- **Hue shift**:
  - Shadows slightly cooler.
  - Highlights slightly warmer.
- **Avoid pure black/white**: reserve for tiny sparkles/eyes/specular pixels.

## 4) Scale + camera readability (locked)
- **Tile**: 32×32.
- **Units**: 32×32 frames, aligned to the pixel grid (no subpixel drift).
- **Buildings**: tile multiples (1×1, 2×2, 3×3) and must “fill” their footprint without fuzzy scaling.
- **Gameplay zoom target**: the default zoom should read cleanly (silhouettes + path edges visible).
  - Visual Snapshot System zoom presets:
    - **Z1**: overview (composition/landmarks)
    - **Z2**: gameplay default (moment-to-moment readability)
    - **Z3**: close-up (silhouette/material inspection)

## 5) Noise budget (locked)
- **Terrain**: low noise (avoid heavy speckle); variation comes from large shapes and occasional small props.
- **Paths**: medium contrast with clear edges; readable intersections.
- **Buildings**: medium texture; use readable roof/wall separation, not dithering soup.
- **Units**: low texture; silhouette + a few high-signal pixels (weapon, eyes, trim).
- **UI**: clean; strong panel framing; icon-first where possible.

## 6) “Golden palette” swatches (hex)
These are **targets**, not strict limits; we can tweak after snapshot review.

- **Outline (near-black)**: `#141419`
- **Shadow (cool dark)**: `#0B0D10`
- **Highlight (near-white)**: `#F5F5F5`

- **Grass mid**: `#228B22`
- **Grass dark**: `#1A781A`
- **Grass light**: `#3CA53C`

- **Path mid**: `#8B7765`
- **Path dark**: `#6E5B4C`
- **Path light**: `#A98F7A`

- **Tree leaf mid**: `#006400`
- **Tree leaf dark**: `#004600`
- **Tree trunk**: `#785532`

- **UI panel background**: `#282832`
- **UI border**: `#505064`

## 7) Snapshot DoD (how we prove progress)
We consider a milestone “done” when the **baseline v2 next** snapshots improve in the expected places:
- Terrain pass improves `base_overview__Z1__world_clean.png` and `base_overview__Z2__world_clean.png`
- Tier-1 buildings improve the Tier-1 closeups in `building_catalog_seed3/`
- Core enemies improve the closeups in `enemy_catalog_seed3/`

All visual changes must keep:
- `python tools/qa_smoke.py --quick` **PASS**
- `python tools/build_gallery.py --shots <run> --refs .cursor/plans/art_examples --out docs/art/compare_gallery.html` working






