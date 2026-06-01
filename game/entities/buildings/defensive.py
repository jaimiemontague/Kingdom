"""
Defensive building entities.
"""

from config import (
    GUARDHOUSE_ARROW_RANGE_TILES,
    GUARDHOUSE_ARROW_DAMAGE,
    GUARDHOUSE_ARROW_COOLDOWN,
    GUARDHOUSE_ARROWS_PER_SHOT,
    GUARDHOUSE_MAX_HP,
    TILE_SIZE,
)
from .base import Building
from .types import BuildingType


class Guardhouse(Building):
    """Guardhouse - spawns guards AND shoots arrows at nearby enemies (WK60 Feature 5)."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.GUARDHOUSE)
        # WK61-R4-BUG-006: explicit combat HP so targeting/UI state always expose values.
        self.max_hp = int(GUARDHOUSE_MAX_HP)
        self.hp = self.max_hp
        self.guards_spawned = 0
        self.max_guards = 3
        self.spawn_timer = 0.0
        self.spawn_interval = 30.0  # Spawn a guard every 30 seconds

        # WK60 Feature 5: Ranged attack (in addition to guard spawning)
        self.attack_range = GUARDHOUSE_ARROW_RANGE_TILES * TILE_SIZE
        self.arrow_damage = GUARDHOUSE_ARROW_DAMAGE
        self.arrow_cooldown_sec = GUARDHOUSE_ARROW_COOLDOWN
        self._arrow_timer = 0.0
        self.is_ranged_attacker = True
        self._last_ranged_event = None
        self.target = None

    def update(self, dt: float, guards_list: list, enemies: list = None):
        """Update guard spawning and arrow attacks."""
        if not self.is_constructed:
            return False

        # --- Guard spawning (existing behavior) ---
        should_spawn = False
        if len(guards_list) < self.max_guards:
            self.spawn_timer += dt
            if self.spawn_timer >= self.spawn_interval:
                self.spawn_timer = 0.0
                should_spawn = True

        # --- WK60 Feature 5: Arrow attacks ---
        if enemies is not None:
            self._arrow_timer = max(0.0, self._arrow_timer - dt)
            if self._arrow_timer <= 0.0:
                best_target = None
                best_dist = float('inf')
                for enemy in enemies:
                    if not getattr(enemy, "is_alive", False):
                        continue
                    dist = ((self.center_x - enemy.x) ** 2 + (self.center_y - enemy.y) ** 2) ** 0.5
                    if dist < self.attack_range and dist < best_dist:
                        best_dist = dist
                        best_target = enemy

                if best_target is not None:
                    # WK61-TUNE-002: fire GUARDHOUSE_ARROWS_PER_SHOT arrows per volley
                    for _arrow_i in range(GUARDHOUSE_ARROWS_PER_SHOT):
                        best_target.take_damage(self.arrow_damage)
                    self._arrow_timer = self.arrow_cooldown_sec
                    self.target = best_target

                    # Store ranged projectile events for engine collection
                    if hasattr(best_target, "x") and hasattr(best_target, "y"):
                        to_x, to_y = float(best_target.x), float(best_target.y)
                    else:
                        to_x = float(getattr(best_target, "center_x", 0.0))
                        to_y = float(getattr(best_target, "center_y", 0.0))
                    # WK61: emit one projectile event per arrow with distinct origin offsets
                    # Arrows originate from different spots on the guardhouse (+/-12px X, +/-4px Y)
                    self._last_ranged_events = []
                    for i in range(GUARDHOUSE_ARROWS_PER_SHOT):
                        offset_x = (i - (GUARDHOUSE_ARROWS_PER_SHOT - 1) / 2.0) * 24
                        offset_y = (i - (GUARDHOUSE_ARROWS_PER_SHOT - 1) / 2.0) * 8
                        self._last_ranged_events.append({
                            "type": "ranged_projectile",
                            "from_x": float(self.center_x) + offset_x,
                            "from_y": float(self.center_y) + offset_y,
                            "to_x": to_x,
                            "to_y": to_y,
                            "projectile_kind": "arrow",
                            "color": (180, 140, 80),
                            "size_px": 2,
                        })
                    # Keep backward compat: _last_ranged_event is the first arrow
                    self._last_ranged_event = self._last_ranged_events[0] if self._last_ranged_events else None
                else:
                    self.target = None
                    self._last_ranged_event = None

        return should_spawn
