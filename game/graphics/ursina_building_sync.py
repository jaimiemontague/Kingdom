"""Per-frame building render-sync for the Ursina renderer.

WK91, Round B-8. Pure-move of the per-frame building render-sync method out of
``game/graphics/ursina_renderer.py``:

* ``sync_snapshot_buildings`` — billboard quads vs lit 3D meshes (castle / house /
  lair), cave/lair tint, POI discovery gating, frustum cull, and the native
  world-space building UI (label / HP bar / gold). Was ``_sync_snapshot_buildings``.

The function takes the ``UrsinaRenderer`` instance as ``r`` and reads/writes its
state (``r._camera_active_layer``, ``r._entities``, ``r._unit_anim_state``,
``r._debug_revealed_pois``, ``r._poi_mystery_markers``, ``r._entity_render``) and
calls its methods (``r._entity_in_view`` — the WK88 frustum wrapper) exactly as
the original method read ``self.*``. The building color constants
(``COLOR_CASTLE`` / ``COLOR_LAIR`` / ``COLOR_BUILDING``) are recomputed here
identically to the ursina_renderer module-level values (``color``-derived, no
renderer import needed). The bare-name helper calls (``_building_type_str`` /
``_footprint_tiles`` / ``_is_3d_mesh_building`` / ``_mesh_kind_for_building`` /
``_building_height_y`` / ``_resolve_prefab_path`` /
``_resolve_construction_staged_prefab`` / ``_environment_model_path`` /
``_sync_building_worldspace_ui`` / ``_maybe_log_tax_overlay_debug``) resolve via
the same leaf sub-module imports the renderer uses.

``UrsinaRenderer`` keeps a 1-line delegating wrapper (``_sync_snapshot_buildings``)
that imports this module lazily, so the ``update()`` pipeline call site is
unchanged and there is no import cycle (this module never imports
``ursina_renderer`` at module top). Leaf deps only.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

import config
from ursina import color

from game.graphics.building_sprites import BuildingSpriteLibrary
from game.graphics.terrain_texture_bridge import TerrainTextureBridge
from game.graphics.ursina_sprite_unlit_shader import sprite_unlit_shader
from game.graphics.ursina_coords import SCALE, sim_px_to_world_xz
from game.graphics.terrain_height import get_terrain_height, is_initialized as _terrain_height_ok
from game.graphics.ursina_environment import _environment_model_path
from game.graphics.ursina_prefabs import (
    _building_type_str,
    _footprint_tiles,
    _is_3d_mesh_building,
    _mesh_kind_for_building,
    _building_height_y,
    _resolve_construction_staged_prefab,
    _resolve_prefab_path,
)
from game.graphics.ursina_building_ui import (
    _sync_building_worldspace_ui,
    _maybe_log_tax_overlay_debug,
)
from game.world import Visibility

if TYPE_CHECKING:
    from game.graphics.ursina_renderer import UrsinaRenderer
    from game.sim.snapshot import SimStateSnapshot

# Building tint constants — recomputed here identically to the ursina_renderer
# module-level values (``color``-derived, no renderer import needed).
COLOR_BUILDING = color.light_gray
COLOR_CASTLE = color.gold
COLOR_LAIR = color.brown

# Debug POI force-reveal flag — recomputed here identically to the ursina_renderer
# module-level value (env-derived, read-only).
_debug_show_pois = os.environ.get("KINGDOM_DEBUG_SHOW_ALL_POIS", "").strip().lower() in ("1", "true", "yes")


def sync_snapshot_buildings(r: "UrsinaRenderer", snapshot: "SimStateSnapshot", world, active_ids: set) -> None:
    # Buildings — billboard quads, except castle / house / lair (v1.5 Sprint 2.1: lit 3D meshes).
    # WK68 R2 (Agent 09): consume frozen BuildingDTOs and key r._entities on the
    # stable dto.entity_id (string) — NOT id(b). The DTO carries center_x/center_y
    # (== live b.x/b.y), is_lair/has_stash_gold (lair detection), is_poi/poi_type
    # (cave/mine tint), is_discovered/tile_visible (visibility). All prefab/mesh
    # helpers (_resolve_prefab_path / _is_3d_mesh_building / _mesh_kind_for_building /
    # _resolve_construction_staged_prefab / _footprint_tiles) read only fields the DTO
    # exposes, so they accept the DTO unchanged (lair detection via is_lair, equivalent
    # to the old hasattr(b,"stash_gold") since every lair sets is_lair=True).
    _active_layer = r._camera_active_layer
    for b in getattr(snapshot, "building_dtos", ()):
        obj_id = b.entity_id
        # building CENTER coords (== live b.x/b.y) for placement / cull / fog sampling.
        b_cx = float(getattr(b, "center_x", 0.0))
        b_cy = float(getattr(b, "center_y", 0.0))
        bts = _building_type_str(getattr(b, "building_type", "") or "")
        # WK61-BUG-003: Skip destroyed buildings that haven't been cleaned
        # from the snapshot yet. The engine's _cleanup_destroyed_buildings
        # removes them, but if a building reaches hp<=0 mid-tick it may
        # still appear in this frame's snapshot. Destroy its entity so the
        # model disappears immediately (rubble replaces it next frame).
        if getattr(b, 'hp', 1) <= 0 and bts != 'castle':
            _dead_ent = r._entities.get(obj_id)
            if _dead_ent is not None:
                import ursina as _u
                r._unit_anim_state.pop(obj_id, None)
                _u.destroy(r._entities.pop(obj_id))
            continue
        # WK57 Wave 3: Buildings are always surface (layer 0) — hide when camera underground
        if _active_layer != 0:
            _bld_existing = r._entities.get(obj_id)
            if _bld_existing is not None:
                _bld_existing.enabled = False
                active_ids.add(obj_id)
            continue
        # WK54+fix: Debug mode — force POIs to render consistently.
        # WK66 L2: record the force-reveal in a renderer-owned dict keyed by the
        # stable entity_id instead of writing b.is_discovered / world.visibility
        # (the renderer must never mutate sim fog/discovery state).
        if _debug_show_pois and getattr(b, 'is_poi', False):
            r._debug_revealed_pois[obj_id] = True
        # WK55-fix: Binary POI visibility — hidden until discovered by hero.
        # Undiscovered POIs are completely hidden (minimap gray dots are the only hint).
        # Once a hero walks within discovery range, the POI becomes fully visible.
        if getattr(b, "is_poi", False) and not _debug_show_pois:
            if not getattr(b, 'is_discovered', False):
                # UNDISCOVERED — hide entity completely; minimap shows gray dot instead
                existing = r._entities.get(obj_id)
                if existing is not None:
                    existing.enabled = False
                    active_ids.add(obj_id)
                # Also hide any leftover mystery marker from old code
                marker = r._poi_mystery_markers.get(obj_id)
                if marker is not None:
                    marker.enabled = False
                continue
            # DISCOVERED — fall through to normal rendering below
        # WK59 perf: frustum culling — skip buildings outside visible tile rect
        if not r._entity_in_view(b_cx, b_cy):
            _bld_existing = r._entities.get(obj_id)
            if _bld_existing is not None:
                _bld_existing.enabled = False
                active_ids.add(obj_id)
            continue
        # Re-enable building if it was previously culled and is now in view
        _bld_reenable = r._entities.get(obj_id)
        if _bld_reenable is not None and getattr(_bld_reenable, "enabled", True) is False:
            _bld_reenable.enabled = True
        bt_raw = getattr(b, "building_type", "") or ""
        is_castle = bts == "castle"
        # Lair detection: is_lair (or has_stash_gold) — equivalent to the old
        # hasattr(b,"stash_gold") since the Lair class sets both.
        is_lair = bool(getattr(b, "is_lair", False) or getattr(b, "has_stash_gold", False))
        # Fog-of-war: lairs appear once a hero explores near them (SEEN) and stay
        # visible permanently.  Previous check required real-time LoS (VISIBLE)
        # which never triggered because lairs spawn 18+ tiles from the castle
        # while hero vision radius is only 10 tiles at game start.
        if is_lair:
            ts = float(config.TILE_SIZE)
            tx, ty = int(b_cx / ts), int(b_cy / ts)
            lair_visible = True
            if 0 <= ty < world.height and 0 <= tx < world.width:
                # Read the sim fog grid READ-ONLY (>= SEEN). In debug mode a
                # POI force-revealed above is always shown (replaces the old
                # renderer write of world.visibility = SEEN).
                lair_visible = (world.visibility[ty][tx] >= Visibility.SEEN) or (
                    _debug_show_pois
                    and r._debug_revealed_pois.get(obj_id, False)
                )
            existing = r._entities.get(obj_id)
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

        wx, wz = sim_px_to_world_xz(b_cx, b_cy)
        # WK53 Wave 2: sample terrain height at building footprint center
        bld_terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

        # WK30: prefab path wins over static mesh / billboard for any building_type with
        # a resolvable prefab JSON. Lairs and env opt-out are handled inside the resolver.
        # WK32: swap JSON by construction_progress (plots + intermediates + fallback).
        prefab_path = _resolve_prefab_path(bts, b)
        if prefab_path is not None:
            staged = _resolve_construction_staged_prefab(b, prefab_path, tw, th)
            ent, obj_id = r._entity_render.get_or_create_prefab_building_entity(
                b, staged, col, key=obj_id
            )
            r._entity_render.sync_prefab_building_entity(
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
            # WK68 R2 (Agent 09): poi_type from the DTO (== live poi_def.poi_type).
            if not getattr(ent, "_ks_cave_tint_applied", False):
                if getattr(b, 'poi_type', None) in ('poi_cave_entrance', 'poi_mine_entrance'):
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
            ent, obj_id = r._entity_render.get_or_create_3d_building_entity(
                b, model_path, col, key=obj_id
            )
            r._entity_render.sync_3d_building_entity(
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
            # WK68 R2 (Agent 09): poi_type from the DTO (== live poi_def.poi_type).
            if not getattr(ent, '_ks_cave_tint_applied', False):
                if getattr(b, 'poi_type', None) in ('poi_cave_entrance', 'poi_mine_entrance'):
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
        ent, obj_id = r._entity_render.get_or_create_entity(
            b,
            model="quad",
            col=col,
            scale=(face_w, hy, 1),
            billboard=True,
            key=obj_id,
        )
        if not getattr(ent, "_ks_billboard_configured", False):
            ent.model = "quad"
            ent.billboard = True
            r._entity_render.apply_pixel_billboard_settings(ent)
            ent._ks_billboard_configured = True
        # Do not assign ent.model every frame — model_setter reloads the mesh (WK22 R2).
        ent.rotation = (0, 0, 0)
        r._entity_render.sync_billboard_entity(
            ent,
            tex=b_tex if b_tex is not None else None,
            tint_col=col,
            scale_xyz=(face_w, hy, 1),
            pos_xyz=(wx, bld_terrain_y + hy * 0.5, wz),
            shader=sprite_unlit_shader,
        )
        # WK57: Visual hint for cave/mine entrances — cool dark tint
        # WK68 R2 (Agent 09): poi_type from the DTO (== live poi_def.poi_type).
        if not getattr(ent, '_ks_cave_tint_applied', False):
            if getattr(b, 'poi_type', None) in ('poi_cave_entrance', 'poi_mine_entrance'):
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

    _maybe_log_tax_overlay_debug(getattr(snapshot, "building_dtos", ()))
