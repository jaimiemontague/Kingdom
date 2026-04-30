"""Hardware-instanced unit draw path: dual GeomNodes + buffer textures (wk47–wk48).

When ``InstancedUnitRenderer.update(snapshot)`` is used by ``UrsinaRenderer``, heroes,
enemies, and workers sync from ``SimStateSnapshot`` into instanced draws (outside + optional
inside-building pass). Legacy per-Entity unit billboards are skipped for that scene
(instancing opt-in: ``KINGDOM_URSINA_INSTANCING=1``; default legacy Entity billboards).
"""
from __future__ import annotations

import math
import struct
import time
from typing import TYPE_CHECKING, Sequence

from panda3d.core import Geom
from panda3d.core import GeomEnums, GeomNode, GeomTriangles, GeomVertexData
from panda3d.core import GeomVertexFormat, GeomVertexWriter, NodePath, Texture
from panda3d.core import TransparencyAttrib

from game.graphics.animation import AnimationClip
from game.graphics.enemy_sprites import EnemySpriteLibrary
from game.graphics.hero_sprites import HeroSpriteLibrary
from game.graphics.instanced_unit_shader import instanced_unit_shader
from game.graphics.shadow_instanced_shader import shadow_instanced_shader
from game.graphics.unit_atlas import FRAME_SIZE, UnitAtlasBuilder
from game.graphics.ursina_coords import sim_px_to_world_xz
from game.graphics.ursina_texture_bridge import pygame_surface_to_ursina_texture
from game.graphics.ursina_units_anim import (
    _enemy_base_clip,
    _frame_index_for_clip,
    _hero_base_clip,
)
from game.world import Visibility

if TYPE_CHECKING:
    from game.sim.snapshot import SimStateSnapshot

import config

MAX_INSTANCES = 1024
# Inside-building heroes are a small slice; separate buffer avoids Panda instance offset limits.
MAX_INSIDE_INSTANCES = 128
BYTES_PER_TEXEL = 16  # RGBA32F

# Render-only visual trailing (not sim-step interpolation).
SMOOTHING_SPEED = 15.0
TELEPORT_DIST_SQ = 2.25  # 1.5^2 — snap past this (teleport / building entry)

# Match Ursina legacy billboard scales (`ursina_renderer.py`); scale with UNIT_SPRITE_PIXELS.
_US = float(getattr(config, "UNIT_SPRITE_PIXELS", config.TILE_SIZE)) / float(config.TILE_SIZE)
HERO_SCALE = 0.62 * _US
ENEMY_SCALE = 0.5 * _US
PEASANT_SCALE = 0.465 * _US
GUARD_SCALE_UNIFORM = 0.5 * _US  # legacy xz; Y was 0.7 — single-instanced quad uses xz scale

# Match ``ursina_renderer.PROJECTILE_*`` — instanced arrow billboards + shadow skip via negative scale.w.
PROJECTILE_BILLBOARD_SCALE = 0.075
PROJECTILE_BILLBOARD_Y = ENEMY_SCALE * 0.5


