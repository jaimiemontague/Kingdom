"""
Shared protocol and context contract for tick-driven systems.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
    # WK64 (audit item 22): widened so all systems can share one context instead
    # of bespoke tick() signatures. All new fields are defaulted so existing
    # SystemContext(...) call sites and tests keep working unchanged.
    peasants: list = field(default_factory=list)
    guards: list = field(default_factory=list)
    bounties: list = field(default_factory=list)
    pois: list = field(default_factory=list)
    rubble_records: list = field(default_factory=list)
    lairs: list = field(default_factory=list)
    castle: object | None = None


class GameSystem(Protocol):
    def update(self, ctx: SystemContext, dt: float) -> None:
        ...
