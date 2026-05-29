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
_debug_tax_overlay = os.environ.get("KINGDOM_DEBUG_TAX_OVERLAY", "").strip().lower() in ("1", "true", "yes")
_tax_overlay_debug_last_print: float = 0.0

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

# WK61-R4: polled from engine/input each frame; renderer also checks Ursina held_keys.
_tax_gold_overlay_held: bool = False


def set_tax_gold_overlay_held(held: bool) -> None:
    global _tax_gold_overlay_held
    _tax_gold_overlay_held = bool(held)


def is_tax_gold_overlay_held() -> bool:
    if _tax_gold_overlay_held:
        return True
    try:
        from ursina import held_keys
        return bool(held_keys.get("g", 0))
    except Exception:
        return False


def building_tax_overlay_snapshot(b, *, is_lair: bool) -> tuple[bool, int]:
    """Return (has_tax_field, amount) for hold-G building gold overlays (WK61-R6)."""
    if is_lair or getattr(b, "is_poi", False):
        return False, 0
    if hasattr(b, "get_overlay_tax_gold"):
        if not getattr(b, "has_tax_stash_data", True):
            return False, 0
        gold = b.get_overlay_tax_gold()
        if gold is None:
            return False, 0
        return True, int(gold)
    if hasattr(b, "stored_tax_gold"):
        return True, int(getattr(b, "stored_tax_gold", 0) or 0)
    return False, 0


def _prefab_local_top_y(ent) -> float:
    """Estimate prefab roof height in parent-local Y for overlay placement."""
    cached = getattr(ent, "_ks_prefab_top_y", None)
    if cached is not None:
        return float(cached)
    max_y = 1.2
    for child in getattr(ent, "children", []) or []:
        try:
            py = float(getattr(child, "y", 0) or 0)
            sc = getattr(child, "scale", None)
            sy = float(getattr(sc, "y", 1) if sc is not None else 1)
            max_y = max(max_y, py + abs(sy) * 0.55)
        except Exception:
            continue
    ent._ks_prefab_top_y = max_y
    return max_y


def _building_gold_overlay_y(ent, *, hy: float = 1.0) -> float:
    """Readable local Y offset for taxable gold Text above prefab or billboard buildings."""
    if getattr(ent, "_ks_prefab_container", False) or getattr(ent, "_ks_building_mode", None) == "prefab":
        return _prefab_local_top_y(ent) + 0.50
    if getattr(ent, "_ks_billboard_configured", False):
        return max(float(hy) * 0.75, 0.9)
    return max(float(hy) * 0.55, 1.8)


def _building_gold_overlay_world_y(ent, *, terrain_y: float, hy: float = 1.0) -> float:
    """World-space Y for hold-G gold billboards: terrain + roof + clearance (WK61-R11 BUG-004)."""
    roof_local = _building_gold_overlay_y(ent, hy=hy)
    if getattr(ent, "_ks_prefab_container", False) or getattr(ent, "_ks_building_mode", None) == "prefab":
        return float(terrain_y) + roof_local + 1.2
    if getattr(ent, "_ks_billboard_configured", False):
        return float(terrain_y) + roof_local + 1.2
    return float(terrain_y) + roof_local + 1.2


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


