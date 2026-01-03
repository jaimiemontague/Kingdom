# Hero Sprite Pipeline (WK2 — Build B)

## Goal
Ship real hero animations for **Warrior/Ranger/Rogue/Wizard** that load automatically via the current engine folder conventions and remain **pixel-crisp** at 32x32.

## Folder conventions (engine-loaded)
Put frames here:

`assets/sprites/heroes/<hero_class>/<action>/frame_###.png`

Where:
- `<hero_class>`: `warrior`, `ranger`, `rogue`, `wizard`
- `<action>`: `idle`, `walk`, `attack`, `hurt`, `inside`

## Naming
Frames load in **filename-sorted order**. Use:
- `frame_000.png`
- `frame_001.png`
- ...

## Frame-count guidance (recommended)
- `idle`: 6
- `walk`: 8
- `attack`: 6
- `hurt`: 4
- `inside`: 6

## Export rules (do not break pixel integrity)
- PNG (RGBA)
- No anti-aliasing, no motion blur
- Nearest-neighbor scaling only (no filtering)
- Keep sprites aligned to the pixel grid

## Alignment rule (prevents jitter)
Keep the character’s **ground contact (“feet”) on the same Y row** across frames for each action.

## Quick validation (deterministic, no UI)
This command exits non-zero if any required class/action folder has no PNG frames:

```bash
python -c "import itertools; from game.graphics.hero_sprites import HeroSpriteLibrary as H; classes=['warrior','ranger','rogue','wizard']; actions=['idle','walk','attack','hurt','inside']; missing=[(c,a) for c,a in itertools.product(classes,actions) if not H._try_load_asset_frames(c,a,32)]; print('missing', missing); raise SystemExit(1 if missing else 0)"
```





