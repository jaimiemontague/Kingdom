"""Terrain, fog overlay, grid debug (WK41 R2 collaborator)."""

from __future__ import annotations

import os
from pathlib import Path

import pygame
import config
from ursina import Entity, Vec2, Vec3, color

from game.graphics.terrain_texture_bridge import TerrainTextureBridge
from game.graphics.ursina_coords import SCALE, px_to_world, sim_px_to_world_xz
from game.graphics.terrain_fog_shader import terrain_fog_shader
from game.graphics.ursina_environment import (
    GROUND_PROP_FLOWER_LOG_MUSHROOM_SCALE,
    GRASS_SCATTER_SCALE_MULTIPLIER,
    PROJECT_ROOT,
    ROCK_SCALE_MULTIPLIER,
    TERRAIN_SCALE_MULTIPLIER,
    TREE_SCALE_MULTIPLIER,
    _building_occupied_tiles,
    _environment_grass_and_doodad_model_lists,
    _environment_model_path,
    _environment_tree_model_list,
    _finalize_kenney_scatter_entity,
    _grass_clump_offset,
    _grass_density_budget,
    _grass_scatter_jitter,
    _grass_tile_selected,
    _scatter_model_index,
    _set_static_prop_fog_tint,
    _stem_is_flower_ground_scatter,
    _stem_is_log_or_mushroom_ground_scatter,
)
from game.world import TileType, Visibility
from ursina.shaders import unlit_shader

FOG_TEX_BRIDGE_KEY = "kingdom_ursina_fog_overlay"


