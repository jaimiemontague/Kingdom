"""Hardware-instanced unit draw path: GeomNode + buffer texture (wk47).

When ``InstancedUnitRenderer.update(snapshot)`` is used by ``UrsinaRenderer``, all heroes,
enemies, and workers sync from ``SimStateSnapshot`` into one instanced draw. Legacy per-Entity
unit billboards are skipped for that scene (see ``KINGDOM_URSINA_INSTANCING`` gate).
"""
from __future__ import annotations

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
BYTES_PER_TEXEL = 16  # RGBA32F

# Match Ursina legacy billboard scales (`ursina_renderer.py`)
HERO_SCALE = 0.62
ENEMY_SCALE = 0.5
PEASANT_SCALE = 0.465
GUARD_SCALE_UNIFORM = 0.5  # legacy xz; Y was 0.7 — single-instanced quad uses xz scale


class InstancedUnitRenderer:
    """Single GeomNode draw with ``NodePath.set_instance_count(N)`` and a float buffer texture.

    Panda3D 1.10.x exposes hardware instance count on ``NodePath``, not ``Geom``.
    """

    __slots__ = (
        "_atlas_builder",
        "_atlas_tex",
        "_instance_buffer",
        "_geom_node_path",
        "_initialized",
        "_geom",
        "_unit_anim_state",
    )

    def __init__(self) -> None:
        self._atlas_builder = UnitAtlasBuilder.get()
        self._atlas_tex = None
        self._instance_buffer: Texture | None = None
        self._geom_node_path: NodePath | None = None
        self._geom: Geom | None = None
        self._initialized = False
        # Mirror ``UrsinaRenderer._unit_anim_surface`` triggers + locomotion timing (wall clock).
        self._unit_anim_state: dict[int, dict] = {}

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

        self._geom_node_path = self._create_instanced_quad()

        sh = instanced_unit_shader._shader
        self._geom_node_path.set_shader(sh)
        self._geom_node_path.set_shader_input("p3d_Texture0", panda_atlas)
        self._geom_node_path.set_shader_input("instanceData", self._instance_buffer)
        self._geom_node_path.set_transparency(TransparencyAttrib.M_alpha)
        self._geom_node_path.set_depth_write(False)
        self._geom_node_path.set_bin("transparent", 1)

    def _create_instanced_quad(self) -> NodePath:
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

        node = GeomNode("instanced_units")
        node.add_geom(geom)
        self._geom = geom

        from ursina import scene

        np = NodePath(node)
        np.reparent_to(scene)
        np.set_instance_count(0)
        return np

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

    def update(self, snapshot: "SimStateSnapshot") -> set:
        """Pack snapshot units into the instance buffer; return active sim object ids for cleanup."""
        self._ensure_initialized()
        assert self._instance_buffer is not None
        assert self._geom is not None

        active_ids: set[int] = set()
        instance_count = 0
        buf = memoryview(self._instance_buffer.modify_ram_image())

        world = getattr(snapshot, "world", None)
        ts = float(config.TILE_SIZE)

        def pack_instance(wx: float, wy: float, wz: float, scale: float, uv) -> None:
            nonlocal instance_count
            if instance_count >= MAX_INSTANCES:
                return
            offset = instance_count * 2 * BYTES_PER_TEXEL
            struct.pack_into("ffff", buf, offset, wx, wy, wz, scale)
            struct.pack_into("ffff", buf, offset + BYTES_PER_TEXEL, *uv)
            instance_count += 1

        # --- Heroes ---
        for h in getattr(snapshot, "heroes", ()):
            if not getattr(h, "is_alive", True):
                continue
            if instance_count >= MAX_INSTANCES:
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
            pack_instance(wx, wy, wz, HERO_SCALE, uv)
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
            if instance_count >= MAX_INSTANCES:
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
            pack_instance(wx, wy, wz, ENEMY_SCALE, uv)
            active_ids.add(obj_id)

        # --- Workers: idle atlas frame 0 (matches legacy billboard idle surface) ---
        for p in getattr(snapshot, "peasants", ()):
            if not getattr(p, "is_alive", True) or instance_count >= MAX_INSTANCES:
                continue
            uv = self._atlas_builder.lookup_uv("worker", "peasant", "idle", 0)
            wx, wz = sim_px_to_world_xz(p.x, p.y)
            wy = PEASANT_SCALE * 0.5
            pack_instance(wx, wy, wz, PEASANT_SCALE, uv)
            active_ids.add(id(p))

        for g in getattr(snapshot, "guards", ()):
            if not getattr(g, "is_alive", True) or instance_count >= MAX_INSTANCES:
                continue
            uv = self._atlas_builder.lookup_uv("worker", "guard", "idle", 0)
            wx, wz = sim_px_to_world_xz(g.x, g.y)
            wy = GUARD_SCALE_UNIFORM * 0.5
            pack_instance(wx, wy, wz, GUARD_SCALE_UNIFORM, uv)
            active_ids.add(id(g))

        tc = getattr(snapshot, "tax_collector", None)
        if tc is not None and getattr(tc, "is_alive", True) and instance_count < MAX_INSTANCES:
            uv = self._atlas_builder.lookup_uv("worker", "tax_collector", "idle", 0)
            wx, wz = sim_px_to_world_xz(tc.x, tc.y)
            wy = PEASANT_SCALE * 0.5
            pack_instance(wx, wy, wz, PEASANT_SCALE, uv)
            active_ids.add(id(tc))

        assert self._geom_node_path is not None
        self._geom_node_path.set_instance_count(instance_count)
        self._instance_buffer.reload()

        # Anim state bookkeeping: drop entries whose sim objects are gone from this frame's buffer.
        for oid in list(self._unit_anim_state.keys()):
            if oid not in active_ids:
                self._unit_anim_state.pop(oid, None)

        return active_ids

    def set_instances(
        self,
        positions: Sequence[tuple[float, float, float]],
        *,
        scale: float = 0.62,
        uv_region: tuple[float, float, float, float] | None = None,
    ) -> int:
        """Pack instance buffer and return instance count (capped at ``MAX_INSTANCES``)."""
        self._ensure_initialized()
        assert self._instance_buffer is not None
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

        assert self._geom_node_path is not None
        self._geom_node_path.set_instance_count(n)
        self._instance_buffer.reload()
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
        if self._geom_node_path is not None:
            self._geom_node_path.remove_node()
            self._geom_node_path = None
        self._geom = None
        self._initialized = False
