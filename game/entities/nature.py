"""
WK44 Stage 2: Nature entities.

Trees are represented both on the world tile grid (TileType.TREE) and as sim entities for
deterministic growth + rendering sync.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Tree:
    grid_x: int
    grid_y: int
    growth_percentage: float = 0.25
    growth_ms_accum: int = 0

    @property
    def key(self) -> tuple[int, int]:
        return (int(self.grid_x), int(self.grid_y))


@dataclass
class LogStack:
    """Render-facing marker for a chopped tree awaiting harvest (Stage 3).

    This is intentionally minimal: simulation logic can treat it as a tile-anchored
    placeholder while renderers use it to show a log pile model.
    """

    grid_x: int
    grid_y: int
    # Growth at the time the tree was chopped (used for yield + render scaling).
    source_tree_growth: float = 1.0

    @property
    def key(self) -> tuple[int, int]:
        return (int(self.grid_x), int(self.grid_y))

    @property
    def scale(self) -> float:
        """0.5 / 0.75 / 1.0 style scale used by rendering."""
        g = float(self.source_tree_growth)
        if g < 0.0:
            return 0.0
        if g > 1.0:
            return 1.0
        return g

