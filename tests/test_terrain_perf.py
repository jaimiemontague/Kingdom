"""Regression tests for terrain entity tracking, chunk culling, and visible-rect math.

These tests target the POST-FIX behavior described in
``.cursor/plans/Ursina Entities Overload Solution.md``. They are expected to
FAIL until Agent 03 lands Phase 1 (culling composition + path tracking) and
Phase 2 (frustum tightening) in Wave 2.

Bug tickets referenced:
- WK58-BUG-001: ``cull_terrain_chunks()`` only processes camera-delta. When the
  camera is stationary, fog-enabled entities outside the visible rect stay
  enabled.
- WK58-BUG-002: ``view_radius = max(int(cam_y * 1.8), 30)`` covers ~88% of the
  map at default camera.
- WK58-BUG-003: ``build_3d_terrain()`` creates path entities but does not call
  ``track_visibility_gated_terrain()``. They bypass culling.

Design notes (Agent 11):

- Pure-logic / fake-entity tests where possible. The collab class
  (``UrsinaTerrainFogCollab``) does not require an Ursina window if its
  dependencies are patched.
- ``test_visible_rect_reasonable_at_default_camera`` patches ``camera`` in
  ``game.graphics.ursina_renderer`` and calls ``_get_visible_tile_rect`` on a
  stub ``self``. The method only touches ``camera`` and ``config`` globally.
- ``test_path_entities_are_tracked`` patches ``Entity`` and the asset helpers
  in ``game.graphics.ursina_terrain_fog_collab`` so ``build_3d_terrain`` can
  run end-to-end on a 10x10 fake world without loading real GLB models.
- ``test_culling_reapplies_after_fog_change`` reproduces the four-step
  sequence (initial fog sync -> camera cull -> /revealmap sync -> stationary
  cull) using fake entities. Today the final cull does not re-hide
  out-of-rect entities (loop bodies are empty when ``new_visible ==
  _visible_chunks``). After the fix, the chunk-visibility composition must
  re-apply.
"""
from __future__ import annotations

import os

# Pygame / Ursina expect a video driver; ``dummy`` avoids opening a window.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from unittest.mock import patch

import pygame
import pytest

pygame.init()

import config
import game.graphics.ursina_renderer as ursina_renderer
import game.graphics.ursina_terrain_fog_collab as tfc
from game.graphics.ursina_terrain_fog_collab import (
    TERRAIN_CHUNK_SIZE,
    UrsinaTerrainFogCollab,
)
from game.world import TileType, Visibility


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------


class _FakeColor:
    """Stand-in for Ursina ``color`` value (used by ``_set_static_prop_fog_tint``)."""

    def __init__(self, r: float = 1.0, g: float = 1.0, b: float = 1.0, a: float = 1.0) -> None:
        self.r = float(r)
        self.g = float(g)
        self.b = float(b)
        self.a = float(a)


class _FakeEntity:
    """Minimal entity surface used by terrain-fog collab code paths.

    Only the attributes/methods the collab actually touches are implemented.
    Constructed without args by tests, and with kwargs by patched
    ``Entity(...)`` calls inside ``build_3d_terrain``.
    """

    def __init__(self, *args, **kwargs) -> None:
        # ``build_3d_terrain`` passes parent=, model=, position=, scale=, color=,
        # collision=, double_sided=, add_to_scene_entities=, rotation=, shader=
        # plus ``name`` for the terrain root. Accept and ignore everything;
        # tests will set fields they care about explicitly.
        self.__dict__.update(kwargs)
        # Required surface
        self.__dict__.setdefault("enabled", True)
        self.__dict__.setdefault("render_queue", 0)
        # ``_set_static_prop_fog_tint`` reads ``ent.color.{r,g,b,a}``.
        if "color" not in self.__dict__ or not hasattr(self.__dict__["color"], "r"):
            self.__dict__["color"] = _FakeColor()


