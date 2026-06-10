"""WK126 T8 (Agent 09): yellow "!" quest-giver marker overlay — bin order, leak
registration, and is_open toggling.

Covers the three T8 headless-gate requirements:
  1. the marker child is lazily created (once) by ``sync_quest_giver_marker``;
  2. ``configure_ks_overlay`` puts it at bin draw-order 110 (WK124 fix: the final
     ``set_bin`` must be ``("fixed", 110)`` AFTER ``always_on_top``'s internal
     clobber-to-0 — reuses the tests/test_wk124_overlay_bin.py assertion pattern);
  3. it is registered in ``_OVERLAY_CHILD_ATTRS`` so ``free_entity_overlays``
     destroys it on giver removal (WK123 C1 leak fix — no orphan into
     ``scene.entities``), and it toggles with ``is_open``.

Two layers, like test_wk124_overlay_bin.py:
  * Layer 1 — FAKE Text/node stubs: deterministic, GPU-free, never skips. Proves
    lazy single creation, no per-frame ``.text``/transform mutation (dirty-gate /
    FPS guardrails), enabled-toggling, and final-bin ordering.
  * Layer 2 — REAL offscreen Ursina: end-to-end Panda3D ``getBinDrawOrder() == 110``
    plus the free-on-teardown leak proof. Skips cleanly without a Panda3D pipe.

Plus the pygame side: ``QuestGiverRenderer`` blits a cached yellow "!" above the
sprite only when ``is_open`` (render_text_cached — cached Surface, no re-raster).
"""
from __future__ import annotations

import os

import pytest

# Headless: never bring up a real display/audio device.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.graphics import ursina_unit_overlays as guo
from game.graphics.ursina_unit_overlays import (
    _OVERLAY_CHILD_ATTRS,
    configure_ks_overlay,
    free_entity_overlays,
    sync_quest_giver_marker,
)


# ---------------------------------------------------------------------------
# WK133 fix: render-boundary export of quest givers onto the frozen snapshot.
# Root cause of the WK133 T8 FAIL capture: RenderSnapshot carries no quest-giver
# field and SimEngine.build_snapshot never exports them, so the (tolerated-absent)
# snapshot_quest_giver_states read ALWAYS returned () and neither the NPC nor the
# "!" marker could render. attach_quest_giver_states (called by
# ursina_app_frame.run_frame right after build_snapshot) is the fix.
# ---------------------------------------------------------------------------
class _FakeLiveGiver:
    def __init__(self, giver_id="b00000007", x=100.0, y=200.0, is_open=True):
        self.giver_id = giver_id
        self.x = x
        self.y = y
        self.is_open = is_open
        self.is_alive = True


class _FakeSim:
    def __init__(self, givers):
        self.quest_givers = givers


class _FakeEngine:
    def __init__(self, givers):
        self.sim = _FakeSim(givers)


def _real_snapshot():
    from game.sim.snapshot import RenderSnapshot

    return RenderSnapshot(world=None)


def test_attach_quest_giver_states_populates_frozen_snapshot():
    """The attach must land on the REAL frozen RenderSnapshot under the exact
    field name the sync's snapshot_quest_giver_states fallback reads."""
    from game.graphics.ursina_unit_sync import (
        attach_quest_giver_states,
        snapshot_quest_giver_states,
    )

    snap = _real_snapshot()
    live = _FakeLiveGiver(is_open=True)
    attach_quest_giver_states(snap, _FakeEngine([live]))

    states = snapshot_quest_giver_states(snap)
    assert len(states) == 1
    st = states[0]
    assert st.giver_id == "b00000007"
    assert st.x == 100.0 and st.y == 200.0
    assert st.is_open is True and st.is_alive is True

    # L1 boundary: the attached state is a VALUE COPY, not the live object —
    # later sim mutation must not bleed into the already-built snapshot.
    assert st is not live
    live.is_open = False
    assert snapshot_quest_giver_states(snap)[0].is_open is True


