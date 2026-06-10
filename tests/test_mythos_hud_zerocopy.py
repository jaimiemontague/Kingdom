"""Mythos S3 (hud-bgra-zero-copy) — byte-equality proof + fallback-path tests.

The zero-copy HUD upload (game/graphics/ursina_app_ui_overlay.py) replaces the
legacy ``pygame.image.tobytes("RGBA")`` -> ``setRamImageAs("RGBA")`` /
PNMImage-band conversion stack with direct memoryview copies, relying on the
verified fact that a pygame SRCALPHA surface's native memory layout (BGRA,
pitch == W*4) is byte-identical to Panda3D's F_rgba native RAM image.

What this proves headlessly (SDL dummy video, no GPU needed — these are pure
CPU RAM-image comparisons):

* FULL path: ``_hud_zero_copy_write_full`` produces a texture RAM image
  byte-identical to the legacy ``setRamImageAs(tobytes(surf,"RGBA"), "RGBA")``
  conversion, on a synthetic surface with varied R/G/B/A values.
* BAND path: ``_hud_zero_copy_write_dirty_bands`` (the
  ``KINGDOM_HUD_ZEROCOPY_BANDS=1`` variant) detects exactly the changed row
  runs, writes only those bands, and the final texture is byte-identical to a
  full legacy conversion of the new frame. Unchanged frame => "clean" (no
  texture write at all); >50%-dirty and >6-run frames => the zero-copy FULL
  memcpy ("full"), NEVER the legacy 50ms setRamImageAs swizzle.
* LAYOUT SELF-CHECK: passes on this box; a simulated mismatch (monkeypatched
  self-check) logs ``[mythos] hud-zero-copy: DISABLED (layout mismatch)`` and
  routes ``_refresh_ui_overlay_texture`` through the LEGACY conversion path
  (proven by spying ``pygame.image.tobytes``), with byte-identical output.
* ENV GATE: ``KINGDOM_HUD_ZEROCOPY=0`` selects the legacy path.
* INTEGRATION: a fake owner driven through the real
  ``_refresh_ui_overlay_texture`` produces legacy-identical texture bytes in
  both zero-copy modes, and the crc32 fingerprint early-out still fires on an
  unchanged frame (no second write).
"""
from __future__ import annotations

import os
import random
from types import SimpleNamespace

import pytest

# Headless: never bring up a real display.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()

from panda3d.core import Texture as PandaTexture  # noqa: E402

import game.graphics.ursina_app_ui_overlay as ui_overlay  # noqa: E402


W, H = 64, 80


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_surface(seed: int = 42, w: int = W, h: int = H) -> pygame.Surface:
    """SRCALPHA surface with varied R/G/B/A (incl. alpha 0 and 255 extremes)."""
    surf = pygame.Surface((w, h), pygame.SRCALPHA, 32)
    rng = random.Random(seed)
    for y in range(h):
        for x in range(w):
            surf.set_at(
                (x, y),
                (rng.randrange(256), rng.randrange(256), rng.randrange(256), rng.randrange(256)),
            )
    return surf


def _legacy_texture_bytes(surf: pygame.Surface) -> bytes:
    """The legacy reference conversion: tobytes('RGBA') -> setRamImageAs('RGBA')."""
    w, h = surf.get_size()
    raw = pygame.image.tobytes(surf, "RGBA")
    tex = PandaTexture()
    tex.setup2dTexture(w, h, PandaTexture.TUnsignedByte, PandaTexture.FRgba)
    tex.setRamImageAs(raw, "RGBA")
    return bytes(tex.get_ram_image())


def _fresh_texture(w: int = W, h: int = H) -> PandaTexture:
    tex = PandaTexture()
    tex.setup2dTexture(w, h, PandaTexture.TUnsignedByte, PandaTexture.FRgba)
    return tex


def _set_rows(surf: pygame.Surface, rows, color=(1, 2, 3, 4)) -> None:
    for y in rows:
        for x in range(surf.get_width()):
            surf.set_at((x, y), color)


