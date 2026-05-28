"""Ordered system runner (WK64, audit item 22).

Drives a fixed-order tuple of game systems through the shared SystemContext +
``update(ctx, dt)`` protocol. Only systems whose ``update`` is proven equivalent
to their previous bespoke call live here; systems with surrounding orchestration
(combat event routing, spawn capping, bounty/HUD side effects, nature tile
bookkeeping, POI's two-method tick) remain called directly in SimEngine.update()
and are documented exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from game.systems.protocol import GameSystem, SystemContext


@dataclass(slots=True)
class SystemRunner:
    systems: Sequence[GameSystem]

    def update_all(self, ctx: SystemContext, dt: float) -> None:
        for system in self.systems:
            system.update(ctx, dt)
