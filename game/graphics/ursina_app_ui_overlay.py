"""WK117: UI-overlay / HUD-texture cluster extracted from ursina_app.py (mixed
static+instance owner-arg pure-move, WK105 pattern). UrsinaApp keeps thin delegating
wrappers (3 @staticmethod, 2 owner-first). Byte-faithful move — no behavior change."""
from __future__ import annotations

import zlib
from typing import TYPE_CHECKING

import pygame
from ursina import Texture, camera, window

from game.display_manager import DisplayManager

if TYPE_CHECKING:  # one-way edge: ursina_app imports THIS module (lazily in wrappers)
    from game.graphics.ursina_app import UrsinaApp  # noqa: F401


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

    Previous path: pygame.tobytes -> _flip_surface_bytes_vertical (8MB memcpy) -> setRamImageAs
    New path:      pygame.tobytes -> setRamImageAs (raw, un-flipped)
    GPU handles the Pygame-vs-Panda3D Y-axis difference via texture_scale=(1,-1) + texture_offset=(0,1)
    on the ui_overlay entity, which is free (just different UV interpolation during rasterization).
    """
    scale = (camera.aspect_ratio, 1)
    if owner._last_ui_overlay_scale != scale:
        owner.ui_overlay.scale = scale
        owner._last_ui_overlay_scale = scale

    surf = owner.engine.screen
    sz = surf.get_size()

    import os as _os
    if _os.environ.get("KINGDOM_FPS_SLOWLOG", "") not in ("", "0") and not getattr(owner, "_hud_size_logged", False):
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
            # R5 phase 3: dirty-region upload — only upload changed rows to GPU.
            if owner._hud_prev_raw is not None and len(owner._hud_prev_raw) == len(raw_data):
                row_stride = sz[0] * 4
                dirty_min = sz[1]
                dirty_max = -1

                # Scan from top to find first dirty row
                for y in range(sz[1]):
                    offset = y * row_stride
                    if raw_data[offset:offset + row_stride] != owner._hud_prev_raw[offset:offset + row_stride]:
                        dirty_min = y
                        break

                if dirty_min < sz[1]:
                    # Scan from bottom to find last dirty row
                    for y in range(sz[1] - 1, dirty_min - 1, -1):
                        offset = y * row_stride
                        if raw_data[offset:offset + row_stride] != owner._hud_prev_raw[offset:offset + row_stride]:
                            dirty_max = y
                            break

                if dirty_max >= dirty_min:
                    sub_h = dirty_max - dirty_min + 1
                    if sub_h > int(sz[1] * 0.4):
                        # WK122: a near-full-height dirty band (top status row + bottom
                        # radar both change every frame) makes the PNMImage load_sub_image
                        # round-trip (~44ms) far slower than a single direct full upload.
                        # Use the proven full-texture path instead. Same final pixels.
                        panda_tex.setRamImageAs(raw_data, "RGBA")
                    else:
                        sub_offset = dirty_min * row_stride
                        sub_bytes = raw_data[sub_offset:sub_offset + sub_h * row_stride]

                        try:
                            from panda3d.core import PNMImage as _PNMImage

                            # Create temp texture holding only the dirty rows
                            temp_tex = PandaTexture()
                            temp_tex.setup2dTexture(sz[0], sub_h, PandaTexture.TUnsignedByte, PandaTexture.FRgba)
                            temp_tex.setRamImageAs(sub_bytes, "RGBA")

                            # Convert to PNMImage for load_sub_image
                            sub_pnm = _PNMImage()
                            temp_tex.store(sub_pnm)

                            # Panda3D texture y=0 is at BOTTOM. Our RAM is un-flipped (pygame top-down),
                            # so RAM row 0 maps to panda_y = height-1. The sub-image's top edge
                            # (dirty_min) maps to panda_y = height - dirty_min - sub_h.
                            panda_y = sz[1] - dirty_min - sub_h
                            owner._hud_composite_texture._texture.load_sub_image(sub_pnm, 0, panda_y)
                        except Exception:
                            # Fallback: full upload if load_sub_image fails
                            panda_tex.setRamImageAs(raw_data, "RGBA")
                # else: no dirty rows (fingerprint false positive) — skip upload
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
