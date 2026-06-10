"""
POI placement system: procedurally places Points of Interest across the map
during world generation, respecting zone palettes, spacing constraints, and
elevation preferences.
"""

from __future__ import annotations

import math
from typing import Optional

from config import MAP_WIDTH, MAP_HEIGHT, TILE_SIZE
from game.entities.poi import POI_DEFINITIONS, POIDefinition, PointOfInterest
from game.world_zones import ZONES, Zone, get_zone


# ---------------------------------------------------------------------------
# Rarity weights for weighted random selection
# ---------------------------------------------------------------------------

_RARITY_WEIGHTS: dict[str, float] = {
    "common": 4.0,
    "uncommon": 2.0,
    "rare": 1.0,
    "legendary": 0.5,
}

# Legendary POI types that are limited to 1 per map
_LEGENDARY_UNIQUE_TYPES: frozenset[str] = frozenset({
    "poi_bandit_fortress",
    "poi_demon_portal",
    "poi_dragon_cave",  # WK132: max 1 per map, highest-tier zone (mountains)
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _center_distance(
    ax: int, ay: int, a_size: tuple[int, int],
    bx: int, by: int, b_size: tuple[int, int],
) -> float:
    """Euclidean distance between the centres of two footprints (in tiles)."""
    cx_a = ax + a_size[0] / 2.0
    cy_a = ay + a_size[1] / 2.0
    cx_b = bx + b_size[0] / 2.0
    cy_b = by + b_size[1] / 2.0
    return math.hypot(cx_a - cx_b, cy_a - cy_b)


def _estimate_zone_area(
    zone: Zone,
    castle_cx: int,
    castle_cy: int,
    rng,
    sample_count: int = 200,
) -> int:
    """Approximate the number of tiles that fall within a zone by sampling."""
    hits = 0
    for _ in range(sample_count):
        tx = rng.randint(0, MAP_WIDTH - 1)
        ty = rng.randint(0, MAP_HEIGHT - 1)
        z = get_zone(tx, ty, castle_cx, castle_cy)
        if z is not None and z.zone_id == zone.zone_id:
            hits += 1
    total_tiles = MAP_WIDTH * MAP_HEIGHT
    if sample_count <= 0:
        return 0
    return int(total_tiles * hits / sample_count)


# ---------------------------------------------------------------------------
# Placement system
# ---------------------------------------------------------------------------

class POIPlacementSystem:
    """Places POIs across the map based on zone palettes and constraints."""

    # Spacing constraints (tiles)
    MIN_POI_SPACING = 6
    MIN_BUILDING_SPACING = 5
    # Buffer zone: no POIs within this many tiles of the absolute map edge.
    MAP_EDGE_BUFFER = 15

    # POI types suitable for unzoned frontier areas (west/northwest and gap sectors).
    _FRONTIER_PALETTE: list[str] = [
        "poi_shrine",
        "poi_treasure_cache",
        "poi_hermit_hut",
        "poi_abandoned_camp",
        "poi_gravestone",
        "poi_cave_entrance",
        "poi_mysterious_well",  # WK132
        "poi_windmill_ruin",    # WK132: frontier-ring exclusive
    ]

    def generate_pois(
        self,
        world,
        buildings: list,
        lairs: list,
        rng,
    ) -> list[PointOfInterest]:
        """Place POIs across the map based on zone palettes and constraints.

        Parameters
        ----------
        world:
            World object with ``is_walkable(gx, gy)`` and
            ``is_buildable(gx, gy)`` helpers.
        buildings:
            Existing player/neutral buildings (list of Building-like objects).
        lairs:
            Existing monster lairs (list of MonsterLair-like objects).
        rng:
            Deterministic RNG instance (from ``get_rng("poi_placement")``).

        Returns
        -------
        list[PointOfInterest]
            Newly created POI instances placed on the map.
        """
        castle_cx = MAP_WIDTH // 2
        castle_cy = MAP_HEIGHT // 2

        placed_pois: list[PointOfInterest] = []
        legendary_placed: set[str] = set()

        # Combine buildings and lairs for spacing checks
        all_structures = list(buildings or []) + list(lairs or [])

        for zone in ZONES:
            budget = self._poi_budget(zone, castle_cx, castle_cy, rng)

            # Build weighted palette for this zone
            palette_types = [
                pt for pt in zone.poi_palette if pt in POI_DEFINITIONS
            ]
            if not palette_types:
                continue

            for _ in range(budget):
                poi_type = self._weighted_pick(palette_types, rng, legendary_placed)
                if poi_type is None:
                    continue

                definition = POI_DEFINITIONS[poi_type]

                # Enforce legendary uniqueness
                if poi_type in _LEGENDARY_UNIQUE_TYPES:
                    if poi_type in legendary_placed:
                        continue

                spot = self._find_valid_spot(
                    world, zone, definition, placed_pois,
                    all_structures, castle_cx, castle_cy, rng,
                )
                if spot is None:
                    continue

                poi = PointOfInterest(spot[0], spot[1], definition)
                placed_pois.append(poi)

                if poi_type in _LEGENDARY_UNIQUE_TYPES:
                    legendary_placed.add(poi_type)

        # Frontier pass: place POIs in unzoned areas (west/northwest gaps).
        # These areas have no defined Zone, so get_zone() returns None for them.
        # We generate a moderate budget and place from a general-purpose palette.
        frontier_pois = self._place_frontier_pois(
            world, placed_pois, all_structures, castle_cx, castle_cy,
            legendary_placed, rng,
        )
        placed_pois.extend(frontier_pois)

        return placed_pois

    # ------------------------------------------------------------------
    # Budget
    # ------------------------------------------------------------------

    def _poi_budget(
        self,
        zone: Zone,
        castle_cx: int,
        castle_cy: int,
        rng,
    ) -> int:
        """Compute how many POIs to place in a zone.

        Budget is area-based but capped more aggressively for far-reaching zones
        to prevent excessive clustering at map edges.
        """
        area = _estimate_zone_area(zone, castle_cx, castle_cy, rng)
        base = max(2, area // 600)
        bonus = zone.difficulty_tier - 1
        # WK132: +1 per zone for the 5-type palette expansion (total map budget
        # rises ~+4 — "modest" per the WK132 scope; caps lifted to match).
        total = min(21, max(2, base + bonus + 1))

        if zone.zone_id == "castle_town":
            total = min(total, 4)

        # Cap outer zones (max_distance=999) to prevent too many POIs at far edges.
        # With center-biased sampling most will land in the inner portion anyway.
        if zone.max_distance >= 999:
            total = min(total, 9)

        return total

    # ------------------------------------------------------------------
    # Weighted selection
    # ------------------------------------------------------------------

    def _weighted_pick(
        self,
        palette: list[str],
        rng,
        legendary_placed: set[str],
    ) -> Optional[str]:
        """Pick a POI type from *palette* using rarity weights."""
        candidates: list[str] = []
        weights: list[float] = []
        for pt in palette:
            defn = POI_DEFINITIONS.get(pt)
            if defn is None:
                continue
            # Skip legendaries already placed
            if pt in _LEGENDARY_UNIQUE_TYPES and pt in legendary_placed:
                continue
            w = _RARITY_WEIGHTS.get(defn.rarity, 1.0)
            candidates.append(pt)
            weights.append(w)

        if not candidates:
            return None

        # random.choices returns a list; we want one item
        return rng.choices(candidates, weights=weights, k=1)[0]

    # ------------------------------------------------------------------
    # Spot finding
    # ------------------------------------------------------------------

    def _find_valid_spot(
        self,
        world,
        zone: Zone,
        definition: POIDefinition,
        placed_pois: list[PointOfInterest],
        all_structures: list,
        castle_cx: int,
        castle_cy: int,
        rng,
        max_attempts: int = 120,
    ) -> Optional[tuple[int, int]]:
        """Find a valid grid position for the POI within *zone*.

        Uses center-biased sampling: candidate positions are generated with a
        Gaussian distribution centered on the map center, which naturally places
        more POIs near the town and fewer at the far edges.
        """
        fw, fh = definition.size
        buf = self.MAP_EDGE_BUFFER

        # Gaussian sigma: ~40% of map half-width gives a nice center-heavy spread
        sigma_x = (MAP_WIDTH - 2 * buf) * 0.4
        sigma_y = (MAP_HEIGHT - 2 * buf) * 0.4

        for _ in range(max_attempts):
            # Center-biased sampling via Gaussian (clamped to valid range)
            gx = int(rng.gauss(castle_cx, sigma_x))
            gy = int(rng.gauss(castle_cy, sigma_y))

            # Clamp to valid range respecting edge buffer
            gx = max(buf, min(MAP_WIDTH - fw - buf, gx))
            gy = max(buf, min(MAP_HEIGHT - fh - buf, gy))

            # Enforce map edge buffer (reject if footprint extends into buffer)
            if gx < buf or gy < buf:
                continue
            if (gx + fw) > (MAP_WIDTH - buf) or (gy + fh) > (MAP_HEIGHT - buf):
                continue

            # Must be inside the target zone
            z = get_zone(gx, gy, castle_cx, castle_cy)
            if z is None or z.zone_id != zone.zone_id:
                continue

            # Full footprint must be walkable and buildable
            if not self._footprint_ok(world, gx, gy, fw, fh):
                continue

            # Spacing: min 8 tiles from any other POI
            if not self._spacing_ok(gx, gy, (fw, fh), placed_pois, self.MIN_POI_SPACING):
                continue

            # Spacing: min 5 tiles from any building or lair
            if not self._structure_spacing_ok(gx, gy, (fw, fh), all_structures, self.MIN_BUILDING_SPACING):
                continue

            # Elevation preference check
            if not self._elevation_ok(world, gx, gy, fw, fh, definition.elevation_preference):
                continue

            return (gx, gy)

        return None

    # ------------------------------------------------------------------
    # Frontier placement (unzoned areas)
    # ------------------------------------------------------------------

    def _place_frontier_pois(
        self,
        world,
        placed_pois: list[PointOfInterest],
        all_structures: list,
        castle_cx: int,
        castle_cy: int,
        legendary_placed: set[str],
        rng,
    ) -> list[PointOfInterest]:
        """Place POIs in unzoned frontier areas (west/northwest)."""
        palette_types = [
            pt for pt in self._FRONTIER_PALETTE if pt in POI_DEFINITIONS
        ]
        if not palette_types:
            return []

        # Budget: comparable to a mid-tier zone (6-8 POIs for the unzoned gap).
        budget = rng.randint(6, 8)
        new_pois: list[PointOfInterest] = []

        for _ in range(budget):
            poi_type = self._weighted_pick(palette_types, rng, legendary_placed)
            if poi_type is None:
                continue
            definition = POI_DEFINITIONS[poi_type]

            # Try to find a spot in unzoned territory (get_zone returns None).
            spot = self._find_frontier_spot(
                world, definition, placed_pois + new_pois,
                all_structures, castle_cx, castle_cy, rng,
            )
            if spot is None:
                continue

            poi = PointOfInterest(spot[0], spot[1], definition)
            new_pois.append(poi)

        return new_pois

    def _find_frontier_spot(
        self,
        world,
        definition: POIDefinition,
        placed_pois: list[PointOfInterest],
        all_structures: list,
        castle_cx: int,
        castle_cy: int,
        rng,
        max_attempts: int = 150,
    ) -> Optional[tuple[int, int]]:
        """Find a valid spot in unzoned frontier territory.

        Uses center-biased sampling and only accepts positions where
        get_zone returns None (i.e. west/northwest and inter-zone gaps).
        """
        fw, fh = definition.size
        buf = self.MAP_EDGE_BUFFER
        # Gaussian centered on map center, moderate spread to keep POIs
        # away from extreme edges while still covering the frontier.
        sigma = (MAP_WIDTH - 2 * buf) * 0.35

        for _ in range(max_attempts):
            gx = int(rng.gauss(castle_cx, sigma))
            gy = int(rng.gauss(castle_cy, sigma))

            # Clamp to valid range respecting edge buffer
            gx = max(buf, min(MAP_WIDTH - fw - buf, gx))
            gy = max(buf, min(MAP_HEIGHT - fh - buf, gy))

            # Must be in unzoned territory
            z = get_zone(gx, gy, castle_cx, castle_cy)
            if z is not None:
                continue

            # Must be outside castle-town radius (at least 16 tiles from center)
            dist = math.hypot(gx - castle_cx, gy - castle_cy)
            if dist < 16:
                continue

            # Full footprint must be walkable and buildable
            if not self._footprint_ok(world, gx, gy, fw, fh):
                continue

            # Spacing checks
            if not self._spacing_ok(gx, gy, (fw, fh), placed_pois, self.MIN_POI_SPACING):
                continue
            if not self._structure_spacing_ok(gx, gy, (fw, fh), all_structures, self.MIN_BUILDING_SPACING):
                continue

            # Elevation preference
            if not self._elevation_ok(world, gx, gy, fw, fh, definition.elevation_preference):
                continue

            return (gx, gy)

        return None

    # ------------------------------------------------------------------
    # Constraint helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _footprint_ok(world, gx: int, gy: int, fw: int, fh: int) -> bool:
        """Every tile in the footprint must be walkable and buildable."""
        for dx in range(fw):
            for dy in range(fh):
                tx, ty = gx + dx, gy + dy
                if not world.is_walkable(tx, ty):
                    return False
                if hasattr(world, "is_buildable") and not world.is_buildable(tx, ty):
                    return False
        return True

    @staticmethod
    def _spacing_ok(
        gx: int, gy: int, size: tuple[int, int],
        pois: list[PointOfInterest],
        min_dist: float,
    ) -> bool:
        """Check minimum centre-to-centre distance from all placed POIs."""
        for poi in pois:
            dist = _center_distance(
                gx, gy, size,
                poi.grid_x, poi.grid_y, poi.poi_def.size,
            )
            if dist < min_dist:
                return False
        return True

    @staticmethod
    def _structure_spacing_ok(
        gx: int, gy: int, size: tuple[int, int],
        structures: list,
        min_dist: float,
    ) -> bool:
        """Check minimum centre-to-centre distance from buildings/lairs."""
        for s in structures:
            s_gx = getattr(s, "grid_x", None)
            s_gy = getattr(s, "grid_y", None)
            s_size = getattr(s, "size", (1, 1))
            if s_gx is None or s_gy is None:
                continue
            dist = _center_distance(gx, gy, size, s_gx, s_gy, s_size)
            if dist < min_dist:
                return False
        return True

    @staticmethod
    def _elevation_ok(
        world,
        gx: int, gy: int,
        fw: int, fh: int,
        preference: str,
    ) -> bool:
        """Soft elevation preference filter.

        Uses ``world.get_elevation(gx, gy)`` if available; otherwise passes.
        For "high" prefer top-quartile, for "low" prefer bottom-quartile,
        "mid" and "any" always pass.
        """
        if preference == "any" or preference == "mid":
            return True

        get_elev = getattr(world, "get_elevation", None)
        if get_elev is None:
            return True

        # Sample centre tile
        cx = gx + fw // 2
        cy = gy + fh // 2
        try:
            elev = get_elev(cx, cy)
        except Exception:
            return True

        if preference == "high":
            return elev >= 0.6
        if preference == "low":
            return elev <= 0.4

        return True