@pytest.fixture(autouse=True)
def _reset_zerocopy_state(monkeypatch: pytest.MonkeyPatch):
    """Each test starts with a fresh env-gate/layout-check verdict."""
    monkeypatch.delenv("KINGDOM_HUD_ZEROCOPY", raising=False)
    monkeypatch.delenv("KINGDOM_HUD_ZEROCOPY_BANDS", raising=False)
    monkeypatch.delenv("KINGDOM_FPS_SLOWLOG", raising=False)
    ui_overlay._hud_zero_copy_reset_for_tests()
    yield
    ui_overlay._hud_zero_copy_reset_for_tests()


# ---------------------------------------------------------------------------
# (1) layout self-check
# ---------------------------------------------------------------------------
def test_layout_self_check_passes_on_this_box() -> None:
    """The decisive measured finding: pygame SRCALPHA native bytes == Panda
    F_rgba native RAM bytes. The runtime self-check must verify it here."""
    ok, masks = ui_overlay._hud_zero_copy_layout_self_check()
    assert ok is True, "layout self-check failed — zero-copy assumption broken on this box"
    assert masks is not None and len(masks) == 4


def test_zero_copy_active_by_default() -> None:
    surf = _make_surface()
    assert ui_overlay._hud_zero_copy_active(surf) is True


def test_env_zero_selects_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KINGDOM_HUD_ZEROCOPY", "0")
    ui_overlay._hud_zero_copy_reset_for_tests()
    surf = _make_surface()
    assert ui_overlay._hud_zero_copy_active(surf) is False


