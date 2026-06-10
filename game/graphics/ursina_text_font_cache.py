"""Ursina ``Text`` font-cache monkeypatch (Mythos S2 spawn-hitch: text-font-cache-patch).

ROOT CAUSE (measured; .cursor/plans/mythos_lag_fix_candidates.json, rank 3):
every ``ursina.Text()`` construction runs ``Text.font_setter``
(site-packages/ursina/text.py:266-287) which

1. appends the font's directory to Panda3D's GLOBAL model-path AGAIN on EVERY
   Text — the path was measured growing 16 -> 216 dirs over ~200 Texts, taxing
   every later font/model lookup (a session-long time-degradation amplifier),
   and
2. re-runs ``FontPool.load_font`` (73% of the measured 5.25-21 ms per-Text
   cost) and then ``font.clear()`` — wiping the shared glyph cache so glyphs
   re-render from scratch.

Every unit spawn creates 1-2 Text labels (name/gold via
``ursina_unit_overlays``), so a 6-enemy wave entering the viewport costs
~35-40 ms in ONE frame. With this patch, Text creation was measured at
~0.27 ms median (22x) and the full hero-spawn render bundle drops
6.6 ms -> 0.84 ms.

THE PATCH — class-property replacement. Attribute-level patching of
``Text.font_setter`` does NOT work because ursina's
``generate_properties_for_class`` bakes ``property`` objects onto the class at
decoration time; replacing the ``property`` itself does work (verified by the
candidate's measurement session).

* ``Text.font`` setter: a ``{font_name: font_object}`` memo. Only the FIRST
  load of each font name falls through to the stock setter (one model-path
  append + one ``FontPool.load_font`` + the stock ``clear()``); every later
  Text reuses the memoized font object directly.
* ``Text.resolution`` setter: no-ops when the new value equals the font's
  current ``getPixelsPerUnit()``. REQUIRED companion: ``Text.__init__`` always
  writes ``self.resolution = Text.default_resolution``, and without the stock
  per-Text ``font.clear()`` the shared font carries rendered glyph pages, so
  the redundant ``setPixelsPerUnit`` hits Panda's ``get_num_pages()==0``
  assert (reproduced by the candidate). A genuinely different value still
  applies (we ``clear()`` first, exactly what stock relied on).

WHY PIXEL-IDENTICAL: ``FontPool`` is a Panda-level pool that ALREADY returns
the same font object for the same filename — stock Ursina shares one font
object across all Texts today. The patch only removes (a) the duplicate
model-path appends (the directory is already on the path from the first load
AND from ursina/application.py:48), (b) redundant ``load_font`` round trips,
(c) the ``font.clear()`` glyph-cache wipe (glyphs lazily re-render with
identical geometry/texture either way), and (d) same-value
``setPixelsPerUnit``/``setLineHeight`` writes. Same font object + same
pixels-per-unit + same line height => byte-identical label rendering.

Applied once at app boot (``UrsinaApp.__init__`` BEFORE ``Ursina()``, so even
the window fps-counter Text populates the memo). Guarded: if the ursina
internals changed shape (upgrade renamed the property, etc.) the patch leaves
stock behavior fully in place and returns False.
"""
from __future__ import annotations

# font name (e.g. 'OpenSans-Regular.ttf') -> loaded Panda font object.
# Module-level so repeated apply calls / multiple Texts share one memo.
_FONT_MEMO: dict[str, object] = {}

_PATCH_FLAG = "_ks_font_cache_patched"


def is_text_font_cache_patch_applied() -> bool:
    """True when :func:`apply_text_font_cache_patch` already ran successfully."""
    try:
        import ursina.text as utext

        return bool(getattr(utext.Text, _PATCH_FLAG, False))
    except Exception:
        return False


def apply_text_font_cache_patch() -> bool:
    """Replace ``Text.font`` / ``Text.resolution`` class properties with cached variants.

    Idempotent; returns True when the patch is (already) active, False when the
    ursina internals did not match the expected shape (stock behavior is then
    left untouched — safe fallback for ursina upgrades).
    """
    try:
        import ursina.text as utext

        text_cls = utext.Text
        if getattr(text_cls, _PATCH_FLAG, False):
            return True

        font_prop = text_cls.__dict__.get("font")
        res_prop = text_cls.__dict__.get("resolution")
        if not isinstance(font_prop, property) or not isinstance(res_prop, property):
            return False
        stock_font_setter = font_prop.fset
        if stock_font_setter is None or font_prop.fget is None or res_prop.fget is None:
            return False

        def _cached_font_setter(self, value):
            font = _FONT_MEMO.get(value)
            if font is None:
                # First load of this font name: full stock path (file search +
                # ONE model-path append + FontPool.load_font + stock clear()).
                stock_font_setter(self, value)
                loaded = getattr(self, "_font", None)
                if loaded is not None:
                    _FONT_MEMO[value] = loaded
                return
            # Memo hit: reuse the shared font object (FontPool would return the
            # SAME object anyway — we skip the lookup, the duplicate model-path
            # append, and the glyph-cache clear()).
            self._font = font
            try:
                # Stock parity: font_setter re-applies the Text's line height
                # (same value in practice; FontPool sharing means stock mutated
                # the shared font here too).
                font.setLineHeight(self.line_height)
            except Exception:
                pass
            # Stock parity: re-render existing text if the font changes after
            # construction (during __init__ no text exists yet -> no-op).
            if getattr(self, "text", ""):
                self.text = self.raw_text

        def _guarded_resolution_setter(self, value):
            font = getattr(self, "_font", None)
            if font is None:
                return
            try:
                if abs(float(font.getPixelsPerUnit()) - float(value)) < 1e-4:
                    return  # redundant write — the per-Text __init__ default path
                # Genuine resolution change on a font with rendered glyph pages:
                # drop the pages first or Panda asserts get_num_pages()==0.
                font.clear()
            except Exception:
                pass
            font.setPixelsPerUnit(value)

        text_cls.font = property(font_prop.fget, _cached_font_setter, font_prop.fdel)
        text_cls.resolution = property(res_prop.fget, _guarded_resolution_setter, res_prop.fdel)
        setattr(text_cls, _PATCH_FLAG, True)
        return True
    except Exception:
        return False
