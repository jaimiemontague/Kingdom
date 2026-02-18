"""
Shared hiring/tax behavior for hero-recruiting buildings.
"""


class HiringBuilding:
    """Mixin for building types that can hire heroes and store tax gold."""

    def _init_hiring_state(self) -> None:
        self.heroes_hired = 0
        self.stored_tax_gold = 0

    def can_hire(self) -> bool:
        return True

    def hire_hero(self) -> None:
        self.heroes_hired += 1

    def add_tax_gold(self, amount: int) -> None:
        self.stored_tax_gold += amount

    def collect_taxes(self) -> int:
        amount = self.stored_tax_gold
        self.stored_tax_gold = 0
        return amount
