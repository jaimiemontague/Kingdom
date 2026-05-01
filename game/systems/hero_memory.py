"""
Hero profile memory constants and stable place keys (WK49).

Simulation-side hooks live on ``Hero``; this module stays free of entity imports.
"""

from __future__ import annotations

PROFILE_MEMORY_MAX_ENTRIES = 30
KNOWN_PLACES_MAX_ENTRIES = 100


def stable_place_id(
    building_type: str,
    grid_x: int,
    grid_y: int,
    *,
    explicit_id: str | None = None,
) -> str:
    """
    Stable dedupe key for a known place: explicit id when present (e.g. future building ids),
    else ``building_type:grid_x:grid_y``.
    """
    if explicit_id:
        return str(explicit_id)
    return f"{str(building_type)}:{int(grid_x)}:{int(grid_y)}"
