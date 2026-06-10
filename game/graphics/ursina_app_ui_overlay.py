"""WK117: UI-overlay / HUD-texture cluster extracted from ursina_app.py (mixed
static+instance owner-arg pure-move, WK105 pattern). UrsinaApp keeps thin delegating
wrappers (3 @staticmethod, 2 owner-first).

Mythos S3 (hud-bgra-zero-copy): the changed-frame upload body now has TWO paths:

* **zero-copy (default, ``KINGDOM_HUD_ZEROCOPY`` != "0")** — the pygame SRCALPHA
  surface's native memory layout (masks 0xff0000/0xff00/0xff/0xff000000 = BGRA
  byte order, pitch == W*4) is byte-identical to Panda3D's F_rgba native BGRA RAM
  image (verified at runtime by ``_hud_zero_copy_layout_self_check`` — a tiny
  surface is converted through the legacy ``tobytes("RGBA")`` +
  ``setRamImageAs("RGBA")`` reference path and compared byte-for-byte against the
  surface's raw view). So the whole tobytes/PNMImage/load_sub_image conversion
  stack collapses to a direct memoryview copy: full-surface memcpy ~0.69ms at
  1920x1032 (vs 7.6ms tobytes + 7-11ms/band PNM round trips + a measured
  50.4ms setRamImageAs full fallback). ``KINGDOM_HUD_ZEROCOPY_BANDS=1`` selects
  the dirty-row-diff variant (diff vs the texture's own RAM image, band writes
  ~0.04ms/180 rows, >50%-dirty / >6-run fallback = the zero-copy FULL memcpy —
  never the 50ms swizzle).
* **legacy (``KINGDOM_HUD_ZEROCOPY=0``, or layout self-check mismatch)** — the
  WK123 multi-band tobytes/PNMImage path below, byte-identical pixels.

GUARDRAIL NOTE (11-fps-performance-guardrails.mdc): this SUPERSEDES the WK123
multi-band dirty upload's *conversion internals* — same final pixels, strictly
less CPU. The dirty-fingerprint early-out (``_hud_quick_fingerprint``) is
unchanged and still gates everything. GPU-side note: Panda marks the whole
texture modified for partial RAM writes too (load_sub_image also bumps
image_modified), so the per-changed-frame GPU DMA is the SAME as before — only
the CPU-side conversion cost changes (downward)."""
from __future__ import annotations

import os
import zlib
from typing import TYPE_CHECKING

import pygame
from ursina import Texture, camera, window

from game.display_manager import DisplayManager

if TYPE_CHECKING:  # one-way edge: ursina_app imports THIS module (lazily in wrappers)
    from game.graphics.ursina_app import UrsinaApp  # noqa: F401


# ---------------------------------------------------------------------------
# Mythos S3: zero-copy BGRA upload state + helpers
# ---------------------------------------------------------------------------

# Resolved once per process (env gate + layout self-check); reset hook for tests.
_ZEROCOPY_STATE: dict = {"checked": False, "enabled": False, "masks": None}

# Dirty-band variant tuning (mirrors the legacy WK123 constants).
_DIRTY_GAP_ROWS = 8
_DIRTY_FULL_FRACTION = 0.5
_DIRTY_MAX_RUNS = 6


def _hud_zero_copy_reset_for_tests() -> None:
    """Test hook: forget the cached env-gate + layout-check verdict."""
    _ZEROCOPY_STATE.update({"checked": False, "enabled": False, "masks": None})


