"""One-shot world generation (terrain + heightmap).

WK86 Round B-3: extracted VERBATIM from ``game/world.py`` using the proven
pure-move pattern. Each function takes the ``World`` instance as ``world`` and
mutates it in place; ``World.generate_terrain`` / ``World.generate_heightmap`` /
``World.flatten_building_footprints`` remain as 1-line delegating wrappers so all
existing callers (``World.__init__``, ``setup_initial_state``, tools/tests) are
unchanged.

Import-cycle safety: ``World`` is imported only under ``TYPE_CHECKING``. The
``TileType`` symbol (defined at module level in ``game.world``) is imported lazily
inside the functions. ``game.world`` imports this module only lazily (inside the
wrappers), so there is no module-top cycle.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from game.sim.determinism import get_rng
from game.world_zones import get_zone_blend

try:
    from noise import pnoise2 as _pnoise2
except ImportError:
    _pnoise2 = None

if TYPE_CHECKING:
    from game.world import World


def generate_terrain(world) -> None:
    """Generate a simple procedural terrain."""
    from game.world import TileType
    # Add some water (a pond/lake)
    rng = getattr(world, "rng", get_rng("world_gen"))
    lake_x = rng.randint(world.width // 4, world.width * 3 // 4)
    lake_y = rng.randint(world.height // 4, world.height * 3 // 4)
    # Scale lake size with map size so large maps don't look empty.
    base = max(3, min(world.width, world.height) // 25)
    lake_radius = rng.randint(base, base + 4)

    for y in range(world.height):
        for x in range(world.width):
            # Create lake
            dist = ((x - lake_x) ** 2 + (y - lake_y) ** 2) ** 0.5
            if dist < lake_radius:
                world.tiles[y][x] = TileType.WATER

    # WK44: clustered forests (not per-tile independent noise)
    # Deterministic blobs: pick a handful of centers then spray points with jitter.
    # Target: noticeably forested maps (avoid barren look) while leaving plenty of buildable space.
    area = int(world.width) * int(world.height)
    cluster_count = max(22, area // 900)
    castle_cx, castle_cy = world.width // 2, world.height // 2
    for _ in range(int(cluster_count)):
        cx = rng.randint(0, world.width - 1)
        cy = rng.randint(0, world.height - 1)
        if world.tiles[cy][cx] == TileType.WATER:
            continue
        radius = rng.randint(5, 12)
        # WK54: zone-influenced tree density
        zone, blend = get_zone_blend(cx, cy, castle_cx, castle_cy)
        tree_mult = 1.0
        if zone is not None:
            tree_mult = 1.0 + (zone.terrain_bias.get("tree_density", 1.0) - 1.0) * blend
        points = int(rng.randint(90, 220) * tree_mult)
        for _k in range(points):
            dx = rng.randint(-radius, radius)
            dy = rng.randint(-radius, radius)
            x = cx + dx
            y = cy + dy
            if not (0 <= x < world.width and 0 <= y < world.height):
                continue
            if world.tiles[y][x] == TileType.WATER:
                continue
            # Slight falloff to keep clusters organic.
            if (dx * dx + dy * dy) > (radius * radius):
                continue
            if rng.random() < 0.92:
                world.tiles[y][x] = TileType.TREE

    # Light background sprinkle to connect clusters (keeps edges from feeling empty).
    # WK54: zone-influenced sprinkle probability
    for y in range(world.height):
        for x in range(world.width):
            if world.tiles[y][x] != TileType.GRASS:
                continue
            zone_s, blend_s = get_zone_blend(x, y, castle_cx, castle_cy)
            sprinkle_mult = 1.0
            if zone_s is not None:
                sprinkle_mult = 1.0 + (zone_s.terrain_bias.get("tree_density", 1.0) - 1.0) * blend_s
            if rng.random() < 0.045 * sprinkle_mult:
                world.tiles[y][x] = TileType.TREE

    # Create paths from edges to center
    center_x, center_y = world.width // 2, world.height // 2

    # Horizontal path
    for x in range(world.width):
        world.tiles[center_y][x] = TileType.PATH
        if center_y + 1 < world.height:
            world.tiles[center_y + 1][x] = TileType.PATH

    # Vertical path
    for y in range(world.height):
        world.tiles[y][center_x] = TileType.PATH
        if center_x + 1 < world.width:
            world.tiles[y][center_x + 1] = TileType.PATH

    # WK45: trim excess TREE tiles AFTER carving paths (paths erase lots of trees along the cross).
    # Target ~600 visible forest tiles at match start; sapling spawning uses a separate total cap.
    # WK54: scale tree cap proportionally with map area (750 for 150x150, ~2083 for 250x250).
    max_starting_trees = max(750, int(area * 750 / (150 * 150)))
    tree_tiles: list[tuple[int, int]] = []
    for ty in range(world.height):
        row = world.tiles[ty]
        for tx in range(world.width):
            if row[tx] == TileType.TREE:
                tree_tiles.append((tx, ty))
    if len(tree_tiles) > max_starting_trees:
        rng.shuffle(tree_tiles)
        for tx, ty in tree_tiles[max_starting_trees:]:
            if world.tiles[ty][tx] == TileType.TREE:
                world.tiles[ty][tx] = TileType.GRASS

    # WK132: zone-aware rock scatter (consumes terrain_bias["rock_density"]).
    generate_rock_scatter(world)


# Baseline per-grass-tile rock probability. Matches the legacy renderer hash
# scatter density (`hash % 503 == 0` in ursina_terrain_build) so a rock_density
# of 1.0 yields roughly the same rock count as the old uniform scatter.
_ROCK_BASE_PROBABILITY = 1.0 / 503.0


def generate_rock_scatter(world) -> None:
    """WK132: scatter decorative rocks, biased by zone ``rock_density``.

    Consumes ``Zone.terrain_bias["rock_density"]`` the same way tree_density
    is consumed above (blend-weighted multiplier per tile). Results land in
    ``world.rock_tiles`` (a set of (tx, ty) grass tiles) for renderers to
    consume; the sim itself treats rocks as purely decorative (non-blocking).

    Determinism: draws from a DEDICATED ``get_rng("rock_scatter")`` stream —
    the legacy ``world_gen`` stream is untouched, so lake/forest layout and
    every downstream placement draw stay byte-identical for a given seed.
    """
    from game.world import TileType

    rng = get_rng("rock_scatter")
    castle_cx, castle_cy = world.width // 2, world.height // 2
    rocks: set[tuple[int, int]] = set()
    for y in range(world.height):
        row = world.tiles[y]
        for x in range(world.width):
            if row[x] != TileType.GRASS:
                continue
            zone, blend = get_zone_blend(x, y, castle_cx, castle_cy)
            rock_mult = 1.0
            if zone is not None:
                rock_mult = 1.0 + (zone.terrain_bias.get("rock_density", 1.0) - 1.0) * blend
            if rng.random() < _ROCK_BASE_PROBABILITY * rock_mult:
                rocks.add((x, y))
    world.rock_tiles = rocks


def generate_heightmap(world) -> None:
    """WK53 Wave 2: Generate a Perlin-noise heightmap at 2x sub-tile resolution.

    Fence-post pattern: for an NxM tile map the grid is (2*N+1) x (2*M+1).
    The castle starting area is flattened to a gentle plateau with cosine falloff.
    Water tiles are clamped to TERRAIN_WATER_LEVEL.
    """
    if _pnoise2 is None:
        # noise package unavailable — leave heightmap as None (flat terrain).
        return

    from game.world import TileType

    import config as cfg

    tw, th = int(world.width), int(world.height)
    gw = tw * 2 + 1
    gh = th * 2 + 1
    world.heightmap_grid_w = gw
    world.heightmap_grid_h = gh

    height_scale = float(getattr(cfg, "TERRAIN_HEIGHT_SCALE", 8.0))
    hill_freq = float(getattr(cfg, "TERRAIN_HILL_FREQUENCY", 0.04))
    mtn_freq = float(getattr(cfg, "TERRAIN_MOUNTAIN_FREQUENCY", 0.10))
    detail_freq = float(getattr(cfg, "TERRAIN_DETAIL_FREQUENCY", 0.25))
    water_level = float(getattr(cfg, "TERRAIN_WATER_LEVEL", 1.0))
    flat_radius = float(getattr(cfg, "TERRAIN_CASTLE_FLAT_RADIUS", 5))

    seed = int(getattr(cfg, "SIM_SEED", 1))

    # Castle center in grid coords (castle is placed at MAP_WIDTH//2-1, MAP_HEIGHT//2-1).
    castle_gx = tw // 2 - 1
    castle_gy = th // 2 - 1
    # In heightmap grid space (2x resolution):
    castle_hx = castle_gx * 2 + 1  # center of castle footprint (3x3) offset
    castle_hz = castle_gy * 2 + 1
    flat_radius_grid = flat_radius * 2.0  # convert tile-radius to grid-radius

    # WK53 R3: flatness exponent — pushes low-to-mid noise toward zero (flat ground)
    # while preserving peaks. Values > 1.0 create more flat terrain; 2.5 gives ~60-70%
    # flat map with distinct hill features rising where noise is strongest.
    flatness_exp = float(getattr(cfg, "TERRAIN_FLATNESS_EXPONENT", 2.5))

    # Generate raw Perlin noise heightmap
    hmap: list[list[float]] = []
    for gz in range(gh):
        row: list[float] = []
        for gx in range(gw):
            # Sample Perlin noise at three octaves
            x_sample = float(gx) / 2.0  # convert back to tile-space for frequency
            z_sample = float(gz) / 2.0
            n = 0.0
            n += 1.0 * _pnoise2(
                x_sample * hill_freq, z_sample * hill_freq,
                base=seed,
            )
            n += 0.4 * _pnoise2(
                x_sample * mtn_freq, z_sample * mtn_freq,
                base=seed + 1,
            )
            n += 0.15 * _pnoise2(
                x_sample * detail_freq, z_sample * detail_freq,
                base=seed + 2,
            )
            # pnoise2 returns roughly [-1, 1]; remap to [0, 1]
            raw_01 = (n + 1.0) * 0.5
            raw_01 = max(0.0, min(1.0, raw_01))
            # WK53 R3: Apply flatness bias — power curve compresses low values
            # toward zero (flat) while preserving peaks. This makes ~60-70% of
            # the map relatively flat with hills as distinct features.
            biased = pow(raw_01, flatness_exp)
            h = biased * height_scale
            h = max(0.0, min(height_scale, h))
            row.append(h)
        hmap.append(row)

    # WK54: Zone-influenced elevation biases (applied before castle flattening
    # so the flat plateau overrides any zone elevation changes).
    try:
        from game.graphics.terrain_height import apply_zone_elevation
        apply_zone_elevation(hmap, gw, gh, tw, th, castle_gx, castle_gy)
    except (ImportError, AttributeError):
        pass  # Zone elevation not yet available

    # Castle flattening: average height across footprint, then gentle cosine falloff
    # Sample average height across the castle's 3×3 footprint (6×6 grid cells)
    castle_footprint_samples = []
    for fz in range(castle_hz - 3, castle_hz + 4):
        for fx in range(castle_hx - 3, castle_hx + 4):
            if 0 <= fx < gw and 0 <= fz < gh:
                castle_footprint_samples.append(hmap[fz][fx])
    castle_h = sum(castle_footprint_samples) / len(castle_footprint_samples) if castle_footprint_samples else hmap[castle_hz][castle_hx]

    for gz in range(gh):
        for gx in range(gw):
            dx = gx - castle_hx
            dz = gz - castle_hz
            dist = math.sqrt(dx * dx + dz * dz)
            if dist < flat_radius_grid:
                t = dist / flat_radius_grid
                blend = 0.5 * (1.0 + math.cos(t * math.pi))
                hmap[gz][gx] = hmap[gz][gx] * (1.0 - blend) + castle_h * blend

    # Water tile clamping: clamp heightmap samples that fall on water tiles
    for gz in range(gh):
        tile_z = min(th - 1, gz // 2)
        for gx in range(gw):
            tile_x = min(tw - 1, gx // 2)
            if world.tiles[tile_z][tile_x] == TileType.WATER:
                hmap[gz][gx] = water_level

    world.heightmap = hmap


def flatten_building_footprints(world, buildings) -> None:
    """Flatten terrain under all placed buildings/lairs.

    Called after buildings are placed during world generation.
    buildings: iterable of objects with grid_x, grid_y, and size (w, h) attributes.
    """
    if world.heightmap is None:
        return
    try:
        from game.graphics.terrain_height import flatten_footprint
    except (ImportError, AttributeError):
        return  # flatten_footprint not yet available
    for b in buildings:
        w, h = getattr(b, 'size', (1, 1))
        if isinstance(w, (list, tuple)):
            w, h = w[0], w[1]
        flatten_footprint(
            world.heightmap, world.heightmap_grid_w, world.heightmap_grid_h,
            int(getattr(b, 'grid_x', 0)), int(getattr(b, 'grid_y', 0)),
            int(w), int(h),
        )
