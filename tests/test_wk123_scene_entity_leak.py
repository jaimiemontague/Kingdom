"""WK123 C1 leak regression: dead-unit overlay children orphan into ``scene.entities``.

Agent 11/03 (QA + renderer). This test REPRODUCES and GATES the wk123 PRIMARY leak
(C1, empirically confirmed): when a unit dies, the renderer's removal path
``UrsinaRenderer._destroy_removed_entities`` (game/graphics/ursina_renderer.py)
calls ``ursina.destroy(parent_billboard)``. Per Ursina's ``destroy.py`` the
child-recursion is COMMENTED OUT (lines 39-43 in this build), so the unit's overlay
*child* Entities -- created with ``parent=ent`` in
``game/graphics/ursina_unit_overlays.py`` (``_ks_hp_bg`` / ``_ks_hp_fg`` /
``_ks_name_label``, plus hero ``_ks_gold_label`` / ``_ks_rest_label`` and the
tax-collector ``_ks_tc_gold`` label at ``ursina_unit_sync.py:446``) -- are NEVER
destroyed. They orphan into ``from ursina import scene`` -> ``scene.entities``
forever, and ``main._update`` walks every entity in that list every frame.

WHAT THIS DRIVES (the REAL renderer path, not a mock):
  * a real Ursina app booted offscreen (``window-type offscreen`` -- no GPU window
    needed; ``len(scene.entities)`` is fully countable, exactly as the prior
    investigation found);
  * the REAL ``UrsinaEntityRenderCollab.get_or_create_entity`` to create N unit
    billboard ``Entity`` objects and register them in ``renderer._entities``
    (keyed on a stable entity_id, exactly like the per-frame sync functions);
  * the REAL overlay-creation helpers from ``ursina_unit_overlays`` -- ``sync_hp_bar``
    (``_ks_hp_bg`` + ``_ks_hp_fg``), ``ensure_ks_name_label`` (``_ks_name_label``),
    ``sync_hero_gold_label`` (``_ks_gold_label``) -- so each parent has the SAME real
    overlay child Entities the live renderer attaches; a subset also gets the
    tax-collector ``_ks_tc_gold`` ``Text`` child created the same way
    ``ursina_unit_sync.sync_snapshot_tax_collector`` creates it;
  * the REAL ``UrsinaRenderer._destroy_removed_entities(active_ids)`` removal path
    (the unfixed ``ursina.destroy(ent)`` call) to "kill" the units.

INVARIANT under test: after spawning N units (with overlays) and then killing ALL of
them via the renderer removal path, ``len(scene.entities)`` must return to the
pre-spawn baseline -- i.e. NO orphaned overlay children remain. Repeated
spawn->death cycles must not grow ``scene.entities`` monotonically.

On CURRENT (unfixed) code this SHOULD FAIL: each dead unit leaks its overlay
children. The test prints the exact per-death leaked-entity delta and the
cross-cycle growth before asserting, so the failure output documents C1.

If Ursina cannot init offscreen in this environment, the bootstrap ``pytest.skip``s
cleanly with the reason, so the main session can run it where a Panda3D pipe exists.
"""
from __future__ import annotations

import os

import pytest

# Headless: never bring up a real display/audio device.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

# Number of units spawned per cycle and number of spawn->death cycles.
N_UNITS = 30
N_CYCLES = 3
# Of the N units, this many are tax collectors (carry a ``_ks_tc_gold`` label).
N_TAX = 5


# ---------------------------------------------------------------------------
# Offscreen Ursina bootstrap (module-scoped; shared by all tests here).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def ursina_app():
    """Boot a real Ursina app with an offscreen window (no GPU surface).

    Skips cleanly when Panda3D/Ursina cannot initialise in this environment.
    """
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
    """Advance one Ursina frame so ``scene._entities_marked_for_removal`` is flushed.

    ``ursina.destroy`` only appends the parent to ``scene._entities_marked_for_removal``;
    the entity leaves ``scene.entities`` on the next ``application`` step. Orphaned
    children are never marked, so they survive the flush -- which is exactly the leak.
    """
    try:
        app.step()
    except Exception:
        # Some Ursina builds drive removal off taskMgr rather than app.step();
        # fall back to flushing the removal list the way the scene does.
        from ursina import scene

        for e in list(getattr(scene, "_entities_marked_for_removal", [])):
            if e in scene.entities:
                scene.entities.remove(e)
        scene._entities_marked_for_removal.clear()


