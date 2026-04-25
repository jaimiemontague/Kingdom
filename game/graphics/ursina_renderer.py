"""
Translates the GameEngine simulation state into Ursina 3D entities.

Perspective view: floor plane is X/Z (Y up). Simulation pixels (x, y) map to
(world_x, world_z) with world_z = -px_y / SCALE so screen-north stays intuitive
(PM WK19 decision).

v1.5 Sprint 1.2 (Agent 03): Terrain is built from discrete 3D meshes under
``assets/models/environment/`` (grass/path_stone road tiles + water tint + tree/rock props), parented
under one root Entity — no TileSpriteLibrary bake or terrain atlas.

Most buildings use BuildingSpriteLibrary on a single billboard quad; **castle**, **house**,
and **lair** use static 3D meshes from ``assets/models/environment/`` (v1.5 Sprint 2.1).
WK30 (Agent 03): for any building whose ``building_type`` resolves to an existing
``assets/prefabs/buildings/<file>.json`` (see ``_PREFAB_BUILDING_TYPE_TO_FILE`` + the
``<building_type>_v1.json`` convention fallback), the prefab path loads **by default**
via multi-piece instantiation, overriding the static mesh / billboard path. Explicit
opt-out: set ``KINGDOM_URSINA_PREFAB_TEST=0`` to force the legacy render path for all
buildings (any other value or unset = prefabs on). Piece clusters are **auto-centered**
on the sim footprint-center and **fit-scaled** so their visible extent stays inside the
sim footprint (schema v0.2). Optional debug: set ``KINGDOM_URSINA_GRID_DEBUG=1`` to draw
tile gridlines on the terrain.
Units use pixel-art billboards (Hero/Enemy/Worker sprite libraries).

v1.5 Sprint 1.2 (Agent 09): Scene lighting (AmbientLight + shadow-casting
DirectionalLight) is created in ``UrsinaRenderer.__init__`` so untextured 3D
terrain/props read with simple flat-shaded dimensionality.
"""
from __future__ import annotations

import json
import os
import re
import time
import zlib
from pathlib import Path

import pygame
import config
from ursina import Entity, Vec2, Vec3, color, Text, scene
from ursina.lights import AmbientLight, DirectionalLight
from ursina.shaders import lit_with_shadows_shader, unlit_shader

from game.graphics.animation import AnimationClip
from game.graphics.building_sprites import BuildingSpriteLibrary
from game.graphics.enemy_sprites import EnemySpriteLibrary
from game.graphics.hero_sprites import HeroSpriteLibrary
from game.graphics.terrain_texture_bridge import TerrainTextureBridge
from game.graphics.ursina_sprite_unlit_shader import sprite_unlit_shader
from game.graphics.vfx import get_projectile_billboard_surface
from game.graphics.worker_sprites import WorkerSpriteLibrary
from game.world import TileType, Visibility

# Fallback tints when a texture is missing
COLOR_HERO = color.azure
COLOR_ENEMY = color.red
COLOR_PEASANT = color.orange
COLOR_GUARD = color.yellow
COLOR_BUILDING = color.light_gray
COLOR_CASTLE = color.gold
COLOR_LAIR = color.brown

# 1 world unit along the floor == 1 tile == 32 px (unchanged from ortho MVP)
SCALE = 32.0

# v1.5 Sprint 1.2: uniform scale for Kenney OBJ tiles (1×1 plane ≈ one sim tile).
TERRAIN_SCALE_MULTIPLIER = 1.0
# Props sit on the same grid; tune if authored mesh bounds drift.
TREE_SCALE_MULTIPLIER = 1.15
ROCK_SCALE_MULTIPLIER = 0.42
# Grass tiles use organic scatter doodads on the base plane, not full-tile voxels.
GRASS_SCATTER_SCALE_MULTIPLIER = 0.52

# Vertical extents (world units), from Agent 09 volumetric mapping table
H_CASTLE = 2.2
H_BUILDING_3X3 = 1.6
H_BUILDING_2X2 = 1.4
H_BUILDING_1X1 = 0.9
H_LAIR = 1.0

# v1.5 Sprint 2.1 (Agent 09): XZ inset so 1×1 houses sit side-by-side; castle/lair
# fill most of the sim footprint (matches BUILDING_SIZES × TILE_SIZE / SCALE).
BUILDING_3D_HOUSE_XZ_INSET = 0.88
BUILDING_3D_CASTLE_XZ_INSET = 0.98
BUILDING_3D_LAIR_XZ_INSET = 0.94

# WK30: XZ inset applied to prefab-backed buildings after fit-to-footprint scaling.
# 1.0 = prefab's authored extent fills the sim footprint exactly; anything <1 leaves a
# small margin so meshes never visually overlap grid lines / adjacent buildings. Tune
# here rather than per-type — prefab authors pick their own authored extent already.
_PREFAB_FIT_INSET = 1.0

# Pixel billboard height in world units (32px sprite read at map scale)
UNIT_BILLBOARD_SCALE = 0.62

# Stable bridge keys — never use id(surface) alone for multi-megapixel sheets (see terrain_texture_bridge).
_FOG_TEX_KEY = "kingdom_ursina_fog_overlay"

ENEMY_SCALE = 0.5
PEASANT_SCALE = 0.465
GUARD_SCALE_XZ = 0.5
GUARD_SCALE_Y = 0.7

# Ranged VFX billboards — keep smaller than hero sprites (~UNIT_BILLBOARD_SCALE 0.62)
PROJECTILE_BILLBOARD_SCALE = 0.1


def sim_px_to_world_xz(px_x: float, px_y: float) -> tuple[float, float]:
    """Map sim pixel coords to the X/Z floor (Y-up world)."""
    return px_x / SCALE, -px_y / SCALE


def px_to_world(px_x: float, px_y: float) -> tuple[float, float]:
    """Backward-compatible name: returns (world_x, world_z) for the floor plane."""
    return sim_px_to_world_xz(px_x, px_y)


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_MODEL_DIR = _PROJECT_ROOT / "assets" / "models" / "environment"
# WK29/WK30: prefab JSONs for kitbashed buildings (authored by Agent 15).
_PREFAB_BUILDINGS_DIR = _PROJECT_ROOT / "assets" / "prefabs" / "buildings"

# WK30 (Agent 03): single-source lookup table for ``building_type`` -> prefab filename.
# Non-convention entries are listed explicitly; anything not in this table falls back to
# the ``<building_type>_v1.json`` convention in ``_resolve_prefab_path``. Keep this table
# sorted and minimal — the expectation is that new buildings land under the convention.
_PREFAB_BUILDING_TYPE_TO_FILE: dict[str, str] = {
    # WK31 economy visual pass (Jaimie): inn_v2, farm_v1, food_stand_v2, gnome_hovel_v1.
    "farm": "farm_v1.json",
    "food_stand": "food_stand_v2.json",
    "gnome_hovel": "gnome_hovel_v1.json",
    # WK29 shipped the first house under a descriptive filename (not ``house_v1``).
    "house": "peasant_house_small_v1.json",
    "inn": "inn_v2.json",
}


def _environment_model_path(kind: str) -> str:
    """Resolve ``assets/models/environment/<kind>.{glb,gltf,obj}`` for Ursina ``Entity(model=...)``."""
    for ext in (".glb", ".gltf", ".obj"):
        p = _ENV_MODEL_DIR / f"{kind}{ext}"
        if p.is_file():
            return f"assets/models/environment/{kind}{ext}"
    return "cube"


