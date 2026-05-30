"""Retreat + deferred-task recovery behavior extracted from ``BasicAI`` (WK82 Round D-2).

Pure move of ``BasicAI.handle_retreating`` and ``BasicAI._finalize_deferred_task``:
each function takes the ``BasicAI`` coordinator as ``ai`` and behaves
byte-identically.

Leaf imports only (no ``ai.behaviors`` package facade) to avoid the import
cycle the audit warns about (``ai.behaviors.__init__`` can pull ``llm_bridge``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import TILE_SIZE
from game.entities.hero import HeroState
from game.sim.determinism import get_rng

if TYPE_CHECKING:
    from ai.basic_ai import BasicAI


def handle_retreating(ai: "BasicAI", hero, view) -> None:
    """Handle retreating state - flee to safety."""
    buildings = view.buildings

    # V1.3 extension: use potion during retreat if available and health is low.
    if hero.health_percent < 0.7 and hero.potions > 0:
        hero.use_potion()
        ai._debug_log(f"{hero.name} -> using potion while retreating (health={hero.health_percent:.1%})")

    nearest_safe = None
    nearest_dist = float("inf")

    for building in buildings:
        if building.building_type in ["castle", "marketplace"]:
            dist = hero.distance_to(building.center_x, building.center_y)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_safe = building

    if nearest_safe:
        if nearest_dist < TILE_SIZE * 2:
            hero.state = HeroState.IDLE
        else:
            hero.target_position = (nearest_safe.center_x, nearest_safe.center_y)


def finalize_deferred_task(ai: "BasicAI", hero, view) -> None:
    """Run deferred task on pop-out (WK11): shopping purchase, get_drink payment, or clear rest_inn."""
    pending = getattr(hero, "pending_task", None)
    pending_building = getattr(hero, "pending_task_building", None)
    if not pending or not pending_building:
        return
    if pending == "shopping":
        # WK67 Move 6: do_shopping proposes the purchase through the sim-owned
        # synchronous command sink (view.commands), so it takes the AiGameView
        # directly now (it projects its own legacy context for the journey
        # trigger). The view carries no economy/sim/engine.
        ai.shopping_behavior.do_shopping(ai, hero, pending_building, view)
    elif pending == "get_drink":
        rng = get_rng("ai_basic")
        cost = int(rng.randint(5, 10))
        cost = min(cost, hero.gold)
        hero.gold -= cost
        current = getattr(pending_building, "gold_earned_from_drinks", 0)
        setattr(pending_building, "gold_earned_from_drinks", current + cost)
    # rest_inn: nothing to finalize (healing happened while inside)
    setattr(hero, "pending_task", None)
    setattr(hero, "pending_task_building", None)
    hero.state = HeroState.IDLE
