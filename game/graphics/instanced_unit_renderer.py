"""Hardware-instanced unit draw path: dual GeomNodes + buffer textures (wk47–wk48).

When ``InstancedUnitRenderer.update(snapshot)`` is used by ``UrsinaRenderer``, heroes,
enemies, and workers sync from ``SimStateSnapshot`` into instanced draws (outside + optional
inside-building pass). Legacy per-Entity unit billboards are skipped for that scene.

Mythos S6 (``inst-default-flip``): this is now the DEFAULT unit-draw path
(``KINGDOM_URSINA_INSTANCING`` defaults to "1"; set "0" for the legacy
per-Entity billboard fallback). Full feature parity shipped with the flip:

* ``inst-hp-bars``: one extra instanced draw renders every unit HP bar
  (per-instance pos + fill fraction; legacy green/red/gray palette derived
  in-shader; bin ``fixed,110`` per the WK124 overlay contract);
* ``inst-parity-gap-fixes``: instance Y samples ``get_terrain_height`` (units
  sit ON hills — TERRAIN_HEIGHT_SCALE=5.0 buried them before), guards/peasants
  keep their legacy non-uniform scales (3-texel instance layout), WK124
  magic/heal projectile kinds render from their own atlas frames, the
  underground layer gate matches legacy, and blob shadows follow the terrain;
* ``inst-linear-interp``: instance positions linearly interpolate between sim
  ticks with ``sim_blend_fraction`` exactly like the legacy path (the prior
  render-only exponential trailing was the pattern prior art REJECTED);
* name/gold labels render via the pooled zoom-LOD Text labels in
  ``instanced_unit_labels.py`` fed from ``label_sources`` (built here from the
  same blended positions so labels never desync from sprites).

WK128: blob shadows are OFF by default (legacy drew no unit shadows; the
owner dislikes the dark ellipses) — the shadow geom is only created when
``KINGDOM_UNIT_SHADOWS=1`` (see ``unit_shadows_env_enabled``). The same round
fixed the upside-down sprites: the instanced shader double-V-flipped (legacy
bottom-up texture_offset math on top of the quad's top-down texcoords); see
``instanced_unit_shader.py`` and tests/test_wk128_instanced_v_orientation.py.
"""
from __future__ import annotations

import os
import struct
from typing import TYPE_CHECKING, Sequence

from panda3d.core import Geom
from panda3d.core import GeomEnums, GeomNode, GeomTriangles, GeomVertexData
from panda3d.core import GeomVertexFormat, GeomVertexWriter, NodePath, Texture
from panda3d.core import TransparencyAttrib

from game.graphics.animation import AnimationClip
from game.graphics.enemy_sprites import EnemySpriteLibrary
from game.graphics.hero_sprites import HeroSpriteLibrary
from game.graphics.worker_sprites import WorkerSpriteLibrary
from game.graphics.instanced_hp_bar_shader import instanced_hp_bar_shader
from game.graphics.instanced_unit_shader import instanced_unit_shader
from game.graphics.shadow_instanced_shader import shadow_instanced_shader
from game.graphics.terrain_height import (
    get_terrain_height,
    is_initialized as _terrain_height_ok,
)
from game.graphics.unit_atlas import FRAME_SIZE, UnitAtlasBuilder
from game.graphics.ursina_coords import sim_px_to_world_xz
from game.graphics.ursina_units_anim import (
    anim_clock_seconds,
    _frame_index_for_clip,
)
from game.graphics.visual_specs import (
    ENEMY_SPEC,
    GUARD_SPEC,
    HERO_SPEC,
    PEASANT_SPEC,
)
from game.world import Visibility

if TYPE_CHECKING:
    from game.sim.render_dto import UnitDTO
    from game.sim.snapshot import SimStateSnapshot

import config

MAX_INSTANCES = 1024
# Inside-building heroes are a small slice; separate buffer avoids Panda instance offset limits.
MAX_INSIDE_INSTANCES = 128
BYTES_PER_TEXEL = 16  # RGBA32F
# Mythos S6: 3 texels per unit instance — (pos + signed x-scale), (uv region),
# (y-scale, 0, 0, 0) — so non-uniform legacy scales survive instancing.
TEXELS_PER_INSTANCE = 3
# HP bars: 2 texels per bar — (pos + fill fraction), (bar_w, bar_h, bar_y, 0).
HP_BAR_TEXELS_PER_INSTANCE = 2

# Legacy linear-interp snap thresholds — byte-match `_sync_unit_atlas_billboard`
# (ursina_renderer.py): converge when nearly stationary; snap past 3.0 world
# units (teleport / building entry) instead of sweeping across the map.
INTERP_MIN_DIST_SQ = 0.0001
INTERP_SNAP_DIST_SQ = 9.0

# Match Ursina legacy billboard scales (`ursina_unit_sync.py`); scale with UNIT_SPRITE_PIXELS.
_US = float(getattr(config, "UNIT_SPRITE_PIXELS", config.TILE_SIZE)) / float(config.TILE_SIZE)
HERO_SCALE = 0.62 * _US
ENEMY_SCALE = 0.5 * _US


# WK137: per-instance enemy billboard scale — `size` stat / 18 (the basic-enemy
# baseline), clamped so a bad stat can never explode an instance. 18->1.0x,
# warchief 24->1.33x, bandit_lord 28->1.56x, demon 32->1.78x, dragon 36->2.0x.
# Recomputed identically in ursina_unit_sync.py (no cross-import between
# renderer modules, matching this file's ENEMY_SCALE duplication convention).
_ENEMY_BASE_SIZE = 18.0
_ENEMY_SCALE_MAX_MULT = 2.0


def enemy_billboard_scale(size: int) -> float:
    mult = max(1.0, min(_ENEMY_SCALE_MAX_MULT, float(size or 18) / _ENEMY_BASE_SIZE))
    return ENEMY_SCALE * mult
