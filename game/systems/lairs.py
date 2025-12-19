"""
Lair system: places monster lairs in the world and updates them to spawn enemies.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from config import (
    MAP_WIDTH,
    MAP_HEIGHT,
    LAIR_INITIAL_COUNT,
    LAIR_MIN_DISTANCE_FROM_CASTLE_TILES,
)
from game.entities.lair import GoblinCamp, WolfDen, SkeletonCrypt, SpiderNest, BanditCamp, MonsterLair


@dataclass
class LairSpawnSpec:
    lair_cls: type[MonsterLair]
    weight: int


DEFAULT_LAIR_SPECS: list[LairSpawnSpec] = [
    LairSpawnSpec(GoblinCamp, 5),
    LairSpawnSpec(WolfDen, 4),
    LairSpawnSpec(SkeletonCrypt, 2),
    LairSpawnSpec(SpiderNest, 4),
    LairSpawnSpec(BanditCamp, 2),
]


class LairSystem:
    def __init__(self, world):
        self.world = world
        self.lairs: list[MonsterLair] = []

    def _distance_tiles(self, ax: int, ay: int, bx: int, by: int) -> float:
        dx = ax - bx
        dy = ay - by
        return (dx * dx + dy * dy) ** 0.5

    def _overlaps_existing(self, gx: int, gy: int, size: tuple[int, int], buildings: list) -> bool:
        for b in buildings or []:
            if getattr(b, "hp", 1) <= 0:
                continue
            for dx in range(size[0]):
                for dy in range(size[1]):
                    if hasattr(b, "occupies_tile") and b.occupies_tile(gx + dx, gy + dy):
                        return True
        return False

    def _pick_lair_type(self) -> type[MonsterLair]:
        bag: list[type[MonsterLair]] = []
        for spec in DEFAULT_LAIR_SPECS:
            bag.extend([spec.lair_cls] * max(1, int(spec.weight)))
        return random.choice(bag)

    def spawn_initial_lairs(self, buildings: list, castle) -> list[MonsterLair]:
        """
        Create and register initial lairs, also appending them to `buildings`.
        """
        castle_gx = getattr(castle, "grid_x", MAP_WIDTH // 2)
        castle_gy = getattr(castle, "grid_y", MAP_HEIGHT // 2)

        created: list[MonsterLair] = []
        tries = 0
        max_tries = LAIR_INITIAL_COUNT * 250

        # Try to ensure early variety: prefer unique lair types until we've placed at least
        # `min(LAIR_INITIAL_COUNT, len(DEFAULT_LAIR_SPECS))` distinct lairs (if placement allows).
        want_unique = min(int(LAIR_INITIAL_COUNT), len(DEFAULT_LAIR_SPECS))
        used: set[type[MonsterLair]] = set()

        while len(created) < LAIR_INITIAL_COUNT and tries < max_tries:
            tries += 1
            lair_cls = self._pick_lair_type()
            if len(used) < want_unique and lair_cls in used:
                continue

            # Create a temp at (0,0) to read size, then discard if invalid
            tmp = lair_cls(0, 0)
            w, h = tmp.size

            gx = random.randint(1, max(1, MAP_WIDTH - w - 2))
            gy = random.randint(1, max(1, MAP_HEIGHT - h - 2))

            if not self.world.is_buildable(gx, gy, w, h):
                continue
            if self._overlaps_existing(gx, gy, (w, h), buildings):
                continue
            if self._distance_tiles(gx, gy, castle_gx, castle_gy) < LAIR_MIN_DISTANCE_FROM_CASTLE_TILES:
                continue

            lair = lair_cls(gx, gy)
            self.lairs.append(lair)
            buildings.append(lair)
            created.append(lair)
            used.add(lair_cls)

        return created

    def update(self, dt: float, buildings: list) -> list:
        """
        Update lairs; return a list of newly spawned enemies.

        Lairs are stored both in `self.lairs` and in the shared `buildings` list.
        """
        spawned = []
        for lair in list(self.lairs):
            if lair.hp <= 0:
                continue
            spawned.extend(lair.update(dt, self.world, buildings))
        return spawned





