"""Shopping behavior extracted from ``BasicAI``."""

from __future__ import annotations

from typing import Any

from game.entities.hero import HeroState
from game.sim.timebase import now_ms as sim_now_ms

from ai.behaviors.movement import route_to_building
from ai.behaviors.view_compat import as_ai_view, view_to_legacy_context
from ai.contracts import HeroTask, TargetType, assign_hero_task
from game.sim.hero_commands import HeroPurchaseCommand

# WK127-T2: sim-time lockout stamped by a completed shopping trip that bought
# NOTHING — breaks the zero-purchase marketplace orbit (want predicates firing
# below the buy rules). Respected by go_shopping, _idle_shopping, and
# moment_shopping_opportunity.
ZERO_PURCHASE_SHOP_COOLDOWN_MS = 60_000


def shop_cooldown_active(hero: Any) -> bool:
    """True while the hero's zero-purchase shopping cooldown (sim-time) is live."""
    try:
        until = int(getattr(hero, "_shop_cooldown_until_ms", 0) or 0)
    except (TypeError, ValueError):
        until = 0
    return int(sim_now_ms()) < until


def blacksmith_has_affordable_upgrade(hero: Any, building: Any) -> bool:
    """True iff ``building`` sells a strict weapon/armor upgrade ``hero`` can
    afford right now — mirrors do_shopping's priority-3/4 buy rules so idle
    heroes only walk to the blacksmith when a purchase can actually happen."""
    if not hasattr(building, "get_available_items"):
        return False
    current_attack = hero.weapon.get("attack", 0) if hero.weapon else 0
    current_defense = hero.armor.get("defense", 0) if hero.armor else 0
    for item in building.get_available_items():
        if hero.gold < item.get("price", 0):
            continue
        if item.get("type") == "weapon" and item.get("attack", 0) > current_attack:
            return True
        if item.get("type") == "armor" and item.get("defense", 0) > current_defense:
            return True
    return False


def find_marketplace_with_potions(buildings: list[Any]) -> Any | None:
    """Find a marketplace that can sell potions."""
    for building in buildings:
        if building.building_type == "marketplace":
            if hasattr(building, "potions_researched") and building.potions_researched:
                return building
    return None


def find_blacksmith(buildings: list[Any], hero: Any = None) -> object | None:
    """Find a blacksmith for weapon/armor purchases."""
    for building in buildings:
        if building.building_type == "blacksmith":
            if hasattr(building, "is_constructed") and not building.is_constructed:
                continue
            return building
    return None


def go_shopping(ai: Any, hero: Any, item_name: str, view: Any) -> None:
    """Send hero to marketplace or blacksmith to buy an item."""
    # WK127-T2: the LLM/fallback buy_item path respects the zero-purchase
    # cooldown — the last trip proved nothing is buyable; stay in the idle
    # pipeline instead of re-orbiting the shop.
    if shop_cooldown_active(hero):
        return
    view = as_ai_view(view)
    buildings = view.buildings
    world = view.world

    target_building = None
    item_lower = (item_name or "").lower()
    if "potion" in item_lower:
        target_building = find_marketplace_with_potions(buildings)
    else:
        target_building = find_blacksmith(buildings, hero)
        
    if not target_building:
        for building in buildings:
            if building.building_type == "marketplace":
                target_building = building
                break

    if target_building:
        route_to_building(hero, world, buildings, target_building)
        hero.state = HeroState.MOVING
        # WK64 (audit item 15): author the task via the typed HeroTask API.
        # assign_hero_task serializes to the identical legacy dict shape so
        # hero.target stays a dict and handle_shopping_arrival (which reads
        # marketplace/blacksmith) is unaffected.
        task = HeroTask(
            type=TargetType.SHOPPING,
            target_ref=target_building,
            payload={
                "item": item_name,
                "marketplace": target_building if target_building.building_type == "marketplace" else None,
                "blacksmith": target_building if target_building.building_type == "blacksmith" else None,
                "shop_building": target_building,
            },
        )
        assign_hero_task(hero, task)


