"""Shared hero movement-routing helpers extracted from ``BasicAI`` behaviors.

WK74 Round C-2b: the "route hero to a building" block (best_adjacent_tile ->
set target_position to the adjacent-tile center, else the building center) was
copy-pasted across exploration/shopping/hunger/basic_ai. ``route_to_building``
is the single canonical implementation (verbatim from the marketplace block in
``exploration.handle_idle``); every byte-identical site calls it instead.
"""

from __future__ import annotations

from typing import Any

from config import TILE_SIZE
from game.systems.navigation import best_adjacent_tile


def route_to_building(hero: Any, world: Any, buildings: Any, building: Any) -> None:
    """Point ``hero.target_position`` at the best reachable tile beside ``building``.

    Reproduces the canonical "route hero to a building" block byte-for-byte:
    prefer the center of the nearest reachable adjacent tile, falling back to the
    building center when no adjacent tile is available (or ``world`` is missing).
    Does NOT set ``hero.state`` or ``hero.target`` -- callers keep that.
    """
    if world:
        adj = best_adjacent_tile(world, buildings, building, hero.x, hero.y)
        if adj:
            hero.target_position = (
                adj[0] * TILE_SIZE + TILE_SIZE / 2,
                adj[1] * TILE_SIZE + TILE_SIZE / 2,
            )
        else:
            hero.target_position = (building.center_x, building.center_y)
    else:
        hero.target_position = (building.center_x, building.center_y)