class InstancedUnitRenderer:
    """Dual ``GeomNode`` draws with ``NodePath.set_instance_count(N)`` and float buffer textures.

    Outside units use the main buffer; heroes with ``is_inside_building`` use a small secondary
    buffer drawn in a late fixed bin (over building façades). Panda3D 1.10.x exposes hardware
    instance count on ``NodePath``, not ``Geom``.
    """

    __slots__ = (
        "_atlas_builder",
        "_atlas_tex",
        "_instance_buffer",
        "_instance_buffer_inside",
        "_geom_node_outside",
        "_geom_node_inside",
        "_shadow_geom_node",
        "_initialized",
        "_geom",
        "_unit_anim_state",
        "_visual_pos_by_id",
    )

    def __init__(self) -> None:
        self._atlas_builder = UnitAtlasBuilder.get()
        self._atlas_tex = None
        self._instance_buffer: Texture | None = None
        self._instance_buffer_inside: Texture | None = None
        self._geom_node_outside: NodePath | None = None
        self._geom_node_inside: NodePath | None = None
        self._shadow_geom_node: NodePath | None = None
        self._geom: Geom | None = None
        self._initialized = False
        # Mirror ``UrsinaRenderer._unit_anim_surface`` triggers + locomotion timing (wall clock).
        self._unit_anim_state: dict[int, dict] = {}
        self._visual_pos_by_id: dict[int, tuple[float, float, float]] = {}

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        atlas_surf = self._atlas_builder.atlas_surface
        self._atlas_tex = pygame_surface_to_ursina_texture(
            atlas_surf, cache_key="unit_instancing_atlas_v1"
        )
        panda_atlas: Texture = self._atlas_tex._texture
        panda_atlas.set_magfilter(Texture.FT_nearest)
        panda_atlas.set_minfilter(Texture.FT_nearest)

        self._instance_buffer = Texture("unit_instance_data")
        self._instance_buffer.setup_buffer_texture(
            MAX_INSTANCES * 2,
            Texture.T_float,
            Texture.F_rgba32,
            GeomEnums.UH_dynamic,
        )

        self._instance_buffer_inside = Texture("unit_instance_data_inside")
        self._instance_buffer_inside.setup_buffer_texture(
            MAX_INSIDE_INSTANCES * 2,
            Texture.T_float,
            Texture.F_rgba32,
            GeomEnums.UH_dynamic,
        )

        np_outside, geom_out = self._create_instanced_quad("instanced_units_outside")
        self._geom_node_outside = np_outside
        self._geom = geom_out
        np_inside, _ = self._create_instanced_quad("instanced_units_inside")
        self._geom_node_inside = np_inside

        np_shadow, _ = self._create_instanced_quad("instanced_units_shadow")
        self._shadow_geom_node = np_shadow
        ssh = shadow_instanced_shader._shader
        self._shadow_geom_node.set_shader(ssh)
        self._shadow_geom_node.set_shader_input("instanceData", self._instance_buffer)
        self._shadow_geom_node.set_transparency(TransparencyAttrib.M_alpha)
        self._shadow_geom_node.set_depth_write(False)
        self._shadow_geom_node.set_bin("transparent", 0)
        # Ground plane + scatter sit near y≈-0.05 .. 0; flat blob must not be backface-culled and
        # needs a slight depth bias or it loses every depth test vs terrain/grass from tilted RTS cam.
        self._shadow_geom_node.set_two_sided(True)
        self._shadow_geom_node.set_depth_offset(10, 0)

        sh = instanced_unit_shader._shader
        self._geom_node_outside.set_shader(sh)
        self._geom_node_outside.set_shader_input("p3d_Texture0", panda_atlas)
        self._geom_node_outside.set_shader_input("instanceData", self._instance_buffer)
        self._geom_node_outside.set_transparency(TransparencyAttrib.M_alpha)
        self._geom_node_outside.set_depth_write(False)
        self._geom_node_outside.set_bin("transparent", 1)

        self._geom_node_inside.set_shader(sh)
        self._geom_node_inside.set_shader_input("p3d_Texture0", panda_atlas)
        self._geom_node_inside.set_shader_input("instanceData", self._instance_buffer_inside)
        self._geom_node_inside.set_transparency(TransparencyAttrib.M_alpha)
        self._geom_node_inside.set_depth_write(False)
        self._geom_node_inside.set_depth_test(False)
        self._geom_node_inside.set_bin("fixed", 100)

    def _create_instanced_quad(self, geom_name: str) -> tuple[NodePath, Geom]:
        fmt = GeomVertexFormat.get_v3t2()
        vdata = GeomVertexData("unit_quad", fmt, GeomEnums.UH_static)
        vdata.set_num_rows(4)

        vertex = GeomVertexWriter(vdata, "vertex")
        texcoord = GeomVertexWriter(vdata, "texcoord")

        vertex.add_data3(-0.5, -0.5, 0)
        vertex.add_data3(0.5, -0.5, 0)
        vertex.add_data3(0.5, 0.5, 0)
        vertex.add_data3(-0.5, 0.5, 0)

        texcoord.add_data2(0, 1)
        texcoord.add_data2(1, 1)
        texcoord.add_data2(1, 0)
        texcoord.add_data2(0, 0)

        tris = GeomTriangles(GeomEnums.UH_static)
        tris.add_vertices(0, 1, 2)
        tris.add_vertices(0, 2, 3)

        geom = Geom(vdata)
        geom.add_primitive(tris)

        node = GeomNode(geom_name)
        node.add_geom(geom)

        from ursina import scene

        np = NodePath(node)
        np.reparent_to(scene)
        np.set_instance_count(0)
        return np, geom

    def _resolve_unit_anim_clip_frame(
        self,
        obj_id: int,
        entity,
        clips: dict[str, AnimationClip],
        base_clip_fn,
    ) -> tuple[str, int]:
        """Same resolution as ``UrsinaRenderer._unit_anim_surface`` minus surface/cache_key."""
        trigger = getattr(entity, "_ursina_anim_trigger", None) or getattr(
            entity, "_render_anim_trigger", None
        )
        if trigger:
            tname = str(trigger)
            if tname in clips:
                setattr(entity, "_ursina_anim_trigger", None)
                setattr(entity, "_render_anim_trigger", None)
                base = base_clip_fn(entity)
                oc = clips[tname]
                self._unit_anim_state[obj_id] = {
                    "clip": tname,
                    "t0": time.time(),
                    "base": base,
                    "oneshot": not oc.loop,
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
                oc_done = clips[st["clip"]]
                elapsed_done = time.time() - st["t0"]
                _, finished = _frame_index_for_clip(oc_done, elapsed_done)
                if finished:
                    st["clip"] = st["base"]
                    st["t0"] = time.time()
                    st["oneshot"] = False
            if not st.get("oneshot"):
                if st["clip"] != base:
                    st["clip"] = base
                    st["t0"] = time.time()

        clip_name = st["clip"]
        clip_obj = clips[clip_name]
        elapsed = time.time() - st["t0"]
        idx, _ = _frame_index_for_clip(clip_obj, elapsed)
        return clip_name, idx

    def _smooth_visual_position(
        self,
        obj_id: int,
        wx: float,
        wy: float,
        wz: float,
        dt: float,
    ) -> tuple[float, float, float]:
        """Render-space exponential smoothing; snap past ``TELEPORT_DIST_SQ`` (teleports, building hops)."""
        tx, ty, tz = wx, wy, wz
        prev = self._visual_pos_by_id.get(obj_id)
        if prev is None:
            self._visual_pos_by_id[obj_id] = (tx, ty, tz)
            return tx, ty, tz
        vx, vy, vz = prev
        dist_sq = (tx - vx) ** 2 + (ty - vy) ** 2 + (tz - vz) ** 2
        if dist_sq > TELEPORT_DIST_SQ:
            self._visual_pos_by_id[obj_id] = (tx, ty, tz)
            return tx, ty, tz
        lerp = 1.0 - math.exp(-SMOOTHING_SPEED * dt)
        nx = vx + (tx - vx) * lerp
        ny = vy + (ty - vy) * lerp
        nz = vz + (tz - vz) * lerp
        new_pos = (nx, ny, nz)
        self._visual_pos_by_id[obj_id] = new_pos
        return new_pos

    def update(self, snapshot: "SimStateSnapshot") -> set:
        """Pack snapshot units into outside + inside buffers; return active sim object ids for cleanup."""
        from ursina import time as ursina_time

        self._ensure_initialized()
        assert self._instance_buffer is not None
        assert self._instance_buffer_inside is not None
        assert self._geom is not None

        dt = max(float(ursina_time.dt), 0.0)
        active_ids: set[int] = set()

        buf_out = memoryview(self._instance_buffer.modify_ram_image())
        buf_in = memoryview(self._instance_buffer_inside.modify_ram_image())

        count_outside = 0
        count_inside = 0

        def pack_outside(vx: float, vy: float, vz: float, scale: float, uv) -> None:
            nonlocal count_outside
            if count_outside >= MAX_INSTANCES:
                return
            offset = count_outside * 2 * BYTES_PER_TEXEL
            struct.pack_into("ffff", buf_out, offset, vx, vy, vz, scale)
            struct.pack_into("ffff", buf_out, offset + BYTES_PER_TEXEL, *uv)
            count_outside += 1

        def pack_inside(vx: float, vy: float, vz: float, scale: float, uv) -> None:
            nonlocal count_inside
            if count_inside >= MAX_INSIDE_INSTANCES:
                return
            offset = count_inside * 2 * BYTES_PER_TEXEL
            struct.pack_into("ffff", buf_in, offset, vx, vy, vz, scale)
            struct.pack_into("ffff", buf_in, offset + BYTES_PER_TEXEL, *uv)
            count_inside += 1

        world = getattr(snapshot, "world", None)
        ts = float(config.TILE_SIZE)

        # --- Outside pass: surface heroes + enemies + workers (smooth into main buffer). ---
        for h in getattr(snapshot, "heroes", ()):
            if not getattr(h, "is_alive", True):
                continue
            if bool(getattr(h, "is_inside_building", False)):
                continue
            if count_outside >= MAX_INSTANCES:
                break
            hc_key = str(getattr(h, "hero_class", "warrior") or "warrior").lower()
            clips_h = HeroSpriteLibrary.clips_for(hc_key, size=FRAME_SIZE)
            obj_id = id(h)
            clip_name, frame_idx = self._resolve_unit_anim_clip_frame(
                obj_id, h, clips_h, _hero_base_clip
            )
            uv = self._atlas_builder.lookup_uv("hero", hc_key, clip_name, frame_idx)
            wx, wz = sim_px_to_world_xz(h.x, h.y)
            wy = HERO_SCALE * 0.5
            vx, vy, vz = self._smooth_visual_position(obj_id, wx, wy, wz, dt)
            pack_outside(vx, vy, vz, HERO_SCALE, uv)
            active_ids.add(obj_id)

        # --- Enemies (fog visibility matches legacy) ---
        for e in getattr(snapshot, "enemies", ()):
            if not getattr(e, "is_alive", True):
                continue
            if world is not None:
                tx, ty = int(e.x / ts), int(e.y / ts)
                if 0 <= ty < world.height and 0 <= tx < world.width:
                    if world.visibility[ty][tx] != Visibility.VISIBLE:
                        continue
            if count_outside >= MAX_INSTANCES:
                break
            et_key = str(getattr(e, "enemy_type", "goblin") or "goblin").lower()
            clips_e = EnemySpriteLibrary.clips_for(et_key, size=FRAME_SIZE)
            obj_id = id(e)
            clip_name, frame_idx = self._resolve_unit_anim_clip_frame(
                obj_id, e, clips_e, _enemy_base_clip
            )
            uv = self._atlas_builder.lookup_uv("enemy", et_key, clip_name, frame_idx)
            wx, wz = sim_px_to_world_xz(e.x, e.y)
            wy = ENEMY_SCALE * 0.5
            vx, vy, vz = self._smooth_visual_position(obj_id, wx, wy, wz, dt)
            pack_outside(vx, vy, vz, ENEMY_SCALE, uv)
            active_ids.add(obj_id)

        # --- Workers ---
        for p in getattr(snapshot, "peasants", ()):
            if not getattr(p, "is_alive", True):
                continue
            if count_outside >= MAX_INSTANCES:
                break
            uv = self._atlas_builder.lookup_uv("worker", "peasant", "idle", 0)
            wx, wz = sim_px_to_world_xz(p.x, p.y)
            wy = PEASANT_SCALE * 0.5
            oid = id(p)
            vx, vy, vz = self._smooth_visual_position(oid, wx, wy, wz, dt)
            pack_outside(vx, vy, vz, PEASANT_SCALE, uv)
            active_ids.add(oid)

        for g in getattr(snapshot, "guards", ()):
            if not getattr(g, "is_alive", True):
                continue
            if count_outside >= MAX_INSTANCES:
                break
            uv = self._atlas_builder.lookup_uv("worker", "guard", "idle", 0)
            wx, wz = sim_px_to_world_xz(g.x, g.y)
            wy = GUARD_SCALE_UNIFORM * 0.5
            oid = id(g)
            vx, vy, vz = self._smooth_visual_position(oid, wx, wy, wz, dt)
            pack_outside(vx, vy, vz, GUARD_SCALE_UNIFORM, uv)
            active_ids.add(oid)

        tc = getattr(snapshot, "tax_collector", None)
        if tc is not None and getattr(tc, "is_alive", True) and count_outside < MAX_INSTANCES:
            uv = self._atlas_builder.lookup_uv("worker", "tax_collector", "idle", 0)
            wx, wz = sim_px_to_world_xz(tc.x, tc.y)
            wy = PEASANT_SCALE * 0.5
            oid = id(tc)
            vx, vy, vz = self._smooth_visual_position(oid, wx, wy, wz, dt)
            pack_outside(vx, vy, vz, PEASANT_SCALE, uv)
            active_ids.add(oid)

        # --- VFX projectiles (outside buffer only; negative scale.w skips blob shadow shader). ---
        uv_proj = self._atlas_builder.lookup_uv("vfx", "projectile", "arrow", 0)
        for proj in getattr(snapshot, "vfx_projectiles", ()) or ():
            if count_outside >= MAX_INSTANCES:
                break
            wx, wz = sim_px_to_world_xz(proj.x, proj.y)
            wy = PROJECTILE_BILLBOARD_Y
            oid = id(proj)
            pack_outside(wx, wy, wz, -PROJECTILE_BILLBOARD_SCALE, uv_proj)
            active_ids.add(oid)

        # --- Inside-building heroes (fixed bin draws after terrain/buildings). ---
        for h in getattr(snapshot, "heroes", ()):
            if not getattr(h, "is_alive", True):
                continue
            if not bool(getattr(h, "is_inside_building", False)):
                continue
            if count_inside >= MAX_INSIDE_INSTANCES:
                break
            hc_key = str(getattr(h, "hero_class", "warrior") or "warrior").lower()
            clips_h = HeroSpriteLibrary.clips_for(hc_key, size=FRAME_SIZE)
            obj_id = id(h)
            clip_name, frame_idx = self._resolve_unit_anim_clip_frame(
                obj_id, h, clips_h, _hero_base_clip
            )
            uv = self._atlas_builder.lookup_uv("hero", hc_key, clip_name, frame_idx)
            wx, wz = sim_px_to_world_xz(h.x, h.y)
            wy = HERO_SCALE * 0.5
            vx, vy, vz = self._smooth_visual_position(obj_id, wx, wy, wz, dt)
            pack_inside(vx, vy, vz, HERO_SCALE, uv)
            active_ids.add(obj_id)

        assert self._geom_node_outside is not None
        assert self._geom_node_inside is not None
        assert self._shadow_geom_node is not None
        self._geom_node_outside.set_instance_count(count_outside)
        self._geom_node_inside.set_instance_count(count_inside)
        self._shadow_geom_node.set_instance_count(count_outside)
        self._instance_buffer.reload()
        self._instance_buffer_inside.reload()

        for oid in list(self._unit_anim_state.keys()):
            if oid not in active_ids:
                self._unit_anim_state.pop(oid, None)

        for oid in list(self._visual_pos_by_id.keys()):
            if oid not in active_ids:
                self._visual_pos_by_id.pop(oid, None)

        return active_ids

    def set_instances(
        self,
        positions: Sequence[tuple[float, float, float]],
        *,
        scale: float = 0.62,
        uv_region: tuple[float, float, float, float] | None = None,
    ) -> int:
        """Pack the outside instance buffer and return instance count (capped at ``MAX_INSTANCES``)."""
        self._ensure_initialized()
        assert self._instance_buffer is not None
        assert self._instance_buffer_inside is not None
        assert self._geom is not None

        if uv_region is None:
            uv_region = self._atlas_builder.lookup_uv("hero", "warrior", "idle", 0)

        n = min(len(positions), MAX_INSTANCES)
        buf = memoryview(self._instance_buffer.modify_ram_image())

        for i in range(n):
            px, py, pz = positions[i]
            offset = i * 2 * BYTES_PER_TEXEL
            struct.pack_into("ffff", buf, offset, px, py, pz, scale)
            struct.pack_into("ffff", buf, offset + BYTES_PER_TEXEL, *uv_region)

        assert self._geom_node_outside is not None
        assert self._geom_node_inside is not None
        assert self._shadow_geom_node is not None
        self._geom_node_outside.set_instance_count(n)
        self._geom_node_inside.set_instance_count(0)
        self._shadow_geom_node.set_instance_count(n)
        self._instance_buffer.reload()
        self._instance_buffer_inside.reload()
        return n

    def test_draw(
        self,
        positions: Sequence[tuple[float, float, float]] | None = None,
        *,
        scale: float = 0.62,
    ) -> int:
        """Upload default 10 world-space instances (or custom positions) for a smoke draw."""
        if positions is None:
            positions = [(i * 1.2 - 5.4, 0.35, 0.0) for i in range(10)]
        return self.set_instances(positions, scale=scale)

    def destroy(self) -> None:
        self._unit_anim_state.clear()
        self._visual_pos_by_id.clear()
        if self._geom_node_outside is not None:
            self._geom_node_outside.remove_node()
            self._geom_node_outside = None
        if self._geom_node_inside is not None:
            self._geom_node_inside.remove_node()
            self._geom_node_inside = None
        if self._shadow_geom_node is not None:
            self._shadow_geom_node.remove_node()
            self._shadow_geom_node = None
        self._geom = None
        self._initialized = False