def _bare_renderer():
    """A ``UrsinaRenderer`` with ONLY the state ``_destroy_removed_entities`` reads.

    ``UrsinaRenderer.__init__`` constructs a heavy graphics stack (world, atlas,
    lighting, terrain). The removal path only touches ``_entities``,
    ``_unit_anim_state``, ``_unit_facing_state``, and the entity's ``_ks_gold_label``
    attr, so an ``object.__new__`` instance with those maps drives the REAL removal
    method without the heavy construction. The real ``UrsinaEntityRenderCollab`` is
    attached so unit billboards are created exactly as the live per-frame sync does.
    """
    from game.graphics.ursina_renderer import UrsinaRenderer
    from game.graphics.ursina_entity_render_collab import UrsinaEntityRenderCollab

    r = object.__new__(UrsinaRenderer)
    r._entities = {}
    r._unit_anim_state = {}
    r._unit_facing_state = {}
    r._entity_render = UrsinaEntityRenderCollab(r)
    return r


def _spawn_units_with_overlays(r, n: int, n_tax: int):
    """Create *n* unit billboards in ``r._entities``, each with real overlay children.

    Drives the REAL collaborator + overlay helpers so the parent->child Entity tree
    matches the live renderer:
      * billboard parent via ``UrsinaEntityRenderCollab.get_or_create_entity``;
      * HP bar (``_ks_hp_bg`` + ``_ks_hp_fg``) via ``sync_hp_bar``;
      * name label (``_ks_name_label``) via ``ensure_ks_name_label``;
      * hero gold label (``_ks_gold_label``) via ``sync_hero_gold_label`` for non-tax
        units (these also go through the renderer's special ``_ks_gold_label``
        destroy branch);
      * tax-collector carried-gold label (``_ks_tc_gold``) for the last *n_tax* units,
        created the same way ``ursina_unit_sync.sync_snapshot_tax_collector`` does.

    Returns the set of entity_id keys created (the snapshot's "active ids" this frame).
    """
    from ursina import Text, color
    from game.graphics.visual_specs import HERO_SPEC, TAX_COLLECTOR_SPEC
    from game.graphics.ursina_unit_overlays import (
        sync_hp_bar,
        ensure_ks_name_label,
        sync_hero_gold_label,
        configure_ks_overlay,
    )

    active_ids: set[str] = set()
    for i in range(n):
        is_tax = i >= (n - n_tax)
        key = f"unit_{i}"
        # Dummy sim object; get_or_create_entity only uses it for id() fallback,
        # but we pass an explicit stable key (exactly like the per-frame sync).
        sim_stub = object()
        ent, obj_id = r._entity_render.get_or_create_entity(
            sim_stub,
            model="quad",
            col=color.white,
            scale=(0.5, 0.5, 1),
            texture=None,
            billboard=True,
            key=key,
        )
        active_ids.add(obj_id)

        if is_tax:
            # Tax collector: name + carried-gold ``$N`` label (no HP bar in spec).
            ensure_ks_name_label(
                ent, "_ks_name_label", "Tax Collector",
                y=TAX_COLLECTOR_SPEC.label_y, scale=TAX_COLLECTOR_SPEC.label_scale,
            )
            tc_gold = Text(
                text="$42", parent=ent, origin=(0, 0), scale=10,
                color=color.rgb(1.0, 0.8, 0.2), billboard=True, y=0.35,
            )
            configure_ks_overlay(tc_gold)
            ent._ks_tc_gold = tc_gold
        else:
            # Hero-style unit: HP bar (2 quads) + name + gold label.
            sync_hp_bar(ent, hp=80, max_hp=100, spec=HERO_SPEC)
            ensure_ks_name_label(
                ent, "_ks_name_label", f"Hero {i}",
                y=HERO_SPEC.label_y, scale=HERO_SPEC.label_scale,
            )
            sync_hero_gold_label(ent, gold=25, taxed_gold=0)

    return active_ids


def _count(scene) -> int:
    return len(scene.entities)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_offscreen_ursina_can_count_scene_entities(ursina_app):
    """Sanity: the offscreen app exposes a countable ``scene.entities`` list."""
    from ursina import scene

    assert isinstance(_count(scene), int)
    assert _count(scene) >= 0


