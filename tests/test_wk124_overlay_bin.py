"""WK124-T1 (Agent 09): world-space overlays (tax-gold ``$N``, HP bars, name labels, hero
``$N``/``Zzz``, tax-collector gold) must draw ON TOP of all buildings.

ROOT CAUSE: ``configure_ks_overlay`` set ``set_bin("fixed", 60)`` and THEN
``always_on_top = True``. Ursina's ``always_on_top`` setter internally runs
``set_bin("fixed", 0)``, clobbering the high bin back to sort 0 -> the label ended at
``fixed,0`` and drew UNDER buildings (``fixed,1``). The old ``render_queue = 2`` line was a
no-op for ``Text`` (Text has no ``.model``).

FIX: set ``always_on_top`` FIRST, then re-assert depth off, then ``set_bin("fixed", 110)``
LAST so nothing clobbers it. 110 beats buildings (fixed,1) and instanced units (fixed,100).

Two layers of coverage, both GPU-free:
  1. A FAKE NodePath that records the final ``set_bin`` -> proves ordering deterministically
     even where Panda3D/Ursina cannot init (no skip). This is the core regression guard for
     the self-cancelling bug.
  2. A REAL offscreen-Ursina ``Text`` whose Panda ``getBinDrawOrder()`` is asserted == 110
     -- this is the end-to-end proof that the live render state is correct. It SKIPS cleanly
     when Panda3D/Ursina cannot initialise (headless box without a GPU pipe).
"""
from __future__ import annotations

import os

import pytest

# Headless: never bring up a real display/audio device.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.graphics.ursina_unit_overlays import configure_ks_overlay


# ---------------------------------------------------------------------------
# Layer 1: fake NodePath -- deterministic, no Panda3D/Ursina, never skips.
# ---------------------------------------------------------------------------
class _FakeAlwaysOnTopNode:
    """Minimal stand-in that mimics the ONLY Ursina/Panda behaviour that matters here:
    the ``always_on_top`` setter internally resets the bin to ``("fixed", 0)`` (and depth
    off). It records every ``set_bin`` call so the test can assert the FINAL bin -- which is
    what Panda's draw order resolves to. This catches the self-cancelling order bug without
    a GPU.
    """

    def __init__(self) -> None:
        self.billboard = False
        self.z = 0.0
        self._always_on_top = False
        self.bin_calls: list[tuple[str, int]] = []
        self.depth_test = True
        self.depth_write = True

    # ``always_on_top`` is a property whose setter clobbers the bin (like Ursina's).
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


def test_fake_node_final_bin_is_fixed_110():
    """After ``configure_ks_overlay``, the LAST bin set must be ('fixed', 110) -- i.e. the
    high bin is assigned AFTER ``always_on_top`` clobbers it, not before."""
    node = _FakeAlwaysOnTopNode()
    configure_ks_overlay(node)

    assert node.final_bin == ("fixed", 110), (
        "the final render bin must be ('fixed', 110); got "
        f"{node.final_bin} (set_bin call order: {node.bin_calls}). If the last bin is "
        "('fixed', 0) the always_on_top setter clobbered the high bin -- the high bin must "
        "be assigned LAST."
    )
    # always_on_top did run (and its clobber-to-0 was overridden afterwards).
    assert node.always_on_top is True
    assert ("fixed", 0) in node.bin_calls, "always_on_top's internal reset should have run"
    assert node.depth_test is False and node.depth_write is False


def test_fake_node_idempotent_guard():
    """The ``_ks_overlay_cfg`` guard must make a second call a no-op (no extra bin churn)."""
    node = _FakeAlwaysOnTopNode()
    configure_ks_overlay(node)
    first = list(node.bin_calls)
    configure_ks_overlay(node)  # already configured -> early return
    assert node.bin_calls == first, "second configure_ks_overlay call must be a no-op"


# ---------------------------------------------------------------------------
# Layer 2: REAL offscreen Ursina Text -- end-to-end Panda draw-order proof.
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


def test_real_text_overlay_bin_draw_order_is_110(ursina_app):
    """A real Ursina ``Text`` configured by ``configure_ks_overlay`` must resolve to the
    Panda3D ``fixed`` bin at draw order 110 -- proving the live render state, not just call
    ordering."""
    from ursina import Text

    label = Text(text="$5", billboard=True)
    configure_ks_overlay(label)

    assert label.getBinName() == "fixed", (
        f"overlay must be in the 'fixed' bin; got {label.getBinName()!r}"
    )
    assert label.getBinDrawOrder() == 110, (
        "overlay draw order must be 110 (> buildings@1 and instanced units@100); got "
        f"{label.getBinDrawOrder()}. A value of 0 means always_on_top clobbered the high "
        "bin -- it must be set AFTER always_on_top."
    )
