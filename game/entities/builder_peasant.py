"""
WK43 Stage 1: BuilderPeasant

Dedicated peasant that constructs auto-spawned neutral building plots, then returns to the
castle and despawns. Regular peasants must not build these plots.
"""

from __future__ import annotations

from enum import Enum, auto

from config import TILE_SIZE
from game.entities.peasant import Peasant, PeasantState


class BuilderPeasantPhase(Enum):
    MOVE_TO_PLOT = auto()
    BUILDING = auto()
    RETURN_TO_CASTLE = auto()
    DESPAWN = auto()


class BuilderPeasant(Peasant):
    def __init__(self, x: float, y: float, *, castle, target_building):
        super().__init__(x, y)
        self.castle = castle
        self.target_building = target_building
        self.phase = BuilderPeasantPhase.MOVE_TO_PLOT
        self.should_despawn = False

        # Minimal visual distinction until renderer support (Agent 03).
        self.color = (110, 220, 110)

    @classmethod
    def spawn_from_castle(cls, *, castle, target_building) -> "BuilderPeasant":
        x = float(getattr(castle, "center_x", 0.0))
        y = float(getattr(castle, "center_y", 0.0))
        return cls(x, y, castle=castle, target_building=target_building)

    def update(self, dt: float, game_state: dict):  # noqa: ARG002 — keep signature consistent with Peasant
        if not self.is_alive:
            return

        if self.phase == BuilderPeasantPhase.DESPAWN:
            self.should_despawn = True
            return

        # If the plot no longer exists or is already built, return home.
        if not self.target_building or getattr(self.target_building, "hp", 0) <= 0:
            self.phase = BuilderPeasantPhase.RETURN_TO_CASTLE
        elif getattr(self.target_building, "is_constructed", False):
            self.phase = BuilderPeasantPhase.RETURN_TO_CASTLE

        if self.phase == BuilderPeasantPhase.MOVE_TO_PLOT:
            tx, ty = float(self.target_building.center_x), float(self.target_building.center_y)
            reached = self.move_towards(tx, ty, dt)
            self.state = PeasantState.MOVING
            if reached or self._adjacent_to_building(self.target_building):
                self.phase = BuilderPeasantPhase.BUILDING
            return

        if self.phase == BuilderPeasantPhase.BUILDING:
            self.state = PeasantState.WORKING
            if hasattr(self.target_building, "start_construction"):
                self.target_building.start_construction()
            if hasattr(self.target_building, "apply_work"):
                done = self.target_building.apply_work(dt, percent_per_sec=0.10)
                if done:
                    # Plot is now a normal constructed building; release builder-only lock.
                    if hasattr(self.target_building, "requires_builder_peasant"):
                        self.target_building.requires_builder_peasant = False
                    self.target_building = None
                    self.phase = BuilderPeasantPhase.RETURN_TO_CASTLE
            return

        if self.phase == BuilderPeasantPhase.RETURN_TO_CASTLE:
            cx = float(getattr(self.castle, "center_x", 0.0))
            cy = float(getattr(self.castle, "center_y", 0.0))
            reached = self.move_towards(cx, cy, dt)
            self.state = PeasantState.MOVING
            if reached or self.distance_to(cx, cy) <= TILE_SIZE * 1.5:
                self.phase = BuilderPeasantPhase.DESPAWN
                self.should_despawn = True
            return

