"""Mythos S2 prefab-swap leak regression (candidate ``prefab-swap-orphan-free``).

GATES the uncovered C1-class leak from .cursor/plans/mythos_lag_fix_candidates.json
(rank 5): on every construction-stage swap (plot -> build_20 -> build_50 -> final)
and prefab-path/mode change, ``UrsinaEntityRenderCollab.get_or_create_prefab_building_entity``
/ ``get_or_create_3d_building_entity`` destroy the OLD prefab root via
``ursina.destroy(ent)``. Ursina's destroy does NOT cascade to regular ``.children``
(the recursion in ursina/destroy.py is commented out), so the root's piece child
Entities (up to ~26 per prefab, created ``parent=root`` in
``ursina_prefabs._load_prefab_instance``) orphan into ``scene.entities`` forever
(measured +84 over 5 swap cycles pre-fix). Real play spawns a neutral building
every ~6s, each crossing 3-4 construction stages — by minute 15-20 that is
~1.5-2k orphans inflating the per-frame Ursina entity walk and every later
``ursina.destroy``'s linear ``entity in scene.entities`` scan: the exact WK123 C1
time-degradation mechanism, re-introduced.

THE FIX under test: both destroy branches call
``ursina_unit_overlays.free_entity_overlays(ent)`` (the WK123 C1 helper — named
overlay attr sweep + children/loose_children sweep) BEFORE ``ursina.destroy(ent)``.

WHAT THIS DRIVES (the REAL renderer path, modeled on
tests/test_wk123_scene_entity_leak.py — not a mock):
  * a real Ursina app booted offscreen (no GPU window needed);
  * the REAL ``_resolve_prefab_path`` / ``_resolve_construction_staged_prefab``
    to obtain genuine on-disk construction-stage prefab JSON paths for a farm;
  * the REAL ``UrsinaEntityRenderCollab.get_or_create_prefab_building_entity``
    swap path (resolved path changes per stage -> destroy + reinstantiate), and
    the REAL ``get_or_create_3d_building_entity`` mode-switch destroy branch;
  * the REAL ``UrsinaRenderer._destroy_removed_entities`` (WK123 C1-fixed) for
    final teardown.

INVARIANT: after cycling a building through its construction stages N times and
then removing it, ``len(scene.entities)`` returns to the pre-spawn baseline, and
the post-cycle count is FLAT (identical) across cycles — not monotonic.

On PRE-FIX code this FAILS: each stage swap leaks the old root's piece children
(verified by neutering the ``free_entity_overlays`` calls — see the sprint report).

If Ursina cannot init offscreen here, the bootstrap ``pytest.skip``s cleanly.
"""
from __future__ import annotations

import os

import pytest

# Headless: never bring up a real display/audio device.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

# Construction cycles driven in the flatness test.
N_CYCLES = 3


# ---------------------------------------------------------------------------
# Offscreen Ursina bootstrap (module-scoped; same pattern as test_wk123_*).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def ursina_app():
    """Boot a real Ursina app with an offscreen window (no GPU surface)."""
    try:
        from panda3d.core import load_prc_file_data

        load_prc_file_data("", "window-type offscreen\n")
        load_prc_file_data("", "audio-library-name null\n")
        import ursina  # noqa: F401
        from ursina import Ursina
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"Panda3D/Ursina import unavailable for offscreen test: {e}")

    try:
        app = Ursina()
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"Could not initialise offscreen Ursina: {e}")

    yield app

    try:
        app.destroy()
    except Exception:
        pass


def _step(app) -> None:
    """Advance one Ursina frame so ``scene._entities_marked_for_removal`` flushes."""
    try:
        app.step()
    except Exception:
        from ursina import scene

        for e in list(getattr(scene, "_entities_marked_for_removal", [])):
            if e in scene.entities:
                scene.entities.remove(e)
        scene._entities_marked_for_removal.clear()


def _bare_renderer():
    """A ``UrsinaRenderer`` with ONLY the state the exercised paths read.

    Same idiom as test_wk123_scene_entity_leak: ``object.__new__`` + the maps
    ``_destroy_removed_entities`` touches, with the REAL collaborator attached so
    building entities are created/swapped exactly as the live per-frame sync does.
    """
    from game.graphics.ursina_entity_render_collab import UrsinaEntityRenderCollab
    from game.graphics.ursina_renderer import UrsinaRenderer

    r = object.__new__(UrsinaRenderer)
    r._entities = {}
    r._unit_anim_state = {}
    r._unit_facing_state = {}
    r._entity_render = UrsinaEntityRenderCollab(r)
    return r


class _BuildingStub:
    """Minimal duck-typed building for the REAL prefab path resolvers."""

    is_lair = False
    has_stash_gold = False

    def __init__(self, progress: float, constructed: bool) -> None:
        self.construction_progress = float(progress)
        self.is_constructed = bool(constructed)