def test_dead_unit_overlay_children_do_not_leak(ursina_app):
    """C1: killing N units via the renderer removal path must NOT orphan overlay children.

    Spawns N units (each with real overlay children) through the real collaborator +
    overlay helpers, records the post-spawn AND pre-spawn ``scene.entities`` counts,
    then kills ALL units via the REAL ``UrsinaRenderer._destroy_removed_entities``
    (active_ids = empty set). After flushing the removal, ``scene.entities`` must
    return to the pre-spawn baseline.

    On unfixed code this FAILS: each parent's overlay children survive ``ursina.destroy``
    and stay in ``scene.entities``. The computed per-death leak delta and the surviving
    count are printed for the C1 record.
    """
    from ursina import scene

    r = _bare_renderer()

    baseline = _count(scene)

    active_ids = _spawn_units_with_overlays(r, N_UNITS, N_TAX)
    _step(ursina_app)
    after_spawn = _count(scene)
    spawned_entities = after_spawn - baseline
    assert len(r._entities) == N_UNITS, (
        f"expected {N_UNITS} parent billboards registered, got {len(r._entities)}"
    )
    assert spawned_entities > N_UNITS, (
        "spawn should add parents AND overlay children to scene.entities; "
        f"only {spawned_entities} added for {N_UNITS} units (overlays missing?)"
    )

    # Kill every unit: the renderer sees an EMPTY active-id set this frame, so every
    # entity in r._entities is 'dead' and goes through _destroy_removed_entities.
    r._destroy_removed_entities(active_ids=set())
    _step(ursina_app)
    after_death = _count(scene)

    leaked_total = after_death - baseline
    leaked_per_death = leaked_total / float(N_UNITS)

    print(
        "\n[wk123 C1] baseline=%d after_spawn=%d (=+%d for %d units) after_death=%d"
        % (baseline, after_spawn, spawned_entities, N_UNITS, after_death)
    )
    print(
        "[wk123 C1] LEAKED %d scene.entities after killing %d units "
        "(%.2f orphaned overlay children per death)"
        % (leaked_total, N_UNITS, leaked_per_death)
    )

    assert r._entities == {}, (
        "renderer should have dropped every dead unit from its _entities map; "
        f"{len(r._entities)} remain"
    )
    assert after_death == baseline, (
        "WK123 C1 LEAK: after killing every unit via the renderer removal path, "
        f"scene.entities did NOT return to baseline ({after_death} vs {baseline}); "
        f"{leaked_total} orphaned overlay child Entities remain "
        f"(~{leaked_per_death:.2f} per dead unit). ursina.destroy(parent) does not "
        "destroy regular .children, so _ks_hp_bg/_ks_hp_fg/_ks_name_label/"
        "_ks_gold_label/_ks_tc_gold leak into scene.entities forever."
    )


def test_repeated_spawn_death_cycles_do_not_grow_scene_entities(ursina_app):
    """C1 monotonic-growth guard: N spawn->death cycles must not accumulate entities.

    Each cycle spawns N units (with overlays) then kills all of them via the renderer
    removal path. With no leak, ``scene.entities`` after each cycle's death returns to
    the same baseline. With the C1 leak it climbs by the per-cycle orphan count every
    iteration -- the per-frame walk in ``main._update`` then grows without bound.
    """
    from ursina import scene

    r = _bare_renderer()

    baseline = _count(scene)
    post_cycle_counts: list[int] = []

    for _cycle in range(N_CYCLES):
        _spawn_units_with_overlays(r, N_UNITS, N_TAX)
        _step(ursina_app)
        r._destroy_removed_entities(active_ids=set())
        _step(ursina_app)
        post_cycle_counts.append(_count(scene))

    print(
        "\n[wk123 C1] baseline=%d post-cycle scene.entities counts=%s (per-cycle growth=%s)"
        % (
            baseline,
            post_cycle_counts,
            [post_cycle_counts[i] - (baseline if i == 0 else post_cycle_counts[i - 1])
             for i in range(len(post_cycle_counts))],
        )
    )

    # No monotonic growth: every post-death count equals the baseline.
    assert post_cycle_counts == [baseline] * N_CYCLES, (
        "WK123 C1 LEAK: scene.entities grew across spawn->death cycles "
        f"(baseline={baseline}, post-cycle={post_cycle_counts}). Each cycle's dead "
        "units orphan their overlay children, so the per-frame entity walk grows "
        "without bound."
    )