def _hud_zero_copy_layout_self_check() -> tuple[bool, tuple | None]:
    """One-time runtime proof that the zero-copy assumption holds on this box.

    Builds a tiny SRCALPHA surface with distinct R/G/B/A values, converts it
    through the LEGACY reference path (``pygame.image.tobytes(..., "RGBA")`` ->
    ``setRamImageAs(..., "RGBA")``) and compares the Panda texture's native RAM
    bytes against the surface's raw memory view. Byte-equal => the direct
    memoryview copy is pixel-identical to the legacy conversion. Returns
    ``(ok, masks)`` where ``masks`` is the verified surface mask tuple (used to
    guard the live surface every frame). Any exception => ``(False, None)``.
    """
    try:
        from panda3d.core import Texture as PandaTexture

        test = pygame.Surface((4, 2), pygame.SRCALPHA, 32)
        px = [
            (255, 0, 0, 255), (0, 255, 0, 128), (0, 0, 255, 64), (10, 20, 30, 40),
            (200, 100, 50, 25), (1, 2, 3, 4), (255, 255, 255, 0), (0, 0, 0, 255),
        ]
        i = 0
        for y in range(2):
            for x in range(4):
                test.set_at((x, y), px[i])
                i += 1
        if test.get_bytesize() != 4 or test.get_pitch() != 4 * 4:
            return False, None
        native = bytes(memoryview(test.get_view("1")).cast("B"))
        raw = pygame.image.tobytes(test, "RGBA")
        ref = PandaTexture()
        ref.setup2dTexture(4, 2, PandaTexture.TUnsignedByte, PandaTexture.FRgba)
        ref.setRamImageAs(raw, "RGBA")
        if bytes(ref.get_ram_image()) != native:
            return False, None
        return True, test.get_masks()
    except Exception:
        return False, None


def _hud_zero_copy_active(surf: pygame.Surface) -> bool:
    """Env gate (``KINGDOM_HUD_ZEROCOPY``, default ON; "0" => legacy) + one-time
    layout self-check + per-call live-surface layout guard. Once disabled (env,
    mismatch, or runtime error) it stays disabled for the session."""
    st = _ZEROCOPY_STATE
    if not st["checked"]:
        st["checked"] = True
        if os.environ.get("KINGDOM_HUD_ZEROCOPY", "1").strip() == "0":
            st["enabled"] = False
        else:
            ok, masks = _hud_zero_copy_layout_self_check()
            st["enabled"] = bool(ok)
            st["masks"] = masks
            if not ok:
                print("[mythos] hud-zero-copy: DISABLED (layout mismatch)", flush=True)
            elif os.environ.get("KINGDOM_FPS_SLOWLOG", "") not in ("", "0"):
                print("[mythos] hud-zero-copy: enabled (BGRA layout verified)", flush=True)
    if not st["enabled"]:
        return False
    try:
        if surf.get_bytesize() == 4 and surf.get_masks() == st["masks"]:
            return True
    except Exception:
        pass
    # Live surface deviates from the verified layout — permanent legacy fallback.
    st["enabled"] = False
    print("[mythos] hud-zero-copy: DISABLED (layout mismatch)", flush=True)
    return False


def _hud_zero_copy_bands_enabled() -> bool:
    """``KINGDOM_HUD_ZEROCOPY_BANDS=1`` selects the dirty-row-diff band variant
    (default OFF: the candidate's primary path is the plain full memcpy, which is
    cheaper than diff+bands since Panda re-uploads the whole texture either way)."""
    return os.environ.get("KINGDOM_HUD_ZEROCOPY_BANDS", "0").strip() not in ("", "0")


def _hud_zero_copy_write_full(panda_tex, surf: pygame.Surface) -> None:
    """Full-surface direct memcpy: pygame native BGRA view -> Panda F_rgba RAM.

    ~0.69ms at 1920x1032 (measured) vs 50.4ms for the legacy setRamImageAs("RGBA")
    swizzle. Views are dropped before returning (get_view locks the surface)."""
    w, h = surf.get_size()
    expected = w * h * 4
    img = panda_tex.modify_ram_image()
    if len(img) != expected:
        img = panda_tex.make_ram_image()
    dst = memoryview(img).cast("B")
    src_proxy = surf.get_view("1")
    try:
        dst[:] = memoryview(src_proxy).cast("B")
    finally:
        del dst, src_proxy, img


