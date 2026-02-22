"""Shopping behavior extracted from ``BasicAI``."""

from __future__ import annotations

from typing import Any

from config import TILE_SIZE
from game.entities.hero import HeroState
from game.systems.navigation import best_adjacent_tile


def find_marketplace_with_potions(buildings: list[Any]) -> Any | None:
    """Find a marketplace that can sell potions."""
    for building in buildings:
        if building.building_type == "marketplace":
            if hasattr(building, "potions_researched") and building.potions_researched:
                return building
    return None


def find_blacksmith_with_upgrades(buildings: list[Any], hero: Any = None) -> object | None:
    """V1.3 extension: find a blacksmith with available upgrades for the hero."""
    for building in buildings:
        if building.building_type == "blacksmith":
            # Check if upgrades are researched (Agent 05 will implement this).
            # For now, assume upgrades are available if weapon/armor upgrades are researched.
            if hero is not None:
                # Check if hero needs weapon upgrade.
                if hasattr(building, "weapon_upgrades_researched") and building.weapon_upgrades_researched:
                    if not hero.weapon or (
                        hasattr(building, "has_better_weapon") and building.has_better_weapon(hero)
                    ):
                        return building
                # Check if hero needs armor upgrade.
                if hasattr(building, "armor_upgrades_researched") and building.armor_upgrades_researched:
                    if not hero.armor or (
                        hasattr(building, "has_better_armor") and building.has_better_armor(hero)
                    ):
                        return building
            else:
                # Legacy: just check if upgrades are researched (no hero check).
                if hasattr(building, "weapon_upgrades_researched") and building.weapon_upgrades_researched:
                    return building
                if hasattr(building, "armor_upgrades_researched") and building.armor_upgrades_researched:
                    return building
    return None


def go_shopping(ai: Any, hero: Any, item_name: str, game_state: dict) -> None:
    """Send hero to marketplace or blacksmith to buy an item."""
    buildings = game_state.get("buildings", [])
    world = game_state.get("world")

    target_building = None
    item_lower = (item_name or "").lower()
    if "potion" in item_lower:
        target_building = find_marketplace_with_potions(buildings)
    else:
        target_building = find_blacksmith_with_upgrades(buildings, hero)
        
    if not target_building:
        for building in buildings:
            if building.building_type == "marketplace":
                target_building = building
                break

    if target_building:
        if world:
            adj = best_adjacent_tile(world, buildings, target_building, hero.x, hero.y)
            if adj:
                hero.target_position = (
                    adj[0] * TILE_SIZE + TILE_SIZE / 2,
                    adj[1] * TILE_SIZE + TILE_SIZE / 2,
                )
            else:
                hero.target_position = (target_building.center_x, target_building.center_y)
        else:
            hero.target_position = (target_building.center_x, target_building.center_y)
        hero.state = HeroState.MOVING
        hero.target = {
            "type": "shopping",
            "item": item_name,
            "marketplace": target_building if target_building.building_type == "marketplace" else None,
            "blacksmith": target_building if target_building.building_type == "blacksmith" else None,
            "shop_building": target_building,
        }


def do_shopping(ai: Any, hero: Any, building: Any, game_state: dict) -> bool:
    """Actually perform shopping at a marketplace or blacksmith."""
    economy = game_state.get("economy")
    # Support both marketplace and blacksmith (both have get_available_items).
    if not hasattr(building, "get_available_items"):
        return False
    items = building.get_available_items()
    purchased_types: set[str] = set()

    # Priority 1: Buy a potion if we have none.
    if hero.potions == 0 and hero.gold >= 20:
        for item in items:
            if item["type"] == "potion":
                if hero.buy_item(item):
                    purchased_types.add("potion")
                    if economy:
                        economy.hero_purchase(hero.name, item["name"], item["price"])
                    break

    # Priority 2: Buy extra potions if rich.
    if hero.gold >= 50 and hero.potions < 2:
        for item in items:
            if item["type"] == "potion" and hero.gold >= item["price"]:
                if hero.buy_item(item):
                    purchased_types.add("potion")
                    if economy:
                        economy.hero_purchase(hero.name, item["name"], item["price"])
                    break

    # Priority 3: Weapon upgrade.
    for item in items:
        if item["type"] == "weapon" and hero.gold >= item["price"]:
            current_attack = hero.weapon.get("attack", 0) if hero.weapon else 0
            if item["attack"] > current_attack:
                if hero.buy_item(item):
                    purchased_types.add("weapon")
                    if economy:
                        economy.hero_purchase(hero.name, item["name"], item["price"])
                    break

    # Priority 4: Armor upgrade.
    for item in items:
        if item["type"] == "armor" and hero.gold >= item["price"]:
            current_defense = hero.armor.get("defense", 0) if hero.armor else 0
            if item["defense"] > current_defense:
                if hero.buy_item(item):
                    purchased_types.add("armor")
                    if economy:
                        economy.hero_purchase(hero.name, item["name"], item["price"])
                    break

    # Post-shopping journey trigger (full health + recent purchase).
    return ai.journey_behavior._maybe_start_journey(ai, hero, game_state, purchased_types)
