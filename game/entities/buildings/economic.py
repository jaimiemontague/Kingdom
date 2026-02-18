"""
Economic building entities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Building, is_research_unlocked, unlock_research
from .types import BuildingType

if TYPE_CHECKING:
    from game.entities.hero import Hero


class Marketplace(Building):
    """Building where heroes can buy items."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.MARKETPLACE)
        self.potions_researched = False  # Must research before heroes can buy potions
        self.potion_price = 20

        # Research synergy: if Advanced Healing is unlocked, marketplaces can sell potions
        # immediately and at a reduced price.
        if is_research_unlocked("Advanced Healing"):
            self.potions_researched = True
            self.potion_price = 15
        self.items = [
            {"name": "Dagger", "type": "weapon", "style": "melee", "price": 60, "attack": 4},
            {"name": "Short Bow", "type": "weapon", "style": "ranged", "price": 70, "attack": 4},
            {"name": "Apprentice Staff", "type": "weapon", "style": "magic", "price": 90, "attack": 6},
            {"name": "Iron Sword", "type": "weapon", "price": 80, "attack": 5},
            {"name": "Long Bow", "type": "weapon", "style": "ranged", "price": 140, "attack": 8},
            {"name": "Poison Dagger", "type": "weapon", "style": "melee", "price": 120, "attack": 7},
            {"name": "Steel Sword", "type": "weapon", "price": 150, "attack": 10},
            {"name": "Wizard Staff", "type": "weapon", "style": "magic", "price": 180, "attack": 12},
            {"name": "Leather Armor", "type": "armor", "price": 60, "defense": 3},
            {"name": "Chain Mail", "type": "armor", "price": 120, "defense": 7},
        ]

    def get_available_items(self) -> list:
        """Get list of items available for purchase."""
        items = self.items.copy()
        # Add potions if researched
        if self.potions_researched:
            items.insert(0, {"name": "Healing Potion", "type": "potion", "price": self.potion_price, "effect": 50})
        return items

    def can_sell_potions(self) -> bool:
        """Check if marketplace can sell potions."""
        return self.potions_researched


class Blacksmith(Building):
    """Building where heroes can upgrade weapons and armor."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.BLACKSMITH)
        self.upgrades_sold = 0
        self.researched_items = []

        # Research options (similar to Library pattern)
        self.available_research = [
            {"name": "Weapon Upgrades", "cost": 300, "researched": is_research_unlocked("Weapon Upgrades")},
            {"name": "Armor Upgrades", "cost": 300, "researched": is_research_unlocked("Armor Upgrades")},
        ]

        # Mirror global unlocks into this instance for display/UX
        for item in self.available_research:
            if item["researched"]:
                self.researched_items.append(item["name"])

        # Base items (always available)
        self.base_items = [
            {"name": "Iron Sword", "type": "weapon", "price": 80, "attack": 5},
            {"name": "Leather Armor", "type": "armor", "price": 60, "defense": 3},
        ]

        # Upgraded items (gated by research)
        self.upgraded_weapons = [
            {"name": "Steel Sword", "type": "weapon", "price": 150, "attack": 10},
            {"name": "Mithril Blade", "type": "weapon", "price": 250, "attack": 15},
        ]

        self.upgraded_armor = [
            {"name": "Chain Mail", "type": "armor", "price": 120, "defense": 7},
            {"name": "Plate Armor", "type": "armor", "price": 200, "defense": 12},
        ]

    def can_research(self, research_name: str) -> bool:
        """Check if a research can be performed."""
        if is_research_unlocked(research_name):
            return False
        for item in self.available_research:
            if item["name"] == research_name and not item["researched"]:
                return True
        return False

    def research(self, research_name: str, economy, game_state: dict | None = None) -> bool:
        """Perform research if affordable."""
        if hasattr(self, "is_constructed") and not self.is_constructed:
            return False
        if is_research_unlocked(research_name):
            return False
        for item in self.available_research:
            if item["name"] == research_name and not item["researched"]:
                if economy.player_gold >= item["cost"]:
                    economy.player_gold -= item["cost"]
                    item["researched"] = True
                    self.researched_items.append(research_name)
                    unlock_research(research_name)
                    return True
        return False

    def get_available_items(self) -> list:
        """Get list of items available for purchase (gated by research)."""
        items = self.base_items.copy()

        # Add upgraded weapons if researched
        if is_research_unlocked("Weapon Upgrades"):
            items.extend(self.upgraded_weapons)

        # Add upgraded armor if researched
        if is_research_unlocked("Armor Upgrades"):
            items.extend(self.upgraded_armor)

        return items

    def has_upgrades_available(self) -> bool:
        """Check if any upgrades are available (researched and affordable for heroes)."""
        return is_research_unlocked("Weapon Upgrades") or is_research_unlocked("Armor Upgrades")


class Inn(Building):
    """Building where heroes can rest and recover HP faster."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.INN)
        self.rest_recovery_rate = 0.02  # Faster than guilds (0.01)
        self.drink_income_gold = 0

    @property
    def heroes_resting(self) -> list:
        """Backward compatibility: same as base class occupants."""
        return self.occupants

    @property
    def gold_earned_from_drinks(self) -> int:
        """Backward compatibility for panel display."""
        return int(getattr(self, "drink_income_gold", 0))

    @gold_earned_from_drinks.setter
    def gold_earned_from_drinks(self, value: int) -> None:
        """Allow AI/other code to set via setattr (writes to drink_income_gold)."""
        self.drink_income_gold = max(0, int(value))

    def on_hero_enter(self, hero: Hero) -> None:
        """Track heroes currently inside the inn (resting or drinking)."""
        super().on_hero_enter(hero)

    def on_hero_exit(self, hero: Hero) -> None:
        """Remove hero from current inn occupants when they leave."""
        super().on_hero_exit(hero)

    def record_drink_purchase(self, amount: int) -> None:
        """Accumulate gold earned from hero drink purchases."""
        self.drink_income_gold += max(0, int(amount))


class TradingPost(Building):
    """Building that generates passive income through trade caravans."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.TRADING_POST)
        self.income_timer = 0.0
        self.income_interval = 10.0  # Generate income every 10 seconds
        self.income_amount = 10  # Gold per interval
        self.total_income_generated = 0

    def update(self, dt: float, economy):
        """Update income generation."""
        if not self.is_constructed:
            return

        self.income_timer += dt
        if self.income_timer >= self.income_interval:
            self.income_timer = 0.0
            economy.player_gold += self.income_amount
            self.total_income_generated += self.income_amount
