"""
Core building primitives and shared research state.
"""

from dataclasses import dataclass

from config import (
    BUILDING_COLORS,
    BUILDING_COSTS,
    BUILDING_SIZES,
    TILE_SIZE,
)
from game.sim.timebase import now_ms as sim_now_ms

from .types import BuildingType

#
# Kingdom-wide research unlocks
# -----------------------------
# NOTE: This is intentionally lightweight (in-process) state. Libraries mirror this so
# research behaves like a global tech tree and can't be purchased repeatedly across
# multiple libraries in a single run.
#
RESEARCH_UNLOCKS = {
    "Advanced Healing": False,
    "Fire Magic": False,
    "Defensive Spells": False,
    "Weapon Upgrades": False,
    "Armor Upgrades": False,
}


@dataclass(frozen=True)
class BuildingRect:
    """Lightweight rectangle helper used for building hit tests."""

    x: float
    y: float
    width: float
    height: float

    def collidepoint(self, px: float, py: float) -> bool:
        return (self.x <= px < (self.x + self.width)) and (self.y <= py < (self.y + self.height))


def is_research_unlocked(name: str) -> bool:
    return bool(RESEARCH_UNLOCKS.get(name, False))


def unlock_research(name: str) -> None:
    if name in RESEARCH_UNLOCKS:
        RESEARCH_UNLOCKS[name] = True


class Building:
    """Base class for all buildings."""

    def __init__(self, grid_x: int, grid_y: int, building_type: BuildingType | str):
        self.grid_x = grid_x
        self.grid_y = grid_y
        self.building_type = building_type
        self.size = BUILDING_SIZES.get(building_type, (1, 1))
        self.color = BUILDING_COLORS.get(building_type, (128, 128, 128))
        self.cost = BUILDING_COSTS.get(building_type, 100)
        self.hp = 200
        self.max_hp = 200
        self.last_damage_time_ms = None  # pygame ticks when last damaged (for "under attack" behavior)
        self.placed_time_ms = sim_now_ms()

        # Construction state (used for newly placed buildings).
        # Default: existing/starting buildings are fully constructed and targetable.
        self.is_constructed = True
        self.construction_started = True
        self._work_accum = 0.0  # fractional HP accumulator for build/repair work

    @property
    def world_x(self) -> float:
        return self.grid_x * TILE_SIZE

    @property
    def world_y(self) -> float:
        return self.grid_y * TILE_SIZE

    @property
    def center_x(self) -> float:
        return self.world_x + (self.size[0] * TILE_SIZE) / 2

    @property
    def center_y(self) -> float:
        return self.world_y + (self.size[1] * TILE_SIZE) / 2

    # Compatibility: many systems treat "targets" as having x/y coordinates.
    # For buildings, use the center point.
    @property
    def x(self) -> float:
        return self.center_x

    @property
    def y(self) -> float:
        return self.center_y

    @property
    def width(self) -> int:
        return self.size[0] * TILE_SIZE

    @property
    def height(self) -> int:
        return self.size[1] * TILE_SIZE

    @property
    def render_state(self) -> "Building":
        """Render accessor used by render-side systems."""
        return self

    def get_rect(self) -> BuildingRect:
        """Get the building's bounding rectangle."""
        return BuildingRect(
            self.world_x, self.world_y,
            self.width, self.height
        )

    def occupies_tile(self, grid_x: int, grid_y: int) -> bool:
        """Check if building occupies a specific grid tile."""
        return (self.grid_x <= grid_x < self.grid_x + self.size[0] and
                self.grid_y <= grid_y < self.grid_y + self.size[1])

    def take_damage(self, amount: int) -> bool:
        """Take damage from an attack. Returns True if destroyed."""
        self.hp = max(0, self.hp - amount)
        self.last_damage_time_ms = sim_now_ms()
        return self.hp <= 0

    @property
    def is_targetable(self) -> bool:
        """Whether enemies can attack this building."""
        if self.hp <= 0:
            return False
        if self.building_type == BuildingType.CASTLE:
            return True
        return bool(self.construction_started)

    def mark_unconstructed(self):
        """Set this building to its just-placed construction state."""
        self.is_constructed = False
        self.construction_started = False
        self.hp = 1
        self._work_accum = 0.0

    def start_construction(self):
        """Called when a peasant starts building; becomes targetable immediately."""
        self.construction_started = True

    def apply_work(self, dt: float, percent_per_sec: float = 0.01) -> bool:
        """
        Apply build/repair work while a peasant is adjacent.

        Increases HP by (percent_per_sec * max_hp) per second until full.
        Returns True if building is now fully repaired/constructed.
        """
        if self.hp >= self.max_hp:
            self.hp = self.max_hp
            self.is_constructed = True
            return True

        # Accumulate fractional work and apply integer HP increases.
        self._work_accum += self.max_hp * percent_per_sec * dt
        add = int(self._work_accum)
        if add > 0:
            self._work_accum -= add
            self.hp = min(self.max_hp, self.hp + add)

        if self.hp >= self.max_hp:
            self.hp = self.max_hp
            self.is_constructed = True
            return True

        return False

    @property
    def is_damaged(self) -> bool:
        """Check if building has taken any damage."""
        return self.hp < self.max_hp

    @property
    def is_under_attack(self) -> bool:
        """True if the building was damaged recently (prevents permanent 'defend forever')."""
        if self.last_damage_time_ms is None:
            return False
        return (sim_now_ms() - self.last_damage_time_ms) < 3000

    @property
    def is_fully_repaired(self) -> bool:
        """Check if building is at full health."""
        return self.hp >= self.max_hp
