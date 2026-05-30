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
from game.graphics.visual_specs import (
    HERO_SPEC, ENEMY_SPEC, PEASANT_SPEC, GUARD_SPEC, TAX_COLLECTOR_SPEC,
)
from game.graphics.ursina_unit_overlays import (
    configure_ks_overlay as _configure_ks_overlay_impl,
    sync_ks_facing_overlay as _sync_ks_facing_overlay_impl,
    ensure_ks_name_label as _ensure_ks_name_label_impl,
    sync_hp_bar,
    sync_hero_gold_label,
    sync_hero_rest_label,
    sync_hero_overlays_facing,
    sync_unit_overlays_facing,
)
from game.graphics.worker_sprites import WorkerSpriteLibrary
# WK87 (Agent 09): the tax-overlay public API + building world-space UI moved to
# ursina_building_ui.py (pure module-function move). Re-export the names callers/tests
# import from this module (ursina_app + engine lifecycle call set_tax_gold_overlay_held;
# tests import building_tax_overlay_snapshot / _building_gold_overlay_y /
# _building_gold_overlay_world_y / _prefab_local_top_y / _sync_building_worldspace_ui).
# The building-sync call sites below call _sync_building_worldspace_ui /
# _maybe_log_tax_overlay_debug as bare names, resolved by this import. Leaf import —
# ursina_building_ui does NOT import ursina_renderer (no cycle).
from game.graphics.ursina_building_ui import (  # noqa: F401
    set_tax_gold_overlay_held,
    is_tax_gold_overlay_held,
    building_tax_overlay_snapshot,
    _prefab_local_top_y,
    _building_gold_overlay_y,
    _building_gold_overlay_world_y,
    _sync_building_worldspace_ui,
    _maybe_log_tax_overlay_debug,
)
from game.world import TileType, Visibility

if TYPE_CHECKING:
    from game.sim.snapshot import (
        PresentationFrameState,
        RenderSnapshot,
        SimStateSnapshot,
    )

# Fallback tint when hero class is unresolved or texture upload fails — match Warrior shirt (HeroSpriteSpec).
COLOR_HERO = color.rgb(180 / 255.0, 45 / 255.0, 45 / 255.0)
COLOR_ENEMY = color.red
COLOR_BUILDING = color.light_gray
COLOR_CASTLE = color.gold
COLOR_LAIR = color.brown


# 1 world unit along the floor == 1 tile == 32 px (scale lives in ursina_coords)
from game.graphics.ursina_coords import SCALE, px_to_world, sim_px_to_world_xz

# WK65 Round 0: env scale constants live in ursina_environment.py (the single source
# imported by ursina_terrain_fog_collab.py). The unused renderer-local copies of
# TERRAIN/TREE/ROCK/GRASS_SCATTER/GROUND_PROP_*_SCALE were deleted (verified zero callers).

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
GUARD_SCALE_XZ = 0.5 * _US
GUARD_SCALE_Y = 0.7 * _US

# Ranged VFX billboards — smaller than unit sprites, readable in perspective.
# 0.3 was large in playtest; 25% of that keeps arrows visible (snapshot + depth fix) without dominating the frame.
PROJECTILE_BILLBOARD_SCALE = 0.075
# Vertical lift: match enemy sprite center (ENEMY_SCALE*0.5) so arrows aren't drawn under terrain.
PROJECTILE_BILLBOARD_Y = ENEMY_SCALE * 0.5

# Debug toggle: render all POIs regardless of discovery state (dev/testing aid).
_debug_show_pois = os.environ.get("KINGDOM_DEBUG_SHOW_ALL_POIS", "").strip().lower() in ("1", "true", "yes")
# WK87 (Agent 09): _debug_tax_overlay / _tax_overlay_debug_last_print moved to
# game/graphics/ursina_building_ui.py with the tax-overlay functions.

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

# WK87 (Agent 09): _tax_gold_overlay_held state + set_tax_gold_overlay_held /
# is_tax_gold_overlay_held / building_tax_overlay_snapshot / _prefab_local_top_y /
# _building_gold_overlay_y / _building_gold_overlay_world_y moved VERBATIM to
# game/graphics/ursina_building_ui.py and re-exported above.


def _configure_ks_overlay(ent) -> None:
    """Depth-off + on-top so labels/HP/gold overlays are not hidden by terrain or prefabs.

    WK62: delegates to ``ursina_unit_overlays.configure_ks_overlay``.
    """
    _configure_ks_overlay_impl(ent)


