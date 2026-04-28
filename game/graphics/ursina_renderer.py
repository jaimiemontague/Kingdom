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

if TYPE_CHECKING:
    from game.sim.snapshot import SimStateSnapshot

# Fallback tints when a texture is missing
COLOR_HERO = color.azure
COLOR_ENEMY = color.red
COLOR_PEASANT = color.orange
COLOR_GUARD = color.yellow
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

# Pixel billboard height in world units (32px sprite read at map scale)
UNIT_BILLBOARD_SCALE = 0.62

# Stable bridge keys — never use id(surface) alone for multi-megapixel sheets (see terrain_texture_bridge).
_FOG_TEX_KEY = "kingdom_ursina_fog_overlay"

ENEMY_SCALE = 0.5
PEASANT_SCALE = 0.465
GUARD_SCALE_XZ = 0.5
GUARD_SCALE_Y = 0.7

# Ranged VFX billboards — smaller than unit sprites, readable in perspective.
# 0.3 was large in playtest; 25% of that keeps arrows visible (snapshot + depth fix) without dominating the frame.
PROJECTILE_BILLBOARD_SCALE = 0.075
# Vertical lift: match enemy sprite center (ENEMY_SCALE*0.5) so arrows aren't drawn under terrain.
PROJECTILE_BILLBOARD_Y = ENEMY_SCALE * 0.5

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
    _hero_base_clip,
    _enemy_base_clip,
    _worker_idle_surface,
)

from game.graphics.ursina_entity_render_collab import UrsinaEntityRenderCollab
from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab

class UrsinaRenderer:
    def __init__(self, world):
        self._world = world

        # Entity mappings: simulation object id() -> Ursina Entity
        self._entities = {}
        # WK44 Stage 2: dynamic trees keyed by tile (tx,ty) for growth scaling.
        self._tree_entities: dict[tuple[int, int], Entity] = {}

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
        cache_key = (cache_prefix, "anim", class_key, clip_name, idx, int(config.TILE_SIZE))
        return surf, cache_key

    def update(self, snapshot: "SimStateSnapshot"):
        """Called every frame by the Ursina app loop."""
        try:
            from game.types import HeroClass
        except Exception:
            HeroClass = None

        self._ensure_shadow_bounds_once()

        world = getattr(snapshot, "world", None) or self._world
        fog_revision = int(getattr(snapshot, "fog_revision", 0))
        self._terrain_fog.build_3d_terrain(world, getattr(snapshot, "buildings", ()))
        self._terrain_fog.sync_dynamic_trees(world, getattr(snapshot, "trees", ()) or ())
        self._terrain_fog.ensure_fog_overlay(world, fog_revision)
        self._terrain_fog.sync_visibility_gated_terrain(world, fog_revision)
        self._terrain_fog.ensure_grid_debug_overlay(world, getattr(snapshot, "buildings", ()))

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

    def _sync_snapshot_buildings(self, snapshot: "SimStateSnapshot", world, active_ids: set) -> None:
        # Buildings — billboard quads, except castle / house / lair (v1.5 Sprint 2.1: lit 3D meshes).
        for b in getattr(snapshot, "buildings", ()):
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
                )
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
                pos_xyz=(wx, hy * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        
    def _sync_snapshot_heroes(self, snapshot: "SimStateSnapshot", active_ids: set, HeroClass) -> None:
        # Heroes — pixel billboards (WK22 R3: walk/idle/inside + attack/hurt from _render_anim_trigger)
        for h in getattr(snapshot, "heroes", ()):
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
                elif hc == HeroClass.CLERIC or str(hc).lower() == "cleric":
                    col = color.rgb(48 / 255, 186 / 255, 178 / 255)

            hc_key = str(getattr(h, "hero_class", "warrior") or "warrior").lower()
            clips_h = HeroSpriteLibrary.clips_for(hc_key, size=int(config.TILE_SIZE))
            sy = UNIT_BILLBOARD_SCALE
            ent, obj_id = self._entity_render.get_or_create_entity(
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
            self._entity_render.sync_billboard_entity(
                ent,
                tex=htex,
                tint_col=col,
                scale_xyz=(sy, sy, 1),
                pos_xyz=(wx, y_center, wz),
                shader=sprite_unlit_shader,
            )
            # Layer compositing (not Y offset): draw after building billboards; skip depth so the
            # "inside" bubble paints over the same footprint as the façade.
            self._entity_render.sync_inside_hero_draw_layer(ent, bool(getattr(h, "is_inside_building", False)))
            active_ids.add(obj_id)

        
    def _sync_snapshot_enemies(self, snapshot: "SimStateSnapshot", world, active_ids: set) -> None:
        # Enemies — billboards (same animation contract as pygame EnemyRenderer)
        ts = float(config.TILE_SIZE)
        for e in getattr(snapshot, "enemies", ()):
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
            ent, obj_id = self._entity_render.get_or_create_entity(
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
            self._entity_render.sync_billboard_entity(
                ent,
                tex=etex,
                tint_col=col,
                scale_xyz=(s, s, 1),
                pos_xyz=(wx, s * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        
    def _sync_snapshot_peasants(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # Peasants — billboards
        for p in getattr(snapshot, "peasants", ()):
            if not getattr(p, "is_alive", True):
                continue
            s = PEASANT_SCALE
            # Default: preserve sprite native colors (no tint multiplier).
            col = color.white
            tint_textured = False
            raw_col = getattr(p, "color", None)
            if isinstance(raw_col, tuple) and len(raw_col) >= 3:
                try:
                    r, g, b = int(raw_col[0]), int(raw_col[1]), int(raw_col[2])
                    col = color.rgb(r / 255.0, g / 255.0, b / 255.0)
                except Exception:
                    col = color.white

            # Builder peasants should be visibly distinct (green tint).
            # Avoid importing sim classes into renderer; use a lightweight type-name check.
            if getattr(p, "__class__", None) is not None and getattr(p.__class__, "__name__", "") == "BuilderPeasant":
                tint_textured = True
            psurf = _worker_idle_surface("peasant")
            ptex = TerrainTextureBridge.surface_to_texture(
                psurf, cache_key=("worker_idle", "peasant", int(config.TILE_SIZE))
            )
            ent, obj_id = self._entity_render.get_or_create_entity(
                p,
                model="quad",
                col=color.white,
                scale=(s, s, 1),
                texture=ptex,
                billboard=True,
            )
            wx, wz = sim_px_to_world_xz(p.x, p.y)
            self._entity_render.sync_billboard_entity(
                ent,
                tex=ptex,
                tint_col=col,
                scale_xyz=(s, s, 1),
                pos_xyz=(wx, s * 0.5, wz),
                shader=sprite_unlit_shader,
                tint_textured=tint_textured,
            )
            active_ids.add(obj_id)

        
    def _sync_snapshot_guards(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # Guards — billboards
        for g in getattr(snapshot, "guards", ()):
            if not getattr(g, "is_alive", True):
                continue
            col = COLOR_GUARD
            gsurf = _worker_idle_surface("guard")
            gtex = TerrainTextureBridge.surface_to_texture(
                gsurf, cache_key=("worker_idle", "guard", int(config.TILE_SIZE))
            )
            sxz = GUARD_SCALE_XZ
            sy = GUARD_SCALE_Y
            ent, obj_id = self._entity_render.get_or_create_entity(
                g,
                model="quad",
                col=color.white,
                scale=(sxz, sy, 1),
                texture=gtex,
                billboard=True,
            )
            wx, wz = sim_px_to_world_xz(g.x, g.y)
            self._entity_render.sync_billboard_entity(
                ent,
                tex=gtex,
                tint_col=col,
                scale_xyz=(sxz, sy, 1),
                pos_xyz=(wx, sy * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        
    def _sync_snapshot_tax_collector(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # Tax Collector — billboards
        tc = getattr(snapshot, "tax_collector", None)
        if tc is not None:
            if not getattr(tc, "is_alive", True):
                pass
            else:
                col = COLOR_PEASANT
                tcsurf = _worker_idle_surface("tax_collector")
                tctex = TerrainTextureBridge.surface_to_texture(
                    tcsurf, cache_key=("worker_idle", "tax_collector", int(config.TILE_SIZE))
                )
                s = PEASANT_SCALE
                ent, obj_id = self._entity_render.get_or_create_entity(
                    tc,
                    model="quad",
                    col=color.white,
                    scale=(s, s, 1),
                    texture=tctex,
                    billboard=True,
                )
                wx, wz = sim_px_to_world_xz(tc.x, tc.y)
                self._entity_render.sync_billboard_entity(
                    ent,
                    tex=tctex,
                    tint_col=col,
                    scale_xyz=(s, s, 1),
                    pos_xyz=(wx, s * 0.5, wz),
                    shader=sprite_unlit_shader,
                )
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
            self._entity_render.sync_billboard_entity(
                ent,
                tex=ptex,
                tint_col=color.white,
                scale_xyz=(s, s, 1),
                pos_xyz=(wx, PROJECTILE_BILLBOARD_Y, wz),
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

