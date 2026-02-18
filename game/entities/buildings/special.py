"""
Special building entities.
"""

from .base import Building, is_research_unlocked, unlock_research
from .types import BuildingType


class Fairgrounds(Building):
    """Fairgrounds - hosts tournaments to train heroes and generate income."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.FAIRGROUNDS)
        self.tournament_timer = 0.0
        self.tournament_interval = 60.0  # Tournament every 60 seconds
        self.tournament_income = 50
        self.total_tournaments = 0

    def update(self, dt: float, economy, heroes: list):
        """Update tournament system."""
        if not self.is_constructed:
            return

        self.tournament_timer += dt
        if self.tournament_timer >= self.tournament_interval:
            self.tournament_timer = 0.0
            # Generate income
            economy.player_gold += self.tournament_income
            self.total_tournaments += 1

            # Give XP to nearby heroes
            for hero in heroes:
                if hero.is_alive:
                    dist = ((self.center_x - hero.x) ** 2 + (self.center_y - hero.y) ** 2) ** 0.5
                    if dist < 150:  # Within range
                        hero.add_xp(10)


class Library(Building):
    """Library - allows research of advanced spells and abilities."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.LIBRARY)
        self.researched_items = []
        self.available_research = [
            {"name": "Advanced Healing", "cost": 200, "researched": is_research_unlocked("Advanced Healing")},
            {"name": "Fire Magic", "cost": 250, "researched": is_research_unlocked("Fire Magic")},
            {"name": "Defensive Spells", "cost": 300, "researched": is_research_unlocked("Defensive Spells")},
        ]

        # Mirror global unlocks into this instance for display/UX.
        for item in self.available_research:
            if item["researched"]:
                self.researched_items.append(item["name"])

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
                    if game_state is not None:
                        self._apply_research_effect(research_name, game_state)
                    return True
        return False

    def _apply_research_effect(self, research_name: str, game_state: dict) -> None:
        """Apply gameplay effects for a completed research unlock."""
        buildings = game_state.get("buildings", []) if isinstance(game_state, dict) else []

        if research_name == "Advanced Healing":
            # Immediate, visible effect: all marketplaces can sell potions and potions are cheaper.
            for b in buildings:
                if getattr(b, "building_type", None) != BuildingType.MARKETPLACE:
                    continue
                b.potions_researched = True
                if hasattr(b, "potion_price"):
                    b.potion_price = min(getattr(b, "potion_price", 20), 15)
                else:
                    b.potion_price = 15

        elif research_name == "Fire Magic":
            for b in buildings:
                if getattr(b, "building_type", None) != BuildingType.WIZARD_TOWER:
                    continue
                # Avoid stacking by relying on the research being one-time.
                b.spell_damage = getattr(b, "spell_damage", 25) + 5
                b.spell_interval = max(1.0, getattr(b, "spell_interval", 5.0) * 0.9)

        elif research_name == "Defensive Spells":
            for b in buildings:
                bt = getattr(b, "building_type", None)
                if bt == BuildingType.WIZARD_TOWER:
                    b.spell_range = getattr(b, "spell_range", 250) + 50
                elif bt == BuildingType.BALLISTA_TOWER:
                    b.attack_range = getattr(b, "attack_range", 200) + 50


class RoyalGardens(Building):
    """Royal Gardens - provides place for heroes to relax, boosting morale."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.ROYAL_GARDENS)
        self.buff_range = 150  # pixels
        # Aura-style: should drop shortly after leaving range (refreshed while in range).
        self.buff_duration = 1.25  # seconds
        self.buff_attack_bonus = 5
        self.buff_defense_bonus = 3

    def get_heroes_in_range(self, heroes: list) -> list:
        """Get heroes within buff range."""
        buffed_heroes = []
        for hero in heroes:
            if hero.is_alive:
                dist = ((self.center_x - hero.x) ** 2 + (self.center_y - hero.y) ** 2) ** 0.5
                if dist < self.buff_range:
                    buffed_heroes.append(hero)
        return buffed_heroes


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
