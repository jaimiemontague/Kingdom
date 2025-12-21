"""
Enemy spawning system.
"""
import pygame
from config import TILE_SIZE, MAP_WIDTH, MAP_HEIGHT, GOBLIN_SPAWN_INTERVAL
from game.entities.enemy import Goblin
from game.sim.determinism import get_rng


class EnemySpawner:
    """Manages enemy wave spawning."""
    
    def __init__(self, world):
        self.world = world
        # Deterministic stream for wave spawns.
        self.rng = get_rng("enemy_spawner")
        self.spawn_timer = 0
        # Release tuning: fewer monsters overall.
        self.extra_spawn_delay_ms = 12000  # additional gap between waves
        self.spawn_interval = GOBLIN_SPAWN_INTERVAL * 3 + self.extra_spawn_delay_ms
        self.elapsed_ms = 0
        self.initial_no_spawn_ms = 5000  # First wave comes 25 seconds sooner than the original 30s
        self.wave_number = 1
        # (~2/3 reduction vs old 4-per-wave baseline)
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
    
    def update(self, dt: float) -> list:
        """
        Update spawner and return list of newly spawned enemies.
        """
        if not self.enabled:
            return []

        # Warmup period: prevent early spawns for a bit.
        self.elapsed_ms += dt * 1000
        if self.elapsed_ms < self.initial_no_spawn_ms:
            return []
        
        self.spawn_timer += dt * 1000
        new_enemies = []
        
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0
            
            # Spawn enemies for this wave
            for _ in range(self.enemies_per_wave):
                x, y = self.get_spawn_position()
                enemy = Goblin(x, y)
                new_enemies.append(enemy)
                self.total_spawned += 1
            
            # Increase difficulty every few waves
            if self.total_spawned % 10 == 0:
                self.wave_number += 1
                # Keep growth modest for release; cap wave size low.
                self.enemies_per_wave = min(4, 1 + (self.wave_number // 3))
                # Slightly decrease spawn interval, but keep a large floor.
                self.spawn_interval = max(9000 + self.extra_spawn_delay_ms, self.spawn_interval - 250)
        
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
        self.spawn_interval = GOBLIN_SPAWN_INTERVAL * 3 + self.extra_spawn_delay_ms

