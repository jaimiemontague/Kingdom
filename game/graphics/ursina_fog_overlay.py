"""Fog-of-war overlay + grid-debug overlay for the Ursina terrain renderer (WK109 slice of ursina_terrain_fog_collab.py).

Extracted VERBATIM from game/graphics/ursina_terrain_fog_collab.py:
ensure_fog_overlay (per-frame fog texture build + GPU upload; heightmap-shader-uniform
path + legacy fog-quad fallback) and ensure_grid_debug_overlay (KINGDOM_URSINA_GRID_DEBUG
visualization) — as owner-arg module functions. The owner is UrsinaTerrainFogCollab,
reached EXCLUSIVELY via owner._r.* (parent UrsinaRenderer state). Neither function reads
or writes any owner __slots__ member other than owner._r, and they make no intra-class
calls. UrsinaTerrainFogCollab keeps 1-line delegating wrappers (same names+signatures) so
ursina_renderer.py:584/591 are unchanged.

Acyclic: imports leaf graphics/config/world modules + ursina/ursina.shaders + pygame at
top (panda3d kept function-local); imports UrsinaTerrainFogCollab ONLY under TYPE_CHECKING.
ursina_terrain_fog_collab.py imports THIS module LAZILY inside the 2 wrapper bodies.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pygame
import config
from ursina import Entity, Vec2, color
from ursina.shaders import unlit_shader

from game.graphics.terrain_texture_bridge import TerrainTextureBridge
from game.graphics.ursina_coords import SCALE, sim_px_to_world_xz
from game.graphics.ursina_scene_ignore import mark_scene_ignore
from game.world import Visibility

if TYPE_CHECKING:
    from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab

FOG_TEX_BRIDGE_KEY = "kingdom_ursina_fog_overlay"


def ensure_fog_overlay(owner, world, fog_revision: int) -> None:
    """Darken unexplored / non-visible tiles in 3D (matches 2D render_fog semantics).

    WK22: Rebuild only when ``engine._fog_revision`` advances (revealer crossed a tile).

    WK23 follow-up: removed throttle; removed CRC skip path; advance ``_fog_revision_seen`` only
    after a successful GPU upload. In perspective, this quad is ground fog only; vertical
    props are separately gated by tile visibility so camera angle cannot make them leak.
    """
    if owner._r._terrain_entity is None:
        return
    my_rev = getattr(owner._r, "_fog_revision_seen", -1)
    # WK58 W6 Fix 1.A (Agent 03): the early-out previously required
    # ``_fog_entity is not None`` which is correct only for the legacy flat-
    # terrain fog quad. The WK53 heightmap shader-uniform path destroys
    # ``_fog_entity`` (see :345-351 below) and applies the fog texture as a
    # ``fog_texture`` shader input on ``_terrain_ground_entity`` instead.
    # Without recognising that path the early-out was always False on the
    # heightmap build, so the 62,500-tile Python loop + GPU upload ran
    # every frame even when ``fog_revision`` had not advanced. Accept the
    # heightmap path by also checking ``_terrain_ground_entity``; this
    # restores the intended "rebuild only when revealer crosses a tile"
    # behaviour. Wave-5 profile: lifts post-reveal FPS ~18 -> ~32-38.
    terrain_ground_ent = getattr(owner._r, "_terrain_ground_entity", None)
    if int(fog_revision) == my_rev and (
        owner._r._fog_entity is not None or terrain_ground_ent is not None
    ):
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
    if owner._r._fog_tile_buf is None or len(owner._r._fog_tile_buf) != need:
        owner._r._fog_tile_buf = bytearray(need)
    buf = owner._r._fog_tile_buf
    # WK53 R1: UNSEEN fog is dark charcoal mist instead of black — (0.2, 0.2, 0.23) * 255.
    # Dark enough to clearly hide unexplored territory, but reads as mist not void.
    _unseen_r, _unseen_g, _unseen_b = 51, 51, 58  # ~(0.2, 0.2, 0.23)
    row_unseen = bytes((_unseen_r, _unseen_g, _unseen_b, 0xFF)) * tw
    for ty in range(th):
        buf[ty * tw * 4 : (ty + 1) * tw * 4] = row_unseen
    vis_b = b"\x00\x00\x00\x00"
    # WK53 R1: SEEN overlay uses the same charcoal mist as UNSEEN but at lower alpha
    # so explored-but-not-visible areas are tinted, not fully hidden.
    _seen_r, _seen_g, _seen_b = 51, 51, 58  # same as UNSEEN — (0.2, 0.2, 0.23)
    try:
        seen_a = int(getattr(config, "URSINA_FOG_SEEN_ALPHA", 0x80))
    except Exception:
        seen_a = 0x80
    seen_a = max(0, min(255, int(seen_a)))
    seen_b = bytes((_seen_r, _seen_g, _seen_b, seen_a))
    # WK23 FIX: write rows in REVERSE sim-Y order so the texture's row-0
    # corresponds to map-south (sim_py == th*ts).  sim_px_to_world_xz negates
    # the Y axis (world_z = -py/SCALE), so map-south ends at world_z=0 (the
    # +Z edge of the quad after rotation_x=90°).  Without this reversal the
    # fog is mirrored North↔South and the lit circle tracks the wrong half of
    # the map relative to where heroes actually stand.
    # WK59 perf: pre-build lookup table to avoid per-tile branching in Python.
    _VIS_VAL = int(Visibility.VISIBLE)
    _SEEN_VAL = int(Visibility.SEEN)
    _pixel_lut = {_VIS_VAL: vis_b, _SEEN_VAL: seen_b}
    for ty in range(th):
        row = world.visibility[ty]
        buf_row = th - 1 - ty
        base = buf_row * tw * 4
        for tx in range(tw):
            px = _pixel_lut.get(row[tx])
            if px is not None:
                o = base + tx * 4
                buf[o : o + 4] = px

    surf = pygame.image.frombuffer(buf, (tw, th), "RGBA")
    owner._r._fog_full_surf = surf

    ftex = TerrainTextureBridge.refresh_surface_texture(surf, cache_key=FOG_TEX_BRIDGE_KEY)
    if ftex is None:
        # Do not advance _fog_revision_seen — otherwise we never retry and fog stays stale.
        return

    ts = int(config.TILE_SIZE)
    # WK23 R1: Quad size + center MUST match _build_3d_terrain() map extent — any drift
    # misaligns fog vs terrain and makes FOW "slide" relative to heroes/units.
    w_world = (tw * ts) / SCALE
    d_world = (th * ts) / SCALE
    cx_px = tw * ts * 0.5
    cy_px = th * ts * 0.5
    wx, wz = sim_px_to_world_xz(cx_px, cy_px)

    from panda3d.core import TransparencyAttrib

    # WK53 R3: Shader-based fog — when the terrain mesh exists with a heightmap,
    # apply the fog texture as a shader uniform on the terrain entity instead of
    # using a separate floating fog quad. This eliminates the gap between fog and
    # terrain that was visible from angled camera views.
    hmap = getattr(world, "heightmap", None)
    terrain_ground_ent = getattr(owner._r, "_terrain_ground_entity", None)

    if hmap is not None and terrain_ground_ent is not None:
        # Shader-based fog path: upload fog texture to the terrain mesh's shader.
        # Enable bilinear filtering for smooth mist transitions.
        if ftex is not None:
            try:
                ftex.filtering = True
            except Exception:
                pass
        # Set the fog_texture uniform on the terrain entity's Panda3D node.
        try:
            from panda3d.core import SamplerState
            np = terrain_ground_ent
            if hasattr(np, 'nodePath'):
                np = np.nodePath
            # Panda3D texture stage for the fog uniform
            _fog_ts = getattr(owner._r, "_fog_texture_stage", None)
            if _fog_ts is None:
                from panda3d.core import TextureStage
                _fog_ts = TextureStage("fog_texture")
                _fog_ts.setSort(1)
                owner._r._fog_texture_stage = _fog_ts
            # Get the Panda3D texture from Ursina texture
            p3d_tex = None
            if ftex is not None:
                if hasattr(ftex, '_texture'):
                    p3d_tex = ftex._texture
                elif hasattr(ftex, 'path'):
                    # Ursina Texture may store the Panda3D texture differently
                    try:
                        p3d_tex = terrain_ground_ent.getTexture()
                    except Exception:
                        pass
            if p3d_tex is None and ftex is not None:
                # Try the Ursina Entity setTexture approach
                try:
                    terrain_ground_ent.setShaderInput("fog_texture", ftex)
                except Exception:
                    pass
            else:
                try:
                    terrain_ground_ent.setShaderInput("fog_texture", p3d_tex)
                except Exception:
                    try:
                        terrain_ground_ent.setShaderInput("fog_texture", ftex)
                    except Exception:
                        pass

            # WK58 W8 (4.C): when the GeoMipTerrain display path is active
            # we ALSO need to push the fog_texture input directly onto the
            # GeoMipTerrain root NodePath. The wrap Entity owns the
            # ``_terrain_ground_entity`` reference and the shader, but
            # GeoMipTerrain installs its own per-block RenderState during
            # ``generate()`` and may not always inherit shader inputs set
            # on the parent transform. Mirroring the input on the root NP
            # is cheap and guarantees the fog texture is sampled in every
            # block's fragment shader.
            _gmt_handle = getattr(owner._r, "_geomip_terrain_handle", None)
            if _gmt_handle is not None:
                try:
                    _root_np = _gmt_handle.terrain.get_root()
                    if p3d_tex is not None:
                        _root_np.set_shader_input("fog_texture", p3d_tex)
                    elif ftex is not None:
                        _root_np.set_shader_input("fog_texture", ftex)
                except Exception:
                    pass
        except Exception:
            pass

        # Destroy the old fog quad if it exists — no longer needed.
        if owner._r._fog_entity is not None:
            try:
                import ursina as u
                u.destroy(owner._r._fog_entity)
            except Exception:
                pass
            owner._r._fog_entity = None

        owner._r._fog_revision_seen = int(fog_revision)
        return

    # Fallback: flat terrain (no heightmap) — use the old fog quad approach.
    fog_y = float(getattr(config, "URSINA_FOG_QUAD_Y", 0.12))

    if owner._r._fog_entity is None:
        owner._r._fog_entity = Entity(
            model="quad",
            texture=ftex,
            scale=(w_world, d_world, 1),
            rotation=(90, 0, 0),
            position=(wx, fog_y, wz),
            color=color.white,
            double_sided=True,
        )
        # WK53 R1: bilinear filtering smooths hard tile edges into gradual mist
        # transitions. The fog texture is 1px-per-tile, so GPU bilinear interpolation
        # across tile boundaries creates natural feathering — "rolling mist" not a grid.
        if owner._r._fog_entity.texture:
            owner._r._fog_entity.texture.filtering = True
        owner._r._fog_entity.texture_scale = Vec2(1, -1)
        owner._r._fog_entity.texture_offset = Vec2(0, 1)
        owner._r._fog_entity.setTransparency(TransparencyAttrib.M_alpha)
        owner._r._fog_entity.set_depth_write(False)
        # Overlay must not depth-fail against billboards/terrain or FOW darkening desyncs visually.
        owner._r._fog_entity.set_depth_test(False)
        owner._r._fog_entity.shader = unlit_shader
        owner._r._fog_entity.hide(0b0001)
        # Ground fog must render before buildings/props; vertical objects are hidden by tile visibility.
        owner._r._fog_entity.render_queue = 0
        # Mythos S1 (`scene-entities-ignore`): renderer-managed quad — no update/input.
        mark_scene_ignore(owner._r._fog_entity)
    else:
        owner._r._fog_entity.texture = ftex
        owner._r._fog_entity.position = (wx, fog_y, wz)
        owner._r._fog_entity.scale = (w_world, d_world, 1)
        owner._r._fog_entity.texture_scale = Vec2(1, -1)
        owner._r._fog_entity.texture_offset = Vec2(0, 1)
        owner._r._fog_entity.render_queue = 0

    owner._r._fog_revision_seen = int(fog_revision)


def ensure_grid_debug_overlay(owner, world, buildings) -> None:
    """WK30 debug: draw tile gridlines on the terrain when ``KINGDOM_URSINA_GRID_DEBUG=1``.

    Off by default. When enabled, renders one line-mesh Entity spanning a
    configurable square region around the castle (smaller than the full map so the
    lines read clearly from a close camera). The region size in tiles is controlled
    by ``KINGDOM_URSINA_GRID_DEBUG_TILES`` (default 20). Slightly above ``y=0`` to
    avoid z-fighting with the terrain quad.
    """
    if os.environ.get("KINGDOM_URSINA_GRID_DEBUG") != "1":
        if owner._r._grid_debug_entity is not None:
            try:
                import ursina as u

                u.destroy(owner._r._grid_debug_entity)
            except Exception:
                pass
            owner._r._grid_debug_entity = None
        return
    if owner._r._grid_debug_entity is not None:
        return
    try:
        from ursina import Mesh
    except Exception:
        return

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
            for b in (buildings or [])
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
    owner._r._grid_debug_entity = Entity(
        model=grid_mesh,
        color=color.rgba(1.0, 0.95, 0.3, 0.95),
        shader=unlit_shader,
        collider=None,
    )
    try:
        from panda3d.core import TransparencyAttrib

        owner._r._grid_debug_entity.setTransparency(TransparencyAttrib.M_alpha)
    except Exception:
        pass
    owner._r._grid_debug_entity.set_depth_write(False)
    # Render above the terrain quad but below fog and billboards.
    owner._r._grid_debug_entity.render_queue = 3
    # Mythos S1 (`scene-entities-ignore`): debug overlay — no update/input.
    mark_scene_ignore(owner._r._grid_debug_entity)