def _hud_zero_copy_write_dirty_bands(panda_tex, surf: pygame.Surface, sz: tuple[int, int]) -> str:
    """Dirty-row-diff variant: numpy row diff (current surface view vs the
    texture's OWN RAM image = previous frame, so no 8.3MB ``_hud_prev_raw``
    retention), then direct memoryview band writes (~0.04ms per 180-row band).

    The >50%-dirty / >6-run fallback is the zero-copy FULL memcpy — NEVER the
    legacy 50ms setRamImageAs swizzle. Returns "clean" | "bands" | "full"
    (introspection for tests). Any failure falls back to the full memcpy so a
    partial frame is never left on screen."""
    w, h = int(sz[0]), int(sz[1])
    row_stride = w * 4
    expected = h * row_stride
    try:
        import numpy as _np

        ram = panda_tex.get_ram_image()
        if len(ram) != expected:
            _hud_zero_copy_write_full(panda_tex, surf)
            return "full"
        src_proxy = surf.get_view("1")
        try:
            src_mv = memoryview(src_proxy).cast("B")
            cur = _np.frombuffer(src_mv, dtype=_np.uint8).reshape(h, row_stride)
            prev = _np.frombuffer(memoryview(ram), dtype=_np.uint8).reshape(h, row_stride)
            dirty = _np.any(cur != prev, axis=1)
            if not bool(dirty.any()):
                # Fingerprint false positive — no modify_ram_image call, so the
                # texture is not marked dirty and no GPU re-upload happens.
                return "clean"
            d = dirty.astype(_np.int8)
            edges = _np.diff(_np.concatenate(([0], d, [0])))
            starts = _np.where(edges == 1)[0].tolist()
            ends = (_np.where(edges == -1)[0] - 1).tolist()
            merged: list[list[int]] = []
            for s, e in zip(starts, ends):
                if merged and s - merged[-1][1] - 1 < _DIRTY_GAP_ROWS:
                    merged[-1][1] = e
                else:
                    merged.append([s, e])
            total_dirty = int(d.sum())
            # Release every view of the texture RAM BEFORE modify_ram_image()
            # (avoids a copy-on-write of the 8MB array while views are live).
            del cur, prev, dirty, d, edges
            del ram
            if total_dirty > _DIRTY_FULL_FRACTION * h or len(merged) > _DIRTY_MAX_RUNS:
                dst = memoryview(panda_tex.modify_ram_image()).cast("B")
                try:
                    dst[:] = src_mv
                finally:
                    del dst
                return "full"
            dst = memoryview(panda_tex.modify_ram_image()).cast("B")
            try:
                for r0, r1 in merged:
                    a = r0 * row_stride
                    b = (r1 + 1) * row_stride
                    dst[a:b] = src_mv[a:b]
            finally:
                del dst
            return "bands"
        finally:
            del src_proxy
    except Exception:
        _hud_zero_copy_write_full(panda_tex, surf)
        return "full"


def _hud_quick_fingerprint(surf: pygame.Surface) -> int:
    """~0.5–0.8 ms @ 1080p: sample every 8th row plus top/bottom chrome rows.

    Stride 16 missed thin HUD deltas (~12px building bars; WK22). WK51 r6: stride 8 so
    header/footer chrome (pin, recall) cannot fall entirely between sampled rows.
    """
    w, h = surf.get_size()
    mv = memoryview(surf.get_view("1"))
    row = w * 4
    acc = zlib.crc32(b"")
    rows: set[int] = set(range(0, h, 8))
    for y in (0, 1, 2, h - 3, h - 2, h - 1):
        if 0 <= y < h:
            rows.add(y)
    for y in sorted(rows):
        a = y * row
        acc = zlib.crc32(mv[a : a + row], acc)
    return acc & 0xFFFFFFFF


def _hud_prefers_nearest_pixel_filter() -> bool:
    """WK22 R3: Pygame HUD is sized to the Ursina window — 1:1 texels; nearest keeps UI text sharp."""
    return True


def _sync_hud_texture_filter_mode(tex: Texture | None) -> None:
    if tex is None:
        return
    nearest = _hud_prefers_nearest_pixel_filter()
    try:
        # Panda/Ursina: None → nearest; True → linear (smoother when window is scaled).
        tex.filtering = None if nearest else True
    except Exception:
        try:
            tex.filtering = False if nearest else True
        except Exception:
            pass


