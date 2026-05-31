"""UrsinaTerrainFogCollab — stateful facade / state-container for the Ursina terrain renderer.

WK109 end-state: after the god-file decomposition this class is just ``__init__`` (which
holds the ``_r`` reference + chunk/instanced/batch ``__slots__`` state) plus thin delegating
wrappers. The behavior lives in focused leaf modules — ``ursina_terrain_growth_sync``,
``ursina_terrain_fog_visibility``, ``ursina_terrain_ground_mesh``, ``ursina_terrain_build``,
and ``ursina_fog_overlay`` — which read/write the state via ``owner.*``. ``ursina_renderer.py``
constructs this class and calls its public methods.
"""

from __future__ import annotations

import os

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
        from game.graphics import ursina_fog_overlay
        return ursina_fog_overlay.ensure_fog_overlay(self, world, fog_revision)

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
        from game.graphics import ursina_terrain_build
        return ursina_terrain_build._batch_static_terrain_for_chunks(self, root, tw, th)

    def ensure_grid_debug_overlay(self, world, buildings) -> None:
        from game.graphics import ursina_fog_overlay
        return ursina_fog_overlay.ensure_grid_debug_overlay(self, world, buildings)

    def build_3d_terrain(self, world, buildings) -> None:
        from game.graphics import ursina_terrain_build
        return ursina_terrain_build.build_3d_terrain(self, world, buildings)

    def _build_terrain_ground_mesh(
        self, root, world, tw: int, th: int, ts: int,
        w_world: float, d_world: float, has_heightmap: bool,
    ) -> None:
        from game.graphics import ursina_terrain_ground_mesh
        return ursina_terrain_ground_mesh._build_terrain_ground_mesh(
            self, root, world, tw, th, ts, w_world, d_world, has_heightmap
        )

    def update_cave_entrance_shader(self, pois, map_width, map_height):
        from game.graphics import ursina_terrain_ground_mesh
        return ursina_terrain_ground_mesh.update_cave_entrance_shader(self, pois, map_width, map_height)

    def _apply_grass_texture(self, ground_ent, tw: int, th: int, use_texture_scale: bool = True) -> None:
        from game.graphics import ursina_terrain_ground_mesh
        return ursina_terrain_ground_mesh._apply_grass_texture(self, ground_ent, tw, th, use_texture_scale=use_texture_scale)

    def sync_dynamic_trees(self, world, snapshot_trees) -> None:
        from game.graphics import ursina_terrain_growth_sync
        return ursina_terrain_growth_sync.sync_dynamic_trees(self, world, snapshot_trees)

    def sync_log_stacks(self, world, snapshot_log_stacks) -> None:
        from game.graphics import ursina_terrain_growth_sync
        return ursina_terrain_growth_sync.sync_log_stacks(self, world, snapshot_log_stacks)
