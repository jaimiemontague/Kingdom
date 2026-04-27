"""Terrain, fog overlay, grid debug (WK41 R2 collaborator)."""

from __future__ import annotations

import os
from pathlib import Path

import pygame
import config
from ursina import Entity, Vec2, Vec3, color

from game.graphics.terrain_texture_bridge import TerrainTextureBridge
from game.graphics.ursina_coords import SCALE, px_to_world, sim_px_to_world_xz
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
        row_unseen = b"\x00\x00\x00\xff" * tw
        for ty in range(th):
            buf[ty * tw * 4 : (ty + 1) * tw * 4] = row_unseen
        vis_b = b"\x00\x00\x00\x00"
        try:
            seen_a = int(getattr(config, "URSINA_FOG_SEEN_ALPHA", 0xAA))
        except Exception:
            seen_a = 0xAA
        seen_a = max(0, min(255, int(seen_a)))
        seen_b = bytes((0, 0, 0, seen_a))
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
        self._r._fog_full_surf = surf

        ftex = TerrainTextureBridge.refresh_surface_texture(surf, cache_key=FOG_TEX_BRIDGE_KEY)
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
            if self._r._fog_entity.texture:
                self._r._fog_entity.texture.filtering = None
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
        """Per-tile path/water meshes + scatter grass doodads on a full-map base plane (v1.5 Sprint 1.2)."""
        if self._r._terrain_entity is not None:
            return

        tw, th = int(world.width), int(world.height)
        ts = int(config.TILE_SIZE)
        m = float(TERRAIN_SCALE_MULTIPLIER)
        grass_models, doodad_models = _environment_grass_and_doodad_model_lists()
        tree_models = _environment_tree_model_list()
        # Gray stone path (Nature Kit path_stone) — reads as pavement vs warm Retro Fantasy roofs.
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

        # Cohesive green ground plane under the grid (organic scatter sits on y≈0 above this).
        w_world = (tw * ts) / SCALE
        d_world = (th * ts) / SCALE
        cx_px = tw * ts * 0.5
        cy_px = th * ts * 0.5
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
        # WK33: tile the user-provided grass albedo across the entire ground plane.
        try:
            from ursina import Texture
            from PIL import Image

            if getattr(self, "_ks_ground_tex", None) is None:
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
                # Default: 1 repeat per ~2 tiles (override for quick tuning).
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

                # WK31: optional stride thins non-grass props (doodads/rocks).
                # WK32 r3: grass keeps r2 sub-tile jitter but now has a startup budget.
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
                        g_ent = Entity(
                            parent=root,
                            model=gm,
                            position=(wx + jx, 0.0, wz + jz),
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
                        position=(wx, 0.0, wz),
                        scale=(tm, tm, tm),
                        color=color.white,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )
                    _finalize_kenney_scatter_entity(tree_ent, tree_model)
                    self.track_visibility_gated_terrain(tree_ent, tx, ty)
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
                    self.track_visibility_gated_terrain(doodad_ent, tx, ty)
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
                        self.track_visibility_gated_terrain(rock_ent, tx, ty)

        # Do not flattenStrong() the terrain root: Panda3D merge can strip per-tile glTF
        # material state and turn Kenney path_stone (and similar) into uniform white strips.
        # WK22 perf note: revisit batching once path meshes use a single atlas or baked strip.
        # root.flattenStrong()
        self._r._terrain_entity = root