def test_layout_mismatch_disables_and_logs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Simulated exotic SDL layout: self-check fails => permanent legacy fallback
    + the required disable log line."""
    monkeypatch.setattr(
        ui_overlay, "_hud_zero_copy_layout_self_check", lambda: (False, None)
    )
    ui_overlay._hud_zero_copy_reset_for_tests()
    surf = _make_surface()
    assert ui_overlay._hud_zero_copy_active(surf) is False
    out = capsys.readouterr().out
    assert "[mythos] hud-zero-copy: DISABLED (layout mismatch)" in out


def test_live_surface_layout_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """A live surface whose masks differ from the verified ones must disable
    zero-copy (per-call guard, not just the init self-check)."""
    surf = _make_surface()
    assert ui_overlay._hud_zero_copy_active(surf) is True
    odd = pygame.Surface((8, 8))  # no per-pixel alpha -> different masks/bytesize
    assert ui_overlay._hud_zero_copy_active(odd) is False
    # ...and it stays disabled for the session.
    assert ui_overlay._hud_zero_copy_active(surf) is False


# ---------------------------------------------------------------------------
# (2) FULL path byte-equality
# ---------------------------------------------------------------------------
def test_full_write_matches_legacy_conversion() -> None:
    surf = _make_surface(seed=7)
    tex = _fresh_texture()
    ui_overlay._hud_zero_copy_write_full(tex, surf)
    assert bytes(tex.get_ram_image()) == _legacy_texture_bytes(surf)
    # Surface must not be left locked (views released).
    assert not surf.get_locked()
    surf.set_at((0, 0), (9, 9, 9, 9))  # would raise if a view still locked it


# ---------------------------------------------------------------------------
# (3) BAND path byte-equality + routing
# ---------------------------------------------------------------------------
def test_band_write_two_runs_matches_legacy() -> None:
    base = _make_surface(seed=11)
    tex = _fresh_texture()
    ui_overlay._hud_zero_copy_write_full(tex, base)

    cur = base.copy()
    _set_rows(cur, (5, 6, 7, 8, 30, 31, 32))
    mode = ui_overlay._hud_zero_copy_write_dirty_bands(tex, cur, (W, H))
    assert mode == "bands", f"expected band path, got {mode!r}"
    assert bytes(tex.get_ram_image()) == _legacy_texture_bytes(cur)
    assert not cur.get_locked()


def test_band_write_clean_frame_skips_upload() -> None:
    base = _make_surface(seed=13)
    tex = _fresh_texture()
    ui_overlay._hud_zero_copy_write_full(tex, base)
    before = bytes(tex.get_ram_image())

    mode = ui_overlay._hud_zero_copy_write_dirty_bands(tex, base.copy(), (W, H))
    assert mode == "clean"
    assert bytes(tex.get_ram_image()) == before


def test_band_write_over_half_dirty_takes_zero_copy_full() -> None:
    """The >50%-dirty fallback goes through the zero-copy FULL memcpy (kills the
    50ms setRamImageAs hitch class) and stays byte-identical."""
    base = _make_surface(seed=17)
    tex = _fresh_texture()
    ui_overlay._hud_zero_copy_write_full(tex, base)

    cur = base.copy()
    _set_rows(cur, range(0, 45))  # 45/80 rows > 50%
    mode = ui_overlay._hud_zero_copy_write_dirty_bands(tex, cur, (W, H))
    assert mode == "full"
    assert bytes(tex.get_ram_image()) == _legacy_texture_bytes(cur)


def test_band_write_fragmented_takes_zero_copy_full() -> None:
    """>6 separated dirty runs (the hero-spawn scatter pattern) also goes to the
    zero-copy full memcpy."""
    base = _make_surface(seed=19)
    tex = _fresh_texture()
    ui_overlay._hud_zero_copy_write_full(tex, base)

    cur = base.copy()
    _set_rows(cur, (0, 9, 18, 27, 36, 45, 54))  # 7 runs, gaps of 8 clean rows
    mode = ui_overlay._hud_zero_copy_write_dirty_bands(tex, cur, (W, H))
    assert mode == "full"
    assert bytes(tex.get_ram_image()) == _legacy_texture_bytes(cur)


# ---------------------------------------------------------------------------
# (4) integration through the real _refresh_ui_overlay_texture
# ---------------------------------------------------------------------------
def _fake_owner(surf: pygame.Surface):
    return SimpleNamespace(
        _last_ui_overlay_scale=None,
        ui_overlay=SimpleNamespace(),
        engine=SimpleNamespace(screen=surf),
        _hud_composite_texture=None,
        _hud_composite_size=None,
        _hud_quick_sig=None,
        _hud_prev_raw=None,
    )


@pytest.fixture()
def _stub_camera(monkeypatch: pytest.MonkeyPatch):
    """ursina's camera.aspect_ratio needs a window; stub it for the headless run."""
    monkeypatch.setattr(ui_overlay, "camera", SimpleNamespace(aspect_ratio=1.5))


def _owner_tex_bytes(owner) -> bytes:
    return bytes(owner._hud_composite_texture._texture.get_ram_image())


def test_refresh_zero_copy_full_mode_end_to_end(_stub_camera, monkeypatch) -> None:
    surf = _make_surface(seed=23)
    owner = _fake_owner(surf)

    calls = {"full": 0}
    real_full = ui_overlay._hud_zero_copy_write_full

    def counting_full(tex, s):
        calls["full"] += 1
        return real_full(tex, s)

    monkeypatch.setattr(ui_overlay, "_hud_zero_copy_write_full", counting_full)

    ui_overlay._refresh_ui_overlay_texture(owner)
    assert owner._hud_composite_texture is not None
    assert owner._hud_composite_size == (W, H)
    assert calls["full"] == 1
    assert _owner_tex_bytes(owner) == _legacy_texture_bytes(surf)
    # zero-copy drops the retained raw copy (band variant diffs vs texture RAM).
    assert owner._hud_prev_raw is None
    # GPU Y-flip properties preserved.
    assert owner.ui_overlay.texture_scale == (1, -1)
    assert owner.ui_overlay.texture_offset == (0, 1)

    # Unchanged frame: the crc32 fingerprint early-out must fire (no new write).
    ui_overlay._refresh_ui_overlay_texture(owner)
    assert calls["full"] == 1, "fingerprint early-out did not fire on unchanged frame"

    # Changed frame: full memcpy again, byte-identical to legacy.
    _set_rows(surf, (10, 11), color=(200, 150, 100, 50))
    ui_overlay._refresh_ui_overlay_texture(owner)
    assert calls["full"] == 2
    assert _owner_tex_bytes(owner) == _legacy_texture_bytes(surf)


