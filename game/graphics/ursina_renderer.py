"""
Translates the GameEngine simulation state into Ursina 3D entities.

Perspective view: floor plane is X/Z (Y up). Simulation pixels (x, y) map to
(world_x, world_z) with world_z = -px_y / SCALE so screen-north stays intuitive
(PM WK19 decision).

v1.5 Sprint 1.2 (Agent 03): Terrain is built from discrete 3D meshes under
``assets/models/environment/`` (grass/path_stone road tiles + water tint + tree/rock props), parented
under one root Entity — no TileSpriteLibrary bake or terrain atlas.

Most buildings use BuildingSpriteLibrary on a single billboard quad; **castle**, **house**,
and **lair** (if no ``lair_v1.json`` prefab) use static 3D meshes from ``assets/models/environment/`` (v1.5 Sprint 2.1). When ``lair_v1.json`` exists, lairs use the prefab path (Graveyard kitbash).
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
from pathlib import Path
from typing import TYPE_CHECKING

import pygame
import config
from ursina import Entity, Vec2, Vec3, color, Text, scene, camera
from ursina.lights import AmbientLight, DirectionalLight
from ursina.shaders import lit_with_shadows_shader, unlit_shader

from game.graphics.animation import AnimationClip
from game.graphics.building_sprites import BuildingSpriteLibrary
from game.graphics.enemy_sprites import EnemySpriteLibrary
from game.graphics.hero_sprites import HeroSpriteLibrary, HeroSpriteSpec
from game.graphics.terrain_texture_bridge import TerrainTextureBridge
from game.graphics.ursina_sprite_unlit_shader import sprite_unlit_shader
from game.graphics.vfx import get_projectile_billboard_surface
from game.graphics.worker_sprites import WorkerSpriteLibrary
from game.world import TileType, Visibility

if TYPE_CHECKING:
    from game.sim.snapshot import SimStateSnapshot

# Fallback tint when hero class is unresolved or texture upload fails — match Warrior shirt (HeroSpriteSpec).
COLOR_HERO = color.rgb(180 / 255.0, 45 / 255.0, 45 / 255.0)
COLOR_ENEMY = color.red
COLOR_BUILDING = color.light_gray
COLOR_CASTLE = color.gold
COLOR_LAIR = color.brown


# 1 world unit along the floor == 1 tile == 32 px (scale lives in ursina_coords)
from game.graphics.ursina_coords import SCALE, px_to_world, sim_px_to_world_xz

# v1.5 Sprint 1.2: uniform scale for Kenney OBJ tiles (1×1 plane ≈ one sim tile).
TERRAIN_SCALE_MULTIPLIER = 1.0
# Props sit on the same grid; tune if authored mesh bounds drift.
# Trees are *not* part of the WK34 ground-scatter 4× pass (only rocks + grass clumps).
# Kenney tree GLBs are already tall; keep this near 1.0 to avoid "massive" canopy scale.
TREE_SCALE_MULTIPLIER = 1.15
ROCK_SCALE_MULTIPLIER = 1.68  # 4× of pre-WK34 0.42
# Grass tiles use organic scatter doodads on the base plane, not full-tile voxels.
GRASS_SCATTER_SCALE_MULTIPLIER = 2.08  # 4× of pre-WK34 0.52
# Flower / log / mushroom mesh instances: half the scatter scale of other ground props (2× original vs 4×).
GROUND_PROP_FLOWER_LOG_MUSHROOM_SCALE = 0.5

# Pixel billboard height in world units; scales with UNIT_SPRITE_PIXELS so larger raster reads larger on screen.
_US = float(getattr(config, "UNIT_SPRITE_PIXELS", config.TILE_SIZE)) / float(config.TILE_SIZE)
UNIT_BILLBOARD_SCALE = 0.62 * _US

# Stable bridge keys — never use id(surface) alone for multi-megapixel sheets (see terrain_texture_bridge).
_FOG_TEX_KEY = "kingdom_ursina_fog_overlay"

ENEMY_SCALE = 0.5 * _US
_WB = float(getattr(config, "URSINA_WORKER_BILLBOARD_BASE", 0.42))
_WYM = float(getattr(config, "URSINA_WORKER_BILLBOARD_Y_SCALE_MUL", 0.55))
PEASANT_SCALE_XZ = _WB * _US
PEASANT_SCALE_Y = PEASANT_SCALE_XZ * _WYM
# Instanced path uses a single uniform scale — approximate squashed height.
PEASANT_SCALE = PEASANT_SCALE_Y
GUARD_SCALE_XZ = 0.5 * _US
GUARD_SCALE_Y = 0.7 * _US

# Ranged VFX billboards — smaller than unit sprites, readable in perspective.
# 0.3 was large in playtest; 25% of that keeps arrows visible (snapshot + depth fix) without dominating the frame.
PROJECTILE_BILLBOARD_SCALE = 0.075
# Vertical lift: match enemy sprite center (ENEMY_SCALE*0.5) so arrows aren't drawn under terrain.
PROJECTILE_BILLBOARD_Y = ENEMY_SCALE * 0.5

# Debug toggle: render all POIs regardless of discovery state (dev/testing aid).
_debug_show_pois = os.environ.get("KINGDOM_DEBUG_SHOW_ALL_POIS", "").strip().lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# R5 Phase 2 (Agent 03): Building label display names for native Ursina text
# ---------------------------------------------------------------------------
_BUILDING_LABEL_MAP: dict[str, str] = {
    "castle": "CASTLE",
    "warrior_guild": "WARRIORS",
    "ranger_guild": "RANGERS",
    "rogue_guild": "ROGUES",
    "wizard_guild": "WIZARDS",
    "market": "MARKET",
    "blacksmith": "SMITH",
    "inn": "INN",
    "trading_post": "TRADE",
    "guard_tower": "GUARDS",
    "house": "HOUSE",
    "farm": "FARM",
    "palace": "PALACE",
    "ballista_tower": "BALLISTA",
    "wizard_tower": "WIZ TOWER",
    "fairground": "FAIR",
    "library": "LIBRARY",
    "gardens": "GARDENS",
    "gnome_hovel": "GNOMES",
    "elven_bungalow": "ELVES",
    "dwarven_settlement": "DWARVES",
    # Temples
    "temple_agrela": "AGRELA",
    "temple_dauros": "DAUROS",
    "temple_fervus": "FERVUS",
    "temple_helia": "HELIA",
    "temple_krolm": "KROLM",
    "temple_lunord": "LUNORD",
    "temple_krypta": "KRYPTA",
}


def _sync_building_worldspace_ui(b, bts: str, ent, is_lair: bool) -> None:
    """R5 Phase 2 (Agent 03): Attach/update label, HP bar, and gold display
    as native Ursina child entities on a building entity.

    Skips POI buildings and lairs — only normal player-built buildings get labels.
    """
    # Skip POIs (discovery-gated) and lairs (enemy structures)
    if getattr(b, "is_poi", False) or is_lair:
        return

    # --- Building label ---
    label_ent = getattr(ent, '_ks_label', None)
    if label_ent is None:
        label_text = _BUILDING_LABEL_MAP.get(bts, bts.upper())
        label_ent = Text(
            text=label_text, parent=ent, origin=(0, 0), scale=15,
            color=color.white, billboard=True, y=1.2,
        )
        ent._ks_label = label_ent

    # --- Building HP bar (show only when damaged) ---
    b_hp = int(getattr(b, 'hp', 0) or 0)
    b_max_hp = int(getattr(b, 'max_hp', 1) or 1)
    hp_bar_ent = getattr(ent, '_ks_hp_bar', None)
    if b_max_hp > 0 and b_hp > 0 and b_hp < b_max_hp:
        ratio = b_hp / b_max_hp
        if hp_bar_ent is None:
            hp_bar_ent = Entity(parent=ent, model='quad',
                color=color.green if ratio > 0.5 else color.red,
                scale=(1.0 * ratio, 0.05, 1), y=1.5, billboard=True, unlit=True)
            hp_bar_ent.set_depth_test(False)
            ent._ks_hp_bar = hp_bar_ent
        else:
            hp_bar_ent.scale_x = ratio
            hp_bar_ent.color = color.green if ratio > 0.5 else color.red
            hp_bar_ent.enabled = True
    elif hp_bar_ent is not None:
        hp_bar_ent.enabled = False

    # --- Gold display (show when building has gold stash) ---
    stash = int(getattr(b, 'stash_gold', 0) or getattr(b, 'stored_tax_gold', 0) or 0)
    gold_ent = getattr(ent, '_ks_gold_label', None)
    if stash > 0:
        text = f"${stash}"
        if gold_ent is None:
            gold_ent = Text(text=text, parent=ent, origin=(0, 0), scale=12,
                color=color.rgb(1.0, 0.8, 0.2), billboard=True, y=0.9)
            ent._ks_gold_label = gold_ent
        else:
            if gold_ent.text != text:
                gold_ent.text = text
            gold_ent.enabled = True
    elif gold_ent is not None:
        gold_ent.enabled = False


def _unit_raster_px() -> int:
    return int(getattr(config, "UNIT_SPRITE_PIXELS", config.TILE_SIZE))

# ---------------------------------------------------------------------------
# Helpers imported from focused sub-modules (extracted WK41, wired WK42)
# ---------------------------------------------------------------------------
from game.graphics.ursina_environment import (
    PROJECT_ROOT,
    _environment_model_path,
    _grass_scatter_jitter,
    _grass_density_budget,
    _grass_tile_selected,
    _grass_clump_offset,
    _environment_mesh_priority,
    _dedupe_env_rels_by_stem,
    _is_grass_scatter_stem,
    _is_doodad_scatter_stem,
    _stem_is_flower_ground_scatter,
    _stem_is_log_or_mushroom_ground_scatter,
    _environment_grass_and_doodad_model_lists,
    _environment_tree_model_list,
    _scatter_model_index,
    _building_occupied_tiles,
    _apply_kenney_scatter_mesh_shading_only,
    _finalize_kenney_scatter_entity,
    _set_static_prop_fog_tint,
    _visibility_signature,
)
from game.graphics.ursina_prefabs import (
    _PREFAB_FIT_INSET,
    _building_type_str,
    _footprint_tiles,
    _is_3d_mesh_building,
    _mesh_kind_for_building,
    _building_3d_origin_y,
    _footprint_scale_3d,
    _building_height_y,
    _stage_prefab_path_candidates,
    _plot_prefab_candidates,
    _first_existing,
    _first_existing_groups,
    _resolve_construction_staged_prefab,
    _resolve_prefab_path,
    _load_prefab_instance,
)
from game.graphics.ursina_units_anim import (
    _frame_index_for_clip,
    _guard_base_clip,
    _hero_base_clip,
    _enemy_base_clip,
    _peasant_base_clip,
    _tax_collector_base_clip,
    _unit_facing_direction,
)

from game.graphics.terrain_height import get_terrain_height, is_initialized as _terrain_height_ok
from game.graphics.unit_atlas import UnitAtlasBuilder, ATLAS_SIZE, FRAME_SIZE
from game.graphics.ursina_entity_render_collab import UrsinaEntityRenderCollab
from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab

class UrsinaRenderer:
    def __init__(self, world):
        self._world = world

        # Entity mappings: simulation object id() -> Ursina Entity
        self._entities = {}
        # WK44 Stage 2: dynamic trees keyed by tile (tx,ty) for growth scaling.
        self._tree_entities: dict[tuple[int, int], Entity] = {}
        # WK46 Stage 3: log pile entities keyed by tile (tx,ty).
        self._log_stack_entities: dict[tuple[int, int], Entity] = {}
        # WK55: POI mystery "?" marker entities, keyed by POI id().
        self._poi_mystery_markers: dict[int, Entity] = {}

        # R4: sim interpolation state for linear position interpolation
        self._frame_blend: float = 0.0
        self._frame_tick_id: int = -1

        # v1.5: parent Entity for per-tile 3D terrain meshes (see _build_3d_terrain).
        self._terrain_entity: Entity | None = None
        # WK53 R3: the heightmap-displaced ground mesh — fog shader updates target this.
        self._terrain_ground_entity: Entity | None = None

        # WK30 debug: tile-gridline overlay entity (populated once when env flag is set).
        self._grid_debug_entity: Entity | None = None

        # Fog-of-war overlay quad (WK22): matches pygame render_fog tints per visibility tile.
        self._fog_entity: Entity | None = None
        self._fog_full_surf: pygame.Surface | None = None
        # RGBA tile buffer reused for fog rebuilds (WK22 R3 perf: avoid 22k pygame.set_at calls).
        self._fog_tile_buf: bytearray | None = None
        self._visibility_gated_terrain: list[tuple[Entity, int, int]] = []
        self._visibility_gated_terrain_by_tile: dict[tuple[int, int], list[Entity]] = {}
        self._terrain_visibility_revision_seen = -1
        self._terrain_visible_tiles_seen: set[tuple[int, int]] | None = None

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
        # Atlas renderer: cached clips metadata per (unit_type, class_key).
        self._clips_cache: dict[tuple[str, str], dict] = {}

        # --- v1.5: base lighting for 3D meshes (flat-shaded, optional shadows) ---
        self._directional_light = None
        self._shadow_bounds_initialized = False
        self._setup_scene_lighting()

        self._terrain_fog = UrsinaTerrainFogCollab(self)
        self._entity_render = UrsinaEntityRenderCollab(self)

    def _setup_scene_lighting(self) -> None:
        """Dim gray-blue ambient + warm directional sun; directional casts shadow maps when enabled.

        Billboards keep unlit_shader + shadow-mask hide; lit 3D terrain/props use default_shader
        from UrsinaApp (lit_with_shadows when URSINA_DIRECTIONAL_SHADOWS is True).
        """
        try:
            from ursina import color as ucolor

            world = self._world
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
        upx = _unit_raster_px()
        _spec = HeroSpriteSpec(size=upx)
        cache_key = (
            cache_prefix,
            "anim",
            class_key,
            clip_name,
            idx,
            upx,
            hash(_spec),
        )
        return surf, cache_key

    # ------------------------------------------------------------------
    # Atlas-based UV rendering (WK59 perf): single shared texture, UV offsets
    # ------------------------------------------------------------------

    def _get_cached_clips(self, unit_type: str, class_key: str) -> dict:
        """Return cached animation clips metadata. Avoids per-frame clips_for() calls."""
        cache_key = (unit_type, class_key)
        if cache_key not in self._clips_cache:
            size = _unit_raster_px()
            if unit_type == "hero":
                self._clips_cache[cache_key] = HeroSpriteLibrary.clips_for(class_key, size=size)
            elif unit_type == "enemy":
                self._clips_cache[cache_key] = EnemySpriteLibrary.clips_for(class_key, size=size)
            else:
                self._clips_cache[cache_key] = WorkerSpriteLibrary.clips_for(class_key, size=size)
        return self._clips_cache[cache_key]

    def _compute_anim_frame(self, obj_id, entity, unit_type: str, class_key: str, base_clip_fn) -> tuple:
        """Compute current animation clip name and frame index. Uses perf_counter for precision."""
        trigger = getattr(entity, "_ursina_anim_trigger", None) or getattr(
            entity, "_render_anim_trigger", None
        )

        base = base_clip_fn(entity)
        st = self._unit_anim_state.get(obj_id)
        now = time.perf_counter()

        if trigger:
            tname = str(trigger)
            setattr(entity, "_ursina_anim_trigger", None)
            setattr(entity, "_render_anim_trigger", None)
            clips = self._get_cached_clips(unit_type, class_key)
            if tname in clips:
                self._unit_anim_state[obj_id] = {
                    "clip": tname,
                    "t0": now,
                    "base": base,
                    "oneshot": not clips[tname].loop,
                }
                st = self._unit_anim_state[obj_id]

        if st is None:
            self._unit_anim_state[obj_id] = {
                "clip": base, "t0": now, "base": base, "oneshot": False
            }
            st = self._unit_anim_state[obj_id]
        else:
            st["base"] = base
            if st.get("oneshot"):
                clips = self._get_cached_clips(unit_type, class_key)
                oc = clips.get(st["clip"])
                if oc:
                    elapsed_done = now - st["t0"]
                    _i, finished = _frame_index_for_clip(oc, elapsed_done)
                    if finished:
                        st["clip"] = base
                        st["t0"] = now
                        st["oneshot"] = False
            if not st.get("oneshot"):
                if st["clip"] != base:
                    st["clip"] = base
                    st["t0"] = now

        clip_name = st["clip"]
        clips = self._get_cached_clips(unit_type, class_key)
        clip = clips.get(clip_name)
        if clip is None:
            return base, 0
        elapsed = now - st["t0"]
        idx, _fin = _frame_index_for_clip(clip, elapsed)
        return clip_name, idx

    def _sync_unit_atlas_billboard(
        self, ent, obj_id, entity, unit_type: str, class_key: str,
        base_clip_fn, tint_col, scale_xyz, pos_xyz, shader
    ) -> None:
        """Update a unit billboard using atlas UV coords instead of per-frame texture swap."""
        atlas = UnitAtlasBuilder.get()
        atlas_tex = atlas.get_ursina_texture()

        # Set atlas texture once (on first frame or if missing)
        if getattr(ent, "_ks_atlas_tex_set", False) is False:
            ent.texture = atlas_tex
            ent.texture_scale = (FRAME_SIZE / ATLAS_SIZE, FRAME_SIZE / ATLAS_SIZE)
            ent._ks_atlas_tex_set = True

        # --- Phase 1: Position interpolation (runs every frame) ---
        # Advance the interpolation window on sim tick boundaries, not on
        # position change — otherwise stationary entities never converge
        # (prev stays stale and blend cycling causes visual oscillation).
        last_tick = getattr(ent, "_ks_last_tick_id", -1)
        if last_tick != self._frame_tick_id:
            ent._ks_prev_sim_pos = getattr(ent, "_ks_curr_sim_pos", pos_xyz)
            ent._ks_curr_sim_pos = pos_xyz
            ent._ks_last_tick_id = self._frame_tick_id

        prev_sim = getattr(ent, "_ks_prev_sim_pos", pos_xyz)
        curr_sim = getattr(ent, "_ks_curr_sim_pos", pos_xyz)

        dx = curr_sim[0] - prev_sim[0]
        dy = curr_sim[1] - prev_sim[1]
        dz = curr_sim[2] - prev_sim[2]
        dist_sq = dx * dx + dy * dy + dz * dz

        if dist_sq < 0.0001 or dist_sq > 9.0:
            interp_pos = curr_sim
        else:
            t = self._frame_blend
            interp_pos = (
                prev_sim[0] + dx * t,
                prev_sim[1] + dy * t,
                prev_sim[2] + dz * t,
            )

        if getattr(ent, "_ks_last_pos", None) != interp_pos:
            ent.position = interp_pos
            ent._ks_last_pos = interp_pos

        # --- Phase 2: Appearance updates (skippable when unchanged) ---
        clip_name, frame_idx = self._compute_anim_frame(
            obj_id, entity, unit_type, class_key, base_clip_fn
        )

        appearance_key = (clip_name, frame_idx, scale_xyz)
        if getattr(ent, '_ks_last_appearance_key', None) == appearance_key:
            return
        ent._ks_last_appearance_key = appearance_key

        # Update UV offset
        uv = atlas.lookup_uv(unit_type, class_key, clip_name, frame_idx)
        new_offset = (uv[0], 1.0 - uv[1] - uv[3])
        if getattr(ent, "_ks_last_uv_offset", None) != new_offset:
            ent.texture_offset = new_offset
            ent._ks_last_uv_offset = new_offset

        # Update scale (with guard)
        if getattr(ent, "_ks_last_scale", None) != scale_xyz:
            ent.scale = scale_xyz
            ent._ks_last_scale = scale_xyz

        # Color (with guard)
        target_color = color.white if atlas_tex is not None else tint_col
        if getattr(ent, "_ks_last_color", None) != target_color:
            ent.color = target_color
            ent._ks_last_color = target_color

        # Billboard + shader (one-time setup)
        if not getattr(ent, "_ks_billboard_configured", False):
            ent.billboard = True
            UrsinaEntityRenderCollab.apply_pixel_billboard_settings(ent)
            ent._ks_billboard_configured = True
        UrsinaEntityRenderCollab.set_shader_if_changed(ent, shader)

    # ------------------------------------------------------------------
    # Camera frustum culling helpers (WK59 perf: skip off-screen entities)
    # ------------------------------------------------------------------

    def _get_visible_tile_rect(self) -> tuple[int, int, int, int]:
        """Return (min_tx, min_ty, max_tx, max_ty) of tiles visible to the camera.

        Traces the camera's forward ray to the Y=0 ground plane to find the
        actual center of the visible area regardless of camera tilt/orbit angle.
        Includes a 5-tile margin to prevent pop-in during panning.
        Falls back to the full map if camera is unavailable (first frame).
        """
        map_w = int(config.MAP_WIDTH)
        map_h = int(config.MAP_HEIGHT)
        full_rect = (0, 0, map_w - 1, map_h - 1)
        try:
            cam_pos = camera.world_position
            if cam_pos is None:
                return full_rect
            cam_y = float(cam_pos.y)
            if cam_y <= 0:
                return full_rect

            # Compute where the camera's forward ray hits the Y=0 ground plane.
            # This gives the actual center of the visible area regardless of tilt.
            cam_fwd = camera.forward
            fwd_y = float(cam_fwd.y)
            if fwd_y >= -0.01:
                # Camera is looking up or horizontal — can't determine ground target
                return full_rect

            t = -cam_y / fwd_y
            ground_x = float(cam_pos.x) + t * float(cam_fwd.x)
            ground_z = float(cam_pos.z) + t * float(cam_fwd.z)

            # Convert ground hit to tile coords (world_z = -sim_y / SCALE, so tile_y = -ground_z)
            center_tile_x = int(ground_x)
            center_tile_y = int(-ground_z)

            # Generous radius: camera height × 1.8, minimum 30 tiles.
            # Oblique views see further than top-down, so be generous.
            view_radius = max(int(cam_y * 1.8), 30)
            margin = 5
            half = view_radius + margin

            min_tx = max(0, center_tile_x - half)
            min_ty = max(0, center_tile_y - half)
            max_tx = min(map_w - 1, center_tile_x + half)
            max_ty = min(map_h - 1, center_tile_y + half)
            return (min_tx, min_ty, max_tx, max_ty)
        except Exception:
            return full_rect

    def _entity_in_view(self, sim_x: float, sim_y: float) -> bool:
        """Check if an entity at sim pixel coords is within the cached visible rect."""
        tile_size = float(config.TILE_SIZE)
        tx = int(sim_x / tile_size)
        ty = int(sim_y / tile_size)
        rect = self._frame_visible_rect
        return rect[0] <= tx <= rect[2] and rect[1] <= ty <= rect[3]

    def update(self, snapshot: "SimStateSnapshot"):
        """Called every frame by the Ursina app loop."""
        try:
            from game.types import HeroClass
        except Exception:
            HeroClass = None

        self._ensure_shadow_bounds_once()

        # R4: cache sim interpolation state for this frame
        self._frame_blend = float(getattr(snapshot, 'sim_blend_fraction', 0.0))
        self._frame_tick_id = int(getattr(snapshot, 'sim_tick_id', 0))

        # WK59 perf: cache visible tile rect for frustum culling this frame
        self._frame_visible_rect = self._get_visible_tile_rect()

        world = getattr(snapshot, "world", None) or self._world
        fog_revision = int(getattr(snapshot, "fog_revision", 0))
        self._terrain_fog.build_3d_terrain(world, getattr(snapshot, "buildings", ()))
        self._terrain_fog.sync_dynamic_trees(world, getattr(snapshot, "trees", ()) or ())
        self._terrain_fog.sync_log_stacks(world, getattr(snapshot, "log_stacks", ()) or ())
        self._terrain_fog.ensure_fog_overlay(world, fog_revision)
        self._terrain_fog.sync_visibility_gated_terrain(world, fog_revision)
        self._terrain_fog.cull_terrain_chunks(self._frame_visible_rect, world)
        self._terrain_fog.ensure_grid_debug_overlay(world, getattr(snapshot, "buildings", ()))

        # WK47 Wave 2b: hardware-instanced units (snapshot → buffer texture).
        # Opt-in: set KINGDOM_URSINA_INSTANCING=1 (known visual issues — see project memory).
        if os.environ.get("KINGDOM_URSINA_INSTANCING", "0") == "1":
            if not hasattr(self, "_instanced_unit_renderer"):
                from game.graphics.instanced_unit_renderer import InstancedUnitRenderer

                self._instanced_unit_renderer = InstancedUnitRenderer()
            active_ids: set[int] = set()
            self._sync_snapshot_buildings(snapshot, world, active_ids)
            unit_ids = self._instanced_unit_renderer.update(snapshot)
            active_ids.update(unit_ids)
            # Projectiles draw inside ``InstancedUnitRenderer`` (wk48); skip legacy Entities.
            self._update_debug_status_text(snapshot)
            self._destroy_removed_entities(active_ids)
            return

        active_ids = set()
        self._sync_snapshot_buildings(snapshot, world, active_ids)
        self._sync_snapshot_heroes(snapshot, active_ids, HeroClass)
        self._sync_snapshot_enemies(snapshot, world, active_ids)
        self._sync_snapshot_peasants(snapshot, active_ids)
        self._sync_snapshot_guards(snapshot, active_ids)
        self._sync_snapshot_tax_collector(snapshot, active_ids)
        self._sync_snapshot_projectiles(snapshot, active_ids)
        self._update_debug_status_text(snapshot)
        self._destroy_removed_entities(active_ids)

    def _ensure_shadow_bounds_once(self) -> None:
        if (
            not self._shadow_bounds_initialized
            and self._directional_light is not None
        ):
            try:
                self._directional_light.update_bounds(scene)
            except Exception:
                pass
            self._shadow_bounds_initialized = True

    def _apply_poi_mystery_state(self, b, ent, wx, wz, bld_terrain_y) -> None:
        """WK55: No-op — binary visibility is handled in _sync_snapshot_buildings.
        Kept as stub so any stray calls don't crash."""
        pass

    def _sync_snapshot_buildings(self, snapshot: "SimStateSnapshot", world, active_ids: set) -> None:
        # Buildings — billboard quads, except castle / house / lair (v1.5 Sprint 2.1: lit 3D meshes).
        for b in getattr(snapshot, "buildings", ()):
            # WK54+fix: Debug mode — force POI tiles to SEEN so they render consistently
            if _debug_show_pois and getattr(b, 'is_poi', False):
                b.is_discovered = True
                # Also mark POI tiles as SEEN in fog-of-war so lair-visibility checks pass
                _world = getattr(snapshot, 'world', None)
                if _world is not None:
                    _poi_def = getattr(b, 'poi_def', None)
                    _pw, _ph = (getattr(_poi_def, 'size', (1,1)) if _poi_def else (1,1))
                    _gx, _gy = int(getattr(b, 'grid_x', 0)), int(getattr(b, 'grid_y', 0))
                    for _dy in range(_ph):
                        for _dx in range(_pw):
                            _tx, _ty = _gx + _dx, _gy + _dy
                            if 0 <= _tx < _world.width and 0 <= _ty < _world.height:
                                if _world.visibility[_ty][_tx] == 0:  # UNSEEN
                                    _world.visibility[_ty][_tx] = 1  # SEEN
            # WK55-fix: Binary POI visibility — hidden until discovered by hero.
            # Undiscovered POIs are completely hidden (minimap gray dots are the only hint).
            # Once a hero walks within discovery range, the POI becomes fully visible.
            if getattr(b, "is_poi", False) and not _debug_show_pois:
                _poi_obj_id = id(b)
                if not getattr(b, 'is_discovered', False):
                    # UNDISCOVERED — hide entity completely; minimap shows gray dot instead
                    existing = self._entities.get(_poi_obj_id)
                    if existing is not None:
                        existing.enabled = False
                        active_ids.add(_poi_obj_id)
                    # Also hide any leftover mystery marker from old code
                    marker = self._poi_mystery_markers.get(_poi_obj_id)
                    if marker is not None:
                        marker.enabled = False
                    continue
                # DISCOVERED — fall through to normal rendering below
            # WK59 perf: frustum culling — skip buildings outside visible tile rect
            if not self._entity_in_view(getattr(b, "x", 0.0), getattr(b, "y", 0.0)):
                _bld_obj_id = id(b)
                _bld_existing = self._entities.get(_bld_obj_id)
                if _bld_existing is not None:
                    _bld_existing.enabled = False
                    active_ids.add(_bld_obj_id)
                continue
            # Re-enable building if it was previously culled and is now in view
            _bld_reenable = self._entities.get(id(b))
            if _bld_reenable is not None and getattr(_bld_reenable, "enabled", True) is False:
                _bld_reenable.enabled = True
            bt_raw = getattr(b, "building_type", "") or ""
            bts = _building_type_str(bt_raw)
            is_castle = bts == "castle"
            is_lair = hasattr(b, "stash_gold")
            # Fog-of-war: lairs are hostile world structures and should not be visible through fog.
            # Match enemy visibility semantics: show only when the lair tile is currently VISIBLE.
            if is_lair:
                ts = float(config.TILE_SIZE)
                tx, ty = int(getattr(b, "x", 0.0) / ts), int(getattr(b, "y", 0.0) / ts)
                lair_visible = True
                if 0 <= ty < world.height and 0 <= tx < world.width:
                    lair_visible = (world.visibility[ty][tx] == Visibility.VISIBLE)
                obj_id = id(b)
                existing = self._entities.get(obj_id)
                if not lair_visible:
                    if existing is not None:
                        existing.enabled = False
                        active_ids.add(obj_id)
                    continue
                if existing is not None and getattr(existing, "enabled", True) is False:
                    existing.enabled = True
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
            # WK53 Wave 2: sample terrain height at building footprint center
            bld_terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

            # WK30: prefab path wins over static mesh / billboard for any building_type with
            # a resolvable prefab JSON. Lairs and env opt-out are handled inside the resolver.
            # WK32: swap JSON by construction_progress (plots + intermediates + fallback).
            prefab_path = _resolve_prefab_path(bts, b)
            if prefab_path is not None:
                staged = _resolve_construction_staged_prefab(b, prefab_path, tw, th)
                ent, obj_id = self._entity_render.get_or_create_prefab_building_entity(
                    b, staged, col
                )
                self._entity_render.sync_prefab_building_entity(
                    ent,
                    mesh_kind=bts,
                    wx=wx,
                    wz=wz,
                    fx=fx,
                    fz=fz,
                    hy=hy,
                    tint_col=col,
                    state=state,
                    terrain_y=bld_terrain_y,
                )
                # WK57: Visual hint for cave/mine entrances — cool dark tint
                if not getattr(ent, "_ks_cave_tint_applied", False):
                    poi_def = getattr(b, 'poi_def', None)
                    if poi_def and getattr(poi_def, 'poi_type', None) in ('poi_cave_entrance', 'poi_mine_entrance'):
                        try:
                            ent.color = color.rgb(180, 180, 200)
                        except Exception:
                            pass
                        ent._ks_cave_tint_applied = True
                # WK55: POI 3-state visibility post-processing
                self._apply_poi_mystery_state(b, ent, wx, wz, bld_terrain_y)
                # R5 Phase 2 (Agent 03): native building label / HP bar / gold
                _sync_building_worldspace_ui(b, bts, ent, is_lair)
                active_ids.add(obj_id)
                continue

            if _is_3d_mesh_building(bts, b):
                mesh_kind = _mesh_kind_for_building(bts, b)
                model_path = _environment_model_path(mesh_kind)
                ent, obj_id = self._entity_render.get_or_create_3d_building_entity(b, model_path, col)
                self._entity_render.sync_3d_building_entity(
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
                    terrain_y=bld_terrain_y,
                )
                # WK57: Visual hint for cave/mine entrances — cool dark tint
                if not getattr(ent, '_ks_cave_tint_applied', False):
                    poi_def = getattr(b, 'poi_def', None)
                    if poi_def and getattr(poi_def, 'poi_type', None) in ('poi_cave_entrance', 'poi_mine_entrance'):
                        try:
                            ent.color = color.rgb(180, 180, 200)
                        except Exception:
                            pass
                        ent._ks_cave_tint_applied = True
                # WK55: POI 3-state visibility post-processing
                self._apply_poi_mystery_state(b, ent, wx, wz, bld_terrain_y)
                # R5 Phase 2 (Agent 03): native building label / HP bar / gold
                _sync_building_worldspace_ui(b, bts, ent, is_lair)
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
            ent, obj_id = self._entity_render.get_or_create_entity(
                b,
                model="quad",
                col=col,
                scale=(face_w, hy, 1),
                billboard=True,
            )
            if not getattr(ent, "_ks_billboard_configured", False):
                ent.model = "quad"
                ent.billboard = True
                self._entity_render.apply_pixel_billboard_settings(ent)
                ent._ks_billboard_configured = True
            # Do not assign ent.model every frame — model_setter reloads the mesh (WK22 R2).
            ent.rotation = (0, 0, 0)
            self._entity_render.sync_billboard_entity(
                ent,
                tex=b_tex if b_tex is not None else None,
                tint_col=col,
                scale_xyz=(face_w, hy, 1),
                pos_xyz=(wx, bld_terrain_y + hy * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            # WK57: Visual hint for cave/mine entrances — cool dark tint
            if not getattr(ent, '_ks_cave_tint_applied', False):
                poi_def = getattr(b, 'poi_def', None)
                if poi_def and getattr(poi_def, 'poi_type', None) in ('poi_cave_entrance', 'poi_mine_entrance'):
                    try:
                        ent.color = color.rgb(180, 180, 200)
                    except Exception:
                        pass
                    ent._ks_cave_tint_applied = True
            # WK55: POI 3-state visibility post-processing
            self._apply_poi_mystery_state(b, ent, wx, wz, bld_terrain_y)
            # R5 Phase 2 (Agent 03): native building label / HP bar / gold
            _sync_building_worldspace_ui(b, bts, ent, is_lair)
            active_ids.add(obj_id)


    def _sync_snapshot_heroes(self, snapshot: "SimStateSnapshot", active_ids: set, HeroClass) -> None:
        # Heroes — atlas UV billboards (WK59 perf: single shared texture, UV offset per frame)
        for h in getattr(snapshot, "heroes", ()):
            if not getattr(h, "is_alive", True):
                continue
            # WK59 perf: frustum culling — skip heroes outside visible tile rect
            if not self._entity_in_view(h.x, h.y):
                _h_obj_id = id(h)
                _h_existing = self._entities.get(_h_obj_id)
                if _h_existing is not None:
                    _h_existing.enabled = False
                    active_ids.add(_h_obj_id)
                continue
            # Re-enable hero if it was previously culled and is now in view
            _h_reenable = self._entities.get(id(h))
            if _h_reenable is not None and getattr(_h_reenable, "enabled", True) is False:
                _h_reenable.enabled = True
            col = COLOR_HERO
            if HeroClass:
                hc = getattr(h, "hero_class", None)
                if hc == HeroClass.WARRIOR or str(hc).lower() == "warrior":
                    col = color.white
                elif hc == HeroClass.RANGER or str(hc).lower() == "ranger":
                    col = color.lime
                elif hc == HeroClass.WIZARD or str(hc).lower() == "wizard":
                    col = color.magenta
                elif hc == HeroClass.ROGUE or str(hc).lower() == "rogue":
                    col = color.violet
                elif hc == HeroClass.CLERIC or str(hc).lower() == "cleric":
                    col = color.rgb(48 / 255, 186 / 255, 178 / 255)

            hc_key = str(getattr(h, "hero_class", "warrior") or "warrior").lower()
            sy = UNIT_BILLBOARD_SCALE
            ent, obj_id = self._entity_render.get_or_create_entity(
                h,
                model="quad",
                col=color.white,
                scale=(sy, sy, 1),
                texture=None,
                billboard=True,
            )
            wx, wz = sim_px_to_world_xz(h.x, h.y)
            terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0
            y_center = terrain_y + sy * 0.5
            facing = _unit_facing_direction(h)
            sx = sy * facing  # negative scale_x flips the billboard horizontally

            self._sync_unit_atlas_billboard(
                ent, obj_id, h, "hero", hc_key, _hero_base_clip,
                col, (sx, sy, 1), (wx, y_center, wz), sprite_unlit_shader,
            )
            # Layer compositing (not Y offset): draw after building billboards; skip depth so the
            # "inside" bubble paints over the same footprint as the facade.
            self._entity_render.sync_inside_hero_draw_layer(ent, bool(getattr(h, "is_inside_building", False)))

            # --- R5: Native Ursina health bar (Agent 09) ---
            _h_hp = int(getattr(h, 'hp', 0) or 0)
            _h_max_hp = int(getattr(h, 'max_hp', 1) or 1)
            _h_hp_bg = getattr(ent, '_ks_hp_bg', None)
            _h_hp_fg = getattr(ent, '_ks_hp_fg', None)

            if _h_max_hp > 0 and _h_hp > 0 and _h_hp < _h_max_hp:
                _h_ratio = _h_hp / _h_max_hp
                _h_bar_w = 0.8
                _h_bar_h = 0.04
                _h_bar_y = 0.50

                if _h_hp_bg is None:
                    _h_hp_bg = Entity(
                        parent=ent, model='quad', color=color.rgb(0.25, 0.25, 0.25),
                        scale=(_h_bar_w, _h_bar_h, 1), position=(0, _h_bar_y, -0.01),
                        billboard=True, unlit=True,
                    )
                    _h_hp_bg.set_depth_test(False)
                    ent._ks_hp_bg = _h_hp_bg

                if _h_hp_fg is None:
                    _h_hp_fg = Entity(
                        parent=ent, model='quad',
                        color=color.green if _h_ratio > 0.5 else color.red,
                        scale=(_h_bar_w * _h_ratio, _h_bar_h, 1),
                        position=(-(_h_bar_w * (1 - _h_ratio) / 2), _h_bar_y, -0.02),
                        billboard=True, unlit=True,
                    )
                    _h_hp_fg.set_depth_test(False)
                    ent._ks_hp_fg = _h_hp_fg
                else:
                    _h_hp_fg.scale_x = _h_bar_w * _h_ratio
                    _h_hp_fg.x = -(_h_bar_w * (1 - _h_ratio) / 2)
                    _h_hp_fg.color = color.green if _h_ratio > 0.5 else color.red

                _h_hp_bg.enabled = True
                _h_hp_fg.enabled = True
            else:
                if _h_hp_bg is not None:
                    _h_hp_bg.enabled = False
                if _h_hp_fg is not None:
                    _h_hp_fg.enabled = False

            # --- R5: Hero name label (Agent 08) ---
            hero_name = getattr(h, 'name', '') or ''
            name_ent = getattr(ent, '_ks_name_label', None)
            if name_ent is None and hero_name:
                from ursina import Text as UrsinaText
                name_ent = UrsinaText(
                    text=hero_name, parent=ent, origin=(0, 0), scale=12,
                    color=color.white, billboard=True, y=-0.6,
                )
                ent._ks_name_label = name_ent
            elif name_ent is not None and name_ent.text != hero_name:
                name_ent.text = hero_name

            # --- R5: Hero gold display (Agent 08) ---
            hero_gold = int(getattr(h, 'gold', 0) or 0)
            hero_taxed = int(getattr(h, 'taxed_gold', 0) or 0)
            total_gold = hero_gold + hero_taxed
            gold_ent = getattr(ent, '_ks_gold_label', None)
            if total_gold > 0:
                gold_text = f"${hero_gold}(+{hero_taxed})" if hero_taxed > 0 else f"${hero_gold}"
                if gold_ent is None:
                    from ursina import Text as UrsinaText
                    gold_ent = UrsinaText(
                        text=gold_text, parent=ent, origin=(0, 0), scale=10,
                        color=color.rgb(1.0, 0.8, 0.2), billboard=True, y=-0.8,
                    )
                    ent._ks_gold_label = gold_ent
                else:
                    if gold_ent.text != gold_text:
                        gold_ent.text = gold_text
                    gold_ent.enabled = True
            elif gold_ent is not None:
                gold_ent.enabled = False

            # --- R5: Hero rest indicator (Agent 08) ---
            is_resting = (getattr(h, 'state', '') == 'RESTING')
            rest_ent = getattr(ent, '_ks_rest_label', None)
            if is_resting:
                if rest_ent is None:
                    from ursina import Text as UrsinaText
                    rest_ent = UrsinaText(
                        text='Zzz', parent=ent, origin=(0, 0), scale=12,
                        color=color.rgb(0.7, 0.85, 1.0), billboard=True, y=0.7, x=0.3,
                    )
                    ent._ks_rest_label = rest_ent
                else:
                    rest_ent.enabled = True
            elif rest_ent is not None:
                rest_ent.enabled = False

            active_ids.add(obj_id)


    def _sync_snapshot_enemies(self, snapshot: "SimStateSnapshot", world, active_ids: set) -> None:
        # Enemies — atlas UV billboards (WK59 perf: single shared texture)
        ts = float(config.TILE_SIZE)
        for e in getattr(snapshot, "enemies", ()):
            tx, ty = int(e.x / ts), int(e.y / ts)
            is_visible = True
            if 0 <= ty < world.height and 0 <= tx < world.width:
                is_visible = (world.visibility[ty][tx] == Visibility.VISIBLE)

            if not getattr(e, "is_alive", True) or not is_visible:
                continue
            # WK59 perf: frustum culling — skip enemies outside visible tile rect
            if not self._entity_in_view(e.x, e.y):
                _e_obj_id = id(e)
                _e_existing = self._entities.get(_e_obj_id)
                if _e_existing is not None:
                    _e_existing.enabled = False
                    active_ids.add(_e_obj_id)
                continue
            # Re-enable enemy if it was previously culled and is now in view
            _e_reenable = self._entities.get(id(e))
            if _e_reenable is not None and getattr(_e_reenable, "enabled", True) is False:
                _e_reenable.enabled = True
            s = ENEMY_SCALE
            col = COLOR_ENEMY
            et_key = str(getattr(e, "enemy_type", "goblin") or "goblin").lower()
            ent, obj_id = self._entity_render.get_or_create_entity(
                e,
                model="quad",
                col=color.white,
                scale=(s, s, 1),
                texture=None,
                billboard=True,
            )
            wx, wz = sim_px_to_world_xz(e.x, e.y)
            terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0
            facing_e = _unit_facing_direction(e)
            sx_e = s * facing_e

            self._sync_unit_atlas_billboard(
                ent, obj_id, e, "enemy", et_key, _enemy_base_clip,
                col, (sx_e, s, 1), (wx, terrain_y + s * 0.5, wz), sprite_unlit_shader,
            )

            # --- R5: Native Ursina health bar (Agent 09) ---
            _e_hp = int(getattr(e, 'hp', 0) or 0)
            _e_max_hp = int(getattr(e, 'max_hp', 1) or 1)
            _e_hp_bg = getattr(ent, '_ks_hp_bg', None)
            _e_hp_fg = getattr(ent, '_ks_hp_fg', None)

            if _e_max_hp > 0 and _e_hp > 0 and _e_hp < _e_max_hp:
                _e_ratio = _e_hp / _e_max_hp
                _e_bar_w = 0.6
                _e_bar_h = 0.03
                _e_bar_y = 0.40

                if _e_hp_bg is None:
                    _e_hp_bg = Entity(
                        parent=ent, model='quad', color=color.rgb(0.25, 0.25, 0.25),
                        scale=(_e_bar_w, _e_bar_h, 1), position=(0, _e_bar_y, -0.01),
                        billboard=True, unlit=True,
                    )
                    _e_hp_bg.set_depth_test(False)
                    ent._ks_hp_bg = _e_hp_bg

                if _e_hp_fg is None:
                    _e_hp_fg = Entity(
                        parent=ent, model='quad',
                        color=color.green if _e_ratio > 0.5 else color.red,
                        scale=(_e_bar_w * _e_ratio, _e_bar_h, 1),
                        position=(-(_e_bar_w * (1 - _e_ratio) / 2), _e_bar_y, -0.02),
                        billboard=True, unlit=True,
                    )
                    _e_hp_fg.set_depth_test(False)
                    ent._ks_hp_fg = _e_hp_fg
                else:
                    _e_hp_fg.scale_x = _e_bar_w * _e_ratio
                    _e_hp_fg.x = -(_e_bar_w * (1 - _e_ratio) / 2)
                    _e_hp_fg.color = color.green if _e_ratio > 0.5 else color.red

                _e_hp_bg.enabled = True
                _e_hp_fg.enabled = True
            else:
                if _e_hp_bg is not None:
                    _e_hp_bg.enabled = False
                if _e_hp_fg is not None:
                    _e_hp_fg.enabled = False

            active_ids.add(obj_id)


    def _sync_snapshot_peasants(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # Peasants — atlas UV billboards (WK59 perf: single shared texture)
        for p in getattr(snapshot, "peasants", ()):
            if not getattr(p, "is_alive", True):
                continue
            if bool(getattr(p, "is_inside_castle", False)):
                continue
            # WK59 perf: frustum culling — skip peasants outside visible tile rect
            if not self._entity_in_view(p.x, p.y):
                _p_obj_id = id(p)
                _p_existing = self._entities.get(_p_obj_id)
                if _p_existing is not None:
                    _p_existing.enabled = False
                    active_ids.add(_p_obj_id)
                continue
            # Re-enable peasant if it was previously culled and is now in view
            _p_reenable = self._entities.get(id(p))
            if _p_reenable is not None and getattr(_p_reenable, "enabled", True) is False:
                _p_reenable.enabled = True
            sx = PEASANT_SCALE_XZ
            sy = PEASANT_SCALE_Y
            col = color.white
            wk = str(getattr(p, "render_worker_type", "peasant") or "peasant")
            ent, obj_id = self._entity_render.get_or_create_entity(
                p,
                model="quad",
                col=color.white,
                scale=(sx, sy, 1),
                texture=None,
                billboard=True,
            )
            wx, wz = sim_px_to_world_xz(p.x, p.y)
            terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

            self._sync_unit_atlas_billboard(
                ent, obj_id, p, "worker", wk, _peasant_base_clip,
                col, (sx, sy, 1), (wx, terrain_y + sy * 0.5, wz), sprite_unlit_shader,
            )

            # --- R5: Native Ursina health bar (Agent 09) ---
            _p_hp = int(getattr(p, 'hp', 0) or 0)
            _p_max_hp = int(getattr(p, 'max_hp', 1) or 1)
            _p_hp_bg = getattr(ent, '_ks_hp_bg', None)
            _p_hp_fg = getattr(ent, '_ks_hp_fg', None)

            if _p_max_hp > 0 and _p_hp > 0 and _p_hp < _p_max_hp:
                _p_ratio = _p_hp / _p_max_hp
                _p_bar_w = 0.5
                _p_bar_h = 0.03
                _p_bar_y = 0.35

                if _p_hp_bg is None:
                    _p_hp_bg = Entity(
                        parent=ent, model='quad', color=color.rgb(0.25, 0.25, 0.25),
                        scale=(_p_bar_w, _p_bar_h, 1), position=(0, _p_bar_y, -0.01),
                        billboard=True, unlit=True,
                    )
                    _p_hp_bg.set_depth_test(False)
                    ent._ks_hp_bg = _p_hp_bg

                if _p_hp_fg is None:
                    _p_hp_fg = Entity(
                        parent=ent, model='quad',
                        color=color.green if _p_ratio > 0.5 else color.red,
                        scale=(_p_bar_w * _p_ratio, _p_bar_h, 1),
                        position=(-(_p_bar_w * (1 - _p_ratio) / 2), _p_bar_y, -0.02),
                        billboard=True, unlit=True,
                    )
                    _p_hp_fg.set_depth_test(False)
                    ent._ks_hp_fg = _p_hp_fg
                else:
                    _p_hp_fg.scale_x = _p_bar_w * _p_ratio
                    _p_hp_fg.x = -(_p_bar_w * (1 - _p_ratio) / 2)
                    _p_hp_fg.color = color.green if _p_ratio > 0.5 else color.red

                _p_hp_bg.enabled = True
                _p_hp_fg.enabled = True
            else:
                if _p_hp_bg is not None:
                    _p_hp_bg.enabled = False
                if _p_hp_fg is not None:
                    _p_hp_fg.enabled = False

            active_ids.add(obj_id)


    def _sync_snapshot_guards(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # Guards — atlas UV billboards (WK59 perf: single shared texture)
        for g in getattr(snapshot, "guards", ()):
            if not getattr(g, "is_alive", True):
                continue
            # WK59 perf: frustum culling — skip guards outside visible tile rect
            if not self._entity_in_view(g.x, g.y):
                _g_obj_id = id(g)
                _g_existing = self._entities.get(_g_obj_id)
                if _g_existing is not None:
                    _g_existing.enabled = False
                    active_ids.add(_g_obj_id)
                continue
            # Re-enable guard if it was previously culled and is now in view
            _g_reenable = self._entities.get(id(g))
            if _g_reenable is not None and getattr(_g_reenable, "enabled", True) is False:
                _g_reenable.enabled = True
            col = color.white
            ent, obj_id = self._entity_render.get_or_create_entity(
                g,
                model="quad",
                col=color.white,
                scale=(GUARD_SCALE_XZ, GUARD_SCALE_Y, 1),
                texture=None,
                billboard=True,
            )
            wx, wz = sim_px_to_world_xz(g.x, g.y)
            terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

            self._sync_unit_atlas_billboard(
                ent, obj_id, g, "worker", "guard", _guard_base_clip,
                col, (GUARD_SCALE_XZ, GUARD_SCALE_Y, 1),
                (wx, terrain_y + GUARD_SCALE_Y * 0.5, wz), sprite_unlit_shader,
            )

            # --- R5: Native Ursina health bar (Agent 09) ---
            _g_hp = int(getattr(g, 'hp', 0) or 0)
            _g_max_hp = int(getattr(g, 'max_hp', 1) or 1)
            _g_hp_bg = getattr(ent, '_ks_hp_bg', None)
            _g_hp_fg = getattr(ent, '_ks_hp_fg', None)

            if _g_max_hp > 0 and _g_hp > 0 and _g_hp < _g_max_hp:
                _g_ratio = _g_hp / _g_max_hp
                _g_bar_w = 0.7
                _g_bar_h = 0.03
                _g_bar_y = 0.45

                if _g_hp_bg is None:
                    _g_hp_bg = Entity(
                        parent=ent, model='quad', color=color.rgb(0.25, 0.25, 0.25),
                        scale=(_g_bar_w, _g_bar_h, 1), position=(0, _g_bar_y, -0.01),
                        billboard=True, unlit=True,
                    )
                    _g_hp_bg.set_depth_test(False)
                    ent._ks_hp_bg = _g_hp_bg

                if _g_hp_fg is None:
                    _g_hp_fg = Entity(
                        parent=ent, model='quad',
                        color=color.green if _g_ratio > 0.5 else color.red,
                        scale=(_g_bar_w * _g_ratio, _g_bar_h, 1),
                        position=(-(_g_bar_w * (1 - _g_ratio) / 2), _g_bar_y, -0.02),
                        billboard=True, unlit=True,
                    )
                    _g_hp_fg.set_depth_test(False)
                    ent._ks_hp_fg = _g_hp_fg
                else:
                    _g_hp_fg.scale_x = _g_bar_w * _g_ratio
                    _g_hp_fg.x = -(_g_bar_w * (1 - _g_ratio) / 2)
                    _g_hp_fg.color = color.green if _g_ratio > 0.5 else color.red

                _g_hp_bg.enabled = True
                _g_hp_fg.enabled = True
            else:
                if _g_hp_bg is not None:
                    _g_hp_bg.enabled = False
                if _g_hp_fg is not None:
                    _g_hp_fg.enabled = False

            active_ids.add(obj_id)


    def _sync_snapshot_tax_collector(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # Tax Collector — atlas UV billboards (WK59 perf: single shared texture)
        tc = getattr(snapshot, "tax_collector", None)
        if tc is not None:
            if not getattr(tc, "is_alive", True):
                pass
            else:
                col = color.white
                sx = PEASANT_SCALE_XZ
                sy = PEASANT_SCALE_Y
                ent, obj_id = self._entity_render.get_or_create_entity(
                    tc,
                    model="quad",
                    col=color.white,
                    scale=(sx, sy, 1),
                    texture=None,
                    billboard=True,
                )
                wx, wz = sim_px_to_world_xz(tc.x, tc.y)
                terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

                self._sync_unit_atlas_billboard(
                    ent, obj_id, tc, "worker", "tax_collector", _tax_collector_base_clip,
                    col, (sx, sy, 1), (wx, terrain_y + sy * 0.5, wz), sprite_unlit_shader,
                )

                # --- R5: Tax collector gold display (Agent 08) ---
                carried = int(getattr(tc, 'carried_gold', 0) or 0)
                tc_gold_ent = getattr(ent, '_ks_tc_gold', None)
                if carried > 0:
                    tc_text = f"${carried}"
                    if tc_gold_ent is None:
                        from ursina import Text as UrsinaText
                        tc_gold_ent = UrsinaText(
                            text=tc_text, parent=ent, origin=(0, 0), scale=10,
                            color=color.rgb(1.0, 0.8, 0.2), billboard=True, y=0.5,
                        )
                        ent._ks_tc_gold = tc_gold_ent
                    else:
                        if tc_gold_ent.text != tc_text:
                            tc_gold_ent.text = tc_text
                        tc_gold_ent.enabled = True
                elif tc_gold_ent is not None:
                    tc_gold_ent.enabled = False

                active_ids.add(obj_id)


    def _sync_snapshot_projectiles(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # Projectiles — VFX arrows as textured billboards (WK5 colors via get_projectile_billboard_surface)
        if self._projectile_tex is None:
            psurf = get_projectile_billboard_surface()
            self._projectile_tex = TerrainTextureBridge.surface_to_texture(
                psurf, cache_key=("ursina", "projectile_arrow_billboard_v1")
            )
        ptex = self._projectile_tex
        for proj in getattr(snapshot, "vfx_projectiles", ()) or ():
            s = PROJECTILE_BILLBOARD_SCALE
            ent, obj_id = self._entity_render.get_or_create_entity(
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
                self._entity_render.apply_pixel_billboard_settings(ent)
                ent._ks_billboard_configured = True
            # Draw above the floor plane: tiny Y (s*0.5) caused depth-fighting with terrain; stack with units.
            if not getattr(ent, "_ks_projectile_depth", False):
                ent.set_depth_test(False)
                ent.render_queue = 2
                ent._ks_projectile_depth = True
            wx, wz = sim_px_to_world_xz(proj.x, proj.y)
            proj_terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0
            self._entity_render.sync_billboard_entity(
                ent,
                tex=ptex,
                tint_col=color.white,
                scale_xyz=(s, s, 1),
                pos_xyz=(wx, proj_terrain_y + PROJECTILE_BILLBOARD_Y, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

    def _update_debug_status_text(self, snapshot: "SimStateSnapshot") -> None:
        heroes_alive = len([h for h in getattr(snapshot, "heroes", ()) if getattr(h, "is_alive", True)])
        enemies_alive = len(getattr(snapshot, "enemies", ()))
        status_text = (
            f"Gold: {getattr(snapshot, 'gold', 0)}  |  Heroes: {heroes_alive}  |  "
            f"Enemies: {enemies_alive}  |  Buildings: {len(getattr(snapshot, 'buildings', ())) }"
        )
        if self.status_text.text != status_text:
            self.status_text.text = status_text


    def _destroy_removed_entities(self, active_ids: set) -> None:
        dead_ids = set(self._entities.keys()) - active_ids
        for obj_id in dead_ids:
            self._unit_anim_state.pop(obj_id, None)
            ent = self._entities.pop(obj_id)
            import ursina

            ursina.destroy(ent)

