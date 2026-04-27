"""Environment scatter, Kenney terrain helpers, fog tint on static props (WK41 mechanical split)."""

from __future__ import annotations

import os
import zlib
from pathlib import Path

import config
from ursina import Entity, color

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_MODEL_DIR = PROJECT_ROOT / "assets" / "models" / "environment"

TERRAIN_SCALE_MULTIPLIER = 1.0
TREE_SCALE_MULTIPLIER = 1.15
ROCK_SCALE_MULTIPLIER = 1.68
GRASS_SCATTER_SCALE_MULTIPLIER = 2.08
GROUND_PROP_FLOWER_LOG_MUSHROOM_SCALE = 0.5


def _environment_model_path(kind: str) -> str:
    """Resolve ``assets/models/environment/<kind>.{glb,gltf,obj}`` for Ursina ``Entity(model=...)``."""
    for ext in (".glb", ".gltf", ".obj"):
        p = _ENV_MODEL_DIR / f"{kind}{ext}"
        if p.is_file():
            return f"assets/models/environment/{kind}{ext}"
    if kind == "lair":
        try:
            candidates: list[Path] = []
            for ext in (".glb", ".gltf", ".obj"):
                candidates.extend(_ENV_MODEL_DIR.glob(f"*{ext}"))
            picks = sorted(
                (
                    p
                    for p in candidates
                    if any(k in p.stem.lower() for k in ("graveyard", "mausoleum", "crypt", "tomb", "gy"))
                ),
                key=lambda p: p.name.lower(),
            )
            if picks:
                return f"assets/models/environment/{picks[0].name}"
        except Exception:
            pass
    return "cube"


def _grass_scatter_jitter(tx: int, ty: int) -> tuple[float, float, float]:
    """Deterministic XZ offset + yaw (degrees) so grass doodads read as scattered foliage."""
    h = (tx * 92837111 ^ ty * 689287499) & 0xFFFFFFFF
    jx = ((h & 0xFFFF) / 65535.0 - 0.5) * 0.38
    jz = (((h >> 16) & 0xFFFF) / 65535.0 - 0.5) * 0.38
    yaw = float((tx * 127 + ty * 331) % 360)
    return jx, jz, yaw


_GRASS_DENSITY_PROFILES: dict[str, tuple[int, int]] = {
    "off": (0, 1),
    "low": (1, 3),
    "default": (1, 3),
    "medium": (1, 2),
    "high": (3, 1),
}


def _grass_density_budget() -> tuple[int, int]:
    """Return ``(clumps_per_selected_tile, tile_sampling_stride)`` for grass preview density."""
    raw = os.environ.get("KINGDOM_URSINA_GRASS_DENSITY", "default").strip().lower()
    if raw in _GRASS_DENSITY_PROFILES:
        return _GRASS_DENSITY_PROFILES[raw]
    try:
        clumps = max(0, min(3, int(raw)))
    except ValueError:
        return _GRASS_DENSITY_PROFILES["default"]
    return clumps, 1 if clumps >= 3 else 2


def _grass_tile_selected(tx: int, ty: int, stride: int) -> bool:
    """Deterministic sparse sampling without a visible modulo grid."""
    if stride <= 1:
        return True
    h = (tx * 92837111 ^ ty * 689287499 ^ 0xA511E9B3) & 0xFFFFFFFF
    return (h % max(1, stride * stride)) == 0


def _grass_clump_offset(
    tx: int, ty: int, slot: int, world_half: float
) -> tuple[float, float, float]:
    """Deterministic sub-tile XZ + yaw; fills the cell so scatter does not read as a coarse grid."""
    h = (tx * 92837111 ^ ty * 689287499 ^ (slot * 0x5BD1E995) ^ (slot * 101)) & 0xFFFFFFFF
    jx = ((h & 0xFFFF) / 65535.0 - 0.5) * 2.0 * world_half * 0.95
    jz = (((h >> 16) & 0xFFFF) / 65535.0 - 0.5) * 2.0 * world_half * 0.95
    yaw = float((tx * 127 + ty * 331 + slot * 47) % 360)
    return jx, jz, yaw