def test_attach_quest_giver_states_noop_without_givers():
    """No givers (pre-quest games / WK67 digest scenario) -> nothing attached,
    and the sync still reads an empty tuple."""
    from game.graphics.ursina_unit_sync import (
        attach_quest_giver_states,
        snapshot_quest_giver_states,
    )

    snap = _real_snapshot()
    attach_quest_giver_states(snap, _FakeEngine([]))
    assert getattr(snap, "quest_givers", None) is None
    assert snapshot_quest_giver_states(snap) == ()

    # Engines without a .sim (or without the attr at all) are tolerated.
    attach_quest_giver_states(snap, object())
    assert snapshot_quest_giver_states(snap) == ()


def test_attach_quest_giver_states_is_open_wiring_off_state():
    """ARM_QUEST=0 capture contract: a giver with is_open=False must cross the
    boundary with is_open=False so sync_quest_giver_marker hides the '!'."""
    from game.graphics.ursina_unit_sync import (
        attach_quest_giver_states,
        snapshot_quest_giver_states,
    )

    snap = _real_snapshot()
    attach_quest_giver_states(snap, _FakeEngine([_FakeLiveGiver(is_open=False)]))
    states = snapshot_quest_giver_states(snap)
    assert len(states) == 1 and states[0].is_open is False


# ---------------------------------------------------------------------------
# Leak registration (pure; never skips)
# ---------------------------------------------------------------------------
def test_marker_attr_registered_for_leak_free_teardown():
    """``_ks_quest_marker`` MUST be in ``_OVERLAY_CHILD_ATTRS`` so the WK123 C1
    removal path (``free_entity_overlays`` before ``ursina.destroy(parent)``)
    frees the marker — Ursina destroy does NOT cascade to children."""
    assert "_ks_quest_marker" in _OVERLAY_CHILD_ATTRS


# ---------------------------------------------------------------------------
# Layer 1: fake Text/node — deterministic, GPU-free, never skips.
# ---------------------------------------------------------------------------
class _FakeMarkerText:
    """Stand-in for ursina ``Text`` with the ONLY behaviours that matter here:
    records construction kwargs, counts ``.text`` writes (dirty-gate proof), and
    mimics the Ursina/Panda ``always_on_top`` setter clobbering the bin to
    ``("fixed", 0)`` so the WK124 final-bin ordering is assertable."""

    instances: list["_FakeMarkerText"] = []

    def __init__(self, **kwargs):
        _FakeMarkerText.instances.append(self)
        self.init_kwargs = dict(kwargs)
        self._text = kwargs.get("text", "")
        self.text_writes = 0
        self.parent = kwargs.get("parent")
        self.y = kwargs.get("y", 0.0)
        self.z = 0.0
        self.enabled = True
        self.billboard = bool(kwargs.get("billboard", False))
        self._always_on_top = False
        self.bin_calls: list[tuple[str, int]] = []
        self.depth_test = True
        self.depth_write = True

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        self._text = value
        self.text_writes += 1

    @property
    def always_on_top(self) -> bool:
        return self._always_on_top

    @always_on_top.setter
    def always_on_top(self, value: bool) -> None:
        self._always_on_top = bool(value)
        if value:
            self.set_bin("fixed", 0)
            self.set_depth_test(False)

    def set_bin(self, name: str, sort: int) -> None:
        self.bin_calls.append((name, int(sort)))

    def set_depth_test(self, flag: bool) -> None:
        self.depth_test = bool(flag)

    def set_depth_write(self, flag: bool) -> None:
        self.depth_write = bool(flag)

    @property
    def final_bin(self) -> tuple[str, int] | None:
        return self.bin_calls[-1] if self.bin_calls else None


class _FakeParent:
    """Bare parent — sync_quest_giver_marker only get/setattrs ``_ks_quest_marker``."""


@pytest.fixture()
def fake_text(monkeypatch):
    _FakeMarkerText.instances = []
    monkeypatch.setattr(guo, "Text", _FakeMarkerText)
    yield _FakeMarkerText


