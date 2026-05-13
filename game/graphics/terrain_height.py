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


# ---------------------------------------------------------------------------
# WK54 Wave 2: Zone-influenced elevation
# ---------------------------------------------------------------------------

def apply_zone_elevation(
    heightmap: list[list[float]],
    grid_w: int,
    grid_h: int,
    tile_w: int,
    tile_h: int,
    castle_cx: int,
    castle_cy: int,
) -> None:
    """Apply zone-specific elevation biases to an existing heightmap.

    Modifies the heightmap in-place. Uses get_zone_blend() to smoothly
    transition elevation multipliers at zone boundaries.

    Called by World.generate_heightmap() after raw Perlin noise generation
    and before castle flattening, so zones sculpt the terrain before the
    castle plateau is carved.

    Parameters:
        heightmap: 2D list ``[gz][gx]`` of height values (modified in-place).
        grid_w, grid_h: heightmap grid dimensions (2*tile+1 per axis).
        tile_w, tile_h: map dimensions in tiles.
        castle_cx, castle_cy: castle center in tile coordinates.
    """
    import math as _math

    # Lazy import to avoid circular dependency (world_zones imports nothing
    # from graphics; graphics modules are imported after world is initialized).
    from game.world_zones import get_zone_blend

    import config as _cfg
    height_scale = float(getattr(_cfg, "TERRAIN_HEIGHT_SCALE", 8.0))

    for gz in range(grid_h):
        # Convert heightmap grid row to tile coordinate
        tile_y = min(tile_h - 1, gz // 2)
        for gx in range(grid_w):
            tile_x = min(tile_w - 1, gx // 2)

            zone, blend_weight = get_zone_blend(tile_x, tile_y, castle_cx, castle_cy)
            if zone is None:
                continue

            elevation_bias = zone.terrain_bias.get("elevation_bias", 1.0)
            if elevation_bias == 1.0:
                continue

            # Effective multiplier ramps from 1.0 (no effect) at the zone
            # border to the full bias deep inside the zone.
            effective = 1.0 + (elevation_bias - 1.0) * blend_weight
            h = heightmap[gz][gx] * effective
            heightmap[gz][gx] = max(0.0, min(height_scale, h))


# ---------------------------------------------------------------------------
# WK54 Wave 3: Terrain flattening for building/POI footprints
# ---------------------------------------------------------------------------

def flatten_footprint(
    heightmap: list[list[float]],
    grid_w: int,
    grid_h: int,
    center_tile_x: int,
    center_tile_y: int,
    width_tiles: int,
    height_tiles: int,
    margin_tiles: int = 2,
) -> None:
    """Flatten the heightmap under a building/POI footprint with smooth blend margin.

    Sets all heightmap samples within the footprint to the average height of
    the footprint center. Cosine-interpolates at the margin ring so the
    flattened area blends smoothly into surrounding terrain.

    Parameters:
        heightmap: 2D list ``[gz][gx]`` of heights (modified in-place).
        grid_w, grid_h: heightmap dimensions.
        center_tile_x, center_tile_y: top-left tile of the footprint.
        width_tiles, height_tiles: footprint size in tiles.
        margin_tiles: number of tiles for smooth blending (default 2).
    """
    import math as _math

    import config as _cfg
    water_level = float(getattr(_cfg, "TERRAIN_WATER_LEVEL", 1.0))

    # Convert tile coords to heightmap grid coords (heightmap is 2x tile resolution)
    fp_gx0 = center_tile_x * 2
    fp_gy0 = center_tile_y * 2
    fp_gx1 = (center_tile_x + width_tiles) * 2
    fp_gy1 = (center_tile_y + height_tiles) * 2

    # Compute the average height at the footprint center
    mid_gx = (fp_gx0 + fp_gx1) // 2
    mid_gy = (fp_gy0 + fp_gy1) // 2
    mid_gx = max(0, min(grid_w - 1, mid_gx))
    mid_gy = max(0, min(grid_h - 1, mid_gy))
    flat_h = heightmap[mid_gy][mid_gx]

    # Ensure flattened height does not go below water level
    flat_h = max(flat_h, water_level)

    margin_grid = margin_tiles * 2  # margin in grid units

    # Expanded rectangle including the margin ring
    ext_gx0 = fp_gx0 - margin_grid
    ext_gy0 = fp_gy0 - margin_grid
    ext_gx1 = fp_gx1 + margin_grid
    ext_gy1 = fp_gy1 + margin_grid

    # Clamp iteration bounds to valid grid range
    iter_gx0 = max(0, ext_gx0)
    iter_gy0 = max(0, ext_gy0)
    iter_gx1 = min(grid_w - 1, ext_gx1)
    iter_gy1 = min(grid_h - 1, ext_gy1)

    for gy in range(iter_gy0, iter_gy1 + 1):
        for gx in range(iter_gx0, iter_gx1 + 1):
            # Check if inside the footprint rectangle
            in_footprint = (fp_gx0 <= gx <= fp_gx1 and fp_gy0 <= gy <= fp_gy1)

            if in_footprint:
                heightmap[gy][gx] = flat_h
            else:
                # Margin ring: compute distance to nearest footprint edge in grid units
                dx = 0
                if gx < fp_gx0:
                    dx = fp_gx0 - gx
                elif gx > fp_gx1:
                    dx = gx - fp_gx1

                dy = 0
                if gy < fp_gy0:
                    dy = fp_gy0 - gy
                elif gy > fp_gy1:
                    dy = gy - fp_gy1

                dist = _math.sqrt(dx * dx + dy * dy)
                if dist <= 0:
                    heightmap[gy][gx] = flat_h
                elif dist < margin_grid:
                    # Cosine interpolation: 1.0 at footprint edge -> 0.0 at margin edge
                    t = dist / margin_grid
                    blend = 0.5 * (1.0 + _math.cos(t * _math.pi))
                    natural_h = heightmap[gy][gx]
                    blended = flat_h * blend + natural_h * (1.0 - blend)
                    heightmap[gy][gx] = max(water_level, blended)
                # else: outside margin ring, leave natural height unchanged