_ENV_SCATTER_MODELS: tuple[list[str], list[str]] | None = None
_ENV_TREE_MODELS: list[str] | None = None


def _environment_mesh_priority(suffix: str) -> int:
    """Prefer ``.glb`` over ``.gltf`` over ``.obj`` when the same stem exists twice."""
    s = suffix.lower()
    if s == ".glb":
        return 0
    if s == ".gltf":
        return 1
    if s == ".obj":
        return 2
    return 9


def _dedupe_env_rels_by_stem(rels: list[str]) -> list[str]:
    """One file per basename; duplicate stems keep the highest-priority extension."""
    best: dict[str, tuple[str, int]] = {}
    for rel in rels:
        stem = Path(rel).stem.lower()
        pri = _environment_mesh_priority(Path(rel).suffix)
        prev = best.get(stem)
        if prev is None or pri < prev[1]:
            best[stem] = (rel, pri)
    return [best[k][0] for k in sorted(best.keys())]


def _is_grass_scatter_stem(name: str) -> bool:
    """Small ground foliage: grass tufts, flowers, Nature Kit ``plant_flat*``."""
    return (
        name.startswith("grass")
        or "tuft" in name
        or "wildflower" in name
        or name.startswith("flower")
        or name.startswith("plant_flat")
    )


def _is_doodad_scatter_stem(name: str) -> bool:
    """Rocks, logs, stumps, mushrooms, bushes — includes Kenney ``plant_bush*`` and ``stone*``."""
    return (
        name.startswith("bush")
        or name.startswith("plant_bush")
        or name.startswith("log")
        or name.startswith("stump")
        or name.startswith("mushroom")
        or name.startswith("rock")
        or name.startswith("stone")
    )


def _stem_is_flower_ground_scatter(name: str) -> bool:
    """Flower-style meshes in the grass scatter list (not grass tufts)."""
    s = str(name).lower()
    return "wildflower" in s or s.startswith("flower") or s.startswith("plant_flat")


def _stem_is_log_or_mushroom_ground_scatter(name: str) -> bool:
    """Log and mushroom doodads — scaled down vs rocks/bushes/stumps."""
    s = str(name).lower()
    return s.startswith("log") or s.startswith("mushroom")


def _environment_grass_and_doodad_model_lists() -> tuple[list[str], list[str]]:
    """WK32: scan ``assets/models/environment`` for grass vs other nature props (fallback to legacy names)."""
    global _ENV_SCATTER_MODELS
    if _ENV_SCATTER_MODELS is not None:
        return _ENV_SCATTER_MODELS
    grass: list[str] = []
    doodad: list[str] = []
    default_grass = _environment_model_path("grass")
    default_rock = _environment_model_path("rock")
    if _ENV_MODEL_DIR.is_dir():
        for p in sorted(_ENV_MODEL_DIR.iterdir()):
            if p.suffix.lower() not in (".glb", ".gltf", ".obj"):
                continue
            rel = f"assets/models/environment/{p.name}"
            name = p.stem.lower()
            if name.startswith("tree"):
                continue
            if _is_grass_scatter_stem(name):
                grass.append(rel)
            elif _is_doodad_scatter_stem(name):
                doodad.append(rel)
    grass = _dedupe_env_rels_by_stem(grass)
    doodad = _dedupe_env_rels_by_stem(doodad)
    if not grass:
        grass = [default_grass]
    if not doodad:
        doodad = [default_rock]
    _ENV_SCATTER_MODELS = (grass, doodad)
    return _ENV_SCATTER_MODELS


