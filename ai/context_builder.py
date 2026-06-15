"""
Builds context dictionaries for LLM decision making.
"""
import math

from config import FOOD_MEAL_COST_GOLD, TILE_SIZE
from ai.quest_chain_context import attach_blackbanner_chain_facts, summarize_quest_chains
from ai.rescue_revenge_context import summarize_story_facts
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
        hb = getattr(hero, "home_building", None)
        home_bt_raw = getattr(hb, "building_type", "") if hb is not None else ""
        home_building_type = str(getattr(home_bt_raw, "value", home_bt_raw) or "").strip().lower()

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
                "home_building_type": home_building_type,
            },
            "inventory": {
                "weapon": hero.weapon["name"] if hero.weapon else "Fists",
                "weapon_attack": hero.weapon["attack"] if hero.weapon else 0,
                "armor": hero.armor["name"] if hero.armor else "None",
                "armor_defense": hero.armor["defense"] if hero.armor else 0,
                "potions": hero.potions,
                # WK134: WK131 item slots were reaching only the autonomous
                # prompts (via HeroInventorySnapshot); the direct-prompt (chat)
                # blob embeds THIS dict, so carry them here too. Additive keys
                # only — every existing reader (fallback decisions, mock
                # responders, inputs_summary) reads named keys.
                "accessory": (
                    (getattr(hero, "accessory", None) or {}).get("name", "")
                    if isinstance(getattr(hero, "accessory", None), dict)
                    else ""
                ),
                "backpack": [
                    str(getattr(it, "name", it))
                    for it in (getattr(hero, "backpack", None) or ())
                ],
            },
            "personality": hero.personality,
            "current_state": hero.state.name,
            "nearby_enemies": [],
            "nearby_allies": [],
            # Keep raw objects for in-engine use/debug, but also provide a JSON-friendly summary for the LLM.
            "available_bounties": game_state.get("bounties", []),
            "bounty_options": ContextBuilder._summarize_bounties(hero, game_state, limit=5),
            "shop_items": [],
            "market_catalog_items": [],
            "distances": {},
        }

        quest_chains = game_state.get("quest_chains") or ()
        if quest_chains:
            summarized_chains = summarize_quest_chains(quest_chains)
            if summarized_chains:
                boss_encounters = game_state.get("boss_encounters") or ()
                elite_enemies = game_state.get("elite_enemies") or game_state.get("elite_encounters") or ()
                summarized_chains = [
                    attach_blackbanner_chain_facts(
                        chain,
                        boss_encounters=boss_encounters,
                        elite_enemies=elite_enemies,
                    )
                    for chain in summarized_chains
                ]
                context["quest_chains"] = summarized_chains

        story_facts = summarize_story_facts(
            captured_heroes=game_state.get("captured_heroes") or (),
            rescue_opportunities=game_state.get("rescue_opportunities") or (),
            boss_kill_memories=game_state.get("boss_kill_memories") or (),
            revenge_opportunities=game_state.get("revenge_opportunities") or (),
        )
        if story_facts:
            context.update(story_facts)
        
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
            elif building.building_type in (
                "warrior_guild",
                "ranger_guild",
                "rogue_guild",
                "wizard_guild",
            ):
                context["distances"][building.building_type] = round(dist / TILE_SIZE, 1)

        # WK55: Nearby POI awareness for LLM decisions (discovered + seen-fog unknowns).
        from ai.behaviors.poi_awareness import get_nearby_pois_for_hero
        context["nearby_pois"] = get_nearby_pois_for_hero(hero, game_state)

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
            "hunger_urgent": bool(getattr(hero, "hunger_urgent", False)),
            "can_afford_meal": int(getattr(hero, "gold", 0) or 0) >= int(FOOD_MEAL_COST_GOLD),
        }

        # 3A: Location context (wk14 Persona and Presence)
        building_context_map = {
            "inn": "resting at the bar",
            "marketplace": "browsing wares",
            "warrior_guild": "training in the guild",
            "ranger_guild": "training in the guild",
            "rogue_guild": "training in the guild",
            "wizard_guild": "training in the guild",
            "blacksmith": "watching the smith work",
        }
        if getattr(hero, "is_inside_building", False) and getattr(hero, "inside_building", None) is not None:
            building = hero.inside_building
            btype = getattr(building, "building_type", "") or ""
            context["current_location"] = btype.replace("_", " ").title()
            occupants = getattr(building, "occupants", []) or []
            context["building_occupants"] = [getattr(h, "name", str(h)) for h in occupants if h is not hero]
            context["building_context"] = building_context_map.get(btype, "inside a building")
        else:
            context["current_location"] = "outdoors"
            context["building_occupants"] = []
            context["building_context"] = ""
        context["player_is_present"] = game_state.get("micro_view_building") is getattr(hero, "inside_building", None)

        # WK18: Hero stat block matching left panel UI for LLM prompt.
        context["hero_stat_block"] = ContextBuilder.build_hero_stat_block(context)

        # WK50 Phase 2B: bounded known places for direct prompt validation (no raw hero objects).
        from game.sim.hero_profile import build_hero_profile_snapshot
        from game.systems import hero_memory as _hm

        snap = build_hero_profile_snapshot(hero, game_state, now_ms=sim_now_ms())
        from game.sim.hero_profile import select_known_places_for_llm

        hero_home_place_id = ""
        if hb is not None and home_building_type:
            gx = int(getattr(hb, "grid_x", 0))
            gy = int(getattr(hb, "grid_y", 0))
            hero_home_place_id = _hm.stable_place_id(home_building_type, gx, gy)

        # Reserve one slot when we prepend hire/spawn guild home that is missing from the
        # profile-derived slice — otherwise rows[:8] would drop priority POIs (inn, marketplace).
        llm_place_limit = 8
        if hero_home_place_id:
            cand = select_known_places_for_llm(snap.known_places, limit=8)
            cand_ids = {str(getattr(p, "place_id", "")).strip().lower() for p in cand}
            if hero_home_place_id.strip().lower() not in cand_ids:
                llm_place_limit = 7

        llm_places = select_known_places_for_llm(snap.known_places, limit=llm_place_limit)
        rows = [
            {
                "place_id": str(getattr(p, "place_id", "")),
                "place_type": str(getattr(p, "place_type", "")),
                "display_name": str(getattr(p, "display_name", "")),
            }
            for p in llm_places
        ]
        if hb is not None and home_building_type and hero_home_place_id:
            existing_ids = {str(r.get("place_id", "")).strip().lower() for r in rows}
            if hero_home_place_id.lower() not in existing_ids:
                dn = home_building_type.replace("_", " ").strip().title() or "Home"
                rows.insert(
                    0,
                    {
                        "place_id": hero_home_place_id,
                        "place_type": home_building_type,
                        "display_name": dn,
                    },
                )
        context["hero_home_place_id"] = hero_home_place_id
        known_llm_rows = rows[:8]
        context["known_places_llm"] = known_llm_rows

        # WK50 R17: Catalog + affordability at the remembered or nearest marketplace even when
        # `shop_items` is empty (hero not within TILE_SIZE*6). Keeps `can_shop` = in-range only.
        def _bt_lower(b) -> str:
            bt = getattr(b, "building_type", "")
            return str(getattr(bt, "value", bt) or "").strip().lower()

        market_buildings = [b for b in game_state.get("buildings", []) if _bt_lower(b) == "marketplace"]
        catalog_market = None
        for row in known_llm_rows:
            if str(row.get("place_type") or "").strip().lower() != "marketplace":
                continue
            pid = str(row.get("place_id") or "").strip()
            for mb in market_buildings:
                gx = int(getattr(mb, "grid_x", 0))
                gy = int(getattr(mb, "grid_y", 0))
                if _hm.stable_place_id("marketplace", gx, gy) == pid:
                    catalog_market = mb
                    break
            if catalog_market is not None:
                break
        if catalog_market is None and market_buildings:
            catalog_market = min(
                market_buildings,
                key=lambda b: hero.distance_to(b.center_x, b.center_y),
            )
        market_catalog_items: list[dict] = []
        if catalog_market is not None and hasattr(catalog_market, "get_available_items"):
            market_catalog_items = [
                {
                    "name": item["name"],
                    "type": item["type"],
                    "price": item["price"],
                    "can_afford": hero.gold >= item["price"],
                }
                for item in catalog_market.get_available_items()
            ]
        context["market_catalog_items"] = market_catalog_items
        return context
    
    @staticmethod
    def build_hero_stat_block(context: dict) -> str:
        """Build a compact hero stat block matching the left panel UI (WK18 LLM context)."""
        hero = context["hero"]
        inv = context["inventory"]
        state = context.get("current_state", "IDLE")
        location = context.get("current_location", "outdoors")
        lines = [
            f"{hero['name']} | {hero['class'].title()} Lv{hero['level']}",
            f"HP: {hero['hp']}/{hero['max_hp']} ({hero['health_percent']}%)",
            f"ATK: {hero['attack']}  DEF: {hero['defense']}",
            f"Gold: {hero['gold']}",
            f"Potions: {inv['potions']}  W: {inv['weapon']}  A: {inv['armor']}",
            f"State: {state}",
        ]
        if location != "outdoors":
            lines.append(f"Inside: {location}")
        return "\n".join(lines)

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