def do_shopping(ai: Any, hero: Any, building: Any, view: Any) -> bool:
    """Actually perform shopping at a marketplace or blacksmith.

    WK67 Move 6 (Wave 3): the hero/economy write is no longer performed here.
    Each priority branch proposes a :class:`~game.sim.hero_commands.HeroPurchaseCommand`
    to the sim-owned, SYNCHRONOUS command sink (``view.commands``). The sink
    applies the purchase immediately (``hero.buy_item`` + ``economy.hero_purchase``
    inside the sim-owned applier) and returns whether it succeeded, so
    ``hero.gold`` updates before the next priority branch's affordability check —
    byte-identical to the original inline ``hero.buy_item`` + ``economy.hero_purchase``
    sequence (priority order and between-purchase gold gating unchanged). The AI
    no longer holds ``economy`` and never mutates hero/economy state directly.

    ``view`` is the :class:`~game.sim.ai_view.AiGameView` threaded from the
    Move-5 migration (it carries ``view.commands``). The post-shopping journey
    trigger still consumes the legacy/bridge context mapping, projected from the
    view via :func:`~ai.behaviors.view_compat.view_to_legacy_context`.
    """
    view = as_ai_view(view)
    sink = view.commands
    # Support both marketplace and blacksmith (both have get_available_items).
    if not hasattr(building, "get_available_items"):
        return False
    items = building.get_available_items()
    purchased_types: set[str] = set()

    # WK131: sell carried backpack loot FIRST (anything in the backpack is by
    # construction unusable — usable loot was auto-equipped on receive). The
    # proceeds (hero.add_gold, 25% tax reserved) fund the upgrade checks below.
    # Empty backpack -> exact no-op, so the WK67 digest scenario (no loot
    # sources) is byte-identical.
    if getattr(hero, "backpack", None) and hasattr(hero, "sell_backpack_items"):
        hero.sell_backpack_items(building)

    # Priority 1: Buy a potion if we have none.
    if hero.potions == 0 and hero.gold >= 20:
        for item in items:
            if item["type"] == "potion":
                if sink.propose(HeroPurchaseCommand(hero.hero_id, item)):
                    purchased_types.add("potion")
                    break

    # Priority 2: Buy extra potions if rich.
    if hero.gold >= 50 and hero.potions < 2:
        for item in items:
            if item["type"] == "potion" and hero.gold >= item["price"]:
                if sink.propose(HeroPurchaseCommand(hero.hero_id, item)):
                    purchased_types.add("potion")
                    break

    # Priority 3: Weapon upgrade.
    for item in items:
        if item["type"] == "weapon" and hero.gold >= item["price"]:
            current_attack = hero.weapon.get("attack", 0) if hero.weapon else 0
            if item["attack"] > current_attack:
                if sink.propose(HeroPurchaseCommand(hero.hero_id, item)):
                    purchased_types.add("weapon")
                    break

    # Priority 4: Armor upgrade.
    for item in items:
        if item["type"] == "armor" and hero.gold >= item["price"]:
            current_defense = hero.armor.get("defense", 0) if hero.armor else 0
            if item["defense"] > current_defense:
                if sink.propose(HeroPurchaseCommand(hero.hero_id, item)):
                    purchased_types.add("armor")
                    break

    # WK127-T2: a trip that bought nothing means the want/buy predicates are
    # unsatisfiable right now — stamp the sim-time cooldown so the idle/LLM
    # pipelines don't immediately re-fire shopping (zero-purchase orbit).
    if not purchased_types:
        hero._shop_cooldown_until_ms = int(sim_now_ms()) + ZERO_PURCHASE_SHOP_COOLDOWN_MS

    # Post-shopping journey trigger (full health + recent purchase).
    return ai.journey_behavior._maybe_start_journey(
        ai, hero, view_to_legacy_context(view), purchased_types
    )