class _FakeRenderer:
    """Stand-in for ``UrsinaRenderer`` providing only the fields the collab uses."""

    def __init__(self) -> None:
        self._terrain_entity = None
        self._terrain_ground_entity = None
        self._visibility_gated_terrain: list = []
        self._visibility_gated_terrain_by_tile: dict[tuple[int, int], list] = {}
        self._tree_entities: dict[tuple[int, int], object] = {}
        self._log_stack_entities: dict[tuple[int, int], object] = {}
        self._fog_entity = None
        self._fog_revision_seen = -1
        self._fog_full_surf = None
        self._fog_tile_buf = None
        self._terrain_visibility_revision_seen = -1
        self._terrain_visible_tiles_seen: set | None = None
        self._grid_debug_entity = None


class _FakeWorld:
    """Pure-data world stub for terrain-fog collab tests."""

    def __init__(self, *, width: int = 32, height: int = 32) -> None:
        self.width = int(width)
        self.height = int(height)
        self.tiles = [
            [TileType.GRASS for _ in range(self.width)] for _ in range(self.height)
        ]
        # Start with everything UNSEEN so the first sync simulates fog active.
        self.visibility = [
            [Visibility.UNSEEN for _ in range(self.width)] for _ in range(self.height)
        ]
        self._currently_visible: list[tuple[int, int]] = []
        self.fog_disabled = False
        # build_3d_terrain optionally consults heightmap fields; leave them off
        # so the flat-fallback ground-mesh branch runs.
        self.heightmap = None
        self.heightmap_grid_w = 0
        self.heightmap_grid_h = 0


class _FakeCameraVec:
    def __init__(self, x: float, y: float, z: float) -> None:
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)


class _FakeCamera:
    """Stand-in for ``ursina.camera`` for visible-rect math.

    Default values mimic an EditorCamera looking down at the map center from a
    typical play height (~70 units). The forward vector tilts downward and
    slightly forward so the ground-ray intersection lands near the map center.
    """

    def __init__(
        self,
        *,
        cam_x: float = 125.0,
        cam_y: float = 70.0,
        cam_z: float = -125.0,
        fwd_x: float = 0.0,
        fwd_y: float = -0.7,
        fwd_z: float = 0.3,
    ) -> None:
        self.world_position = _FakeCameraVec(cam_x, cam_y, cam_z)
        self.forward = _FakeCameraVec(fwd_x, fwd_y, fwd_z)


# ---------------------------------------------------------------------------
# Test class 1: terrain entity tracking
# ---------------------------------------------------------------------------


