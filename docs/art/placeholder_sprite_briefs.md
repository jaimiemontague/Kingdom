# Placeholder Sprite Briefs (Ready-to-draw)

## Global spec
- **Format**: PNG (RGBA)
- **Grid**: 32px tile grid
- **Sprite frame size**: `32x32` for units; buildings use tile multiples
- **Camera**: top-down-ish; prioritize silhouette and contrast over detail

## Heroes (32x32)
Folder:
`assets/sprites/heroes/<hero_class>/<action>/`

Actions: `idle`, `walk`, `attack`, `hurt`, `inside`

### Warrior
- **Silhouette**: broad shoulders, visible sword/shield read
- **Accent**: blue cloth/trim; metal highlights for weapon
- **Idle**: subtle breathing + slight sword bob
- **Attack**: clear wind-up + slash pose

### Ranger
- **Silhouette**: hood + bow profile (bow must read)
- **Accent**: green cloak; small quiver highlight
- **Walk**: cloak flutter; bow held diagonally for silhouette
- **Attack**: draw → release (strong 1-frame “release” pose)

### Rogue
- **Silhouette**: slimmer body, dagger(s), crouchier stance
- **Accent**: steel/grey; optional small red/teal gem for contrast
- **Walk**: quick, low bob
- **Attack**: lunge + short arc

### Wizard
- **Silhouette**: tall hat/hood + staff
- **Accent**: purple robe; staff tip glow pixel highlight
- **Attack**: staff forward + 1-frame bright “cast” pose
- **Idle**: subtle robe sway + staff tilt

## Enemies (32x32)
Folder:
`assets/sprites/enemies/<enemy_type>/<action>/`

Actions: `idle`, `walk`, `attack`, `hurt`, `dead`

### Goblin
- **Silhouette**: big head + short legs (instantly “goblin”)
- **Palette**: warm leather/brown; bright eyes/teeth as contrast
- **Attack**: quick stab/swing with a big forward lean

### Wolf
- **Silhouette**: strong snout + tail; body as ellipse
- **Palette**: grey ramp; darker underside for grounding
- **Attack**: pounce frame (biggest silhouette)

### Skeleton
- **Silhouette**: boxier torso; long thin limbs
- **Palette**: off-white bone + dark cavities (ribs/eyes)
- **Dead**: collapsed pile or sideways torso for strong read

## Buildings (tile multiples)
Folder:
`assets/sprites/buildings/<building_type>/<state>/`

States: `built`, `construction`, `damaged`

### Sizes (from `config.py`)
- `castle`: 3x3 → 96x96
- `warrior_guild`: 2x2 → 64x64
- `ranger_guild`: 2x2 → 64x64
- `rogue_guild`: 2x2 → 64x64
- `wizard_guild`: 2x2 → 64x64
- `marketplace`: 2x2 → 64x64
- `ballista_tower`: 1x1 → 32x32
- `temples_*`: 3x3 → 96x96
- `house`: 1x1 → 32x32
- `farm`: 2x2 → 64x64
- `food_stand`: 1x1 → 32x32

### State variants
- **construction**: scaffolding + darker overlay; keep the building silhouette recognizable
- **damaged**: cracks + smoke; avoid turning it into visual noise







