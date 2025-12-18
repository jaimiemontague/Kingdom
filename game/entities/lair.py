"""
Monster lairs: hostile world-structures that periodically spawn enemies and can be cleared.
"""

from __future__ import annotations

import random
from typing import Optional

import pygame

from config import (
    TILE_SIZE,
    COLOR_WHITE,
    LAIR_STASH_GROWTH_PER_SPAWN,
)
from game.entities.building import Building
from game.entities.enemy import Goblin, Wolf, Skeleton
from game.graphics.font_cache import get_font


def _occupied_tiles(buildings: list) -> set[tuple[int, int]]:
    blocked: set[tuple[int, int]] = set()
    for b in buildings or []:
        if getattr(b, "hp", 1) <= 0:
            continue
        gx = getattr(b, "grid_x", None)
        gy = getattr(b, "grid_y", None)
        size = getattr(b, "size", None)
        if gx is None or gy is None or not size:
            continue
        for dx in range(size[0]):
            for dy in range(size[1]):
                blocked.add((gx + dx, gy + dy))
    return blocked


def _adjacent_spawn_tile(world, buildings: list, lair: "MonsterLair") -> Optional[tuple[int, int]]:
    """Pick a walkable, unoccupied tile adjacent to the lair footprint."""
    gx = lair.grid_x
    gy = lair.grid_y
    w, h = lair.size
    blocked = _occupied_tiles(buildings)

    candidates: list[tuple[int, int]] = []
    # Ring around footprint
    for x in range(gx - 1, gx + w + 1):
        candidates.append((x, gy - 1))
        candidates.append((x, gy + h))
    for y in range(gy, gy + h):
        candidates.append((gx - 1, y))
        candidates.append((gx + w, y))

    random.shuffle(candidates)
    for cx, cy in candidates:
        if (cx, cy) in blocked:
            continue
        if not world.is_walkable(cx, cy):
            continue
        return (cx, cy)
    return None


class MonsterLair(Building):
    """
    Hostile structure that spawns enemies over time and stores a gold stash.

    Notes:
    - We intentionally make lairs non-targetable for enemies (so monsters don't attack lairs).
    - Heroes can damage lairs via CombatSystem additions.
    """

    is_lair = True

    def __init__(
        self,
        grid_x: int,
        grid_y: int,
        building_type: str,
        *,
        spawn_interval_sec: float,
        stash_gold: int,
        threat_level: int = 1,
    ):
        super().__init__(grid_x, grid_y, building_type)
        self.spawn_interval_sec = float(spawn_interval_sec)
        self.spawn_timer = 0.0
        self.threat_level = int(threat_level)
        self.stash_gold = int(stash_gold)

        # Lairs are always "constructed" and block movement.
        self.is_constructed = True
        self.construction_started = True

        # Override default building HP.
        self.max_hp = 250 + (self.threat_level * 75)
        self.hp = self.max_hp

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    @property
    def is_targetable(self) -> bool:
        # Prevent enemies from selecting lairs as targets.
        return False

    def add_stash(self, amount: int):
        self.stash_gold = max(0, int(self.stash_gold) + int(amount))

    def update(self, dt: float, world, buildings: list) -> list:
        """Tick spawn timers; return list of newly spawned enemies."""
        if self.hp <= 0:
            return []

        self.spawn_timer += float(dt)
        if self.spawn_timer < self.spawn_interval_sec:
            return []

        self.spawn_timer = 0.0

        spawn_tile = _adjacent_spawn_tile(world, buildings, self)
        if spawn_tile is None:
            return []

        sx = spawn_tile[0] * TILE_SIZE + TILE_SIZE / 2
        sy = spawn_tile[1] * TILE_SIZE + TILE_SIZE / 2

        enemies = self.spawn_enemies(sx, sy)
        if enemies:
            self.add_stash(LAIR_STASH_GROWTH_PER_SPAWN * len(enemies))
        return enemies

    def spawn_enemies(self, world_x: float, world_y: float) -> list:
        """Override in subclasses."""
        return []

    def on_cleared(self, hero) -> dict:
        """Award stash to the hero who cleared it. Returns a summary dict."""
        payout = int(self.stash_gold)
        self.stash_gold = 0
        if hero is not None and payout > 0:
            # Use add_gold so taxes apply consistently with combat rewards.
            if hasattr(hero, "add_gold"):
                hero.add_gold(payout)
            else:
                hero.gold = getattr(hero, "gold", 0) + payout
        return {"gold": payout, "threat_level": self.threat_level, "lair_type": self.building_type}

    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        super().render(surface, camera_offset)

        # Simple label + stash indicator
        cam_x, cam_y = camera_offset
        sx = self.world_x - cam_x
        sy = self.world_y - cam_y

        font = get_font(16)
        label = self.building_type.replace("_", " ").upper()
        txt = font.render(label, True, COLOR_WHITE)
        rect = txt.get_rect(center=(sx + self.width // 2, sy + self.height // 2))
        surface.blit(txt, rect)

        small = get_font(14)
        stash = small.render(f"${self.stash_gold}", True, (255, 215, 0))
        stash_rect = stash.get_rect(center=(sx + self.width // 2, sy + self.height + 8))
        surface.blit(stash, stash_rect)


class GoblinCamp(MonsterLair):
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(
            grid_x,
            grid_y,
            "goblin_camp",
            spawn_interval_sec=7.0,
            stash_gold=60,
            threat_level=1,
        )
        self.size = (2, 2)
        self.color = (120, 80, 40)

    def spawn_enemies(self, world_x: float, world_y: float) -> list:
        # Small bursts.
        n = 1 if random.random() < 0.7 else 2
        return [Goblin(world_x, world_y) for _ in range(n)]


class WolfDen(MonsterLair):
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(
            grid_x,
            grid_y,
            "wolf_den",
            spawn_interval_sec=6.0,
            stash_gold=40,
            threat_level=1,
        )
        self.size = (2, 2)
        self.color = (90, 90, 90)

    def spawn_enemies(self, world_x: float, world_y: float) -> list:
        n = 2 if random.random() < 0.6 else 1
        return [Wolf(world_x, world_y) for _ in range(n)]


class SkeletonCrypt(MonsterLair):
    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(
            grid_x,
            grid_y,
            "skeleton_crypt",
            spawn_interval_sec=9.0,
            stash_gold=90,
            threat_level=2,
        )
        self.size = (3, 3)
        self.color = (70, 60, 90)

    def spawn_enemies(self, world_x: float, world_y: float) -> list:
        # Slower, tougher spawns.
        return [Skeleton(world_x, world_y)]