def _environment_tree_model_list() -> list[str]:
    """All ``tree_*`` meshes under environment (Kenney Nature pines/oaks/etc.); fallback to ``tree_pine``."""
    global _ENV_TREE_MODELS
    if _ENV_TREE_MODELS is not None:
        return _ENV_TREE_MODELS
    out: list[str] = []
    default = _environment_model_path("tree_pine")
    if _ENV_MODEL_DIR.is_dir():
        for p in sorted(_ENV_MODEL_DIR.iterdir()):
            if p.suffix.lower() not in (".glb", ".gltf", ".obj"):
                continue
            name = p.stem.lower()
            if name.startswith("tree"):
                out.append(f"assets/models/environment/{p.name}")
    out = _dedupe_env_rels_by_stem(out)
    if not out:
        out = [default]
    _ENV_TREE_MODELS = out
    return _ENV_TREE_MODELS


def _scatter_model_index(tx: int, ty: int, n: int, salt: int) -> int:
    if n <= 1:
        return 0
    h = (tx * 92837111 ^ ty * 689287499 ^ int(salt) * 1009) & 0xFFFFFFFF
    return int(h % n)


def _building_occupied_tiles(buildings) -> set[tuple[int, int]]:
    """Grid cells covered by any building footprint (for scatter exclusion)."""
    occ: set[tuple[int, int]] = set()
    for b in buildings or []:
        try:
            gx, gy = int(b.grid_x), int(b.grid_y)
            sw, sh = int(b.size[0]), int(b.size[1])
        except Exception:
            continue
        for dx in range(sw):
            for dy in range(sh):
                occ.add((gx + dx, gy + dy))
    return occ


def _apply_kenney_scatter_mesh_shading_only(ent: Entity, model_rel: str) -> None:
    """Fix factor-only / flat materials on env meshes without changing ``entity.color``."""
    try:
        from tools.model_viewer_kenney import _apply_gltf_color_and_shading

        if getattr(ent, "model", None) is None:
            return
        label = model_rel.replace("\\", "/")
        _apply_gltf_color_and_shading(ent.model, debug_materials=False, model_label=label)
        _apply_gltf_color_and_shading(ent, debug_materials=False, model_label=label)
    except Exception:
        pass


def _finalize_kenney_scatter_entity(
    ent: Entity, model_rel: str, *, apply_pack_tint: bool = True
) -> None:
    """Grass/rock/tree/doodad scatter: same material path as path_stone + optional pack tint."""
    try:
        from tools.kenney_pack_scale import apply_kenney_pack_color_tint_to_entity

        _apply_kenney_scatter_mesh_shading_only(ent, model_rel)
        if apply_pack_tint:
            apply_kenney_pack_color_tint_to_entity(ent, model_rel.replace("\\", "/"))
        try:
            m = float(getattr(config, "URSINA_ENV_SCATTER_BRIGHTNESS", 1.0))
        except Exception:
            m = 1.0
        if m > 1.0001:
            try:
                ent.color = color.rgba(
                    min(1.0, float(ent.color.r) * m),
                    min(1.0, float(ent.color.g) * m),
                    min(1.0, float(ent.color.b) * m),
                    float(ent.color.a),
                )
            except Exception:
                pass
        ent._ks_base_color = ent.color
    except Exception:
        pass


def _set_static_prop_fog_tint(ent: Entity, fog_mult: float) -> None:
    """Apply explored-fog darkening to a static terrain prop without compounding tint."""
    if getattr(ent, "_ks_fog_mult", None) == fog_mult:
        return
    base = getattr(ent, "_ks_base_color", None)
    if base is None:
        base = ent.color
        ent._ks_base_color = base
    try:
        ent.color = color.rgba(
            float(base.r) * float(fog_mult),
            float(base.g) * float(fog_mult),
            float(base.b) * float(fog_mult),
            float(base.a),
        )
    except Exception:
        ent.color = base
    ent._ks_fog_mult = fog_mult


def _visibility_signature(world) -> int:
    """Cheap checksum so we only rebuild the fog texture when the grid changes.

    Callers should gate on ``engine._fog_revision`` to avoid running this every frame.
    """
    h = zlib.crc32(b"")
    for y in range(world.height):
        h = zlib.crc32(bytes(world.visibility[y]), h)
    return h & 0xFFFFFFFF