def test_marker_created_lazily_once_and_toggles_with_is_open(fake_text):
    ent = _FakeParent()

    # Closed giver: no child at all (lazy).
    sync_quest_giver_marker(ent, False)
    assert getattr(ent, "_ks_quest_marker", None) is None
    assert fake_text.instances == []

    # Open: child created once, "!" yellow, above the head, parented to ent.
    sync_quest_giver_marker(ent, True)
    mark = getattr(ent, "_ks_quest_marker", None)
    assert mark is not None and mark is fake_text.instances[0]
    assert mark.text == "!"
    assert mark.init_kwargs.get("parent") is ent
    assert mark.init_kwargs.get("billboard") is True
    assert abs(float(mark.init_kwargs.get("y", 0.0)) - 0.8) < 1e-6
    from ursina import color as _color  # headless-safe import (no app init)

    assert mark.init_kwargs.get("color") == _color.rgb(1.0, 0.85, 0.15)
    assert mark.enabled is True

    # Toggle off -> hidden, NOT destroyed/recreated.
    sync_quest_giver_marker(ent, False)
    assert mark.enabled is False
    assert len(fake_text.instances) == 1

    # Toggle on again -> SAME instance re-enabled (no re-create).
    sync_quest_giver_marker(ent, True)
    assert getattr(ent, "_ks_quest_marker") is mark
    assert mark.enabled is True
    assert len(fake_text.instances) == 1


def test_marker_no_per_frame_text_or_bin_mutation(fake_text):
    """FPS guardrails: repeated open frames must not re-write ``.text`` (the "!"
    is constant -> zero re-raster) and must not churn render-bin state (the
    ``_ks_overlay_cfg`` guard makes configure_ks_overlay a no-op after the
    first call)."""
    ent = _FakeParent()
    sync_quest_giver_marker(ent, True)
    mark = ent._ks_quest_marker
    writes_after_create = mark.text_writes
    bins_after_create = list(mark.bin_calls)

    for _ in range(50):  # 50 "frames" with the offer still open
        sync_quest_giver_marker(ent, True)

    assert mark.text_writes == writes_after_create, "no per-frame Text.text writes"
    assert mark.bin_calls == bins_after_create, "no per-frame set_bin churn"
    assert len(fake_text.instances) == 1


def test_marker_final_bin_is_fixed_110(fake_text):
    """WK124 bin-order assertion: the LAST bin set must be ('fixed', 110) — i.e.
    assigned AFTER always_on_top's internal clobber to ('fixed', 0)."""
    ent = _FakeParent()
    sync_quest_giver_marker(ent, True)
    mark = ent._ks_quest_marker

    assert mark.final_bin == ("fixed", 110), (
        "final render bin must be ('fixed', 110); got "
        f"{mark.final_bin} (set_bin call order: {mark.bin_calls})"
    )
    assert mark.always_on_top is True
    assert ("fixed", 0) in mark.bin_calls, "always_on_top's internal reset should have run"
    assert mark.depth_test is False and mark.depth_write is False


def test_marker_freed_by_free_entity_overlays(fake_text, monkeypatch):
    """Registration proof at the function level: ``free_entity_overlays`` must
    destroy the marker via the named-attr sweep and clear the attr."""
    destroyed = []

    import ursina as _u

    monkeypatch.setattr(_u, "destroy", lambda e: destroyed.append(e))

    ent = _FakeParent()
    sync_quest_giver_marker(ent, True)
    mark = ent._ks_quest_marker

    free_entity_overlays(ent)

    assert mark in destroyed
    assert getattr(ent, "_ks_quest_marker", None) is None


# ---------------------------------------------------------------------------
# Layer 2: REAL offscreen Ursina — Panda3D draw-order + leak proof.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def ursina_app():
    """Boot a real Ursina app offscreen; skip cleanly if Panda3D/Ursina can't init."""
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
    """Flush ``scene._entities_marked_for_removal`` (same helper as the WK123 leak test)."""
    try:
        app.step()
    except Exception:
        from ursina import scene

        for e in list(getattr(scene, "_entities_marked_for_removal", [])):
            if e in scene.entities:
                scene.entities.remove(e)
        scene._entities_marked_for_removal.clear()


def test_real_marker_bin_draw_order_110_and_toggle(ursina_app):
    """A REAL marker Text must resolve to Panda's 'fixed' bin at draw order 110
    (on top of buildings@1 and instanced units@100) and toggle with is_open."""
    from ursina import Entity, destroy

    giver_ent = Entity(model="quad", billboard=True)
    try:
        sync_quest_giver_marker(giver_ent, True)
        mark = getattr(giver_ent, "_ks_quest_marker", None)
        assert mark is not None
        assert mark.text == "!"
        assert mark.getBinName() == "fixed"
        assert mark.getBinDrawOrder() == 110, (
            "marker draw order must be 110; got "
            f"{mark.getBinDrawOrder()} — 0 means always_on_top clobbered the high bin"
        )

        # Toggle with is_open: hide, re-show same node.
        sync_quest_giver_marker(giver_ent, False)
        assert mark.enabled is False
        sync_quest_giver_marker(giver_ent, True)
        assert mark.enabled is True
        assert giver_ent._ks_quest_marker is mark
    finally:
        free_entity_overlays(giver_ent)
        destroy(giver_ent)
        _step(ursina_app)


