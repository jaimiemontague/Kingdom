"""
Builds context dictionaries for LLM decision making.
"""
from config import TILE_SIZE


class ContextBuilder:
    """Builds structured context for LLM prompts."""
    
    @staticmethod
    def build_hero_context(hero, game_state: dict) -> dict:
        """Build full context for a hero's decision."""
        context = {
            "hero": {
                "name": hero.name,
                "class": hero.hero_class,
                "level": hero.level,
                "hp": hero.hp,
                "max_hp": hero.max_hp,
                "health_percent": round(hero.health_percent * 100),
                "gold": hero.gold,
                "attack": hero.attack,
                "defense": hero.defense,
                "xp": hero.xp,
                "xp_to_level": hero.xp_to_level,
            },
            "inventory": {
                "weapon": hero.weapon["name"] if hero.weapon else "Fists",
                "weapon_attack": hero.weapon["attack"] if hero.weapon else 0,
                "armor": hero.armor["name"] if hero.armor else "None", 
                "armor_defense": hero.armor["defense"] if hero.armor else 0,
                "potions": hero.potions,
            },
            "personality": hero.personality,
            "current_state": hero.state.name,
            "nearby_enemies": [],
            "nearby_allies": [],
            "available_bounties": game_state.get("bounties", []),
            "shop_items": [],
            "distances": {},
        }
        
        # Add nearby enemies with details
        for enemy in game_state.get("enemies", []):
            if enemy.is_alive:
                dist = hero.distance_to(enemy.x, enemy.y)
                if dist < TILE_SIZE * 12:  # Within 12 tiles
                    context["nearby_enemies"].append({
                        "type": enemy.enemy_type,
                        "hp": enemy.hp,
                        "max_hp": enemy.max_hp,
                        "health_percent": round((enemy.hp / enemy.max_hp) * 100),
                        "attack": enemy.attack_power,
                        "distance_tiles": round(dist / TILE_SIZE, 1),
                        "is_attacking_me": enemy.target == hero,
                    })
        
        # Sort by distance
        context["nearby_enemies"].sort(key=lambda e: e["distance_tiles"])
        
        # Add nearby allies
        for other_hero in game_state.get("heroes", []):
            if other_hero != hero and other_hero.is_alive:
                dist = hero.distance_to(other_hero.x, other_hero.y)
                if dist < TILE_SIZE * 10:
                    context["nearby_allies"].append({
                        "name": other_hero.name,
                        "class": other_hero.hero_class,
                        "health_percent": round(other_hero.health_percent * 100),
                        "distance_tiles": round(dist / TILE_SIZE, 1),
                    })
        
        # Add building distances and shop items
        for building in game_state.get("buildings", []):
            dist = hero.distance_to(building.center_x, building.center_y)
            
            if building.building_type == "castle":
                context["distances"]["castle"] = round(dist / TILE_SIZE, 1)
            elif building.building_type == "marketplace":
                context["distances"]["marketplace"] = round(dist / TILE_SIZE, 1)
                if dist < TILE_SIZE * 6:
                    context["shop_items"] = [
                        {
                            "name": item["name"],
                            "type": item["type"],
                            "price": item["price"],
                            "can_afford": hero.gold >= item["price"],
                        }
                        for item in building.get_available_items()
                    ]
            elif building.building_type == "warrior_guild":
                context["distances"]["warrior_guild"] = round(dist / TILE_SIZE, 1)
        
        # Add situational flags
        context["situation"] = {
            "in_combat": len([e for e in context["nearby_enemies"] if e["distance_tiles"] < 2]) > 0,
            "low_health": hero.health_percent < 0.5,
            "critical_health": hero.health_percent < 0.25,
            "has_potions": hero.potions > 0,
            "can_shop": len(context["shop_items"]) > 0,
            "near_safety": context["distances"].get("castle", 999) < 5 or context["distances"].get("marketplace", 999) < 5,
            "enemies_nearby": len(context["nearby_enemies"]) > 0,
            "outnumbered": len(context["nearby_enemies"]) > len(context["nearby_allies"]) + 1,
        }
        
        return context
    
    @staticmethod
    def build_summary(context: dict) -> str:
        """Build a human-readable summary of the context."""
        hero = context["hero"]
        inv = context["inventory"]
        sit = context["situation"]
        
        summary = f"""
{hero['name']} the {hero['class'].title()} (Level {hero['level']})
Health: {hero['hp']}/{hero['max_hp']} ({hero['health_percent']}%)
Gold: {hero['gold']} | Attack: {hero['attack']} | Defense: {hero['defense']}
Weapon: {inv['weapon']} | Armor: {inv['armor']} | Potions: {inv['potions']}
Personality: {context['personality']}

Current State: {context['current_state']}
"""
        
        if context["nearby_enemies"]:
            summary += "\nNearby Enemies:\n"
            for enemy in context["nearby_enemies"][:5]:
                summary += f"  - {enemy['type']} ({enemy['health_percent']}% HP) at {enemy['distance_tiles']} tiles"
                if enemy["is_attacking_me"]:
                    summary += " [ATTACKING YOU]"
                summary += "\n"
        
        if context["nearby_allies"]:
            summary += "\nNearby Allies:\n"
            for ally in context["nearby_allies"]:
                summary += f"  - {ally['name']} ({ally['health_percent']}% HP) at {ally['distance_tiles']} tiles\n"
        
        if context["shop_items"]:
            summary += "\nShop Items Available:\n"
            for item in context["shop_items"]:
                afford = "✓" if item["can_afford"] else "✗"
                summary += f"  [{afford}] {item['name']} ({item['type']}) - {item['price']}g\n"
        
        summary += f"\nDistances: Castle {context['distances'].get('castle', '?')} tiles, "
        summary += f"Market {context['distances'].get('marketplace', '?')} tiles\n"
        
        # Situation flags
        flags = []
        if sit["in_combat"]:
            flags.append("IN COMBAT")
        if sit["critical_health"]:
            flags.append("CRITICAL HEALTH")
        elif sit["low_health"]:
            flags.append("LOW HEALTH")
        if sit["outnumbered"]:
            flags.append("OUTNUMBERED")
        if sit["near_safety"]:
            flags.append("NEAR SAFETY")
        
        if flags:
            summary += f"\nStatus: {', '.join(flags)}"
        
        return summary.strip()

