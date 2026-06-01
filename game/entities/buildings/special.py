"""
Special building entities.
"""

from .base import Building
from .types import BuildingType


class Palace(Building):
    """Upgradeable Palace - the player's main building."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.PALACE)
        self.level = 1
        self.max_level = 3
        self.hp = 500
        self.max_hp = 500
        self.max_peasants = 2
        self.max_tax_collectors = 1
        self.max_palace_guards = 0

    def can_upgrade(self) -> bool:
        """Check if palace can be upgraded."""
        return self.level < self.max_level

    def get_upgrade_cost(self) -> int:
        """Get cost to upgrade to next level."""
        if self.level == 1:
            return 500
        if self.level == 2:
            return 1000
        return 0

    def upgrade(self, economy) -> bool:
        """Upgrade palace to next level."""
        if not self.can_upgrade():
            return False

        cost = self.get_upgrade_cost()
        if economy.player_gold >= cost:
            economy.player_gold -= cost
            self.level += 1

            if self.level == 2:
                self.max_peasants = 4
                self.max_tax_collectors = 2
                self.max_palace_guards = 1
                self.max_hp = 750
                self.hp = 750
            elif self.level == 3:
                self.max_peasants = 6
                self.max_tax_collectors = 3
                self.max_palace_guards = 2
                self.max_hp = 1000
                self.hp = 1000

            return True
        return False
