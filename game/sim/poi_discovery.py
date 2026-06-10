"""WK69 Round B-1 (W2): POI-discovery service extracted from SimEngine (behavior-preserving move).

Takes the live SimEngine as ``sim`` and reads/writes its state exactly as the
former ``SimEngine._check_poi_discovery`` method did. SimEngine keeps a one-line
delegating wrapper so callers/tests are unchanged.

This module must NOT import ``game.sim_engine`` at runtime (no import cycle): it
takes ``sim`` as a duck-typed parameter and only imports the same leaf helpers
the original method used.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from config import POI_DISCOVERY_RANGE_TILES, TILE_SIZE

if TYPE_CHECKING:  # type-only; avoids a runtime import cycle with game.sim_engine
    from game.sim_engine import SimEngine

# Mythos S5 (poi-discovery-throttle): run the O(POIs x heroes) proximity scan
# every Nth tick instead of every tick. At FAST speed (20 ticks/s) the default
# interval of 8 means at most 0.4s of added discovery latency — heroes cover
# well under one tile in that window vs. the multi-tile discovery radius, so no
# discovery is ever missed, only (rarely) credited a few ticks later.
# KINGDOM_POI_SCAN_INTERVAL=1 restores the per-tick scan (A/B hatch).
try:
    _POI_SCAN_INTERVAL = max(1, int(os.environ.get("KINGDOM_POI_SCAN_INTERVAL", "8")))
except ValueError:
    _POI_SCAN_INTERVAL = 8


def check_poi_discovery(sim: "SimEngine") -> None:
    """Check if any hero is within discovery range of undiscovered POIs."""
    # Throttle FIRST (cheap counter) so skipped ticks pay ~nothing. The counter
    # starts at the first tick (scan on ticks 1, 1+N, 1+2N, ...) so early-game
    # discoveries near spawn are not delayed behind a full interval.
    tick = int(getattr(sim, "_poi_scan_tick_counter", 0)) + 1
    sim._poi_scan_tick_counter = tick
    if _POI_SCAN_INTERVAL > 1 and (tick - 1) % _POI_SCAN_INTERVAL != 0:
        return

    pois = getattr(sim, 'pois', [])
    if not pois or not sim.heroes:
        return

    discovery_range_px = POI_DISCOVERY_RANGE_TILES * TILE_SIZE
    range_sq = float(discovery_range_px) * float(discovery_range_px)

    # Snapshot alive-hero positions once per scan (was re-read per POI).
    hero_positions = [
        (hero, float(getattr(hero, 'world_x', getattr(hero, 'x', 0))),
         float(getattr(hero, 'world_y', getattr(hero, 'y', 0))))
        for hero in sim.heroes
        if getattr(hero, 'is_alive', False)
    ]
    if not hero_positions:
        return

    for poi in pois:
        if poi.is_discovered:
            continue

        poi_def = getattr(poi, 'poi_def', None)
        if poi_def is None:
            continue

        # Cache the POI center on the POI (grid pos/size never change post-placement).
        center = getattr(poi, '_poi_center_px_cache', None)
        if center is None:
            size = getattr(poi_def, 'size', (1, 1))
            center = (
                (poi.grid_x + size[0] / 2.0) * TILE_SIZE,
                (poi.grid_y + size[1] / 2.0) * TILE_SIZE,
            )
            try:
                poi._poi_center_px_cache = center
            except Exception:
                pass
        poi_cx, poi_cy = center

        for hero, hx, hy in hero_positions:
            dx = hx - poi_cx
            dy = hy - poi_cy
            # Squared-distance compare == `hypot(dx,dy) <= range` for the
            # boundary-exact radii used here (range is an exact integer px).
            if dx * dx + dy * dy <= range_sq:
                poi.is_discovered = True
                poi.discoverer_hero_id = getattr(hero, 'hero_id', None)
                # Emit discovery event as a proper dict for event bus consumers
                if sim.event_bus:
                    sim.event_bus.emit({
                        "type": "poi_discovered",
                        "poi": poi,
                        "hero": hero,
                        "hero_id": str(getattr(hero, 'hero_id', '') or ''),
                        "poi_type": getattr(poi_def, 'poi_type', ''),
                        "display_name": getattr(poi_def, 'display_name', ''),
                    })
                break  # Only need one hero to discover
