"""Visibility-gating + frustum chunk-culling + instanced-tree fog for the Ursina terrain renderer (WK106 slice of ursina_terrain_fog_collab.py).

Extracted VERBATIM from game/graphics/ursina_terrain_fog_collab.py: the 9-method
visibility/cull/instanced-fog cluster (_apply_prop_visibility_state,
track_visibility_gated_terrain, untrack_visibility_gated_terrain,
sync_terrain_prop_tile_visibility, sync_visibility_gated_terrain,
_build_terrain_chunks, cull_terrain_chunks, _ensure_instanced_nature_renderer,
_sync_instanced_trees_fog) as owner-arg module functions. The owner is
UrsinaTerrainFogCollab, reached via owner.* (own slots) / owner._r.* (parent
UrsinaRenderer). UrsinaTerrainFogCollab keeps 1-line delegating wrappers (same
names + signatures) so build_3d_terrain / ursina_renderer.py / growth_sync /
test_terrain_perf call sites are unchanged.

Acyclic: imports only leaf graphics/config/world modules + ursina_environment
(_set_static_prop_fog_tint) + ursina_terrain_growth_sync (_InstancedTreeStub,
one-way edge); imports UrsinaTerrainFogCollab ONLY under TYPE_CHECKING.
ursina_terrain_fog_collab.py imports THIS module LAZILY inside the wrapper
bodies (one-way edge: fog_collab -> fog_visibility at call time only).
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

import config
from game.graphics.ursina_environment import _set_static_prop_fog_tint
from game.graphics.ursina_terrain_growth_sync import _InstancedTreeStub
from game.world import Visibility

if TYPE_CHECKING:
    from ursina import Entity
    from game.graphics.ursina_terrain_fog_collab import UrsinaTerrainFogCollab

TERRAIN_CHUNK_SIZE = 16  # MIRROR of ursina_terrain_fog_collab.TERRAIN_CHUNK_SIZE (L47); do NOT back-import (cycle). Keep in sync.


def _apply_prop_visibility_state(
    owner,
    ent: Entity,
    *,
    fog_visible: bool | None = None,
    chunk_visible: bool | None = None,
) -> None:
    """WK58 Phase 1 Fix 1A: compose fog and chunk visibility into ent.enabled.

    Fog sync writes only ``_ks_fog_visible``; chunk culling writes only
    ``_ks_chunk_visible``. The entity is enabled iff both bits are True.
    This prevents the two systems from fighting each other's enabled state
    and keeps the invariant after ``/revealmap`` (fog flips all props
    visible but out-of-frustum chunks must stay hidden).
    """
    if fog_visible is not None:
        ent._ks_fog_visible = bool(fog_visible)
    if chunk_visible is not None:
        ent._ks_chunk_visible = bool(chunk_visible)
    should_enable = bool(getattr(ent, "_ks_fog_visible", True)) and bool(
        getattr(ent, "_ks_chunk_visible", True)
    )
    if getattr(ent, "_ks_prop_enabled", None) is not should_enable:
        try:
            ent.enabled = should_enable
        except (AssertionError, Exception):
            pass
        ent._ks_prop_enabled = should_enable


def track_visibility_gated_terrain(owner, ent: Entity, tx: int, ty: int) -> None:
    """Register vertical terrain props that should disappear only in unexplored fog."""
    # Vertical props must draw after the ground-fog quad; otherwise their tops can be clipped
    # by fog that is visually behind them at shallow perspective camera angles.
    ent.render_queue = 1
    # WK58 Phase 1 Fix 1A: initialize both visibility bits so the composed
    # state starts hidden (fog hasn't revealed) but assumes chunk-visible
    # until the first cull pass narrows it.
    ent._ks_fog_visible = False
    ent._ks_chunk_visible = True
    key = (int(tx), int(ty))
    owner._r._visibility_gated_terrain.append((ent, key[0], key[1]))
    owner._r._visibility_gated_terrain_by_tile.setdefault(key, []).append(ent)


def untrack_visibility_gated_terrain(owner, ent: Entity) -> None:
    """Remove a terrain prop from fog bookkeeping when its Entity is destroyed.

    Without this, ``sync_dynamic_trees`` / ``sync_log_stacks`` leave zombie entries in
    ``_visibility_gated_*``. Those lists grow forever and each fog revision revisits dead
    NodePaths — progressively slower FPS during longer sessions.
    """
    owner._r._visibility_gated_terrain = [
        row for row in owner._r._visibility_gated_terrain if row[0] is not ent
    ]
    bt = owner._r._visibility_gated_terrain_by_tile
    empty_keys: list[tuple[int, int]] = []
    for key, lst in list(bt.items()):
        filtered = [e for e in lst if e is not ent]
        if filtered:
            bt[key] = filtered
        else:
            empty_keys.append(key)
    for key in empty_keys:
        bt.pop(key, None)


def sync_terrain_prop_tile_visibility(owner, ent: Entity, vis: Visibility) -> None:
    # WK58 Phase 1 Fix 1A: write only the fog bit; chunk visibility is owned
    # by ``cull_terrain_chunks`` and composed via ``_apply_prop_visibility_state``.
    is_visible = vis != Visibility.UNSEEN
    _apply_prop_visibility_state(owner, ent, fog_visible=is_visible)
    if is_visible:
        try:
            seen_mult = float(getattr(config, "URSINA_SEEN_PROP_FOG_MULT", 0.5))
        except Exception:
            seen_mult = 0.5
        _set_static_prop_fog_tint(ent, seen_mult if vis == Visibility.SEEN else 1.0)


def sync_visibility_gated_terrain(owner, world, fog_revision: int) -> None:
    """Hide tall terrain props only in UNSEEN fog so they cannot protrude into unknown territory."""
    engine_rev = int(fog_revision)
    if owner._r._terrain_visibility_revision_seen == engine_rev:
        # WK58 Phase 4: instanced trees keep their own fog-revision counter so
        # we still need to give them a chance to refresh if the engine bumped
        # the revision since our last instanced sync. Cheap when up-to-date.
        _sync_instanced_trees_fog(owner, world, fog_revision)
        return

    if getattr(world, 'fog_disabled', False):
        # WK58 Phase 1 Fix 1A: /revealmap fully reveals the map.  Reset
        # BOTH visibility bits so every tracked prop is enabled at the end
        # of this sync; the next cull pass (same frame in production) will
        # narrow ``chunk_visible`` back down for out-of-frustum tiles.
        # Mirrors the player-visible semantics of /revealmap: "show
        # everything for an instant, then frustum culling re-applies".
        for ent, tx, ty in owner._r._visibility_gated_terrain:
            _apply_prop_visibility_state(
                owner, ent, fog_visible=True, chunk_visible=True
            )
            _set_static_prop_fog_tint(ent, 1.0)
        owner._r._terrain_visible_tiles_seen = None
        owner._r._terrain_visibility_revision_seen = engine_rev
        # WK58 Phase 4: same /revealmap pulse for instanced trees.
        _sync_instanced_trees_fog(owner, world, fog_revision)
        return

    current_visible = set(getattr(world, "_currently_visible", set()) or set())
    if owner._r._terrain_visible_tiles_seen is None:
        for ent, tx, ty in owner._r._visibility_gated_terrain:
            if 0 <= ty < world.height and 0 <= tx < world.width:
                vis = world.visibility[ty][tx]
            else:
                vis = Visibility.UNSEEN
            sync_terrain_prop_tile_visibility(owner, ent, vis)
    else:
        changed_tiles = owner._r._terrain_visible_tiles_seen ^ current_visible
        for tx, ty in changed_tiles:
            ents = owner._r._visibility_gated_terrain_by_tile.get((int(tx), int(ty)))
            if not ents:
                continue
            if 0 <= ty < world.height and 0 <= tx < world.width:
                vis = world.visibility[ty][tx]
            else:
                vis = Visibility.UNSEEN
            for ent in ents:
                sync_terrain_prop_tile_visibility(owner, ent, vis)
    owner._r._terrain_visible_tiles_seen = current_visible
    owner._r._terrain_visibility_revision_seen = engine_rev
    # WK58 Phase 4: instanced trees fog pass after the regular gated-prop loop.
    _sync_instanced_trees_fog(owner, world, fog_revision)


def _build_terrain_chunks(owner) -> None:
    """Group terrain entities into spatial chunks for frustum culling."""
    chunks: dict[tuple[int, int], list] = {}
    for entry in owner._r._visibility_gated_terrain:
        ent, tx, ty = entry
        cx = tx // TERRAIN_CHUNK_SIZE
        cy = ty // TERRAIN_CHUNK_SIZE
        key = (cx, cy)
        if key not in chunks:
            chunks[key] = []
        chunks[key].append(entry)
    # Also include dynamic tree entities — but ONLY legacy Entity-backed
    # trees. WK58 Phase 4 ``_InstancedTreeStub`` instances are managed by
    # the instanced renderer's own fog/transform pipeline and would only
    # waste cycles in the per-frame chunk cull (their ``enabled`` attribute
    # is a plain field with no Panda3D side-effect).
    for (tx, ty), ent in owner._r._tree_entities.items():
        if isinstance(ent, _InstancedTreeStub):
            continue
        cx = tx // TERRAIN_CHUNK_SIZE
        cy = ty // TERRAIN_CHUNK_SIZE
        key = (cx, cy)
        if key not in chunks:
            chunks[key] = []
        # Avoid duplicates — trees are already in _visibility_gated_terrain
        if not any(e is ent for e, _, _ in chunks[key]):
            chunks[key].append((ent, tx, ty))
    owner._terrain_chunks = chunks
    owner._visible_chunks = set(chunks.keys())  # All visible initially
    owner._chunks_built = True


def cull_terrain_chunks(owner, visible_rect: tuple[int, int, int, int], world) -> None:
    """Enable/disable terrain chunks based on camera frustum.

    WK58 Phase 1 Fix 1A: writes only the ``_ks_chunk_visible`` bit on tracked
    props.  ``ent.enabled`` is composed against ``_ks_fog_visible`` inside
    ``_apply_prop_visibility_state``.  When the fog revision has advanced
    since this method last ran (e.g. just after ``/revealmap`` re-enabled
    every prop in ``sync_visibility_gated_terrain``), the full chunk mask
    is re-applied so out-of-frustum chunks stay hidden even when the
    camera is stationary and the chunk set is unchanged.

    Called every frame from renderer.update().
    """
    if not getattr(owner, '_chunks_built', False):
        return

    min_tx, min_ty, max_tx, max_ty = visible_rect
    # Convert tile rect to chunk rect
    min_cx = min_tx // TERRAIN_CHUNK_SIZE
    min_cy = min_ty // TERRAIN_CHUNK_SIZE
    max_cx = max_tx // TERRAIN_CHUNK_SIZE
    max_cy = max_ty // TERRAIN_CHUNK_SIZE

    # Compute new set of visible chunks
    new_visible: set[tuple[int, int]] = set()
    for cx in range(min_cx, max_cx + 1):
        for cy in range(min_cy, max_cy + 1):
            if (cx, cy) in owner._terrain_chunks:
                new_visible.add((cx, cy))

    # WK58 Phase 1 Fix 1A: when the fog revision changed since last cull,
    # the sync pass may have flipped every prop visible (full reveal) or
    # may have enabled new tiles whose chunk is out of frustum.  Iterate
    # ALL chunks once and set ``chunk_visible`` so the composed enabled
    # state is consistent regardless of camera delta.  This is the
    # invariant the WK58-BUG-001 repro test exercises.
    current_fog_rev = int(getattr(owner._r, "_terrain_visibility_revision_seen", -1))
    if current_fog_rev != owner._last_cull_fog_revision:
        for chunk_key, entries in owner._terrain_chunks.items():
            is_visible = chunk_key in new_visible
            for ent, tx, ty in entries:
                _apply_prop_visibility_state(owner, ent, chunk_visible=is_visible)
        owner._last_cull_fog_revision = current_fog_rev
    else:
        # Steady-state delta path: only chunks that changed visibility
        # need their composed state updated.
        became_hidden = owner._visible_chunks - new_visible
        for chunk_key in became_hidden:
            for ent, tx, ty in owner._terrain_chunks[chunk_key]:
                _apply_prop_visibility_state(owner, ent, chunk_visible=False)

        became_visible = new_visible - owner._visible_chunks
        for chunk_key in became_visible:
            for ent, tx, ty in owner._terrain_chunks[chunk_key]:
                _apply_prop_visibility_state(owner, ent, chunk_visible=True)

    owner._visible_chunks = new_visible

    # WK58 Phase 4: re-pack the instanced tree buffer once per frame so
    # registration/growth/fog flips applied earlier in the frame are visible
    # on the GPU. ``update_buffer`` skips work for models whose ``dirty`` bit
    # isn't set, so the steady-state cost is just a dict-walk.
    if owner._instanced_trees_on and owner._instanced_nature_renderer is not None:
        # Push the freshly-computed camera-frustum chunk set into the
        # renderer BEFORE flushing the buffer so the instance count drops
        # from "every fog-visible tree on the map" (~2,083 post-/revealmap)
        # to "trees in the ~48 visible chunks" (~300-500). Hardware
        # instancing draws every instance unconditionally — the GPU has no
        # chunk-cull of its own. Filtering on the CPU before pack is the
        # only handle.
        try:
            owner._instanced_nature_renderer.set_visible_chunks(
                new_visible, chunk_size=TERRAIN_CHUNK_SIZE
            )
        except Exception:
            pass
        try:
            owner._instanced_nature_renderer.update_buffer()
        except Exception:
            pass
        # WK58 Wave 7 diagnostic: dump renderer state on each fog rev change
        # so we can see post-reveal active_count + per-model state.
        if os.environ.get("KINGDOM_DIAG_INSTANCED_TREES", "").strip() == "1":
            rev = int(getattr(owner._r, "_terrain_visibility_revision_seen", -1))
            last_dump = int(getattr(owner, "_instanced_trees_last_fog_rev", -1))
            try:
                owner._instanced_nature_renderer.diagnostic_dump(
                    f"fog_rev={rev} last_synced_fog_rev={last_dump}"
                )
            except Exception:
                pass


def _ensure_instanced_nature_renderer(owner):
    """WK58 Phase 4: lazy-init the hardware-instanced tree renderer.

    Returns the renderer instance, or ``None`` if construction failed
    (e.g. Panda3D unavailable, shader compile error). Caller MUST fall
    back to legacy Entity path if this returns ``None``.
    """
    if owner._instanced_nature_renderer is not None:
        return owner._instanced_nature_renderer
    try:
        from game.graphics.instanced_nature_renderer import (
            InstancedNatureRenderer,
        )
        owner._instanced_nature_renderer = InstancedNatureRenderer()
    except Exception:
        owner._instanced_nature_renderer = None
    return owner._instanced_nature_renderer


def _sync_instanced_trees_fog(owner, world, fog_revision: int) -> None:
    """WK58 Phase 4: propagate fog visibility into the instanced tree buffer.

    Skipped when the legacy individual-Entity path is active. Called once per
    frame from ``sync_visibility_gated_terrain`` after the regular gated-prop
    loop so the instanced trees inherit the same fog-revealed-by-tile state
    as the rest of the terrain. The renderer is responsible for the actual
    re-pack via ``update_buffer`` (see ``cull_terrain_chunks``).
    """
    if not owner._instanced_trees_on:
        return
    inst_renderer = owner._instanced_nature_renderer
    if inst_renderer is None:
        return
    engine_rev = int(fog_revision)
    if owner._instanced_trees_last_fog_rev == engine_rev:
        return

    if getattr(world, 'fog_disabled', False):
        # /revealmap: every registered tile becomes fog-visible. Calling the
        # helper avoids iterating world.width * world.height tiles.
        inst_renderer.set_all_fog_visible()
        owner._instanced_trees_last_fog_rev = engine_rev
        return

    # Standard fog pass: walk only the tiles that actually have trees
    # registered. With ~2,083 trees on the full map this is two orders of
    # magnitude cheaper than scanning every tile.
    for tkey in list(owner._tree_instance_ids.keys()):
        tx, ty = tkey
        if 0 <= ty < world.height and 0 <= tx < world.width:
            vis = world.visibility[ty][tx]
        else:
            vis = Visibility.UNSEEN
        inst_renderer.set_fog_visibility(tkey, vis != Visibility.UNSEEN)
    owner._instanced_trees_last_fog_rev = engine_rev
