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


def _billboard_y_offsets() -> dict[str, float]:
    """World-space Y offset from terrain to billboard center (matches UrsinaRenderer)."""
    import config

    us = float(getattr(config, "UNIT_SPRITE_PIXELS", config.TILE_SIZE)) / float(config.TILE_SIZE)
    unit = 0.62 * us
    wb = float(getattr(config, "URSINA_WORKER_BILLBOARD_BASE", 0.42)) * us
    wym = float(getattr(config, "URSINA_WORKER_BILLBOARD_Y_SCALE_MUL", 0.55))
    worker_y = wb * wym
    guard_y = 0.7 * us
    enemy = 0.5 * us
    return {
        "hero": unit * 0.5,
        "enemy": enemy * 0.5,
        "peasant": worker_y * 0.5,
        "guard": guard_y * 0.5,
        "tax_collector": worker_y * 0.5,
    }


def sim_xy_to_virtual_screen(
    sim_x: float,
    sim_y: float,
    billboard_y_offset: float,
    *,
    virtual_w: int,
    virtual_h: int,
) -> tuple[float, float] | None:
    """Project a sim entity position to virtual HUD pixels (same space as InputEvent.pos)."""
    from game.graphics.ursina_coords import sim_px_to_world_xz

    wx, wz = sim_px_to_world_xz(sim_x, sim_y)
    wy = billboard_y_offset
    try:
        from game.graphics.terrain_height import get_terrain_height, is_initialized

        if is_initialized():
            wy = get_terrain_height(wx, wz) + billboard_y_offset
    except Exception:
        pass

    try:
        from ursina import application, window
        from panda3d.core import Point2, Point3
    except Exception:
        return None

    base = getattr(application, "base", None)
    if base is None or not window:
        return None

    try:
        world_pt = Point3(wx, wy, wz)
        cam_pt = base.camera.getRelativePoint(base.render, world_pt)
        ndc = Point2()
        if not base.camLens.project(cam_pt, ndc):
            return None
    except Exception:
        return None

    win_w = max(1, int(window.size[0]))
    win_h = max(1, int(window.size[1]))
    px_x = (float(ndc.x) + 1.0) * 0.5 * win_w
    px_y = (1.0 - float(ndc.y)) * 0.5 * win_h
    vx = px_x * float(virtual_w) / float(win_w)
    vy = px_y * float(virtual_h) / float(win_h)
    return (vx, vy)


def pick_unit_at_screen(
    screen_pos: tuple[int, int],
    *,
    heroes=(),
    enemies=(),
    peasants=(),
    guards=(),
    tax_collector=None,
    virtual_w: int = 1920,
    virtual_h: int = 1080,
    pick_radius_px: float = 42.0,
) -> tuple[str, object] | None:
    """Return (kind, entity) for the closest live unit near ``screen_pos``.

    WK61-R4-BUG-002: floor-ray picking misses billboards on hills and at shallow
    camera angles; screen-space distance to projected sprite centers is reliable
    when clicking directly on visible units.
    """
    sx, sy = float(screen_pos[0]), float(screen_pos[1])
    r2 = float(pick_radius_px) * float(pick_radius_px)
    best: tuple[str, object] | None = None
    best_d2 = r2 + 1.0
    yoffs = _billboard_y_offsets()

    def _consider(kind: str, ent, sim_x: float, sim_y: float) -> None:
        nonlocal best, best_d2
        if ent is None or not getattr(ent, "is_alive", True):
            return
        if int(getattr(ent, "hp", 1) or 0) <= 0:
            return
        pt = sim_xy_to_virtual_screen(
            sim_x,
            sim_y,
            yoffs[kind],
            virtual_w=virtual_w,
            virtual_h=virtual_h,
        )
        if pt is None:
            return
        dx = pt[0] - sx
        dy = pt[1] - sy
        d2 = dx * dx + dy * dy
        if d2 < best_d2:
            best_d2 = d2
            best = (kind, ent)

    for h in heroes:
        _consider("hero", h, float(getattr(h, "x", 0.0)), float(getattr(h, "y", 0.0)))
    for e in enemies:
        _consider("enemy", e, float(getattr(e, "x", 0.0)), float(getattr(e, "y", 0.0)))
    for p in peasants:
        if bool(getattr(p, "is_inside_castle", False)):
            continue
        _consider("peasant", p, float(getattr(p, "x", 0.0)), float(getattr(p, "y", 0.0)))
    for g in guards:
        _consider("guard", g, float(getattr(g, "x", 0.0)), float(getattr(g, "y", 0.0)))
    if tax_collector is not None:
        _consider(
            "tax_collector",
            tax_collector,
            float(getattr(tax_collector, "x", 0.0)),
            float(getattr(tax_collector, "y", 0.0)),
        )
    return best
