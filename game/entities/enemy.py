"""
Enemy entities.
"""
import pygame
import math
import random
from enum import Enum, auto
from config import (
    TILE_SIZE, GOBLIN_HP, GOBLIN_ATTACK, GOBLIN_SPEED,
    COLOR_RED, COLOR_WHITE, COLOR_GREEN
)


class EnemyState(Enum):
    IDLE = auto()
    MOVING = auto()
    ATTACKING = auto()
    DEAD = auto()


class Enemy:
    """Base enemy class."""
    
    def __init__(self, x: float, y: float, enemy_type: str = "goblin"):
        self.x = x
        self.y = y
        self.enemy_type = enemy_type
        
        # Stats (set by subclass)
        self.hp = 30
        self.max_hp = 30
        self.attack_power = 5
        self.speed = 1.5
        self.xp_reward = 25
        self.gold_reward = 10
        
        # AI State
        self.state = EnemyState.IDLE
        self.target = None
        
        # Combat
        self.attack_cooldown = 0
        self.attack_cooldown_max = 1500  # ms between attacks
        self.attack_range = TILE_SIZE * 1.2
        
        # Visual
        self.size = 18
        self.color = COLOR_RED
        
    @property
    def is_alive(self) -> bool:
        return self.hp > 0
    
    @property
    def health_percent(self) -> float:
        return self.hp / self.max_hp
    
    def take_damage(self, amount: int) -> bool:
        """Take damage, returns True if killed."""
        self.hp = max(0, self.hp - amount)
        if self.hp <= 0:
            self.state = EnemyState.DEAD
            return True
        return False
    
    def distance_to(self, x: float, y: float) -> float:
        """Calculate distance to a point."""
        return math.sqrt((self.x - x) ** 2 + (self.y - y) ** 2)
    
    def move_towards(self, target_x: float, target_y: float, dt: float):
        """Move towards a target position."""
        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        
        if dist > 0:
            move_dist = self.speed * dt * 60
            if move_dist >= dist:
                self.x = target_x
                self.y = target_y
            else:
                self.x += (dx / dist) * move_dist
                self.y += (dy / dist) * move_dist
    
    def find_target(self, heroes: list, peasants: list, buildings: list):
        """Find the nearest valid target (peasant, hero, or targetable building)."""
        best_target = None
        best_dist = float('inf')

        # Check peasants that are NOT inside the castle
        for peasant in peasants or []:
            if getattr(peasant, "is_alive", False) and not getattr(peasant, "is_inside_castle", False):
                dist = self.distance_to(peasant.x, peasant.y)
                if dist < best_dist:
                    best_dist = dist
                    best_target = peasant
        
        # Check heroes that are NOT resting (inside buildings)
        for hero in heroes:
            if hero.is_alive and hero.state.name != "RESTING":
                dist = self.distance_to(hero.x, hero.y)
                if dist < best_dist:
                    best_dist = dist
                    best_target = hero
        
        # Check buildings - prioritize ones with resting heroes inside
        for building in buildings:
            if building.hp <= 0:
                continue
            if hasattr(building, "is_targetable") and not building.is_targetable:
                continue
            
            dist = self.distance_to(building.center_x, building.center_y)
            
            # Check if building has heroes resting inside
            has_heroes_inside = False
            for hero in heroes:
                if (hero.is_alive and hero.state.name == "RESTING" and 
                    hero.home_building == building):
                    has_heroes_inside = True
                    break
            
            # Prioritize buildings with heroes inside
            if has_heroes_inside and dist < best_dist:
                best_dist = dist
                best_target = building
            # Castle is always a valid fallback target
            elif building.building_type == "castle" and dist < best_dist * 0.8:
                best_dist = dist
                best_target = building
        
        self.target = best_target
        return best_target
    
    def update(self, dt: float, heroes: list, peasants: list, buildings: list):
        """Update enemy state and behavior."""
        if not self.is_alive:
            return
        
        # Update attack cooldown
        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt * 1000
        
        # Find target if we don't have one
        if self.target is None or (hasattr(self.target, 'is_alive') and not self.target.is_alive):
            self.find_target(heroes, peasants, buildings)
        
        if self.target is None:
            self.state = EnemyState.IDLE
            return
        
        # Get target position
        if hasattr(self.target, 'x'):
            target_x, target_y = self.target.x, self.target.y
        else:
            target_x, target_y = self.target.center_x, self.target.center_y
        
        dist = self.distance_to(target_x, target_y)
        
        # Attack if in range
        if dist <= self.attack_range:
            self.state = EnemyState.ATTACKING
            if self.attack_cooldown <= 0:
                self.do_attack()
                self.attack_cooldown = self.attack_cooldown_max
        else:
            # Move towards target
            self.state = EnemyState.MOVING
            self.move_towards(target_x, target_y, dt)
    
    def do_attack(self):
        """Perform an attack on the current target."""
        if self.target and hasattr(self.target, 'take_damage'):
            self.target.take_damage(self.attack_power)
    
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        """Render the enemy."""
        if not self.is_alive:
            return
            
        cam_x, cam_y = camera_offset
        screen_x = self.x - cam_x
        screen_y = self.y - cam_y
        
        # Draw enemy body (triangle for goblins)
        points = [
            (screen_x, screen_y - self.size // 2),
            (screen_x - self.size // 2, screen_y + self.size // 2),
            (screen_x + self.size // 2, screen_y + self.size // 2),
        ]
        pygame.draw.polygon(surface, self.color, points)
        pygame.draw.polygon(surface, COLOR_WHITE, points, 1)
        
        # Draw health bar
        bar_width = self.size + 6
        bar_height = 3
        bar_x = screen_x - bar_width // 2
        bar_y = screen_y - self.size // 2 - 6
        
        pygame.draw.rect(surface, (60, 60, 60), (bar_x, bar_y, bar_width, bar_height))
        health_color = COLOR_GREEN if self.health_percent > 0.5 else COLOR_RED
        pygame.draw.rect(
            surface, 
            health_color, 
            (bar_x, bar_y, bar_width * self.health_percent, bar_height)
        )


class Goblin(Enemy):
    """Basic goblin enemy."""
    
    def __init__(self, x: float, y: float):
        super().__init__(x, y, "goblin")
        self.hp = GOBLIN_HP
        self.max_hp = GOBLIN_HP
        self.attack_power = GOBLIN_ATTACK * 2  # 2x damage (scaled back from 4x)
        self.speed = GOBLIN_SPEED
        self.xp_reward = 25
        self.gold_reward = 10  # Fixed 10 gold per goblin
        self.color = (139, 69, 19)  # Brown-ish green
        
        # Track who has hit this goblin for gold distribution
        self.attackers = set()  # Set of hero names who have hit this goblin
    
    def register_attacker(self, hero):
        """Register a hero as having attacked this goblin."""
        self.attackers.add(hero.name)