_WB = float(getattr(config, "URSINA_WORKER_BILLBOARD_BASE", 0.42))
_WYM = float(getattr(config, "URSINA_WORKER_BILLBOARD_Y_SCALE_MUL", 0.55))
# Mythos S6 (`inst-parity-gap-fixes`): legacy non-uniform scales restored (the
# old single uniform scale squashed peasants to 0.231 wide and guards to 0.5 tall).
PEASANT_SCALE_X = _WB * _US
PEASANT_SCALE_Y = PEASANT_SCALE_X * _WYM
GUARD_SCALE_X = 0.5 * _US
GUARD_SCALE_Y = 0.7 * _US

# Match ``ursina_renderer.PROJECTILE_*`` — instanced arrow billboards + shadow skip via negative scale.w.
PROJECTILE_BILLBOARD_SCALE = 0.075
PROJECTILE_BILLBOARD_Y = ENEMY_SCALE * 0.5

# World-space HP-bar dims per kind: the legacy parent-local spec dims
# (visual_specs.UnitVisualSpec) pre-multiplied by the unit billboard scale
# (legacy bars are children of the scaled billboard parent). (w, h, y_offset).
_HP_BAR_DIMS = {
    "hero": (
        HERO_SPEC.hp_bar_w * HERO_SPEC.scale_x,
        HERO_SPEC.hp_bar_h * HERO_SPEC.scale_y,
        HERO_SPEC.hp_bar_y * HERO_SPEC.scale_y,
    ),
    "enemy": (
        ENEMY_SPEC.hp_bar_w * ENEMY_SPEC.scale_x,
        ENEMY_SPEC.hp_bar_h * ENEMY_SPEC.scale_y,
        ENEMY_SPEC.hp_bar_y * ENEMY_SPEC.scale_y,
    ),
    "peasant": (
        PEASANT_SPEC.hp_bar_w * PEASANT_SPEC.scale_x,
        PEASANT_SPEC.hp_bar_h * PEASANT_SPEC.scale_y,
        PEASANT_SPEC.hp_bar_y * PEASANT_SPEC.scale_y,
    ),
    "guard": (
        GUARD_SPEC.hp_bar_w * GUARD_SPEC.scale_x,
        GUARD_SPEC.hp_bar_h * GUARD_SPEC.scale_y,
        GUARD_SPEC.hp_bar_y * GUARD_SPEC.scale_y,
    ),
    # tax_collector: spec.hp_bar_w == 0 -> never packed (legacy parity).
}