def _construction_stage_paths():
    """Resolve the REAL on-disk stage prefab paths for a farm (plot/20/50/final).

    Uses the exact resolvers the per-frame building sync uses, so the test swaps
    through the same JSON files real construction crosses.
    """
    from game.graphics.ursina_prefabs import (
        _footprint_tiles,
        _resolve_construction_staged_prefab,
        _resolve_prefab_path,
    )

    base = _resolve_prefab_path("farm", _BuildingStub(1.0, True))
    if base is None:
        pytest.skip("farm prefab JSON not found on disk")
    tw, th = _footprint_tiles("farm")

    paths = []
    for prog in (0.0, 0.3, 0.7):
        paths.append(
            _resolve_construction_staged_prefab(_BuildingStub(prog, False), base, tw, th)
        )
    paths.append(base)

    # The swap leak needs real path CHANGES; require at least 3 distinct stage files.
    if len({str(p) for p in paths}) < 3:
        pytest.skip(f"not enough distinct farm stage prefabs on disk: {paths}")
    return paths


def _count(scene) -> int:
    return len(scene.entities)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_construction_stage_swaps_do_not_orphan_pieces(ursina_app):
    """One full plot->20->50->final stage walk + removal must return to baseline."""
    from ursina import color, scene

    r = _bare_renderer()
    paths = _construction_stage_paths()
    baseline = _count(scene)

    per_swap_counts = []
    for p in paths:
        r._entity_render.get_or_create_prefab_building_entity(
            object(), p, color.white, key="bld_swap"
        )
        _step(ursina_app)
        per_swap_counts.append(_count(scene))

    # Sanity: a prefab root carries piece children (the orphan source). Without
    # this the test would vacuously pass on an empty prefab.
    assert per_swap_counts[-1] > baseline + 1, (
        "expected the final prefab to add a root AND piece children; counts "
        f"baseline={baseline} per-swap={per_swap_counts}"
    )

    # Remove the building via the REAL (WK123 C1-fixed) removal path.
    r._destroy_removed_entities(active_ids=set())
    _step(ursina_app)
    after_death = _count(scene)
    leaked = after_death - baseline

    print(
        "\n[mythos prefab-swap] baseline=%d per-swap=%s after_death=%d leaked=%d"
        % (baseline, per_swap_counts, after_death, leaked)
    )

    assert r._entities == {}, "renderer should have dropped the building from _entities"
    assert after_death == baseline, (
        "PREFAB-SWAP LEAK: scene.entities did not return to baseline after a full "
        f"construction-stage walk + removal ({after_death} vs {baseline}; {leaked} "
        "orphaned entities). Each stage swap's ursina.destroy(root) leaves the old "
        "root's piece children in scene.entities — free_entity_overlays must run "
        "before destroy in get_or_create_prefab_building_entity."
    )


def test_repeated_construction_cycles_keep_scene_entities_flat(ursina_app):
    """N stage-walk cycles must hold ``len(scene.entities)`` FLAT, not monotonic.

    The building stays alive in its final stage after each cycle, so every
    post-cycle count must be identical; growth == the per-cycle orphan count.
    """
    from ursina import color, scene

    r = _bare_renderer()
    paths = _construction_stage_paths()
    baseline = _count(scene)

    post_cycle_counts = []
    for _cycle in range(N_CYCLES):
        for p in paths:
            r._entity_render.get_or_create_prefab_building_entity(
                object(), p, color.white, key="bld_cycle"
            )
            _step(ursina_app)
        post_cycle_counts.append(_count(scene))

    growth = [
        post_cycle_counts[i] - post_cycle_counts[0] for i in range(len(post_cycle_counts))
    ]
    print(
        "\n[mythos prefab-swap] baseline=%d post-cycle counts=%s growth-vs-cycle1=%s"
        % (baseline, post_cycle_counts, growth)
    )

    assert len(set(post_cycle_counts)) == 1, (
        "PREFAB-SWAP LEAK: scene.entities grew across construction cycles "
        f"(post-cycle counts={post_cycle_counts}). Orphaned stage-prefab pieces "
        "accumulate per swap, re-introducing the WK123 C1 time-degradation."
    )

    r._destroy_removed_entities(active_ids=set())
    _step(ursina_app)
    assert _count(scene) == baseline, (
        f"final removal did not return to baseline ({_count(scene)} vs {baseline})"
    )


def test_prefab_to_mesh3d_mode_switch_does_not_orphan(ursina_app):
    """The mesh_3d branch's mode-mismatch destroy must also free prefab children."""
    from ursina import color, scene

    r = _bare_renderer()
    paths = _construction_stage_paths()
    baseline = _count(scene)

    r._entity_render.get_or_create_prefab_building_entity(
        object(), paths[-1], color.white, key="bld_mode"
    )
    _step(ursina_app)
    with_prefab = _count(scene)
    assert with_prefab > baseline + 1, "prefab should add a root AND piece children"

    # Same key, mesh_3d mode: destroys the prefab root (mode mismatch) and creates
    # a single cube entity in its place.
    r._entity_render.get_or_create_3d_building_entity(
        object(), "cube", color.white, key="bld_mode"
    )
    _step(ursina_app)
    after_switch = _count(scene)
    orphans = after_switch - (baseline + 1)

    print(
        "\n[mythos prefab-swap] baseline=%d with_prefab=%d after_mode_switch=%d orphans=%d"
        % (baseline, with_prefab, after_switch, orphans)
    )

    assert after_switch == baseline + 1, (
        f"MODE-SWITCH LEAK: expected baseline+1 (the cube) after prefab->mesh_3d "
        f"switch, got {after_switch} ({orphans} orphaned prefab piece children)."
    )

    r._destroy_removed_entities(active_ids=set())
    _step(ursina_app)
    assert _count(scene) == baseline