def _grass_scatter_jitter(tx: int, ty: int) -> tuple[float, float, float]:
    """Deterministic XZ offset + yaw (degrees) so grass doodads read as scattered foliage."""
    h = (tx * 92837111 ^ ty * 689287499) & 0xFFFFFFFF
    jx = ((h & 0xFFFF) / 65535.0 - 0.5) * 0.38
    jz = (((h >> 16) & 0xFFFF) / 65535.0 - 0.5) * 0.38
    yaw = float((tx * 127 + ty * 331) % 360)
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


def _building_occupied_tiles(engine) -> set[tuple[int, int]]:
    """Grid cells covered by any building footprint (for scatter exclusion)."""
    occ: set[tuple[int, int]] = set()
    for b in getattr(engine, "buildings", []) or []:
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
        _apply_gltf_color_and_shading(
            ent.model,
            debug_materials=False,
            model_label=model_rel.replace("\\", "/"),
        )
    except Exception:
        pass


def _finalize_kenney_scatter_entity(
    ent: Entity, model_rel: str, *, apply_pack_tint: bool = True
) -> None:
    """Grass/rock/tree/doodad scatter: same material path as path_stone + optional pack tint.

    Without ``_apply_gltf_color_and_shading``, factor-only GLBs read as flat white; rocks look
    unshaded. ``model_rel`` is a repo-relative path using forward slashes, e.g.
    ``assets/models/environment/grass.obj``.

    Set ``apply_pack_tint=False`` when ``entity.color`` is authored (e.g. water blue tint).
    """
    try:
        from tools.kenney_pack_scale import apply_kenney_pack_color_tint_to_entity

        _apply_kenney_scatter_mesh_shading_only(ent, model_rel)
        if apply_pack_tint:
            apply_kenney_pack_color_tint_to_entity(ent, model_rel.replace("\\", "/"))
    except Exception:
        pass


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
    # Authored meshes: assume pivot near ground (common for env exports); adjust per-asset if needed.
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


def _stage_prefab_path(base_prefab: Path, stage: str) -> Path:
    """Intermediate build JSON: <core>_build_<stage>_v<ver>.json matching base version (WK32)."""
    stem = base_prefab.stem
    m = re.match(r"^(.+)_v(\d+)$", stem)
    if m:
        core, ver = m.group(1), m.group(2)
        return _PREFAB_BUILDINGS_DIR / f"{core}_build_{stage}_v{ver}.json"
    return _PREFAB_BUILDINGS_DIR / f"{stem}_build_{stage}_v1.json"


def _plot_prefab_path(tw: int, th: int) -> Path:
    w = max(1, min(3, int(tw)))
    h = max(1, min(3, int(th)))
    return _PREFAB_BUILDINGS_DIR / f"plot_{w}x{h}_v1.json"


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.is_file():
            return p
    return None


def _resolve_construction_staged_prefab(
    building,
    base_prefab: Path,
    tw: int,
    th: int,
) -> Path:
    """WK32 (rev 2026-04-18): stage prefab from ``construction_progress`` + file fallback.

    Thresholds (must match Agent 15 filenames):
      progress == 0.0            -> plot_{w}x{h}_v1
      0.0 < progress < 0.50      -> <base>_build_20_v*.json
      0.50 <= progress < 1.0     -> <base>_build_50_v*.json
      progress >= 1.0 (built)    -> final base prefab

    Fallback when a stage file is missing (never crash): 50% → 20% → plot → final (last resort).
    ``KINGDOM_URSINA_PREFAB_TEST=0`` skips the whole prefab path upstream (no staging).
    """
    if bool(getattr(building, "is_constructed", True)):
        return base_prefab
    prog = float(getattr(building, "construction_progress", 0.0) or 0.0)
    prog = min(1.0, max(0.0, prog))
    if prog >= 1.0:
        return base_prefab

    p_plot = _plot_prefab_path(tw, th)
    p20 = _stage_prefab_path(base_prefab, "20")
    p50 = _stage_prefab_path(base_prefab, "50")

    # Only the initial instant (no build work yet) uses the empty plot; any HP gain uses 20%/50%.
    at_plot = prog <= 1e-9
    if at_plot:
        order = [p_plot, p50, p20, base_prefab]
    elif prog < 0.5:
        order = [p20, p50, base_prefab, p_plot]
    elif prog < 1.0:
        order = [p50, base_prefab, p20, p_plot]
    else:
        order = [base_prefab]

    picked = _first_existing(order)
    if picked is not None:
        return picked
    return base_prefab if base_prefab.is_file() else p_plot


def _resolve_prefab_path(bts: str, building) -> Path | None:
    """WK30: default-on prefab resolution by ``building_type``.

    Returns the Path of the prefab JSON to load for this building, or ``None`` if the
    legacy (static mesh / billboard) render path should be used instead.

    Decision rules (short-circuit in order):

    1. ``KINGDOM_URSINA_PREFAB_TEST=0`` (explicit zero) → force legacy path for everything.
       Any other value, or env unset, keeps prefabs on.
    2. No ``building_type`` string → legacy.
    3. Lairs keep their dedicated ``lair`` mesh (no prefab contract yet). Detected via the
       same ``is_lair`` / ``stash_gold`` hook used by ``_is_3d_mesh_building``.
    4. Filename = explicit ``_PREFAB_BUILDING_TYPE_TO_FILE`` entry, else convention
       ``<building_type>_v1.json``.
    5. File must exist under ``_PREFAB_BUILDINGS_DIR``; otherwise → legacy.
    """
    if os.environ.get("KINGDOM_URSINA_PREFAB_TEST") == "0":
        return None
    if not bts:
        return None
    if getattr(building, "is_lair", False) or hasattr(building, "stash_gold"):
        return None
    filename = _PREFAB_BUILDING_TYPE_TO_FILE.get(bts) or f"{bts}_v1.json"
    path = _PREFAB_BUILDINGS_DIR / filename
    return path if path.is_file() else None


def _load_prefab_instance(prefab_path: Path, world_pos: Vec3) -> Entity:
    """Instantiate a prefab JSON as a container Entity with one child model per piece.

    Applies ``tools.model_viewer_kenney._apply_gltf_color_and_shading`` per piece (two-path
    classifier: textured vs factor-only). Import kept in tools/ for WK29 spike (single source
    of truth with the Kenney viewer).

    Schema v0.2 (WK30 hotfix-to-R1): the loader **auto-centers** the piece XZ bounding box
    onto the root origin, and stashes ``authored_footprint_tiles`` + piece XZ spread on the
    root so ``_sync_prefab_building_entity`` can fit-scale the cluster to the sim footprint.
    Piece Y values are honored verbatim (vertical stacking is an author intent we do not
    distort). Effect: prefabs with different per-prefab anchors (WK28 assembler) all render
    centered on the sim building's footprint-center, and the visible mesh extent fits
    within the sim footprint.
    """
    from game.graphics.prefab_texture_overrides import apply_prefab_texture_override
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

    # WK30: compute XZ bounding box from piece positions so the cluster can be centered.
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

    models_root = _PROJECT_ROOT / "assets" / "models"

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
        # WK31: Kenney pack uniform scale vs Retro (single source: tools/kenney_pack_scale.py).
        pf = pack_extent_multiplier_for_rel(rel)
        # WK30 auto-center: subtract the XZ centroid so the cluster is centered on (0, 0)
        # in root-local space. Y is left alone (vertical stacking stays as authored).
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
            )
        except Exception:
            pass

    return root


