"""WK129 BUG 2 — inside-building heroes rubberband under the instanced renderer.

LEGACY behavior (the pre-Mythos default path): a hero inside a building renders
as a STATIONARY billboard pinned ON the building — the pygame hero renderer
literally anchors at ``dto.inside_building_center`` (hero_renderer.py:142-150),
and the sim teleports the hero's x/y to the building center on entry
(hero_rest.start_resting_at_building / enter_building_briefly).

The Mythos instanced renderer (now DEFAULT) fed inside heroes through the same
``_interp_visual_position`` linear interpolator as outside units. The entry
teleport (door -> building center, typically 1-3 world units, i.e. BELOW the
3.0-unit snap threshold) was therefore LERPED across the building facade, and
any in/out flap (brief shopping enters, under-attack rest ejects) lerped the
sprite back and forth around the building = rubberbanding. Exit lerped FROM the
stale building anchor.

FIX (instanced_unit_renderer.py inside pass):
* inside heroes are PINNED at the building anchor (``inside_building_center``
  when carried, else the sim position — equal once inside) with the legacy Y
  (terrain + half billboard height); NO interpolation;
* the interp window is RESET to the anchor on every inside frame, and reset to
  the new sim position on the first OUTSIDE frame after being inside, so both
  transitions SNAP (no sweep onto / off the building).

These tests feed the renderer an outside -> inside -> stays -> exit DTO
sequence (multiple blend fractions per tick, like real frames) and assert the
packed instance position is EXACTLY the anchor on every inside frame and snaps
cleanly on exit. They FAIL on the pre-fix renderer (which packs interpolated
sweep positions on the entry tick and lerps the exit).
"""
from __future__ import annotations

import os
import struct
from types import SimpleNamespace

import pytest

# Headless: never bring up a real display/audio device.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


@pytest.fixture(scope="module")
def ursina_app():
    """Offscreen Ursina bootstrap — same pattern as test_mythos_instanced_overlays."""
    try:
        from panda3d.core import load_prc_file_data

        load_prc_file_data("", "window-type offscreen\n")
        load_prc_file_data("", "audio-library-name null\n")
        import ursina  # noqa: F401
        from ursina import Ursina
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"Panda3D/Ursina unavailable for offscreen test: {e}")

    try:
        app = Ursina()
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"Could not initialise offscreen Ursina: {e}")

    yield app

    try:
        app.destroy()
    except Exception:
        pass


def _hero(x, y, *, inside=False, center=None, state="IDLE"):
    from game.sim.render_dto import UnitDTO

    return UnitDTO(
        entity_id="ranger1",
        kind="hero",
        x=float(x),
        y=float(y),
        facing=1,
        is_alive=True,
        hp=80.0,
        max_hp=100.0,
        size=20,
        state_name=state,
        anim_trigger=None,
        anim_trigger_seq=0,
        hero_class="ranger",
        name="Brina",
        is_inside_building=bool(inside),
        inside_building_center=center,
    )


def _snap(h):
    return SimpleNamespace(
        hero_dtos=(h,),
        enemy_dtos=(),
        peasant_dtos=(),
        guard_dtos=(),
        tax_collector_dto=None,
        vfx_projectiles=(),
        world=None,
    )


def _packed_pos(tex):
    raw = bytes(tex.get_ram_image())
    return struct.unpack_from("ffff", raw, 0)[:3]


# Sim-px coords: guild center 1 tile (32px) from the door — well below the
# 3.0-world-unit snap threshold, i.e. the exact regime the interpolator lerps.
DOOR = (320.0, 320.0)
CENTER = (352.0, 320.0)
EXIT = (384.0, 320.0)
BLENDS = (0.2, 0.5, 0.8)


def _expected_world(px_xy, scale_half):
    from game.graphics.instanced_unit_renderer import HERO_SCALE
    from game.graphics.terrain_height import get_terrain_height, is_initialized
    from game.graphics.ursina_coords import sim_px_to_world_xz

    wx, wz = sim_px_to_world_xz(*px_xy)
    ty = get_terrain_height(wx, wz) if is_initialized() else 0.0
    return (wx, ty + HERO_SCALE * 0.5, wz)


