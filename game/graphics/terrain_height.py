"""Terrain heightmap data reference and bilinear interpolation (WK53 Wave 2).

Single source of truth for terrain elevation. All entity Y-placement code
calls ``get_terrain_height(world_x, world_z)`` rather than sampling the
heightmap directly.

Module-level state is set by ``init_heightmap()`` during terrain setup and
cleared by ``clear_heightmap()`` on map change.
"""

from __future__ import annotations

# Module-level heightmap state --------------------------------------------------
_heightmap: list[list[float]] | None = None
_grid_w: int = 0
_grid_h: int = 0
_world_w: float = 0.0  # total world extent in Ursina X units
_world_h: float = 0.0  # total world extent in Ursina Z units (positive)
_world_origin_x: float = 0.0  # min world X of the map (usually 0)
_world_origin_z: float = 0.0  # min world Z of the map (most-negative Z)


def init_heightmap(
    heightmap: list[list[float]],
    grid_w: int,
    grid_h: int,
    world_w: float,
    world_h: float,
    world_origin_x: float = 0.0,
    world_origin_z: float = 0.0,
) -> None:
    """Store a reference to the world's heightmap for interpolation queries.

    Args:
        heightmap: 2D list ``[gz][gx]`` of height values.
        grid_w, grid_h: dimensions of the heightmap grid.
        world_w: total map extent along the Ursina X axis.
        world_h: total map extent along the Ursina Z axis (positive value).
        world_origin_x: X coordinate of grid index 0.
        world_origin_z: Z coordinate of grid index 0 (most-negative Z edge).
    """
    global _heightmap, _grid_w, _grid_h, _world_w, _world_h
    global _world_origin_x, _world_origin_z
    _heightmap = heightmap
    _grid_w = int(grid_w)
    _grid_h = int(grid_h)
    _world_w = float(world_w)
    _world_h = float(world_h)
    _world_origin_x = float(world_origin_x)
    _world_origin_z = float(world_origin_z)


def clear_heightmap() -> None:
    """Release the heightmap reference (e.g. on map change)."""
    global _heightmap, _grid_w, _grid_h, _world_w, _world_h
    _heightmap = None
    _grid_w = _grid_h = 0
    _world_w = _world_h = 0.0


def get_terrain_height(world_x: float, world_z: float) -> float:
    """Return the terrain elevation at the given world X/Z position.

    Uses bilinear interpolation between the four nearest heightmap grid points
    for smooth height values between grid samples.

    Returns 0.0 if the heightmap is not initialized or coords are out of bounds.
    """
    if _heightmap is None or _grid_w < 2 or _grid_h < 2:
        return 0.0

    # Convert world coordinates to continuous grid-space indices.
    # X axis: world_origin_x .. world_origin_x + world_w  ->  grid 0 .. grid_w-1
    # Z axis: world_origin_z .. world_origin_z + world_h  ->  grid 0 .. grid_h-1
    #
    # NOTE: the Ursina Z axis is negative (sim_px_to_world_xz negates Y), so
    # ``world_origin_z`` is the most-negative Z and grid row 0 maps there.
    if _world_w <= 0.0 or _world_h <= 0.0:
        return 0.0

    gx_f = (float(world_x) - _world_origin_x) / _world_w * (_grid_w - 1)
    gz_f = (float(world_z) - _world_origin_z) / _world_h * (_grid_h - 1)

    # Clamp to valid grid range
    gx_f = max(0.0, min(gx_f, _grid_w - 1.0))
    gz_f = max(0.0, min(gz_f, _grid_h - 1.0))

    gx0 = int(gx_f)
    gz0 = int(gz_f)
    gx1 = min(gx0 + 1, _grid_w - 1)
    gz1 = min(gz0 + 1, _grid_h - 1)

    fx = gx_f - gx0
    fz = gz_f - gz0

    # Bilinear interpolation
    h00 = _heightmap[gz0][gx0]
    h10 = _heightmap[gz0][gx1]
    h01 = _heightmap[gz1][gx0]
    h11 = _heightmap[gz1][gx1]

    h0 = h00 + (h10 - h00) * fx
    h1 = h01 + (h11 - h01) * fx
    return h0 + (h1 - h0) * fz


def is_initialized() -> bool:
    """Return True if a heightmap has been loaded."""
    return _heightmap is not None and _grid_w >= 2 and _grid_h >= 2
