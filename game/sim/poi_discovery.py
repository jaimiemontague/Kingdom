"""WK69 Round B-1 (W2): POI-discovery service extracted from SimEngine (behavior-preserving move).

Takes the live SimEngine as ``sim`` and reads/writes its state exactly as the
former ``SimEngine._check_poi_discovery`` method did. SimEngine keeps a one-line
delegating wrapper so callers/tests are unchanged.

This module must NOT import ``game.sim_engine`` at runtime (no import cycle): it
takes ``sim`` as a duck-typed parameter and only imports the same leaf helpers
the original method used.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from config import POI_DISCOVERY_RANGE_TILES, TILE_SIZE

if TYPE_CHECKING:  # type-only; avoids a runtime import cycle with game.sim_engine
    from game.sim_engine import SimEngine


def check_poi_discovery(sim: "SimEngine") -> None:
    """Check if any hero is within discovery range of undiscovered POIs."""
    pois = getattr(sim, 'pois', [])
    if not pois or not sim.heroes:
        return

    discovery_range_px = POI_DISCOVERY_RANGE_TILES * TILE_SIZE

    for poi in pois:
        if poi.is_discovered:
            continue

        poi_def = getattr(poi, 'poi_def', None)
        if poi_def is None:
            continue

        size = getattr(poi_def, 'size', (1, 1))
        poi_cx = (poi.grid_x + size[0] / 2.0) * TILE_SIZE
        poi_cy = (poi.grid_y + size[1] / 2.0) * TILE_SIZE

        for hero in sim.heroes:
            if not getattr(hero, 'is_alive', False):
                continue
            hx = float(getattr(hero, 'world_x', getattr(hero, 'x', 0)))
            hy = float(getattr(hero, 'world_y', getattr(hero, 'y', 0)))
            dist = math.hypot(hx - poi_cx, hy - poi_cy)
            if dist <= discovery_range_px:
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
