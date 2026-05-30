"""Camera frustum-culling math for the Ursina renderer (WK88, Round B-5).

Pure-move of the camera lens / FOV-heuristic visible-rect query out of
``game/graphics/ursina_renderer.py``.  Both functions take the
``UrsinaRenderer`` instance as ``r`` and read its camera-state / cache fields
exactly as the original methods read ``self.*``.  The per-frame
``_frame_visible_rect`` cache stays on the renderer; only the rect-COMPUTE lives
here.  ``UrsinaRenderer`` keeps 1-line delegating wrappers (``_get_visible_tile_rect``
/ ``_entity_in_view``) that import this module lazily, so there is no import
cycle (this module never imports ``ursina_renderer`` at top level).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import config
from ursina import camera

if TYPE_CHECKING:
    from game.graphics.ursina_renderer import UrsinaRenderer


def get_visible_tile_rect(r: "UrsinaRenderer") -> tuple[int, int, int, int]:
    """Return (min_tx, min_ty, max_tx, max_ty) of tiles visible to the camera.

    WK58 Phase 2 (WK58-BUG-002): replaces the ``cam_y * 1.8`` heuristic that
    covered ~88% of the map with a real lens-frustum query.  Strategy:

    1.  Try Panda3D ``base.camLens.extrude(corner)`` for the four NDC corners
        (-1,-1), (1,-1), (-1,1), (1,1).  Transform near/far points to world
        space and intersect each ray with the y=0 ground plane.  Use the
        bounding box of the four hits, plus a small safety margin.
    2.  If any corner ray fails to hit the ground plane (e.g. shallow
        pitch, no ``base`` in headless tests, lens API mismatch), fall
        back to an FOV-based heuristic: pitch + ``camera.fov`` give the
        near/far ground-hit distances, ``aspect_ratio`` scales the
        horizontal extent.  This still produces a much tighter rect than
        the old ``cam_y * 1.8`` formula.
    3.  If anything else goes wrong, return the full map rect for that
        frame (matches old fallback contract).
    """
    import math as _math

    map_w = int(config.MAP_WIDTH)
    map_h = int(config.MAP_HEIGHT)
    full_rect = (0, 0, map_w - 1, map_h - 1)

    # --- Read camera state up front; bail to full_rect if anything missing.
    try:
        cam_pos = camera.world_position
        cam_fwd = camera.forward
        if cam_pos is None or cam_fwd is None:
            return full_rect
        cam_x = float(cam_pos.x)
        cam_y = float(cam_pos.y)
        cam_z = float(cam_pos.z)
        fwd_x = float(cam_fwd.x)
        fwd_y = float(cam_fwd.y)
        fwd_z = float(cam_fwd.z)
    except Exception:
        return full_rect

    if cam_y <= 0:
        return full_rect

    # --- Strategy 1: Panda3D lens extrusion of the four NDC corners.
    # Only runs in real Ursina runtime; headless tests fall through to
    # strategy 2 because ``application.base`` is None there.
    lens_rect: tuple[int, int, int, int] | None = None
    try:
        from panda3d.core import Point2, Point3
        from ursina import application as _ursina_app

        _base = getattr(_ursina_app, "base", None)
        lens = getattr(_base, "camLens", None) if _base is not None else None
        cam_node = getattr(_base, "cam", None) if _base is not None else None
        if lens is not None and cam_node is not None and _base is not None:
            cam_to_world = cam_node.get_mat(_base.render)
            xs: list[float] = []
            zs: list[float] = []
            lens_ok = True
            for sx, sy in ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)):
                np_near = Point3()
                np_far = Point3()
                if not lens.extrude(Point2(sx, sy), np_near, np_far):
                    lens_ok = False
                    break
                wn = cam_to_world.xform_point(np_near)
                wf = cam_to_world.xform_point(np_far)
                ry = float(wf.y) - float(wn.y)
                if abs(ry) < 1e-6:
                    lens_ok = False
                    break
                t = -float(wn.y) / ry
                if not _math.isfinite(t) or t <= 0:
                    # Ray points away from ground (e.g. corner aimed above
                    # horizon).  Fall back rather than guess.
                    lens_ok = False
                    break
                hx = float(wn.x) + t * (float(wf.x) - float(wn.x))
                hz = float(wn.z) + t * (float(wf.z) - float(wn.z))
                xs.append(hx)
                zs.append(hz)
            if lens_ok and xs and zs:
                margin = 6  # tiles
                min_tx = max(0, int(min(xs)) - margin)
                max_tx = min(map_w - 1, int(max(xs)) + margin)
                # world_z = -sim_y / SCALE = -tile_y (TILE_SIZE == SCALE).
                min_ty = max(0, int(-max(zs)) - margin)
                max_ty = min(map_h - 1, int(-min(zs)) + margin)
                if max_tx >= min_tx and max_ty >= min_ty:
                    lens_rect = (min_tx, min_ty, max_tx, max_ty)
    except Exception as _exc:
        lens_rect = None
        if not getattr(r, "_visible_rect_lens_warned", False):
            try:
                print(
                    "[ursina-cull] camera-lens extrusion unavailable; "
                    f"falling back to FOV heuristic ({_exc!r})",
                    flush=True,
                )
            except Exception:
                pass
            try:
                setattr(r, "_visible_rect_lens_warned", True)
            except Exception:
                pass

    if lens_rect is not None:
        return lens_rect

    # --- Strategy 2: FOV/pitch heuristic.  Self-contained (no self access).
    try:
        flen_sq = fwd_x * fwd_x + fwd_y * fwd_y + fwd_z * fwd_z
        if flen_sq < 1e-9 or fwd_y >= -0.01:
            return full_rect
        flen = _math.sqrt(flen_sq)
        nfx = fwd_x / flen
        nfy = fwd_y / flen
        nfz = fwd_z / flen

        t_ground = -cam_y / nfy
        if not _math.isfinite(t_ground) or t_ground <= 0:
            return full_rect
        ground_x = cam_x + t_ground * nfx
        ground_z = cam_z + t_ground * nfz
        center_tile_x = int(ground_x)
        center_tile_y = int(-ground_z)

        try:
            fov_deg = float(getattr(camera, "fov", 42.0))
        except Exception:
            fov_deg = 42.0
        if not (1.0 <= fov_deg <= 170.0):
            fov_deg = 42.0
        half_fov_v = _math.radians(fov_deg) * 0.5

        try:
            aspect = float(getattr(camera, "aspect_ratio", None) or (16.0 / 9.0))
        except Exception:
            aspect = 16.0 / 9.0
        if not (0.5 <= aspect <= 4.0):
            aspect = 16.0 / 9.0
        half_fov_h = _math.atan(_math.tan(half_fov_v) * aspect)

        horizontal_len = _math.sqrt(nfx * nfx + nfz * nfz)
        pitch = _math.atan2(abs(nfy), max(1e-3, horizontal_len))

        sin_pitch = _math.sin(pitch)
        look_dist = cam_y / max(0.05, sin_pitch)

        half_w = look_dist * _math.tan(half_fov_h)

        near_pitch = pitch + half_fov_v
        far_pitch = pitch - half_fov_v
        if near_pitch >= _math.pi * 0.5 - 0.01:
            near_dist = cam_y
        else:
            near_dist = cam_y / max(0.05, _math.sin(near_pitch))
        if far_pitch <= 0.05:
            far_dist = look_dist * 3.0
        else:
            far_dist = cam_y / max(0.05, _math.sin(far_pitch))
        half_along = max(8.0, (far_dist - near_dist) * 0.5)

        half_extent = max(half_w, half_along)

        margin = 8  # tiles of safety
        half = int(half_extent + margin)

        min_tx = max(0, center_tile_x - half)
        min_ty = max(0, center_tile_y - half)
        max_tx = min(map_w - 1, center_tile_x + half)
        max_ty = min(map_h - 1, center_tile_y + half)
        if max_tx < min_tx or max_ty < min_ty:
            return full_rect
        return (min_tx, min_ty, max_tx, max_ty)
    except Exception:
        return full_rect


def entity_in_view(r: "UrsinaRenderer", sim_x: float, sim_y: float) -> bool:
    """Check if an entity at sim pixel coords is within the cached visible rect."""
    tile_size = float(config.TILE_SIZE)
    tx = int(sim_x / tile_size)
    ty = int(sim_y / tile_size)
    rect = r._frame_visible_rect
    return rect[0] <= tx <= rect[2] and rect[1] <= ty <= rect[3]