def _frame_index_for_clip(clip: AnimationClip, elapsed: float) -> tuple[int, bool]:
    """Match ``AnimationPlayer`` timing: non-looping finishes after n frame-times."""
    n = len(clip.frames)
    ft = clip.frame_time_sec
    if n == 0:
        return 0, True
    if ft <= 0:
        return 0, False
    if clip.loop:
        cycle = n * ft
        if cycle <= 0:
            return 0, False
        t = elapsed % cycle
        idx = int(t / ft) % n
        return idx, False
    steps = int(elapsed / ft)
    if steps >= n:
        return n - 1, True
    return steps, False


def _hero_base_clip(hero) -> str:
    if bool(getattr(hero, "is_inside_building", False)):
        return "inside"
    state = getattr(hero, "state", None)
    state_name = str(getattr(state, "name", state))
    if state_name in ("MOVING", "RETREATING"):
        return "walk"
    return "idle"


def _enemy_base_clip(enemy) -> str:
    state = getattr(enemy, "state", None)
    state_name = str(getattr(state, "name", state))
    return "walk" if state_name == "MOVING" else "idle"


def _worker_idle_surface(worker_type: str):
    wt = str(worker_type or "peasant").lower()
    clips = WorkerSpriteLibrary.clips_for(wt)
    return clips["idle"].frames[0]


def _visibility_signature(world) -> int:
    """Cheap checksum so we only rebuild the fog texture when the grid changes.

    WK22 Agent-10 perf note: this is O(W*H) — ~22,500 tiles at default map size.
    Callers should gate on ``engine._fog_revision`` to avoid running this every frame.
    """
    h = zlib.crc32(b"")
    for y in range(world.height):
        h = zlib.crc32(bytes(world.visibility[y]), h)
    return h & 0xFFFFFFFF


