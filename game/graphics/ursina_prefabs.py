"""Prefab resolution, construction staging, and prefab JSON instantiation (WK41 mechanical split)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import config
from ursina import Entity, Vec3

from game.graphics.ursina_environment import PROJECT_ROOT

_PREFAB_BUILDINGS_DIR = PROJECT_ROOT / "assets" / "prefabs" / "buildings"

H_CASTLE = 2.2
H_BUILDING_3X3 = 1.6
H_BUILDING_2X2 = 1.4
H_BUILDING_1X1 = 0.9
H_LAIR = 1.0

BUILDING_3D_HOUSE_XZ_INSET = 0.88
BUILDING_3D_CASTLE_XZ_INSET = 0.98
BUILDING_3D_LAIR_XZ_INSET = 0.94

_PREFAB_FIT_INSET = 1.0

_PREFAB_BUILDING_TYPE_TO_FILE: dict[str, str] = {
    "farm": "farm_v2.json",
    "food_stand": "food_stand_v2.json",
    "house": "peasant_house_small_v1.json",
    "inn": "inn_v2.json",
    "marketplace": "marketplace_v1.json",
    "blacksmith": "blacksmith_v1.json",
    "trading_post": "trading_post_v1.json",
    "ranger_guild": "ranger_guild_v1.json",
    "temple": "temple_v1.json",
    "guardhouse": "guardhouse_v1.json",
}


def _building_type_str(bt) -> str:
    if bt is None:
        return ""
    return str(getattr(bt, "value", bt) or "")


def _footprint_tiles(building_type) -> tuple[int, int]:
    key = getattr(building_type, "value", building_type)
    return config.BUILDING_SIZES.get(key, (2, 2))


def _is_3d_mesh_building(bts: str, building) -> bool:
    """Castle, peasant house, and monster lairs render as lit 3D meshes (not sprite billboards)."""
    if getattr(building, "is_lair", False) or hasattr(building, "stash_gold"):
        return True
    return bts in ("castle", "house")


def _mesh_kind_for_building(bts: str, building) -> str:
    if getattr(building, "is_lair", False) or hasattr(building, "stash_gold"):
        return "lair"
    if bts == "castle":
        return "castle"
    return "house"


def _building_3d_origin_y(model_path: str, sy: float) -> float:
    """Ursina ``cube`` is centered on its local origin; scale ``sy`` is the world height."""
    if model_path == "cube":
        return sy * 0.5
    return 0.0


def _footprint_scale_3d(
    mesh_kind: str, fx: float, fz: float, hy: float
) -> tuple[float, float, float]:
    """Fill sim footprint in XZ with small insets so adjacent 1×1 houses do not overlap meshes."""
    ix = iz = 1.0
    if mesh_kind == "house":
        ix = iz = BUILDING_3D_HOUSE_XZ_INSET
    elif mesh_kind == "castle":
        ix = iz = BUILDING_3D_CASTLE_XZ_INSET
    elif mesh_kind == "lair":
        ix = iz = BUILDING_3D_LAIR_XZ_INSET
    return (fx * ix, hy, fz * iz)


def _building_height_y(
    tw: int, th: int, building_type, is_lair: bool, is_castle: bool
) -> float:
    if is_castle:
        return H_CASTLE
    if is_lair:
        return H_LAIR
    if tw >= 3 and th >= 3:
        return H_BUILDING_3X3
    if tw == 1 and th == 1:
        return H_BUILDING_1X1
    return H_BUILDING_2X2


def _stage_prefab_path_candidates(base_prefab: Path, stage: str) -> list[Path]:
    """Intermediate JSON candidates: prefer ``<stem>_build_<stage>_v1`` (e.g. inn_v2 → inn_v2_build_20_v1)."""
    stem = base_prefab.stem
    out: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        s = str(p)
        if s not in seen:
            seen.add(s)
            out.append(p)

    add(_PREFAB_BUILDINGS_DIR / f"{stem}_build_{stage}_v1.json")
    m = re.match(r"^(.+)_v(\d+)$", stem)
    if m:
        core, ver = m.group(1), m.group(2)
        add(_PREFAB_BUILDINGS_DIR / f"{core}_build_{stage}_v{ver}.json")
        # Some assets were authored as v1 even when the "final" prefab is v2+.
        # Example: farm_v2.json uses farm_build_20_v1.json / farm_build_50_v1.json.
        add(_PREFAB_BUILDINGS_DIR / f"{core}_build_{stage}_v1.json")
    return out


def _plot_prefab_candidates(tw: int, th: int) -> list[Path]:
    """Ordered plot prefab paths: exact ``plot_wxh`` first, then sensible larger plot fallbacks (WK32 r2)."""
    w, h = int(tw), int(th)
    out: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        s = str(p)
        if s not in seen:
            seen.add(s)
            out.append(p)

    add(_PREFAB_BUILDINGS_DIR / f"plot_{w}x{h}_v1.json")
    wc = max(1, min(3, w))
    hc = max(1, min(3, h))
    if (wc, hc) != (w, h):
        add(_PREFAB_BUILDINGS_DIR / f"plot_{wc}x{hc}_v1.json")
    side = max(1, min(3, max(w, h)))
    add(_PREFAB_BUILDINGS_DIR / f"plot_{side}x{side}_v1.json")
    for sq in (3, 2, 1):
        add(_PREFAB_BUILDINGS_DIR / f"plot_{sq}x{sq}_v1.json")
    return out


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.is_file():
            return p
    return None


def _first_existing_groups(groups: list[list[Path]]) -> Path | None:
    for grp in groups:
        hit = _first_existing(grp)
        if hit is not None:
            return hit
    return None


def _resolve_construction_staged_prefab(
    building,
    base_prefab: Path,
    tw: int,
    th: int,
) -> Path:
    """WK32 (rev 2026-04-18): stage prefab from ``construction_progress`` + file fallback."""
    if bool(getattr(building, "is_constructed", True)):
        return base_prefab
    prog = float(getattr(building, "construction_progress", 0.0) or 0.0)
    prog = min(1.0, max(0.0, prog))
    if prog >= 1.0:
        return base_prefab

    plot_cands = _plot_prefab_candidates(tw, th)
    c20 = _stage_prefab_path_candidates(base_prefab, "20")
    c50 = _stage_prefab_path_candidates(base_prefab, "50")
    base_list = [base_prefab] if base_prefab.is_file() else []

    at_plot = prog <= 1e-9
    if at_plot:
        groups = [plot_cands, c50, c20, base_list]
    elif prog < 0.5:
        groups = [c20, c50, base_list, plot_cands]
    elif prog < 1.0:
        groups = [c50, base_list, c20, plot_cands]
    else:
        groups = [base_list]

    picked = _first_existing_groups(groups) if groups else None
    if picked is not None:
        return picked
    if base_prefab.is_file():
        return base_prefab
    if plot_cands:
        return plot_cands[0]
    return base_prefab


def _resolve_prefab_path(bts: str, building) -> Path | None:
    """WK30: default-on prefab resolution by ``building_type``."""
    if os.environ.get("KINGDOM_URSINA_PREFAB_TEST") == "0":
        return None
    if not bts:
        return None
    if getattr(building, "is_lair", False) or hasattr(building, "stash_gold"):
        p = _PREFAB_BUILDINGS_DIR / "lair_v1.json"
        return p if p.is_file() else None
    filename = _PREFAB_BUILDING_TYPE_TO_FILE.get(bts) or f"{bts}_v1.json"
    path = _PREFAB_BUILDINGS_DIR / filename
    return path if path.is_file() else None


def _load_prefab_instance(prefab_path: Path, world_pos: Vec3) -> Entity:
    """Instantiate a prefab JSON as a container Entity with one child model per piece."""
    from game.graphics.prefab_texture_overrides import (
        apply_prefab_texture_override,
        parse_object_uv_scale_field,
    )
    from tools.kenney_pack_scale import apply_kenney_pack_color_tint_to_entity, pack_extent_multiplier_for_rel
    from tools.model_viewer_kenney import _apply_gltf_color_and_shading

    raw = json.loads(prefab_path.read_text(encoding="utf-8"))
    pieces = raw.get("pieces") or []
    ga = float(raw.get("ground_anchor_y", 0.0))
    authored_ft_raw = raw.get("footprint_tiles", [1, 1]) or [1, 1]
    try:
        authored_w = float(authored_ft_raw[0])
        authored_d = float(authored_ft_raw[1])
    except (TypeError, ValueError, IndexError):
        authored_w = authored_d = 1.0

    if isinstance(world_pos, Vec3):
        wp = (world_pos.x, world_pos.y, world_pos.z)
    else:
        wp = (float(world_pos[0]), float(world_pos[1]), float(world_pos[2]))

    xs = [float(pp.get("pos", [0, 0, 0])[0]) for pp in pieces] or [0.0]
    zs = [float(pp.get("pos", [0, 0, 0])[2]) for pp in pieces] or [0.0]
    min_x, max_x = min(xs), max(xs)
    min_z, max_z = min(zs), max(zs)
    centroid_x = (min_x + max_x) * 0.5
    centroid_z = (min_z + max_z) * 0.5
    spread_x = max_x - min_x
    spread_z = max_z - min_z

    root = Entity(position=wp, collider=None)
    root._ks_prefab_container = True
    root._ks_ground_anchor_y = ga
    root._ks_prefab_source = str(prefab_path)
    root._ks_prefab_authored_ft = (authored_w, authored_d)
    root._ks_prefab_xz_spread = (spread_x, spread_z)
    root._ks_prefab_xz_centroid = (centroid_x, centroid_z)

    models_root = PROJECT_ROOT / "assets" / "models"

    for piece in pieces:
        rel = str(piece.get("model", "")).replace("\\", "/").lstrip("/")
        if not rel:
            continue
        abs_model = models_root / rel
        if not abs_model.is_file():
            continue
        model_str = f"assets/models/{rel}"
        ppos = piece.get("pos", [0, 0, 0])
        prot = piece.get("rot", [0, 0, 0])
        psc = piece.get("scale", [1, 1, 1])
        pf = pack_extent_multiplier_for_rel(rel)
        cpos_x = float(ppos[0]) - centroid_x
        cpos_z = float(ppos[2]) - centroid_z
        child = Entity(
            parent=root,
            model=model_str,
            position=(cpos_x, float(ppos[1]), cpos_z),
            rotation=(float(prot[0]), float(prot[1]), float(prot[2])),
            scale=(
                float(psc[0]) * pf,
                float(psc[1]) * pf,
                float(psc[2]) * pf,
            ),
            collider=None,
            double_sided=True,
        )
        child.collision = False
        child.render_queue = 1
        try:
            child.set_depth_test(True)
            child.set_depth_write(True)
        except Exception:
            pass
        try:
            if child.model is not None:
                _apply_gltf_color_and_shading(
                    child.model,
                    debug_materials=False,
                    model_label=rel,
                )
                apply_kenney_pack_color_tint_to_entity(child, rel)
        except Exception:
            pass
        try:
            apply_prefab_texture_override(
                child,
                piece.get("texture_override"),
                piece.get("texture_override_mode"),
                object_uv_scale=parse_object_uv_scale_field(piece.get("texture_override_object_scale")),
            )
        except Exception:
            pass

    return root