def test_inside_hero_pinned_at_building_anchor_no_rubberband(ursina_app):
    from game.graphics.instanced_unit_renderer import InstancedUnitRenderer

    r = InstancedUnitRenderer()

    # Tick 1: outside at the door (seeds the interp window with the door pos).
    for b in BLENDS:
        r.update(_snap(_hero(*DOOR)), 1, sim_blend=b, active_layer=0)

    expected_anchor = _expected_world(CENTER, 0.5)

    # Ticks 2..6: inside, sim pos teleported to the guild center, DTO carries
    # the building anchor. EVERY frame (including the entry tick at every
    # blend fraction) must pack EXACTLY the anchor — no interpolation sweep.
    inside_positions = []
    for tick in range(2, 7):
        for b in BLENDS:
            r.update(
                _snap(_hero(*CENTER, inside=True, center=CENTER, state="RESTING")),
                tick,
                sim_blend=b,
                active_layer=0,
            )
            assert r._geom_node_inside.get_instance_count() == 1
            assert r._geom_node_outside.get_instance_count() == 0
            pos = _packed_pos(r._instance_buffer_inside)
            inside_positions.append(pos)
            assert pos == pytest.approx(expected_anchor, abs=1e-4), (
                f"tick={tick} blend={b}: inside hero packed at {pos}, expected "
                f"the building anchor {expected_anchor} — the inside pass is "
                "interpolating (rubberband regression)"
            )

    # No oscillation across the whole inside window.
    xs = [p[0] for p in inside_positions]
    zs = [p[2] for p in inside_positions]
    assert max(xs) - min(xs) < 1e-5 and max(zs) - min(zs) < 1e-5, (
        "inside hero position oscillated across frames (rubberband)"
    )


def test_inside_hero_without_anchor_falls_back_to_sim_pos(ursina_app):
    from game.graphics.instanced_unit_renderer import InstancedUnitRenderer

    r = InstancedUnitRenderer()
    expected = _expected_world(CENTER, 0.5)
    for b in BLENDS:
        r.update(_snap(_hero(*DOOR)), 1, sim_blend=b, active_layer=0)
    for tick in (2, 3):
        for b in BLENDS:
            r.update(
                _snap(_hero(*CENTER, inside=True, center=None)),
                tick,
                sim_blend=b,
                active_layer=0,
            )
            pos = _packed_pos(r._instance_buffer_inside)
            assert pos == pytest.approx(expected, abs=1e-4), (
                "anchor-less inside hero must pin at its (teleported) sim pos"
            )


def test_exit_resnaps_cleanly_to_outside_position(ursina_app):
    from game.graphics.instanced_unit_renderer import InstancedUnitRenderer

    r = InstancedUnitRenderer()
    for b in BLENDS:
        r.update(_snap(_hero(*DOOR)), 1, sim_blend=b, active_layer=0)
    for tick in (2, 3, 4):
        for b in BLENDS:
            r.update(
                _snap(_hero(*CENTER, inside=True, center=CENTER)),
                tick,
                sim_blend=b,
                active_layer=0,
            )

    # Tick 5: popped out (center + 1 tile). The very first outside frame must
    # pack EXACTLY the exit position — not a lerp from the building anchor.
    expected_exit = _expected_world(EXIT, 0.5)
    for b in BLENDS:
        r.update(_snap(_hero(*EXIT)), 5, sim_blend=b, active_layer=0)
        assert r._geom_node_outside.get_instance_count() == 1
        assert r._geom_node_inside.get_instance_count() == 0
        pos = _packed_pos(r._instance_buffer)
        assert pos == pytest.approx(expected_exit, abs=1e-4), (
            f"blend={b}: exit frame packed at {pos}, expected a clean snap to "
            f"{expected_exit} — exiting lerps from the building anchor"
        )

    # Subsequent ordinary OUTSIDE movement must still interpolate (the pin is
    # scoped to the inside transition; normal smoothing is unchanged).
    moved = (EXIT[0] + 16.0, EXIT[1])  # half a tile — interpolation regime
    r.update(_snap(_hero(*moved)), 6, sim_blend=0.5, active_layer=0)
    pos = _packed_pos(r._instance_buffer)
    lo = _expected_world(EXIT, 0.5)[0]
    hi = _expected_world(moved, 0.5)[0]
    assert lo < pos[0] < hi, (
        "outside movement after an exit must still interpolate between ticks"
    )
