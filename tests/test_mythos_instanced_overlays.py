"""Mythos S6 (`instancing-default` stack) — headless gates for the default flip.

Covers, GPU-free (offscreen Ursina where node/Text construction is needed,
pure-Python elsewhere):

* `inst-default-flip` — KINGDOM_URSINA_INSTANCING defaults ON ("1"); "0" (or
  false/no/off) selects the legacy per-Entity fallback; the renderer LATCHES
  the mode on first read (no mid-session path mixing).
* `inst-hp-bars` — the instanced branch packs HP-bar instance data for exactly
  the units legacy `sync_hp_bar` shows bars for (hp>0 & max_hp>0 & spec bar
  width >0: heroes/enemies/peasants/guards; NOT the tax collector, NOT dead
  units, NOT projectiles), with the legacy spec dims pre-multiplied by the
  billboard scale, fill fraction = hp/max_hp, bin fixed,110, and the C7
  set_two_sided invariant on every instanced geom (units/inside/shadow/bars).
  Zero ursina Entities are created by the instanced unit pass.
* `inst-parity-gap-fixes` — instance Y == get_terrain_height + half height on
  hilly coords; guards keep their non-uniform 0.5x0.7 legacy scale (3-texel
  layout); WK124 magic/heal projectile kinds resolve their own atlas frames.
* `inst-linear-interp` — packed positions blend prev->curr sim-tick positions
  with sim_blend_fraction (legacy parity), advancing on tick boundaries.
* `label-zoom-lod-pooled` — pooled Text labels appear at near zoom, are culled
  at the gate's far zoom (selected hero exempt), with hysteresis at the
  threshold, and the pool NEVER grows scene.entities across frames (bounded,
  reused — C1-leak compliant).
"""
from __future__ import annotations

import os
import struct
from types import SimpleNamespace

import pytest

# Headless: never bring up a real display/audio device.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


# ---------------------------------------------------------------------------
# Pure-Python: env default + renderer latch (`inst-default-flip`)
# ---------------------------------------------------------------------------
def test_env_unset_defaults_to_instanced(monkeypatch: pytest.MonkeyPatch) -> None:
    from game.graphics.instanced_unit_renderer import instanced_units_env_enabled

    monkeypatch.delenv("KINGDOM_URSINA_INSTANCING", raising=False)
    assert instanced_units_env_enabled() is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "off", " 0 "])
