# Sprites

## Folder structure (engine-loaded)
### Heroes
`assets/sprites/heroes/<hero_class>/<action>/*.png`

### Enemies
`assets/sprites/enemies/<enemy_type>/<action>/*.png`

### Buildings
`assets/sprites/buildings/<building_type>/<state>/*.png`

### Workers
`assets/sprites/workers/<worker_type>/<action>/*.png`

### Vendor / source packs (not engine paths)
Purchased or reference art may live under `assets/sprites/vendor/<short_name>/` (e.g. `vendor/tiny_rpg_pack_v1_03`). Copy or re-export frames into the **heroes / enemies / workers** trees above for the game to load them. For the Tiny RPG pack, see `vendor/tiny_rpg_pack_v1_03/README_EXPORT.md` and run `tools/tiny_rpg_export_frames.py`.

## Naming
Frames load in **filename-sorted order**. Recommended:
- `frame_000.png`
- `frame_001.png`
- ...

## Pixel rules
- Keep sprites on the **pixel grid**
- Avoid anti-aliasing and blur
- Prefer a **1px outline** for unit readability (see `docs/art/pixel_style_guide.md`)







