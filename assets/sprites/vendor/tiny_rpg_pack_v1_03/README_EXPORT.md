# Tiny RPG pack → Kingdom Sim sprite export

## Files

| File | Purpose |
|------|---------|
| `Map.csv` | Which **Tiny RPG character folder** backs each **Kingdom** hero/enemy unit. |
| `Map_actions.csv` | Each **source PNG** (horizontal 100×100 strip) merged into a **kingdom_action** (`merge_index` order). |

Source art lives under `Characters(100x100)/<Character>/<Character>/` using the **non-shadow** sheets (no baked ground shadow).

**Spider and wolf** are intentionally **not** mapped here — they stay on the game’s **procedural** (or any prior) sprites. Do not add `spider` / `wolf` rows to `Map_actions.csv` unless you decide to replace them later.

## Export command (repo root)

```powershell
python tools/tiny_rpg_export_frames.py --pack assets/sprites/vendor/tiny_rpg_pack_v1_03 --dry-run
python tools/tiny_rpg_export_frames.py --pack assets/sprites/vendor/tiny_rpg_pack_v1_03 --execute --clean-action --verify
python tools/tiny_rpg_export_frames.py --execute --clean-action --verify --only-unit heroes/warrior
```

- **`--dry-run`**: list strips and frame counts only.
- **`--execute`**: write `assets/sprites/heroes/...` and `assets/sprites/enemies/...` as `frame_000.png`, …
- **`--clean-action`**: delete existing `frame_*.png` in each target action folder before writing (recommended on first import; avoids `rmtree` on OneDrive folders).
- **`--verify`**: writes magnified compare strips under `docs/screenshots/tiny_rpg_export_verify/` (100×100 cell → union crop → final 48×48 PNG) so you can spot-check against vendor art.
- **`--only-unit CATEGORY/UNIT`**: optional repeatable pilot filter, e.g. `--only-unit heroes/warrior --only-unit heroes/ranger`.

### Cropping and size (important)

Characters sit in the **center** of each **100×100** strip cell with lots of empty margin. The exporter:

1. Builds a **union** content box (non-transparent pixels, including black outline/detail pixels) across **all frames in that action** so motion stays aligned.
2. Crops every frame with that same rectangle.
3. Pastes that crop **without scaling** into a transparent `--out-w` × `--out-h` canvas, anchored so the original 100×100 source cell center maps to the output center.

Default **`--out-w` / `--out-h` is 48**, matching `config.UNIT_SPRITE_PIXELS`. Runtime loading via `load_png_frames(..., scale_to=(48, 48))` is therefore a no-op for these exports, preserving the Tiny RPG source pixels inside a 48×48 transparent game slot.

- **`--no-content-crop`**: legacy path — scales the full 100×100 cell to the output size (characters look tiny).
- **`--content-pad N`**: inflate the union bbox by `N` pixels before clamping (default 2).
- **`--scale-crop-to-fit`**: legacy path — scales the union crop into the output canvas. Avoid this for final game art because it changes the pack's native pixel quality.

Native 48×48 exports are intentionally larger than the visible character. Most units remain roughly 20–30 source pixels tall/wide with transparent padding around them. Wide attack arcs may clip at the 48×48 slot edge, but the body itself should not shrink between idle/walk/attack.

- **`--crop-cap-factor K`** (default **0**): if `max(union w,h) > max(out_w,out_h) * K`, shrink the crop to a **centered** `min(K*max(out),100)` square. Use this only for special-case clipping; the normal native-canvas export leaves capping disabled.

## Action mapping rules

| Kingdom action | Tiny RPG filenames (typical) |
|----------------|------------------------------|
| `idle` | `*-Idle.png` |
| `walk` | `*-Walk.png` or `*-Walk01.png` + `*-Walk02.png` (merge) |
| `attack` | `*-Attack01.png` + `*-Attack02.png` (+ `*-Attack03.png` or `*-Attack3.png` when present) |
| `hurt` | `*-Hurt.png` |
| `dead` (enemies) | `*-Death.png` |
| `inside` (heroes) | Same as `idle` for most classes; **cleric** uses `Priest-Heal.png` (temple / buff read). |

Rogue note: `rogue` intentionally uses the `Archer` source strips (same silhouette family as `ranger`) with a deterministic steel/purple recolor pass during export.

## After export

```powershell
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report
```

Ensure **`assets/ATTRIBUTION.md`** lists this purchased pack per your license terms.
