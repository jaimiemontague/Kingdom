"""Mythos S2 Text font-cache patch regression (candidate ``text-font-cache-patch``).

Headless gates for ``game/graphics/ursina_text_font_cache.py``:

1. the patch applies (and is idempotent) against the installed ursina build;
2. after the patch, creating many ``Text`` labels no longer grows Panda's global
   model-path (stock appends ONE duplicate directory PER TEXT — measured 16->216
   dirs over ~200 Texts, the session-long degradation amplifier) — at most the
   single first-load append remains;
3. shared-font semantics are UNCHANGED from stock: every Text holds the same
   font object ``FontPool`` would return (FontPool already pools per filename),
   at the stock default pixels-per-unit — the headless half of the
   "pixel-identical" claim (same font object + same pixels-per-unit + same line
   height => identical glyph rendering);
4. text content still renders/mutates correctly through the patched path;
5. the guarded ``resolution`` setter: a same-value write is a safe no-op (the
   path every ``Text.__init__`` takes — without the guard the shared
   page-bearing font would hit Panda's ``get_num_pages()==0`` assert), and a
   genuinely different value still applies.

Skips cleanly when Ursina cannot boot offscreen.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

N_LABELS = 40


@pytest.fixture(scope="module")
def ursina_app():
    """Boot a real Ursina app offscreen; skip cleanly if it can't init."""
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
    """Flush ``scene._entities_marked_for_removal`` so destroyed Texts leave
    ``scene.entities`` NOW — not during a later test module's frame step (which
    would skew that module's baseline counts, e.g. the wk123 leak gates)."""
    try:
        app.step()
    except Exception:
        from ursina import scene

        for e in list(getattr(scene, "_entities_marked_for_removal", [])):
            if e in scene.entities:
                scene.entities.remove(e)
        scene._entities_marked_for_removal.clear()


def test_patch_applies_and_is_idempotent(ursina_app):
    from game.graphics.ursina_text_font_cache import (
        apply_text_font_cache_patch,
        is_text_font_cache_patch_applied,
    )

    assert apply_text_font_cache_patch() is True, (
        "font-cache patch failed to apply against this ursina build — the stock "
        "per-Text FontPool.load_font + model-path append spawn-hitch is back"
    )
    assert apply_text_font_cache_patch() is True  # idempotent re-apply
    assert is_text_font_cache_patch_applied() is True


def test_text_creation_does_not_grow_model_path_and_shares_font(ursina_app):
    from panda3d.core import FontPool, getModelPath
    from ursina import Text, destroy

    from game.graphics.ursina_text_font_cache import apply_text_font_cache_patch

    assert apply_text_font_cache_patch() is True

    created = []
    try:
        # Consume the one legitimate first-load fall-through (stock path: one
        # model-path append + FontPool.load_font + memoization).
        created.append(Text(text="warm"))
        n0 = getModelPath().getNumDirectories()

        for i in range(N_LABELS):
            created.append(Text(text=f"Hero {i}"))
        n1 = getModelPath().getNumDirectories()
        grown = n1 - n0

        print(f"\n[mythos font-cache] model-path dirs: {n0} -> {n1} (+{grown}) over {N_LABELS} Texts")
        # Stock ursina appends one duplicate directory PER TEXT (= +40 here).
        assert grown == 0, (
            f"model-path grew by {grown} dirs over {N_LABELS} Texts — the per-Text "
            "append_path is back (session-long Text-creation degradation amplifier)"
        )

        labels = created[1:]
        fonts = {id(getattr(t, "_font", None)) for t in labels}
        assert None not in {getattr(t, "_font", None) for t in labels}, "a Text has no font"
        assert len(fonts) == 1, "patched Texts must share ONE font object (stock FontPool semantics)"

        # The shared object is exactly the pooled font stock would use, at the
        # stock default resolution — headless pixel-identity proxy.
        pool_font = FontPool.load_font(Text.default_font)
        assert labels[0]._font.this == pool_font.this, (
            "patched Text font is not the FontPool-pooled object stock ursina shares"
        )
        assert abs(float(labels[0]._font.getPixelsPerUnit()) - float(Text.default_resolution)) < 1e-3

        # Content still renders/mutates through the patched path.
        assert labels[5].text == "Hero 5"
        labels[5].text = "$42"
        assert labels[5].text == "$42"
    finally:
        for t in created:
            try:
                destroy(t)
            except Exception:
                pass
        _step(ursina_app)


def test_resolution_guard_noops_same_value_and_applies_real_changes(ursina_app):
    from ursina import Text, destroy

    from game.graphics.ursina_text_font_cache import apply_text_font_cache_patch

    assert apply_text_font_cache_patch() is True

    t = Text(text="rg")
    try:
        font = t._font
        ppu0 = float(font.getPixelsPerUnit())

        # Same-value write: the path every Text.__init__ takes. Must be a safe
        # no-op on the shared page-bearing font (no Panda get_num_pages assert).
        t.resolution = ppu0
        assert abs(float(font.getPixelsPerUnit()) - ppu0) < 1e-6

        # A genuine change must still apply (guard clears pages first), then
        # restore the shared default for the rest of the process.
        t.resolution = ppu0 * 2.0
        assert abs(float(font.getPixelsPerUnit()) - ppu0 * 2.0) < 1e-3
        t.resolution = ppu0
        assert abs(float(font.getPixelsPerUnit()) - ppu0) < 1e-3
    finally:
        try:
            destroy(t)
        except Exception:
            pass
        _step(ursina_app)
