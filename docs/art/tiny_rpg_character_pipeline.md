# Tiny RPG pack → Kingdom Sim: character sprite pipeline

This document describes how horizontal-strip characters from **Tiny RPG Character Pack** (`assets/sprites/vendor/tiny_rpg_pack_v1_03/`) become animated `frame_###.png` sets under `assets/sprites/`, how the game loads them, and how **pygame**, **Ursina billboards**, and **Ursina instancing** consume clips. Use it when onboarding a new Tiny RPG character (hero, enemy, or worker).

---

## 1. Vendor layout

- **Character PNGs** live under  
  `assets/sprites/vendor/tiny_rpg_pack_v1_03/Characters(100x100)/<CharacterName>/<CharacterName>/*.png`
- Each file is typically a **horizontal strip** of cells (**100×100** per frame by default). The exporter splits with `_split_horizontal_strip()` in [`tools/tiny_rpg_export_frames.py`](../../tools/tiny_rpg_export_frames.py).

Character folder names may contain spaces (e.g. `Skeleton Archer`); the resolver `_resolve_inner_character_dir` walks into `<Character>/<Character>`.

---

## 2. CSV roles

| File | Purpose |
|------|---------|
| [`Map.csv`](../../assets/sprites/vendor/tiny_rpg_pack_v1_03/Map.csv) | Short human-readable map: which Tiny RPG character backs each Kingdom **unit** (e.g. warrior ↔ Knight, guard ↔ Soldier). |
| [`Map_actions.csv`](../../assets/sprites/vendor/tiny_rpg_pack_v1_03/Map_actions.csv) | **Machine export spec**: columns `kingdom_category`, `kingdom_unit`, `tiny_rpg_character`, `kingdom_action`, `source_filename`, `merge_index`. |

**`kingdom_category`** must be one of: `heroes`, `enemies`, `workers`.

**`merge_index`**: When one logical action (usually **attack**) spans multiple strip files, add **one CSV row per strip**, with `merge_index` `0, 1, 2, …`. The exporter sorts by `merge_index`, loads each strip’s frames in order, and **concatenates** them into a single animation clip on disk (many `frame_NNN.png` in one folder).

Example (warrior attack = Knight):

```text
heroes,warrior,Knight,attack,Knight-Attack01.png,0
heroes,warrior,Knight,attack,Knight-Attack02.png,1
heroes,warrior,Knight,attack,Knight-Attack03.png,2
```

Guard (Soldier) mirrors this pattern in `Map_actions.csv` under `workers,guard,Soldier,...`.

---

## 3. Export tool behavior

Script: [`tools/tiny_rpg_export_frames.py`](../../tools/tiny_rpg_export_frames.py).

Per `(kingdom_category, kingdom_unit, tiny_rpg_character, kingdom_action)` group:

1. Load each `source_filename` PNG; split into raw **100×100** cells.
2. Append all cells into `all_frames` in `merge_index` order.
3. Compute a **union bounding box** of visible (alpha) pixels across **all frames** in that action so every frame uses the **same crop rect** (aligned motion).
4. Crop each frame; optionally cap oversized crops (`--crop-cap-factor`) so wide swings are not crushed when pasted into the output canvas.
5. Paste each cropped frame into a **`out_w × out_h`** canvas (default **48×48**), centered (letterbox), **nearest-neighbor** only.
6. Write `frame_000.png`, `frame_001.png`, … under:
   - `assets/sprites/heroes/<class>/<action>/`
   - `assets/sprites/enemies/<type>/<action>/`
   - `assets/sprites/workers/<worker_type>/<action>/`

### CLI cookbook (PowerShell, repo root)

Dry-run one unit:

```powershell
python tools/tiny_rpg_export_frames.py --pack assets/sprites/vendor/tiny_rpg_pack_v1_03 --dry-run --only-unit heroes/warrior
```

Write files + QA compare strips:

```powershell
python tools/tiny_rpg_export_frames.py --pack assets/sprites/vendor/tiny_rpg_pack_v1_03 --execute --clean-action --verify --only-unit workers/guard
```

Useful flags (see script `--help`): `--out-w` / `--out-h`, `--content-pad`, `--crop-cap-factor`, `--no-content-crop`, `--scale-crop-to-fit` (legacy).

---

## 4. Runtime sprite libraries

| Unit kind | Library | Asset root |
|-----------|---------|------------|
| Heroes | [`game/graphics/hero_sprites.py`](../../game/graphics/hero_sprites.py) | `assets/sprites/heroes/<class>/<action>/` |
| Enemies | [`game/graphics/enemy_sprites.py`](../../game/graphics/enemy_sprites.py) | `assets/sprites/enemies/<type>/<action>/` |
| Workers | [`game/graphics/worker_sprites.py`](../../game/graphics/worker_sprites.py) | `assets/sprites/workers/<type>/<action>/` |

Each library exposes `clips_for(...) → dict[str, AnimationClip]` built from [`AnimationClip`](../../game/graphics/animation.py) (`frames`, `frame_time_sec`, `loop`). PNGs are loaded via `load_png_frames(..., scale_to=UNIT_SPRITE_PIXELS)`; if missing, **procedural** placeholders fill in.

