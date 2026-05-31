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
    _stem_is_flower_ground_scatter,
    _stem_is_log_or_mushroom_ground_scatter,
)
from game.world import TileType, Visibility
from ursina.shaders import unlit_shader

# WK104 back-import (one-way edge fog_collab -> growth_sync): _InstancedTreeStub
# moved to ursina_terrain_growth_sync.py, but STAYING code here constructs it
# (build_3d_terrain) and isinstance-checks it (cull_terrain_chunks). growth_sync
# never imports this module at runtime (TYPE_CHECKING only), so this stays acyclic.
from game.graphics.ursina_terrain_growth_sync import _InstancedTreeStub

FOG_TEX_BRIDGE_KEY = "kingdom_ursina_fog_overlay"

TERRAIN_CHUNK_SIZE = 16  # tiles per chunk edge for frustum culling


class UrsinaTerrainFogCollab:
    """Terrain root + fog quad + visibility-gated props + optional grid overlay."""

    __slots__ = ("_r", "_tree_sync_tick_counter", "_last_growth_by_tile",
                 "_terrain_chunks", "_visible_chunks", "_chunks_built",
                 "_last_cull_fog_revision", "_static_terrain_batches",
                 "_static_batch_fog_size", "_static_batch_flatten_level",
                 # WK58 Phase 4: hardware-instanced tree path. ``_instanced_trees_on``
                 # mirrors ``KINGDOM_URSINA_INSTANCED_TREES`` at construction; the
                 # individual-Entity tree branch in ``build_3d_terrain`` /
                 # ``sync_dynamic_trees`` is skipped when this is True.
                 # ``_instanced_nature_renderer`` is the renderer (lazy-init on first
                 # tree). ``_tree_instance_ids`` maps (tx, ty) -> instance_id so
                 # ``sync_dynamic_trees`` can grow/remove without re-walking models.
                 "_instanced_trees_on", "_instanced_nature_renderer",
                 "_tree_instance_ids", "_instanced_trees_last_fog_rev")

    def __init__(self, renderer) -> None:
        self._r = renderer
        self._tree_sync_tick_counter = 0
        self._last_growth_by_tile = None
        self._terrain_chunks: dict[tuple[int, int], list] = {}
        self._visible_chunks: set[tuple[int, int]] = set()
        self._chunks_built = False
        # WK58 Phase 1 Fix 1A: track fog revision against which chunk_visible
        # bits were last applied. When sync advances the fog revision, the next
        # cull pass re-iterates all chunks once to refresh chunk_visible so the
        # composition invariant ``ent.enabled = fog_visible AND chunk_visible``
        # is maintained after /revealmap even when the camera is stationary.
        self._last_cull_fog_revision: int = -1
        # WK58 Phase 3: number of static batch parent Entities created by
        # ``_batch_static_terrain_for_chunks``. Surfaced via
        # ``tools/perf_render_benchmark.py``.
        self._static_terrain_batches: int = 0
        # WK58 Phase 3 telemetry: which fog-batch granularity and flatten
        # strategy was used for the most recent build. Set when batching runs.
        # Default 8x8 (per plan Section 7 — fog seams stay reasonable while
        # the static count drops from ~7,500 individual props to ~1,000
        # batch parents).  ``KINGDOM_URSINA_STATIC_BATCH_SIZE`` env var lets
        # Agent 10 sweep larger sizes (16, 32) for benchmarking without
        # touching code.  Measured perf for 250x250 + /revealmap:
        #   8x8  -> ~1017 batches, after_avg ~15 FPS
        #   16x16 -> ~256 batches,  after_avg ~16.6 FPS
        #   32x32 -> ~64 batches,   after_avg ~15.6 FPS
        # Static-prop count is no longer the bottleneck at any of these;
        # remaining gap to 45 FPS comes from the ~2,083 individual tree
        # entities and would need Phase 4 (tree instancing) to close.
        try:
            _bsz = int(os.environ.get("KINGDOM_URSINA_STATIC_BATCH_SIZE", "") or "8")
        except ValueError:
            _bsz = 8
        if _bsz <= 0:
            _bsz = 8
        self._static_batch_fog_size: int = _bsz
        self._static_batch_flatten_level: str = "none"

        # WK58 Phase 4: hardware-instanced tree renderer (per plan Section 8).
        # Read env var once at construction so the legacy and instanced code paths
        # stay deterministic across a single session (no flipping between the two
        # mid-game). Default in ``instanced_trees_env_enabled`` is "1" (ON) once
        # Wave 4 visual parity is confirmed; set ``KINGDOM_URSINA_INSTANCED_TREES=0``
        # for the legacy individual-Entity fallback.
        try:
            from game.graphics.instanced_nature_renderer import (
                instanced_trees_env_enabled,
            )
            self._instanced_trees_on: bool = bool(instanced_trees_env_enabled())
        except Exception:
            self._instanced_trees_on = False
        self._instanced_nature_renderer = None  # lazy-init on first tree
        # (tx, ty) -> instance_id, parallel to ``_r._tree_entities`` for the legacy
        # path so ``sync_dynamic_trees`` can address growth/remove by tile.
        self._tree_instance_ids: dict[tuple[int, int], int] = {}
        self._instanced_trees_last_fog_rev: int = -1

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
        # WK58 W6 Fix 1.A (Agent 03): the early-out previously required
        # ``_fog_entity is not None`` which is correct only for the legacy flat-
        # terrain fog quad. The WK53 heightmap shader-uniform path destroys
        # ``_fog_entity`` (see :345-351 below) and applies the fog texture as a
        # ``fog_texture`` shader input on ``_terrain_ground_entity`` instead.
        # Without recognising that path the early-out was always False on the
        # heightmap build, so the 62,500-tile Python loop + GPU upload ran
        # every frame even when ``fog_revision`` had not advanced. Accept the
        # heightmap path by also checking ``_terrain_ground_entity``; this
        # restores the intended "rebuild only when revealer crosses a tile"
        # behaviour. Wave-5 profile: lifts post-reveal FPS ~18 -> ~32-38.
        terrain_ground_ent = getattr(self._r, "_terrain_ground_entity", None)
        if int(fog_revision) == my_rev and (
            self._r._fog_entity is not None or terrain_ground_ent is not None
        ):
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

                # WK58 W8 (4.C): when the GeoMipTerrain display path is active
                # we ALSO need to push the fog_texture input directly onto the
                # GeoMipTerrain root NodePath. The wrap Entity owns the
                # ``_terrain_ground_entity`` reference and the shader, but
                # GeoMipTerrain installs its own per-block RenderState during
                # ``generate()`` and may not always inherit shader inputs set
                # on the parent transform. Mirroring the input on the root NP
                # is cheap and guarantees the fog texture is sampled in every
                # block's fragment shader.
                _gmt_handle = getattr(self._r, "_geomip_terrain_handle", None)
                if _gmt_handle is not None:
                    try:
                        _root_np = _gmt_handle.terrain.get_root()
                        if p3d_tex is not None:
                            _root_np.set_shader_input("fog_texture", p3d_tex)
                        elif ftex is not None:
                            _root_np.set_shader_input("fog_texture", ftex)
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

    def _apply_prop_visibility_state(self, ent, *, fog_visible=None, chunk_visible=None) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility._apply_prop_visibility_state(
            self, ent, fog_visible=fog_visible, chunk_visible=chunk_visible
        )

    def track_visibility_gated_terrain(self, ent, tx: int, ty: int) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility.track_visibility_gated_terrain(self, ent, tx, ty)

    def untrack_visibility_gated_terrain(self, ent) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility.untrack_visibility_gated_terrain(self, ent)

    def sync_terrain_prop_tile_visibility(self, ent, vis) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility.sync_terrain_prop_tile_visibility(self, ent, vis)

    def sync_visibility_gated_terrain(self, world, fog_revision: int) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility.sync_visibility_gated_terrain(self, world, fog_revision)

    def _build_terrain_chunks(self) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility._build_terrain_chunks(self)

    def cull_terrain_chunks(self, visible_rect, world) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility.cull_terrain_chunks(self, visible_rect, world)

    def _ensure_instanced_nature_renderer(self):
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility._ensure_instanced_nature_renderer(self)

    def _sync_instanced_trees_fog(self, world, fog_revision: int) -> None:
        from game.graphics import ursina_terrain_fog_visibility
        return ursina_terrain_fog_visibility._sync_instanced_trees_fog(self, world, fog_revision)

    def _batch_static_terrain_for_chunks(self, root, tw: int, th: int) -> None:
        """WK58 Phase 3: merge static terrain props into fog-batch parent Entities.

        Trees (entities tagged with ``_ks_tree_base_scale``) are excluded — they
        retain dynamic scale via ``sync_dynamic_trees`` and must stay individual.
        Static props (grass / doodads / path stones / water / rocks) are grouped
        by ``(fog_batch_x, fog_batch_y, model_key, shader_key, color_key)`` so
        a single ``flatten_strong()`` does not collapse heterogeneous materials.

        After flattening, the original ``_visibility_gated_terrain`` list is
        rebuilt: tree entries are kept 1:1, each batch parent is added as one
        entry anchored at the fog-batch center tile.  ``sync_visibility_*`` and
        ``cull_terrain_chunks`` therefore toggle batch parents as a single unit,
        which is exactly the perf win Phase 3 chases (plan Section 7).

        Granularity:
        - 8x8 fog batches by default (~32 batches per 16x16 cull chunk).
        - Fallback to ``flatten_medium`` then no-flatten if ``flatten_strong``
          throws (mixed shader/model combos can refuse merge).
        """
        fog_batch_size = int(self._static_batch_fog_size or 8)
        if fog_batch_size <= 0:
            fog_batch_size = 8

        existing = list(self._r._visibility_gated_terrain)
        if not existing:
            self._static_terrain_batches = 0
            self._static_batch_flatten_level = "none"
            return

        new_vgt: list = []
        new_vgt_by_tile: dict[tuple[int, int], list] = {}
        batch_statics: dict[tuple, list] = {}

        # WK58 Phase 3: signature key. The plan (Section 7) starts with
        # ``(bx, by, model, shader, color)`` to keep ``flatten_strong()``
        # from collapsing heterogeneous materials. In production that
        # produces ~1 batch per source prop because every grass model + pack
        # tint + (Panda3D NodePath scene path) is a distinct key. The
        # consolidation we actually need is far coarser: one batch per fog
        # cell regardless of material — ``flatten_strong()`` will keep
        # different Geoms intact inside the single parent NodePath, and the
        # per-frame visibility loop only needs to toggle the batch parent.
        # This matches the plan's Risk Register row 4 fallback path ("group
        # by model/material/tint first; if flatten fails fall back to
        # reparenting without flatten") but applied the other way: start
        # broad to actually shrink the count, then narrow only if visuals
        # break.
        for entry in existing:
            ent, tx, ty = entry
            # Trees keep their per-tile entry so dynamic scaling / log-stack
            # replacement continues to address them individually.
            if hasattr(ent, "_ks_tree_base_scale"):
                new_vgt.append(entry)
                new_vgt_by_tile.setdefault((int(tx), int(ty)), []).append(ent)
                continue

            bx = int(tx) // fog_batch_size
            by = int(ty) // fog_batch_size
            bkey = (bx, by)
            batch_statics.setdefault(bkey, []).append(entry)

        # Track which flatten strategy actually completed for evidence + log.
        any_strong = False
        any_medium = False
        any_noflatten = False
        batches_created = 0

        for bkey, entries in batch_statics.items():
            if not entries:
                continue

            bx, by = bkey

            batch_parent = Entity(
                parent=root,
                name=f"static_batch_{bx}_{by}",
                add_to_scene_entities=False,
            )

            for ent, _tx, _ty in entries:
                try:
                    ent.reparent_to(batch_parent)
                except Exception:
                    # If reparent fails the child stays parented to root; the
                    # batch will simply skip flattening that node.  Counted as
                    # ``no-flatten`` for diagnostic purposes only.
                    pass

            # ``clear_model_nodes()`` removes the Panda3D ModelNode flag that
            # prevents flatten from merging child meshes — without this,
            # ``flatten_strong()`` is a no-op for entities loaded via .glb/.obj
            # (which carry ModelNode by default).  Safe to call on the parent;
            # only affects nodes flagged ``T_dont_flatten``.
            try:
                batch_parent.clear_model_nodes()
            except Exception:
                pass

            # Prefer flatten_strong; fall back per Risk Register row 4.
            try:
                batch_parent.flatten_strong()
                any_strong = True
            except Exception:
                try:
                    batch_parent.flatten_medium()
                    any_medium = True
                except Exception:
                    any_noflatten = True

            # Anchor batch at fog-batch center tile, clamped to map bounds so
            # the fog-by-tile lookup (and chunk-by-tile bucket) stays valid.
            center_tx = bx * fog_batch_size + fog_batch_size // 2
            center_ty = by * fog_batch_size + fog_batch_size // 2
            center_tx = max(0, min(center_tx, int(tw) - 1))
            center_ty = max(0, min(center_ty, int(th) - 1))

            # Carry the composed-visibility state markers onto the parent so the
            # existing ``_apply_prop_visibility_state`` pipeline keeps working
            # for the post-batch world. We do NOT touch ``_ks_tree_base_scale``
            # on the parent — trees must never be batched.
            try:
                batch_parent.render_queue = 1
            except Exception:
                pass
            batch_parent._ks_fog_visible = False
            batch_parent._ks_chunk_visible = True

            new_vgt.append((batch_parent, center_tx, center_ty))
            new_vgt_by_tile.setdefault((center_tx, center_ty), []).append(batch_parent)
            batches_created += 1

        self._r._visibility_gated_terrain = new_vgt
        self._r._visibility_gated_terrain_by_tile = new_vgt_by_tile
        self._static_terrain_batches = batches_created
        if any_strong and not any_medium and not any_noflatten:
            self._static_batch_flatten_level = "strong"
        elif any_medium and not any_noflatten:
            self._static_batch_flatten_level = "medium" if not any_strong else "mixed_strong_medium"
        elif any_noflatten and not any_strong and not any_medium:
            self._static_batch_flatten_level = "none"
        else:
            # mixed outcome — some succeeded, some fell back.
            parts = []
            if any_strong:
                parts.append("strong")
            if any_medium:
                parts.append("medium")
            if any_noflatten:
                parts.append("none")
            self._static_batch_flatten_level = "+".join(parts) if parts else "none"

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
                    # WK58 Phase 1 Fix 1B (WK58-BUG-003): register path stones
                    # in the visibility/cull system.  Before this, path entities
                    # bypassed both fog gating and chunk culling entirely
                    # (~996 always-on props on a 250x250 map).
                    self.track_visibility_gated_terrain(path_ent, tx, ty)
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
                    # WK58 Phase 4: route into the instanced renderer when the env
                    # flag is on. We deliberately skip the individual Entity
                    # creation AND the visibility/chunk tracking — the instanced
                    # path has its own fog gating via ``set_fog_visibility``.
                    # Leaving the per-tree Entity disabled in scene would still
                    # cost a NodePath; not creating it at all is the actual win.
                    if self._instanced_trees_on:
                        inst_renderer = self._ensure_instanced_nature_renderer()
                        iid = None
                        if inst_renderer is not None:
                            iid = inst_renderer.register_tree(
                                tree_model,
                                (float(wx), float(prop_y), float(wz)),
                                float(tm),
                                (int(tx), int(ty)),
                            )
                        if iid is not None:
                            self._tree_instance_ids[(int(tx), int(ty))] = int(iid)
                            # Stamp the base scale on a sentinel so
                            # ``sync_dynamic_trees`` can compute growth-scaled
                            # values without re-deriving from config. We don't
                            # need a full Entity; a small dict-side record on
                            # ``_r._tree_entities`` keyed by tile works fine
                            # because callers only ever check ``key in ents`` or
                            # iterate ``ents.items()``. Use a lightweight stub
                            # with the same surface the legacy ent exposed:
                            # ``_ks_tree_base_scale``, ``_ks_tree_growth``,
                            # ``scale``. ``sync_dynamic_trees`` reads those
                            # attributes and writes ``ent.scale`` — for the
                            # instanced path we redirect both to the renderer.
                            stub = _InstancedTreeStub(
                                instance_id=int(iid),
                                renderer_ref=inst_renderer,
                                base_scale=float(tm),
                                tile_xy=(int(tx), int(ty)),
                            )
                            self._r._tree_entities[(int(tx), int(ty))] = stub
                            continue
                        # Fall through to legacy path if registration failed
                        # (model load failure or slot cap hit). This is safe:
                        # the env flag promises "instanced when possible",
                        # never "no trees at all" — Jaimie's hard directive.
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
        # WK58 Phase 3: merge static terrain props (grass / doodads / paths /
        # water / rocks) into fog-batch parent Entities so Panda3D only walks
        # tens-to-hundreds of nodes per frame instead of ~10k. Trees stay
        # individual because ``sync_dynamic_trees`` mutates their scale.
        self._batch_static_terrain_for_chunks(root, tw, th)
        self._build_terrain_chunks()
        # WK58 Wave 7 diagnostic: dump instanced-tree renderer state once after
        # build to catch "no trees registered" / "no shader bound" cases.
        if (
            self._instanced_trees_on
            and self._instanced_nature_renderer is not None
            and os.environ.get("KINGDOM_DIAG_INSTANCED_TREES", "").strip() == "1"
        ):
            try:
                self._instanced_nature_renderer.diagnostic_dump("post-build_3d_terrain")
            except Exception:
                pass

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

        WK58 W8 (Agent 03, Section 4.C): When ``KINGDOM_URSINA_GEOMIPTERRAIN=1`` is set
        AND a heightmap is available, build Panda3D's ``GeoMipTerrain`` with
        distance-based LOD instead of the static 62,500-vert custom Mesh. Both code
        paths populate ``self._r._terrain_ground_entity`` so the fog-shader uniform
        upload in ``ensure_fog_overlay`` works identically. ``get_terrain_height``
        keeps reading from the source-of-truth Perlin array via the ``terrain_height``
        module — display mesh choice does NOT affect prop / unit / building Y.
        """
        import math as _math

        from game.graphics.terrain_height import get_terrain_height

        cx_px = tw * ts * 0.5
        cy_px = th * ts * 0.5

        hmap = getattr(world, "heightmap", None)
        gw = getattr(world, "heightmap_grid_w", 0)
        gh = getattr(world, "heightmap_grid_h", 0)

        # --- WK58 W8 / 4.C: GeoMipTerrain LOD path (env-flag gated) -----------
        # When KINGDOM_URSINA_GEOMIPTERRAIN=1 we use Panda3D's GeoMipTerrain
        # for distance-based LOD on zoom-out. Falls through to the custom Mesh
        # path on any error (env=1 silently degrades to env=0 — the custom
        # Mesh remains the always-available implementation).
        if has_heightmap and hmap is not None and gw >= 2 and gh >= 2:
            try:
                from game.graphics.terrain_geomipterrain import (
                    geomipterrain_enabled,
                    build_geomip_terrain,
                )
                if geomipterrain_enabled():
                    height_scale = float(getattr(config, "TERRAIN_HEIGHT_SCALE", 8.0))
                    handle = build_geomip_terrain(
                        parent_entity=root,
                        hmap=hmap,
                        gw=int(gw),
                        gh=int(gh),
                        tw=int(tw),
                        th=int(th),
                        world_w=float(w_world),
                        world_d=float(d_world),
                        height_scale=height_scale,
                        tiles_per_repeat=2.0,
                    )
                    if handle is not None:
                        # ``ensure_fog_overlay`` targets ``_terrain_ground_entity``;
                        # set it to the wrap Entity so the fog texture lands on
                        # the same NodePath the shader is bound to.
                        self._r._terrain_ground_entity = handle.wrap_entity
                        # Renderer reads ``_geomip_terrain_handle`` once per
                        # frame and calls ``update_lod()``. ``__init__`` of
                        # UrsinaRenderer pre-declares None.
                        setattr(self._r, "_geomip_terrain_handle", handle)
                        return
            except Exception:
                # Fall through to custom mesh path on any GeoMipTerrain failure.
                pass

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

    def update_cave_entrance_shader(self, pois, map_width, map_height):
        """Upload discovered cave/mine entrance positions to the terrain shader.

        Converts POI grid positions to fog UV space [0,1] and sets shader uniforms.
        Call this whenever POI discovery state changes.
        """
        # FEATURE GATE: underground visuals disabled — shader defaults (radius=0,
        # entrances at 99,99) already produce no holes, so just skip the update.
        return

        ground_ent = getattr(self._r, '_terrain_ground_entity', None)
        if ground_ent is None:
            return

        from config import UNDERGROUND_HOLE_RADIUS_TILES, UNDERGROUND_HOLE_EDGE_TILES

        entrances = []
        for poi in pois:
            poi_def = getattr(poi, 'poi_def', None)
            if poi_def is None:
                continue
            if poi_def.interaction_type != 'dungeon':
                continue
            if not getattr(poi, 'is_discovered', False):
                continue
            size = poi_def.size
            cx = poi.grid_x + size[0] / 2.0
            cy = poi.grid_y + size[1] / 2.0
            # Convert to fog UV space: x/map_width, 1 - y/map_height (Y is flipped)
            uv_x = cx / map_width
            uv_y = 1.0 - (cy / map_height)
            entrances.append((uv_x, uv_y))
            if len(entrances) >= 8:
                break

        for i in range(8):
            if i < len(entrances):
                ground_ent.set_shader_input(f"cave_entrance_{i}", Vec2(*entrances[i]))
            else:
                ground_ent.set_shader_input(f"cave_entrance_{i}", Vec2(99.0, 99.0))

        if entrances:
            hole_r = UNDERGROUND_HOLE_RADIUS_TILES / max(map_width, map_height)
            edge_w = UNDERGROUND_HOLE_EDGE_TILES / max(map_width, map_height)
            ground_ent.set_shader_input("cave_hole_radius", hole_r)
            ground_ent.set_shader_input("cave_edge_width", edge_w)
        else:
            ground_ent.set_shader_input("cave_hole_radius", 0.0)
            ground_ent.set_shader_input("cave_edge_width", 0.0)

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
        from game.graphics import ursina_terrain_growth_sync
        return ursina_terrain_growth_sync.sync_dynamic_trees(self, world, snapshot_trees)

    def sync_log_stacks(self, world, snapshot_log_stacks) -> None:
        from game.graphics import ursina_terrain_growth_sync
        return ursina_terrain_growth_sync.sync_log_stacks(self, world, snapshot_log_stacks)
