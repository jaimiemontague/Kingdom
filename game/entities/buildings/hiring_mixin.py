"""
Shared hiring/tax behavior for hero-recruiting buildings.
"""

from config import GUILD_MAX_HEROES


class HiringBuilding:
    """Mixin for building types that can hire heroes and store tax gold."""

    def _init_hiring_state(self) -> None:
        self.heroes_hired = 0
        self.max_heroes = GUILD_MAX_HEROES  # WK60 Feature 3: guild hero cap
        self.stored_tax_gold = 0

    def can_hire(self) -> bool:
        """WK60: Returns False when guild has reached its hero cap."""
        return self.heroes_hired < self.max_heroes

    def hire_hero(self) -> None:
        self.heroes_hired += 1

    def on_hero_death(self) -> None:
        """WK60: Free up a slot when a hero from this guild dies."""
        if self.heroes_hired > 0:
            self.heroes_hired -= 1

    def add_tax_gold(self, amount: int) -> None:
        self.stored_tax_gold += amount

    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount
