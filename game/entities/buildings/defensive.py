"""
Defensive building entities.
"""

from .base import Building, is_research_unlocked
from .types import BuildingType


class Guardhouse(Building):
    """Guardhouse - spawns guards to defend the kingdom."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.GUARDHOUSE)
        self.guards_spawned = 0
        self.max_guards = 3
        self.spawn_timer = 0.0
        self.spawn_interval = 30.0  # Spawn a guard every 30 seconds

    def update(self, dt: float, guards_list: list):
        """Update guard spawning."""
        if not self.is_constructed:
            return

        if len(guards_list) < self.max_guards:
            self.spawn_timer += dt
            if self.spawn_timer >= self.spawn_interval:
                self.spawn_timer = 0.0
                # Guard spawning will be handled by engine
                return True
        return False


class BallistaTower(Building):
    """Ballista Tower - provides ranged defense against enemies."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.BALLISTA_TOWER)
        self.attack_range = 200  # pixels
        self.attack_damage = 15
        self.attack_cooldown = 0.0
        self.attack_interval = 2.0  # Attack every 2 seconds
        self.target = None

        # WK5: Ranged attacker interface
        self.is_ranged_attacker = True

        # WK5: Ranged projectile event storage (for engine collection)
        self._last_ranged_event = None

        # Research synergy: defensive spells extend tower range.
        if is_research_unlocked("Defensive Spells"):
            self.attack_range += 50

    def update(self, dt: float, enemies: list):
        """Update tower attacks."""
        if not self.is_constructed:
            return

        self.attack_cooldown = max(0, self.attack_cooldown - dt)

        if self.attack_cooldown <= 0:
            # Find nearest enemy in range
            best_target = None
            best_dist = float('inf')

            for enemy in enemies:
                if not enemy.is_alive:
                    continue
                dist = ((self.center_x - enemy.x) ** 2 + (self.center_y - enemy.y) ** 2) ** 0.5
                if dist < self.attack_range and dist < best_dist:
                    best_dist = dist
                    best_target = enemy

            if best_target:
                # Attack the enemy
                if best_target.take_damage(self.attack_damage):
                    # Enemy killed
                    pass
                self.attack_cooldown = self.attack_interval
                self.target = best_target

                # WK5: Emit ranged projectile event for ranged attackers
                if getattr(self, "is_ranged_attacker", False):
                    spec = None
                    if hasattr(self, "get_ranged_spec"):
                        try:
                            spec = self.get_ranged_spec()
                        except Exception:
                            spec = None

                    kind = (spec or {}).get("kind", "bolt")
                    color = (spec or {}).get("color", (180, 180, 200))
                    size = (spec or {}).get("size_px", 2)

                    # Store event for engine collection (WK5: building attacks happen in update(), not combat system)
                    self._last_ranged_event = {
                        "type": "ranged_projectile",
                        "from_x": float(self.center_x),
                        "from_y": float(self.center_y),
                        "to_x": float(best_target.x),
                        "to_y": float(best_target.y),
                        "projectile_kind": kind,
                        "color": color,
                        "size_px": size,
                    }
                else:
                    # Clear any stale event for non-ranged attackers
                    self._last_ranged_event = None
            else:
                self.target = None
                # Clear any stale event if no target
                self._last_ranged_event = None


class WizardTower(Building):
    """Wizard's Tower - provides magical defense capabilities."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.WIZARD_TOWER)
        self.spell_range = 250  # pixels
        self.spell_cooldown = 0.0
        self.spell_interval = 5.0  # Cast spell every 5 seconds
        self.spell_damage = 25

        # Research synergy: apply any unlocked research to new towers.
        if is_research_unlocked("Fire Magic"):
            self.spell_damage += 5
            self.spell_interval = max(1.0, self.spell_interval * 0.9)
        if is_research_unlocked("Defensive Spells"):
            self.spell_range += 50

    def update(self, dt: float, enemies: list):
        """Update spell casting."""
        if not self.is_constructed:
            return

        self.spell_cooldown = max(0, self.spell_cooldown - dt)

        if self.spell_cooldown <= 0:
            # Find enemies in range
            targets = []
            for enemy in enemies:
                if not enemy.is_alive:
                    continue
                dist = ((self.center_x - enemy.x) ** 2 + (self.center_y - enemy.y) ** 2) ** 0.5
                if dist < self.spell_range:
                    targets.append(enemy)

            if targets:
                # Cast spell on all targets in range
                for target in targets:
                    target.take_damage(self.spell_damage)
                self.spell_cooldown = self.spell_interval
