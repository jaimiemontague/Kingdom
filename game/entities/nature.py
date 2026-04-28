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