def _sync_building_worldspace_ui(
    b,
    bts: str,
    ent,
    is_lair: bool,
    *,
    wx: float = 0.0,
    wz: float = 0.0,
    terrain_y: float = 0.0,
    hy: float = 1.0,
) -> None:
    """R5 Phase 2 (Agent 03): Attach/update label, HP bar, and gold display
    as native Ursina child entities on a building entity.

    Skips POI buildings and lairs — only normal player-built buildings get labels.
    """
    # Skip POIs (discovery-gated) and lairs (enemy structures)
    if getattr(b, "is_poi", False) or is_lair:
        return

    # --- Building label --- (WK61-FEAT-001 / R4-BUG-001: no permanent prefab labels)
    label_ent = getattr(ent, "_ks_label", None)
    if label_ent is not None:
        label_ent.enabled = False
        if not getattr(ent, "_ks_label_removed", False):
            try:
                import ursina as _u
                _u.destroy(label_ent)
            except Exception:
                pass
            ent._ks_label_removed = True
            if hasattr(ent, "_ks_label"):
                delattr(ent, "_ks_label")

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

    # --- Gold display (WK61-R10/R11: show $0 while G held; world-space billboard above roof) ---
    has_tax, stash = building_tax_overlay_snapshot(b, is_lair=is_lair)
    g_held = is_tax_gold_overlay_held()
    gold_ent = getattr(ent, "_ks_gold_label", None)
    overlay_world_y = _building_gold_overlay_world_y(ent, terrain_y=terrain_y, hy=hy)
    if has_tax and g_held:
        text = f"${stash}"
        label_color = (
            color.rgb(1.0, 0.8, 0.2) if stash > 0 else color.rgb(0.55, 0.55, 0.55)
        )
        if gold_ent is None:
            gold_ent = Text(
                text=text,
                parent=scene,
                origin=(0, 0),
                scale=12,
                color=label_color,
                billboard=True,
            )
            _configure_ks_overlay(gold_ent)
            ent._ks_gold_label = gold_ent
        else:
            if getattr(gold_ent, "parent", None) is not scene:
                gold_ent.parent = scene
            if gold_ent.text != text:
                gold_ent.text = text
            gold_ent.color = label_color
            gold_ent.enabled = True
            _configure_ks_overlay(gold_ent)
        gold_ent.world_position = Vec3(float(wx), overlay_world_y, float(wz))
    elif gold_ent is not None:
        gold_ent.enabled = False


