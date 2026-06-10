"""Zone system for the Kingdom map.

Divides the world into named biome regions using distance-from-castle (rings)
and compass direction (sectors). Each zone carries terrain generation biases,
enemy/POI palettes, and difficulty metadata.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Zone:
    """A named map region with terrain biases and content palettes."""

    name: str
    zone_id: str
    difficulty_tier: int  # 1 (safe) – 5 (deadly)
    min_distance: float   # inner ring radius in tiles from castle
    max_distance: float   # outer ring radius (999 = to map edge)
    angle_start: float    # compass sector start in degrees (0=N, clockwise)
    angle_end: float      # compass sector end
    enemy_palette: list[str] = field(default_factory=list)
    poi_palette: list[str] = field(default_factory=list)
    terrain_bias: dict[str, float] = field(default_factory=dict)
    description: str = ""


# ---------------------------------------------------------------------------
# Zone definitions
# ---------------------------------------------------------------------------

ZONES: list[Zone] = [
    Zone(
        name="Castle Town",
        zone_id="castle_town",
        difficulty_tier=1,
        min_distance=0,
        max_distance=15,
        angle_start=0,
        angle_end=360,
        enemy_palette=[],
        poi_palette=[
            "poi_shrine",
            "poi_treasure_cache",
            "poi_mysterious_well",  # WK132
        ],
        terrain_bias={
            "tree_density": 0.5,
            "rock_density": 0.3,
            "elevation_bias": 0.3,
        },
        description=(
            "The heart of the kingdom. Stone paths radiate from the castle "
            "and the land is gently tended."
        ),
    ),
    Zone(
        name="Darkwood Forest",
        zone_id="darkwood",
        difficulty_tier=2,
        min_distance=24,
        max_distance=999,
        angle_start=150,
        angle_end=210,
        enemy_palette=["wolf", "spider"],
        poi_palette=[
            "poi_hermit_hut",
            "poi_druid_grove",
            "poi_abandoned_camp",
            "poi_treasure_cache",
            "poi_gravestone",
            "poi_mysterious_well",  # WK132
            "poi_ancient_ruins",    # WK132
        ],
        terrain_bias={
            "tree_density": 2.5,
            "rock_density": 0.4,
            "elevation_bias": 0.8,
        },
        description=(
            "Dense forest to the south. The trees grow thick and wolves "
            "hunt in packs beneath the canopy."
        ),
    ),
    Zone(
        name="Mountains",
        zone_id="mountains",
        difficulty_tier=3,
        min_distance=20,
        max_distance=999,
        angle_start=330,
        angle_end=30,
        enemy_palette=["skeleton", "goblin"],
        poi_palette=[
            "poi_cave_entrance",
            "poi_mine_entrance",
            "poi_wizard_tower",
            "poi_shrine",
            "poi_treasure_cache",
            "poi_mysterious_well",  # WK132
            "poi_ruined_outpost",   # WK132
            "poi_ancient_ruins",    # WK132
            "poi_dragon_cave",      # WK132: highest-tier zone, max 1/map
        ],
        terrain_bias={
            "tree_density": 0.3,
            "rock_density": 3.0,
            "elevation_bias": 2.0,
        },
        description=(
            "Jagged peaks rise to the north. Ancient mines dot the cliffs "
            "and the wind cuts like a blade."
        ),
    ),
    Zone(
        name="Canyon Land",
        zone_id="canyon_land",
        difficulty_tier=3,
        min_distance=22,
        max_distance=999,
        angle_start=60,
        angle_end=120,
        enemy_palette=["skeleton", "bandit"],
        poi_palette=[
            "poi_graveyard",
            "poi_bandit_fortress",
            "poi_abandoned_camp",
            "poi_gravestone",
            "poi_demon_portal",
            "poi_mysterious_well",  # WK132
            "poi_ruined_outpost",   # WK132
            "poi_ancient_ruins",    # WK132
        ],
        terrain_bias={
            "tree_density": 0.2,
            "rock_density": 2.5,
            "elevation_bias": 1.5,
        },
        description=(
            "Barren ridges and deep valleys stretch eastward. The dead do "
            "not rest here, and bandits lurk among the rock formations."
        ),
    ),
]

# Blend margin (tiles) used by get_zone_blend for smooth zone transitions
BLEND_MARGIN: float = 8.0


# ---------------------------------------------------------------------------
# Zone resolution helpers
# ---------------------------------------------------------------------------

def _angle_in_sector(angle: float, start: float, end: float) -> bool:
    """Return True if *angle* falls within the sector [start, end).

    Handles wrap-around correctly (e.g. start=330, end=30 spans north).
    All values are in degrees, 0-360.
    """
    if start <= end:
        return start <= angle < end
    # Wraps around 0 (e.g. 330 -> 30)
    return angle >= start or angle < end


def get_zone(
    tile_x: int,
    tile_y: int,
    castle_cx: int,
    castle_cy: int,
) -> Zone | None:
    """Return the zone that contains the given tile, or None for unzoned frontier.

    Parameters
    ----------
    tile_x, tile_y:
        Tile coordinates to query.
    castle_cx, castle_cy:
        Tile coordinates of the castle centre.
    """
    dx = tile_x - castle_cx
    dy = tile_y - castle_cy
    distance = math.hypot(dx, dy)

    # Compass angle: 0 = North, clockwise
    angle = math.degrees(math.atan2(dx, -dy)) % 360

    # Castle Town is checked first (distance-only, full 360 degrees)
    castle_town = ZONES[0]
    if distance <= castle_town.max_distance:
        return castle_town

    # Check remaining zones (distance + angle sector)
    for zone in ZONES[1:]:
        if distance < zone.min_distance:
            continue
        if zone.max_distance != 999 and distance > zone.max_distance:
            continue
        if _angle_in_sector(angle, zone.angle_start, zone.angle_end):
            return zone

    return None


def get_zone_blend(
    tile_x: int,
    tile_y: int,
    castle_cx: int,
    castle_cy: int,
) -> tuple[Zone | None, float]:
    """Return *(zone, blend_weight)* for smooth zone transitions.

    *blend_weight* ramps from 0.0 at the zone border to 1.0 when the tile
    is ``BLEND_MARGIN`` tiles (or more) inside the zone. The ramp uses
    cosine interpolation for a smooth transition.

    For tiles that fall outside any zone, returns ``(None, 0.0)``.
    """
    dx = tile_x - castle_cx
    dy = tile_y - castle_cy
    distance = math.hypot(dx, dy)
    angle = math.degrees(math.atan2(dx, -dy)) % 360

    # Castle Town — blend based on how far inside the ring the tile is
    castle_town = ZONES[0]
    if distance <= castle_town.max_distance:
        depth = castle_town.max_distance - distance
        t = min(depth / BLEND_MARGIN, 1.0)
        # Cosine interpolation: 0 -> 0, 1 -> 1, smooth in between
        weight = 0.5 * (1.0 - math.cos(t * math.pi))
        return castle_town, weight

    # Other zones
    for zone in ZONES[1:]:
        if distance < zone.min_distance:
            continue
        if zone.max_distance != 999 and distance > zone.max_distance:
            continue
        if not _angle_in_sector(angle, zone.angle_start, zone.angle_end):
            continue

        # Depth into zone measured from zone.min_distance
        depth = distance - zone.min_distance
        t = min(depth / BLEND_MARGIN, 1.0)
        weight = 0.5 * (1.0 - math.cos(t * math.pi))
        return zone, weight

    return None, 0.0