class UrsinaTerrainFogCollab:
    """Terrain root + fog quad + visibility-gated props + optional grid overlay."""

    __slots__ = ("_r",)

    def __init__(self, renderer) -> None:
        self._r = renderer

    def ensure_fog_overlay(self, world, fog_revision: int) -> None:
        """Darken unexplored / non-visible tiles in 3D (matches 2D render_fog semantics).

        WK22: Rebuild only when ``engine._fog_revision`` advances (revealer crossed a tile).

        WK23 follow-up: removed throttle; removed CRC skip path; advance ``_fog_revision_seen`` only
        after a successful GPU upload. In perspective, this quad is ground fog only; vertical
        props are separately gated by tile visibility so camera angle cannot make them leak.
        """
        if self._r._terrain_entity is None:
            return
        my_rev = getattr(self._r, "_fog_revision_seen", -1)
        if int(fog_revision) == my_rev and self._r._fog_entity is not None:
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
        if self._r._fog_tile_buf is None or len(self._r._fog_tile_buf) != need:
            self._r._fog_tile_buf = bytearray(need)
        buf = self._r._fog_tile_buf
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
        self._r._fog_full_surf = surf

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
        terrain_ground_ent = getattr(self._r, "_terrain_ground_entity", None)

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
                _fog_ts = getattr(self._r, "_fog_texture_stage", None)
                if _fog_ts is None:
                    from panda3d.core import TextureStage
                    _fog_ts = TextureStage("fog_texture")
                    _fog_ts.setSort(1)
                    self._r._fog_texture_stage = _fog_ts
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
            except Exception:
                pass

            # Destroy the old fog quad if it exists — no longer needed.
            if self._r._fog_entity is not None:
                try:
                    import ursina as u
                    u.destroy(self._r._fog_entity)
                except Exception:
                    pass
                self._r._fog_entity = None

            self._r._fog_revision_seen = int(fog_revision)
            return

        # Fallback: flat terrain (no heightmap) — use the old fog quad approach.
        fog_y = float(getattr(config, "URSINA_FOG_QUAD_Y", 0.12))

        if self._r._fog_entity is None:
            self._r._fog_entity = Entity(
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
            if self._r._fog_entity.texture:
                self._r._fog_entity.texture.filtering = True
            self._r._fog_entity.texture_scale = Vec2(1, -1)
            self._r._fog_entity.texture_offset = Vec2(0, 1)
            self._r._fog_entity.setTransparency(TransparencyAttrib.M_alpha)
            self._r._fog_entity.set_depth_write(False)
            # Overlay must not depth-fail against billboards/terrain or FOW darkening desyncs visually.
            self._r._fog_entity.set_depth_test(False)
            self._r._fog_entity.shader = unlit_shader
            self._r._fog_entity.hide(0b0001)
            # Ground fog must render before buildings/props; vertical objects are hidden by tile visibility.
            self._r._fog_entity.render_queue = 0
        else:
            self._r._fog_entity.texture = ftex
            self._r._fog_entity.position = (wx, fog_y, wz)
            self._r._fog_entity.scale = (w_world, d_world, 1)
            self._r._fog_entity.texture_scale = Vec2(1, -1)
            self._r._fog_entity.texture_offset = Vec2(0, 1)
            self._r._fog_entity.render_queue = 0

        self._r._fog_revision_seen = int(fog_revision)

    def track_visibility_gated_terrain(self, ent: Entity, tx: int, ty: int) -> None:
        """Register vertical terrain props that should disappear only in unexplored fog."""
        # Vertical props must draw after the ground-fog quad; otherwise their tops can be clipped
        # by fog that is visually behind them at shallow perspective camera angles.
        ent.render_queue = 1
        key = (int(tx), int(ty))
        self._r._visibility_gated_terrain.append((ent, key[0], key[1]))
        self._r._visibility_gated_terrain_by_tile.setdefault(key, []).append(ent)

    def untrack_visibility_gated_terrain(self, ent: Entity) -> None:
        """Remove a terrain prop from fog bookkeeping when its Entity is destroyed.

        Without this, ``sync_dynamic_trees`` / ``sync_log_stacks`` leave zombie entries in
        ``_visibility_gated_*``. Those lists grow forever and each fog revision revisits dead
        NodePaths — progressively slower FPS during longer sessions.
        """
        self._r._visibility_gated_terrain = [
            row for row in self._r._visibility_gated_terrain if row[0] is not ent
        ]
        bt = self._r._visibility_gated_terrain_by_tile
        empty_keys: list[tuple[int, int]] = []
        for key, lst in list(bt.items()):
            filtered = [e for e in lst if e is not ent]
            if filtered:
                bt[key] = filtered
            else:
                empty_keys.append(key)
        for key in empty_keys:
            bt.pop(key, None)

    def sync_terrain_prop_tile_visibility(self, ent: Entity, vis: Visibility) -> None:
        is_visible = vis != Visibility.UNSEEN
        if getattr(ent, "_ks_prop_enabled", None) is not is_visible:
            ent.enabled = bool(is_visible)
            ent._ks_prop_enabled = bool(is_visible)
        if is_visible:
            try:
                seen_mult = float(getattr(config, "URSINA_SEEN_PROP_FOG_MULT", 0.5))
            except Exception:
                seen_mult = 0.5
            _set_static_prop_fog_tint(ent, seen_mult if vis == Visibility.SEEN else 1.0)

    def sync_visibility_gated_terrain(self, world, fog_revision: int) -> None:
        """Hide tall terrain props only in UNSEEN fog so they cannot protrude into unknown territory."""
        engine_rev = int(fog_revision)
        if self._r._terrain_visibility_revision_seen == engine_rev:
            return

        current_visible = set(getattr(world, "_currently_visible", set()) or set())
        if self._r._terrain_visible_tiles_seen is None:
            for ent, tx, ty in self._r._visibility_gated_terrain:
                if 0 <= ty < world.height and 0 <= tx < world.width:
                    vis = world.visibility[ty][tx]
                else:
                    vis = Visibility.UNSEEN
                self.sync_terrain_prop_tile_visibility(ent, vis)
        else:
            changed_tiles = self._r._terrain_visible_tiles_seen ^ current_visible
            for tx, ty in changed_tiles:
                ents = self._r._visibility_gated_terrain_by_tile.get((int(tx), int(ty)))
                if not ents:
                    continue
                if 0 <= ty < world.height and 0 <= tx < world.width:
                    vis = world.visibility[ty][tx]
                else:
                    vis = Visibility.UNSEEN
                for ent in ents:
                    self.sync_terrain_prop_tile_visibility(ent, vis)
        self._r._terrain_visible_tiles_seen = current_visible
        self._r._terrain_visibility_revision_seen = engine_rev

    def ensure_grid_debug_overlay(self, world, buildings) -> None:
        """WK30 debug: draw tile gridlines on the terrain when ``KINGDOM_URSINA_GRID_DEBUG=1``.

        Off by default. When enabled, renders one line-mesh Entity spanning a
        configurable square region around the castle (smaller than the full map so the
        lines read clearly from a close camera). The region size in tiles is controlled
        by ``KINGDOM_URSINA_GRID_DEBUG_TILES`` (default 20). Slightly above ``y=0`` to
        avoid z-fighting with the terrain quad.
        """
        if os.environ.get("KINGDOM_URSINA_GRID_DEBUG") != "1":
            if self._r._grid_debug_entity is not None:
                try:
                    import ursina as u

                    u.destroy(self._r._grid_debug_entity)
                except Exception:
                    pass
                self._r._grid_debug_entity = None
            return
        if self._r._grid_debug_entity is not None:
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
        self._r._grid_debug_entity = Entity(
            model=grid_mesh,
            color=color.rgba(1.0, 0.95, 0.3, 0.95),
            shader=unlit_shader,
            collider=None,
        )
        try:
            from panda3d.core import TransparencyAttrib

            self._r._grid_debug_entity.setTransparency(TransparencyAttrib.M_alpha)
        except Exception:
            pass
        self._r._grid_debug_entity.set_depth_write(False)
        # Render above the terrain quad but below fog and billboards.
        self._r._grid_debug_entity.render_queue = 3

    def build_3d_terrain(self, world, buildings) -> None:
        """WK53 Wave 2: heightmap-displaced mesh + per-tile path/water + scatter props with terrain Y.

        Replaces the flat ground plane with a vertex-displaced mesh whose Y values come from
        the world's heightmap (Perlin noise, generated in World.generate_heightmap).
        Props (trees, grass, rocks, paths) are placed at the correct terrain height.
        """
        if self._r._terrain_entity is not None:
            return

        from game.graphics.terrain_height import get_terrain_height, init_heightmap, is_initialized

        tw, th = int(world.width), int(world.height)
        ts = int(config.TILE_SIZE)
        m = float(TERRAIN_SCALE_MULTIPLIER)
        grass_models, doodad_models = _environment_grass_and_doodad_model_lists()
        tree_models = _environment_tree_model_list()
        path_model = _environment_model_path("path_stone")
        rock_model = _environment_model_path("rock")
        occupied_tiles = _building_occupied_tiles(buildings)
        tm = m * float(TREE_SCALE_MULTIPLIER)
        rm = m * float(ROCK_SCALE_MULTIPLIER)
        g_sc = m * float(GRASS_SCATTER_SCALE_MULTIPLIER)
        scatter_stride = max(1, int(getattr(config, "URSINA_TERRAIN_SCATTER_STRIDE", 1)))
        grass_clumps, grass_stride = _grass_density_budget()

        root = Entity(name="terrain_3d_root")
        water_tint = color.rgb(0.24, 0.48, 0.82)

        w_world = (tw * ts) / SCALE
        d_world = (th * ts) / SCALE

        # --- Initialize the terrain_height module with world heightmap ---
        hmap = getattr(world, "heightmap", None)
        gw = getattr(world, "heightmap_grid_w", 0)
        gh = getattr(world, "heightmap_grid_h", 0)
        has_heightmap = hmap is not None and gw >= 2 and gh >= 2

        if has_heightmap and not is_initialized():
            # World origin: X starts at 0, Z is negative (sim_px_to_world_xz negates Y).
            # Grid row 0 -> most-negative Z (bottom of map in world space).
            # The map spans X=[0, w_world], Z=[-d_world, 0].
            init_heightmap(
                heightmap=hmap,
                grid_w=gw,
                grid_h=gh,
                world_w=w_world,
                world_h=d_world,
                world_origin_x=0.0,
                world_origin_z=-d_world,
            )

        # --- Build heightmap-displaced terrain mesh (or flat fallback) ---
        self._build_terrain_ground_mesh(root, world, tw, th, ts, w_world, d_world, has_heightmap)

        # --- Per-tile props with terrain Y ---
        for ty in range(th):
            for tx in range(tw):
                tile = int(world.tiles[ty][tx])
                cx_px = tx * ts + ts * 0.5
                cy_px = ty * ts + ts * 0.5
                wx, wz = px_to_world(cx_px, cy_px)
                prop_y = get_terrain_height(wx, wz) if has_heightmap else 0.0

                if tile == TileType.PATH:
                    path_ent = Entity(
                        parent=root,
                        model=path_model,
                        position=(wx, prop_y, wz),
                        scale=(m, m, m),
                        color=color.white,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )
                    _finalize_kenney_scatter_entity(path_ent, path_model)
                elif tile == TileType.WATER:
                    water_y = float(getattr(config, "TERRAIN_WATER_LEVEL", 1.0)) if has_heightmap else 0.005
                    tile_w = (float(ts) / SCALE) * m
                    water_ent = Entity(
                        parent=root,
                        model="quad",
                        rotation=(90, 0, 0),
                        position=(wx, water_y + 0.005, wz),
                        scale=(tile_w, tile_w, 1),
                        color=water_tint,
                        collision=False,
                        double_sided=True,
                        shader=unlit_shader,
                        add_to_scene_entities=False,
                    )
                    self.track_visibility_gated_terrain(water_ent, tx, ty)

                on_scatter_grid = (tx % scatter_stride == 0) and (ty % scatter_stride == 0)
                in_occ = (tx, ty) in occupied_tiles
                grass_here = (
                    grass_clumps > 0
                    and (tile == TileType.GRASS or tile == TileType.TREE)
                    and not in_occ
                    and _grass_tile_selected(tx, ty, grass_stride)
                )
                if grass_here:
                    tile_w = float(ts) / float(SCALE)
                    wh = tile_w * 0.46
                    for slot in range(int(grass_clumps)):
                        jx, jz, yaw = _grass_clump_offset(tx, ty, slot, wh)
                        gi = _scatter_model_index(
                            tx, ty, len(grass_models), salt=11 + slot * 17
                        )
                        gm = grass_models[gi]
                        g_stem = Path(gm).stem
                        g_mul = (
                            float(GROUND_PROP_FLOWER_LOG_MUSHROOM_SCALE)
                            if _stem_is_flower_ground_scatter(g_stem)
                            else 1.0
                        )
                        g_scale = g_sc * g_mul
                        g_y = get_terrain_height(wx + jx, wz + jz) if has_heightmap else 0.0
                        g_ent = Entity(
                            parent=root,
                            model=gm,
                            position=(wx + jx, g_y, wz + jz),
                            scale=(g_scale, g_scale, g_scale),
                            rotation=(0, yaw, 0),
                            color=color.white,
                            collision=False,
                            double_sided=True,
                            add_to_scene_entities=False,
                        )
                        _finalize_kenney_scatter_entity(g_ent, gm)
                        self.track_visibility_gated_terrain(g_ent, tx, ty)

                if tile == TileType.TREE:
                    ti = _scatter_model_index(tx, ty, len(tree_models), salt=41)
                    tree_model = tree_models[ti]
                    tree_ent = Entity(
                        parent=root,
                        model=tree_model,
                        position=(wx, prop_y, wz),
                        scale=(tm, tm, tm),
                        color=color.white,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )
                    _finalize_kenney_scatter_entity(tree_ent, tree_model)
                    self.track_visibility_gated_terrain(tree_ent, tx, ty)
                    self._r._tree_entities[(int(tx), int(ty))] = tree_ent
                    tree_ent._ks_tree_base_scale = float(tm)
                elif (
                    tile == TileType.GRASS
                    and on_scatter_grid
                    and not in_occ
                    and ((tx * 131 + ty * 17) % 11 == 0)
                ):
                    di = _scatter_model_index(tx, ty, len(doodad_models), salt=29)
                    dm = doodad_models[di]
                    jx, jz, yaw = _grass_scatter_jitter(tx + 101, ty + 67)
                    dstem = Path(dm).stem
                    dm_scale = rm * (0.85 if "bush" in dstem.lower() else 1.0)
                    if _stem_is_log_or_mushroom_ground_scatter(dstem):
                        dm_scale *= float(GROUND_PROP_FLOWER_LOG_MUSHROOM_SCALE)
                    d_y = get_terrain_height(wx + jx * 0.55, wz + jz * 0.55) if has_heightmap else 0.0
                    doodad_ent = Entity(
                        parent=root,
                        model=dm,
                        position=(wx + jx * 0.55, d_y, wz + jz * 0.55),
                        scale=(dm_scale, dm_scale, dm_scale),
                        rotation=(0, yaw, 0),
                        color=color.white,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )
                    _finalize_kenney_scatter_entity(doodad_ent, dm)
                    self.track_visibility_gated_terrain(doodad_ent, tx, ty)
                elif tile == TileType.GRASS and on_scatter_grid and not in_occ:
                    h = (tx * 92837111 ^ ty * 689287499) & 0xFFFFFFFF
                    if h % 503 == 0:
                        rock_ent = Entity(
                            parent=root,
                            model=rock_model,
                            position=(wx, prop_y, wz),
                            scale=(rm, rm, rm),
                            color=color.white,
                            collision=False,
                            double_sided=True,
                            add_to_scene_entities=False,
                        )
                        _finalize_kenney_scatter_entity(rock_ent, rock_model)
                        self.track_visibility_gated_terrain(rock_ent, tx, ty)

        self._r._terrain_entity = root

    def _build_terrain_ground_mesh(
        self, root, world, tw: int, th: int, ts: int,
        w_world: float, d_world: float, has_heightmap: bool,
    ) -> None:
        """Build the ground: heightmap-displaced indexed triangle mesh, or flat quad fallback.

        The mesh uses the world heightmap at 2x sub-tile resolution. Each vertex's Y is
        sampled from the heightmap. UVs tile the grass texture matching the existing
        texture_scale. Per-vertex normals are computed from adjacent height samples.

        WK53 R3: The terrain mesh uses terrain_fog_shader which samples both the grass
        albedo and a fog-of-war texture in a single draw call. The fog texture is uploaded
        as a shader uniform by ensure_fog_overlay() each time visibility changes.
        """
        import math as _math

        from game.graphics.terrain_height import get_terrain_height

        cx_px = tw * ts * 0.5
        cy_px = th * ts * 0.5

        hmap = getattr(world, "heightmap", None)
        gw = getattr(world, "heightmap_grid_w", 0)
        gh = getattr(world, "heightmap_grid_h", 0)

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
            self._apply_grass_texture(ground_ent, tw, th)
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
        self._apply_grass_texture(ground_ent, tw, th, use_texture_scale=False)

        # WK53 R3: Set fog UV transform so the shader can derive fog-of-war UVs from
        # the tiled grass UVs. fog_uv = grass_uv * fog_uv_scale + fog_uv_offset maps
        # tiled UVs back to [0,1] across the full map extent, with N/S flip.
        fog_uv_sx = tiles_per_repeat / float(tw) if tw > 0 else 1.0
        fog_uv_sy = -tiles_per_repeat / float(th) if th > 0 else -1.0
        ground_ent.set_shader_input("fog_uv_scale", Vec2(fog_uv_sx, fog_uv_sy))
        ground_ent.set_shader_input("fog_uv_offset", Vec2(0.0, 1.0))

        # Store reference so ensure_fog_overlay can upload the fog texture to this entity.
        self._r._terrain_ground_entity = ground_ent

    def _apply_grass_texture(self, ground_ent, tw: int, th: int, use_texture_scale: bool = True) -> None:
        """Load and apply the grass albedo texture to a ground entity."""
        try:
            from ursina import Texture
            from PIL import Image

            if getattr(self._r, "_ks_ground_tex", None) is None:
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
                    self._r._ks_ground_tex = Texture(img, filtering=None)
                else:
                    self._r._ks_ground_tex = None

            if self._r._ks_ground_tex is not None:
                ground_ent.texture = self._r._ks_ground_tex
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

    def sync_dynamic_trees(self, world, snapshot_trees) -> None:
        """WK44/WK45: scale existing 3D tree entities using sim Tree.growth_percentage.

        WK45: saplings can spawn (create entity) and can be removed when building over them.
        """
        ents = getattr(self._r, "_tree_entities", None)
        if not ents:
            return
        if not snapshot_trees:
            return

        # WK45: saplings can spawn on previously-grass tiles. Create new tree Entities on-demand
        # so spawned saplings are visible in Ursina without rebuilding the whole terrain.
        root = getattr(self._r, "_terrain_entity", None)
        if root is None:
            return

        try:
            tree_models = _environment_tree_model_list()
        except Exception:
            tree_models = []

        try:
            m = float(getattr(config, "TILE_SIZE", 32))
            tm = (m / SCALE) * float(TREE_SCALE_MULTIPLIER)
        except Exception:
            tm = 1.0

        growth_by_tile: dict[tuple[int, int], float] = {}
        for t in snapshot_trees:
            try:
                tx = int(getattr(t, "grid_x", 0))
                ty = int(getattr(t, "grid_y", 0))
                g = float(getattr(t, "growth_percentage", 1.0))
            except Exception:
                continue
            if g < 0.0:
                g = 0.0
            if g > 1.0:
                g = 1.0
            growth_by_tile[(tx, ty)] = g

            key = (tx, ty)
            if key not in ents:
                if not tree_models:
                    continue
                try:
                    from game.graphics.terrain_height import get_terrain_height, is_initialized as _hm_ok
                    wx, wz = sim_px_to_world_xz(tx * int(config.TILE_SIZE), ty * int(config.TILE_SIZE))
                    tree_y = get_terrain_height(wx, wz) if _hm_ok() else 0.0
                    ti = _scatter_model_index(tx, ty, len(tree_models), salt=41)
                    tree_model = tree_models[ti]
                    tree_ent = Entity(
                        parent=root,
                        model=tree_model,
                        position=(wx, tree_y, wz),
                        scale=(tm, tm, tm),
                        color=color.white,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )
                    _finalize_kenney_scatter_entity(tree_ent, tree_model)
                    self.track_visibility_gated_terrain(tree_ent, tx, ty)
                    ents[key] = tree_ent
                    tree_ent._ks_tree_base_scale = float(tm)
                except Exception:
                    # Spawn visibility should never crash the renderer.
                    pass

        for key, ent in list(ents.items()):
            g = growth_by_tile.get(key)
            if g is None:
                # If a tree entity exists but the sim no longer reports a Tree at this tile,
                # and the world tile is no longer TREE, destroy it (sapling built over).
                try:
                    if world is not None and int(world.get_tile(int(key[0]), int(key[1]))) != int(TileType.TREE):
                        import ursina as u

                        self.untrack_visibility_gated_terrain(ent)
                        u.destroy(ent)
                        ents.pop(key, None)
                except Exception:
                    pass
                continue
            base = float(getattr(ent, "_ks_tree_base_scale", 1.0))
            # Visual mapping: keep saplings visible at 25% without letting them block (blocking is sim-side).
            # Map growth 0..1 -> visual_scale 0.25..1.0 (linear).
            s = base * (0.25 + 0.75 * g)
            # Avoid churn if the scale is already correct.
            if getattr(ent, "_ks_tree_growth", None) != g:
                ent.scale = (s, s, s)
                ent._ks_tree_growth = g

    def sync_log_stacks(self, world, snapshot_log_stacks) -> None:
        """WK46 Stage 3: render chopped-tree log piles keyed by tile.

        Visibility gating rules:
        - enabled only if tile visibility != UNSEEN
        - apply fog tint multiplier when SEEN (reuse existing helper)
        """
        ents = getattr(self._r, "_log_stack_entities", None)
        if ents is None:
            return

        root = getattr(self._r, "_terrain_entity", None)
        if root is None:
            return

        want_by_tile: dict[tuple[int, int], float] = {}
        for ls in snapshot_log_stacks or ():
            try:
                tx = int(getattr(ls, "grid_x", 0))
                ty = int(getattr(ls, "grid_y", 0))
                sc = float(getattr(ls, "scale", 1.0))
            except Exception:
                continue
            if sc < 0.0:
                sc = 0.0
            if sc > 1.0:
                sc = 1.0
            want_by_tile[(tx, ty)] = sc

        if not want_by_tile and not ents:
            return

        try:
            base = float(getattr(config, "TILE_SIZE", 32)) / SCALE
        except Exception:
            base = 1.0
        base_scale = base * 0.60

        try:
            model_path = _environment_model_path("log_stackLarge")
        except Exception:
            model_path = None

        for key, sc in want_by_tile.items():
            tx, ty = int(key[0]), int(key[1])
            if model_path is None:
                continue
            if key not in ents:
                try:
                    from game.graphics.terrain_height import get_terrain_height, is_initialized as _hm_ok
                    wx, wz = sim_px_to_world_xz(tx * int(config.TILE_SIZE), ty * int(config.TILE_SIZE))
                    log_y = get_terrain_height(wx, wz) if _hm_ok() else 0.0
                    ent = Entity(
                        parent=root,
                        model=model_path,
                        position=(wx, log_y, wz),
                        scale=(base_scale, base_scale, base_scale),
                        color=color.white,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )
                    _finalize_kenney_scatter_entity(ent, model_path)
                    self.track_visibility_gated_terrain(ent, tx, ty)
                    ents[key] = ent
                    ent._ks_log_base_scale = float(base_scale)
                except Exception:
                    pass
            ent = ents.get(key)
            if ent is None:
                continue
            b = float(getattr(ent, "_ks_log_base_scale", base_scale))
            s = b * float(sc if sc > 0.0 else 0.0)
            if getattr(ent, "_ks_log_scale", None) != sc:
                ent.scale = (s, s, s)
                ent._ks_log_scale = sc
            # Ensure visibility gating applies even if fog revision doesn't change (cheap, per-stack).
            try:
                vis = world.visibility[ty][tx]
            except Exception:
                vis = Visibility.UNSEEN
            self.sync_terrain_prop_tile_visibility(ent, vis)

        for key, ent in list(ents.items()):
            if key in want_by_tile:
                continue
            try:
                import ursina as u

                self.untrack_visibility_gated_terrain(ent)
                u.destroy(ent)
            except Exception:
                pass
            ents.pop(key, None)
