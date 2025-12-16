"""
Guard unit spawned by guardhouses/palace for basic defense.
"""

import math
import pygame
from enum import Enum, auto
from config import TILE_SIZE, COLOR_WHITE, COLOR_GREEN, COLOR_RED


class GuardState(Enum):
    IDLE = auto()
    MOVING = auto()
    ATTACKING = auto()
    DEAD = auto()


class Guard:
    """Simple defensive unit: patrols around home, engages nearby enemies."""

    def __init__(self, x: float, y: float, home_building=None):
        self.x = x
        self.y = y
        self.home_building = home_building
        self.home_x = x
        self.home_y = y

        # Stats
        self.max_hp = 80
        self.hp = self.max_hp
        self.attack_power = 8
        self.speed = 2.0

        # Combat
        self.attack_cooldown = 0.0
        self.attack_cooldown_max = 1.2  # seconds
        self.attack_range = TILE_SIZE * 1.4
        self.aggro_range = TILE_SIZE * 6.0

        # AI
        self.state = GuardState.IDLE
        self.target = None
        self.target_position = None

        # Visual
        self.size = 14
        self.color = (120, 120, 160)

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    @property
    def health_percent(self) -> float:
        return self.hp / self.max_hp if self.max_hp else 0.0

    def distance_to(self, x: float, y: float) -> float:
        return math.sqrt((self.x - x) ** 2 + (self.y - y) ** 2)

    def take_damage(self, amount: int) -> bool:
        self.hp = max(0, self.hp - amount)
        if self.hp <= 0:
            self.state = GuardState.DEAD
            return True
        return False

    def move_towards(self, target_x: float, target_y: float, dt: float) -> bool:
        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 3:
            self.x = target_x
            self.y = target_y
            return True
        if dist > 0:
            move_dist = self.speed * dt * 60
            self.x += (dx / dist) * move_dist
            self.y += (dy / dist) * move_dist
        return False

    def _sync_home(self):
        if self.home_building is not None:
            self.home_x = getattr(self.home_building, "center_x", self.home_x)
            self.home_y = getattr(self.home_building, "center_y", self.home_y)

    def find_target(self, enemies: list):
        best = None
        best_dist = float("inf")
        for e in enemies or []:
            if not getattr(e, "is_alive", False):
                continue
            dist = self.distance_to(e.x, e.y)
            if dist <= self.aggro_range and dist < best_dist:
                best_dist = dist
                best = e
        self.target = best
        return best

    def update(self, dt: float, enemies: list):
        if not self.is_alive:
            return

        self._sync_home()

        # Cooldown tick
        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)

        # Validate target
        if self.target is not None and hasattr(self.target, "is_alive") and not self.target.is_alive:
            self.target = None

        # Acquire
        if self.target is None:
            self.find_target(enemies)

        # If no target, return home if wandered
        if self.target is None:
            dist_home = self.distance_to(self.home_x, self.home_y)
            if dist_home > TILE_SIZE * 2:
                self.state = GuardState.MOVING
                self.target_position = (self.home_x, self.home_y)
            else:
                self.state = GuardState.IDLE
                self.target_position = None
            return

        # Engage
        dist = self.distance_to(self.target.x, self.target.y)
        if dist <= self.attack_range:
            self.state = GuardState.ATTACKING
            if self.attack_cooldown <= 0:
                killed = self.target.take_damage(self.attack_power)
                if killed:
                    self.target = None
                self.attack_cooldown = self.attack_cooldown_max
        else:
            self.state = GuardState.MOVING
            self.target_position = (self.target.x, self.target.y)
            self.move_towards(self.target_position[0], self.target_position[1], dt)

    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        if not self.is_alive:
            return

        cam_x, cam_y = camera_offset
        sx = self.x - cam_x
        sy = self.y - cam_y

        pygame.draw.circle(surface, self.color, (int(sx), int(sy)), self.size // 2)
        pygame.draw.circle(surface, COLOR_WHITE, (int(sx), int(sy)), self.size // 2, 1)

        # Symbol
        font = pygame.font.Font(None, 14)
        symbol_text = font.render("G", True, COLOR_WHITE)
        symbol_rect = symbol_text.get_rect(center=(int(sx), int(sy)))
        surface.blit(symbol_text, symbol_rect)

        # Health bar
        bar_w = self.size + 8
        bar_h = 3
        bx = sx - bar_w // 2
        by = sy - self.size // 2 - 7
        pygame.draw.rect(surface, (60, 60, 60), (bx, by, bar_w, bar_h))
        hc = COLOR_GREEN if self.health_percent > 0.5 else COLOR_RED
        pygame.draw.rect(surface, hc, (bx, by, bar_w * self.health_percent, bar_h))


