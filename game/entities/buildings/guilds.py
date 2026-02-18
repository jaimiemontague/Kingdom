"""
Guild building entities.
"""

from .base import Building
from .hiring_mixin import HiringBuilding
from .types import BuildingType


class WarriorGuild(HiringBuilding, Building):
    """Building that allows hiring warrior heroes."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.WARRIOR_GUILD)
        self._init_hiring_state()


class RangerGuild(HiringBuilding, Building):
    """Building that allows hiring ranger heroes."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.RANGER_GUILD)
        self._init_hiring_state()


class RogueGuild(HiringBuilding, Building):
    """Building that allows hiring rogue heroes."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.ROGUE_GUILD)
        self._init_hiring_state()


class WizardGuild(HiringBuilding, Building):
    """Building that allows hiring wizard heroes."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.WIZARD_GUILD)
        self._init_hiring_state()
