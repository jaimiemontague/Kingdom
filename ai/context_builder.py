"""
Builds context dictionaries for LLM decision making.
"""
from config import TILE_SIZE
from game.sim.timebase import now_ms as sim_now_ms


class ContextBuilder:
    """Builds structured context for LLM prompts."""

    @staticmethod
    def _summarize_bounties(hero, game_state: dict, limit: int = 5) -> list[dict]:
        """Create a JSON-friendly bounty list with distance/risk/validity for LLM use."""
        bounties = game_state.get("bounties", []) or []
        buildings = game_state.get("buildings", []) or []
        enemies = game_state.get("enemies", []) or []
        now_ms = sim_now_ms()

        out = []
        for b in bounties:
            try:
                if hasattr(b, "get_goal_position"):
                    gx, gy = b.get_goal_position(buildings)
                else:
                    gx, gy = float(getattr(b, "x", 0.0)), float(getattr(b, "y", 0.0))
                dist_px = float(hero.distance_to(gx, gy))
            except Exception:
                gx, gy = 0.0, 0.0
                dist_px = 0.0

            risk = 0.0
            if hasattr(b, "estimate_risk"):
                try:
                    risk = float(b.estimate_risk(enemies))
                except Exception:
                    risk = 0.0

            valid = True
            if hasattr(b, "is_valid"):
                try:
                    valid = bool(b.is_valid(buildings))
                except Exception:
                    valid = True

            assigned_active = False
            if hasattr(b, "is_assigned_active"):
                try:
                    assigned_active = bool(b.is_assigned_active(now_ms, ttl_ms=15000))
                except Exception:
                    assigned_active = False

            out.append(
                {
                    "id": getattr(b, "bounty_id", None),
                    "type": getattr(b, "bounty_type", "explore"),
                    "reward": int(getattr(b, "reward", 0)),
                    "distance_tiles": round(dist_px / TILE_SIZE, 1) if TILE_SIZE else 0.0,
                    "risk": round(risk, 2),
                    "valid": valid,
                    "assigned_to": getattr(b, "assigned_to", None),
                    "assigned_active": assigned_active,
                }
            )

        # Valid first, then higher value adjusted by distance
        out.sort(key=lambda s: (not s["valid"], s["distance_tiles"], -s["reward"]))
        return out[: max(0, int(limit))]
    
    @staticmethod
    def build_hero_context(hero, game_state: dict) -> dict:
        """Build full context for a hero's decision."""
        context = {
            "hero": {
                "id": getattr(hero, "hero_id", None),
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
            # Keep raw objects for in-engine use/debug, but also provide a JSON-friendly summary for the LLM.
            "available_bounties": game_state.get("bounties", []),
            "bounty_options": ContextBuilder._summarize_bounties(hero, game_state, limit=5),
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
                        "id": getattr(other_hero, "hero_id", None),
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

        # Bounties (Majesty-style control lever)
        if context.get("bounty_options"):
            summary += "\nAvailable Bounties:\n"
            for b in context["bounty_options"][:5]:
                valid = "✓" if b.get("valid", True) else "✗"
                assigned = ""
                if b.get("assigned_to") and b.get("assigned_active"):
                    assigned = f" (assigned to {b['assigned_to']})"
                summary += (
                    f"  [{valid}] {b.get('type','explore')} reward=${b.get('reward',0)} "
                    f"dist={b.get('distance_tiles','?')} tiles risk={b.get('risk',0)}{assigned}\n"
                )
        
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

    @staticmethod
    def build_inputs_summary(context: dict) -> str:
        """
        Build a compact, stable one-liner summarizing the inputs that led to a decision.        This is intended for UI/debug logs (not for the LLM prompt).
        """
        hero = context.get("hero", {}) or {}
        inv = context.get("inventory", {}) or {}
        sit = context.get("situation", {}) or {}

        enemies = context.get("nearby_enemies", []) or []
        nearest_enemy = enemies[0] if enemies else None

        hp_pct = hero.get("health_percent", "?")
        gold = hero.get("gold", "?")
        potions = inv.get("potions", "?")
        in_combat = bool(sit.get("in_combat", False))
        can_shop = bool(sit.get("can_shop", False))
        outnumbered = bool(sit.get("outnumbered", False))

        nearest = ""
        if nearest_enemy:
            et = nearest_enemy.get("type", "?")
            d = nearest_enemy.get("distance_tiles", "?")
            nearest = f" nearest_enemy={et}@{d}t"
        return (
            f"hp={hp_pct}% gold={gold} potions={potions} "
            f"in_combat={int(in_combat)} outnumbered={int(outnumbered)} can_shop={int(can_shop)}"
            f"{nearest}"
        )