class UrsinaRenderer:
    def __init__(self, engine):
        self.engine = engine

        # Entity mappings: simulation object id() -> Ursina Entity
        self._entities = {}

        # v1.5: parent Entity for per-tile 3D terrain meshes (see _build_3d_terrain).
        self._terrain_entity: Entity | None = None

        # WK30 debug: tile-gridline overlay entity (populated once when env flag is set).
        self._grid_debug_entity: Entity | None = None

        # Fog-of-war overlay quad (WK22): matches pygame render_fog tints per visibility tile.
        self._fog_entity: Entity | None = None
        self._fog_full_surf: pygame.Surface | None = None
        # RGBA tile buffer reused for fog rebuilds (WK22 R3 perf: avoid 22k pygame.set_at calls).
        self._fog_tile_buf: bytearray | None = None
        self._visibility_gated_terrain: list[tuple[Entity, int, int]] = []
        self._terrain_visibility_revision_seen = -1

        # Status Text UI (2D overlay, not affected by world camera)
        self.status_text = Text(
            text="Kingdom Sim - Ursina Viewer",
            position=(-0.85, 0.47),
            scale=1.2,
            color=color.black,
            background=True,
        )

        # WK22 R3: per-sim-object billboard animation (wall clock; consumes _render_anim_trigger).
        self._unit_anim_state: dict[int, dict] = {}
        # WK23: single shared GPU texture for VFX projectiles (arrow-shaped, not yellow fallback).
        self._projectile_tex = None

        # --- v1.5: base lighting for 3D meshes (flat-shaded, optional shadows) ---
        self._directional_light = None
        self._shadow_bounds_initialized = False
        self._setup_scene_lighting()

    def _setup_scene_lighting(self) -> None:
        """Dim gray-blue ambient + warm directional sun; directional casts shadow maps when enabled.

        Billboards keep unlit_shader + shadow-mask hide; lit 3D terrain/props use default_shader
        from UrsinaApp (lit_with_shadows when URSINA_DIRECTIONAL_SHADOWS is True).
        """
        try:
            from ursina import color as ucolor

            world = self.engine.world
            tw, th = int(world.width), int(world.height)
            ts = float(config.TILE_SIZE)
            cx_px = tw * ts * 0.5
            cy_px = th * ts * 0.5
            cx, cz = sim_px_to_world_xz(cx_px, cy_px)

            # Slightly cool ambient so untextured meshes are not silhouette-black.
            AmbientLight(parent=scene, color=ucolor.rgba(0.34, 0.38, 0.44, 1.0))

            _shadows = bool(getattr(config, "URSINA_DIRECTIONAL_SHADOWS", False))
            sm = int(getattr(config, "URSINA_SHADOW_MAP_SIZE", 768))
            sm = max(256, min(2048, sm))

            dl = DirectionalLight(
                parent=scene,
                shadows=_shadows,
                shadow_map_resolution=Vec2(sm, sm),
                color=ucolor.rgba(0.98, 0.95, 0.88, 1.0),
            )
            # Downward angled sun toward map center (same framing as prior UrsinaApp setup).
            dl.position = Vec3(cx + 55.0, 95.0, cz + 40.0)
            dl.look_at(Vec3(cx, 0.0, cz))
            self._directional_light = dl
        except Exception:
            self._directional_light = None

    def _unit_anim_surface(
        self,
        obj_id: int,
        entity,
        clips: dict[str, AnimationClip],
        base_clip_fn,
        cache_prefix: str,
        class_key: str,
    ) -> tuple[pygame.Surface, tuple]:
        """Pick hero/enemy frame from clips using triggers + base locomotion; time-based playback."""
        # Prefer snapshot from engine (see _update_render_animations): pygame clears _render_anim_trigger first.
        trigger = getattr(entity, "_ursina_anim_trigger", None) or getattr(
            entity, "_render_anim_trigger", None
        )
        if trigger:
            tname = str(trigger)
            if tname in clips:
                setattr(entity, "_ursina_anim_trigger", None)
                setattr(entity, "_render_anim_trigger", None)
                base = base_clip_fn(entity)
                self._unit_anim_state[obj_id] = {
                    "clip": tname,
                    "t0": time.time(),
                    "base": base,
                    "oneshot": not clips[tname].loop,
                }
            else:
                setattr(entity, "_ursina_anim_trigger", None)
                setattr(entity, "_render_anim_trigger", None)

        base = base_clip_fn(entity)
        st = self._unit_anim_state.get(obj_id)
        if st is None:
            self._unit_anim_state[obj_id] = {
                "clip": base,
                "t0": time.time(),
                "base": base,
                "oneshot": False,
            }
            st = self._unit_anim_state[obj_id]
        else:
            st["base"] = base
            if st.get("oneshot"):
                oc = clips[st["clip"]]
                elapsed_done = time.time() - st["t0"]
                _i, finished = _frame_index_for_clip(oc, elapsed_done)
                if finished:
                    st["clip"] = st["base"]
                    st["t0"] = time.time()
                    st["oneshot"] = False
            if not st.get("oneshot"):
                if st["clip"] != base:
                    st["clip"] = base
                    st["t0"] = time.time()

        clip_name = st["clip"]
        clip = clips[clip_name]
        elapsed = time.time() - st["t0"]
        idx, _fin = _frame_index_for_clip(clip, elapsed)
        surf = clip.frames[idx]
        cache_key = (cache_prefix, "anim", class_key, clip_name, idx, int(config.TILE_SIZE))
        return surf, cache_key

    def _ensure_fog_overlay(self) -> None:
        """Darken unexplored / non-visible tiles in 3D (matches 2D render_fog semantics).

        WK22: Rebuild only when ``engine._fog_revision`` advances (revealer crossed a tile).

        WK23 follow-up: removed throttle; removed CRC skip path; advance ``_fog_revision_seen`` only
        after a successful GPU upload. In perspective, this quad is ground fog only; vertical
        props are separately gated by tile visibility so camera angle cannot make them leak.
        """
        if self._terrain_entity is None:
            return

        world = self.engine.world

        engine_rev = getattr(self.engine, "_fog_revision", 0)
        my_rev = getattr(self, "_fog_revision_seen", -1)
        if engine_rev == my_rev and self._fog_entity is not None:
            return

        tw, th = int(world.width), int(world.height)

        # WK22 Agent-10 perf: render fog at TILE resolution (1 px per tile)
        # instead of pixel resolution (TILE_SIZE px per tile).  This shrinks
        # the surface from 4800×4800 (92 MB) to 150×150 (90 KB) — a ~1000×
        # reduction in tobytes / PIL / GPU upload cost.  The GPU upscales
        # the texture to cover the terrain quad; nearest-neighbor filtering
        # keeps hard tile edges.
        #
        # WK22 R3 bug hunt: building the fog surface with set_at() per tile
        # costs tens of ms (Python call overhead) and caused rhythmic hitches
        # whenever visibility changed.  Fill a packed RGBA bytearray instead.
        need = tw * th * 4
        if self._fog_tile_buf is None or len(self._fog_tile_buf) != need:
            self._fog_tile_buf = bytearray(need)
        buf = self._fog_tile_buf
        row_unseen = b"\x00\x00\x00\xff" * tw
        for ty in range(th):
            buf[ty * tw * 4 : (ty + 1) * tw * 4] = row_unseen
        vis_b = b"\x00\x00\x00\x00"
        seen_b = b"\x00\x00\x00\xaa"  # 170 alpha — matches 2D fog "seen" tint
        # WK23 FIX: write rows in REVERSE sim-Y order so the texture's row-0
        # corresponds to map-south (sim_py == th*ts).  sim_px_to_world_xz negates
        # the Y axis (world_z = -py/SCALE), so map-south ends at world_z=0 (the
        # +Z edge of the quad after rotation_x=90°).  Without this reversal the
        # fog is mirrored North↔South and the lit circle tracks the wrong half of
        # the map relative to where heroes actually stand.
        for ty in range(th):
            row = world.visibility[ty]
            # Map sim row ty → buf row (th-1-ty) to flip N/S in texture space.
            buf_row = th - 1 - ty
            base = buf_row * tw * 4
            for tx in range(tw):
                st = row[tx]
                if st == Visibility.VISIBLE:
                    o = base + tx * 4
                    buf[o : o + 4] = vis_b
                elif st == Visibility.SEEN:
                    o = base + tx * 4
                    buf[o : o + 4] = seen_b

        surf = pygame.image.frombuffer(buf, (tw, th), "RGBA")
        self._fog_full_surf = surf

        ftex = TerrainTextureBridge.refresh_surface_texture(surf, cache_key=_FOG_TEX_KEY)
        if ftex is None:
            # Do not advance _fog_revision_seen — otherwise we never retry and fog stays stale.
            return

        ts = int(config.TILE_SIZE)
        # WK23 R1: Quad size + center MUST match _build_3d_terrain() map extent — any drift
        # misaligns fog vs terrain and makes FOW “slide” relative to heroes/units.
        w_world = (tw * ts) / SCALE
        d_world = (th * ts) / SCALE
        cx_px = tw * ts * 0.5
        cy_px = th * ts * 0.5
        wx, wz = sim_px_to_world_xz(cx_px, cy_px)

        from panda3d.core import TransparencyAttrib

        # SPRINT-BUG-008: keep fog well above the terrain quad.
        fog_y = float(getattr(config, "URSINA_FOG_QUAD_Y", 0.12))

        if self._fog_entity is None:
            self._fog_entity = Entity(
                model="quad",
                texture=ftex,
                scale=(w_world, d_world, 1),
                rotation=(90, 0, 0),
                position=(wx, fog_y, wz),
                color=color.white,
                double_sided=True,
            )
            if self._fog_entity.texture:
                self._fog_entity.texture.filtering = None
            self._fog_entity.texture_scale = Vec2(1, -1)
            self._fog_entity.texture_offset = Vec2(0, 1)
            self._fog_entity.setTransparency(TransparencyAttrib.M_alpha)
            self._fog_entity.set_depth_write(False)
            # Overlay must not depth-fail against billboards/terrain or FOW darkening desyncs visually.
            self._fog_entity.set_depth_test(False)
            self._fog_entity.shader = unlit_shader
            self._fog_entity.hide(0b0001)
            # Ground fog must render before buildings/props; vertical objects are hidden by tile visibility.
            self._fog_entity.render_queue = 0
        else:
            self._fog_entity.texture = ftex
            self._fog_entity.position = (wx, fog_y, wz)
            self._fog_entity.scale = (w_world, d_world, 1)
            self._fog_entity.texture_scale = Vec2(1, -1)
            self._fog_entity.texture_offset = Vec2(0, 1)
            self._fog_entity.render_queue = 0

        self._fog_revision_seen = engine_rev

    def _track_visibility_gated_terrain(self, ent: Entity, tx: int, ty: int) -> None:
        """Register vertical terrain props that should disappear unless their base tile is visible."""
        # Vertical props must draw after the ground-fog quad; otherwise their tops can be clipped
        # by fog that is visually behind them at shallow perspective camera angles.
        ent.render_queue = 1
        self._visibility_gated_terrain.append((ent, int(tx), int(ty)))

    def _sync_visibility_gated_terrain(self) -> None:
        """Hide tall terrain props outside visible fog so they cannot protrude over the fog edge."""
        world = self.engine.world
        engine_rev = int(getattr(self.engine, "_fog_revision", 0))
        if self._terrain_visibility_revision_seen == engine_rev:
            return
        for ent, tx, ty in self._visibility_gated_terrain:
            is_visible = (
                0 <= ty < world.height
                and 0 <= tx < world.width
                and world.visibility[ty][tx] == Visibility.VISIBLE
            )
            ent.enabled = bool(is_visible)
        self._terrain_visibility_revision_seen = engine_rev

    def _ensure_grid_debug_overlay(self) -> None:
        """WK30 debug: draw tile gridlines on the terrain when ``KINGDOM_URSINA_GRID_DEBUG=1``.

        Off by default. When enabled, renders one line-mesh Entity spanning a
        configurable square region around the castle (smaller than the full map so the
        lines read clearly from a close camera). The region size in tiles is controlled
        by ``KINGDOM_URSINA_GRID_DEBUG_TILES`` (default 20). Slightly above ``y=0`` to
        avoid z-fighting with the terrain quad.
        """
        if os.environ.get("KINGDOM_URSINA_GRID_DEBUG") != "1":
            if self._grid_debug_entity is not None:
                try:
                    import ursina as u

                    u.destroy(self._grid_debug_entity)
                except Exception:
                    pass
                self._grid_debug_entity = None
            return
        if self._grid_debug_entity is not None:
            return
        try:
            from ursina import Mesh
        except Exception:
            return

        world = self.engine.world
        tw, th = int(world.width), int(world.height)
        ts = int(config.TILE_SIZE)

        try:
            radius_tiles = int(os.environ.get("KINGDOM_URSINA_GRID_DEBUG_TILES", "") or "0")
        except ValueError:
            radius_tiles = 0
        # Anchor on the castle for debug focus; fall back to map center.
        castle = next(
            (
                b
                for b in getattr(self.engine, "buildings", [])
                if getattr(b, "building_type", None) == "castle"
            ),
            None,
        )
        if castle is not None:
            cx_tiles = int(castle.grid_x) + int(castle.size[0]) // 2
            cy_tiles = int(castle.grid_y) + int(castle.size[1]) // 2
        else:
            cx_tiles = tw // 2
            cy_tiles = th // 2

        if radius_tiles <= 0:
            tx_lo, tx_hi = 0, tw
            ty_lo, ty_hi = 0, th
        else:
            tx_lo = max(0, cx_tiles - radius_tiles)
            tx_hi = min(tw, cx_tiles + radius_tiles + 1)
            ty_lo = max(0, cy_tiles - radius_tiles)
            ty_hi = min(th, cy_tiles + radius_tiles + 1)

        y = 0.02  # just above terrain to avoid z-fighting; still below building meshes.
        x_min_world = (tx_lo * ts) / SCALE
        x_max_world = (tx_hi * ts) / SCALE
        z_max_world = -(ty_lo * ts) / SCALE
        z_min_world = -(ty_hi * ts) / SCALE

        verts: list[tuple[float, float, float]] = []
        for tx in range(tx_lo, tx_hi + 1):
            x = (tx * ts) / SCALE
            verts.append((x, y, z_min_world))
            verts.append((x, y, z_max_world))
        for ty in range(ty_lo, ty_hi + 1):
            z = -(ty * ts) / SCALE
            verts.append((x_min_world, y, z))
            verts.append((x_max_world, y, z))

        grid_mesh = Mesh(vertices=verts, mode="line", thickness=2.5)
        self._grid_debug_entity = Entity(
            model=grid_mesh,
            color=color.rgba(1.0, 0.95, 0.3, 0.95),
            shader=unlit_shader,
            collider=None,
        )
        try:
            from panda3d.core import TransparencyAttrib

            self._grid_debug_entity.setTransparency(TransparencyAttrib.M_alpha)
        except Exception:
            pass
        self._grid_debug_entity.set_depth_write(False)
        # Render above the terrain quad but below fog and billboards.
        self._grid_debug_entity.render_queue = 3

    def _build_3d_terrain(self) -> None:
        """Per-tile path/water meshes + scatter grass doodads on a full-map base plane (v1.5 Sprint 1.2)."""
        if self._terrain_entity is not None:
            return

        world = self.engine.world
        tw, th = int(world.width), int(world.height)
        ts = int(config.TILE_SIZE)
        m = float(TERRAIN_SCALE_MULTIPLIER)
        grass_models, doodad_models = _environment_grass_and_doodad_model_lists()
        tree_models = _environment_tree_model_list()
        # Gray stone path (Nature Kit path_stone) — reads as pavement vs warm Retro Fantasy roofs.
        path_model = _environment_model_path("path_stone")
        rock_model = _environment_model_path("rock")
        occupied_tiles = _building_occupied_tiles(self.engine)
        tm = m * float(TREE_SCALE_MULTIPLIER)
        rm = m * float(ROCK_SCALE_MULTIPLIER)
        g_sc = m * float(GRASS_SCATTER_SCALE_MULTIPLIER)
        scatter_stride = max(1, int(getattr(config, "URSINA_TERRAIN_SCATTER_STRIDE", 1)))

        root = Entity(name="terrain_3d_root")
        water_tint = color.rgb(0.24, 0.48, 0.82)

        # Cohesive green ground plane under the grid (organic scatter sits on y≈0 above this).
        w_world = (tw * ts) / SCALE
        d_world = (th * ts) / SCALE
        cx_px = tw * ts * 0.5
        cy_px = th * ts * 0.5
        base_wx, base_wz = sim_px_to_world_xz(cx_px, cy_px)
        Entity(
            parent=root,
            model="quad",
            color=color.rgb(0.2, 0.5, 0.2),
            scale=(w_world, d_world, 1),
            rotation=(90, 0, 0),
            position=(base_wx, -0.05, base_wz),
            collision=False,
            double_sided=True,
            shader=unlit_shader,
            add_to_scene_entities=False,
        )

        for ty in range(th):
            for tx in range(tw):
                tile = int(world.tiles[ty][tx])
                cx_px = tx * ts + ts * 0.5
                cy_px = ty * ts + ts * 0.5
                wx, wz = px_to_world(cx_px, cy_px)

                if tile == TileType.PATH:
                    path_ent = Entity(
                        parent=root,
                        model=path_model,
                        position=(wx, 0.0, wz),
                        scale=(m, m, m),
                        color=color.white,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )
                    _finalize_kenney_scatter_entity(path_ent, path_model)
                elif tile == TileType.WATER:
                    # WK32-BUG-007: flat water plane — not a tinted grass cross-mesh.
                    tile_w = (float(ts) / SCALE) * m
                    Entity(
                        parent=root,
                        model="quad",
                        rotation=(90, 0, 0),
                        position=(wx, 0.005, wz),
                        scale=(tile_w, tile_w, 1),
                        color=water_tint,
                        collision=False,
                        double_sided=True,
                        shader=unlit_shader,
                        add_to_scene_entities=False,
                    )

                # WK31: optional stride reduces grass-clutter entities (deterministic grid; trees unchanged).
                # WK32: sample grass model index from expanded environment list.
                on_scatter_grid = (tx % scatter_stride == 0) and (ty % scatter_stride == 0)
                in_occ = (tx, ty) in occupied_tiles
                if (
                    (tile == TileType.GRASS or tile == TileType.TREE)
                    and on_scatter_grid
                    and not in_occ
                ):
                    jx, jz, yaw = _grass_scatter_jitter(tx, ty)
                    gi = _scatter_model_index(tx, ty, len(grass_models), salt=11)
                    gm = grass_models[gi]
                    g_ent = Entity(
                        parent=root,
                        model=gm,
                        position=(wx + jx, 0.0, wz + jz),
                        scale=(g_sc, g_sc, g_sc),
                        rotation=(0, yaw, 0),
                        color=color.white,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )
                    _finalize_kenney_scatter_entity(g_ent, gm)
                    self._track_visibility_gated_terrain(g_ent, tx, ty)

                if tile == TileType.TREE:
                    ti = _scatter_model_index(tx, ty, len(tree_models), salt=41)
                    tree_model = tree_models[ti]
                    tree_ent = Entity(
                        parent=root,
                        model=tree_model,
                        position=(wx, 0.0, wz),
                        scale=(tm, tm, tm),
                        color=color.white,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )
                    _finalize_kenney_scatter_entity(tree_ent, tree_model)
                    self._track_visibility_gated_terrain(tree_ent, tx, ty)
                elif (
                    tile == TileType.GRASS
                    and on_scatter_grid
                    and not in_occ
                    and ((tx * 131 + ty * 17) % 11 == 0)
                ):
                    di = _scatter_model_index(tx, ty, len(doodad_models), salt=29)
                    dm = doodad_models[di]
                    jx, jz, yaw = _grass_scatter_jitter(tx + 101, ty + 67)
                    dm_scale = rm * (0.85 if "bush" in Path(dm).stem.lower() else 1.0)
                    doodad_ent = Entity(
                        parent=root,
                        model=dm,
                        position=(wx + jx * 0.55, 0.0, wz + jz * 0.55),
                        scale=(dm_scale, dm_scale, dm_scale),
                        rotation=(0, yaw, 0),
                        color=color.white,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )
                    _finalize_kenney_scatter_entity(doodad_ent, dm)
                    self._track_visibility_gated_terrain(doodad_ent, tx, ty)
                elif tile == TileType.GRASS and on_scatter_grid and not in_occ:
                    h = (tx * 92837111 ^ ty * 689287499) & 0xFFFFFFFF
                    if h % 503 == 0:
                        rock_ent = Entity(
                            parent=root,
                            model=rock_model,
                            position=(wx, 0.0, wz),
                            scale=(rm, rm, rm),
                            color=color.white,
                            collision=False,
                            double_sided=True,
                            add_to_scene_entities=False,
                        )
                        _finalize_kenney_scatter_entity(rock_ent, rock_model)
                        self._track_visibility_gated_terrain(rock_ent, tx, ty)

        # Do not flattenStrong() the terrain root: Panda3D merge can strip per-tile glTF
        # material state and turn Kenney path_stone (and similar) into uniform white strips.
        # WK22 perf note: revisit batching once path meshes use a single atlas or baked strip.
        # root.flattenStrong()
        self._terrain_entity = root

    @staticmethod
    def _apply_pixel_billboard_settings(ent: Entity) -> None:
        """Alpha-cutout sprites: discard transparent texels; sort/blend without black halos."""
        from panda3d.core import TransparencyAttrib

        ent.shader = sprite_unlit_shader
        ent.double_sided = True
        ent.setTransparency(TransparencyAttrib.M_alpha)
        ent.set_depth_write(False)
        ent.render_queue = 1
        # WK22 SPRINT-BUG-006: exclude alpha billboards from directional shadow pass (mask 0b0001).
        ent.hide(0b0001)

    @staticmethod
    def _sync_inside_hero_draw_layer(ent: Entity, is_inside: bool) -> None:
        """Stack order like a 2D top layer: same world position, drawn after buildings, no depth reject.

        When a hero uses the ``inside`` clip (bubble/circle), the quad must composite over the
        building façade pixels — not float in Y. Terrain/fog stay 0–2; inside heroes use queue 3.
        """
        want = bool(is_inside)
        if getattr(ent, "_ks_inside_layer", None) is want:
            return
        ent._ks_inside_layer = want
        if want:
            ent.render_queue = 3
            ent.set_depth_test(False)
        else:
            ent.render_queue = 1
            ent.set_depth_test(True)

    @staticmethod
    def _set_texture_if_changed(ent: Entity, tex) -> None:
        """Avoid model.setTexture every frame — Ursina's texture setter always reapplies (WK22 R3)."""
        if getattr(ent, "_texture", None) is tex:
            return
        ent.texture = tex

    @staticmethod
    def _set_shader_if_changed(ent: Entity, sh) -> None:
        """Avoid setShader + default_input churn every frame (major cost when hiring many heroes)."""
        if getattr(ent, "_shader", None) is sh:
            return
        ent.shader = sh

    @staticmethod
    def _sync_billboard_entity(
        ent: Entity,
        *,
        tex,
        tint_col,
        scale_xyz: tuple[float, float, float],
        pos_xyz: tuple[float, float, float],
        shader,
    ) -> None:
        """Position every frame; avoid re-setting billboard/scale/shader when unchanged (Ursina churn)."""
        UrsinaRenderer._set_texture_if_changed(ent, tex)
        ent.color = color.white if tex is not None else tint_col
        if getattr(ent, "_ks_last_scale", None) != scale_xyz:
            ent.scale = scale_xyz
            ent._ks_last_scale = scale_xyz
        if not getattr(ent, "_billboard", False):
            ent.billboard = True
        UrsinaRenderer._set_shader_if_changed(ent, shader)
        ent.position = pos_xyz

    def _get_or_create_entity(
        self,
        sim_obj,
        *,
        model="cube",
        col=color.white,
        scale=(1, 1, 1),
        rotation=(0, 0, 0),
        texture=None,
        billboard=False,
    ):
        obj_id = id(sim_obj)
        if obj_id not in self._entities:
            kw = dict(
                model=model,
                color=col,
                scale=scale,
                rotation=rotation,
                billboard=billboard,
            )
            if texture is not None:
                kw["texture"] = texture
            ent = Entity(**kw)
            if billboard:
                self._apply_pixel_billboard_settings(ent)
                ent._ks_billboard_configured = True
            self._entities[obj_id] = ent
        return self._entities[obj_id], obj_id

    @staticmethod
    def _apply_lit_3d_building_settings(ent: Entity) -> None:
        """Lit meshes use the same shader as world geometry (lit + shadows), not sprite_unlit."""
        from panda3d.core import TransparencyAttrib

        ent.billboard = False
        _shadows = bool(getattr(config, "URSINA_DIRECTIONAL_SHADOWS", False))
        ent.shader = lit_with_shadows_shader if _shadows else unlit_shader
        ent.double_sided = True
        ent.render_queue = 1
        ent.collision = False
        try:
            ent.setTransparency(TransparencyAttrib.M_none)
        except Exception:
            pass
        ent.set_depth_test(True)
        ent.set_depth_write(True)

    def _get_or_create_3d_building_entity(
        self, sim_obj, model_path: str, col
    ) -> tuple:
        """Replace a prior billboard entity for the same sim object if switching render mode."""
        import ursina as u

        obj_id = id(sim_obj)
        if obj_id in self._entities:
            ent = self._entities[obj_id]
            if getattr(ent, "_ks_building_mode", None) != "mesh_3d":
                u.destroy(ent)
                del self._entities[obj_id]
            elif getattr(ent, "_ks_mesh_model_path", None) != model_path:
                u.destroy(ent)
                del self._entities[obj_id]

        if obj_id not in self._entities:
            ent = Entity(
                model=model_path,
                color=col,
                collider=None,
                double_sided=True,
            )
            ent._ks_building_mode = "mesh_3d"
            ent._ks_mesh_model_path = model_path
            ent._ks_billboard_configured = False
            self._apply_lit_3d_building_settings(ent)
            self._entities[obj_id] = ent
        return self._entities[obj_id], obj_id

    @staticmethod
    def _sync_3d_building_entity(
        ent: Entity,
        *,
        mesh_kind: str,
        model_path: str,
        wx: float,
        wz: float,
        fx: float,
        fz: float,
        hy: float,
        tint_col,
        state: str,
    ) -> None:
        """Position/scale lit mesh to footprint; sim-agnostic (render only)."""
        UrsinaRenderer._set_texture_if_changed(ent, None)
        scale_xyz = _footprint_scale_3d(mesh_kind, fx, fz, hy)
        if getattr(ent, "_ks_last_scale", None) != scale_xyz:
            ent.scale = scale_xyz
            ent._ks_last_scale = scale_xyz
        _sx, sy, _sz = scale_xyz
        oy = _building_3d_origin_y(model_path, sy)
        ent.position = (wx, oy, wz)
        _shadows = bool(getattr(config, "URSINA_DIRECTIONAL_SHADOWS", False))
        want_shader = lit_with_shadows_shader if _shadows else unlit_shader
        UrsinaRenderer._set_shader_if_changed(ent, want_shader)
        if state == "damaged":
            ent.color = color.rgb(0.78, 0.42, 0.42)
        elif state == "construction":
            ent.color = color.rgb(0.72, 0.72, 0.65)
        else:
            ent.color = tint_col

    def _get_or_create_prefab_building_entity(
        self, sim_obj, prefab_path: Path, col
    ) -> tuple:
        """WK30: multi-piece prefab root for any building type.

        Replaces a prior billboard / static-mesh / mismatched-prefab entity for the same
        sim object so mode switches (env flag flipped, prefab added/removed at runtime,
        building type churn) destroy + rebuild cleanly.
        """
        import ursina as u

        obj_id = id(sim_obj)
        if obj_id in self._entities:
            ent = self._entities[obj_id]
            if getattr(ent, "_ks_building_mode", None) != "prefab" or getattr(
                ent, "_ks_prefab_path", None
            ) != str(prefab_path):
                u.destroy(ent)
                del self._entities[obj_id]

        if obj_id not in self._entities:
            root = _load_prefab_instance(prefab_path, Vec3(0, 0, 0))
            root.color = col
            root._ks_building_mode = "prefab"
            root._ks_prefab_path = str(prefab_path)
            root.collision = False
            self._entities[obj_id] = root
        return self._entities[obj_id], obj_id

    @staticmethod
    def _sync_prefab_building_entity(
        ent: Entity,
        *,
        mesh_kind: str,
        wx: float,
        wz: float,
        fx: float,
        fz: float,
        hy: float,
        tint_col,
        state: str,
    ) -> None:
        """WK30 fit-scale: map authored prefab extent to the sim footprint (XZ only).

        ``fx`` / ``fz`` are the sim footprint extents in world units (1 unit = 1 tile).
        ``hy`` is the legacy sim-height hint; **we deliberately do not scale Y** — piece
        vertical stacking stays as authored to avoid squashing roofs / towers.

        Scale rule (WK31: anisotropic XZ for non-square sim footprints):
          effective_w = max(authored_w, spread_x + 1.0)  # 1.0 = assumed Kenney piece width
          effective_d = max(authored_d, spread_z + 1.0)
          scale_x     = (fx / max(effective_w, 1e-6)) * PREFAB_FIT_INSET
          scale_z     = (fz / max(effective_d, 1e-6)) * PREFAB_FIT_INSET

        **Why not uniform** ``min(fx/ew, fz/ed)`` on both axes: for a 3×2 building, one
        ratio is often smaller; uniform scaling under-fills the long edge (inn looked
        squeezed into ~2×2). Independent X/Z mapping fills the sim ``fx × fz`` rect.

        When the sim footprint is square and effective_w ≈ effective_d, scale_x ≈ scale_z.
        When a prefab overflows its authored footprint, the max(..) effective_* terms
        still apply; tighten piece layouts in JSON if stretching is undesirable.
        """
        UrsinaRenderer._set_texture_if_changed(ent, None)
        authored_w, authored_d = getattr(ent, "_ks_prefab_authored_ft", (1.0, 1.0))
        spread_x, spread_z = getattr(ent, "_ks_prefab_xz_spread", (0.0, 0.0))
        effective_w = max(float(authored_w), float(spread_x) + 1.0)
        effective_d = max(float(authored_d), float(spread_z) + 1.0)
        scale_x = (fx / max(effective_w, 1e-6)) * _PREFAB_FIT_INSET
        scale_z = (fz / max(effective_d, 1e-6)) * _PREFAB_FIT_INSET
        scale_xyz = (scale_x, 1.0, scale_z)
        if getattr(ent, "_ks_last_scale", None) != scale_xyz:
            ent.scale = scale_xyz
            ent._ks_last_scale = scale_xyz
        ga = float(getattr(ent, "_ks_ground_anchor_y", 0.0))
        ent.position = (wx, ga, wz)
        if state == "damaged":
            ent.color = color.rgb(0.78, 0.42, 0.42)
        elif state == "construction":
            ent.color = color.rgb(0.72, 0.72, 0.65)
        else:
            ent.color = tint_col

    def update(self):
        """Called every frame by the Ursina app loop."""
        try:
            from game.types import HeroClass
        except Exception:
            HeroClass = None

        if (
            not self._shadow_bounds_initialized
            and self._directional_light is not None
        ):
            try:
                self._directional_light.update_bounds(scene)
            except Exception:
                pass
            self._shadow_bounds_initialized = True

        self._build_3d_terrain()
        self._ensure_fog_overlay()
        self._sync_visibility_gated_terrain()
        self._ensure_grid_debug_overlay()

        gs = self.engine.get_game_state()

        active_ids = set()

        # Buildings — billboard quads, except castle / house / lair (v1.5 Sprint 2.1: lit 3D meshes).
        for b in gs["buildings"]:
            bt_raw = getattr(b, "building_type", "") or ""
            bts = _building_type_str(bt_raw)
            is_castle = bts == "castle"
            is_lair = hasattr(b, "stash_gold")
            if is_castle:
                col = COLOR_CASTLE
            elif is_lair:
                col = COLOR_LAIR
            else:
                col = COLOR_BUILDING

            tw, th = _footprint_tiles(bt_raw)
            fx = b.width / SCALE
            fz = b.height / SCALE
            hy = _building_height_y(tw, th, bt_raw, is_lair, is_castle)

            state = "construction" if not getattr(b, "is_constructed", True) else "built"
            if getattr(b, "hp", 200) < getattr(b, "max_hp", 200) * 0.4:
                state = "damaged"

            wx, wz = sim_px_to_world_xz(b.x, b.y)

            # WK30: prefab path wins over static mesh / billboard for any building_type with
            # a resolvable prefab JSON. Lairs and env opt-out are handled inside the resolver.
            # WK32: swap JSON by construction_progress (plots + intermediates + fallback).
            prefab_path = _resolve_prefab_path(bts, b)
            if prefab_path is not None:
                staged = _resolve_construction_staged_prefab(b, prefab_path, tw, th)
                ent, obj_id = self._get_or_create_prefab_building_entity(
                    b, staged, col
                )
                self._sync_prefab_building_entity(
                    ent,
                    mesh_kind=bts,
                    wx=wx,
                    wz=wz,
                    fx=fx,
                    fz=fz,
                    hy=hy,
                    tint_col=col,
                    state=state,
                )
                active_ids.add(obj_id)
                continue

            if _is_3d_mesh_building(bts, b):
                mesh_kind = _mesh_kind_for_building(bts, b)
                model_path = _environment_model_path(mesh_kind)
                ent, obj_id = self._get_or_create_3d_building_entity(b, model_path, col)
                self._sync_3d_building_entity(
                    ent,
                    mesh_kind=mesh_kind,
                    model_path=model_path,
                    wx=wx,
                    wz=wz,
                    fx=fx,
                    fz=fz,
                    hy=hy,
                    tint_col=col,
                    state=state,
                )
                active_ids.add(obj_id)
                continue

            bw = max(1, int(b.width))
            bh = max(1, int(b.height))
            b_surf = BuildingSpriteLibrary.get(bts, state, size_px=(bw, bh))
            b_tex = (
                TerrainTextureBridge.surface_to_texture(
                    b_surf, cache_key=("bld", bts, state, bw, bh)
                )
                if b_surf
                else None
            )

            # Facade width ≈ larger footprint edge; one textured face (no cube "roof" duplicate).
            face_w = max(fx, fz)
            ent, obj_id = self._get_or_create_entity(
                b,
                model="quad",
                col=col,
                scale=(face_w, hy, 1),
                billboard=True,
            )
            if not getattr(ent, "_ks_billboard_configured", False):
                ent.model = "quad"
                ent.billboard = True
                self._apply_pixel_billboard_settings(ent)
                ent._ks_billboard_configured = True
            # Do not assign ent.model every frame — model_setter reloads the mesh (WK22 R2).
            ent.rotation = (0, 0, 0)
            self._sync_billboard_entity(
                ent,
                tex=b_tex if b_tex is not None else None,
                tint_col=col,
                scale_xyz=(face_w, hy, 1),
                pos_xyz=(wx, hy * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        # Heroes — pixel billboards (WK22 R3: walk/idle/inside + attack/hurt from _render_anim_trigger)
        for h in gs["heroes"]:
            if not getattr(h, "is_alive", True):
                continue
            col = COLOR_HERO
            if HeroClass:
                hc = getattr(h, "hero_class", None)
                if hc == HeroClass.RANGER or str(hc).lower() == "ranger":
                    col = color.lime
                elif hc == HeroClass.WIZARD or str(hc).lower() == "wizard":
                    col = color.magenta
                elif hc == HeroClass.ROGUE or str(hc).lower() == "rogue":
                    col = color.violet

            hc_key = str(getattr(h, "hero_class", "warrior") or "warrior").lower()
            clips_h = HeroSpriteLibrary.clips_for(hc_key, size=int(config.TILE_SIZE))
            sy = UNIT_BILLBOARD_SCALE
            ent, obj_id = self._get_or_create_entity(
                h,
                model="quad",
                col=color.white,
                scale=(sy, sy, 1),
                texture=None,
                billboard=True,
            )
            hsurf, h_cache_key = self._unit_anim_surface(
                obj_id, h, clips_h, _hero_base_clip, "hero", hc_key
            )
            htex = TerrainTextureBridge.surface_to_texture(hsurf, cache_key=h_cache_key)
            wx, wz = sim_px_to_world_xz(h.x, h.y)
            y_center = sy * 0.5
            self._sync_billboard_entity(
                ent,
                tex=htex,
                tint_col=col,
                scale_xyz=(sy, sy, 1),
                pos_xyz=(wx, y_center, wz),
                shader=sprite_unlit_shader,
            )
            # Layer compositing (not Y offset): draw after building billboards; skip depth so the
            # "inside" bubble paints over the same footprint as the façade.
            self._sync_inside_hero_draw_layer(ent, bool(getattr(h, "is_inside_building", False)))
            active_ids.add(obj_id)

        # Enemies — billboards (same animation contract as pygame EnemyRenderer)
        world = self.engine.world
        ts = float(config.TILE_SIZE)
        for e in gs["enemies"]:
            tx, ty = int(e.x / ts), int(e.y / ts)
            is_visible = True
            if 0 <= ty < world.height and 0 <= tx < world.width:
                is_visible = (world.visibility[ty][tx] == Visibility.VISIBLE)
            
            if not getattr(e, "is_alive", True) or not is_visible:
                continue
            s = ENEMY_SCALE
            col = COLOR_ENEMY
            et_key = str(getattr(e, "enemy_type", "goblin") or "goblin").lower()
            clips_e = EnemySpriteLibrary.clips_for(et_key, size=int(config.TILE_SIZE))
            ent, obj_id = self._get_or_create_entity(
                e,
                model="quad",
                col=color.white,
                scale=(s, s, 1),
                texture=None,
                billboard=True,
            )
            esurf, e_cache_key = self._unit_anim_surface(
                obj_id, e, clips_e, _enemy_base_clip, "enemy", et_key
            )
            etex = TerrainTextureBridge.surface_to_texture(esurf, cache_key=e_cache_key)
            wx, wz = sim_px_to_world_xz(e.x, e.y)
            self._sync_billboard_entity(
                ent,
                tex=etex,
                tint_col=col,
                scale_xyz=(s, s, 1),
                pos_xyz=(wx, s * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        # Peasants — billboards
        for p in gs["peasants"]:
            if not getattr(p, "is_alive", True):
                continue
            s = PEASANT_SCALE
            col = COLOR_PEASANT
            psurf = _worker_idle_surface("peasant")
            ptex = TerrainTextureBridge.surface_to_texture(
                psurf, cache_key=("worker_idle", "peasant", int(config.TILE_SIZE))
            )
            ent, obj_id = self._get_or_create_entity(
                p,
                model="quad",
                col=color.white,
                scale=(s, s, 1),
                texture=ptex,
                billboard=True,
            )
            wx, wz = sim_px_to_world_xz(p.x, p.y)
            self._sync_billboard_entity(
                ent,
                tex=ptex,
                tint_col=col,
                scale_xyz=(s, s, 1),
                pos_xyz=(wx, s * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        # Guards — billboards
        for g in gs["guards"]:
            if not getattr(g, "is_alive", True):
                continue
            col = COLOR_GUARD
            gsurf = _worker_idle_surface("guard")
            gtex = TerrainTextureBridge.surface_to_texture(
                gsurf, cache_key=("worker_idle", "guard", int(config.TILE_SIZE))
            )
            sxz = GUARD_SCALE_XZ
            sy = GUARD_SCALE_Y
            ent, obj_id = self._get_or_create_entity(
                g,
                model="quad",
                col=color.white,
                scale=(sxz, sy, 1),
                texture=gtex,
                billboard=True,
            )
            wx, wz = sim_px_to_world_xz(g.x, g.y)
            self._sync_billboard_entity(
                ent,
                tex=gtex,
                tint_col=col,
                scale_xyz=(sxz, sy, 1),
                pos_xyz=(wx, sy * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        # Tax Collectors — billboards (get_game_state may omit tax_collectors; fall back to engine singleton)
        _tc_list = gs.get("tax_collectors")
        if not _tc_list:
            _singleton = getattr(self.engine, "tax_collector", None)
            _tc_list = [_singleton] if _singleton is not None else []
        for tc in _tc_list:
            if not getattr(tc, "is_alive", True):
                continue
            col = COLOR_PEASANT
            tcsurf = _worker_idle_surface("tax_collector")
            tctex = TerrainTextureBridge.surface_to_texture(
                tcsurf, cache_key=("worker_idle", "tax_collector", int(config.TILE_SIZE))
            )
            s = PEASANT_SCALE
            ent, obj_id = self._get_or_create_entity(
                tc,
                model="quad",
                col=color.white,
                scale=(s, s, 1),
                texture=tctex,
                billboard=True,
            )
            wx, wz = sim_px_to_world_xz(tc.x, tc.y)
            self._sync_billboard_entity(
                ent,
                tex=tctex,
                tint_col=col,
                scale_xyz=(s, s, 1),
                pos_xyz=(wx, s * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        # Projectiles — VFX arrows as textured billboards (WK5 colors via get_projectile_billboard_surface)
        if self._projectile_tex is None:
            psurf = get_projectile_billboard_surface()
            self._projectile_tex = TerrainTextureBridge.surface_to_texture(
                psurf, cache_key=("ursina", "projectile_arrow_billboard_v1")
            )
        ptex = self._projectile_tex
        vfx = getattr(self.engine, "vfx_system", None)
        for proj in gs.get("projectiles") or (
            vfx.get_active_projectiles() if vfx is not None else []
        ):
            s = PROJECTILE_BILLBOARD_SCALE
            ent, obj_id = self._get_or_create_entity(
                proj,
                model="quad",
                col=color.white,
                scale=(s, s, 1),
                texture=ptex,
                billboard=True,
            )
            if not getattr(ent, "_ks_billboard_configured", False):
                ent.model = "quad"
                ent.billboard = True
                self._apply_pixel_billboard_settings(ent)
                ent._ks_billboard_configured = True
            wx, wz = sim_px_to_world_xz(proj.x, proj.y)
            self._sync_billboard_entity(
                ent,
                tex=ptex,
                tint_col=color.white,
                scale_xyz=(s, s, 1),
                pos_xyz=(wx, s * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        heroes_alive = len([h for h in gs["heroes"] if getattr(h, "is_alive", True)])
        enemies_alive = len(gs["enemies"])
        status_text = (
            f"Gold: {gs['gold']}  |  Heroes: {heroes_alive}  |  "
            f"Enemies: {enemies_alive}  |  Buildings: {len(gs['buildings'])}"
        )
        if self.status_text.text != status_text:
            self.status_text.text = status_text

        dead_ids = set(self._entities.keys()) - active_ids
        for obj_id in dead_ids:
            self._unit_anim_state.pop(obj_id, None)
            ent = self._entities.pop(obj_id)
            import ursina

            ursina.destroy(ent)
