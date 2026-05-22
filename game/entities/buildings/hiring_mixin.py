"""
Shared hiring/tax behavior for hero-recruiting buildings.
"""

from config import GUILD_MAX_HEROES, GUILD_REST_RECOVERY_RATE


class TaxStashMixin:
    """Mixin for buildings that hold taxable gold until TaxCollector collects."""

    def _init_tax_stash(self) -> None:
        self.stored_tax_gold = 0

    @property
    def has_tax_stash_data(self) -> bool:
        """WK61-R6: True when hold-G overlay may read ``stored_tax_gold`` (including $0)."""
        return True

    def get_overlay_tax_gold(self) -> int:
        """Taxable gold for hold-G overlay; 0 when empty, never None."""
        return int(getattr(self, "stored_tax_gold", 0) or 0)

    def add_tax_gold(self, amount: int) -> None:
        self.stored_tax_gold += int(amount)

    def collect_taxes(self) -> int:
        amount = int(self.stored_tax_gold)
        self.stored_tax_gold = 0
        return amount


class HiringBuilding(TaxStashMixin):
    """Mixin for building types that can hire heroes and store tax gold."""

    def _init_hiring_state(self) -> None:
        self._init_tax_stash()
        self.heroes_hired = 0
        self.max_heroes = GUILD_MAX_HEROES  # WK60 Feature 3: guild hero cap
        self.rest_recovery_rate = GUILD_REST_RECOVERY_RATE  # WK61-TUNE-003: 5x healing in guilds

    def can_hire(self) -> bool:
        """WK60: Returns False when guild has reached its hero cap."""
        return self.heroes_hired < self.max_heroes

    def hire_hero(self) -> None:
        self.heroes_hired += 1

    def on_hero_death(self) -> None:
        """WK60: Free up a slot when a hero from this guild dies."""
        if self.heroes_hired > 0:
            self.heroes_hired -= 1
