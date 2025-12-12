"""
Hero entity with stats, inventory, and AI state machine.
"""
import pygame
import random
import math
from enum import Enum, auto
from config import (
    TILE_SIZE, HERO_BASE_HP, HERO_BASE_ATTACK, HERO_BASE_DEFENSE,
    HERO_SPEED, HERO_HIRE_COST, COLOR_BLUE, COLOR_WHITE, COLOR_GREEN, COLOR_RED
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


class Hero:
    """A hero unit controlled by basic AI + LLM decisions."""
    
    def __init__(self, x: float, y: float, hero_class: str = "warrior"):
        self.x = x
        self.y = y
        self.hero_class = hero_class
        self.name = random.choice(HERO_NAMES)
        
        # Stats
        self.level = 1
        self.xp = 0
        self.xp_to_level = 100
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
        
        # Healing/rest tracking
        self.hp_when_left_home = self.max_hp  # Track HP when leaving home
        self.hp_healed_this_rest = 0  # Track how much healed during current rest
        self.last_heal_time = 0  # For timing heal ticks
        self.damage_since_left_home = 0  # Track damage taken since leaving
        
        # Inventory
        self.weapon = None  # {"name": str, "attack": int}
        self.armor = None   # {"name": str, "defense": int}
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
        
    @property
    def attack(self) -> int:
        """Total attack including weapon bonus."""
        weapon_bonus = self.weapon.get("attack", 0) if self.weapon else 0
        return self.base_attack + weapon_bonus + (self.level - 1) * 2
    
    @property
    def defense(self) -> int:
        """Total defense including armor bonus."""
        armor_bonus = self.armor.get("defense", 0) if self.armor else 0
        return self.base_defense + armor_bonus + (self.level - 1)
    
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
        self.state = HeroState.RESTING
        self.hp_healed_this_rest = 0
        self.last_heal_time = 0
    
    def update_resting(self, dt: float) -> bool:
        """Update resting state. Returns True if still resting."""
        if self.state != HeroState.RESTING:
            return False
        
        self.last_heal_time += dt
        
        # Heal 1 HP every 2 seconds
        if self.last_heal_time >= 2.0:
            self.last_heal_time = 0
            if self.hp < self.max_hp:
                self.hp += 1
                self.hp_healed_this_rest += 1
        
        # Stop resting if fully healed or healed 30 points
        if self.hp >= self.max_hp or self.hp_healed_this_rest >= 30:
            self.finish_resting()
            return False
        
        return True
    
    def finish_resting(self):
        """Finish resting and leave home."""
        self.state = HeroState.IDLE
        self.hp_when_left_home = self.hp
        self.damage_since_left_home = 0
        self.hp_healed_this_rest = 0
    
    def transfer_taxes_to_home(self):
        """Transfer taxed gold to home building."""
        if self.home_building and self.taxed_gold > 0:
            self.home_building.add_tax_gold(self.taxed_gold)
            self.taxed_gold = 0
    
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
            self.weapon = {"name": item["name"], "attack": item["attack"]}
        elif item["type"] == "armor":
            self.armor = {"name": item["name"], "defense": item["defense"]}
        
        return True
    
    def wants_to_shop(self, marketplace_has_potions: bool) -> bool:
        """Check if hero wants to go shopping."""
        # Only shop when at full health and idle
        if self.hp < self.max_hp:
            return False
        
        # Need at least 30 gold to feel the need to shop
        if self.gold < 30:
            return False
        
        # If no potions and gold >= 30, want to buy one potion
        if self.potions == 0 and marketplace_has_potions:
            return True
        
        # If gold >= 50, might want to buy more potions (LLM decides)
        if self.gold >= 50 and self.potions < self.max_potions and marketplace_has_potions:
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
        
        # State machine behavior handled by basic_ai module
        # This just handles movement if we have a target
        if self.state == HeroState.MOVING and self.target_position:
            self.move_towards(self.target_position[0], self.target_position[1], dt)
            
            # Check if reached destination
            if self.distance_to(self.target_position[0], self.target_position[1]) < 5:
                self.target_position = None
                self.state = HeroState.IDLE
    
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

