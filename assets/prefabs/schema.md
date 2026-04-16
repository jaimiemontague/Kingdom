# Building prefab JSON — schema v0.1

Authoritative for **`assets/prefabs/buildings/*.json`**. The Kenney assembler (`tools/model_assembler_kenney.py`) reads and writes this shape; runtime loaders must accept the same fields.

## File layout

- One file per prefab: **`assets/prefabs/buildings/<prefab_id>.json`**
- **`prefab_id`** must match the filename stem (e.g. `peasant_house_small_v1.json` → `prefab_id`: `peasant_house_small_v1`).
- Source **`.glb` / `.gltf` assets are never copied** into `assets/prefabs/`. The `model` field holds a path **relative to `assets/models/`**.

## Root object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prefab_id` | string | yes | Stable id; use suffix `_vN` and bump when changing a shipped prefab. |
| `building_type` | string | yes | Matches sim building type key (e.g. `house`) — must align with `config.py` when used in-game. |
| `footprint_tiles` | `[int, int]` | yes | Width × depth in **tiles** `[w, d]`. Must match the sim footprint for that `building_type` when wired to gameplay. |
| `ground_anchor_y` | number | yes | World **Y** of the building anchor / ground plane for placement (typically `0.0`). |
| `rotation_steps` | number | yes | Degrees per toolbar “rotate step” in the tool (plan default: `90`). Stored for round-trip and future tooling. |
| `attribution` | string[] | yes | Kenney pack ids (e.g. `kenney_retro-fantasy-kit`) — one entry per pack referenced by any `pieces[].model`. Used for credits. |
| `pieces` | array | yes | Ordered list of kit pieces; see below. |
| `notes` | string | no | Human-readable design notes (not read by sim). |

## `pieces[]` item

Each element is one placed kit piece:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | yes | Path relative to **`assets/models/`** (POSIX slashes). Example: `Models/GLB format/wall-paint-door.glb`. |
| `pos` | `[x, y, z]` | yes | Translation from prefab origin. `[0, 0, 0]` = anchor at **center of footprint on the ground**. |
| `rot` | `[rx, ry, rz]` | yes | Rotation in **degrees** (Euler order as produced by the assembler; typically Y-up). |
| `scale` | `[sx, sy, sz]` | yes | Uniform or per-axis scale (default `[1, 1, 1]`). |

## Rules

1. **`model` paths** resolve under `assets/models/` only — no absolute paths.
2. **Transforms** are **per-piece** local transforms in prefab space from the shared origin.
3. **`footprint_tiles`** is a contract with the 2D sim; if the assembled mesh does not fit, shrink the prefab or ask **Agent 05** to change `config.py` (not Agent 15 alone).
4. **`attribution`** must list every Kenney pack used; keep `assets/ATTRIBUTION.md` in sync when adding packs.

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
