"""Terrain construction (3D entity build + static chunk batching) for the Ursina renderer (WK108 slice of ursina_terrain_fog_collab.py).

Extracted VERBATIM from game/graphics/ursina_terrain_fog_collab.py:
_batch_static_terrain_for_chunks (WK58 Phase 3 static-prop fog-batch merge) and
build_3d_terrain (the main terrain/prop/tree/rock/grass/water/path constructor) —
as owner-arg module functions. The owner is UrsinaTerrainFogCollab, reached via
owner._r.* (parent UrsinaRenderer: _terrain_entity, _tree_entities,
_visibility_gated_terrain[_by_tile]) and owner.* (own slots: _instanced_trees_on,
_tree_instance_ids, _instanced_nature_renderer, _static_batch_*). build_3d_terrain
calls the WK106/WK107 wrappers (track_visibility_gated_terrain,
_ensure_instanced_nature_renderer, _build_terrain_chunks, _build_terrain_ground_mesh)
via owner.<wrapper>(...), and calls _batch_static_terrain_for_chunks as a direct
co-resident module function. UrsinaTerrainFogCollab keeps 1-line delegating wrappers
(same names+signatures) so ursina_renderer.py:572 and test_terrain_perf are stable.

Acyclic: imports leaf graphics/config/world modules + ursina/ursina.shaders at top
+ _InstancedTreeStub from ursina_terrain_growth_sync (one-way edge); imports
UrsinaTerrainFogCollab ONLY under TYPE_CHECKING. ursina_terrain_fog_collab.py imports
THIS module LAZILY inside the 2 wrapper bodies (one-way edge).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import config
from ursina import Entity, color
from ursina.shaders import unlit_shader

from game.graphics.ursina_coords import SCALE, px_to_world
from game.graphics.ursina_environment import (
    GROUND_PROP_FLOWER_LOG_MUSHROOM_SCALE,
    GRASS_SCATTER_SCALE_MULTIPLIER,
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
from game.graphics.ursina_terrain_growth_sync import _InstancedTreeStub
from game.world import TileType

if TYPE_CHECKING:
    from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab


def _batch_static_terrain_for_chunks(owner, root, tw: int, th: int) -> None:
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
    fog_batch_size = int(owner._static_batch_fog_size or 8)
    if fog_batch_size <= 0:
        fog_batch_size = 8

    existing = list(owner._r._visibility_gated_terrain)
    if not existing:
        owner._static_terrain_batches = 0
        owner._static_batch_flatten_level = "none"
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

    owner._r._visibility_gated_terrain = new_vgt
    owner._r._visibility_gated_terrain_by_tile = new_vgt_by_tile
    owner._static_terrain_batches = batches_created
    if any_strong and not any_medium and not any_noflatten:
        owner._static_batch_flatten_level = "strong"
    elif any_medium and not any_noflatten:
        owner._static_batch_flatten_level = "medium" if not any_strong else "mixed_strong_medium"
    elif any_noflatten and not any_strong and not any_medium:
        owner._static_batch_flatten_level = "none"
    else:
        # mixed outcome — some succeeded, some fell back.
        parts = []
        if any_strong:
            parts.append("strong")
        if any_medium:
            parts.append("medium")
        if any_noflatten:
            parts.append("none")
        owner._static_batch_flatten_level = "+".join(parts) if parts else "none"


def build_3d_terrain(owner, world, buildings) -> None:
    """WK53 Wave 2: heightmap-displaced mesh + per-tile path/water + scatter props with terrain Y.

    Replaces the flat ground plane with a vertex-displaced mesh whose Y values come from
    the world's heightmap (Perlin noise, generated in World.generate_heightmap).
    Props (trees, grass, rocks, paths) are placed at the correct terrain height.
    """
    if owner._r._terrain_entity is not None:
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
    owner._build_terrain_ground_mesh(root, world, tw, th, ts, w_world, d_world, has_heightmap)

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
                owner.track_visibility_gated_terrain(path_ent, tx, ty)
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
                owner.track_visibility_gated_terrain(water_ent, tx, ty)

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
                    owner.track_visibility_gated_terrain(g_ent, tx, ty)

            if tile == TileType.TREE:
                ti = _scatter_model_index(tx, ty, len(tree_models), salt=41)
                tree_model = tree_models[ti]
                # WK58 Phase 4: route into the instanced renderer when the env
                # flag is on. We deliberately skip the individual Entity
                # creation AND the visibility/chunk tracking — the instanced
                # path has its own fog gating via ``set_fog_visibility``.
                # Leaving the per-tree Entity disabled in scene would still
                # cost a NodePath; not creating it at all is the actual win.
                if owner._instanced_trees_on:
                    inst_renderer = owner._ensure_instanced_nature_renderer()
                    iid = None
                    if inst_renderer is not None:
                        iid = inst_renderer.register_tree(
                            tree_model,
                            (float(wx), float(prop_y), float(wz)),
                            float(tm),
                            (int(tx), int(ty)),
                        )
                    if iid is not None:
                        owner._tree_instance_ids[(int(tx), int(ty))] = int(iid)
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
                        owner._r._tree_entities[(int(tx), int(ty))] = stub
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
                owner.track_visibility_gated_terrain(tree_ent, tx, ty)
                owner._r._tree_entities[(int(tx), int(ty))] = tree_ent
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
                owner.track_visibility_gated_terrain(doodad_ent, tx, ty)
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
                    owner.track_visibility_gated_terrain(rock_ent, tx, ty)

    owner._r._terrain_entity = root
    # WK58 Phase 3: merge static terrain props (grass / doodads / paths /
    # water / rocks) into fog-batch parent Entities so Panda3D only walks
    # tens-to-hundreds of nodes per frame instead of ~10k. Trees stay
    # individual because ``sync_dynamic_trees`` mutates their scale.
    _batch_static_terrain_for_chunks(owner, root, tw, th)
    owner._build_terrain_chunks()
    # WK58 Wave 7 diagnostic: dump instanced-tree renderer state once after
    # build to catch "no trees registered" / "no shader bound" cases.
    if (
        owner._instanced_trees_on
        and owner._instanced_nature_renderer is not None
        and os.environ.get("KINGDOM_DIAG_INSTANCED_TREES", "").strip() == "1"
    ):
        try:
            owner._instanced_nature_renderer.diagnostic_dump("post-build_3d_terrain")
        except Exception:
            pass