class TestTerrainEntityTracking:
    """Verify all terrain entity types register in the visibility system and
    that chunk culling re-applies after fog changes (camera stationary).
    """

    def test_path_entities_are_tracked(self):
        """Bug WK58-BUG-003: build_3d_terrain() creates path entities but does
        not call track_visibility_gated_terrain(). They bypass culling.

        Verifies path stone entities appear in ``_visibility_gated_terrain_by_tile``.

        Approach: run ``build_3d_terrain`` on a 10x10 fake world that contains
        a horizontal strip of PATH tiles. Patch ``Entity`` and the asset
        helpers so no real GLB models load. After the build, every PATH tile
        coordinate must appear as a key in ``_visibility_gated_terrain_by_tile``.

        Today this test FAILS — the PATH branch (lines 552-563 of
        ``ursina_terrain_fog_collab.py``) creates the entity but never calls
        ``self.track_visibility_gated_terrain(path_ent, tx, ty)``.
        """
        renderer = _FakeRenderer()
        collab = UrsinaTerrainFogCollab(renderer)

        world = _FakeWorld(width=10, height=10)
        path_y = 5
        path_tile_coords: set[tuple[int, int]] = set()
        for tx in range(world.width):
            world.tiles[path_y][tx] = TileType.PATH
            path_tile_coords.add((tx, path_y))
        # Mark everything VISIBLE so we don't have to think about fog state here.
        world.visibility = [
            [Visibility.VISIBLE for _ in range(world.width)] for _ in range(world.height)
        ]

        # WK58 Phase 3 (Wave 3): once ``_batch_static_terrain_for_chunks``
        # runs as part of ``build_3d_terrain``, the path entities are
        # reparented to a per-fog-batch parent Entity and the
        # ``_visibility_gated_terrain_by_tile`` dict is rebuilt keyed by the
        # batch center tile. To keep this Phase-1 regression test stable
        # post-Phase-3, capture the snapshot of tracked entries BEFORE the
        # batcher rebuilds them. We do that by patching the batcher to a
        # no-op while letting the rest of ``build_3d_terrain`` (including the
        # ``track_visibility_gated_terrain(path_ent, ...)`` call from Fix 1B)
        # run unchanged. The original invariant — that PATH tiles appear as
        # tracked keys — is exactly what this test exercises for WK58-BUG-003.
        with patch.object(tfc, "Entity", _FakeEntity), patch.object(
            tfc, "_finalize_kenney_scatter_entity", lambda *a, **kw: None
        ), patch.object(
            tfc,
            "_environment_grass_and_doodad_model_lists",
            lambda: (["grass_model"], ["doodad_model"]),
        ), patch.object(
            tfc, "_environment_tree_model_list", lambda: ["tree_model"]
        ), patch.object(
            tfc, "_environment_model_path", lambda kind: f"fake_{kind}"
        ), patch.object(
            tfc, "_building_occupied_tiles", lambda buildings: set()
        ), patch.object(
            UrsinaTerrainFogCollab,
            "_build_terrain_ground_mesh",
            lambda *a, **kw: None,
        ), patch.object(
            UrsinaTerrainFogCollab,
            "_batch_static_terrain_for_chunks",
            lambda *a, **kw: None,
        ):
            collab.build_3d_terrain(world, [])

        tracked_tiles = set(renderer._visibility_gated_terrain_by_tile.keys())
        missing = sorted(path_tile_coords - tracked_tiles)
        assert not missing, (
            "Path stone entities are not registered in "
            "_visibility_gated_terrain_by_tile. Missing PATH tile keys: "
            f"{missing[:10]}{'...' if len(missing) > 10 else ''} "
            "(WK58-BUG-003: build_3d_terrain's PATH branch creates the entity "
            "but does not call self.track_visibility_gated_terrain(path_ent, tx, ty))."
        )

    def test_culling_reapplies_after_fog_change(self):
        """Bug WK58-BUG-001: cull_terrain_chunks() only processes camera-delta.
        When the camera is stationary, fog-enabled entities outside the visible
        rect stay enabled.

        Repro sequence:

        1. Initial fog sync (all UNSEEN) -> all tracked entities disabled.
        2. Camera cull to chunk (0,0) only -> chunks (1,1) entities stay
           disabled (their fog state is already UNSEEN). visible_chunks={(0,0)}.
        3. ``/revealmap`` fires: ``world.fog_disabled = True`` and the fog
           revision advances. ``sync_visibility_gated_terrain`` re-enables
           EVERY tracked entity (including those in chunk (1,1)).
        4. Next frame: camera has not moved, so the cull rect is unchanged
           -> ``new_visible == self._visible_chunks`` -> both ``became_hidden``
           and ``became_visible`` are empty -> loop bodies never execute ->
           chunk (1,1) entities remain enabled even though they are outside
           the camera frustum.

        After the fix (Phase 1 — compose ``ent._ks_fog_visible &&
        ent._ks_chunk_visible``), step 4's cull must re-hide entities whose
        chunk is outside the visible rect, regardless of camera delta.
        """
        renderer = _FakeRenderer()
        collab = UrsinaTerrainFogCollab(renderer)

        world = _FakeWorld(width=32, height=32)

        # Two entities per chunk so the asserts are unambiguous even if one
        # path is silently re-enabled.
        in_view_ents = []
        out_view_ents = []
        for tx, ty in [(2, 2), (3, 3)]:
            e = _FakeEntity()
            in_view_ents.append((e, tx, ty))
            collab.track_visibility_gated_terrain(e, tx, ty)
        for tx, ty in [(20, 20), (22, 22)]:
            e = _FakeEntity()
            out_view_ents.append((e, tx, ty))
            collab.track_visibility_gated_terrain(e, tx, ty)

        collab._build_terrain_chunks()
        assert (0, 0) in collab._terrain_chunks, "chunk (0,0) should exist"
        assert (1, 1) in collab._terrain_chunks, "chunk (1,1) should exist"

        cull_rect_chunk_00 = (0, 0, 10, 10)

        # ``_set_static_prop_fog_tint`` calls into ursina_environment helpers
        # that read ``ent.color``; we don't care about tint here, only about
        # ``ent.enabled``. Patch it out for both arms of the sync.
        with patch.object(tfc, "_set_static_prop_fog_tint", lambda *a, **kw: None):
            # Step 1: initial fog sync (everything UNSEEN -> everything disabled)
            collab.sync_visibility_gated_terrain(world, fog_revision=0)
            for ent, _, _ in in_view_ents + out_view_ents:
                assert ent.enabled is False, (
                    "Initial fog sync should disable all entities when "
                    "visibility is UNSEEN."
                )

            # Step 2: camera cull to chunk (0,0) only. became_visible includes
            # (0,0) (from the initial all-visible set) -> chunk 0,0 entities go
            # through the (vis != UNSEEN) check, which is False, so they stay
            # disabled. Chunk (1,1) is in became_hidden -> entities disabled.
            collab.cull_terrain_chunks(cull_rect_chunk_00, world)
            assert collab._visible_chunks == {(0, 0)}, (
                f"Expected visible_chunks to narrow to {{(0,0)}}, got "
                f"{sorted(collab._visible_chunks)}."
            )

            # Step 3: /revealmap fires. world.fog_disabled=True, fog revision
            # advances. sync re-enables every tracked entity.
            world.fog_disabled = True
            collab.sync_visibility_gated_terrain(world, fog_revision=1)
            for ent, _, _ in in_view_ents + out_view_ents:
                assert ent.enabled is True, (
                    "After /revealmap with fog_disabled=True, "
                    "sync_visibility_gated_terrain must enable every tracked "
                    "entity (precondition for reproducing the bug)."
                )

            # Step 4: camera has not moved. With the bug, became_hidden and
            # became_visible are both empty and the out-of-rect entities stay
            # enabled. With the fix, chunk-visibility composition re-hides
            # them.
            collab.cull_terrain_chunks(cull_rect_chunk_00, world)

            still_enabled_out_of_view = [
                (tx, ty) for ent, tx, ty in out_view_ents if ent.enabled
            ]
            assert not still_enabled_out_of_view, (
                "WK58-BUG-001: after /revealmap re-enabled all entities, the "
                "next chunk-cull pass with a stationary camera must re-hide "
                "entities outside the visible rect. Entities still enabled at "
                f"out-of-view tiles: {still_enabled_out_of_view}. "
                "Today cull_terrain_chunks only processes (became_hidden / "
                "became_visible) which are both empty when the chunk set is "
                "unchanged, so no re-hide happens."
            )
            # Entities inside the visible rect must still be enabled.
            for ent, tx, ty in in_view_ents:
                assert ent.enabled is True, (
                    f"In-view entity at ({tx},{ty}) must remain enabled after "
                    "the second cull pass."
                )

    def test_visible_rect_reasonable_at_default_camera(self):
        """Bug WK58-BUG-002: view_radius = max(int(cam_y * 1.8), 30) covers 88%
        of the map.

        Verifies the visible rect at default camera covers <50% of chunks
        (target ~30-60 chunks).

        Approach: stub ``camera`` in ``game.graphics.ursina_renderer`` with a
        fake EditorCamera at the map center at cam_y=70 (typical default).
        Call ``_get_visible_tile_rect`` on a stub ``self`` (the method only
        touches the global ``camera`` and ``config``). Compute how many 16x16
        chunks the returned tile rect covers, and assert it is below 50% of
        the total chunk count.

        Today this FAILS — at cam_y=70 the formula produces a ~250x227 tile
        rect covering ~94% of the 16x16 chunk grid.
        """
        map_w = int(config.MAP_WIDTH)
        map_h = int(config.MAP_HEIGHT)
        chunk_size = int(TERRAIN_CHUNK_SIZE)
        # Use the same ``+1`` chunk-count math the production cull uses
        # (``max_cx = max_tx // chunk_size`` -> inclusive range).
        total_chunks_x = (map_w - 1) // chunk_size + 1
        total_chunks_y = (map_h - 1) // chunk_size + 1
        total_chunks = total_chunks_x * total_chunks_y

        # Default EditorCamera-like state: above map center, looking down with
        # a small forward tilt. cam_y=70 is the production default playtest
        # height.
        fake_cam = _FakeCamera(
            cam_x=float(map_w) * 0.5,
            cam_y=70.0,
            cam_z=-float(map_h) * 0.5,
            fwd_x=0.0,
            fwd_y=-0.7,
            fwd_z=0.3,
        )

        stub_self = type("RendererStub", (), {})()

        with patch.object(ursina_renderer, "camera", fake_cam):
            rect = ursina_renderer.UrsinaRenderer._get_visible_tile_rect(stub_self)

        min_tx, min_ty, max_tx, max_ty = rect
        # Defensive: ensure the rect parsed sensibly (non-empty).
        assert max_tx >= min_tx and max_ty >= min_ty, f"Degenerate rect: {rect}"

        min_cx = min_tx // chunk_size
        min_cy = min_ty // chunk_size
        max_cx = max_tx // chunk_size
        max_cy = max_ty // chunk_size
        chunks_in_rect = (max_cx - min_cx + 1) * (max_cy - min_cy + 1)
        pct_covered = chunks_in_rect / total_chunks

        # The PM-stated target is ~30-60 visible chunks at default camera,
        # well below 50% of the 16x16 = 256 grid. We assert <50% to leave
        # implementation headroom; ``definition_of_done`` separately requires
        # ``visible_chunks < 80``.
        assert pct_covered < 0.5, (
            "WK58-BUG-002: visible tile rect at default camera (cam_y=70) "
            f"covers {chunks_in_rect}/{total_chunks} chunks "
            f"({pct_covered * 100:.1f}%), well over the <50% target. "
            f"Returned rect: {rect}. "
            "Today ``view_radius = max(int(cam_y * 1.8), 30)`` yields ~108-144 "
            "tiles which is most of the 250-tile map. The fix must use real "
            "lens frustum math (or a much tighter heuristic) so the rect "
            "tracks the actual screen area."
        )