**Guard actions** (workers/guard): `idle`, `walk`, `attack` (loops while `GuardState.ATTACKING`), `hurt`, `dead`. State→clip mapping for pygame lives in [`game/graphics/renderers/worker_renderer.py`](../../game/graphics/renderers/worker_renderer.py); Ursina base locomotion uses `_guard_base_clip()` in [`game/graphics/ursina_units_anim.py`](../../game/graphics/ursina_units_anim.py).

---

## 5. Renderer contracts

### Pygame

[`game/graphics/renderers/registry.py`](../../game/graphics/renderers/registry.py) uses `WorkerRenderer` / `GuardRenderer`: [`AnimationPlayer`](../../game/graphics/animation.py) advances with **sim/render dt** and blits `frame()` each frame.

### Ursina — billboard Entities

[`game/graphics/ursina_renderer.py`](../../game/graphics/ursina_renderer.py): heroes and enemies use `_unit_anim_surface(...)`, which stores per-entity wall-clock state in `_unit_anim_state`, resolves optional one-shot clips via `_render_anim_trigger` / `_ursina_anim_trigger`, and picks the current `AnimationClip` frame. **Guards use the same path** as heroes (not `_worker_idle_surface`, which only exposes idle frame 0).

Tint: textured Tiny RPG sprites should use **`color.white`** tint so pixels read faithfully (same idea as textured warriors).

### Ursina — hardware instancing

[`game/graphics/instanced_unit_renderer.py`](../../game/graphics/instanced_unit_renderer.py): packs all frames into [`UnitAtlasBuilder`](../../game/graphics/unit_atlas.py) (`2048×2048` atlas). Each unit instance sends **UV coordinates** for one frame. Guards must call `_resolve_unit_anim_clip_frame(...)` with `WorkerSpriteLibrary.clips_for("guard")` and `_guard_base_clip`, same pattern as heroes/enemies—otherwise guards appear frozen on atlas frame `idle/0` even though walk/attack UVs exist.

### One-shot combat clips

Setting `entity._render_anim_trigger = "hurt"` plays the `hurt` clip once on Ursina paths until the clip finishes, then returns to the base locomotion clip. [`game/entities/guard.py`](../../game/entities/guard.py) sets this on non-lethal damage in `take_damage`.

---

## 6. Adding a new Tiny RPG character (checklist)

1. Add vendor PNGs under `Characters(100x100)/...` if not already present.
2. Add a summary row to `Map.csv` (documentation).
3. Add **one row per strip per action** to `Map_actions.csv`; use multiple rows + `merge_index` for multi-strip attacks.
4. Run exporter with `--dry-run`, then `--execute --clean-action --verify`.
5. Confirm folders exist:  
   `assets/sprites/<heroes|enemies|workers>/<unit>/<action>/frame_*.png`
6. If the unit is a **new worker type**, extend `WorkerSpriteLibrary` actions / paths (or use an existing type).
7. Ensure **Ursina** uses `_unit_anim_surface` + a `_foo_base_clip` (not `_worker_idle_surface`) if that unit should animate.
8. Ensure **instancing** resolves `(clip, frame_idx)` for that unit if `InstancedUnitRenderer` draws it.
9. Run `python tools/qa_smoke.py --quick` and `python tools/validate_assets.py --report`.

---

## 7. Common pitfalls

| Symptom | Likely cause |
|---------|----------------|
| Character looks tiny in 48×48 | Exported with `--no-content-crop` or wrong `--out-w/h`. Prefer default content crop + letterbox. |
| Attack animation missing middle swings | Missing `merge_index` rows in `Map_actions.csv` for extra strip files. |
| PNGs on disk but sprite **frozen** in Ursina | Billboard path still using **`_worker_idle_surface`** (idle frame 0 only). Switch to **`_unit_anim_surface`** + base clip function. |
| Frozen in instancing only | Atlas packs frames, but draw path hardcodes `lookup_uv(..., "idle", 0)`. Use `_resolve_unit_anim_clip_frame`. |
| Wrong colors on billboard | Strong tint (`COLOR_*`) multiplied over textured sprite; use **`color.white`** for authored pixels. |
| Stale atlas after adding PNGs | `UnitAtlasBuilder` is a singleton built once per process; restart the game. `WorkerSpriteLibrary._cache` is also per-process—restart after replacing assets during dev. |

---

## 8. Reference: Soldier guard worked example

- **Map**: `workers,guard,Soldier` in [`Map.csv`](../../assets/sprites/vendor/tiny_rpg_pack_v1_03/Map.csv).
- **Actions**: `idle`, `walk`, merged `attack` (three Soldier attack strips), `hurt`, `dead` in [`Map_actions.csv`](../../assets/sprites/vendor/tiny_rpg_pack_v1_03/Map_actions.csv).
- **Output**: `assets/sprites/workers/guard/<action>/frame_*.png`.
- **Ursina**: `_sync_snapshot_guards` uses `WorkerSpriteLibrary.clips_for("guard")` + `_unit_anim_surface(..., _guard_base_clip, ...)`.
- **Instancing**: guard loop uses `_resolve_unit_anim_clip_frame` + `lookup_uv("worker", "guard", clip_name, frame_idx)`.

---

## 9. Licensing

Tiny RPG pack usage and attribution must remain consistent with [`assets/ATTRIBUTION.md`](../../assets/ATTRIBUTION.md). Exported PNGs are derived from the vendor pack; do not substitute unrelated art without updating attribution.
