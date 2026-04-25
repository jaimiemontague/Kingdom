# Building prefab JSON — schema v0.2

Authoritative for **`assets/prefabs/buildings/*.json`**. The Kenney assembler (`tools/model_assembler_kenney.py`) reads and writes this shape; runtime loaders must accept the same fields.

For the full art/tooling procedure behind `texture_override`, see `.cursor/plans/prefab_texture_override_standard.md`.

## File layout

- One file per prefab: **`assets/prefabs/buildings/<prefab_id>.json`**
- **`prefab_id`** must match the filename stem (e.g. `peasant_house_small_v1.json` → `prefab_id`: `peasant_house_small_v1`).
- Source **`.glb` / `.gltf` assets are never copied** into `assets/prefabs/`. The `model` field holds a path **relative to `assets/models/`**.

## Root object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prefab_id` | string | yes | Stable id; use suffix `_vN` and bump when changing a shipped prefab. |
| `building_type` | string | yes | Sim building type key (e.g. `house`) — must align with `config.py` when used in-game. **Exception (WK32):** empty-plot prefabs `plot_*x*_v1.json` use `plot_1x1` / `plot_2x2` / `plot_3x3` so they are not mistaken for playable buildings; the renderer loads them by filename for the construction ladder. |
| `footprint_tiles` | `[int, int]` | yes | Width × depth in **tiles** `[w, d]`. Must match the sim footprint for that `building_type` when wired to gameplay. |
| `ground_anchor_y` | number | yes | World **Y** of the building anchor / ground plane for placement (typically `0.0`). |
| `rotation_steps` | number | yes | Degrees per toolbar “rotate step” in the tool (plan default: `90`). Stored for round-trip and future tooling. |
| `attribution` | string[] | yes | Kenney pack ids (e.g. `kenney_retro-fantasy-kit`) — one entry per pack referenced by any `pieces[].model`. Used for credits. |
| `pieces` | array | yes | Ordered list of kit pieces; see below. |
| `notes` | string | no | Human-readable design notes (not read by sim). |

### Anchor / origin convention (v0.2)

**Authoring (assembler):** Piece `pos` values are whatever the tool wrote — often a **per-prefab ad-hoc origin** (e.g. pieces clustered in one corner of the footprint grid). Authors do **not** need to manually center the cluster in XZ for correct in-game placement.

**Runtime (`game/graphics/ursina_renderer.py`):**

1. **`_load_prefab_instance`** reads all `pieces[].pos`, builds the **XZ axis-aligned bounding box** of those positions, and computes its **centroid** `(centroid_x, centroid_z)`.
2. Each child piece is placed with **XZ offset** `pos.x - centroid_x`, `pos.z - centroid_z` so the **mesh cluster is centered on the prefab root in local XZ**. **Y is unchanged** — vertical stacking and ground height are author intent.
3. The prefab **root entity** is placed at the sim building’s **footprint-center** world position (see `_sync_prefab_building_entity`). The cluster is **fit-scaled** to match `footprint_tiles` vs the sim grid.

**Contract:** After load, the visible geometry is centered on the building’s footprint in XZ regardless of how the JSON was authored in the assembler. Prefab JSON files are still valid if piece positions look “off-center” in raw coordinates.

## `pieces[]` item

Each element is one placed kit piece:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | yes | Path relative to **`assets/models/`** (POSIX slashes). Example: `Models/GLB format/wall-paint-door.glb`. |
| `pos` | `[x, y, z]` | yes | Translation in **assembler space** (as saved by the tool). At runtime, the Ursina loader applies **XZ auto-centering** (subtracts the piece-cluster XZ centroid); **Y is not re-centered**. |
| `rot` | `[rx, ry, rz]` | yes | Rotation in **degrees** (Euler order as produced by the assembler; typically Y-up). |
| `scale` | `[sx, sy, sz]` | yes | Uniform or per-axis scale (default `[1, 1, 1]`). |
| `texture_override` | string | no | Optional path relative to **`assets/`** for a curated PNG texture override. Example: `textures/buildings/inn/inn_roof_shingles.png`. Overrides are applied only to this prefab piece and do not mutate source Kenney GLBs. |
| `texture_override_mode` | string | no | Optional mapping mode for `texture_override`. Default/object-space mode ignores source UVs and is best for Kenney atlas pieces. Use `"uv"` only for generated decal meshes with authored UVs, such as explicit window panels. |

## Rules

1. **`model` paths** resolve under `assets/models/` only — no absolute paths.
2. **Transforms** are **per-piece** in assembler space; the runtime derives centered local transforms for children as described above.
3. **`footprint_tiles`** is a contract with the 2D sim; if the assembled mesh does not fit after fit-scaling, shrink the prefab or ask **Agent 05** to change `config.py` (not Agent 15 alone).
4. **`attribution`** must list every Kenney pack used; keep `assets/ATTRIBUTION.md` in sync when adding packs.
5. **`texture_override` paths** must resolve under `assets/` and should use low-res, nearest-neighbor-friendly PNGs. Overrides are authored at final game value, so the renderer displays them without applying the source pack's albedo darkening on top.
6. **`texture_override_mode: "uv"`** is for generated decal meshes only. Do not use it on Kenney atlas meshes unless their UVs are known to map the desired image.

## Example (minimal)

```json
{
  "prefab_id": "peasant_house_small_v1",
  "building_type": "house",
  "footprint_tiles": [1, 1],
  "ground_anchor_y": 0.0,
  "rotation_steps": 90,
  "attribution": ["kenney_retro-fantasy-kit"],
  "pieces": [
    {
      "model": "Models/GLB format/wall-paint-door.glb",
      "pos": [0.0, 0.0, 0.0],
      "rot": [0, 0, 0],
      "scale": [1.0, 1.0, 1.0]
    }
  ],
  "notes": "human-readable design notes"
}
```

## Version history

| Version | Summary |
|---------|---------|
| v0.1 | Initial WK28 spike — root fields + `pieces[{model,pos,rot,scale}]`. |
| v0.2 | **Runtime:** `_load_prefab_instance` **auto-centers** the piece cluster in **XZ** on the prefab root (centroid subtraction); **Y** unchanged. Sim places root at footprint center; `_sync_prefab_building_entity` fit-scales to `footprint_tiles`. Schema doc aligned with `game/graphics/ursina_renderer.py` (WK30). Assembler may still save ad-hoc origins; authors need not manually center in XZ. |
| v0.3 | Added optional per-piece `texture_override` path relative to `assets/` for curated prefab-scoped texture polish (WK32 Inn pass). |
| v0.4 | Added optional `texture_override_mode` for UV-mapped generated decals, used when object-space projection is not readable enough for doors/windows. |
