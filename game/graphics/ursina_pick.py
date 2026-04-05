"""
Perspective ray vs ground plane (y=0) for Ursina / WK20 map picking.

Coordinate system matches WK19: floor X/Z, Y up; sim pixels relate via ursina_renderer.SCALE.
"""
from __future__ import annotations

from panda3d.core import CollisionRay, Point3, Vec3


def pick_world_xz_on_floor_y0() -> tuple[float, float] | None:
    """
    Cast a ray from the main camera through the current mouse position into the lens,
    intersect the infinite plane y=0, return (world_x, world_z) in Ursina world space.

    Returns None if parallel to the plane, hit is behind the camera, or window missing.
    """
    from ursina import camera, mouse, window

    if not window:
        return None

    ray = CollisionRay()
    ray.set_from_lens(
        camera.lens_node,
        mouse.x * 2 / window.aspect_ratio,
        mouse.y * 2,
    )
    o = Point3(ray.get_origin())
    d = Vec3(ray.get_direction())
    mat = camera.get_net_transform().get_mat()
    ow = mat.xform_point(o)
    dw = mat.xform_vec(d)
    if abs(dw.y) < 1e-8:
        return None
    t = -ow.y / dw.y
    if t < 0:
        return None
    hit = ow + dw * t
    return (float(hit.x), float(hit.z))
