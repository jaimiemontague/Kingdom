"""Dynamic tree-growth + log-stack sync for the Ursina terrain renderer (WK104 slice of ursina_terrain_fog_collab.py).

Extracted VERBATIM from game/graphics/ursina_terrain_fog_collab.py: sync_dynamic_trees,
sync_log_stacks (owner-arg module functions; the owner is UrsinaTerrainFogCollab, reached
via owner.* / owner._r.*), and the _InstancedTreeStub DTO (standalone). UrsinaTerrainFogCollab
keeps 1-line delegating wrappers (same names) so ursina_renderer.py's call sites are unchanged.
Acyclic: this module imports only leaf graphics/config/world modules + ursina at top; it
imports UrsinaTerrainFogCollab ONLY under TYPE_CHECKING. ursina_terrain_fog_collab.py re-imports
_InstancedTreeStub from here (one-way edge).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import config
from ursina import Entity, color

from game.graphics.ursina_coords import SCALE, sim_px_to_world_xz
from game.graphics.ursina_environment import (
    TREE_SCALE_MULTIPLIER,
    _environment_model_path,
    _environment_tree_model_list,
    _finalize_kenney_scatter_entity,
    _scatter_model_index,
)
from game.world import TileType, Visibility

if TYPE_CHECKING:
    from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab

TERRAIN_CHUNK_SIZE = 16  # MIRROR of ursina_terrain_fog_collab.TERRAIN_CHUNK_SIZE (L41); do NOT back-import (cycle). Keep in sync.


class _InstancedTreeStub:
    """Tile-keyed record for trees rendered by ``InstancedNatureRenderer``.

    WK58 Phase 4: when the instanced path is active, ``UrsinaRenderer._tree_entities``
    no longer holds Ursina ``Entity`` objects — it holds these stubs. The stub
    presents the SAME attribute surface that ``sync_dynamic_trees`` reads on a
    legacy tree entity (``_ks_tree_base_scale``, ``_ks_tree_growth``, ``scale``,
    ``enabled``), but writes go to the instanced renderer via ``instance_id``.

    This keeps the dynamic-growth code path unchanged from the legacy perspective:
    ``ent.scale = (s, s, s)`` becomes ``renderer.update_tree_scale(instance_id, s)``.
    """

    __slots__ = (
        "_instance_id",
        "_renderer_ref",
        "_ks_tree_base_scale",
        "_ks_tree_growth",
        "_scale",
        "_tile_xy",
        "enabled",
        "_ks_fog_visible",
        "_ks_chunk_visible",
        "_ks_prop_enabled",
        "render_queue",
        "_ks_base_color",
        "_ks_fog_mult",
        "color",
    )

    def __init__(
        self,
        *,
        instance_id: int,
        renderer_ref,
        base_scale: float,
        tile_xy: tuple[int, int],
    ) -> None:
        self._instance_id = int(instance_id)
        self._renderer_ref = renderer_ref
        self._ks_tree_base_scale = float(base_scale)
        self._ks_tree_growth = None  # matches "first scale write always applies" semantics
        self._scale = (base_scale, base_scale, base_scale)
        self._tile_xy = tile_xy
        # ``sync_visibility_*`` /``cull_terrain_chunks`` read these via getattr; we
        # never register the stub in ``_visibility_gated_terrain`` so the gating
        # logic only touches them on the instance-by-tile fog notifier path.
        self.enabled = True
        self._ks_fog_visible = False
        self._ks_chunk_visible = True
        self._ks_prop_enabled = None
        self.render_queue = 1
        self._ks_base_color = None
        self._ks_fog_mult = None
        self.color = None

    @property
    def scale(self):  # mirrors Ursina Entity.scale getter
        return self._scale

    @scale.setter
    def scale(self, value) -> None:
        """Translate ``ent.scale = (s, s, s)`` into a renderer instance update."""
        if isinstance(value, (tuple, list)) and len(value) >= 1:
            s = float(value[0])
        else:
            s = float(value)
        self._scale = (s, s, s)
        if self._renderer_ref is not None:
            try:
                self._renderer_ref.update_tree_scale(self._instance_id, s)
            except Exception:
                pass

    @property
    def instance_id(self) -> int:
        return self._instance_id

    @property
    def tile_xy(self) -> tuple[int, int]:
        return self._tile_xy


def sync_dynamic_trees(owner, world, snapshot_trees) -> None:
    """WK44/WK45: scale existing 3D tree entities using sim Tree.growth_percentage.

    WK45: saplings can spawn (create entity) and can be removed when building over them.
    """
    ents = getattr(owner._r, "_tree_entities", None)
    if not ents:
        return
    if not snapshot_trees:
        return

    # R2-A: Throttle to every 4th frame — tree growth is sim-minutes, checking
    # every frame wastes 3-5ms.  counter==0 on first call passes (0%4==0).
    counter = owner._tree_sync_tick_counter
    owner._tree_sync_tick_counter = counter + 1
    if counter % 4 != 0:
        return

    # WK45: saplings can spawn on previously-grass tiles. Create new tree Entities on-demand
    # so spawned saplings are visible in Ursina without rebuilding the whole terrain.
    root = getattr(owner._r, "_terrain_entity", None)
    if root is None:
        return

    try:
        tree_models = _environment_tree_model_list()
    except Exception:
        tree_models = []

    try:
        m = float(getattr(config, "TILE_SIZE", 32))
        tm = (m / SCALE) * float(TREE_SCALE_MULTIPLIER)
    except Exception:
        tm = 1.0

    growth_by_tile: dict[tuple[int, int], float] = {}
    for t in snapshot_trees:
        try:
            tx = int(getattr(t, "grid_x", 0))
            ty = int(getattr(t, "grid_y", 0))
            g = float(getattr(t, "growth_percentage", 1.0))
        except Exception:
            continue
        if g < 0.0:
            g = 0.0
        if g > 1.0:
            g = 1.0
        growth_by_tile[(tx, ty)] = g

        key = (tx, ty)
        if key not in ents:
            if not tree_models:
                continue
            try:
                from game.graphics.terrain_height import get_terrain_height, is_initialized as _hm_ok
                wx, wz = sim_px_to_world_xz(tx * int(config.TILE_SIZE), ty * int(config.TILE_SIZE))
                tree_y = get_terrain_height(wx, wz) if _hm_ok() else 0.0
                ti = _scatter_model_index(tx, ty, len(tree_models), salt=41)
                tree_model = tree_models[ti]
                # WK58 Phase 4: route saplings through the instanced renderer
                # when active. ``register_tree`` returns ``None`` if the
                # model failed to load or the per-model slot cap is hit —
                # in either case we fall back to the legacy Entity path so
                # the sapling still shows up (no "missing trees" regression).
                if owner._instanced_trees_on:
                    inst_renderer = owner._ensure_instanced_nature_renderer()
                    iid = None
                    if inst_renderer is not None:
                        iid = inst_renderer.register_tree(
                            tree_model,
                            (float(wx), float(tree_y), float(wz)),
                            float(tm),
                            (int(tx), int(ty)),
                        )
                    if iid is not None:
                        owner._tree_instance_ids[(int(tx), int(ty))] = int(iid)
                        stub = _InstancedTreeStub(
                            instance_id=int(iid),
                            renderer_ref=inst_renderer,
                            base_scale=float(tm),
                            tile_xy=(int(tx), int(ty)),
                        )
                        ents[key] = stub
                        # Force the next instanced-fog sync to pick this
                        # new tile up so the sapling is visible right away
                        # (otherwise it's stuck at fog_visible=False until
                        # the player crosses the tile).
                        if world is not None and 0 <= ty < world.height and 0 <= tx < world.width:
                            vis = world.visibility[ty][tx]
                            if vis != Visibility.UNSEEN and inst_renderer is not None:
                                inst_renderer.set_fog_visibility(
                                    (int(tx), int(ty)), True
                                )
                        continue
                tree_ent = Entity(
                    parent=root,
                    model=tree_model,
                    position=(wx, tree_y, wz),
                    scale=(tm, tm, tm),
                    color=color.white,
                    collision=False,
                    double_sided=True,
                    add_to_scene_entities=False,
                )
                _finalize_kenney_scatter_entity(tree_ent, tree_model)
                owner.track_visibility_gated_terrain(tree_ent, tx, ty)
                ents[key] = tree_ent
                tree_ent._ks_tree_base_scale = float(tm)
                # Register in terrain chunk for frustum culling
                if getattr(owner, '_chunks_built', False):
                    cx = tx // TERRAIN_CHUNK_SIZE
                    cy = ty // TERRAIN_CHUNK_SIZE
                    ckey = (cx, cy)
                    if ckey not in owner._terrain_chunks:
                        owner._terrain_chunks[ckey] = []
                    owner._terrain_chunks[ckey].append((tree_ent, tx, ty))
            except Exception:
                # Spawn visibility should never crash the renderer.
                pass

    # R2-E: Skip the entity scale loop entirely if growth_by_tile is identical
    # to the previous run — no tree has grown or been removed since last sync.
    last_growth = owner._last_growth_by_tile
    if growth_by_tile == last_growth:
        return
    owner._last_growth_by_tile = growth_by_tile

    for key, ent in list(ents.items()):
        g = growth_by_tile.get(key)
        if g is None:
            # If a tree entity exists but the sim no longer reports a Tree at this tile,
            # and the world tile is no longer TREE, destroy it (sapling built over).
            try:
                if world is not None and int(world.get_tile(int(key[0]), int(key[1]))) != int(TileType.TREE):
                    # WK58 Phase 4: instanced trees use ``_InstancedTreeStub``
                    # and live in the instanced renderer's per-model slot
                    # tables, NOT in ``_visibility_gated_terrain`` or
                    # Ursina's scene graph. Free the renderer slot instead.
                    if isinstance(ent, _InstancedTreeStub):
                        inst_renderer = owner._instanced_nature_renderer
                        if inst_renderer is not None:
                            try:
                                inst_renderer.remove_tree(ent.instance_id)
                            except Exception:
                                pass
                        owner._tree_instance_ids.pop(key, None)
                        ents.pop(key, None)
                    else:
                        import ursina as u

                        owner.untrack_visibility_gated_terrain(ent)
                        u.destroy(ent)
                        ents.pop(key, None)
            except Exception:
                pass
            continue
        base = float(getattr(ent, "_ks_tree_base_scale", 1.0))
        # Visual mapping: keep saplings visible at 25% without letting them block (blocking is sim-side).
        # Map growth 0..1 -> visual_scale 0.25..1.0 (linear).
        s = base * (0.25 + 0.75 * g)
        # Avoid churn if the scale is already correct.
        if getattr(ent, "_ks_tree_growth", None) != g:
            ent.scale = (s, s, s)
            ent._ks_tree_growth = g


def sync_log_stacks(owner, world, snapshot_log_stacks) -> None:
    """WK46 Stage 3: render chopped-tree log piles keyed by tile.

    Visibility gating rules:
    - enabled only if tile visibility != UNSEEN
    - apply fog tint multiplier when SEEN (reuse existing helper)
    """
    ents = getattr(owner._r, "_log_stack_entities", None)
    if ents is None:
        return

    root = getattr(owner._r, "_terrain_entity", None)
    if root is None:
        return

    want_by_tile: dict[tuple[int, int], float] = {}
    for ls in snapshot_log_stacks or ():
        try:
            tx = int(getattr(ls, "grid_x", 0))
            ty = int(getattr(ls, "grid_y", 0))
            sc = float(getattr(ls, "scale", 1.0))
        except Exception:
            continue
        if sc < 0.0:
            sc = 0.0
        if sc > 1.0:
            sc = 1.0
        want_by_tile[(tx, ty)] = sc

    if not want_by_tile and not ents:
        return

    try:
        base = float(getattr(config, "TILE_SIZE", 32)) / SCALE
    except Exception:
        base = 1.0
    base_scale = base * 0.60

    try:
        model_path = _environment_model_path("log_stackLarge")
    except Exception:
        model_path = None

    for key, sc in want_by_tile.items():
        tx, ty = int(key[0]), int(key[1])
        if model_path is None:
            continue
        if key not in ents:
            try:
                from game.graphics.terrain_height import get_terrain_height, is_initialized as _hm_ok
                wx, wz = sim_px_to_world_xz(tx * int(config.TILE_SIZE), ty * int(config.TILE_SIZE))
                log_y = get_terrain_height(wx, wz) if _hm_ok() else 0.0
                ent = Entity(
                    parent=root,
                    model=model_path,
                    position=(wx, log_y, wz),
                    scale=(base_scale, base_scale, base_scale),
                    color=color.white,
                    collision=False,
                    double_sided=True,
                    add_to_scene_entities=False,
                )
                _finalize_kenney_scatter_entity(ent, model_path)
                owner.track_visibility_gated_terrain(ent, tx, ty)
                ents[key] = ent
                ent._ks_log_base_scale = float(base_scale)
            except Exception:
                pass
        ent = ents.get(key)
        if ent is None:
            continue
        b = float(getattr(ent, "_ks_log_base_scale", base_scale))
        s = b * float(sc if sc > 0.0 else 0.0)
        if getattr(ent, "_ks_log_scale", None) != sc:
            ent.scale = (s, s, s)
            ent._ks_log_scale = sc
        # Ensure visibility gating applies even if fog revision doesn't change (cheap, per-stack).
        try:
            vis = world.visibility[ty][tx]
        except Exception:
            vis = Visibility.UNSEEN
        owner.sync_terrain_prop_tile_visibility(ent, vis)

    for key, ent in list(ents.items()):
        if key in want_by_tile:
            continue
        try:
            import ursina as u

            owner.untrack_visibility_gated_terrain(ent)
            u.destroy(ent)
        except Exception:
            pass
        ents.pop(key, None)