def _refresh_ui_overlay_texture(owner: "UrsinaApp") -> None:
    """Upload pygame HUD to GPU — zero-copy Y-inversion via GPU texture coords (R5 round 3.5).

    GPU handles the Pygame-vs-Panda3D Y-axis difference via texture_scale=(1,-1) +
    texture_offset=(0,1) on the ui_overlay entity, which is free (just different UV
    interpolation during rasterization).

    Mythos S3 (hud-bgra-zero-copy): after the (unchanged) crc32 fingerprint
    early-out, the changed-frame conversion dispatches to the zero-copy BGRA
    memcpy path (default; see module docstring) or the legacy WK123 multi-band
    tobytes/PNMImage path (``KINGDOM_HUD_ZEROCOPY=0`` or layout mismatch). Both
    produce byte-identical texture content (proven by
    tests/test_mythos_hud_zerocopy.py).
    """
    scale = (camera.aspect_ratio, 1)
    if owner._last_ui_overlay_scale != scale:
        owner.ui_overlay.scale = scale
        owner._last_ui_overlay_scale = scale

    surf = owner.engine.screen
    sz = surf.get_size()

    if os.environ.get("KINGDOM_FPS_SLOWLOG", "") not in ("", "0") and not getattr(owner, "_hud_size_logged", False):
        owner._hud_size_logged = True
        print(f"[hud-size] surface={sz} camera_aspect={getattr(__import__('ursina').camera, 'aspect_ratio', '?')}", flush=True)

    try:
        quick = _hud_quick_fingerprint(surf)
    except Exception:
        quick = None

    force_upload = bool(getattr(owner.engine, "_ursina_hud_force_upload", False))
    if force_upload:
        setattr(owner.engine, "_ursina_hud_force_upload", False)

    if (
        not force_upload
        and quick is not None
        and owner._hud_composite_texture is not None
        and owner._hud_composite_size == sz
        and owner._hud_quick_sig is not None
        and quick == owner._hud_quick_sig
    ):
        return

    if _hud_zero_copy_active(surf):
        try:
            _refresh_ui_overlay_texture_zero_copy(owner, surf, sz, quick)
            return
        except Exception:
            # Never leave a partial frame: disable zero-copy for the session and
            # repaint fully through the legacy conversion path below.
            _ZEROCOPY_STATE["enabled"] = False
            print("[mythos] hud-zero-copy: DISABLED (runtime error; legacy path restored)", flush=True)

    _refresh_ui_overlay_texture_legacy(owner, surf, sz, quick)


def _refresh_ui_overlay_texture_zero_copy(
    owner: "UrsinaApp", surf: pygame.Surface, sz: tuple[int, int], quick: int | None
) -> None:
    """Zero-copy changed-frame upload (see module docstring). Pixel-identical to
    the legacy path; ``_hud_prev_raw`` is dropped (the band variant diffs against
    the texture's own RAM image instead of a retained 8.3MB bytes copy)."""
    # ``surf`` is unchanged since ``quick`` was computed (WK121 reuse). If the
    # fingerprint itself failed (quick None), store None so the next frame can
    # never false-early-out — same effective semantics as the legacy fallback sig.
    owner._hud_quick_sig = quick

    from panda3d.core import Texture as PandaTexture

    panda_tex = None
    if owner._hud_composite_texture is not None and owner._hud_composite_size == sz:
        cand = owner._hud_composite_texture._texture
        if int(cand.getXSize()) == int(sz[0]) and int(cand.getYSize()) == int(sz[1]):
            panda_tex = cand

    if panda_tex is None:
        # (Re)create the composite texture — mirrors the legacy creation branch,
        # with the setRamImageAs("RGBA") swizzle replaced by the direct memcpy.
        panda_tex = PandaTexture()
        panda_tex.setup2dTexture(sz[0], sz[1], PandaTexture.TUnsignedByte, PandaTexture.FRgba)
        _hud_zero_copy_write_full(panda_tex, surf)
        owner._hud_composite_texture = Texture(panda_tex)
        owner._hud_composite_size = sz
        owner.ui_overlay.texture = owner._hud_composite_texture
        # GPU-side Y-inversion: must be set AFTER texture assignment (Ursina may
        # reset texture properties during assignment).
        owner.ui_overlay.texture_scale = (1, -1)
        owner.ui_overlay.texture_offset = (0, 1)
        _sync_hud_texture_filter_mode(owner._hud_composite_texture)
        owner._hud_prev_raw = None
        return

    if _hud_zero_copy_bands_enabled():
        _hud_zero_copy_write_dirty_bands(panda_tex, surf, sz)
    else:
        _hud_zero_copy_write_full(panda_tex, surf)
    owner._hud_prev_raw = None


