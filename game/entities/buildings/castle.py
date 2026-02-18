"""
Castle building entity.
"""

from .base import Building
from .types import BuildingType


class Castle(Building):
    """The player's main building. Game over if destroyed."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.CASTLE)
        self.hp = 500
        self.max_hp = 500
