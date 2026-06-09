"""
WK71: hero economy behavior extracted from Hero into a mixin.

Mixed into Hero (``class Hero(..., HeroEconomyMixin, ...)``). Holds ONLY
methods; all instance state stays initialized in ``Hero.__init__``. Method
bodies moved VERBATIM (they already use ``self.*``, which resolves on the
combined Hero instance), so the MRO and every call site are unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from config import TILE_SIZE, TAX_RATE
from game.sim.timebase import now_ms as sim_now_ms

if TYPE_CHECKING:
    from game.entities.buildings.base import Building


class HeroEconomyMixin:
    """WK71: economy behavior extracted from Hero. Mixed into Hero; accesses self.* set in Hero.__init__."""

    def add_gold(self, amount: int):
        """Add gold with automatic 25% tax reservation."""
        gross = int(amount)
        if gross > 0:
            self.increment_career_stat("gold_earned", gross)
        tax_amount = int(gross * TAX_RATE)
        spendable = gross - tax_amount
        self.gold += spendable
        self.taxed_gold += tax_amount

    def increment_career_stat(self, name: str, amount: int = 1) -> None:
        """Bump a fixed career counter (ignored if unknown key)."""
        if name not in self.profile_career:
            return
        self.profile_career[name] = int(self.profile_career[name]) + int(amount)

    def transfer_taxes_to_home(self):
        """Transfer taxed gold to home building."""
        if self.home_building and self.taxed_gold > 0:
            self.home_building.add_tax_gold(self.taxed_gold)
            self.taxed_gold = 0

    def use_potion(self) -> bool:
        """Use a healing potion if available."""
        if self.potions > 0:
            self.potions -= 1
            self.heal(self.potion_heal_amount)
            return True
        return False

    def _is_at_food_stand(self, food_stand: "Building | None") -> bool:
        """Inside the stand or within ~1 tile (matches shop proximity pattern)."""
        if food_stand is None:
            return False
        if self.is_inside_building and self.inside_building is food_stand:
            return True
        dist = self.distance_to(float(food_stand.center_x), float(food_stand.center_y))
        return dist <= TILE_SIZE * 1.0

    def buy_meal_at_food_stand(self, food_stand: "Building | None") -> bool:
        """Buy a meal at a food stand; deposits sale tax to the stand stash."""
        from config import FOOD_MEAL_COST_GOLD, FOOD_MEAL_HUNGER_RESET, HUNGER_INTERVAL_MS

        if food_stand is None:
            return False
        if getattr(food_stand, "building_type", None) != "food_stand":
            return False
        if not self._is_at_food_stand(food_stand):
            return False
        if self.gold < FOOD_MEAL_COST_GOLD:
            return False

        self.gold -= FOOD_MEAL_COST_GOLD
        tax_amount = int(FOOD_MEAL_COST_GOLD * TAX_RATE)
        if tax_amount > 0 and hasattr(food_stand, "add_tax_gold"):
            food_stand.add_tax_gold(tax_amount)
        if FOOD_MEAL_HUNGER_RESET:
            self.next_meal_due_ms = int(sim_now_ms()) + int(HUNGER_INTERVAL_MS)
        if self._event_bus is not None:
            try:
                self._event_bus.emit({
                    "type": "hero_ate",
                    "hero_id": str(self.hero_id),
                    "hero_name": str(self.name),
                    "building_type": "food_stand",
                    "cost_gold": FOOD_MEAL_COST_GOLD,
                })
            except Exception:
                pass
        return True

    def _shop_for_tax_deposit(self, shop_building: "Building | None" = None) -> "Building | None":
        """Resolve the shop that should receive sale tax (WK61-R8-BUG-001)."""
        if shop_building is not None and hasattr(shop_building, "add_tax_gold"):
            return shop_building
        shop = getattr(self, "inside_building", None)
        if shop is not None and hasattr(shop, "add_tax_gold"):
            return shop
        # WK11 deferred shopping: purchase runs after pop_out, so inside_building is cleared.
        if getattr(self, "pending_task", None) == "shopping":
            pending_shop = getattr(self, "pending_task_building", None)
            if pending_shop is not None and hasattr(pending_shop, "add_tax_gold"):
                return pending_shop
        return None

    def buy_item(self, item: dict, *, shop_building: "Building | None" = None) -> bool:
        """Attempt to buy an item using spendable (non-taxed) gold. Returns True if successful."""
        if self.gold < item["price"]:
            return False

        self.gold -= item["price"]

        if item["type"] == "potion":
            if self.potions < self.max_potions:
                self.potions += 1
                self.potion_heal_amount = item.get("effect", 50)
            else:
                # Refund if at max potions
                self.gold += item["price"]
                return False
        elif item["type"] == "weapon":
            self.weapon = {"name": item["name"], "attack": item["attack"]}
        elif item["type"] == "armor":
            self.armor = {"name": item["name"], "defense": item["defense"]}

        # Track successful purchase for journey triggers (sim-time only).
        try:
            self.last_purchase_ms = int(sim_now_ms())
        except Exception:
            self.last_purchase_ms = None
        self.last_purchase_type = str(item.get("type", "")) if item else ""
        self.increment_career_stat("purchases_made", 1)
        # WK61-R4-BUG-004: route shop-sale tax to the building stash (TaxCollector collects later).
        price = int(item.get("price", 0))
        if price > 0:
            from config import TAX_RATE

            tax_amount = int(price * TAX_RATE)
            if tax_amount > 0:
                shop = self._shop_for_tax_deposit(shop_building)
                if shop is not None:
                    shop.add_tax_gold(tax_amount)
        return True

    def wants_to_shop(self, marketplace_has_potions: bool) -> bool:
        """Check if hero wants to go shopping."""
        # WK61-R4-BUG-005: shop when mostly healthy (WK61 lowered base HP; strict full-HP blocked shopping).
        from config import SHOP_MIN_HEALTH_FRACTION

        if self.health_percent < float(SHOP_MIN_HEALTH_FRACTION):
            return False

        # Need at least 30 gold to feel the need to shop
        if self.gold < 30:
            return False

        # WK127-T8: want-to-shop fires ONLY when a do_shopping buy rule can
        # actually succeed — mirror ai/behaviors/shopping.do_shopping exactly:
        #   priority 1: potions == 0 (gold >= 30 already guaranteed above)
        #   priority 2: gold >= 50 and potions < 2
        # The old middle clause (potions < 2 with only 30-49 gold) fired where
        # NO buy rule could succeed -> zero-purchase marketplace orbit.
        if self.potions == 0 and marketplace_has_potions:
            return True

        if self.gold >= 50 and self.potions < 2 and marketplace_has_potions:
            return True

        return False

    def get_shopping_context(self) -> dict:
        """Get context for LLM shopping decisions."""
        return {
            "spendable_gold": self.gold,
            "taxed_gold": self.taxed_gold,
            "current_potions": self.potions,
            "max_potions": self.max_potions,
            "potion_price": 20,
            "hero_class": self.hero_class,
            "personality": self.personality,
        }
