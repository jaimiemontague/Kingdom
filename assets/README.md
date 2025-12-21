# Assets Overview

This folder holds all game content files (sprites, maps, etc.).

## Sprite conventions (important)
The code will automatically load PNG frames if you follow these folder structures.

### Heroes
`assets/sprites/heroes/<hero_class>/<action>/*.png`

Actions:
- `idle`, `walk`, `attack`, `hurt`, `inside`

### Enemies
`assets/sprites/enemies/<enemy_type>/<action>/*.png`

Actions:
- `idle`, `walk`, `attack`, `hurt`, `dead`

### Buildings
`assets/sprites/buildings/<building_type>/<state>/*.png`

States:
- `built`, `construction`, `damaged`

## Export rules (pixel integrity)
- **PNG (RGBA)** only
- **Nearest-neighbor** scaling only (no smoothing/filters)
- Keep animation frames consistent in size and alignment
- Frames are loaded in **filename-sorted order** (e.g. `frame_000.png`, `frame_001.png`, ...)



