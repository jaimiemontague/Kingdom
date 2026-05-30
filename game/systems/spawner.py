"""
Enemy spawning system.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from config import (
    TILE_SIZE,
    MAP_WIDTH,
    MAP_HEIGHT,
    GOBLIN_SPAWN_INTERVAL,
    SPAWNER_INITIAL_NO_SPAWN_MS,
    SPAWNER_FIRST_WAVE_INTERVAL_MS,
    SPAWNER_EXTRA_SPAWN_DELAY_MS,
    SPAWNER_GOBLIN_INTERVAL_MULT,
)
from game.entities.enemy import Goblin, Wolf, Skeleton, SkeletonArcher, Spider, Bandit
from game.sim.determinism import get_rng
from game.systems.protocol import GameSystem, SystemContext

if TYPE_CHECKING:
    from game.systems.difficulty import DifficultySystem


# WK60: weighted enemy pool for mixed-type trickle spawns (not Goblins-only).
# Weight shifts toward tougher enemies as game_time increases.
_ENEMY_POOL_EARLY = [
    (Goblin, 6),
    (Wolf, 3),
    (Spider, 2),
]
_ENEMY_POOL_MID = [
    (Goblin, 3),
    (Wolf, 3),
    (Spider, 3),
    (Skeleton, 2),
    (SkeletonArcher, 1),
]
_ENEMY_POOL_LATE = [
    (Goblin, 2),
    (Wolf, 2),
    (Spider, 2),
    (Skeleton, 3),
    (SkeletonArcher, 2),
    (Bandit, 2),
]


class EnemySpawner(GameSystem):
    """Manages enemy wave spawning."""

    def __init__(self, world, difficulty: "DifficultySystem | None" = None):
        self.world = world
        self.difficulty = difficulty
        # Deterministic stream for wave spawns.
        self.rng = get_rng("enemy_spawner")
        self.spawn_timer = 0
        # WK61-R10: faster first wave and shorter gaps between trickle waves.
        self.first_wave_interval_ms = SPAWNER_FIRST_WAVE_INTERVAL_MS
        self._spawned_first_wave_archer = False
        self.extra_spawn_delay_ms = SPAWNER_EXTRA_SPAWN_DELAY_MS
        self.spawn_interval = (
            GOBLIN_SPAWN_INTERVAL * SPAWNER_GOBLIN_INTERVAL_MULT + self.extra_spawn_delay_ms
        )
        self.elapsed_ms = 0
        self.initial_no_spawn_ms = SPAWNER_INITIAL_NO_SPAWN_MS
        self.wave_number = 1
        # WK60: raised cap from 4 to 6
        self.enemies_per_wave = 1
        self.total_spawned = 0
        self.enabled = True
        
    def get_spawn_position(self) -> tuple:
        """Get a random spawn position at the edge of the map."""
        rng = getattr(self, "rng", get_rng("enemy_spawner"))
        edge = rng.choice(['top', 'bottom', 'left', 'right'])
        
        if edge == 'top':
            x = rng.randint(1, MAP_WIDTH - 2)
            y = 0
        elif edge == 'bottom':
            x = rng.randint(1, MAP_WIDTH - 2)
            y = MAP_HEIGHT - 1
        elif edge == 'left':
            x = 0
            y = rng.randint(1, MAP_HEIGHT - 2)
        else:  # right
            x = MAP_WIDTH - 1
            y = rng.randint(1, MAP_HEIGHT - 2)
        
        # Convert to world coordinates
        world_x = x * TILE_SIZE + TILE_SIZE // 2
        world_y = y * TILE_SIZE + TILE_SIZE // 2
        
        return world_x, world_y

    def _get_first_wave_spawn_position(self) -> tuple:
        """
        Deterministic spawn position near the map center (castle) so Wave 1 is visible quickly.
        """
        cx = MAP_WIDTH // 2
        cy = MAP_HEIGHT // 2

        candidates = [
            (0, -10),
            (0, -8),
            (0, 10),
            (-10, 0),
            (10, 0),
            (0, -14),
            (0, 14),
        ]
        for dx, dy in candidates:
            gx = cx + dx
            gy = cy + dy
            if gx < 1 or gx >= MAP_WIDTH - 1 or gy < 1 or gy >= MAP_HEIGHT - 1:
                continue
            if hasattr(self.world, "is_walkable") and not self.world.is_walkable(gx, gy):
                continue
            return (gx * TILE_SIZE + TILE_SIZE // 2, gy * TILE_SIZE + TILE_SIZE // 2)

        # Fallback: center tile.
        return (cx * TILE_SIZE + TILE_SIZE // 2, cy * TILE_SIZE + TILE_SIZE // 2)
    
    def update(self, ctx: SystemContext, dt: float) -> None:
        """Protocol update hook that appends spawned enemies to the shared context."""
        spawned = self.spawn(dt)
        if spawned:
            ctx.enemies.extend(spawned)

    def _pick_enemy_class(self):
        """WK60: pick a weighted random enemy class based on elapsed game time."""
        minutes = self.elapsed_ms / 60_000.0
        if minutes < 5:
            pool = _ENEMY_POOL_EARLY
        elif minutes < 12:
            pool = _ENEMY_POOL_MID
        else:
            pool = _ENEMY_POOL_LATE
        bag = []
        for cls, w in pool:
            bag.extend([cls] * w)
        return self.rng.choice(bag)

    def spawn(self, dt: float) -> list:
        """
        Update spawner and return list of newly spawned enemies.
        """
        if not self.enabled:
            return []

        # Warmup period: prevent early spawns for a bit.
        self.elapsed_ms += dt * 1000
        if self.elapsed_ms < self.initial_no_spawn_ms:
            return []

        # WK60: apply difficulty multiplier to spawn interval
        interval_mult = 1.0
        if self.difficulty is not None:
            interval_mult = self.difficulty.get_multiplier("spawn_interval")

        self.spawn_timer += dt * 1000
        new_enemies = []

        current_interval = self.first_wave_interval_ms if self.total_spawned == 0 else self.spawn_interval
        effective_interval = current_interval * interval_mult

        if self.spawn_timer >= effective_interval:
            self.spawn_timer = 0

            # WK60: apply difficulty multiplier to enemies per wave
            epw = self.enemies_per_wave
            if self.difficulty is not None:
                epw = max(1, int(round(epw * self.difficulty.get_multiplier("enemies_per_wave"))))

            # Spawn enemies for this wave
            for _ in range(epw):
                if not self._spawned_first_wave_archer:
                    x, y = self._get_first_wave_spawn_position()
                    enemy = SkeletonArcher(x, y)
                    self._spawned_first_wave_archer = True
                else:
                    x, y = self.get_spawn_position()
                    # WK60: mixed enemy types instead of Goblins-only
                    enemy_cls = self._pick_enemy_class()
                    enemy = enemy_cls(x, y)

                # WK60: apply difficulty multipliers to enemy stats on spawn
                # WK72: scaling consolidated into DifficultySystem.apply_to_enemy
                if self.difficulty is not None:
                    self.difficulty.apply_to_enemy(enemy)

                new_enemies.append(enemy)
                self.total_spawned += 1

            # Increase difficulty every few waves
            if self.total_spawned % 10 == 0:
                self.wave_number += 1
                # WK60: raised cap from 4 to 6
                self.enemies_per_wave = min(6, 1 + (self.wave_number // 3))
                # WK60: faster interval reduction (-500 from -250), lower floor (15000 from 21000)
                self.spawn_interval = max(15000, self.spawn_interval - 500)

        return new_enemies
    
    def set_enabled(self, enabled: bool):
        """Enable or disable spawning."""
        self.enabled = enabled
        
    def reset(self):
        """Reset the spawner."""
        self.spawn_timer = 0
        self.elapsed_ms = 0
        self.wave_number = 1
        self.enemies_per_wave = 1
        self.total_spawned = 0
        self._spawned_first_wave_archer = False
        self.spawn_interval = (
            GOBLIN_SPAWN_INTERVAL * SPAWNER_GOBLIN_INTERVAL_MULT + SPAWNER_EXTRA_SPAWN_DELAY_MS
        )

