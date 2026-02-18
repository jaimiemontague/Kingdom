"""
Neutral (auto-spawned) buildings.

These are not placeable by the player; they appear via NeutralBuildingSystem and
slowly generate taxable income over time.
"""

from __future__ import annotations

from config import BUILDING_SIZES, BUILDING_COLORS, BUILDING_COSTS
from game.entities.building import Building


class NeutralBuilding(Building):
    """Base for neutral buildings that generate tax passively."""

    is_neutral = True
    is_player_placeable = False

    def __init__(self, grid_x: int, grid_y: int, building_type: str, *, tax_per_minute: float):
        super().__init__(grid_x, grid_y, building_type)

        # Ensure config defaults exist (but still allow overrides).
        self.size = BUILDING_SIZES.get(building_type, self.size)
        self.color = BUILDING_COLORS.get(building_type, self.color)
        self.cost = BUILDING_COSTS.get(building_type, 0)

        # Tax storage/collection mirrors guild buildings so TaxCollector can pick it up.
        self.stored_tax_gold = 0
        self._tax_accum = 0.0
        self.tax_per_minute = float(tax_per_minute)

        # Neutral buildings appear fully constructed.
        self.is_constructed = True
        self.construction_started = True

        # Slightly squishier than guilds.
        self.max_hp = 180
        self.hp = self.max_hp

    def collect_taxes(self) -> int:
        amount = int(self.stored_tax_gold)
        self.stored_tax_gold = 0
        return amount

    def update(self, dt: float):
        """
        Generate tax over time.

        We store as integer gold and keep fractional in `_tax_accum`.
        """
        if self.hp <= 0:
            return
        gold_per_sec = self.tax_per_minute / 60.0
        self._tax_accum += gold_per_sec * float(dt)
        add = int(self._tax_accum)
        if add > 0:
            self._tax_accum -= add
            self.stored_tax_gold += add


class House(NeutralBuilding):
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "house", tax_per_minute=3.0)


class Farm(NeutralBuilding):
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "farm", tax_per_minute=4.0)
        # Farms are larger targets.
        self.max_hp = 220
        self.hp = self.max_hp


class FoodStand(NeutralBuilding):
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, "food_stand", tax_per_minute=3.5)