def test_env_zero_selects_legacy(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    from game.graphics.instanced_unit_renderer import instanced_units_env_enabled

    monkeypatch.setenv("KINGDOM_URSINA_INSTANCING", raw)
    assert instanced_units_env_enabled() is False


@pytest.mark.parametrize("raw", ["1", "true", "yes", "on"])
def test_env_one_selects_instanced(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    from game.graphics.instanced_unit_renderer import instanced_units_env_enabled

    monkeypatch.setenv("KINGDOM_URSINA_INSTANCING", raw)
    assert instanced_units_env_enabled() is True


def test_renderer_gate_latches_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """The renderer reads the env ONCE; later env changes cannot flip the path."""
    from game.graphics.ursina_renderer import UrsinaRenderer

    monkeypatch.delenv("KINGDOM_URSINA_INSTANCING", raising=False)
    r = object.__new__(UrsinaRenderer)
    assert r._instancing_enabled() is True, "env unset must default to the instanced path"
    monkeypatch.setenv("KINGDOM_URSINA_INSTANCING", "0")
    assert r._instancing_enabled() is True, "mode must be latched (no mid-session flip)"

    r2 = object.__new__(UrsinaRenderer)
    assert r2._instancing_enabled() is False, "'0' must select the legacy fallback"


# ---------------------------------------------------------------------------
# Offscreen Ursina bootstrap (module-scoped) — same pattern as
# tests/test_wk123_scene_entity_leak.py.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def ursina_app():
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


# ---------------------------------------------------------------------------
# Helpers: frozen DTO units + fake snapshot
# ---------------------------------------------------------------------------
def _unit(entity_id: str, kind: str = "hero", *, x=320.0, y=320.0, hp=100,
          max_hp=100, is_alive=True, **kw):
    from game.sim.render_dto import UnitDTO

    return UnitDTO(
        entity_id=entity_id,
        kind=kind,
        x=float(x),
        y=float(y),
        facing=1,
        is_alive=bool(is_alive),
        hp=float(hp),
        max_hp=float(max_hp),
        size=20,
        state_name="IDLE",
        anim_trigger=None,
        anim_trigger_seq=0,
        **kw,
    )


def _snapshot(heroes=(), enemies=(), peasants=(), guards=(), tc=None, projectiles=()):
    return SimpleNamespace(
        hero_dtos=tuple(heroes),
        enemy_dtos=tuple(enemies),
        peasant_dtos=tuple(peasants),
        guard_dtos=tuple(guards),
        tax_collector_dto=tc,
        vfx_projectiles=tuple(projectiles),
        world=None,
    )


def _step(app) -> None:
    """Advance one Ursina frame so ``scene._entities_marked_for_removal`` flushes
    (``ursina.destroy`` only marks; removal happens on the next step) — same
    helper as tests/test_wk123_scene_entity_leak.py."""
    try:
        app.step()
    except Exception:
        from ursina import scene

        for e in list(getattr(scene, "_entities_marked_for_removal", [])):
            if e in scene.entities:
                scene.entities.remove(e)
        scene._entities_marked_for_removal.clear()


def _read_texels(tex, index: int, n_texels: int = 1):
    """Unpack ``n_texels`` consecutive RGBA32F texels starting at ``index``."""
    raw = bytes(tex.get_ram_image())
    out = []
    for i in range(n_texels):
        out.append(struct.unpack_from("ffff", raw, (index + i) * 16))
    return out


# ---------------------------------------------------------------------------
# inst-hp-bars + inst-parity-gap-fixes + zero-Entity invariant
# ---------------------------------------------------------------------------
def test_instanced_update_packs_hp_bars_and_parity(ursina_app):
    from ursina import scene

    from game.graphics import instanced_unit_renderer as iur_mod
    from game.graphics.instanced_unit_renderer import (
        GUARD_SCALE_X,
        GUARD_SCALE_Y,
        HERO_SCALE,
        InstancedUnitRenderer,
        TEXELS_PER_INSTANCE,
    )
    from game.graphics.terrain_height import clear_heightmap, init_heightmap
    from game.graphics.visual_specs import HERO_SPEC

    H = 2.5  # flat-but-elevated heightmap: every sample at 2.5 world units
    init_heightmap(
        heightmap=[[H, H], [H, H]], grid_w=2, grid_h=2,
        world_w=100.0, world_h=100.0, world_origin_x=0.0, world_origin_z=-100.0,
    )
    try:
        r = InstancedUnitRenderer()
        heroes = (
            _unit("hero_dmg", "hero", hp=40, max_hp=100, name="Aldous", gold=25),
            _unit("hero_full", "hero", x=352.0, hp=100, max_hp=100, name="Brina"),
            _unit("hero_dead", "hero", x=384.0, hp=0, max_hp=100, is_alive=False),
        )
        enemies = (_unit("en_1", "enemy", x=416.0, hp=30, max_hp=60, enemy_type="goblin"),)
        peasants = (_unit("p_1", "peasant", x=448.0, hp=10, max_hp=20),)
        guards = (_unit("g_1", "guard", x=480.0, hp=50, max_hp=50),)
        tc = _unit("tc_1", "tax_collector", x=512.0, hp=10, max_hp=10, carried_gold=42)
        projectiles = (
            SimpleNamespace(x=320.0, y=352.0, kind="arrow"),
            SimpleNamespace(x=352.0, y=352.0, kind="magic"),
            SimpleNamespace(x=384.0, y=352.0, kind="heal"),
        )
        snap = _snapshot(heroes, enemies, peasants, guards, tc, projectiles)

        before_entities = len(scene.entities)
        r.update(snap, 1, sim_blend=0.0, active_layer=0)
        after_entities = len(scene.entities)

        # The instanced unit pass must create ZERO ursina Entities (geoms are
        # plain NodePaths; per-instance data only — C1 composition).
        assert after_entities == before_entities, (
            f"instanced update created {after_entities - before_entities} scene Entities"
        )

        # Unit instances: 2 live heroes + 1 enemy + 1 peasant + 1 guard + 1 tc
        # + 3 projectiles = 9 (dead hero skipped).
        assert r._geom_node_outside.get_instance_count() == 9
        # HP bars: damaged hero + full hero + enemy + peasant + guard = 5
        # (legacy shows full-health bars too; NO tc bar, NO dead-unit bar,
        # NO projectile bar).
        assert r._hp_bar_geom_node.get_instance_count() == 5

        # C7 invariant: every instanced geom is two-sided (incl. the new bars).
        for np_ in (r._geom_node_outside, r._geom_node_inside,
                    r._shadow_geom_node, r._hp_bar_geom_node):
            assert np_.get_two_sided(), f"{np_.name} lost set_two_sided (C7 regression)"
        # WK124 overlay contract: bars draw in the fixed,110 overlay bin.
        assert r._hp_bar_geom_node.get_bin_name() == "fixed"
        assert r._hp_bar_geom_node.get_bin_draw_order() == 110

        # --- terrain-Y parity: hero instance 0 at sim (320,320) -> world
        # (10,-10); y must be terrain height + half billboard height.
        (t0,) = _read_texels(r._instance_buffer, 0)
        assert t0[0] == pytest.approx(10.0, rel=1e-4)
        assert t0[2] == pytest.approx(-10.0, rel=1e-4)
        assert t0[1] == pytest.approx(H + HERO_SCALE * 0.5, rel=1e-4), (
            "instance Y must sample get_terrain_height (units sit ON hills)"
        )

        # --- guard non-uniform scale (instance index 4: 2 heroes, enemy,
        # peasant, then guard): texel0.w = x-scale, texel2.x = y-scale.
        g0, _, g2 = _read_texels(r._instance_buffer, 4 * TEXELS_PER_INSTANCE, 3)
        assert g0[3] == pytest.approx(GUARD_SCALE_X, rel=1e-4)
        assert g2[0] == pytest.approx(GUARD_SCALE_Y, rel=1e-4)
        assert GUARD_SCALE_X != GUARD_SCALE_Y, "guard must not be squashed uniform"

        # --- HP bar 0 = damaged hero: pos matches the unit instance, fill=0.4,
        # dims = legacy spec dims x billboard scale.
        b0, b1 = _read_texels(r._hp_bar_buffer, 0, 2)
        assert b0[:3] == pytest.approx(t0[:3], rel=1e-4), "bar must ride the unit's blended pos"
        assert b0[3] == pytest.approx(0.4, rel=1e-4)
        assert b1[0] == pytest.approx(HERO_SPEC.hp_bar_w * HERO_SPEC.scale_x, rel=1e-4)
        assert b1[1] == pytest.approx(HERO_SPEC.hp_bar_h * HERO_SPEC.scale_y, rel=1e-4)
        assert b1[2] == pytest.approx(HERO_SPEC.hp_bar_y * HERO_SPEC.scale_y, rel=1e-4)

        # --- WK124 projectile kinds: instance 6/7/8 = arrow/magic/heal with
        # three DISTINCT atlas frames (magic/heal no longer render as arrows).
        uvs = []
        for i in (6, 7, 8):
            _, uv_tex, _ = _read_texels(r._instance_buffer, i * TEXELS_PER_INSTANCE, 3)
            uvs.append(tuple(round(v, 6) for v in uv_tex))
        assert len(set(uvs)) == 3, f"arrow/magic/heal must use distinct atlas frames: {uvs}"
        atlas = iur_mod.UnitAtlasBuilder.get()
        assert tuple(round(v, 6) for v in atlas.lookup_uv("vfx", "projectile", "magic", 0)) == uvs[1]
        assert tuple(round(v, 6) for v in atlas.lookup_uv("vfx", "projectile", "heal", 0)) == uvs[2]

        # --- layer gate: camera underground (layer 1) -> all surface units
        # (layer 0 default) skipped.
        r.update(snap, 2, sim_blend=0.0, active_layer=1)
        assert r._geom_node_outside.get_instance_count() == 3, (
            "underground camera must hide surface units (projectiles excepted — legacy parity)"
        )
        assert r._hp_bar_geom_node.get_instance_count() == 0

        # Repeated updates keep scene.entities flat (no per-frame node churn).
        for tick in (3, 4, 5):
            r.update(snap, tick, sim_blend=0.5, active_layer=0)
        assert len(scene.entities) == before_entities
        r.destroy()
    finally:
        clear_heightmap()


# ---------------------------------------------------------------------------
# inst-linear-interp
# ---------------------------------------------------------------------------
def test_instanced_positions_blend_linearly_between_ticks(ursina_app):
    from game.graphics.instanced_unit_renderer import InstancedUnitRenderer

    r = InstancedUnitRenderer()
    snap_a = _snapshot(heroes=(_unit("h1", "hero", x=320.0, y=320.0),))
    snap_b = _snapshot(heroes=(_unit("h1", "hero", x=384.0, y=320.0),))  # +2 world x

    r.update(snap_a, 1, sim_blend=0.0)
    (t0,) = _read_texels(r._instance_buffer, 0)
    assert t0[0] == pytest.approx(10.0, rel=1e-5)

    # New sim tick at x=12: blend 0.5 -> halfway (legacy sim_blend_fraction
    # semantics, NOT exponential trailing).
    r.update(snap_b, 2, sim_blend=0.5)
    (t1,) = _read_texels(r._instance_buffer, 0)
    assert t1[0] == pytest.approx(11.0, rel=1e-5)

    # Same tick, later render frame (blend 0.9) -> 90% of the way.
    r.update(snap_b, 2, sim_blend=0.9)
    (t2,) = _read_texels(r._instance_buffer, 0)
    assert t2[0] == pytest.approx(11.8, rel=1e-5)

    # Next tick with no movement -> converges exactly on the sim position.
    r.update(snap_b, 3, sim_blend=0.25)
    (t3,) = _read_texels(r._instance_buffer, 0)
    assert t3[0] == pytest.approx(12.0, rel=1e-5)
    r.destroy()


# ---------------------------------------------------------------------------
# label-zoom-lod-pooled
# ---------------------------------------------------------------------------
def _hero_sources(n: int):
    sources = []
    for i in range(n):
        dto = _unit(f"hero_{i}", "hero", x=320.0 + 32 * i, name=f"Hero{i}", gold=10 + i)
        sources.append(("hero", dto, (10.0 + i, 0.465, -10.0)))
    return sources


def test_label_pool_lod_and_stability(ursina_app):
    from ursina import scene

    from game.graphics.instanced_unit_labels import InstancedUnitLabelPool

    pool = InstancedUnitLabelPool(max_labels=16)
    sources = _hero_sources(5)

    baseline = len(scene.entities)

    # Far zoom FIRST (the gate scenario boots zoomed out): no labels, and —
    # crucially — no Text nodes even get created.
    pool.sync(sources, zoom_ratio=0.3)
    assert pool.active_label_count == 0
    assert pool.pool_entity_count == 0
    assert len(scene.entities) == baseline

    # Near zoom: 5 names + 5 gold labels appear from the pool.
    pool.sync(sources, zoom_ratio=1.0)
    assert pool.active_label_count == 10
    created = pool.pool_entity_count
    assert 0 < created <= 16
    after_create = len(scene.entities)

    # Pool stability: repeated frames mutate, never create/destroy.
    for _ in range(4):
        pool.sync(sources, zoom_ratio=1.0)
    assert pool.pool_entity_count == created
    assert len(scene.entities) == after_create

    # Zoom back out: labels disabled, pool RETAINED (no entity churn).
    pool.sync(sources, zoom_ratio=0.3)
    assert pool.active_label_count == 0
    assert pool.pool_entity_count == created
    assert len(scene.entities) == after_create

    # Selected hero bypasses the LOD at far zoom (name + gold).
    pool.sync(sources, zoom_ratio=0.3, selected_id="hero_2")
    assert pool.active_label_count == 2
    assert {k for k in pool._assigned} == {("hero_2", "name"), ("hero_2", "gold")}

    pool.destroy()
    _step(ursina_app)  # flush ursina's deferred entity removal
    assert len(scene.entities) == baseline


def test_label_pool_hysteresis(ursina_app):
    from game.graphics.instanced_unit_labels import InstancedUnitLabelPool

    pool = InstancedUnitLabelPool(max_labels=8)
    sources = _hero_sources(2)

    # Starts culled; 0.75 sits between OFF(0.7) and ON(0.8) -> stays off.
    pool.sync(sources, zoom_ratio=0.75)
    assert pool.lod_visible is False
    # Crossing ON turns labels on.
    pool.sync(sources, zoom_ratio=0.85)
    assert pool.lod_visible is True
    # Back into the hysteresis band -> stays ON (no flicker at the threshold).
    pool.sync(sources, zoom_ratio=0.75)
    assert pool.lod_visible is True
    # Below OFF -> culled again.
    pool.sync(sources, zoom_ratio=0.65)
    assert pool.lod_visible is False
    pool.destroy()
    _step(ursina_app)  # flush removals — don't skew later modules' baselines


def test_label_pool_bounded_at_cap(ursina_app):
    from game.graphics.instanced_unit_labels import InstancedUnitLabelPool

    pool = InstancedUnitLabelPool(max_labels=4)
    sources = _hero_sources(5)  # wants 10 labels; cap is 4
    pool.sync(sources, zoom_ratio=1.0)
    assert pool.pool_entity_count == 4
    assert pool.active_label_count == 4
    # Stable across frames at the cap.
    pool.sync(sources, zoom_ratio=1.0)
    assert pool.pool_entity_count == 4
    pool.destroy()
    _step(ursina_app)  # flush removals — don't skew later modules' baselines
