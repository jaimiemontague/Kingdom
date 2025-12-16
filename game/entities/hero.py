"""
Hero entity with stats, inventory, and AI state machine.
"""
import pygame
import random
import math
import itertools
from enum import Enum, auto
from config import (
    TILE_SIZE, HERO_BASE_HP, HERO_BASE_ATTACK, HERO_BASE_DEFENSE,
    HERO_SPEED, COLOR_BLUE, COLOR_WHITE, COLOR_GREEN, COLOR_RED
)


class HeroState(Enum):
    IDLE = auto()
    MOVING = auto()
    FIGHTING = auto()
    SHOPPING = auto()
    RETREATING = auto()
    RESTING = auto()
    DEAD = auto()


# Random hero names
HERO_NAMES = [
    "Brock", "Aria", "Theron", "Lyra", "Gareth", "Mira", "Roland", "Elara",
    "Cedric", "Kira", "Magnus", "Freya", "Aldric", "Seraphina", "Dante", "Nova"
]

# Stable numeric IDs for heroes (names can collide).
HERO_ID_COUNTER = itertools.count(1)


class Hero:
    """A hero unit controlled by basic AI + LLM decisions."""
    
    def __init__(self, x: float, y: float, hero_class: str = "warrior"):
        self.hero_id = next(HERO_ID_COUNTER)
        self.x = x
        self.y = y
        self.hero_class = hero_class
        self.name = random.choice(HERO_NAMES)
        
        # Stats
        self.level = 1
        self.xp = 0
        self.xp_to_level = 100
        # Base stats start from config defaults, then class-tune below.
        self.hp = HERO_BASE_HP
        self.max_hp = HERO_BASE_HP
        self.base_attack = HERO_BASE_ATTACK
        self.base_defense = HERO_BASE_DEFENSE
        self.speed = HERO_SPEED
        
        # Resources
        self.gold = 0  # Spendable gold
        self.taxed_gold = 0  # Gold reserved for taxes (25% of earnings)
        
        # Home building reference (set when hired)
        self.home_building = None

        # Optional resting building (e.g., Inn). If set, RESTING happens "inside" this building.
        # Home building is still used for tax deposits and as default rest location.
        self.rest_building = None

        # Temporary buffs (applied by buildings like Royal Gardens)
        self._buffs = {}  # name -> {"expires_ms": int, "attack": int, "defense": int}
        
        # Tax transfer timing - transfer taxes periodically even if not resting
        self.last_tax_transfer_time = 0  # pygame ticks
        self.tax_transfer_interval = 30000  # 30 seconds in milliseconds
        
        # Healing/rest tracking
        self.hp_when_left_home = self.max_hp  # Track HP when leaving home
        self.hp_healed_this_rest = 0  # Track how much healed during current rest
        self.last_heal_time = 0  # For timing heal ticks
        self.damage_since_left_home = 0  # Track damage taken since leaving
        
        # Inventory
        self.weapon = None  # {"name": str, "attack": int}
        self.armor = None   # {"name": str, "defense": int}
        # Blacksmith upgrades (flat bonuses; stack with equipment)
        self.weapon_upgrade_level = 0
        self.armor_upgrade_level = 0
        self.max_upgrade_level = 3
        self.potions = 0
        self.max_potions = 5  # Can carry up to 5 potions
        self.potion_heal_amount = 50
        
        # AI State
        self.state = HeroState.IDLE
        self.target = None  # Could be position tuple, enemy, or building
        self.target_position = None
        self.path = []
        
        # Combat
        self.attack_cooldown = 0
        self.attack_cooldown_max = 1000  # ms between attacks
        self.attack_range = TILE_SIZE * 1.5

        # Class special ability state (used by some classes).
        self._special_cooldown_ms = 0
        self.mana = 0
        self.max_mana = 0
        
        # LLM decision tracking
        self.last_llm_decision_time = 0
        self.pending_llm_decision = False
        self.last_llm_action = None
        self.personality = random.choice([
            "brave and aggressive",
            "cautious and strategic", 
            "greedy but cowardly",
            "balanced and reliable"
        ])
        
        # Visual
        self.size = 20
        self.color = COLOR_BLUE

        # Class tuning (Majesty-style class differentiation).
        if self.hero_class == "ranger":
            # Faster, lower HP/defense, longer range.
            self.max_hp = 80
            self.hp = self.max_hp
            self.base_attack = 8
            self.base_defense = 3
            self.speed = 2.6
            self.attack_range = TILE_SIZE * 4.0
            self.color = (46, 139, 87)  # Sea green
        elif self.hero_class == "rogue":
            # Fast, fragile-ish, reward-driven.
            self.max_hp = 75
            self.hp = self.max_hp
            self.base_attack = 9
            self.base_defense = 2
            self.speed = 3.0
            self.attack_range = TILE_SIZE * 1.6
            self.color = (75, 0, 130)  # Indigo
            self._special_cooldown_ms = 0
        elif self.hero_class == "wizard":
            # Glass cannon at range; simple mana + spell cooldown for bonus damage.
            self.max_hp = 65
            self.hp = self.max_hp
            self.base_attack = 7
            self.base_defense = 1
            self.speed = 2.1
            self.attack_range = TILE_SIZE * 5.0
            self.color = (147, 112, 219)  # Medium purple
            self.max_mana = 100
            self.mana = self.max_mana
            self._special_cooldown_ms = 0
        elif self.hero_class == "healer":
            # Support: sturdy enough, low damage, prefers staying back.
            self.max_hp = 85
            self.hp = self.max_hp
            self.base_attack = 5
            self.base_defense = 4
            self.speed = 2.3
            self.attack_range = TILE_SIZE * 3.5
            self.color = (255, 192, 203)  # Pink
        elif self.hero_class == "monk":
            # Defensive melee: tanky, moderate damage.
            self.max_hp = 120
            self.hp = self.max_hp
            self.base_attack = 8
            self.base_defense = 6
            self.speed = 2.2
            self.attack_range = TILE_SIZE * 1.6
            self.color = (255, 255, 224)  # Light yellow
        elif self.hero_class == "cultist":
            # Nature caster-ish: mid HP, mid range.
            self.max_hp = 90
            self.hp = self.max_hp
            self.base_attack = 7
            self.base_defense = 3
            self.speed = 2.4
            self.attack_range = TILE_SIZE * 4.0
            self.color = (50, 205, 50)  # Lime green
        elif self.hero_class == "priestess":
            # Death caster-ish: fragile, longer range.
            self.max_hp = 75
            self.hp = self.max_hp
            self.base_attack = 8
            self.base_defense = 2
            self.speed = 2.2
            self.attack_range = TILE_SIZE * 4.5
            self.color = (75, 0, 130)  # Indigo
        elif self.hero_class == "barbarian":
            # Berserker: high HP and high damage, low defense.
            self.max_hp = 140
            self.hp = self.max_hp
            self.base_attack = 12
            self.base_defense = 2
            self.speed = 2.4
            self.attack_range = TILE_SIZE * 1.6
            self.color = (139, 0, 0)  # Dark red
        elif self.hero_class == "solarii":
            # Sun warrior: mid HP, good damage, mid range.
            self.max_hp = 100
            self.hp = self.max_hp
            self.base_attack = 10
            self.base_defense = 4
            self.speed = 2.4
            self.attack_range = TILE_SIZE * 3.0
            self.color = (255, 165, 0)  # Orange
        elif self.hero_class == "adept":
            # Wind adept: fast, lowish HP, longer range.
            self.max_hp = 80
            self.hp = self.max_hp
            self.base_attack = 7
            self.base_defense = 2
            self.speed = 3.2
            self.attack_range = TILE_SIZE * 4.5
            self.color = (176, 196, 222)  # Light steel blue
        elif self.hero_class == "gnome":
            # Worker-ish hero: weaker combat, quick mover.
            self.max_hp = 70
            self.hp = self.max_hp
            self.base_attack = 6
            self.base_defense = 3
            self.speed = 2.8
            self.attack_range = TILE_SIZE * 1.6
            self.color = (128, 128, 0)  # Olive
        elif self.hero_class == "elf":
            # Archer: like ranger but slightly different tuning.
            self.max_hp = 75
            self.hp = self.max_hp
            self.base_attack = 9
            self.base_defense = 2
            self.speed = 2.7
            self.attack_range = TILE_SIZE * 4.5
            self.color = (34, 139, 34)  # Forest green
        elif self.hero_class == "dwarf":
            # Tank: slow, high defense.
            self.max_hp = 130
            self.hp = self.max_hp
            self.base_attack = 9
            self.base_defense = 7
            self.speed = 1.9
            self.attack_range = TILE_SIZE * 1.6
            self.color = (101, 67, 33)  # Brown

    @property
    def debug_id(self) -> str:
        """Stable identifier suitable for logs/UI."""
        return f"{self.name}#{self.hero_id}"
    
    def _get_class_symbol(self) -> str:
        """Get a simple symbol/letter for this hero class."""
        symbols = {
            "warrior": "W",
            "ranger": "R",
            "rogue": "T",  # T for Thief
            "wizard": "Z",  # Z for wizard (W taken by warrior)
            "healer": "H",
            "monk": "M",
            "cultist": "C",
            "priestess": "P",
            "barbarian": "B",
            "solarii": "S",
            "adept": "A",
            "gnome": "G",
            "elf": "E",
            "dwarf": "D",
        }
        return symbols.get(self.hero_class, "?")
        
    @property
    def attack(self) -> int:
        """Total attack including weapon bonus."""
        weapon_bonus = self.weapon.get("attack", 0) if self.weapon else 0
        smith_bonus = self.weapon_upgrade_level * 2
        buff_bonus = self.get_buff_attack_bonus()
        return self.base_attack + weapon_bonus + smith_bonus + buff_bonus + (self.level - 1) * 2
    
    @property
    def defense(self) -> int:
        """Total defense including armor bonus."""
        armor_bonus = self.armor.get("defense", 0) if self.armor else 0
        smith_bonus = self.armor_upgrade_level * 2
        buff_bonus = self.get_buff_defense_bonus()
        return self.base_defense + armor_bonus + smith_bonus + buff_bonus + (self.level - 1)

    def _purge_expired_buffs(self):
        now = pygame.time.get_ticks()
        expired = [k for k, v in self._buffs.items() if v.get("expires_ms", 0) <= now]
        for k in expired:
            self._buffs.pop(k, None)

    def apply_buff(self, name: str, duration_sec: float, attack_bonus: int = 0, defense_bonus: int = 0):
        """Apply/refresh a temporary buff."""
        now = pygame.time.get_ticks()
        expires = now + int(max(0.0, duration_sec) * 1000)
        self._buffs[name] = {"expires_ms": expires, "attack": int(attack_bonus), "defense": int(defense_bonus)}

    def has_buff(self, name: str) -> bool:
        self._purge_expired_buffs()
        return name in self._buffs

    def get_buff_attack_bonus(self) -> int:
        self._purge_expired_buffs()
        return sum(v.get("attack", 0) for v in self._buffs.values())

    def get_buff_defense_bonus(self) -> int:
        self._purge_expired_buffs()
        return sum(v.get("defense", 0) for v in self._buffs.values())

    def can_upgrade_weapon(self) -> bool:
        return self.weapon_upgrade_level < self.max_upgrade_level

    def can_upgrade_armor(self) -> bool:
        return self.armor_upgrade_level < self.max_upgrade_level

    def get_weapon_upgrade_cost(self) -> int:
        return 60 + self.weapon_upgrade_level * 50

    def get_armor_upgrade_cost(self) -> int:
        return 60 + self.armor_upgrade_level * 50

    def buy_weapon_upgrade(self) -> bool:
        if not self.can_upgrade_weapon():
            return False
        cost = self.get_weapon_upgrade_cost()
        if self.gold < cost:
            return False
        self.gold -= cost
        self.weapon_upgrade_level += 1
        return True

    def buy_armor_upgrade(self) -> bool:
        if not self.can_upgrade_armor():
            return False
        cost = self.get_armor_upgrade_cost()
        if self.gold < cost:
            return False
        self.gold -= cost
        self.armor_upgrade_level += 1
        return True
    
    @property
    def is_alive(self) -> bool:
        return self.hp > 0
    
    @property
    def health_percent(self) -> float:
        return self.hp / self.max_hp
    
    def take_damage(self, amount: int) -> bool:
        """Take damage, returns True if killed."""
        actual_damage = max(1, amount - self.defense)
        self.hp = max(0, self.hp - actual_damage)
        self.damage_since_left_home += actual_damage
        if self.hp <= 0:
            self.state = HeroState.DEAD
            return True
        return False
    
    def add_gold(self, amount: int):
        """Add gold with automatic 25% tax reservation."""
        tax_amount = int(amount * 0.25)
        spendable = amount - tax_amount
        self.gold += spendable
        self.taxed_gold += tax_amount
    
    def should_go_home_to_rest(self) -> bool:
        """Check if hero should return home to rest."""
        damage_taken = self.max_hp - self.hp
        
        # If we've taken more than 10 total damage since last leaving home
        # and we're not already resting
        if self.state == HeroState.RESTING:
            return False
        
        # First time threshold: took 10+ damage total
        if self.damage_since_left_home >= 10:
            return True
        
        # If we left home damaged and took 5 more damage
        hp_missing_when_left = self.max_hp - self.hp_when_left_home
        if hp_missing_when_left > 10:
            # We left home still hurt, only return if we've taken 5 more
            additional_damage = self.damage_since_left_home
            if additional_damage >= 5:
                return True
        
        return False
    
    def start_resting(self):
        """Start resting at home."""
        # Can't rest if the rest building is currently under attack
        b = self.rest_building or self.home_building
        if b and getattr(b, "is_under_attack", False):
            self.state = HeroState.IDLE
            return False
        
        self.state = HeroState.RESTING
        self.hp_healed_this_rest = 0
        self.last_heal_time = 0
        return True

    def start_resting_at(self, building) -> bool:
        """Start resting at a specific building (e.g. inn)."""
        self.rest_building = building
        return self.start_resting()
    
    def update_resting(self, dt: float) -> bool:
        """Update resting state. Returns True if still resting."""
        if self.state != HeroState.RESTING:
            return False
        
        # Check if building is under attack - must pop out and defend!
        b = self.rest_building or self.home_building
        if b and getattr(b, "is_under_attack", False):
            self.pop_out_of_building()
            return False
        
        self.last_heal_time += dt
        
        # Heal tick rate can vary by building (Inn faster).
        heal_interval = 1.0
        if b and getattr(b, "building_type", "") == "inn":
            # Inn rest rate is defined as "percent per sec" on the building; convert to seconds per 1 HP.
            # If missing/invalid, default to faster than guild.
            rate = float(getattr(b, "rest_recovery_rate", 0.02) or 0.02)
            # 1 HP per interval => interval = 1 / (rate * max_hp)
            heal_interval = max(0.2, 1.0 / max(0.001, rate * max(1, self.max_hp)))
        if self.last_heal_time >= heal_interval:
            self.last_heal_time = 0
            if self.hp < self.max_hp:
                self.hp += 1
                self.hp_healed_this_rest += 1
        
        # Stop resting if fully healed or healed 30 points
        if self.hp >= self.max_hp or self.hp_healed_this_rest >= 30:
            self.finish_resting()
            return False
        
        return True
    
    def pop_out_of_building(self):
        """Hero pops out of building (when building takes damage)."""
        self.state = HeroState.IDLE
        self.hp_healed_this_rest = 0
        # Stay near the building to defend it
        b = self.rest_building or self.home_building
        if b:
            # Position slightly outside the building
            self.x = b.center_x + TILE_SIZE
            self.y = b.center_y
        self.rest_building = None
    
    def can_rest_at_home(self) -> bool:
        """Check if hero can rest at their home building."""
        if not self.home_building:
            return False
        # Cannot rest while the building is currently under attack
        return not getattr(self.home_building, "is_under_attack", False)

    def can_rest_at(self, building) -> bool:
        if not building:
            return False
        if getattr(building, "hp", 0) <= 0:
            return False
        if getattr(building, "building_type", "") == "inn" and getattr(building, "is_constructed", True) is False:
            return False
        return not getattr(building, "is_under_attack", False)
    
    def finish_resting(self):
        """Finish resting and leave home."""
        self.state = HeroState.IDLE
        self.hp_when_left_home = self.hp
        self.damage_since_left_home = 0
        self.hp_healed_this_rest = 0
        self.rest_building = None
    
    def transfer_taxes_to_home(self):
        """Transfer taxed gold to home building."""
        if self.home_building and self.taxed_gold > 0:
            self.home_building.add_tax_gold(self.taxed_gold)
            self.taxed_gold = 0
            import pygame
            self.last_tax_transfer_time = pygame.time.get_ticks()
    
    def heal(self, amount: int):
        """Heal the hero."""
        self.hp = min(self.max_hp, self.hp + amount)
    
    def use_potion(self) -> bool:
        """Use a healing potion if available."""
        if self.potions > 0:
            self.potions -= 1
            self.heal(self.potion_heal_amount)
            return True
        return False
    
    def add_xp(self, amount: int):
        """Add experience points, level up if enough."""
        self.xp += amount
        while self.xp >= self.xp_to_level:
            self.xp -= self.xp_to_level
            self.level_up()
    
    def level_up(self):
        """Level up the hero."""
        self.level += 1
        self.max_hp += 20
        self.hp = self.max_hp  # Full heal on level up
        self.xp_to_level = int(self.xp_to_level * 1.5)
    
    def buy_item(self, item: dict) -> bool:
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
            self.weapon = {
                "name": item["name"],
                "attack": item["attack"],
                # Optional weapon metadata for class preferences.
                "style": item.get("style", "melee"),
            }
        elif item["type"] == "armor":
            self.armor = {"name": item["name"], "defense": item["defense"]}
        
        return True
    
    def wants_to_shop(self, marketplace_items: list) -> bool:
        """Check if hero wants to go shopping based on available items."""
        # Only shop when at full health and idle
        if self.hp < self.max_hp:
            return False
        
        # Need at least 30 gold to feel the need to shop
        if self.gold < 30:
            return False
        
        # Potions (if available)
        has_potion_for_sale = any(item.get("type") == "potion" for item in marketplace_items)
        if has_potion_for_sale:
            # If no potions, strongly desire to buy one.
            if self.potions == 0 and any(item.get("type") == "potion" and self.gold >= item.get("price", 999999) for item in marketplace_items):
                return True
            # If rich, might want to stock up.
            if self.gold >= 50 and self.potions < self.max_potions:
                return True

        # Weapon/armor upgrades
        current_attack = self.weapon.get("attack", 0) if self.weapon else 0
        current_defense = self.armor.get("defense", 0) if self.armor else 0
        for item in marketplace_items:
            if item.get("price", 999999) > self.gold:
                continue
            if item.get("type") == "weapon" and item.get("attack", 0) > current_attack:
                return True
            if item.get("type") == "armor" and item.get("defense", 0) > current_defense:
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
    
    def set_target_position(self, x: float, y: float):
        """Set a position to move towards."""
        self.target_position = (x, y)
        self.state = HeroState.MOVING
    
    def distance_to(self, x: float, y: float) -> float:
        """Calculate distance to a point."""
        return math.sqrt((self.x - x) ** 2 + (self.y - y) ** 2)
    
    def move_towards(self, target_x: float, target_y: float, dt: float):
        """Move towards a target position."""
        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        
        if dist > 0:
            # Normalize and apply speed
            move_dist = self.speed * dt * 60  # 60 is base FPS
            if move_dist >= dist:
                self.x = target_x
                self.y = target_y
            else:
                self.x += (dx / dist) * move_dist
                self.y += (dy / dist) * move_dist
    
    def update(self, dt: float, game_state: dict):
        """Update hero state and behavior."""
        if not self.is_alive:
            return
        
        # Update attack cooldown
        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt * 1000

        # Update class special cooldown
        if self._special_cooldown_ms > 0:
            self._special_cooldown_ms -= dt * 1000

        # Wizard mana regen (simple, always-on).
        if self.hero_class == "wizard" and self.max_mana > 0:
            self.mana = min(self.max_mana, self.mana + (12.0 * dt))
        
        # Periodic tax transfer: if hero has taxed gold and is near home building, transfer it
        # This ensures taxes get deposited even if hero doesn't need to rest
        import pygame
        current_time = pygame.time.get_ticks()
        if (self.taxed_gold > 0 and self.home_building and 
            current_time - self.last_tax_transfer_time >= self.tax_transfer_interval):
            # Check if near home building (within 3 tiles)
            dist_to_home = self.distance_to(self.home_building.center_x, self.home_building.center_y)
            if dist_to_home < TILE_SIZE * 3:
                self.transfer_taxes_to_home()
                self.last_tax_transfer_time = current_time
        
        # State machine behavior handled by basic_ai module
        # This just handles movement if we have a target
        if self.state == HeroState.MOVING and self.target_position:
            self.move_towards(self.target_position[0], self.target_position[1], dt)
            
            # Check if reached destination
            if self.distance_to(self.target_position[0], self.target_position[1]) < 5:
                self.target_position = None
                self.state = HeroState.IDLE

    def compute_attack_damage(self, target=None) -> int:
        """
        Return the damage this hero deals on a basic attack.
        Some classes add simple specials (prototype-friendly).
        """
        dmg = self.attack

        # Rogue: occasional backstab bonus against healthier targets.
        if self.hero_class == "rogue":
            if self._special_cooldown_ms <= 0 and target is not None and hasattr(target, "hp") and hasattr(target, "max_hp"):
                hp_pct = (target.hp / target.max_hp) if target.max_hp else 0.0
                if hp_pct >= 0.7 and random.random() < 0.25:
                    self._special_cooldown_ms = 2000
                    dmg += 6 + (self.level // 2)

        # Wizard: periodic spellburst if mana available.
        if self.hero_class == "wizard":
            if self._special_cooldown_ms <= 0 and self.mana >= 25:
                self.mana -= 25
                self._special_cooldown_ms = 2500
                dmg += 10 + (self.level * 2)

        return int(dmg)
    
    def get_context_for_llm(self, game_state: dict) -> dict:
        """Build context dictionary for LLM decision making."""
        context = {
            "hero": {
                "name": self.name,
                "class": self.hero_class,
                "level": self.level,
                "hp": self.hp,
                "max_hp": self.max_hp,
                "health_percent": round(self.health_percent * 100),
                "gold": self.gold,
                "attack": self.attack,
                "defense": self.defense,
            },
            "inventory": {
                "weapon": self.weapon["name"] if self.weapon else "Fists",
                "armor": self.armor["name"] if self.armor else "None",
                "potions": self.potions,
            },
            "personality": self.personality,
            "current_state": self.state.name,
            "nearby_enemies": [],
            "available_bounties": game_state.get("bounties", []),
            "shop_items": [],
            "situation": {
                "in_combat": False,
                "low_health": self.health_percent < 0.5,
                "critical_health": self.health_percent < 0.25,
                "has_potions": self.potions > 0,
                "near_safety": False,
            },
        }
        
        # Add nearby enemies
        for enemy in game_state.get("enemies", []):
            if enemy.is_alive:
                dist = self.distance_to(enemy.x, enemy.y)
                if dist < TILE_SIZE * 10:  # Within 10 tiles
                    context["nearby_enemies"].append({
                        "type": enemy.enemy_type,
                        "hp": enemy.hp,
                        "max_hp": enemy.max_hp,
                        "distance": round(dist / TILE_SIZE, 1),
                    })
        
        # Add shop items if near marketplace
        for building in game_state.get("buildings", []):
            if building.building_type == "marketplace":
                dist = self.distance_to(building.center_x, building.center_y)
                if dist < TILE_SIZE * 5:
                    context["shop_items"] = building.get_available_items()
                    context["near_marketplace"] = True
        
        return context
    
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        """Render the hero."""
        if not self.is_alive:
            return
            
        cam_x, cam_y = camera_offset
        screen_x = self.x - cam_x
        screen_y = self.y - cam_y
        
        # Draw hero body
        pygame.draw.circle(
            surface,
            self.color,
            (int(screen_x), int(screen_y)),
            self.size // 2
        )
        
        # Draw border
        pygame.draw.circle(
            surface,
            COLOR_WHITE,
            (int(screen_x), int(screen_y)),
            self.size // 2,
            2
        )
        
        # Draw class symbol/letter
        font = pygame.font.Font(None, 18)
        class_symbol = self._get_class_symbol()
        symbol_color = COLOR_WHITE if self.color[0] + self.color[1] + self.color[2] < 400 else (0, 0, 0)
        symbol_text = font.render(class_symbol, True, symbol_color)
        symbol_rect = symbol_text.get_rect(center=(int(screen_x), int(screen_y)))
        surface.blit(symbol_text, symbol_rect)
        
        # Draw health bar
        bar_width = self.size + 10
        bar_height = 4
        bar_x = screen_x - bar_width // 2
        bar_y = screen_y - self.size // 2 - 8
        
        # Background
        pygame.draw.rect(surface, (60, 60, 60), (bar_x, bar_y, bar_width, bar_height))
        
        # Health
        health_color = COLOR_GREEN if self.health_percent > 0.5 else COLOR_RED
        pygame.draw.rect(
            surface, 
            health_color, 
            (bar_x, bar_y, bar_width * self.health_percent, bar_height)
        )
        
        # Draw name
        font = pygame.font.Font(None, 16)
        name_text = font.render(self.name, True, COLOR_WHITE)
        name_rect = name_text.get_rect(center=(screen_x, screen_y + self.size // 2 + 10))
        surface.blit(name_text, name_rect)
        
        # Draw gold if any (show both spendable and taxed)
        total_gold = self.gold + self.taxed_gold
        if total_gold > 0:
            gold_text = font.render(f"${self.gold}(+{self.taxed_gold})", True, (255, 215, 0))
            gold_rect = gold_text.get_rect(center=(screen_x, screen_y + self.size // 2 + 22))
            surface.blit(gold_text, gold_rect)
        
        # Show resting indicator
        if self.state == HeroState.RESTING:
            rest_text = font.render("Zzz", True, (150, 200, 255))
            rest_rect = rest_text.get_rect(center=(screen_x + 15, screen_y - self.size // 2 - 15))
            surface.blit(rest_text, rest_rect)

        # Show buff indicator (royal gardens etc)
        if self.has_buff("royal_gardens"):
            buff_text = font.render("+", True, (120, 255, 120))
            buff_rect = buff_text.get_rect(center=(screen_x - 15, screen_y - self.size // 2 - 15))
            surface.blit(buff_text, buff_rect)

