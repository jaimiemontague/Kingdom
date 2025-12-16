"""
Economy system for gold, taxes, and transactions.
"""
from config import STARTING_GOLD, TAX_RATE, BUILDING_COSTS, HERO_HIRE_COST


class EconomySystem:
    """Manages the kingdom's economy."""
    
    def __init__(self):
        self.player_gold = STARTING_GOLD
        self.total_tax_collected = 0
        self.total_spent_by_heroes = 0
        self.transaction_log = []
        # Effects from buildings/research
        self.commerce_tax_multiplier = 1.0  # Elven bungalow boosts commerce
        
    def can_afford_building(self, building_type: str) -> bool:
        """Check if player can afford a building."""
        cost = BUILDING_COSTS.get(building_type, 999999)
        return self.player_gold >= cost
    
    def buy_building(self, building_type: str) -> bool:
        """Attempt to purchase a building. Returns True if successful."""
        cost = BUILDING_COSTS.get(building_type, 0)
        if self.player_gold >= cost:
            self.player_gold -= cost
            self.transaction_log.append({
                "type": "building_purchase",
                "building": building_type,
                "cost": cost,
            })
            return True
        return False
    
    def can_afford_hero(self) -> bool:
        """Check if player can afford to hire a hero."""
        return self.player_gold >= HERO_HIRE_COST
    
    def hire_hero(self) -> bool:
        """Attempt to hire a hero. Returns True if successful."""
        if self.player_gold >= HERO_HIRE_COST:
            self.player_gold -= HERO_HIRE_COST
            self.transaction_log.append({
                "type": "hero_hire",
                "cost": HERO_HIRE_COST,
            })
            return True
        return False
    
    def hero_purchase(self, hero_name: str, item_name: str, price: int):
        """Process a hero purchasing an item (applies tax)."""
        self.total_spent_by_heroes += price
        tax = int(price * TAX_RATE * self.commerce_tax_multiplier)
        self.player_gold += tax
        self.total_tax_collected += tax
        
        self.transaction_log.append({
            "type": "hero_purchase",
            "hero": hero_name,
            "item": item_name,
            "price": price,
            "tax": tax,
        })
        
        return tax
    
    def add_bounty(self, amount: int) -> bool:
        """Place a bounty (costs gold)."""
        if self.player_gold >= amount:
            self.player_gold -= amount
            self.transaction_log.append({
                "type": "bounty_placed",
                "amount": amount,
            })
            return True
        return False
    
    def claim_bounty(self, hero_name: str, amount: int):
        """Hero claims a bounty reward."""
        self.transaction_log.append({
            "type": "bounty_claimed",
            "hero": hero_name,
            "amount": amount,
        })
    
    def get_recent_transactions(self, count: int = 5) -> list:
        """Get the most recent transactions."""
        return self.transaction_log[-count:]