def _refresh_ui_overlay_texture_legacy(
    owner: "UrsinaApp", surf: pygame.Surface, sz: tuple[int, int], quick: int | None
) -> None:
    """Legacy WK123 conversion stack (tobytes + numpy row-diff + PNMImage band
    uploads + setRamImageAs full fallback) — byte-faithful to the pre-Mythos body;
    reached via ``KINGDOM_HUD_ZEROCOPY=0`` or the layout-mismatch fallback."""
    raw_data = pygame.image.tobytes(surf, "RGBA")

    # WK121: ``surf`` is unchanged since ``quick`` was computed at L74 (only read
    # by pygame.image.tobytes above), so reuse it instead of re-scanning — saves
    # one ~0.7ms crc32 pass on every changed frame. Identical stored value.
    if quick is not None:
        owner._hud_quick_sig = quick
    else:
        owner._hud_quick_sig = zlib.crc32(raw_data) & 0xFFFFFFFF

    # Skip Python-side byte flip; GPU handles Y-inversion via texture_scale=(1,-1).
    # This eliminates an 8MB memoryview reversal (~15-30ms at 1080p RGBA).

    from panda3d.core import Texture as PandaTexture

    if owner._hud_composite_texture is None or owner._hud_composite_size != sz:
        panda_tex = PandaTexture()
        panda_tex.setup2dTexture(sz[0], sz[1], PandaTexture.TUnsignedByte, PandaTexture.FRgba)
        panda_tex.setRamImageAs(raw_data, "RGBA")
        owner._hud_composite_texture = Texture(panda_tex)
        owner._hud_composite_size = sz
        owner.ui_overlay.texture = owner._hud_composite_texture
        # GPU-side Y-inversion: flip V coord so Pygame's top-down rows render correctly
        # in Panda3D's bottom-up coordinate system. Must be set AFTER texture assignment
        # since Ursina may reset texture properties during assignment.
        owner.ui_overlay.texture_scale = (1, -1)
        owner.ui_overlay.texture_offset = (0, 1)
        _sync_hud_texture_filter_mode(owner._hud_composite_texture)
        owner._hud_prev_raw = raw_data
    else:
        panda_tex = owner._hud_composite_texture._texture
        if int(panda_tex.getXSize()) != int(sz[0]) or int(panda_tex.getYSize()) != int(sz[1]):
            panda_tex = PandaTexture()
            panda_tex.setup2dTexture(sz[0], sz[1], PandaTexture.TUnsignedByte, PandaTexture.FRgba)
            panda_tex.setRamImageAs(raw_data, "RGBA")
            owner._hud_composite_texture = Texture(panda_tex)
            owner._hud_composite_size = sz
            owner.ui_overlay.texture = owner._hud_composite_texture
            # Re-apply GPU-side Y-inversion after texture reassignment
            owner.ui_overlay.texture_scale = (1, -1)
            owner.ui_overlay.texture_offset = (0, 1)
            _sync_hud_texture_filter_mode(owner._hud_composite_texture)
            owner._hud_prev_raw = raw_data
        else:
            # WK123: multi-band dirty-region upload. The HUD changes in MULTIPLE
            # separated regions every frame — the top status row (gold/wave) AND the
            # bottom-left radar (a dot per unit). The old single-band logic spanned
            # dirty_min..dirty_max, which for top+bottom deltas is nearly full height
            # and tripped the WK122 large-band cap into a full ~5.3MB upload. Here we
            # find the actual contiguous dirty row-runs with numpy and upload only those
            # bands (top run + bottom run, skipping the static middle). The union of the
            # uploaded runs is exactly the set of changed rows, so the on-screen texture
            # is pixel-identical to a full upload — just cheaper. Render-only.
            if owner._hud_prev_raw is not None and len(owner._hud_prev_raw) == len(raw_data):
                W, H = sz
                row_stride = W * 4

                def _upload_band(r0: int, r1: int) -> None:
                    """Upload rows [r0, r1] (inclusive) via load_sub_image. Same
                    mechanism the old single-band path used, factored out per run."""
                    from panda3d.core import PNMImage as _PNMImage

                    sub_h = r1 - r0 + 1
                    sub_offset = r0 * row_stride
                    sub_bytes = raw_data[sub_offset:sub_offset + sub_h * row_stride]

                    # Temp texture holding only this band's rows
                    temp_tex = PandaTexture()
                    temp_tex.setup2dTexture(W, sub_h, PandaTexture.TUnsignedByte, PandaTexture.FRgba)
                    temp_tex.setRamImageAs(sub_bytes, "RGBA")

                    # Convert to PNMImage for load_sub_image
                    sub_pnm = _PNMImage()
                    temp_tex.store(sub_pnm)

                    # Panda3D texture y=0 is at BOTTOM. Our RAM is un-flipped (pygame
                    # top-down), so RAM row 0 maps to panda_y = H-1. The band's top edge
                    # (r0) maps to panda_y = H - r0 - sub_h.
                    panda_y = H - r0 - sub_h
                    owner._hud_composite_texture._texture.load_sub_image(sub_pnm, 0, panda_y)

                try:
                    import numpy as _np

                    cur = _np.frombuffer(raw_data, dtype=_np.uint8).reshape(H, row_stride)
                    prev = _np.frombuffer(owner._hud_prev_raw, dtype=_np.uint8).reshape(H, row_stride)
                    dirty = _np.any(cur != prev, axis=1)  # bool[H], ~0.3-0.6ms

                    if not dirty.any():
                        # No change (fingerprint false positive) — skip upload entirely.
                        pass
                    else:
                        # Contiguous dirty row-runs: pad with a clean row each side, diff
                        # the int mask, +1 transition = run start, -1 = one past run end.
                        d = dirty.astype(_np.int8)
                        edges = _np.diff(_np.concatenate(([0], d, [0])))
                        starts = _np.where(edges == 1)[0]
                        ends = _np.where(edges == -1)[0] - 1  # inclusive last dirty row

                        # Merge runs separated by a small clean gap (< 8 rows) so we don't
                        # fragment into many tiny uploads.
                        GAP = 8
                        merged: list[list[int]] = []
                        for s, e in zip(starts.tolist(), ends.tolist()):
                            if merged and s - merged[-1][1] - 1 < GAP:
                                merged[-1][1] = e
                            else:
                                merged.append([s, e])

                        total_dirty = int(d.sum())
                        if total_dirty > 0.5 * H or len(merged) > 6:
                            # Too much changed (or too fragmented): a single direct full
                            # upload is cheaper than many sub-uploads. Same final pixels.
                            panda_tex.setRamImageAs(raw_data, "RGBA")
                        else:
                            try:
                                for r0, r1 in merged:
                                    _upload_band(r0, r1)
                            except Exception:
                                # On ANY band failure, fall back to a full upload so we
                                # never leave a partial frame on screen.
                                panda_tex.setRamImageAs(raw_data, "RGBA")
                except Exception:
                    # numpy/setup failure — safe full upload.
                    panda_tex.setRamImageAs(raw_data, "RGBA")
            else:
                # No previous data or size changed — full upload
                panda_tex.setRamImageAs(raw_data, "RGBA")

            owner._hud_prev_raw = raw_data


def _sync_headless_ui_canvas_to_window(owner: "UrsinaApp") -> None:
    """Poll Ursina ``window.size`` and resize ``engine.screen`` to match — fonts/layout rasterize at native pixels."""
    try:
        W, H = int(window.size[0]), int(window.size[1])
    except Exception:
        return
    if W < 32 or H < 32:
        return
    eng = owner.engine
    prev = (int(getattr(eng, "window_width", 0)), int(getattr(eng, "window_height", 0)))
    DisplayManager.apply_headless_ui_canvas_size(eng, W, H)
    cur = (int(eng.window_width), int(eng.window_height))
    owner.input_manager.set_virtual_screen_size(cur)
    if prev != cur:
        owner._hud_quick_sig = None
        owner._hud_composite_texture = None
        owner._hud_composite_size = None
        owner._hud_prev_raw = None
