# Sprites

## Folder structure (engine-loaded)
### Heroes
`assets/sprites/heroes/<hero_class>/<action>/*.png`

### Enemies
`assets/sprites/enemies/<enemy_type>/<action>/*.png`

### Buildings
`assets/sprites/buildings/<building_type>/<state>/*.png`

## Naming
Frames load in **filename-sorted order**. Recommended:
- `frame_000.png`
- `frame_001.png`
- ...

## Pixel rules
- Keep sprites on the **pixel grid**
- Avoid anti-aliasing and blur
- Prefer a **1px outline** for unit readability (see `docs/art/pixel_style_guide.md`)



