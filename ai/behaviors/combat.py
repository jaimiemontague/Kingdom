"""Combat state behavior extracted from ``BasicAI`` (WK82 Round D-2).

Pure move of ``BasicAI.handle_fighting``: the function takes the ``BasicAI``
coordinator as ``ai`` and behaves byte-identically. The nested
``_chase_goal_unchanged`` helper moves with it.

Leaf imports only (no ``ai.behaviors`` package facade) to avoid the import
cycle the audit warns about (``ai.behaviors.__init__`` can pull ``llm_bridge``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import TILE_SIZE
from game.entities.hero import HeroState
from game.systems.navigation import best_adjacent_tile

if TYPE_CHECKING:
    from ai.basic_ai import BasicAI


def handle_fighting(ai: "BasicAI", hero, view) -> None:
    """Handle fighting state."""
    # V1.3 extension: prefer using potions before health gets too low.
    if hero.health_percent < 0.6 and hero.potions > 0:
        hero.use_potion()
        ai._debug_log(f"{hero.name} -> using potion in combat (health={hero.health_percent:.1%})")

    # Check if target is still valid.
    # WK61-FIX: Buildings now have is_alive (WK61-BUG-003). Only fight enemies
    # or lairs; if target is a non-lair building, drop it immediately.
    if hero.target and hasattr(hero.target, "is_alive"):
        if hasattr(hero.target, "building_type") and not getattr(hero.target, "is_lair", False):
            # Non-lair building target in FIGHTING state is invalid — go idle.
            hero.target = None
            hero.state = HeroState.IDLE
            return
        if not hero.target.is_alive:
            hero.target = None
            hero.state = HeroState.IDLE
            return

        # Check if target in range.
        dist = hero.distance_to(hero.target.x, hero.target.y)
        if dist > hero.attack_range:
            # Move towards target (for lairs/buildings, approach adjacent tile to avoid unreachable goals).
            buildings = view.buildings
            world = view.world

            def _chase_goal_unchanged(nx: float, ny: float) -> bool:
                """Avoid rewriting target_position every tick when the goal tile is stable (WK22 path churn)."""
                prev = getattr(hero, "target_position", None)
                if prev is None or world is None:
                    return False
                ngx, ngy = world.world_to_grid(nx, ny)
                ogx, ogy = world.world_to_grid(prev[0], prev[1])
                return (ngx, ngy) == (ogx, ogy)

            if getattr(hero.target, "is_lair", False):
                if world:
                    adj = best_adjacent_tile(world, buildings, hero.target, hero.x, hero.y)
                    if adj:
                        new_tx = adj[0] * TILE_SIZE + TILE_SIZE / 2
                        new_ty = adj[1] * TILE_SIZE + TILE_SIZE / 2
                    else:
                        new_tx, new_ty = hero.target.x, hero.target.y
                else:
                    new_tx, new_ty = hero.target.x, hero.target.y
                if _chase_goal_unchanged(new_tx, new_ty):
                    hero.state = HeroState.MOVING
                    return
                hero.target_position = (new_tx, new_ty)
            else:
                new_tx, new_ty = hero.target.x, hero.target.y
                if _chase_goal_unchanged(new_tx, new_ty):
                    hero.state = HeroState.MOVING
                    return
                hero.target_position = (new_tx, new_ty)
            hero.state = HeroState.MOVING
    else:
        # Find new target.
        hero.state = HeroState.IDLE