def instanced_units_env_enabled() -> bool:
    """Return True iff ``KINGDOM_URSINA_INSTANCING`` enables the instanced unit path.

    Mythos S6 (``inst-default-flip``): default is "1" (instancing ON) — C7 fixed
    the backface-cull invisibility (set_two_sided) and S6 shipped full overlay/
    correctness parity. Set "0" explicitly for the legacy per-Entity fallback.
    Mirrors ``instanced_nature_renderer.instanced_trees_env_enabled``.
    """
    raw = os.environ.get("KINGDOM_URSINA_INSTANCING", "1")
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def unit_shadows_env_enabled() -> bool:
    """Return True iff ``KINGDOM_UNIT_SHADOWS`` enables the instanced blob shadows.

    WK128: default is "0" (OFF). The legacy per-Entity unit path drew NO unit
    shadows, and the owner dislikes the instanced dark-ellipse blobs — so the
    shadow geom is not even created by default. Set "1" to re-enable for
    future taste-testing.
    """
    raw = os.environ.get("KINGDOM_UNIT_SHADOWS", "0")
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _flip_uv_horizontal(uv: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """Flip a UV region (u_start, v_start, u_width, v_height) horizontally.

    Returns (u_start + u_width, v_start, -u_width, v_height) so the shader
    samples the texture in reverse U order, mirroring the sprite.
    """
    u, v, uw, vh = uv
    return (u + uw, v, -uw, vh)


# --- WK68 R2: base-clip selection from the frozen ``UnitDTO`` ---------------
# These mirror the per-kind ``_*_base_clip`` functions in ``ursina_units_anim``
# byte-for-byte, except they read ``dto.state_name``/``dto.is_inside_building``/
# ``dto.is_alive`` off the frozen DTO instead of off a live sim entity. The DTO
# carries ``state_name = str(getattr(state, "name", state))`` (render_dto.py),
# i.e. the SAME value the entity-reading functions compute, so the clip choice
# is identical — but the renderer no longer touches a live entity.


def _hero_base_clip_dto(dto: "UnitDTO") -> str:
    if dto.is_inside_building:
        return "inside"
    if dto.state_name in ("MOVING", "RETREATING"):
        return "walk"
    return "idle"


def _enemy_base_clip_dto(dto: "UnitDTO") -> str:
    return "walk" if dto.state_name == "MOVING" else "idle"


def _guard_base_clip_dto(dto: "UnitDTO") -> str:
    sn = dto.state_name
    if sn == "DEAD":
        return "dead"
    if sn == "ATTACKING":
        return "attack"
    if sn == "MOVING":
        return "walk"
    return "idle"


def _peasant_base_clip_dto(dto: "UnitDTO") -> str:
    if not dto.is_alive:
        return "dead"
    sn = dto.state_name
    if sn == "DEAD":
        return "dead"
    if sn == "WORKING":
        return "work"
    if sn == "MOVING":
        return "walk"
    return "idle"


def _tax_collector_base_clip_dto(dto: "UnitDTO") -> str:
    sn = dto.state_name
    if sn == "COLLECTING":
        return "collect"
    if sn == "RETURNING":
        return "return"
    if sn == "MOVING_TO_GUILD":
        return "walk"
    if sn == "RESTING_AT_CASTLE":
        return "rest"
    return "idle"


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
        "_hp_bar_buffer",
        "_geom_node_outside",
        "_geom_node_inside",
        "_shadow_geom_node",
        "_hp_bar_geom_node",
        "_initialized",
        "_geom",
        "_unit_anim_state",
        "_interp_pos_by_id",
        "_inside_ids",
        "_facing_by_id",
        "_frame_tick_id",
        "label_sources",
        "_overflow_logged",
    )

    def __init__(self) -> None:
        self._atlas_builder = UnitAtlasBuilder.get()
        self._atlas_tex = None
        self._instance_buffer: Texture | None = None
        self._instance_buffer_inside: Texture | None = None
        self._hp_bar_buffer: Texture | None = None
        self._geom_node_outside: NodePath | None = None
        self._geom_node_inside: NodePath | None = None
        self._shadow_geom_node: NodePath | None = None
        self._hp_bar_geom_node: NodePath | None = None
        self._geom: Geom | None = None
        self._initialized = False
        # Mythos S4/S6 (`label-zoom-lod-pooled`): per-frame label feed for the
        # pooled name/gold Text labels — (kind, dto, blended world pos) tuples,
        # rebuilt every update() from the SAME blended positions packed into the
        # instance buffer so labels never desync from sprites.
        self.label_sources: list = []
        self._overflow_logged = False
        # Mirror ``UrsinaRenderer._compute_anim_frame`` triggers + locomotion timing.
        # Wall-clock in normal play; sim-tick-derived under DETERMINISTIC_SIM (WK67 Wave 5).
        # WK68 R2: all per-unit render state is keyed on the frozen DTO's stable
        # string ``entity_id`` (hero_id/entity_id), never ``id(obj)``.
        self._unit_anim_state: dict[str, dict] = {}
        # Mythos S6 (`inst-linear-interp`): per-unit linear sim-tick interpolation
        # state — [prev_pos, curr_pos, last_tick_id], the same machinery as the
        # legacy `_sync_unit_atlas_billboard` (advance the window on tick
        # boundaries, blend by sim_blend_fraction). Replaces the exponential
        # render trailing that prior art rejected ("lurch then crawl").
        self._interp_pos_by_id: dict[str, list] = {}
        # WK129 (inside-hero pin): hero ids rendered by the inside-building pass
        # LAST frame. Inside heroes are pinned at the building anchor (never
        # interpolated), and on the inside->outside transition the interp window
        # is reset to the new sim position so the sprite SNAPS out instead of
        # lerping from the building anchor (rubberband fix).
        self._inside_ids: set[str] = set()
        # WK68 R2: renderer-OWNED facing per unit (1=right, -1=left), derived from
        # the DTO x-delta — same idiom as the migrated pygame HeroRenderer._facing.
        # Replaces ``_unit_facing_direction`` which mutated the live entity
        # (``entity._ks_facing``/``_ks_last_x``); the renderer no longer writes to
        # sim entities and no longer reads a live entity at all.
        self._facing_by_id: dict[str, tuple[int, float]] = {}
        # WK67 Wave 5: the current frame's sim tick id (set in ``update``); the anim
        # clock derives from it under DETERMINISTIC_SIM so captures are byte-reproducible.
        self._frame_tick_id: int = 0

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        # Use the SAME atlas Texture object as the proven legacy billboard path
        # (UnitAtlasBuilder.get_ursina_texture -> TerrainTextureBridge), not a
        # separate surface->texture converter, so V handling and the sampled
        # atlas band match the legacy `_sync_unit_atlas_billboard`.
        self._atlas_tex = UnitAtlasBuilder.get().get_ursina_texture()
        panda_atlas: Texture = self._atlas_tex._texture
        panda_atlas.set_magfilter(Texture.FT_nearest)
        panda_atlas.set_minfilter(Texture.FT_nearest)

        self._instance_buffer = Texture("unit_instance_data")
        self._instance_buffer.setup_buffer_texture(
            MAX_INSTANCES * TEXELS_PER_INSTANCE,
            Texture.T_float,
            Texture.F_rgba32,
            GeomEnums.UH_dynamic,
        )

        self._instance_buffer_inside = Texture("unit_instance_data_inside")
        self._instance_buffer_inside.setup_buffer_texture(
            MAX_INSIDE_INSTANCES * TEXELS_PER_INSTANCE,
            Texture.T_float,
            Texture.F_rgba32,
            GeomEnums.UH_dynamic,
        )

        # Mythos S6 (`inst-hp-bars`): per-bar buffer — pos+fill / world dims.
        self._hp_bar_buffer = Texture("unit_hp_bar_data")
        self._hp_bar_buffer.setup_buffer_texture(
            MAX_INSTANCES * HP_BAR_TEXELS_PER_INSTANCE,
            Texture.T_float,
            Texture.F_rgba32,
            GeomEnums.UH_dynamic,
        )

        np_outside, geom_out = self._create_instanced_quad("instanced_units_outside")
        self._geom_node_outside = np_outside
        self._geom = geom_out
        np_inside, _ = self._create_instanced_quad("instanced_units_inside")
        self._geom_node_inside = np_inside

        # WK128: blob shadows are OFF by default (legacy drew no unit shadows;
        # owner dislikes the dark ellipses). The geom is only created when
        # KINGDOM_UNIT_SHADOWS=1 — nothing else (picking/bounds/buffers)
        # depends on it; all consumers None-guard.
        if unit_shadows_env_enabled():
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
        # Bind the atlas onto texture stage 0 so the shader's reserved
        # ``p3d_Texture0`` auto-input samples it (mirrors the working legacy
        # ``Entity.texture`` path); priority 1 overrides any default stage tex.
        self._geom_node_outside.set_texture(panda_atlas, 1)
        self._geom_node_outside.set_shader_input("instanceData", self._instance_buffer)
        self._geom_node_outside.set_transparency(TransparencyAttrib.M_alpha)
        self._geom_node_outside.set_depth_write(False)
        self._geom_node_outside.set_bin("transparent", 1)
        # Camera-facing quad is single-sided; disable backface culling or units
        # render invisible from the tilted RTS cam (mirrors shadow geom L227,
        # legacy billboard double_sided, and instanced trees set_two_sided).
        self._geom_node_outside.set_two_sided(True)

        self._geom_node_inside.set_shader(sh)
        self._geom_node_inside.set_texture(panda_atlas, 1)
        self._geom_node_inside.set_shader_input("instanceData", self._instance_buffer_inside)
        self._geom_node_inside.set_transparency(TransparencyAttrib.M_alpha)
        self._geom_node_inside.set_depth_write(False)
        self._geom_node_inside.set_depth_test(False)
        self._geom_node_inside.set_bin("fixed", 100)
        # Same single-sided quad as the outside geom; must not be backface-culled.
        self._geom_node_inside.set_two_sided(True)

        # Mythos S6 (`inst-hp-bars`): one instanced draw for ALL unit HP bars.
        # Render state mirrors the legacy overlay contract (configure_ks_overlay):
        # depth test/write OFF + bin "fixed",110 (WK124 — over buildings at
        # fixed,1 AND the inside-unit pass at fixed,100). No texture needed —
        # the fragment derives the legacy green/red/gray palette from the fill.
        np_bars, _ = self._create_instanced_quad("instanced_units_hp_bars")
        self._hp_bar_geom_node = np_bars
        bsh = instanced_hp_bar_shader._shader
        self._hp_bar_geom_node.set_shader(bsh)
        self._hp_bar_geom_node.set_shader_input("instanceData", self._hp_bar_buffer)
        self._hp_bar_geom_node.set_depth_write(False)
        self._hp_bar_geom_node.set_depth_test(False)
        self._hp_bar_geom_node.set_bin("fixed", 110)
        # C7 invariant: camera-facing instanced quads MUST be two-sided or the
        # tilted RTS camera backface-culls them (the 5-failed-attempts bug).
        self._hp_bar_geom_node.set_two_sided(True)

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

        # GPU instancing: instance positions live in the buffer texture, invisible to
        # Panda's CPU-side frustum culler, which would otherwise cull this whole node
        # (bounds = the base quad at the origin) whenever the camera looks away from
        # the origin -> all units vanish. Force an infinite bound so it's never culled.
        from panda3d.core import OmniBoundingVolume
        node.set_bounds(OmniBoundingVolume())
        node.set_final(True)

        from ursina import scene

        np = NodePath(node)
        np.reparent_to(scene)
        np.set_instance_count(0)
        return np, geom

    def _facing_for_dto(self, dto: "UnitDTO") -> int:
        """Renderer-owned facing (1=right, -1=left) from the DTO x-delta.

        Mirrors the movement branch of the old ``_unit_facing_direction`` and the
        migrated pygame ``HeroRenderer`` facing exactly: sticky facing that flips
        only when |Δx| > 0.01, ``last_x`` updated every call, default 1 on first
        sight. The target-based branch of ``_unit_facing_direction`` is dropped on
        purpose — the frozen DTO carries no live combat target, the same boundary
        choice the pygame hero/enemy renderers already made.
        """
        cur_x = float(dto.x)
        prev = self._facing_by_id.get(dto.entity_id)
        if prev is None:
            self._facing_by_id[dto.entity_id] = (1, cur_x)
            return 1
        facing, last_x = prev
        if abs(cur_x - last_x) > 0.01:
            facing = 1 if (cur_x - last_x) >= 0 else -1
        self._facing_by_id[dto.entity_id] = (facing, cur_x)
        return facing

    def _resolve_unit_anim_clip_frame(
        self,
        dto: "UnitDTO",
        clips: dict[str, AnimationClip],
        base_clip_fn,
    ) -> tuple[str, int]:
        """Same resolution as ``UrsinaRenderer._compute_anim_frame`` minus surface/cache_key.

        WK68 R2: reads the one-shot trigger + monotonic ``anim_trigger_seq`` and the
        base clip off the frozen ``UnitDTO`` (``dto.anim_trigger`` /
        ``dto.anim_trigger_seq``; ``base_clip_fn(dto)``), keyed on the stable string
        ``dto.entity_id`` — never ``id(obj)`` and never a live entity.
        """
        obj_id = dto.entity_id
        # WK66 Move 1a: play one-shots when the sim's monotonic anim_trigger_seq
        # advances vs our renderer-owned last-seen value; never write the trigger
        # back onto the entity.
        trigger = dto.anim_trigger
        trigger_seq = int(dto.anim_trigger_seq or 0)
        # WK67 Wave 5: wall-clock perf_counter in normal play; sim-tick-derived under
        # DETERMINISTIC_SIM (byte-reproducible captures). Same clock as the legacy path.
        now = anim_clock_seconds(self._frame_tick_id)
        st = self._unit_anim_state.get(obj_id)
        last_seq = st.get("last_seq", -1) if st is not None else -1
        if trigger and trigger_seq != last_seq:
            tname = str(trigger)
            if tname in clips:
                base = base_clip_fn(dto)
                oc = clips[tname]
                self._unit_anim_state[obj_id] = {
                    "clip": tname,
                    "t0": now,
                    "base": base,
                    "oneshot": not oc.loop,
                    "last_seq": trigger_seq,
                }
                st = self._unit_anim_state[obj_id]
            elif st is not None:
                st["last_seq"] = trigger_seq

        base = base_clip_fn(dto)
        st = self._unit_anim_state.get(obj_id)
        if st is None:
            self._unit_anim_state[obj_id] = {
                "clip": base,
                "t0": now,
                "base": base,
                "oneshot": False,
                "last_seq": trigger_seq,
            }
            st = self._unit_anim_state[obj_id]
        else:
            st["base"] = base
            if st.get("oneshot"):
                oc_done = clips[st["clip"]]
                elapsed_done = now - st["t0"]
                _, finished = _frame_index_for_clip(oc_done, elapsed_done)
                if finished:
                    st["clip"] = st["base"]
                    st["t0"] = now
                    st["oneshot"] = False
            if not st.get("oneshot"):
                if st["clip"] != base:
                    st["clip"] = base
                    st["t0"] = now

        clip_name = st["clip"]
        clip_obj = clips[clip_name]
        elapsed = now - st["t0"]
        idx, _ = _frame_index_for_clip(clip_obj, elapsed)
        return clip_name, idx

    def _interp_visual_position(
        self,
        obj_id: str,
        wx: float,
        wy: float,
        wz: float,
        tick_id: int,
        blend: float,
    ) -> tuple[float, float, float]:
        """Linear sim-tick interpolation — Mythos S6 ``inst-linear-interp``.

        Byte-matches the legacy ``_sync_unit_atlas_billboard`` Phase 1
        (ursina_renderer.py): the prev/curr window advances on SIM TICK
        boundaries (not on position change — stationary units must converge),
        and the in-between position is ``prev + (curr - prev) * blend`` where
        ``blend`` is the engine's ``sim_blend_fraction``. Snap (no sweep) when
        nearly stationary (< ``INTERP_MIN_DIST_SQ``) or past
        ``INTERP_SNAP_DIST_SQ`` (teleport / building entry). Replaces the
        exponential constant-alpha trailing prior art rejected
        ("lurch then crawl" / hero skip-teleport in the frozen build).
        """
        target = (wx, wy, wz)
        st = self._interp_pos_by_id.get(obj_id)
        if st is None:
            self._interp_pos_by_id[obj_id] = [target, target, tick_id]
            return target
        if st[2] != tick_id:
            st[0] = st[1]
            st[1] = target
            st[2] = tick_id
        prev = st[0]
        curr = st[1]
        dx = curr[0] - prev[0]
        dy = curr[1] - prev[1]
        dz = curr[2] - prev[2]
        dist_sq = dx * dx + dy * dy + dz * dz
        if dist_sq < INTERP_MIN_DIST_SQ or dist_sq > INTERP_SNAP_DIST_SQ:
            return curr
        return (prev[0] + dx * blend, prev[1] + dy * blend, prev[2] + dz * blend)

    def update(
        self,
        snapshot: "SimStateSnapshot",
        frame_tick_id: int = 0,
        *,
        sim_blend: float = 0.0,
        active_layer: int = 0,
        in_view=None,
    ) -> set:
        """Pack snapshot units into outside + inside buffers; return active sim object ids for cleanup.

        ``frame_tick_id`` is the current sim tick (``PresentationFrameState.sim_tick_id``,
        forwarded by ``UrsinaRenderer.update``). The anim FSM derives its clock from it
        under DETERMINISTIC_SIM (WK67 Wave 5), and the Mythos S6 linear interpolation
        advances its prev/curr window on its boundaries.

        Mythos S6 keyword args (legacy-parity, all default-safe for old callers):

        * ``sim_blend`` — the engine's ``sim_blend_fraction``; instance positions
          linearly interpolate between the last two sim-tick positions with it
          (``inst-linear-interp``), exactly like the legacy per-Entity path.
        * ``active_layer`` — the camera's active layer (``r._camera_active_layer``);
          units on other layers are skipped exactly like the legacy layer gate
          (heroes/enemies by ``dto.layer``; peasants/guards/tax-collector are
          surface-only and skip whenever the camera is underground).
        * ``in_view`` — optional ``(sim_x, sim_y) -> bool`` frustum test (the
          renderer's ``_entity_in_view``); used ONLY to filter ``label_sources``
          so the pooled labels spend their budget on on-screen units. Unit
          instances are still packed regardless (GPU clips them — CPU frustum
          culling of instances is not worth the bookkeeping).
        """
        self._frame_tick_id = int(frame_tick_id)
        self._ensure_initialized()
        assert self._instance_buffer is not None
        assert self._instance_buffer_inside is not None
        assert self._hp_bar_buffer is not None
        assert self._geom is not None

        blend = float(sim_blend)
        tick = self._frame_tick_id
        active_layer = int(active_layer)
        # WK68 R2: ids are the DTOs' stable string entity_id (units); the legacy
        # projectile slice still keys on id(proj) (no projectile DTO yet — out of
        # scope), hence the mixed-key set. Both are only used to prune this
        # renderer's own per-id dicts; they never index the Ursina Entity table.
        active_ids: set = set()
        # Mythos S4/S6: fresh per-frame label feed (list reused via clear-by-rebind;
        # tuples reference frozen DTOs — no live sim objects retained past the frame).
        label_sources: list = []
        self.label_sources = label_sources

        buf_out = memoryview(self._instance_buffer.modify_ram_image())
        buf_in = memoryview(self._instance_buffer_inside.modify_ram_image())
        buf_bar = memoryview(self._hp_bar_buffer.modify_ram_image())

        count_outside = 0
        count_inside = 0
        count_bars = 0

        _stride = TEXELS_PER_INSTANCE * BYTES_PER_TEXEL

        def pack_outside(
            vx: float, vy: float, vz: float, scale_x: float, uv, scale_y: float
        ) -> None:
            nonlocal count_outside
            if count_outside >= MAX_INSTANCES:
                self._log_overflow_once()
                return
            offset = count_outside * _stride
            struct.pack_into("ffff", buf_out, offset, vx, vy, vz, scale_x)
            struct.pack_into("ffff", buf_out, offset + BYTES_PER_TEXEL, *uv)
            struct.pack_into(
                "ffff", buf_out, offset + 2 * BYTES_PER_TEXEL, scale_y, 0.0, 0.0, 0.0
            )
            count_outside += 1

        def pack_inside(
            vx: float, vy: float, vz: float, scale_x: float, uv, scale_y: float
        ) -> None:
            nonlocal count_inside
            if count_inside >= MAX_INSIDE_INSTANCES:
                self._log_overflow_once()
                return
            offset = count_inside * _stride
            struct.pack_into("ffff", buf_in, offset, vx, vy, vz, scale_x)
            struct.pack_into("ffff", buf_in, offset + BYTES_PER_TEXEL, *uv)
            struct.pack_into(
                "ffff", buf_in, offset + 2 * BYTES_PER_TEXEL, scale_y, 0.0, 0.0, 0.0
            )
            count_inside += 1

        def pack_hp_bar(vx: float, vy: float, vz: float, hp, max_hp, kind: str) -> None:
            """Mythos S6 `inst-hp-bars`: one bar instance per unit with hp > 0.

            Gating byte-matches legacy ``sync_hp_bar``: spec.hp_bar_w > 0 (so no
            tax-collector bar) and ``max_hp > 0 and hp > 0`` — legacy shows the
            bar for ALL live units, full-health included (a full green bar).
            """
            nonlocal count_bars
            dims = _HP_BAR_DIMS.get(kind)
            if dims is None:
                return
            hp_i = int(hp or 0)
            max_i = int(max_hp or 1)
            if hp_i <= 0 or max_i <= 0:
                return
            if count_bars >= MAX_INSTANCES:
                self._log_overflow_once()
                return
            ratio = hp_i / max_i
            offset = count_bars * HP_BAR_TEXELS_PER_INSTANCE * BYTES_PER_TEXEL
            struct.pack_into("ffff", buf_bar, offset, vx, vy, vz, ratio)
            struct.pack_into(
                "ffff", buf_bar, offset + BYTES_PER_TEXEL, dims[0], dims[1], dims[2], 0.0
            )
            count_bars += 1

        def add_label_source(kind: str, dto, pos) -> None:
            # Pooled-label feed: only on-screen units (legacy disables labels for
            # frustum-culled units; the pool budget goes to visible ones).
            if in_view is not None:
                try:
                    if not in_view(dto.x, dto.y):
                        return
                except Exception:
                    pass
            label_sources.append((kind, dto, pos))

        world = getattr(snapshot, "world", None)
        ts = float(config.TILE_SIZE)
        terrain_ok = _terrain_height_ok()

        # --- Outside pass: surface heroes + enemies + workers (blend into main buffer). ---
        # WK68 R2: iterate the frozen *_dtos tuples; key all per-unit render state on
        # the stable string dto.entity_id; never touch a live sim entity.
        for h in getattr(snapshot, "hero_dtos", ()):
            if not h.is_alive:
                continue
            if h.is_inside_building:
                continue
            # Mythos S6 (`inst-parity-gap-fixes`): legacy layer gate — hide units
            # on a different layer than the camera (ursina_unit_sync.py).
            if int(getattr(h, "layer", 0)) != active_layer:
                continue
            if count_outside >= MAX_INSTANCES:
                break
            hc_key = str(h.hero_class or "warrior").lower()
            clips_h = HeroSpriteLibrary.clips_for(hc_key, size=FRAME_SIZE)
            obj_id = h.entity_id
            clip_name, frame_idx = self._resolve_unit_anim_clip_frame(
                h, clips_h, _hero_base_clip_dto
            )
            uv = self._atlas_builder.lookup_uv("hero", hc_key, clip_name, frame_idx)
            facing = self._facing_for_dto(h)
            if facing < 0:
                uv = _flip_uv_horizontal(uv)
            wx, wz = sim_px_to_world_xz(h.x, h.y)
            # Mythos S6 (`inst-parity-gap-fixes`): terrain-Y like legacy — without
            # it TERRAIN_HEIGHT_SCALE=5.0 buries units into hills.
            terrain_y = get_terrain_height(wx, wz) if terrain_ok else 0.0
            wy = terrain_y + HERO_SCALE * 0.5
            if obj_id in self._inside_ids:
                # WK129 (inside-hero pin): first frame back OUTSIDE after being
                # inside a building — the sim pops the hero out at a new position
                # (building center + 1 tile). Reset the interp window so the
                # sprite SNAPS to the exit position instead of lerping out from
                # the building anchor (the rubberband artifact).
                self._inside_ids.discard(obj_id)
                self._interp_pos_by_id[obj_id] = [(wx, wy, wz), (wx, wy, wz), tick]
                vx, vy, vz = wx, wy, wz
            else:
                vx, vy, vz = self._interp_visual_position(obj_id, wx, wy, wz, tick, blend)
            pack_outside(vx, vy, vz, HERO_SCALE, uv, HERO_SCALE)
            pack_hp_bar(vx, vy, vz, h.hp, h.max_hp, "hero")
            add_label_source("hero", h, (vx, vy, vz))
            active_ids.add(obj_id)

        # --- Enemies (fog visibility + layer gate match legacy) ---
        for e in getattr(snapshot, "enemy_dtos", ()):
            if not e.is_alive:
                continue
            if int(getattr(e, "layer", 0)) != active_layer:
                continue
            if world is not None:
                tx, ty = int(e.x / ts), int(e.y / ts)
                if 0 <= ty < world.height and 0 <= tx < world.width:
                    if world.visibility[ty][tx] != Visibility.VISIBLE:
                        continue
            if count_outside >= MAX_INSTANCES:
                break
            et_key = str(e.enemy_type or "goblin").lower()
            clips_e = EnemySpriteLibrary.clips_for(et_key, size=FRAME_SIZE)
            obj_id = e.entity_id
            clip_name, frame_idx = self._resolve_unit_anim_clip_frame(
                e, clips_e, _enemy_base_clip_dto
            )
            uv = self._atlas_builder.lookup_uv("enemy", et_key, clip_name, frame_idx)
            facing_e = self._facing_for_dto(e)
            if facing_e < 0:
                uv = _flip_uv_horizontal(uv)
            wx, wz = sim_px_to_world_xz(e.x, e.y)
            terrain_y = get_terrain_height(wx, wz) if terrain_ok else 0.0
            # WK137: honor per-enemy `size` so bosses render larger (one mul/div,
            # no allocation — this is the per-frame hot loop).
            e_scale = enemy_billboard_scale(e.size)
            wy = terrain_y + e_scale * 0.5
            vx, vy, vz = self._interp_visual_position(obj_id, wx, wy, wz, tick, blend)
            pack_outside(vx, vy, vz, e_scale, uv, e_scale)
            pack_hp_bar(vx, vy, vz, e.hp, e.max_hp, "enemy")
            add_label_source("enemy", e, (vx, vy, vz))
            active_ids.add(obj_id)

        # --- Workers (peasants / builder variant — animated UVs like guards).
        # Peasants/guards/tax-collector are surface-only (legacy: hidden when the
        # camera layer is underground).
        if active_layer == 0:
            for p in getattr(snapshot, "peasant_dtos", ()):
                if not p.is_alive:
                    continue
                if p.is_inside_castle:
                    continue
                if count_outside >= MAX_INSTANCES:
                    break
                wk = str(p.render_worker_type or "peasant")
                clips_p = WorkerSpriteLibrary.clips_for(wk, size=FRAME_SIZE)
                oid = p.entity_id
                clip_name, frame_idx = self._resolve_unit_anim_clip_frame(
                    p, clips_p, _peasant_base_clip_dto
                )
                uv = self._atlas_builder.lookup_uv("worker", wk, clip_name, frame_idx)
                wx, wz = sim_px_to_world_xz(p.x, p.y)
                terrain_y = get_terrain_height(wx, wz) if terrain_ok else 0.0
                wy = terrain_y + PEASANT_SCALE_Y * 0.5
                vx, vy, vz = self._interp_visual_position(oid, wx, wy, wz, tick, blend)
                # Legacy non-uniform peasant scale (0.42 x 0.231 pre-_US).
                pack_outside(vx, vy, vz, PEASANT_SCALE_X, uv, PEASANT_SCALE_Y)
                pack_hp_bar(vx, vy, vz, p.hp, p.max_hp, "peasant")
                add_label_source("peasant", p, (vx, vy, vz))
                active_ids.add(oid)

            for g in getattr(snapshot, "guard_dtos", ()):
                if not g.is_alive:
                    continue
                if count_outside >= MAX_INSTANCES:
                    break
                clips_g = WorkerSpriteLibrary.clips_for("guard", size=FRAME_SIZE)
                oid = g.entity_id
                clip_name, frame_idx = self._resolve_unit_anim_clip_frame(
                    g, clips_g, _guard_base_clip_dto
                )
                uv = self._atlas_builder.lookup_uv("worker", "guard", clip_name, frame_idx)
                wx, wz = sim_px_to_world_xz(g.x, g.y)
                terrain_y = get_terrain_height(wx, wz) if terrain_ok else 0.0
                wy = terrain_y + GUARD_SCALE_Y * 0.5
                vx, vy, vz = self._interp_visual_position(oid, wx, wy, wz, tick, blend)
                # Legacy non-uniform guard scale (0.5 x 0.7 pre-_US) — the old
                # uniform 0.5 squashed guards short.
                pack_outside(vx, vy, vz, GUARD_SCALE_X, uv, GUARD_SCALE_Y)
                pack_hp_bar(vx, vy, vz, g.hp, g.max_hp, "guard")
                add_label_source("guard", g, (vx, vy, vz))
                active_ids.add(oid)

            tc = getattr(snapshot, "tax_collector_dto", None)
            if tc is not None and tc.is_alive and count_outside < MAX_INSTANCES:
                clips_tc = WorkerSpriteLibrary.clips_for("tax_collector", size=FRAME_SIZE)
                oid = tc.entity_id
                clip_name, frame_idx = self._resolve_unit_anim_clip_frame(
                    tc, clips_tc, _tax_collector_base_clip_dto
                )
                uv = self._atlas_builder.lookup_uv("worker", "tax_collector", clip_name, frame_idx)
                wx, wz = sim_px_to_world_xz(tc.x, tc.y)
                terrain_y = get_terrain_height(wx, wz) if terrain_ok else 0.0
                wy = terrain_y + PEASANT_SCALE_Y * 0.5
                vx, vy, vz = self._interp_visual_position(oid, wx, wy, wz, tick, blend)
                # No HP bar (TAX_COLLECTOR_SPEC.hp_bar_w == 0 — legacy parity).
                pack_outside(vx, vy, vz, PEASANT_SCALE_X, uv, PEASANT_SCALE_Y)
                add_label_source("tax_collector", tc, (vx, vy, vz))
                active_ids.add(oid)

        # --- VFX projectiles (outside buffer only; negative scale.w skips blob shadow shader). ---
        # Mythos S6 (`inst-parity-gap-fixes`): per-kind atlas frames (WK124 wizard
        # "magic" + cleric "heal" orbs no longer render as arrows) + terrain-Y
        # (legacy adds get_terrain_height under PROJECTILE_BILLBOARD_Y).
        uv_proj_by_kind = {
            "arrow": self._atlas_builder.lookup_uv("vfx", "projectile", "arrow", 0),
            "magic": self._atlas_builder.lookup_uv("vfx", "projectile", "magic", 0),
            "heal": self._atlas_builder.lookup_uv("vfx", "projectile", "heal", 0),
        }
        for proj in getattr(snapshot, "vfx_projectiles", ()) or ():
            if count_outside >= MAX_INSTANCES:
                break
            pkind = str(getattr(proj, "kind", "arrow") or "arrow")
            uv_proj = uv_proj_by_kind.get(pkind, uv_proj_by_kind["arrow"])
            wx, wz = sim_px_to_world_xz(proj.x, proj.y)
            terrain_y = get_terrain_height(wx, wz) if terrain_ok else 0.0
            wy = terrain_y + PROJECTILE_BILLBOARD_Y
            oid = id(proj)
            pack_outside(
                wx, wy, wz, -PROJECTILE_BILLBOARD_SCALE, uv_proj, PROJECTILE_BILLBOARD_SCALE
            )
            active_ids.add(oid)

        # --- Inside-building heroes (fixed bin draws after terrain/buildings). ---
        for h in getattr(snapshot, "hero_dtos", ()):
            if not h.is_alive:
                continue
            if not h.is_inside_building:
                continue
            if int(getattr(h, "layer", 0)) != active_layer:
                continue
            if count_inside >= MAX_INSIDE_INSTANCES:
                break
            hc_key = str(h.hero_class or "warrior").lower()
            clips_h = HeroSpriteLibrary.clips_for(hc_key, size=FRAME_SIZE)
            obj_id = h.entity_id
            clip_name, frame_idx = self._resolve_unit_anim_clip_frame(
                h, clips_h, _hero_base_clip_dto
            )
            uv = self._atlas_builder.lookup_uv("hero", hc_key, clip_name, frame_idx)
            facing_in = self._facing_for_dto(h)
            if facing_in < 0:
                uv = _flip_uv_horizontal(uv)
            # WK129 (inside-hero pin): legacy renders an inside hero as a
            # STATIONARY billboard pinned ON the building (the pygame legacy
            # path literally anchors at ``inside_building_center``; the sim also
            # teleports the hero's x/y to the building center on entry). The
            # instanced path must NOT interpolate this teleport: lerping the
            # entry jump sweeps the sprite across the facade (and an in/out
            # flap lerps back and forth = the rubberband bug). Pin at the
            # building anchor (fall back to the sim position, which equals the
            # center once inside) and RESET the interp window to the anchor so
            # there is nothing stale to lerp from. Y stays terrain + half
            # billboard height — the exact Y legacy uses for inside heroes
            # (ursina_unit_sync.sync_snapshot_heroes).
            anchor = getattr(h, "inside_building_center", None)
            ax, ay = (float(anchor[0]), float(anchor[1])) if anchor is not None else (h.x, h.y)
            wx, wz = sim_px_to_world_xz(ax, ay)
            terrain_y = get_terrain_height(wx, wz) if terrain_ok else 0.0
            wy = terrain_y + HERO_SCALE * 0.5
            vx, vy, vz = wx, wy, wz
            self._interp_pos_by_id[obj_id] = [(vx, vy, vz), (vx, vy, vz), tick]
            self._inside_ids.add(obj_id)
            pack_inside(vx, vy, vz, HERO_SCALE, uv, HERO_SCALE)
            # Legacy shows HP bar + name/gold labels for inside heroes too (the
            # hero sync loop does not skip them); bars draw at fixed,110 over
            # the inside pass at fixed,100 — same stacking as legacy.
            pack_hp_bar(vx, vy, vz, h.hp, h.max_hp, "hero")
            add_label_source("hero", h, (vx, vy, vz))
            active_ids.add(obj_id)

        assert self._geom_node_outside is not None
        assert self._geom_node_inside is not None
        assert self._hp_bar_geom_node is not None
        self._geom_node_outside.set_instance_count(count_outside)
        self._geom_node_inside.set_instance_count(count_inside)
        # WK128: shadow geom only exists when KINGDOM_UNIT_SHADOWS=1.
        if self._shadow_geom_node is not None:
            self._shadow_geom_node.set_instance_count(count_outside)
        self._hp_bar_geom_node.set_instance_count(count_bars)
        self._instance_buffer.reload()
        self._instance_buffer_inside.reload()
        self._hp_bar_buffer.reload()

        for oid in list(self._unit_anim_state.keys()):
            if oid not in active_ids:
                self._unit_anim_state.pop(oid, None)

        for oid in list(self._interp_pos_by_id.keys()):
            if oid not in active_ids:
                self._interp_pos_by_id.pop(oid, None)

        for oid in list(self._facing_by_id.keys()):
            if oid not in active_ids:
                self._facing_by_id.pop(oid, None)

        # WK129: drop inside-state for heroes that no longer render (death /
        # despawn while inside) so a recycled id can't trigger a bogus exit-snap.
        self._inside_ids.intersection_update(active_ids)

        return active_ids

    def _log_overflow_once(self) -> None:
        if not self._overflow_logged:
            self._overflow_logged = True
            try:
                print(
                    "[mythos] instanced-unit buffer overflow: instance cap "
                    f"({MAX_INSTANCES} outside / {MAX_INSIDE_INSTANCES} inside) "
                    "reached — excess units/bars skipped this frame",
                    flush=True,
                )
            except Exception:
                pass

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
            offset = i * TEXELS_PER_INSTANCE * BYTES_PER_TEXEL
            struct.pack_into("ffff", buf, offset, px, py, pz, scale)
            struct.pack_into("ffff", buf, offset + BYTES_PER_TEXEL, *uv_region)
            struct.pack_into(
                "ffff", buf, offset + 2 * BYTES_PER_TEXEL, abs(scale), 0.0, 0.0, 0.0
            )

        assert self._geom_node_outside is not None
        assert self._geom_node_inside is not None
        assert self._hp_bar_geom_node is not None
        self._geom_node_outside.set_instance_count(n)
        self._geom_node_inside.set_instance_count(0)
        # WK128: shadow geom only exists when KINGDOM_UNIT_SHADOWS=1.
        if self._shadow_geom_node is not None:
            self._shadow_geom_node.set_instance_count(n)
        self._hp_bar_geom_node.set_instance_count(0)
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
        self._interp_pos_by_id.clear()
        self._inside_ids.clear()
        self._facing_by_id.clear()
        self.label_sources = []
        if self._geom_node_outside is not None:
            self._geom_node_outside.remove_node()
            self._geom_node_outside = None
        if self._geom_node_inside is not None:
            self._geom_node_inside.remove_node()
            self._geom_node_inside = None
        if self._shadow_geom_node is not None:
            self._shadow_geom_node.remove_node()
            self._shadow_geom_node = None
        if self._hp_bar_geom_node is not None:
            self._hp_bar_geom_node.remove_node()
            self._hp_bar_geom_node = None
        self._geom = None
        self._initialized = False
