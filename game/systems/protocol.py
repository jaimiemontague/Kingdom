"""
Shared protocol and context contract for tick-driven systems.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from game.events import EventBus


@dataclass
class SystemContext:
    heroes: list
    enemies: list
    buildings: list
    world: object
    economy: object
    event_bus: EventBus


class GameSystem(Protocol):
    def update(self, ctx: SystemContext, dt: float) -> None:
        ...
