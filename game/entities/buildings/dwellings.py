"""
Non-human dwelling building entities.
"""

from .base import Building
from .hiring_mixin import HiringBuilding
from .types import BuildingType


class GnomeHovel(HiringBuilding, Building):
    """Gnome Hovel - recruits Gnomes who assist with building/repairing."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.GNOME_HOVEL)
        self._init_hiring_state()


class ElvenBungalow(HiringBuilding, Building):
    """Elven Bungalow - recruits Elves, increases marketplace income."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.ELVEN_BUNGALOW)
        self._init_hiring_state()


class DwarvenSettlement(HiringBuilding, Building):
    """Dwarven Settlement - recruits Dwarves, unlocks Ballista Tower."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.DWARVEN_SETTLEMENT)
        self._init_hiring_state()
