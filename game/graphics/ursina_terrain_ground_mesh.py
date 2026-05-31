"""Terrain ground-surface mesh, grass texture, and cave-entrance shader for the Ursina renderer (WK107 slice of ursina_terrain_fog_collab.py).

Extracted VERBATIM from game/graphics/ursina_terrain_fog_collab.py:
_build_terrain_ground_mesh (heightmap-displaced mesh / GeoMipTerrain LOD / flat
fallback), update_cave_entrance_shader (feature-gated, early-returns), and
_apply_grass_texture (albedo load + tiling) — as owner-arg module functions. The
owner is UrsinaTerrainFogCollab, reached via owner._r.* (parent UrsinaRenderer
state: _terrain_ground_entity, _geomip_terrain_handle, _ks_ground_tex).
UrsinaTerrainFogCollab keeps 1-line delegating wrappers (same names+signatures) so
build_3d_terrain's `self._build_terrain_ground_mesh(...)` call and any external
`update_cave_entrance_shader` caller are unchanged.

Acyclic: imports only leaf graphics/config modules + ursina/ursina.shaders at top;
imports UrsinaTerrainFogCollab ONLY under TYPE_CHECKING. ursina_terrain_fog_collab.py
imports THIS module LAZILY inside the wrapper bodies (one-way edge).
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

import config
from ursina import Entity, Vec2, color
from ursina.shaders import unlit_shader

from game.graphics.terrain_fog_shader import terrain_fog_shader
from game.graphics.ursina_coords import sim_px_to_world_xz
from game.graphics.ursina_environment import PROJECT_ROOT

if TYPE_CHECKING:
    from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab


def _build_terrain_ground_mesh(
    owner, root, world, tw: int, th: int, ts: int,
    w_world: float, d_world: float, has_heightmap: bool,
) -> None:
    """Build the ground: heightmap-displaced indexed triangle mesh, or flat quad fallback.

    The mesh uses the world heightmap at 2x sub-tile resolution. Each vertex's Y is
    sampled from the heightmap. UVs tile the grass texture matching the existing
    texture_scale. Per-vertex normals are computed from adjacent height samples.

    WK53 R3: The terrain mesh uses terrain_fog_shader which samples both the grass
    albedo and a fog-of-war texture in a single draw call. The fog texture is uploaded
    as a shader uniform by ensure_fog_overlay() each time visibility changes.

    WK58 W8 (Agent 03, Section 4.C): When ``KINGDOM_URSINA_GEOMIPTERRAIN=1`` is set
    AND a heightmap is available, build Panda3D's ``GeoMipTerrain`` with
    distance-based LOD instead of the static 62,500-vert custom Mesh. Both code
    paths populate ``self._r._terrain_ground_entity`` so the fog-shader uniform
    upload in ``ensure_fog_overlay`` works identically. ``get_terrain_height``
    keeps reading from the source-of-truth Perlin array via the ``terrain_height``
    module — display mesh choice does NOT affect prop / unit / building Y.
    """
    import math as _math

    from game.graphics.terrain_height import get_terrain_height

    cx_px = tw * ts * 0.5
    cy_px = th * ts * 0.5

    hmap = getattr(world, "heightmap", None)
    gw = getattr(world, "heightmap_grid_w", 0)
    gh = getattr(world, "heightmap_grid_h", 0)

    # --- WK58 W8 / 4.C: GeoMipTerrain LOD path (env-flag gated) -----------
    # When KINGDOM_URSINA_GEOMIPTERRAIN=1 we use Panda3D's GeoMipTerrain
    # for distance-based LOD on zoom-out. Falls through to the custom Mesh
    # path on any error (env=1 silently degrades to env=0 — the custom
    # Mesh remains the always-available implementation).
    if has_heightmap and hmap is not None and gw >= 2 and gh >= 2:
        try:
            from game.graphics.terrain_geomipterrain import (
                geomipterrain_enabled,
                build_geomip_terrain,
            )
            if geomipterrain_enabled():
                height_scale = float(getattr(config, "TERRAIN_HEIGHT_SCALE", 8.0))
                handle = build_geomip_terrain(
                    parent_entity=root,
                    hmap=hmap,
                    gw=int(gw),
                    gh=int(gh),
                    tw=int(tw),
                    th=int(th),
                    world_w=float(w_world),
                    world_d=float(d_world),
                    height_scale=height_scale,
                    tiles_per_repeat=2.0,
                )
                if handle is not None:
                    # ``ensure_fog_overlay`` targets ``_terrain_ground_entity``;
                    # set it to the wrap Entity so the fog texture lands on
                    # the same NodePath the shader is bound to.
                    owner._r._terrain_ground_entity = handle.wrap_entity
                    # Renderer reads ``_geomip_terrain_handle`` once per
                    # frame and calls ``update_lod()``. ``__init__`` of
                    # UrsinaRenderer pre-declares None.
                    setattr(owner._r, "_geomip_terrain_handle", handle)
                    return
        except Exception:
            # Fall through to custom mesh path on any GeoMipTerrain failure.
            pass

    if not has_heightmap or hmap is None or gw < 2 or gh < 2:
        # Flat fallback — identical to old ground plane
        base_wx, base_wz = sim_px_to_world_xz(cx_px, cy_px)
        ground_ent = Entity(
            parent=root,
            model="quad",
            color=color.white,
            scale=(w_world, d_world, 1),
            rotation=(90, 0, 0),
            position=(base_wx, -0.05, base_wz),
            collision=False,
            double_sided=True,
            shader=unlit_shader,
            add_to_scene_entities=False,
        )
        _apply_grass_texture(owner, ground_ent, tw, th)
        return

    # --- Heightmap-displaced mesh ---
    try:
        from ursina import Mesh
    except ImportError:
        return

    # Step sizes in world units per grid cell
    dx_world = w_world / (gw - 1)
    dz_world = d_world / (gh - 1)

    # Build vertex list and UV list
    verts: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    norms: list[tuple[float, float, float]] = []

    # Texture tiling: match existing tiles_per_repeat=2.0
    tiles_per_repeat = 2.0
    try:
        raw = os.environ.get("KINGDOM_URSINA_GROUND_TEX_TILES_PER_REPEAT", "").strip()
        if raw:
            tiles_per_repeat = max(0.25, float(raw))
    except Exception:
        tiles_per_repeat = 2.0

    for gz in range(gh):
        for gx in range(gw):
            # World position: X = gx * dx_world, Z = -(gh-1-gz) * dz_world
            # Grid row 0 is sim-row 0 (top of map) which is the most-negative Z
            wx = gx * dx_world
            wz = -(gh - 1 - gz) * dz_world
            wy = hmap[gz][gx]
            verts.append((wx, wy, wz))

            # UV: tile the texture
            tile_x = gx / 2.0  # grid cell -> tile coord
            tile_z = gz / 2.0
            u = tile_x / tiles_per_repeat
            v = tile_z / tiles_per_repeat
            uvs.append((u, v))

    # Per-vertex normals from adjacent height samples
    for gz in range(gh):
        for gx in range(gw):
            # Sample neighbors (clamped)
            gx0 = max(0, gx - 1)
            gx1 = min(gw - 1, gx + 1)
            gz0 = max(0, gz - 1)
            gz1 = min(gh - 1, gz + 1)

            hL = hmap[gz][gx0]
            hR = hmap[gz][gx1]
            hD = hmap[gz0][gx]
            hU = hmap[gz1][gx]

            # Tangent vectors (unnormalized)
            sx = (gx1 - gx0) * dx_world
            sz = (gz1 - gz0) * dz_world
            # Normal = cross(tangent_x, tangent_z)
            # tangent_x = (sx, hR-hL, 0), tangent_z = (0, hU-hD, sz)
            nx = -(hR - hL) * sz
            ny = sx * sz
            nz = -(hU - hD) * sx
            ln = _math.sqrt(nx * nx + ny * ny + nz * nz)
            if ln > 1e-8:
                nx /= ln
                ny /= ln
                nz /= ln
            else:
                nx, ny, nz = 0.0, 1.0, 0.0
            norms.append((nx, ny, nz))

    # Build triangle indices (two triangles per quad cell)
    triangles: list[int] = []
    for gz in range(gh - 1):
        for gx in range(gw - 1):
            i00 = gz * gw + gx
            i10 = gz * gw + gx + 1
            i01 = (gz + 1) * gw + gx
            i11 = (gz + 1) * gw + gx + 1
            # Triangle 1
            triangles.extend([i00, i01, i10])
            # Triangle 2
            triangles.extend([i10, i01, i11])

    terrain_mesh = Mesh(
        vertices=verts,
        triangles=triangles,
        uvs=uvs,
        normals=norms,
        mode="triangle",
    )

    ground_ent = Entity(
        parent=root,
        model=terrain_mesh,
        color=color.white,
        collision=False,
        double_sided=True,
        shader=terrain_fog_shader,
        add_to_scene_entities=False,
    )
    _apply_grass_texture(owner, ground_ent, tw, th, use_texture_scale=False)

    # WK53 R3: Set fog UV transform so the shader can derive fog-of-war UVs from
    # the tiled grass UVs. fog_uv = grass_uv * fog_uv_scale + fog_uv_offset maps
    # tiled UVs back to [0,1] across the full map extent, with N/S flip.
    fog_uv_sx = tiles_per_repeat / float(tw) if tw > 0 else 1.0
    fog_uv_sy = -tiles_per_repeat / float(th) if th > 0 else -1.0
    ground_ent.set_shader_input("fog_uv_scale", Vec2(fog_uv_sx, fog_uv_sy))
    ground_ent.set_shader_input("fog_uv_offset", Vec2(0.0, 1.0))

    # Store reference so ensure_fog_overlay can upload the fog texture to this entity.
    owner._r._terrain_ground_entity = ground_ent


def update_cave_entrance_shader(owner, pois, map_width, map_height):
    """Upload discovered cave/mine entrance positions to the terrain shader.

    Converts POI grid positions to fog UV space [0,1] and sets shader uniforms.
    Call this whenever POI discovery state changes.
    """
    # FEATURE GATE: underground visuals disabled — shader defaults (radius=0,
    # entrances at 99,99) already produce no holes, so just skip the update.
    return

    ground_ent = getattr(owner._r, '_terrain_ground_entity', None)
    if ground_ent is None:
        return

    from config import UNDERGROUND_HOLE_RADIUS_TILES, UNDERGROUND_HOLE_EDGE_TILES

    entrances = []
    for poi in pois:
        poi_def = getattr(poi, 'poi_def', None)
        if poi_def is None:
            continue
        if poi_def.interaction_type != 'dungeon':
            continue
        if not getattr(poi, 'is_discovered', False):
            continue
        size = poi_def.size
        cx = poi.grid_x + size[0] / 2.0
        cy = poi.grid_y + size[1] / 2.0
        # Convert to fog UV space: x/map_width, 1 - y/map_height (Y is flipped)
        uv_x = cx / map_width
        uv_y = 1.0 - (cy / map_height)
        entrances.append((uv_x, uv_y))
        if len(entrances) >= 8:
            break

    for i in range(8):
        if i < len(entrances):
            ground_ent.set_shader_input(f"cave_entrance_{i}", Vec2(*entrances[i]))
        else:
            ground_ent.set_shader_input(f"cave_entrance_{i}", Vec2(99.0, 99.0))

    if entrances:
        hole_r = UNDERGROUND_HOLE_RADIUS_TILES / max(map_width, map_height)
        edge_w = UNDERGROUND_HOLE_EDGE_TILES / max(map_width, map_height)
        ground_ent.set_shader_input("cave_hole_radius", hole_r)
        ground_ent.set_shader_input("cave_edge_width", edge_w)
    else:
        ground_ent.set_shader_input("cave_hole_radius", 0.0)
        ground_ent.set_shader_input("cave_edge_width", 0.0)


def _apply_grass_texture(owner, ground_ent, tw: int, th: int, use_texture_scale: bool = True) -> None:
    """Load and apply the grass albedo texture to a ground entity."""
    try:
        from ursina import Texture
        from PIL import Image

        if getattr(owner._r, "_ks_ground_tex", None) is None:
            p = (
                PROJECT_ROOT
                / "assets"
                / "models"
                / "Models"
                / "Textures"
                / "floor_ground_grass.png"
            )
            if p.is_file():
                img = Image.open(p).convert("RGBA")
                owner._r._ks_ground_tex = Texture(img, filtering=None)
            else:
                owner._r._ks_ground_tex = None

        if owner._r._ks_ground_tex is not None:
            ground_ent.texture = owner._r._ks_ground_tex
            if use_texture_scale:
                tiles_per_repeat = 2.0
                try:
                    raw = os.environ.get("KINGDOM_URSINA_GROUND_TEX_TILES_PER_REPEAT", "").strip()
                    if raw:
                        tiles_per_repeat = max(0.25, float(raw))
                except Exception:
                    tiles_per_repeat = 2.0
                ground_ent.texture_scale = Vec2(float(tw) / tiles_per_repeat, float(th) / tiles_per_repeat)
    except Exception:
        pass