def _maybe_log_tax_overlay_debug(buildings) -> None:
    """Optional once/sec debug when KINGDOM_DEBUG_TAX_OVERLAY=1 (WK61-R10)."""
    global _tax_overlay_debug_last_print
    if not _debug_tax_overlay:
        return
    import time

    now = time.time()
    if now - _tax_overlay_debug_last_print < 1.0:
        return
    _tax_overlay_debug_last_print = now
    g_held = is_tax_gold_overlay_held()
    tax_count = 0
    stash_sum = 0
    for b in buildings or ():
        is_lair = hasattr(b, "stash_gold")
        has_tax, stash = building_tax_overlay_snapshot(b, is_lair=is_lair)
        if has_tax:
            tax_count += 1
            stash_sum += int(stash)
    print(
        f"[KINGDOM_DEBUG_TAX_OVERLAY] g_held={g_held} "
        f"tax_buildings={tax_count} sum_stash={stash_sum}"
    )


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
        self._unit_anim_state: dict[int, dict] = {}
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

        # WK57 Wave 2: Underground terrain mesh manager
        from game.graphics.underground_terrain import UndergroundTerrainManager
        self._underground_mgr = UndergroundTerrainManager()
        self._underground_cave_shader_rev = -1  # tracks when to update cave entrance shader

        # WK57 Wave 3: Underground lighting (torch PointLights) + layer visibility state
        self._underground_lights: list = []  # Panda3D PointLight NodePaths
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

    def _compute_anim_frame(self, obj_id, entity, unit_type: str, class_key: str, base_clip_fn) -> tuple:
        """Compute current animation clip name and frame index. Uses perf_counter for precision."""
        # WK66 Move 1a: read the one-shot trigger + the sim's monotonic
        # anim_trigger_seq and play when the seq advances vs our renderer-owned
        # last-seen value, instead of clearing the trigger on the entity. The
        # renderer no longer writes _ursina_anim_trigger/_render_anim_trigger back.
        trigger = getattr(entity, "_ursina_anim_trigger", None) or getattr(
            entity, "_render_anim_trigger", None
        )
        trigger_seq = int(getattr(entity, "_anim_trigger_seq", 0) or 0)

        base = base_clip_fn(entity)
        st = self._unit_anim_state.get(obj_id)
        now = time.perf_counter()
        last_seq = st.get("last_seq", -1) if st is not None else -1

        if trigger and trigger_seq != last_seq:
            tname = str(trigger)
            clips = self._get_cached_clips(unit_type, class_key)
            if tname in clips:
                self._unit_anim_state[obj_id] = {
                    "clip": tname,
                    "t0": now,
                    "base": base,
                    "oneshot": not clips[tname].loop,
                    "last_seq": trigger_seq,
                }
                st = self._unit_anim_state[obj_id]
            elif st is not None:
                # Unknown clip name: still record the seq so we don't re-evaluate it.
                st["last_seq"] = trigger_seq

        if st is None:
            self._unit_anim_state[obj_id] = {
                "clip": base, "t0": now, "base": base, "oneshot": False,
                "last_seq": trigger_seq,
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

        WK58 Phase 2 (WK58-BUG-002): replaces the ``cam_y * 1.8`` heuristic that
        covered ~88% of the map with a real lens-frustum query.  Strategy:

        1.  Try Panda3D ``base.camLens.extrude(corner)`` for the four NDC corners
            (-1,-1), (1,-1), (-1,1), (1,1).  Transform near/far points to world
            space and intersect each ray with the y=0 ground plane.  Use the
            bounding box of the four hits, plus a small safety margin.
        2.  If any corner ray fails to hit the ground plane (e.g. shallow
            pitch, no ``base`` in headless tests, lens API mismatch), fall
            back to an FOV-based heuristic: pitch + ``camera.fov`` give the
            near/far ground-hit distances, ``aspect_ratio`` scales the
            horizontal extent.  This still produces a much tighter rect than
            the old ``cam_y * 1.8`` formula.
        3.  If anything else goes wrong, return the full map rect for that
            frame (matches old fallback contract).
        """
        import math as _math

        map_w = int(config.MAP_WIDTH)
        map_h = int(config.MAP_HEIGHT)
        full_rect = (0, 0, map_w - 1, map_h - 1)

        # --- Read camera state up front; bail to full_rect if anything missing.
        try:
            cam_pos = camera.world_position
            cam_fwd = camera.forward
            if cam_pos is None or cam_fwd is None:
                return full_rect
            cam_x = float(cam_pos.x)
            cam_y = float(cam_pos.y)
            cam_z = float(cam_pos.z)
            fwd_x = float(cam_fwd.x)
            fwd_y = float(cam_fwd.y)
            fwd_z = float(cam_fwd.z)
        except Exception:
            return full_rect

        if cam_y <= 0:
            return full_rect

        # --- Strategy 1: Panda3D lens extrusion of the four NDC corners.
        # Only runs in real Ursina runtime; headless tests fall through to
        # strategy 2 because ``application.base`` is None there.
        lens_rect: tuple[int, int, int, int] | None = None
        try:
            from panda3d.core import Point2, Point3
            from ursina import application as _ursina_app

            _base = getattr(_ursina_app, "base", None)
            lens = getattr(_base, "camLens", None) if _base is not None else None
            cam_node = getattr(_base, "cam", None) if _base is not None else None
            if lens is not None and cam_node is not None and _base is not None:
                cam_to_world = cam_node.get_mat(_base.render)
                xs: list[float] = []
                zs: list[float] = []
                lens_ok = True
                for sx, sy in ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)):
                    np_near = Point3()
                    np_far = Point3()
                    if not lens.extrude(Point2(sx, sy), np_near, np_far):
                        lens_ok = False
                        break
                    wn = cam_to_world.xform_point(np_near)
                    wf = cam_to_world.xform_point(np_far)
                    ry = float(wf.y) - float(wn.y)
                    if abs(ry) < 1e-6:
                        lens_ok = False
                        break
                    t = -float(wn.y) / ry
                    if not _math.isfinite(t) or t <= 0:
                        # Ray points away from ground (e.g. corner aimed above
                        # horizon).  Fall back rather than guess.
                        lens_ok = False
                        break
                    hx = float(wn.x) + t * (float(wf.x) - float(wn.x))
                    hz = float(wn.z) + t * (float(wf.z) - float(wn.z))
                    xs.append(hx)
                    zs.append(hz)
                if lens_ok and xs and zs:
                    margin = 6  # tiles
                    min_tx = max(0, int(min(xs)) - margin)
                    max_tx = min(map_w - 1, int(max(xs)) + margin)
                    # world_z = -sim_y / SCALE = -tile_y (TILE_SIZE == SCALE).
                    min_ty = max(0, int(-max(zs)) - margin)
                    max_ty = min(map_h - 1, int(-min(zs)) + margin)
                    if max_tx >= min_tx and max_ty >= min_ty:
                        lens_rect = (min_tx, min_ty, max_tx, max_ty)
        except Exception as _exc:
            lens_rect = None
            if not getattr(self, "_visible_rect_lens_warned", False):
                try:
                    print(
                        "[ursina-cull] camera-lens extrusion unavailable; "
                        f"falling back to FOV heuristic ({_exc!r})",
                        flush=True,
                    )
                except Exception:
                    pass
                try:
                    setattr(self, "_visible_rect_lens_warned", True)
                except Exception:
                    pass

        if lens_rect is not None:
            return lens_rect

        # --- Strategy 2: FOV/pitch heuristic.  Self-contained (no self access).
        try:
            flen_sq = fwd_x * fwd_x + fwd_y * fwd_y + fwd_z * fwd_z
            if flen_sq < 1e-9 or fwd_y >= -0.01:
                return full_rect
            flen = _math.sqrt(flen_sq)
            nfx = fwd_x / flen
            nfy = fwd_y / flen
            nfz = fwd_z / flen

            t_ground = -cam_y / nfy
            if not _math.isfinite(t_ground) or t_ground <= 0:
                return full_rect
            ground_x = cam_x + t_ground * nfx
            ground_z = cam_z + t_ground * nfz
            center_tile_x = int(ground_x)
            center_tile_y = int(-ground_z)

            try:
                fov_deg = float(getattr(camera, "fov", 42.0))
            except Exception:
                fov_deg = 42.0
            if not (1.0 <= fov_deg <= 170.0):
                fov_deg = 42.0
            half_fov_v = _math.radians(fov_deg) * 0.5

            try:
                aspect = float(getattr(camera, "aspect_ratio", None) or (16.0 / 9.0))
            except Exception:
                aspect = 16.0 / 9.0
            if not (0.5 <= aspect <= 4.0):
                aspect = 16.0 / 9.0
            half_fov_h = _math.atan(_math.tan(half_fov_v) * aspect)

            horizontal_len = _math.sqrt(nfx * nfx + nfz * nfz)
            pitch = _math.atan2(abs(nfy), max(1e-3, horizontal_len))

            sin_pitch = _math.sin(pitch)
            look_dist = cam_y / max(0.05, sin_pitch)

            half_w = look_dist * _math.tan(half_fov_h)

            near_pitch = pitch + half_fov_v
            far_pitch = pitch - half_fov_v
            if near_pitch >= _math.pi * 0.5 - 0.01:
                near_dist = cam_y
            else:
                near_dist = cam_y / max(0.05, _math.sin(near_pitch))
            if far_pitch <= 0.05:
                far_dist = look_dist * 3.0
            else:
                far_dist = cam_y / max(0.05, _math.sin(far_pitch))
            half_along = max(8.0, (far_dist - near_dist) * 0.5)

            half_extent = max(half_w, half_along)

            margin = 8  # tiles of safety
            half = int(half_extent + margin)

            min_tx = max(0, center_tile_x - half)
            min_ty = max(0, center_tile_y - half)
            max_tx = min(map_w - 1, center_tile_x + half)
            max_ty = min(map_h - 1, center_tile_y + half)
            if max_tx < min_tx or max_ty < min_ty:
                return full_rect
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

        # R4: cache sim interpolation state for this frame
        self._frame_blend = float(getattr(snapshot, 'sim_blend_fraction', 0.0))
        self._frame_tick_id = int(getattr(snapshot, 'sim_tick_id', 0))

        # WK59 perf: cache visible tile rect for frustum culling this frame
        self._frame_visible_rect = self._get_visible_tile_rect()
        if _stage_profile: _rec("02_get_visible_tile_rect", _t0); _t0 = time.perf_counter()

        world = getattr(snapshot, "world", None) or self._world
        fog_revision = int(getattr(snapshot, "fog_revision", 0))
        self._terrain_fog.build_3d_terrain(world, getattr(snapshot, "buildings", ()))
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
        self._terrain_fog.ensure_grid_debug_overlay(world, getattr(snapshot, "buildings", ()))
        if _stage_profile: _rec("09_ensure_grid_debug_overlay", _t0); _t0 = time.perf_counter()

        # WK47 Wave 2b: hardware-instanced units (snapshot → buffer texture).
        # Opt-in: set KINGDOM_URSINA_INSTANCING=1 (known visual issues — see project memory).
        if os.environ.get("KINGDOM_URSINA_INSTANCING", "0") == "1":
            if not hasattr(self, "_instanced_unit_renderer"):
                from game.graphics.instanced_unit_renderer import InstancedUnitRenderer

                self._instanced_unit_renderer = InstancedUnitRenderer()
            active_ids: set[int] = set()
            self._sync_snapshot_buildings(snapshot, world, active_ids)
            self._sync_underground_meshes(snapshot, world)
            unit_ids = self._instanced_unit_renderer.update(snapshot)
            active_ids.update(unit_ids)
            # Projectiles draw inside ``InstancedUnitRenderer`` (wk48); skip legacy Entities.
            self._update_debug_status_text(snapshot)
            self._destroy_removed_entities(active_ids)
            return

        active_ids = set()
        self._sync_snapshot_buildings(snapshot, world, active_ids)
        if _stage_profile: _rec("10_sync_snapshot_buildings", _t0); _t0 = time.perf_counter()
        # WK57 Wave 2: Create underground meshes for discovered dungeon POIs
        self._sync_underground_meshes(snapshot, world)
        if _stage_profile: _rec("11_sync_underground_meshes", _t0); _t0 = time.perf_counter()
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
        # Buildings — billboard quads, except castle / house / lair (v1.5 Sprint 2.1: lit 3D meshes).
        _active_layer = self._camera_active_layer
        for b in getattr(snapshot, "buildings", ()):
            # WK61-BUG-003: Skip destroyed buildings that haven't been cleaned
            # from the snapshot yet. The engine's _cleanup_destroyed_buildings
            # removes them, but if a building reaches hp<=0 mid-tick it may
            # still appear in this frame's snapshot. Destroy its entity so the
            # model disappears immediately (rubble replaces it next frame).
            if getattr(b, 'hp', 1) <= 0 and getattr(b, 'building_type', '') != 'castle':
                _dead_obj_id = id(b)
                _dead_ent = self._entities.get(_dead_obj_id)
                if _dead_ent is not None:
                    import ursina as _u
                    self._unit_anim_state.pop(_dead_obj_id, None)
                    _u.destroy(self._entities.pop(_dead_obj_id))
                continue
            # WK57 Wave 3: Buildings are always surface (layer 0) — hide when camera underground
            if _active_layer != 0:
                _bld_obj_id = id(b)
                _bld_existing = self._entities.get(_bld_obj_id)
                if _bld_existing is not None:
                    _bld_existing.enabled = False
                    active_ids.add(_bld_obj_id)
                continue
            # WK54+fix: Debug mode — force POIs to render consistently.
            # WK66 L2: record the force-reveal in a renderer-owned dict keyed by the
            # stable entity_id instead of writing b.is_discovered / world.visibility
            # (the renderer must never mutate sim fog/discovery state).
            if _debug_show_pois and getattr(b, 'is_poi', False):
                self._debug_revealed_pois[str(getattr(b, 'entity_id', None) or id(b))] = True
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
            # Fog-of-war: lairs appear once a hero explores near them (SEEN) and stay
            # visible permanently.  Previous check required real-time LoS (VISIBLE)
            # which never triggered because lairs spawn 18+ tiles from the castle
            # while hero vision radius is only 10 tiles at game start.
            if is_lair:
                ts = float(config.TILE_SIZE)
                tx, ty = int(getattr(b, "x", 0.0) / ts), int(getattr(b, "y", 0.0) / ts)
                lair_visible = True
                if 0 <= ty < world.height and 0 <= tx < world.width:
                    # Read the sim fog grid READ-ONLY (>= SEEN). In debug mode a
                    # POI force-revealed above is always shown (replaces the old
                    # renderer write of world.visibility = SEEN).
                    lair_visible = (world.visibility[ty][tx] >= Visibility.SEEN) or (
                        _debug_show_pois
                        and self._debug_revealed_pois.get(
                            str(getattr(b, "entity_id", None) or id(b)), False
                        )
                    )
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
                # R5 Phase 2 (Agent 03): native building label / HP bar / gold
                _sync_building_worldspace_ui(
                    b, bts, ent, is_lair, wx=wx, wz=wz, terrain_y=bld_terrain_y, hy=hy
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
                # R5 Phase 2 (Agent 03): native building label / HP bar / gold
                _sync_building_worldspace_ui(
                    b, bts, ent, is_lair, wx=wx, wz=wz, terrain_y=bld_terrain_y, hy=hy
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
            # R5 Phase 2 (Agent 03): native building label / HP bar / gold
            _sync_building_worldspace_ui(
                b, bts, ent, is_lair, wx=wx, wz=wz, terrain_y=bld_terrain_y, hy=hy
            )
            active_ids.add(obj_id)

        _maybe_log_tax_overlay_debug(getattr(snapshot, "buildings", ()))

    def _sync_underground_meshes(self, snapshot: "SimStateSnapshot", world) -> None:
        """WK57 Wave 2: Create underground cave meshes for discovered dungeon POIs.

        WK65 Round 0: FEATURE GATE — underground visuals are disabled and the method
        returns immediately. The dead render block that previously followed this return
        (cave-mesh/stalactite creation + torch PointLight helpers
        ``_create_underground_lighting`` / ``_remove_underground_lighting``) was
        unreachable and has been deleted. The sim-side dungeon entry
        (``poi_interaction._handle_dungeon``) is unaffected. If underground visuals are
        revived, restore from git history (WK57 Wave 2/3).
        """
        return

    def _sync_snapshot_heroes(self, snapshot: "SimStateSnapshot", active_ids: set, HeroClass) -> None:
        # Heroes — atlas UV billboards (WK59 perf: single shared texture, UV offset per frame)
        _active_layer = self._camera_active_layer
        for h in getattr(snapshot, "heroes", ()):
            if not getattr(h, "is_alive", True):
                continue
            # WK57 Wave 3: Layer-aware visibility — hide heroes on a different layer
            _hero_layer = getattr(h, 'layer', 0)
            if _hero_layer != _active_layer:
                _h_obj_id = id(h)
                _h_existing = self._entities.get(_h_obj_id)
                if _h_existing is not None:
                    _h_existing.enabled = False
                    active_ids.add(_h_obj_id)
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
            is_resting = (getattr(h, 'state', '') == 'RESTING')
            sync_hero_rest_label(ent, is_resting)

            # WK61-R4-BUG-001: un-mirror overlay children when parent faces left.
            # WK62: delegates to ursina_unit_overlays.sync_hero_overlays_facing
            sync_hero_overlays_facing(ent, facing)

            active_ids.add(obj_id)


    def _sync_snapshot_enemies(self, snapshot: "SimStateSnapshot", world, active_ids: set) -> None:
        # Enemies — atlas UV billboards (WK59 perf: single shared texture)
        _active_layer = self._camera_active_layer
        ts = float(config.TILE_SIZE)
        for e in getattr(snapshot, "enemies", ()):
            # WK57 Wave 3: Layer-aware visibility — hide enemies on a different layer
            _enemy_layer = getattr(e, 'layer', 0)
            if _enemy_layer != _active_layer:
                _e_obj_id = id(e)
                _e_existing = self._entities.get(_e_obj_id)
                if _e_existing is not None:
                    _e_existing.enabled = False
                    active_ids.add(_e_obj_id)
                continue

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
        _active_layer = self._camera_active_layer
        for p in getattr(snapshot, "peasants", ()):
            if not getattr(p, "is_alive", True):
                continue
            if bool(getattr(p, "is_inside_castle", False)):
                continue
            # WK57 Wave 3: Peasants are always surface (layer 0) — hide when camera underground
            if _active_layer != 0:
                _p_obj_id = id(p)
                _p_existing = self._entities.get(_p_obj_id)
                if _p_existing is not None:
                    _p_existing.enabled = False
                    active_ids.add(_p_obj_id)
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
            # WK62: delegates to ursina_unit_overlays.sync_hp_bar
            _p_hp = int(getattr(p, 'hp', 0) or 0)
            _p_max_hp = int(getattr(p, 'max_hp', 1) or 1)
            sync_hp_bar(ent, _p_hp, _p_max_hp, PEASANT_SPEC)

            worker_label = str(getattr(p, "render_worker_type", "peasant") or "peasant").replace("_", " ").title()
            _ensure_ks_name_label(ent, "_ks_name_label", worker_label, y=PEASANT_SPEC.label_y, scale=PEASANT_SPEC.label_scale)

            active_ids.add(obj_id)


    def _sync_snapshot_guards(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # Guards — atlas UV billboards (WK59 perf: single shared texture)
        _active_layer = self._camera_active_layer
        for g in getattr(snapshot, "guards", ()):
            if not getattr(g, "is_alive", True):
                continue
            # WK57 Wave 3: Guards are always surface (layer 0) — hide when camera underground
            if _active_layer != 0:
                _g_obj_id = id(g)
                _g_existing = self._entities.get(_g_obj_id)
                if _g_existing is not None:
                    _g_existing.enabled = False
                    active_ids.add(_g_obj_id)
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
            # WK62: delegates to ursina_unit_overlays.sync_hp_bar
            _g_hp = int(getattr(g, 'hp', 0) or 0)
            _g_max_hp = int(getattr(g, 'max_hp', 1) or 1)
            sync_hp_bar(ent, _g_hp, _g_max_hp, GUARD_SPEC)

            _ensure_ks_name_label(ent, "_ks_name_label", "Guard", y=GUARD_SPEC.label_y, scale=GUARD_SPEC.label_scale)

            active_ids.add(obj_id)


    def _sync_snapshot_tax_collector(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        # Tax Collector — atlas UV billboards (WK59 perf: single shared texture)
        tc = getattr(snapshot, "tax_collector", None)
        if tc is not None:
            if not getattr(tc, "is_alive", True):
                pass
            # WK57 Wave 3: Tax collector is always surface — hide when camera underground
            elif self._camera_active_layer != 0:
                _tc_existing = self._entities.get(id(tc))
                if _tc_existing is not None:
                    _tc_existing.enabled = False
                    active_ids.add(id(tc))
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

    # ------------------------------------------------------------------
    # WK60 Feature 7: Bounty flag 3D rendering
    # ------------------------------------------------------------------
    # Constants for bounty flag visual elements
    _BOUNTY_POLE_HEIGHT = 0.6
    _BOUNTY_POLE_RADIUS = 0.02
    _BOUNTY_FLAG_SCALE = (0.18, 0.12, 0.01)
    _BOUNTY_FLAG_OFFSET_Y = 0.05  # flag sits slightly below pole top
    _BOUNTY_TEXT_OFFSET_Y = 0.12  # text sits above pole top

    def _sync_snapshot_bounties(self, snapshot: "SimStateSnapshot", active_ids: set) -> None:
        """Create/update/remove 3D bounty flag entities for each unclaimed bounty."""
        import ursina

        # WK66 Move 3: consume frozen BountyDTOs (bounty_id/claimed/x/y/reward) — the
        # Ursina flag shows only $reward (not responders/tier), and none of those
        # fields are mutated during the render pass, so this is behavior-identical.
        bounties = getattr(snapshot, "bounty_dtos", None)
        if bounties is None:
            bounties = getattr(snapshot, "bounties", ()) or ()

        # Build set of currently active bounty IDs
        active_bounty_ids: set[int] = set()
        for b in bounties:
            bid = getattr(b, "bounty_id", None)
            if bid is None:
                continue
            if getattr(b, "claimed", False):
                continue
            active_bounty_ids.add(bid)

            bx = float(getattr(b, "x", 0))
            by = float(getattr(b, "y", 0))
            reward = int(getattr(b, "reward", 0))

            wx, wz = sim_px_to_world_xz(bx, by)
            terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

            if bid in self._bounty_entities:
                # Update existing entities positions (in case bounty moved, unlikely but safe)
                parts = self._bounty_entities[bid]
                pole_y = terrain_y + self._BOUNTY_POLE_HEIGHT * 0.5
                parts[0].position = Vec3(wx, pole_y, wz)  # pole
                parts[1].position = Vec3(wx + 0.08, terrain_y + self._BOUNTY_POLE_HEIGHT - self._BOUNTY_FLAG_OFFSET_Y, wz)  # flag
                parts[2].position = Vec3(wx, terrain_y + self._BOUNTY_POLE_HEIGHT + self._BOUNTY_TEXT_OFFSET_Y, wz)  # text
            else:
                # Create new flag assembly: pole + pennant + reward text
                pole = Entity(
                    model="cube",
                    color=color.rgb(0.4, 0.25, 0.1),  # brown
                    scale=Vec3(self._BOUNTY_POLE_RADIUS * 2, self._BOUNTY_POLE_HEIGHT, self._BOUNTY_POLE_RADIUS * 2),
                    position=Vec3(wx, terrain_y + self._BOUNTY_POLE_HEIGHT * 0.5, wz),
                    shader=unlit_shader,
                )
                # Gold pennant flag — offset slightly to the side of the pole
                flag = Entity(
                    model="quad",
                    color=color.rgb(1.0, 0.84, 0.0),  # gold
                    scale=Vec3(*self._BOUNTY_FLAG_SCALE),
                    position=Vec3(wx + 0.08, terrain_y + self._BOUNTY_POLE_HEIGHT - self._BOUNTY_FLAG_OFFSET_Y, wz),
                    billboard=True,
                    shader=unlit_shader,
                )
                # Reward text label above the flag
                reward_text = Text(
                    text=f"${reward}",
                    position=(0, 0),
                    scale=1.0,
                    color=color.rgb(1.0, 0.84, 0.0),
                    billboard=True,
                    parent=scene,
                )
                reward_text.world_position = Vec3(wx, terrain_y + self._BOUNTY_POLE_HEIGHT + self._BOUNTY_TEXT_OFFSET_Y, wz)
                reward_text.world_scale = Vec3(0.15, 0.15, 0.15)

                self._bounty_entities[bid] = [pole, flag, reward_text]

        # Remove entities for claimed/expired bounties
        removed_ids = set(self._bounty_entities.keys()) - active_bounty_ids
        for bid in removed_ids:
            parts = self._bounty_entities.pop(bid)
            for part in parts:
                ursina.destroy(part)

    # ------------------------------------------------------------------
    # WK61-FEAT-004: Rubble rendering (destroyed building debris)
    # ------------------------------------------------------------------

    def _sync_snapshot_rubble(self, snapshot: "SimStateSnapshot") -> None:
        """Create/destroy rubble entity groups from snapshot.rubble_records."""
        import ursina as _ursina
        import random as _random

        rubble_records = getattr(snapshot, 'rubble_records', ())
        active_ids = {r.record_id for r in rubble_records}

        # Remove expired rubble
        for rid in list(self._rubble_entities.keys()):
            if rid not in active_ids:
                for ent in self._rubble_entities[rid]:
                    _ursina.destroy(ent)
                del self._rubble_entities[rid]

        # Create new rubble
        for r in rubble_records:
            if r.record_id in self._rubble_entities:
                continue  # already rendered

            entities = []
            # Convert grid position to world position using the same
            # coordinate system as buildings (sim pixels -> Ursina X/Z).
            ts = float(config.TILE_SIZE)
            center_px_x = r.grid_x * ts + (r.width_tiles * ts) * 0.5
            center_px_y = r.grid_y * ts + (r.height_tiles * ts) * 0.5
            wx, wz = sim_px_to_world_xz(center_px_x, center_px_y)
            terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

            # Place 3 small rock models scattered within footprint
            rng = _random.Random(r.record_id)  # deterministic per rubble
            footprint_world = r.width_tiles * 0.5  # half-extent in world units

            _rock_stems = [
                'rock_smallA', 'rock_smallB', 'rock_smallC',
                'rock_smallD', 'rock_smallE', 'rock_smallF',
            ]

            for _i in range(3):
                offset_x = rng.uniform(-footprint_world * 0.3, footprint_world * 0.3)
                offset_z = rng.uniform(-footprint_world * 0.3, footprint_world * 0.3)
                rock_stem = rng.choice(_rock_stems)
                rock_model = _environment_model_path(rock_stem)
                rock_scale = rng.uniform(0.8, 1.5)
                rock_rot = rng.uniform(0, 360)

                rock = Entity(
                    model=rock_model,
                    position=(wx + offset_x, terrain_y + 0.1, wz + offset_z),
                    scale=rock_scale,
                    rotation_y=rock_rot,
                    color=color.rgb(0.6, 0.55, 0.5),  # dusty gray-brown
                )
                entities.append(rock)

            self._rubble_entities[r.record_id] = entities

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
            gold = getattr(ent, "_ks_gold_label", None)
            if gold is not None:
                try:
                    import ursina as _u

                    _u.destroy(gold)
                except Exception:
                    pass
            import ursina

            ursina.destroy(ent)