# ---------------------------------------------------------------------------
# Test class 2: chunk batching (Phase 3 — not yet implemented)
# ---------------------------------------------------------------------------


class TestTerrainChunkBatching:
    """Verify that after Phase 3 batching, the count of entries in
    ``_visibility_gated_terrain`` is much lower (~hundreds, not ~10,500).
    """

    def test_static_entity_count_reduced(self):
        """WK58 Phase 3: ``_batch_static_terrain_for_chunks`` merges static
        terrain props (grass / doodads / paths / water / rocks) into fog-batch
        parent Entities and rebuilds ``_visibility_gated_terrain`` so the per-
        frame visibility loop walks tens-to-hundreds of nodes instead of
        thousands. Trees (tagged with ``_ks_tree_base_scale``) must remain
        individual because ``sync_dynamic_trees`` mutates their scale.

        Approach (pure-logic, no real Ursina init):

        1. Build a synthetic ``_visibility_gated_terrain`` with N static
           ``_FakeEntity`` props sprinkled across an 80x80 fake world plus a
           handful of trees (each tagged with ``_ks_tree_base_scale``).
        2. Call ``_batch_static_terrain_for_chunks(root, tw=80, th=80)`` with
           ``Entity`` patched so the batch parent is also a ``_FakeEntity``
           (no Panda3D node graph required) and ``flatten_strong`` /
           ``reparent_to`` available as no-op methods on the fake.
        3. Assert the post-batch tracked count is much lower than the pre-
           batch count (target: dropped to the trees + batch-parent total —
           well under 1000 for this synthetic case).
        4. Assert every tree entry survives 1:1 with its tile coordinates and
           ``_ks_tree_base_scale`` attribute preserved.

        Cross-domain note: this test edit by Agent 03 is the single documented
        exception from the file-lane rule for the wk58 wave 3 round. The PM
        prompt explicitly authorizes unblocking the previously-skipped
        ``TestTerrainChunkBatching::test_static_entity_count_reduced``.
        """

        class _BatchFakeEntity(_FakeEntity):
            """Adds the Panda3D shape methods the batcher touches."""

            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                self._reparented_to = None
                self._flatten_strong_called = False
                self._flatten_medium_called = False

            def reparent_to(self, parent) -> None:
                self._reparented_to = parent

            def flatten_strong(self) -> None:
                self._flatten_strong_called = True

            def flatten_medium(self) -> None:
                self._flatten_medium_called = True

        renderer = _FakeRenderer()
        collab = UrsinaTerrainFogCollab(renderer)

        tw = th = 80

        # Synthetic statics: ~500 path stones, ~500 grass clumps, ~200 doodads,
        # ~100 water quads. That's 1,300 static props ranging across the map.
        # The batcher should collapse these to << 1000 batch parents (likely
        # well under 200 with 8x8 fog batching + a couple of model/color groups).
        static_specs: list[tuple[int, int, str, str]] = []  # tx, ty, model_key, color_key
        rng_seed = 0
        for i in range(500):
            tx = (i * 7) % tw
            ty = (i * 11) % th
            static_specs.append((tx, ty, "fake_path", "white"))
        for i in range(500):
            tx = (i * 13 + 2) % tw
            ty = (i * 17 + 3) % th
            static_specs.append((tx, ty, "fake_grass", "white"))
        for i in range(200):
            tx = (i * 19 + 5) % tw
            ty = (i * 23 + 7) % th
            static_specs.append((tx, ty, "fake_doodad", "white"))
        for i in range(100):
            tx = (i * 29 + 11) % tw
            ty = (i * 31 + 13) % th
            static_specs.append((tx, ty, "quad", "blue"))

        for tx, ty, model_key, color_key in static_specs:
            ent = _BatchFakeEntity()
            ent.model = model_key
            ent.shader = ""
            ent.color = color_key
            renderer._visibility_gated_terrain.append((ent, tx, ty))
            renderer._visibility_gated_terrain_by_tile.setdefault(
                (tx, ty), []
            ).append(ent)

        # 50 trees scattered across the map — these MUST stay individual.
        tree_specs: list[tuple[int, int]] = [
            ((i * 37) % tw, (i * 41) % th) for i in range(50)
        ]
        tree_entries_before: list[tuple] = []
        for tx, ty in tree_specs:
            tree_ent = _BatchFakeEntity()
            tree_ent.model = "fake_tree"
            tree_ent.shader = ""
            tree_ent.color = "white"
            tree_ent._ks_tree_base_scale = 1.0
            renderer._visibility_gated_terrain.append((tree_ent, tx, ty))
            renderer._visibility_gated_terrain_by_tile.setdefault(
                (tx, ty), []
            ).append(tree_ent)
            tree_entries_before.append((tree_ent, tx, ty))

        pre_batch_count = len(renderer._visibility_gated_terrain)
        # Sanity: synthetic dataset is large enough to exercise the bug.
        assert pre_batch_count == len(static_specs) + len(tree_specs)
        assert pre_batch_count > 1000

        # Patch ``Entity`` so the batch parents are also fake (no real Ursina
        # init); the batcher calls Entity(parent=root, name=..., add_to_scene_entities=False).
        with patch.object(tfc, "Entity", _BatchFakeEntity):
            fake_root = _BatchFakeEntity(name="terrain_3d_root")
            collab._batch_static_terrain_for_chunks(fake_root, tw, th)

        post_batch = renderer._visibility_gated_terrain
        post_batch_count = len(post_batch)

        # Phase 3 success: the visibility-gated list collapses from thousands
        # to roughly (trees + batch parents). For this synthetic dataset on an
        # 80x80 map with 8x8 batches the static side compresses by 10x or more.
        assert post_batch_count < pre_batch_count, (
            f"Phase 3 batching did not reduce tracked count: "
            f"pre={pre_batch_count} post={post_batch_count}"
        )
        assert post_batch_count <= 600, (
            "Phase 3: tracked count after batching should drop to hundreds "
            f"(got {post_batch_count} from {pre_batch_count} for {len(static_specs)} "
            f"statics + {len(tree_specs)} trees on an 80x80 map with 8x8 fog "
            "batches). Either signature grouping is too narrow or trees were "
            "accidentally batched."
        )

        # Trees must survive 1:1 with their original tile keys and the
        # ``_ks_tree_base_scale`` marker.
        tree_post_entries = [
            entry for entry in post_batch
            if hasattr(entry[0], "_ks_tree_base_scale")
        ]
        assert len(tree_post_entries) == len(tree_specs), (
            f"Trees must remain individual after batching. "
            f"Expected {len(tree_specs)} tree entries, got {len(tree_post_entries)}."
        )
        post_tree_tiles = sorted((tx, ty) for _ent, tx, ty in tree_post_entries)
        pre_tree_tiles = sorted(tree_specs)
        assert post_tree_tiles == pre_tree_tiles, (
            "Tree tile coordinates changed during batching. "
            f"Before: {pre_tree_tiles[:5]}..., after: {post_tree_tiles[:5]}..."
        )

        # The batch counter should reflect the number of batch parents created.
        assert collab._static_terrain_batches > 0, (
            "Expected _static_terrain_batches to be set to the number of "
            "batch parents created."
        )
        # And it should equal (post_batch_count - trees) since every non-tree
        # entry in post_batch is a batch parent.
        non_tree_entries = post_batch_count - len(tree_post_entries)
        assert collab._static_terrain_batches == non_tree_entries, (
            f"_static_terrain_batches={collab._static_terrain_batches} "
            f"should equal post-batch non-tree entries={non_tree_entries}."
        )


