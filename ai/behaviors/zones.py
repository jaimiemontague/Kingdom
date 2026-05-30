"""Shared patrol-zone assignment logic.

Extracted from ``ai.behaviors.exploration`` in WK84 Round D-4: ``assign_patrol_zone``
is consumed by ``exploration`` (explore/handle_idle), ``movement`` and
``stuck_recovery`` (via ``ai.exploration_behavior``), so it is genuinely shared
zone logic rather than exploration-specific. It lives here as a single home.

This module imports only leaf deps (``config`` constants + the view-compat
shim); it never imports ``exploration``, so there is no import cycle (exploration
imports ``assign_patrol_zone`` back from here).
"""

from __future__ import annotations

import math
from typing import Any

from config import TILE_SIZE

from ai.behaviors.view_compat import as_ai_view


def assign_patrol_zone(ai: Any, hero: Any, view: Any) -> tuple[float, float]:
    """Assign a unique patrol zone to a hero based on their index."""
    if hero.name in ai.hero_zones:
        return ai.hero_zones[hero.name]

    view = as_ai_view(view)
    # Get castle position as reference.
    castle = view.castle
    if castle:
        base_x, base_y = castle.center_x, castle.center_y
    else:
        from config import MAP_HEIGHT, MAP_WIDTH

        base_x = (MAP_WIDTH // 2) * TILE_SIZE
        base_y = (MAP_HEIGHT // 2) * TILE_SIZE

    # Assign zones in a circle around the castle.
    heroes = [h for h in view.heroes if h.is_alive]
    try:
        idx = heroes.index(hero)
    except ValueError:
        idx = len(ai.hero_zones)

    num_heroes = max(len(heroes), 1)
    angle = (2 * math.pi * idx) / num_heroes + ai._ai_rng.uniform(-0.2, 0.2)
    radius = TILE_SIZE * ai._ai_rng.uniform(6, 10)  # Spread zones further out.

    zone_x = base_x + math.cos(angle) * radius
    zone_y = base_y + math.sin(angle) * radius

    ai.hero_zones[hero.name] = (zone_x, zone_y)
    ai._debug_log(
        f"{hero.name} assigned zone at ({zone_x:.0f}, {zone_y:.0f}), angle={math.degrees(angle):.0f}deg"
    )
    return (zone_x, zone_y)