def test_real_marker_freed_no_scene_leak(ursina_app):
    """WK123 C1 invariant for the new child: after free_entity_overlays + destroy
    of the giver entity, ``scene.entities`` returns to its pre-spawn baseline —
    the marker must NOT orphan."""
    from ursina import Entity, destroy, scene

    _step(ursina_app)
    baseline = len(scene.entities)

    for _ in range(3):  # repeated open->remove cycles must not grow the scene
        giver_ent = Entity(model="quad", billboard=True)
        sync_quest_giver_marker(giver_ent, True)
        assert getattr(giver_ent, "_ks_quest_marker", None) is not None

        # The renderer removal path: free overlays FIRST, then destroy parent.
        free_entity_overlays(giver_ent)
        destroy(giver_ent)
        _step(ursina_app)

    leaked = len(scene.entities) - baseline
    assert leaked == 0, (
        f"{leaked} entity(ies) leaked into scene.entities across giver removal "
        "cycles — the quest marker child must be freed by free_entity_overlays"
    )


# ---------------------------------------------------------------------------
# Pygame renderer: "!" blit toggles with is_open; cached surface (no re-raster).
# ---------------------------------------------------------------------------
@pytest.fixture()
def pygame_surface():
    """Self-initializing pygame fixture — suite-order independent.

    pygame.init() + an explicit pygame.font.init(): these tests must never rely
    on an earlier suite test having left pygame/font initialized (an earlier
    test's pygame.quit() frees the native handles behind any module-level cached
    Font; rendering with one is an uncatchable 0xC0000005 access violation —
    font_cache is generation-guarded against this since WK126, but the tests
    still own their init lifecycle explicitly).
    """
    import pygame

    pygame.init()
    pygame.font.init()
    try:
        yield pygame.Surface((96, 96))
    finally:
        pygame.quit()


class _GiverState:
    def __init__(self, is_open: bool):
        self.x = 48.0
        self.y = 56.0
        self.giver_id = "b00000007"
        self.is_open = is_open
        self.is_alive = True
        self.size = 14
        self.color = (240, 200, 60)


def test_pygame_quest_giver_marker_blit_toggles(pygame_surface):
    from game.graphics.renderers.quest_giver_renderer import QuestGiverRenderer

    r = QuestGiverRenderer()

    def marker_region_pixels(is_open: bool):
        pygame_surface.fill((0, 0, 0))
        r.render(pygame_surface, _GiverState(is_open), (0.0, 0.0))
        # Region above the body where the "!" lands (center y - size//2 - 10).
        return [
            pygame_surface.get_at((px, py))[:3]
            for px in range(40, 57)
            for py in range(30, 46)
        ]

    closed = marker_region_pixels(False)
    open_ = marker_region_pixels(True)
    assert closed != open_, "the '!' must add pixels above the sprite when is_open"
    # Yellow-ish pixels present only when open.
    def has_yellow(pixels):
        return any(p[0] > 180 and p[1] > 150 and p[2] < 100 for p in pixels)

    assert has_yellow(open_) and not has_yellow(closed)


def test_pygame_marker_surface_is_cached(pygame_surface):
    """render_text_cached must return the SAME Surface object across frames —
    the Zzz-block FPS pattern (no per-frame font re-raster)."""
    from game.graphics.font_cache import render_text_cached
    from game.graphics.renderers.quest_giver_renderer import (
        MARKER_COLOR,
        MARKER_FONT_SIZE,
        MARKER_TEXT,
    )

    s1 = render_text_cached(MARKER_FONT_SIZE, MARKER_TEXT, MARKER_COLOR)
    s2 = render_text_cached(MARKER_FONT_SIZE, MARKER_TEXT, MARKER_COLOR)
    assert s1 is s2