# ---------------------------------------------------------------------------
# Test class 3: fog overlay early-out regression (WK58 Wave 6, Fix 1.A)
# ---------------------------------------------------------------------------


class _FakeFogTexture:
    """Minimal stand-in for the Ursina Texture returned by
    ``TerrainTextureBridge.refresh_surface_texture``. The collab body only
    sets ``filtering`` on it after the call and then passes it into
    ``terrain_ground_ent.setShaderInput`` which is wrapped in try/except.
    """

    def __init__(self) -> None:
        self.filtering = False


class _FakeTerrainGroundEntity:
    """Stand-in for the heightmap terrain ground entity.

    The collab heightmap branch (lines 295-354) calls ``setShaderInput`` on
    this entity, which is wrapped in ``try/except Exception: pass``. We do
    NOT implement setShaderInput here, so the except branch absorbs the
    AttributeError silently — that matches production behavior on real Ursina
    entities that have not had a shader bound yet.
    """


class TestFogOverlayPerf:
    """Regression coverage for WK58 Fix 1.A (fog early-out broken post-WK53 heightmap)."""

    def test_ensure_fog_overlay_early_out_post_heightmap(self):
        """Bug WK58 (Wave 5 finding): ``ensure_fog_overlay``'s early-out at
        lines 213-215 was::

            if int(fog_revision) == my_rev and self._r._fog_entity is not None:
                return

        WK53's heightmap migration (lines 295-354) replaced the dedicated fog
        quad with a shader uniform on the terrain mesh, and at line 344-351 it
        explicitly sets ``self._r._fog_entity = None`` after the first
        heightmap-path run. From that point onward ``_fog_entity is not None``
        is permanently ``False``, so the early-out NEVER fires and the function
        runs its full body (62,500-tile Python loop + ``pygame.image.frombuffer``
        + ``TerrainTextureBridge.refresh_surface_texture`` GPU upload) every
        frame regardless of whether ``fog_revision`` advanced.

        After Agent 03's Fix 1.A, ``ensure_fog_overlay`` must early-out when
        ``fog_revision == _fog_revision_seen`` regardless of whether
        ``_fog_entity`` is ``None``, as long as the heightmap shader path is
        active (``_terrain_ground_entity is not None``).

        Approach:
        1. Build a fake collab state with ``_fog_entity = None``,
           ``_terrain_ground_entity = <truthy>``, ``_terrain_entity = <truthy>``,
           and ``_fog_revision_seen`` already set to the same value the calls
           pass in. This is the post-WK53 steady-state shape.
        2. Spy on ``pygame.image.frombuffer`` (called at line 269, AFTER the
           buffer-fill loop) so we count entries into the rebuild body.
        3. Also spy on ``TerrainTextureBridge.refresh_surface_texture`` so we
           don't need a real Ursina Texture (and so we can count GPU uploads).
        4. Call ``ensure_fog_overlay(world, fog_revision=42)`` twice with the
           same revision number. Assert ``pygame.image.frombuffer`` was
           invoked AT MOST ONCE across both calls.

        Today this test FAILS — the bug causes 2 invocations (one per call).
        After Fix 1.A lands, the call site early-outs on the second invocation
        and the assertion passes.

        Note: this single-shot test pins the *invariant* (early-out works on
        the heightmap path). Agent 10's perf benchmark continues to measure
        the FPS impact in a real Ursina session.
        """
        renderer = _FakeRenderer()
        # Heightmap path preconditions: terrain root exists, ground entity
        # exists, fog quad is None (destroyed by the prior heightmap-path run).
        renderer._terrain_entity = _FakeEntity()
        renderer._terrain_ground_entity = _FakeTerrainGroundEntity()
        renderer._fog_entity = None

        # Match the revision so the gate SHOULD trip on both calls under the
        # fix. Today it trips on neither because ``_fog_entity is None``.
        baseline_rev = 42
        renderer._fog_revision_seen = baseline_rev

        collab = UrsinaTerrainFogCollab(renderer)

        # Use a small world so even if the loop runs the test stays fast. The
        # bug is structural, not size-dependent.
        world = _FakeWorld(width=10, height=10)
        # Drive the heightmap branch (lines 295-354) — the post-WK53 shape.
        world.heightmap = [[0.0 for _ in range(world.width)] for _ in range(world.height)]
        world.heightmap_grid_w = world.width
        world.heightmap_grid_h = world.height

        # Spy on pygame.image.frombuffer (called at line 269, AFTER the
        # buffer-fill loop completes). One call == one entry into the rebuild
        # body past the early-out at line 215.
        frombuffer_calls = {"count": 0}

        def _spy_frombuffer(buf, size, fmt):
            frombuffer_calls["count"] += 1
            # Return a real (small) pygame Surface so the rest of the body
            # can run without crashing on a non-Surface argument.
            surf = pygame.Surface(size, flags=pygame.SRCALPHA)
            return surf

        # Also stub the GPU upload so we never touch real Ursina Texture
        # construction. Return our minimal fake so ``filtering = True`` on
        # line 300 doesn't crash and so the heightmap branch proceeds.
        upload_calls = {"count": 0}

        def _spy_refresh(surf, *, cache_key):
            upload_calls["count"] += 1
            return _FakeFogTexture()

        with patch.object(tfc.pygame.image, "frombuffer", _spy_frombuffer), \
             patch.object(tfc.TerrainTextureBridge, "refresh_surface_texture", _spy_refresh):
            # First call: under the bug, this runs the full body. Under the
            # fix, this ALSO runs because (revision unchanged AND _fog_entity
            # is None) — wait, the gate must early-out when revision matches.
            # Both calls should early-out. Counter stays at 0.
            collab.ensure_fog_overlay(world, fog_revision=baseline_rev)
            collab.ensure_fog_overlay(world, fog_revision=baseline_rev)

        # Today (pre-fix), the bug causes both calls to run the rebuild body,
        # so frombuffer_calls["count"] == 2. After Fix 1.A the gate should
        # recognise the heightmap path is active and early-out on BOTH calls
        # (revision already matches before the first call). We assert <= 1 to
        # be lenient about whether the implementation triggers on the first
        # or second call — what matters is that we don't pay 62,500-tile
        # rebuild cost every single frame.
        assert frombuffer_calls["count"] <= 1, (
            "WK58 Fix 1.A: ensure_fog_overlay must early-out when "
            f"fog_revision ({baseline_rev}) matches _fog_revision_seen "
            f"({baseline_rev}) even when _fog_entity is None on the heightmap "
            "path. Today the gate at lines 213-215 also requires "
            "_fog_entity is not None, so post-WK53 (where _fog_entity is "
            "destroyed at line 351) the gate NEVER fires and the function "
            "runs its full 62,500-tile rebuild body every frame. "
            f"Got frombuffer_calls={frombuffer_calls['count']} across 2 "
            "matched-revision calls; expected <= 1. "
            f"upload_calls={upload_calls['count']} (also expected <= 1)."
        )
        # Cross-check: upload should also be skipped when frombuffer is.
        assert upload_calls["count"] <= 1, (
            "TerrainTextureBridge.refresh_surface_texture was invoked "
            f"{upload_calls['count']} times across 2 matched-revision calls; "
            "expected <= 1. The early-out must skip both the loop body AND "
            "the GPU upload."
        )
