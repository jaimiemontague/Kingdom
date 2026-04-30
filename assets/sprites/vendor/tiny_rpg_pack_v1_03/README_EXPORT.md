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
python tools/tiny_rpg_export_frames.py --pack assets/sprites/vendor/tiny_rpg_pack_v1_03 --execute --clean-action
python tools/tiny_rpg_export_frames.py --execute --clean-action --verify
```

- **`--dry-run`**: list strips and frame counts only.
- **`--execute`**: write `assets/sprites/heroes/...` and `assets/sprites/enemies/...` as `frame_000.png`, …
- **`--clean-action`**: delete existing `frame_*.png` in each target action folder before writing (recommended on first import; avoids `rmtree` on OneDrive folders).
- **`--verify`**: writes magnified compare strips under `docs/screenshots/tiny_rpg_export_verify/` (100×100 cell → union crop → final PNG) so you can spot-check against vendor art.

### Cropping and size (important)

Characters sit in the **center** of each **100×100** strip cell with lots of empty margin. The exporter:

1. Builds a **union** content box (non-transparent, non-black pixels) across **all frames in that action** so motion stays aligned.
2. Crops every frame with that same rectangle.
3. **Uniform** scales into `--out-w` × `--out-h` with **nearest-neighbor** (Pillow when available), then **letterboxes** on transparent pixels (no squash).

Default **`--out-w` / `--out-h` is 16** (native-ish character size). Runtime scales once via `load_png_frames(..., scale_to=)` using `config.UNIT_SPRITE_PIXELS` (default 48).

- **`--no-content-crop`**: legacy path — scales the full 100×100 cell to the output size (characters look tiny).
- **`--content-pad N`**: inflate the union bbox by `N` pixels before clamping (default 2).

Larger outputs (e.g. `--out-w 32 --out-h 32`) preserve more detail for wide attack swings.

- **`--crop-cap-factor K`** (default **3**): if `max(union w,h) > max(out_w,out_h) * K`, shrink the crop to a **centered** `min(K*max(out),100)` square so downsampling to 16×16 stays readable (may clip extreme slash pixels). Use **`0`** to disable capping.

## Action mapping rules

| Kingdom action | Tiny RPG filenames (typical) |
|----------------|------------------------------|
| `idle` | `*-Idle.png` |
| `walk` | `*-Walk.png` or `*-Walk01.png` + `*-Walk02.png` (merge) |
| `attack` | `*-Attack01.png` + `*-Attack02.png` (+ `*-Attack03.png` or `*-Attack3.png` when present) |
| `hurt` | `*-Hurt.png` |
| `dead` (enemies) | `*-Death.png` |
| `inside` (heroes) | Same as `idle` for most classes; **cleric** uses `Priest-Heal.png` (temple / buff read). |

## After export

```powershell
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report
```

Ensure **`assets/ATTRIBUTION.md`** lists this purchased pack per your license terms.