def test_refresh_zero_copy_band_mode_end_to_end(_stub_camera, monkeypatch) -> None:
    monkeypatch.setenv("KINGDOM_HUD_ZEROCOPY_BANDS", "1")
    surf = _make_surface(seed=29)
    owner = _fake_owner(surf)

    ui_overlay._refresh_ui_overlay_texture(owner)  # creation frame (full write)
    assert _owner_tex_bytes(owner) == _legacy_texture_bytes(surf)

    # NOTE: rows are chosen inside the quick-fingerprint's sampled coverage for
    # this 64x80 geometry (the fingerprint slices a 4-byte-pixel memoryview, so
    # its samples cover 4-row blocks every 32 rows: 0-11, 32-35, 64-67). Two
    # separated runs => the dirty-band path, both visible to the fingerprint.
    _set_rows(surf, (32, 33, 34), color=(120, 30, 60, 200))
    _set_rows(surf, (64, 65, 66), color=(10, 220, 90, 128))
    ui_overlay._refresh_ui_overlay_texture(owner)  # band frame
    assert _owner_tex_bytes(owner) == _legacy_texture_bytes(surf)


def test_refresh_layout_mismatch_routes_to_legacy(
    _stub_camera, monkeypatch, capsys
) -> None:
    """Simulated mismatched layout => the refresh must run the LEGACY conversion
    (pygame.image.tobytes called) and still produce the correct texture bytes."""
    monkeypatch.setattr(
        ui_overlay, "_hud_zero_copy_layout_self_check", lambda: (False, None)
    )
    ui_overlay._hud_zero_copy_reset_for_tests()

    surf = _make_surface(seed=31)
    owner = _fake_owner(surf)

    tobytes_calls = {"n": 0}
    real_tobytes = pygame.image.tobytes

    def counting_tobytes(*a, **kw):
        tobytes_calls["n"] += 1
        return real_tobytes(*a, **kw)

    monkeypatch.setattr(pygame.image, "tobytes", counting_tobytes)

    ui_overlay._refresh_ui_overlay_texture(owner)
    assert tobytes_calls["n"] >= 1, "legacy conversion path was not used"
    assert "[mythos] hud-zero-copy: DISABLED (layout mismatch)" in capsys.readouterr().out
    monkeypatch.setattr(pygame.image, "tobytes", real_tobytes)
    assert _owner_tex_bytes(owner) == _legacy_texture_bytes(surf)
    # Legacy path retains the raw copy for its band diff.
    assert owner._hud_prev_raw is not None


def test_refresh_env_disabled_routes_to_legacy(_stub_camera, monkeypatch) -> None:
    monkeypatch.setenv("KINGDOM_HUD_ZEROCOPY", "0")
    ui_overlay._hud_zero_copy_reset_for_tests()

    surf = _make_surface(seed=37)
    owner = _fake_owner(surf)

    tobytes_calls = {"n": 0}
    real_tobytes = pygame.image.tobytes

    def counting_tobytes(*a, **kw):
        tobytes_calls["n"] += 1
        return real_tobytes(*a, **kw)

    monkeypatch.setattr(pygame.image, "tobytes", counting_tobytes)
    ui_overlay._refresh_ui_overlay_texture(owner)
    monkeypatch.setattr(pygame.image, "tobytes", real_tobytes)

    assert tobytes_calls["n"] >= 1, "KINGDOM_HUD_ZEROCOPY=0 must select the legacy path"
    assert _owner_tex_bytes(owner) == _legacy_texture_bytes(surf)