def _sync_ks_facing_overlay(child, facing: float) -> None:
    """Keep overlay readable when the parent billboard uses negative scale_x for facing.

    WK62: delegates to ``ursina_unit_overlays.sync_ks_facing_overlay``.
    """
    _sync_ks_facing_overlay_impl(child, facing)


def _ensure_ks_name_label(
    ent,
    attr: str,
    text: str,
    *,
    y: float = 0.55,
    scale: float = 10,
    label_color=None,
) -> None:
    """WK62: delegates to ``ursina_unit_overlays.ensure_ks_name_label``."""
    _ensure_ks_name_label_impl(ent, attr, text, y=y, scale=scale, label_color=label_color)


# WK87 (Agent 09): _sync_building_worldspace_ui / _maybe_log_tax_overlay_debug moved
# VERBATIM to game/graphics/ursina_building_ui.py and re-exported above; the
# building-sync call sites below call them as bare names resolved by that import.


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
    anim_clock_seconds,
    _frame_index_for_clip,
    _guard_base_clip,
    _hero_base_clip,
    _enemy_base_clip,
    _peasant_base_clip,
    _tax_collector_base_clip,
    # WK89 Round B-6 (Agent 09): the unit-anim-frame computation now lives in
    # ursina_units_anim.py. Re-export the DTO base-clip selector so any importer of
    # ``ursina_renderer._base_clip_from_dto`` keeps working.
    base_clip_from_dto as _base_clip_from_dto,
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
        # WK60 Feature 7: Bounty flag 3D entities, keyed by bounty_id.
        self._bounty_entities: dict[int, list[Entity]] = {}
        # WK61-FEAT-004: Rubble entity groups, keyed by RubbleRecord.record_id.
        self._rubble_entities: dict[int, list] = {}

        # R4: sim interpolation state for linear position interpolation
        self._frame_blend: float = 0.0
        self._frame_tick_id: int = -1

        # v1.5: parent Entity for per-tile 3D terrain meshes (see _build_3d_terrain).
        self._terrain_entity: Entity | None = None
        # WK53 R3: the heightmap-displaced ground mesh — fog shader updates target this.
        self._terrain_ground_entity: Entity | None = None
        # WK58 W8 (4.C): handle for Panda3D GeoMipTerrain when
        # KINGDOM_URSINA_GEOMIPTERRAIN=1. None when the custom Mesh path is
        # active. Renderer.update() calls handle.update_lod() once per frame
        # to refresh LOD blocks against the camera focal point.
        self._geomip_terrain_handle: object | None = None

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

        # WK22 R3: per-sim-object billboard animation (wall clock). WK66: each entry
        # also tracks "last_seq" — the sim's anim_trigger_seq we last played — so a
        # one-shot plays once per new trigger without writing back to the entity.
        self._unit_anim_state: dict = {}
        # WK68 R2 (Agent 09): renderer-owned movement-facing scratch, keyed by the
        # stable render entity_id (string). Replaces the old write-back of
        # ``_ks_facing`` / ``_ks_last_x`` onto the live sim entity (which the renderer
        # no longer holds — it reads frozen DTOs). Value: {"facing": int, "last_x": float}.
        self._unit_facing_state: dict[str, dict] = {}
        # WK66 L2: renderer-owned record of POIs force-revealed by debug mode
        # (KINGDOM_DEBUG_SHOW_ALL_POIS), keyed by stable entity_id. Replaces the
        # old renderer writes of b.is_discovered / world.visibility = SEEN.
        self._debug_revealed_pois: dict[str, bool] = {}
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

        # WK57 Wave 3: layer visibility state (camera layer set each frame by UrsinaApp).
        # WK80 (Agent 09): the underground RENDER state (_underground_mgr / cave-shader rev /
        # _underground_lights) was removed — its render body died in WK65 (early-return
        # _sync_underground_meshes, since deleted in WK80). The SIM-side dungeon
        # (poi_interaction._handle_dungeon) is unaffected; restore from git (WK57) to revive.
        self._camera_active_layer: int = 0  # set each frame by UrsinaApp

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

    def _facing_from_dto(self, dto) -> int:
        # WK89 Round B-6 (Agent 09): pure-move to ursina_units_anim.py behind this
        # delegating wrapper. The movement scratch (``_unit_facing_state``) stays on
        # the renderer; the function reads it via ``r``. Call sites unchanged.
        from game.graphics import ursina_units_anim
        return ursina_units_anim.facing_from_dto(self, dto)

    def _compute_anim_frame(self, obj_id, entity, unit_type: str, class_key: str, base_clip_fn=None) -> tuple:
        # WK89 Round B-6 (Agent 09): pure-move to ursina_units_anim.py behind this
        # delegating wrapper. The per-entity anim-state FSM (``_unit_anim_state``) and
        # the sim-tick id (``_frame_tick_id``, the WK67 sim-tick anim clock basis) stay
        # on the renderer; the function reads them via ``r``. Call sites unchanged.
        from game.graphics import ursina_units_anim
        return ursina_units_anim.compute_anim_frame(self, obj_id, entity, unit_type, class_key, base_clip_fn)

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
        from game.graphics import ursina_frustum
        return ursina_frustum.get_visible_tile_rect(self)

    def _entity_in_view(self, sim_x, sim_y):
        from game.graphics import ursina_frustum
        return ursina_frustum.entity_in_view(self, sim_x, sim_y)

    def update(self, snapshot: "RenderSnapshot", frame: "PresentationFrameState | None" = None):
        """Called every frame by the Ursina app loop.

        WK67 Move 4 / L6: presentation timing (``sim_blend_fraction``/``sim_tick_id``)
        is no longer on the sim ``snapshot`` — it arrives on ``frame`` (a
        :class:`~game.sim.snapshot.PresentationFrameState`). ``frame`` defaults to a
        neutral ``PresentationFrameState()`` so callers that don't drive interpolation
        keep working; the real Ursina app loop always passes the engine-built frame.
        """
        if frame is None:
            from game.sim.snapshot import PresentationFrameState

            frame = PresentationFrameState()

        try:
            from game.types import HeroClass
        except Exception:
            HeroClass = None

        # WK58 Wave 5 (Agent 10) — per-stage profiling. Off by default; enable with
        # KINGDOM_URSINA_STAGE_PROFILE=1 to record per-substage ms in self._stage_ms_samples.
        # Removed/disabled by default before reporting done.
        _stage_profile = os.environ.get("KINGDOM_URSINA_STAGE_PROFILE", "0") == "1"
        if _stage_profile:
            if not hasattr(self, "_stage_ms_samples"):
                self._stage_ms_samples: dict[str, list[float]] = {}
            _stage_samples = self._stage_ms_samples
            _perf = time.perf_counter
            def _rec(name, t0):
                _stage_samples.setdefault(name, []).append((_perf() - t0) * 1000.0)
            _t0 = _perf()
        else:
            _rec = None
            _t0 = 0.0

        self._ensure_shadow_bounds_once()
        if _stage_profile: _rec("01_ensure_shadow_bounds_once", _t0); _t0 = time.perf_counter()

        # R4: cache sim interpolation state for this frame.
        # WK67 Move 4 / L6: these are presentation timing — read from ``frame``, not snapshot.
        self._frame_blend = float(getattr(frame, 'sim_blend_fraction', 0.0))
        self._frame_tick_id = int(getattr(frame, 'sim_tick_id', 0))

        # WK59 perf: cache visible tile rect for frustum culling this frame
        self._frame_visible_rect = self._get_visible_tile_rect()
        if _stage_profile: _rec("02_get_visible_tile_rect", _t0); _t0 = time.perf_counter()

        world = getattr(snapshot, "world", None) or self._world
        fog_revision = int(getattr(snapshot, "fog_revision", 0))
        # WK68 R2 (Agent 09): feed the one-time terrain build the frozen BuildingDTOs.
        # _building_occupied_tiles reads b.grid_x/grid_y/size — now carried by the DTO.
        self._terrain_fog.build_3d_terrain(world, getattr(snapshot, "building_dtos", ()))
        # WK58 W8 (4.C): per-frame LOD refresh for the GeoMipTerrain display
        # path (env-flag gated; handle is None when the custom Mesh path is
        # active, so this is a cheap attribute read in the default case).
        _gmt = getattr(self, "_geomip_terrain_handle", None)
        if _gmt is not None:
            _gmt.update_lod()
        if _stage_profile: _rec("03_build_3d_terrain", _t0); _t0 = time.perf_counter()
        self._terrain_fog.sync_dynamic_trees(world, getattr(snapshot, "trees", ()) or ())
        if _stage_profile: _rec("04_sync_dynamic_trees", _t0); _t0 = time.perf_counter()
        self._terrain_fog.sync_log_stacks(world, getattr(snapshot, "log_stacks", ()) or ())
        if _stage_profile: _rec("05_sync_log_stacks", _t0); _t0 = time.perf_counter()
        self._terrain_fog.ensure_fog_overlay(world, fog_revision)
        if _stage_profile: _rec("06_ensure_fog_overlay", _t0); _t0 = time.perf_counter()
        self._terrain_fog.sync_visibility_gated_terrain(world, fog_revision)
        if _stage_profile: _rec("07_sync_visibility_gated_terrain", _t0); _t0 = time.perf_counter()
        self._terrain_fog.cull_terrain_chunks(self._frame_visible_rect, world)
        if _stage_profile: _rec("08_cull_terrain_chunks", _t0); _t0 = time.perf_counter()
        # WK68 R2 (Agent 09): grid-debug overlay reads b.building_type=="castle" — DTO ok.
        self._terrain_fog.ensure_grid_debug_overlay(world, getattr(snapshot, "building_dtos", ()))
        if _stage_profile: _rec("09_ensure_grid_debug_overlay", _t0); _t0 = time.perf_counter()

        # WK47 Wave 2b: hardware-instanced units (snapshot → buffer texture).
        # Opt-in: set KINGDOM_URSINA_INSTANCING=1 (known visual issues — see project memory).
        if os.environ.get("KINGDOM_URSINA_INSTANCING", "0") == "1":
            if not hasattr(self, "_instanced_unit_renderer"):
                from game.graphics.instanced_unit_renderer import InstancedUnitRenderer

                self._instanced_unit_renderer = InstancedUnitRenderer()
            active_ids: set[int] = set()
            self._sync_snapshot_buildings(snapshot, world, active_ids)
            # WK67 Wave 5: forward the sim tick so the instanced anim FSM uses the
            # SAME tick basis as the legacy path (deterministic captures under
            # DETERMINISTIC_SIM; wall-clock otherwise).
            unit_ids = self._instanced_unit_renderer.update(snapshot, self._frame_tick_id)
            active_ids.update(unit_ids)
            # Projectiles draw inside ``InstancedUnitRenderer`` (wk48); skip legacy Entities.
            self._update_debug_status_text(snapshot)
            self._destroy_removed_entities(active_ids)
            return

        active_ids = set()
        self._sync_snapshot_buildings(snapshot, world, active_ids)
        if _stage_profile: _rec("10_sync_snapshot_buildings", _t0); _t0 = time.perf_counter()
        self._sync_snapshot_heroes(snapshot, active_ids, HeroClass)
        if _stage_profile: _rec("12_sync_snapshot_heroes", _t0); _t0 = time.perf_counter()
        self._sync_snapshot_enemies(snapshot, world, active_ids)
        if _stage_profile: _rec("13_sync_snapshot_enemies", _t0); _t0 = time.perf_counter()
        self._sync_snapshot_peasants(snapshot, active_ids)
        if _stage_profile: _rec("14_sync_snapshot_peasants", _t0); _t0 = time.perf_counter()
        self._sync_snapshot_guards(snapshot, active_ids)
        if _stage_profile: _rec("15_sync_snapshot_guards", _t0); _t0 = time.perf_counter()
        self._sync_snapshot_tax_collector(snapshot, active_ids)
        if _stage_profile: _rec("16_sync_snapshot_tax_collector", _t0); _t0 = time.perf_counter()
        self._sync_snapshot_projectiles(snapshot, active_ids)
        if _stage_profile: _rec("17_sync_snapshot_projectiles", _t0); _t0 = time.perf_counter()
        self._sync_snapshot_bounties(snapshot, active_ids)
        if _stage_profile: _rec("17b_sync_snapshot_bounties", _t0); _t0 = time.perf_counter()
        self._sync_snapshot_rubble(snapshot)
        if _stage_profile: _rec("17c_sync_snapshot_rubble", _t0); _t0 = time.perf_counter()
        self._update_debug_status_text(snapshot)
        if _stage_profile: _rec("18_update_debug_status_text", _t0); _t0 = time.perf_counter()
        self._destroy_removed_entities(active_ids)
        if _stage_profile: _rec("19_destroy_removed_entities", _t0)

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

    def _sync_snapshot_buildings(self, snapshot: "SimStateSnapshot", world, active_ids: set) -> None:
        # WK91 (Agent 09): pure-moved to ursina_building_sync.sync_snapshot_buildings.
        from game.graphics import ursina_building_sync
        return ursina_building_sync.sync_snapshot_buildings(self, snapshot, world, active_ids)

    def _sync_snapshot_heroes(self, snapshot: "SimStateSnapshot", active_ids: set, HeroClass) -> None:
        # Heroes — atlas UV billboards (WK59 perf: single shared texture, UV offset per frame)
        # WK68 R2 (Agent 09): consume frozen UnitDTOs and key self._entities on the stable
        # dto.entity_id (string) — NOT id(h). id() of a per-frame DTO is unstable; entity_id
        # is consistent across create / cull / re-enable / destroy.
        _active_layer = self._camera_active_layer
        for h in getattr(snapshot, "hero_dtos", ()):
            if not getattr(h, "is_alive", True):
                continue
            obj_id = h.entity_id
            # WK57 Wave 3: Layer-aware visibility — hide heroes on a different layer
            _hero_layer = getattr(h, 'layer', 0)
            if _hero_layer != _active_layer:
                _h_existing = self._entities.get(obj_id)
                if _h_existing is not None:
                    _h_existing.enabled = False
                    active_ids.add(obj_id)
                continue
            # WK59 perf: frustum culling — skip heroes outside visible tile rect
            if not self._entity_in_view(h.x, h.y):
                _h_existing = self._entities.get(obj_id)
                if _h_existing is not None:
                    _h_existing.enabled = False
                    active_ids.add(obj_id)
                continue
            # Re-enable hero if it was previously culled and is now in view
            _h_reenable = self._entities.get(obj_id)
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
                key=obj_id,
            )
            wx, wz = sim_px_to_world_xz(h.x, h.y)
            terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0
            y_center = terrain_y + sy * 0.5
            facing = self._facing_from_dto(h)
            sx = sy * facing  # negative scale_x flips the billboard horizontally

            self._sync_unit_atlas_billboard(
                ent, obj_id, h, "hero", hc_key, None,
                col, (sx, sy, 1), (wx, y_center, wz), sprite_unlit_shader,
            )
            # Layer compositing (not Y offset): draw after building billboards; skip depth so the
            # "inside" bubble paints over the same footprint as the facade.
            self._entity_render.sync_inside_hero_draw_layer(ent, bool(getattr(h, "is_inside_building", False)))

            # --- R5: Native Ursina health bar (Agent 09) ---
            # WK62: delegates to ursina_unit_overlays.sync_hp_bar
            _h_hp = int(getattr(h, 'hp', 0) or 0)
            _h_max_hp = int(getattr(h, 'max_hp', 1) or 1)
            sync_hp_bar(ent, _h_hp, _h_max_hp, HERO_SPEC)

            # --- R5: Hero name label (Agent 08) ---
            hero_name = getattr(h, 'name', '') or ''
            _ensure_ks_name_label(ent, '_ks_name_label', hero_name, y=HERO_SPEC.label_y, scale=HERO_SPEC.label_scale)

            # --- R5: Hero gold display (Agent 08) ---
            # WK62: delegates to ursina_unit_overlays.sync_hero_gold_label
            hero_gold = int(getattr(h, 'gold', 0) or 0)
            hero_taxed = int(getattr(h, 'taxed_gold', 0) or 0)
            sync_hero_gold_label(ent, hero_gold, hero_taxed)

            # --- R5: Hero rest indicator (Agent 08) ---
            # WK62: delegates to ursina_unit_overlays.sync_hero_rest_label
            # WK68 R2 (Agent 09): BEHAVIOR-PRESERVING. The legacy line compared the live
            # ``hero.state`` (a plain ``HeroState`` Enum, NOT a str-enum) to the string
            # 'RESTING' — which is ALWAYS False, so the "Zzz" label never showed. The DTO
            # flattens state to the string 'RESTING' when resting, so reading dto.state
            # here would FLIP this on and add a label that legacy never drew. To keep the
            # captures byte-identical we reproduce the legacy always-False result.
            # (Latent dead indicator — flagged to Agent 08/UX; fix belongs in their lane.)
            is_resting = False
            sync_hero_rest_label(ent, is_resting)

            # WK61-R4-BUG-001: un-mirror overlay children when parent faces left.
            # WK62: delegates to ursina_unit_overlays.sync_hero_overlays_facing
            sync_hero_overlays_facing(ent, facing)

            active_ids.add(obj_id)


    def _sync_snapshot_enemies(self, snapshot: "SimStateSnapshot", world, active_ids: set) -> None:
        # Enemies — atlas UV billboards (WK59 perf: single shared texture)
        # WK68 R2 (Agent 09): frozen UnitDTOs keyed on the stable dto.entity_id (not id(e)).
        _active_layer = self._camera_active_layer
        ts = float(config.TILE_SIZE)
        for e in getattr(snapshot, "enemy_dtos", ()):
            obj_id = e.entity_id
            # WK57 Wave 3: Layer-aware visibility — hide enemies on a different layer
            _enemy_layer = getattr(e, 'layer', 0)
            if _enemy_layer != _active_layer:
                _e_existing = self._entities.get(obj_id)
                if _e_existing is not None:
                    _e_existing.enabled = False
                    active_ids.add(obj_id)
                continue

            tx, ty = int(e.x / ts), int(e.y / ts)
            is_visible = True
            if 0 <= ty < world.height and 0 <= tx < world.width:
                is_visible = (world.visibility[ty][tx] == Visibility.VISIBLE)

            if not getattr(e, "is_alive", True) or not is_visible:
                continue
            # WK59 perf: frustum culling — skip enemies outside visible tile rect
            if not self._entity_in_view(e.x, e.y):
                _e_existing = self._entities.get(obj_id)
                if _e_existing is not None:
                    _e_existing.enabled = False
                    active_ids.add(obj_id)
                continue
            # Re-enable enemy if it was previously culled and is now in view
            _e_reenable = self._entities.get(obj_id)
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
                key=obj_id,
            )
            wx, wz = sim_px_to_world_xz(e.x, e.y)
            terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0
            facing_e = self._facing_from_dto(e)
            sx_e = s * facing_e

            self._sync_unit_atlas_billboard(
                ent, obj_id, e, "enemy", et_key, None,
                col, (sx_e, s, 1), (wx, terrain_y + s * 0.5, wz), sprite_unlit_shader,
            )

            # --- R5: Native Ursina health bar (Agent 09) ---
            # WK62: delegates to ursina_unit_overlays.sync_hp_bar
            _e_hp = int(getattr(e, 'hp', 0) or 0)
            _e_max_hp = int(getattr(e, 'max_hp', 1) or 1)
            sync_hp_bar(ent, _e_hp, _e_max_hp, ENEMY_SPEC)

            enemy_label = str(getattr(e, "enemy_type", "enemy") or "enemy").replace("_", " ").title()
            _ensure_ks_name_label(ent, "_ks_name_label", enemy_label, y=ENEMY_SPEC.label_y, scale=ENEMY_SPEC.label_scale)

            # WK62: delegates to ursina_unit_overlays.sync_unit_overlays_facing
            sync_unit_overlays_facing(ent, facing_e)

            active_ids.add(obj_id)


    def _sync_snapshot_peasants(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # Peasants — atlas UV billboards (WK59 perf: single shared texture)
        # WK68 R2 (Agent 09): frozen UnitDTOs keyed on the stable dto.entity_id (not id(p)).
        _active_layer = self._camera_active_layer
        for p in getattr(snapshot, "peasant_dtos", ()):
            if not getattr(p, "is_alive", True):
                continue
            if bool(getattr(p, "is_inside_castle", False)):
                continue
            obj_id = p.entity_id
            # WK57 Wave 3: Peasants are always surface (layer 0) — hide when camera underground
            if _active_layer != 0:
                _p_existing = self._entities.get(obj_id)
                if _p_existing is not None:
                    _p_existing.enabled = False
                    active_ids.add(obj_id)
                continue
            # WK59 perf: frustum culling — skip peasants outside visible tile rect
            if not self._entity_in_view(p.x, p.y):
                _p_existing = self._entities.get(obj_id)
                if _p_existing is not None:
                    _p_existing.enabled = False
                    active_ids.add(obj_id)
                continue
            # Re-enable peasant if it was previously culled and is now in view
            _p_reenable = self._entities.get(obj_id)
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
                key=obj_id,
            )
            wx, wz = sim_px_to_world_xz(p.x, p.y)
            terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

            self._sync_unit_atlas_billboard(
                ent, obj_id, p, "worker", wk, None,
                col, (sx, sy, 1), (wx, terrain_y + sy * 0.5, wz), sprite_unlit_shader,
            )

            # --- R5: Native Ursina health bar (Agent 09) ---
            # WK62: delegates to ursina_unit_overlays.sync_hp_bar
            _p_hp = int(getattr(p, 'hp', 0) or 0)
            _p_max_hp = int(getattr(p, 'max_hp', 1) or 1)
            sync_hp_bar(ent, _p_hp, _p_max_hp, PEASANT_SPEC)

            worker_label = str(getattr(p, "render_worker_type", "peasant") or "peasant").replace("_", " ").title()
            _ensure_ks_name_label(ent, "_ks_name_label", worker_label, y=PEASANT_SPEC.label_y, scale=PEASANT_SPEC.label_scale)

            active_ids.add(obj_id)


    def _sync_snapshot_guards(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # Guards — atlas UV billboards (WK59 perf: single shared texture)
        # WK68 R2 (Agent 09): frozen UnitDTOs keyed on the stable dto.entity_id (not id(g)).
        _active_layer = self._camera_active_layer
        for g in getattr(snapshot, "guard_dtos", ()):
            if not getattr(g, "is_alive", True):
                continue
            obj_id = g.entity_id
            # WK57 Wave 3: Guards are always surface (layer 0) — hide when camera underground
            if _active_layer != 0:
                _g_existing = self._entities.get(obj_id)
                if _g_existing is not None:
                    _g_existing.enabled = False
                    active_ids.add(obj_id)
                continue
            # WK59 perf: frustum culling — skip guards outside visible tile rect
            if not self._entity_in_view(g.x, g.y):
                _g_existing = self._entities.get(obj_id)
                if _g_existing is not None:
                    _g_existing.enabled = False
                    active_ids.add(obj_id)
                continue
            # Re-enable guard if it was previously culled and is now in view
            _g_reenable = self._entities.get(obj_id)
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
                key=obj_id,
            )
            wx, wz = sim_px_to_world_xz(g.x, g.y)
            terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

            self._sync_unit_atlas_billboard(
                ent, obj_id, g, "worker", "guard", None,
                col, (GUARD_SCALE_XZ, GUARD_SCALE_Y, 1),
                (wx, terrain_y + GUARD_SCALE_Y * 0.5, wz), sprite_unlit_shader,
            )

            # --- R5: Native Ursina health bar (Agent 09) ---
            # WK62: delegates to ursina_unit_overlays.sync_hp_bar
            _g_hp = int(getattr(g, 'hp', 0) or 0)
            _g_max_hp = int(getattr(g, 'max_hp', 1) or 1)
            sync_hp_bar(ent, _g_hp, _g_max_hp, GUARD_SPEC)

            _ensure_ks_name_label(ent, "_ks_name_label", "Guard", y=GUARD_SPEC.label_y, scale=GUARD_SPEC.label_scale)

            active_ids.add(obj_id)


    def _sync_snapshot_tax_collector(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # Tax Collector — atlas UV billboards (WK59 perf: single shared texture)
        # WK68 R2 (Agent 09): frozen UnitDTO (tax_collector_dto) keyed on the stable
        # dto.entity_id (not id(tc)).
        tc = getattr(snapshot, "tax_collector_dto", None)
        if tc is not None:
            tc_id = tc.entity_id
            if not getattr(tc, "is_alive", True):
                pass
            # WK57 Wave 3: Tax collector is always surface — hide when camera underground
            elif self._camera_active_layer != 0:
                _tc_existing = self._entities.get(tc_id)
                if _tc_existing is not None:
                    _tc_existing.enabled = False
                    active_ids.add(tc_id)
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
                    key=tc_id,
                )
                wx, wz = sim_px_to_world_xz(tc.x, tc.y)
                terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

                self._sync_unit_atlas_billboard(
                    ent, obj_id, tc, "worker", "tax_collector", None,
                    col, (sx, sy, 1), (wx, terrain_y + sy * 0.5, wz), sprite_unlit_shader,
                )

                _ensure_ks_name_label(ent, "_ks_name_label", "Tax Collector", y=TAX_COLLECTOR_SPEC.label_y, scale=TAX_COLLECTOR_SPEC.label_scale)

                # --- R5: Tax collector gold display (Agent 08) ---
                carried = int(getattr(tc, 'carried_gold', 0) or 0)
                tc_gold_ent = getattr(ent, '_ks_tc_gold', None)
                if carried > 0:
                    tc_text = f"${carried}"
                    if tc_gold_ent is None:
                        from ursina import Text as UrsinaText
                        tc_gold_ent = UrsinaText(
                            text=tc_text, parent=ent, origin=(0, 0), scale=10,
                            color=color.rgb(1.0, 0.8, 0.2), billboard=True, y=0.35,
                        )
                        _configure_ks_overlay(tc_gold_ent)
                        ent._ks_tc_gold = tc_gold_ent
                    else:
                        if tc_gold_ent.text != tc_text:
                            tc_gold_ent.text = tc_text
                        tc_gold_ent.enabled = True
                        _configure_ks_overlay(tc_gold_ent)
                elif tc_gold_ent is not None:
                    tc_gold_ent.enabled = False

                active_ids.add(obj_id)


    def _sync_snapshot_projectiles(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # WK90 (Agent 09): pure-moved to ursina_misc_props_sync.sync_snapshot_projectiles.
        from game.graphics import ursina_misc_props_sync
        return ursina_misc_props_sync.sync_snapshot_projectiles(self, snapshot, active_ids)

    # ------------------------------------------------------------------
    # WK60 Feature 7: Bounty flag 3D rendering
    # ------------------------------------------------------------------
    # Constants for bounty flag visual elements (read by
    # ursina_misc_props_sync.sync_snapshot_bounties via ``r._BOUNTY_*``).
    _BOUNTY_POLE_HEIGHT = 0.6
    _BOUNTY_POLE_RADIUS = 0.02
    _BOUNTY_FLAG_SCALE = (0.18, 0.12, 0.01)
    _BOUNTY_FLAG_OFFSET_Y = 0.05  # flag sits slightly below pole top
    _BOUNTY_TEXT_OFFSET_Y = 0.12  # text sits above pole top

    def _sync_snapshot_bounties(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # WK90 (Agent 09): pure-moved to ursina_misc_props_sync.sync_snapshot_bounties.
        from game.graphics import ursina_misc_props_sync
        return ursina_misc_props_sync.sync_snapshot_bounties(self, snapshot, active_ids)

    # ------------------------------------------------------------------
    # WK61-FEAT-004: Rubble rendering (destroyed building debris)
    # ------------------------------------------------------------------

    def _sync_snapshot_rubble(self, snapshot: "SimStateSnapshot") -> None:
        # WK90 (Agent 09): pure-moved to ursina_misc_props_sync.sync_snapshot_rubble.
        from game.graphics import ursina_misc_props_sync
        return ursina_misc_props_sync.sync_snapshot_rubble(self, snapshot)

    def _update_debug_status_text(self, snapshot: "SimStateSnapshot") -> None:
        # WK68 R2 (Agent 09): counts from the frozen DTO tuples (same values as the live
        # tuples — equal length; hero alive-filter mirrors the live read).
        heroes_alive = len([h for h in getattr(snapshot, "hero_dtos", ()) if getattr(h, "is_alive", True)])
        enemies_alive = len(getattr(snapshot, "enemy_dtos", ()))
        status_text = (
            f"Gold: {getattr(snapshot, 'gold', 0)}  |  Heroes: {heroes_alive}  |  "
            f"Enemies: {enemies_alive}  |  Buildings: {len(getattr(snapshot, 'building_dtos', ())) }"
        )
        if self.status_text.text != status_text:
            self.status_text.text = status_text


    def _destroy_removed_entities(self, active_ids: set) -> None:
        dead_ids = set(self._entities.keys()) - active_ids
        for obj_id in dead_ids:
            self._unit_anim_state.pop(obj_id, None)
            # WK68 R2 (Agent 09): drop the entity_id-keyed facing scratch too (units only;
            # a no-op miss for building/projectile keys). Prevents unbounded growth.
            self._unit_facing_state.pop(obj_id, None)
            ent = self._entities.pop(obj_id)
            gold = getattr(ent, "_ks_gold_label", None)
            if gold is not None:
                try:
                    import ursina as _u

                    _u.destroy(gold)
                except Exception:
                    pass
            import ursina

            ursina.destroy(ent)

