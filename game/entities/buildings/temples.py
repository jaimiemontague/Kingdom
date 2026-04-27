"""
Temple building entities.
"""

from .base import Building
from .hiring_mixin import HiringBuilding
from .types import BuildingType


class TempleAgrela(HiringBuilding, Building):
    """Temple to Agrela - recruits Healers."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.TEMPLE_AGRELA)
        self._init_hiring_state()


class Temple(HiringBuilding, Building):
    """Temple — recruits Clerics (healers)."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.TEMPLE)
        self._init_hiring_state()


class TempleDauros(HiringBuilding, Building):
    """Temple to Dauros - recruits Monks."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.TEMPLE_DAUROS)
        self._init_hiring_state()


class TempleFervus(HiringBuilding, Building):
    """Temple to Fervus - recruits Cultists."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.TEMPLE_FERVUS)
        self._init_hiring_state()


class TempleKrypta(HiringBuilding, Building):
    """Temple to Krypta - recruits Priestesses."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.TEMPLE_KRYPTA)
        self._init_hiring_state()


class TempleKrolm(HiringBuilding, Building):
    """Temple to Krolm - recruits Barbarians."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.TEMPLE_KROLM)
        self._init_hiring_state()


class TempleHelia(HiringBuilding, Building):
    """Temple to Helia - recruits Solarii."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.TEMPLE_HELIA)
        self._init_hiring_state()


class TempleLunord(HiringBuilding, Building):
    """Temple to Lunord - recruits Adepts."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.TEMPLE_LUNORD)
        self._init_hiring_state()
