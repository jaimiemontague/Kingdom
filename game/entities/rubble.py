"""
WK61-FEAT-004: Rubble records for destroyed buildings.

Data-only module. Agent 05 creates RubbleRecord entries when buildings are destroyed;
Agent 03's renderer reads them from the snapshot to place rubble meshes in 3D.
"""

from dataclasses import dataclass


@dataclass
class RubbleRecord:
    """Lightweight record describing a destroyed building's rubble footprint."""

    record_id: int        # unique ID (incrementing counter)
    center_x: float       # world pixel position (same as building.center_x was)
    center_y: float       # world pixel position (same as building.center_y was)
    grid_x: int           # grid tile position
    grid_y: int           # grid tile position
    width_tiles: int      # footprint width in tiles (2 or 3)
    height_tiles: int     # footprint height in tiles (2 or 3)
    building_type: str    # e.g. "house", "farm", "warrior_guild"
    created_ms: int       # sim_now_ms() when rubble was spawned
    duration_ms: int = 120_000  # 2 minutes before rubble disappears


_next_rubble_id = 0


def make_rubble_id() -> int:
    """Return a unique rubble record ID (monotonically incrementing)."""
    global _next_rubble_id
    _next_rubble_id += 1
    return _next_rubble_id
