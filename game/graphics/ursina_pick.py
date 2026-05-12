"""
Perspective ray vs ground plane for Ursina / WK20 map picking.

Coordinate system matches WK19: floor X/Z, Y up; sim pixels relate via ursina_renderer.SCALE.

WK53 R4: When a heightmap is loaded, iteratively refine the ray-plane intersection
to account for terrain elevation. Without this, clicking on heroes/buildings
sitting on hills misses because the y=0 intersection projects to the wrong XZ.
"""
from __future__ import annotations

from panda3d.core import CollisionRay, Point3, Vec3


def _intersect_ray_y_plane(ow, dw, y_level: float = 0.0):
    """Intersect a world-space ray with the horizontal plane at ``y_level``.

    Returns (x, z) or None if the ray is parallel or the hit is behind the camera.
    """
    if abs(dw.y) < 1e-8:
        return None
    t = (y_level - ow.y) / dw.y
    if t < 0:
        return None
    hit = ow + dw * t
    return (float(hit.x), float(hit.z))


def pick_world_xz_on_floor_y0() -> tuple[float, float] | None:
    """
    Cast a ray from the main camera through the current mouse position into the lens,
    intersect the terrain surface, return (world_x, world_z) in Ursina world space.

    WK53 R4: When a heightmap is active, performs iterative refinement (up to 3
    iterations) to converge on the terrain surface instead of the y=0 plane.
    This fixes hero/building click-selection on elevated terrain.

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

    # Initial intersection at y=0
    result = _intersect_ray_y_plane(ow, dw, 0.0)
    if result is None:
        return None

    # If heightmap is available, refine the intersection to account for terrain elevation.
    # Without this, heroes on hills are un-clickable because the y=0 hit projects to
    # a different XZ than where the hero visually appears on screen.
    try:
        from game.graphics.terrain_height import get_terrain_height, is_initialized
        if is_initialized():
            wx, wz = result
            for _ in range(3):
                h = get_terrain_height(wx, wz)
                refined = _intersect_ray_y_plane(ow, dw, h)
                if refined is None:
                    break
                wx, wz = refined
            result = (wx, wz)
    except Exception:
        pass

    return result
