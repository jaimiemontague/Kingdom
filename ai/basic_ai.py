"""
Basic AI state machine for hero movement and combat.
Handles routine behavior, defers important decisions to LLM.
"""
import math
import random
from game.entities.hero import HeroState
from game.systems.pathfinding import find_path, grid_to_world_path
from config import TILE_SIZE, HEALTH_THRESHOLD_FOR_DECISION, LLM_DECISION_COOLDOWN
from ai.context_builder import ContextBuilder
from game.systems.navigation import best_adjacent_tile

# Debug logging (set to True to see AI decision logs)
DEBUG_AI = False

_last_log = {}
def debug_log(msg, throttle_key=None):
    if not DEBUG_AI:
        return
    # Throttle repeated messages
    if throttle_key:
        import time
        now = time.time()
        if throttle_key in _last_log and now - _last_log[throttle_key] < 1.0:
            return
        _last_log[throttle_key] = now
    print(f"[AI] {msg}")


class BasicAI:
    """
    Handles basic hero AI behavior.
    Movement, pathfinding, and combat targeting are handled here.
    Strategic decisions are deferred to the LLM brain.
    """
    
    def __init__(self, llm_brain=None):
        self.llm_brain = llm_brain
        # Track each hero's personal patrol zone (assigned on first idle)
        self.hero_zones = {}  # hero.name -> (center_x, center_y)

        # Bounty pursuit tuning (prototype-friendly constants)
        self.bounty_assign_ttl_ms = 15000
        self.bounty_pick_cooldown_ms = 2500
        self.bounty_max_pursue_ms = 35000
        self.bounty_claim_radius_px = TILE_SIZE * 2
        
    def update(self, dt: float, heroes: list, game_state: dict):
        """Update AI for all heroes."""
        for hero in heroes:
            if not hero.is_alive:
                continue
            self.update_hero(hero, dt, game_state)
    
    def assign_patrol_zone(self, hero, game_state: dict):
        """Assign a unique patrol zone to a hero based on their index."""
        if hero.name in self.hero_zones:
            return self.hero_zones[hero.name]
        
        # Get castle position as reference
        castle = game_state.get("castle")
        if castle:
            base_x, base_y = castle.center_x, castle.center_y
        else:
            from config import MAP_WIDTH, MAP_HEIGHT
            base_x = (MAP_WIDTH // 2) * TILE_SIZE
            base_y = (MAP_HEIGHT // 2) * TILE_SIZE
        
        # Assign zones in a circle around the castle
        heroes = [h for h in game_state.get("heroes", []) if h.is_alive]
        try:
            idx = heroes.index(hero)
        except ValueError:
            idx = len(self.hero_zones)
        
        num_heroes = max(len(heroes), 1)
        angle = (2 * math.pi * idx) / num_heroes + random.uniform(-0.2, 0.2)
        radius = TILE_SIZE * random.uniform(6, 10)  # Spread zones further out
        
        zone_x = base_x + math.cos(angle) * radius
        zone_y = base_y + math.sin(angle) * radius
        
        self.hero_zones[hero.name] = (zone_x, zone_y)
        debug_log(f"{hero.name} assigned zone at ({zone_x:.0f}, {zone_y:.0f}), angle={math.degrees(angle):.0f}deg")
        return (zone_x, zone_y)
    
    def update_hero(self, hero, dt: float, game_state: dict):
        """Update AI for a single hero."""
        enemies = game_state.get("enemies", [])
        buildings = game_state.get("buildings", [])
        
        # Handle resting state first (doesn't need LLM)
        if hero.state == HeroState.RESTING:
            self.handle_resting(hero, dt, game_state)
            return

        # Priority: Defend castle if it's under attack (unless already fighting)
        castle = game_state.get("castle")
        if castle and castle.is_damaged and hero.state != HeroState.FIGHTING:
            self.defend_castle(hero, game_state, castle)
            return

        # Priority: Defend home building if it's damaged
        if hero.home_building and hero.home_building.is_damaged and hero.state != HeroState.FIGHTING:
            self.defend_home_building(hero, game_state)
            return

        # Priority: Defend nearby neutral buildings (houses/farms/food stands) if under attack.
        if hero.state != HeroState.FIGHTING:
            if self.defend_neutral_building_if_visible(hero, game_state):
                return

        # Check if hero should go home to rest (priority check)
        # But only if building is not damaged
        if hero.state == HeroState.IDLE and hero.should_go_home_to_rest():
            if hero.can_rest_at_home():
                self.send_home_to_rest(hero, game_state)
                return
        
        # Check if we need an LLM decision
        if self.should_consult_llm(hero, game_state):
            self.request_llm_decision(hero, game_state)
        
        # Handle LLM decision response
        if hero.pending_llm_decision and self.llm_brain:
            decision = self.llm_brain.get_decision(hero.name)
            if decision:
                self.apply_llm_decision(hero, decision, game_state)
                hero.pending_llm_decision = False
        
        # State machine behavior
        if hero.state == HeroState.IDLE:
            self.handle_idle(hero, game_state)
        elif hero.state == HeroState.MOVING:
            self.handle_moving(hero, game_state)
        elif hero.state == HeroState.FIGHTING:
            self.handle_fighting(hero, game_state)
        elif hero.state == HeroState.RETREATING:
            self.handle_retreating(hero, game_state)
        elif hero.state == HeroState.SHOPPING:
            self.handle_shopping(hero, game_state)
    
    def should_consult_llm(self, hero, game_state: dict) -> bool:
        """Determine if we should ask the LLM for a decision."""
        import pygame
        current_time = pygame.time.get_ticks()
        
        # Respect cooldown
        if current_time - hero.last_llm_decision_time < LLM_DECISION_COOLDOWN:
            return False
        
        # Don't stack requests
        if hero.pending_llm_decision:
            return False
        
        # Critical decision points:
        
        # 1. Health is low during combat
        if hero.state == HeroState.FIGHTING and hero.health_percent < HEALTH_THRESHOLD_FOR_DECISION:
            return True
        
        # 2. Has gold and near marketplace
        if hero.gold >= 30:
            for building in game_state.get("buildings", []):
                if building.building_type == "marketplace":
                    dist = hero.distance_to(building.center_x, building.center_y)
                    if dist < TILE_SIZE * 6:
                        return True
        
        return False
    
    def request_llm_decision(self, hero, game_state: dict):
        """Request a decision from the LLM brain."""
        import pygame
        
        if self.llm_brain:
            context = ContextBuilder.build_hero_context(hero, game_state)
            self.llm_brain.request_decision(hero.name, context)
            hero.pending_llm_decision = True
            hero.last_llm_decision_time = pygame.time.get_ticks()
    
    def apply_llm_decision(self, hero, decision: dict, game_state: dict):
        """Apply an LLM decision to the hero."""
        action = decision.get("action", "")
        target = decision.get("target", "")
        
        hero.last_llm_action = decision
        
        if action == "retreat":
            self.start_retreat(hero, game_state)
        elif action == "fight":
            hero.state = HeroState.FIGHTING
        elif action == "buy_item":
            self.go_shopping(hero, target, game_state)
        elif action == "use_potion":
            hero.use_potion()
        elif action == "explore":
            self.explore(hero, game_state)
        elif action == "accept_bounty":
            pass
    
    def handle_idle(self, hero, game_state: dict):
        """Handle idle state - heroes patrol their assigned zone."""
        enemies = game_state.get("enemies", [])
        buildings = game_state.get("buildings", [])
        
        debug_log(f"{hero.name} is IDLE at ({hero.x:.0f}, {hero.y:.0f})", throttle_key=f"{hero.name}_idle")

        # If we were pursuing a bounty but ended up idle, clear it (avoid dangling targets).
        if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "bounty":
            hero.target = None
            hero.target_position = None

        # Majesty-style indirect control: bounties should be a primary lever.
        if self.maybe_take_bounty(hero, game_state):
            return
        
        # Check if hero wants to go shopping (full health, has gold, needs potions)
        if hero.hp >= hero.max_hp:
            marketplace = self.find_marketplace_with_potions(buildings)
            if marketplace and hero.wants_to_shop(marketplace.can_sell_potions()):
                debug_log(f"{hero.name} -> going shopping")
                world = game_state.get("world")
                if world:
                    adj = best_adjacent_tile(world, buildings, marketplace, hero.x, hero.y)
                    if adj:
                        hero.target_position = (adj[0] * TILE_SIZE + TILE_SIZE / 2, adj[1] * TILE_SIZE + TILE_SIZE / 2)
                    else:
                        hero.target_position = (marketplace.center_x, marketplace.center_y)
                else:
                    hero.target_position = (marketplace.center_x, marketplace.center_y)
                hero.state = HeroState.MOVING
                hero.target = {"type": "shopping", "marketplace": marketplace}
                return

        # Get this hero's patrol zone
        zone_x, zone_y = self.assign_patrol_zone(hero, game_state)
        
        debug_log(f"{hero.name} zone=({zone_x:.0f}, {zone_y:.0f}), hero at ({hero.x:.0f}, {hero.y:.0f})", throttle_key=f"{hero.name}_zone")
        
        # Heroes only know about enemies within 5 tiles of themselves (no map-wide awareness)
        awareness_radius = TILE_SIZE * 5  # 160 pixels - hero can only "see" this far
        
        enemies_nearby = []
        for enemy in enemies:
            if not enemy.is_alive:
                continue
            
            dist_to_hero = hero.distance_to(enemy.x, enemy.y)
            
            # Hero can only see enemies within their awareness radius
            if dist_to_hero <= awareness_radius:
                enemies_nearby.append((enemy, dist_to_hero))
        
        # If there are enemies nearby, engage the closest one
        if enemies_nearby:
            enemies_nearby.sort(key=lambda x: x[1])
            target_enemy, target_dist = enemies_nearby[0]
            debug_log(f"{hero.name} -> sees enemy {target_dist:.0f}px away, engaging!")
            hero.target = target_enemy
            hero.set_target_position(target_enemy.x, target_enemy.y)
            hero.state = HeroState.MOVING
            return
        
        debug_log(f"{hero.name} -> no enemies within {awareness_radius}px", throttle_key=f"{hero.name}_no_enemy")
        
        # No enemies in zone - patrol within our zone
        dist_to_zone = hero.distance_to(zone_x, zone_y)
        debug_log(f"{hero.name} dist_to_zone={dist_to_zone:.0f}")
        
        if dist_to_zone > TILE_SIZE * 4:
            # Too far from zone, return to it
            debug_log(f"{hero.name} -> returning to zone")
            hero.target_position = (zone_x, zone_y)
            hero.state = HeroState.MOVING
            hero.target = {"type": "patrol"}
        else:
            # Wander within zone
            if random.random() < 0.02:  # 2% chance per frame
                angle = random.uniform(0, 2 * math.pi)
                wander_dist = TILE_SIZE * random.uniform(1, 3)
                target_x = zone_x + math.cos(angle) * wander_dist
                target_y = zone_y + math.sin(angle) * wander_dist
                debug_log(f"{hero.name} -> wandering to ({target_x:.0f}, {target_y:.0f})")
                hero.target_position = (target_x, target_y)
                hero.state = HeroState.MOVING
                hero.target = {"type": "patrol"}
    
    def find_marketplace_with_potions(self, buildings: list):
        """Find a marketplace that can sell potions."""
        for building in buildings:
            if building.building_type == "marketplace":
                if hasattr(building, 'potions_researched') and building.potions_researched:
                    return building
        return None
    
    def handle_moving(self, hero, game_state: dict):
        """Handle moving state."""
        enemies = game_state.get("enemies", [])
        buildings = game_state.get("buildings", [])

        # Bounty pursuit: claim/abandon logic while walking.
        if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "bounty":
            bounty = self._resolve_bounty_from_target(hero.target, game_state.get("bounties", []))
            if bounty is None:
                # Bounty vanished (claimed/cleaned up)
                hero.target = None
                hero.target_position = None
                hero.state = HeroState.IDLE
                return

            # Abandon invalid or already-claimed bounties
            if getattr(bounty, "claimed", False) or (hasattr(bounty, "is_valid") and not bounty.is_valid(buildings)):
                if hasattr(bounty, "unassign") and getattr(bounty, "assigned_to", None) == hero.name:
                    bounty.unassign()
                hero.target = None
                hero.target_position = None
                hero.state = HeroState.IDLE
                return

            # Timeout to avoid permanent lock
            import pygame
            now_ms = pygame.time.get_ticks()
            started_ms = int(hero.target.get("started_ms", now_ms))
            if now_ms - started_ms > self.bounty_max_pursue_ms:
                if hasattr(bounty, "unassign") and getattr(bounty, "assigned_to", None) == hero.name:
                    bounty.unassign()
                hero.target = None
                hero.target_position = None
                hero.state = HeroState.IDLE
                return

            # Claim if we're close enough (works both in-game and in headless observer)
            goal_x, goal_y = (float(getattr(bounty, "x", hero.x)), float(getattr(bounty, "y", hero.y)))
            if hasattr(bounty, "get_goal_position"):
                goal_x, goal_y = bounty.get_goal_position(buildings)
            if hero.distance_to(goal_x, goal_y) <= float(self.bounty_claim_radius_px):
                if hasattr(bounty, "claim"):
                    bounty.claim(hero)
                hero.target = None
                hero.target_position = None
                hero.state = HeroState.IDLE
                return
        
        # Check if reached destination
        if hero.target_position:
            dist = hero.distance_to(hero.target_position[0], hero.target_position[1])
            if dist < TILE_SIZE // 2:
                # Check if we were going home
                if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "going_home":
                    hero.transfer_taxes_to_home()
                    hero.start_resting()
                    hero.target = None
                    hero.target_position = None
                    return
                
                # Check if we were going shopping
                if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "shopping":
                    marketplace = hero.target.get("marketplace")
                    if marketplace:
                        # Briefly "enter" the building (Majesty-style) for clarity.
                        hero.enter_building_briefly(marketplace, duration_sec=0.5)
                        self.do_shopping(hero, marketplace, game_state)
                    hero.target = None
                    hero.target_position = None
                    hero.state = HeroState.IDLE
                    return
                
                hero.target_position = None
                hero.state = HeroState.IDLE
                return
        
        # Only auto-engage if we're moving toward an enemy target (not patrolling/shopping/etc)
        if hero.target and isinstance(hero.target, dict):
            target_type = hero.target.get("type")
            # Don't interrupt these activities
            if target_type in ["going_home", "shopping", "patrol", "guard_home", "patrol_castle", "defend_castle"]:
                return
        
        # If chasing an enemy, check if we've gone too far from our zone (8 tiles max)
        if hero.target and hasattr(hero.target, 'is_alive'):
            zone_x, zone_y = self.assign_patrol_zone(hero, game_state)
            dist_to_zone = math.sqrt((hero.x - zone_x)**2 + (hero.y - zone_y)**2)
            max_chase_dist = TILE_SIZE * 8
            
            if dist_to_zone > max_chase_dist:
                debug_log(f"{hero.name} -> too far from zone ({dist_to_zone:.0f}px), giving up chase")
                hero.target = None
                hero.target_position = None
                hero.state = HeroState.IDLE
                return
        
        # If we have an enemy target, check if we're in range to fight
        if hero.target and hasattr(hero.target, 'is_alive') and hero.target.is_alive:
            dist = hero.distance_to(hero.target.x, hero.target.y)
            if dist <= hero.attack_range:
                hero.state = HeroState.FIGHTING
                return
    
    def handle_fighting(self, hero, game_state: dict):
        """Handle fighting state."""
        enemies = game_state.get("enemies", [])
        
        # Check if target is still valid
        if hero.target and hasattr(hero.target, 'is_alive'):
            if not hero.target.is_alive:
                hero.target = None
                hero.state = HeroState.IDLE
                return
            
            # Check if target in range
            dist = hero.distance_to(hero.target.x, hero.target.y)
            if dist > hero.attack_range:
                # Move towards target
                hero.target_position = (hero.target.x, hero.target.y)
                hero.state = HeroState.MOVING
        else:
            # Find new target
            hero.state = HeroState.IDLE
    
    def handle_retreating(self, hero, game_state: dict):
        """Handle retreating state - flee to safety."""
        buildings = game_state.get("buildings", [])
        
        nearest_safe = None
        nearest_dist = float('inf')
        
        for building in buildings:
            if building.building_type in ["castle", "marketplace"]:
                dist = hero.distance_to(building.center_x, building.center_y)
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_safe = building
        
        if nearest_safe:
            if nearest_dist < TILE_SIZE * 2:
                hero.state = HeroState.IDLE
                if hero.health_percent < 0.7 and hero.potions > 0:
                    hero.use_potion()
            else:
                hero.target_position = (nearest_safe.center_x, nearest_safe.center_y)
    
    def handle_shopping(self, hero, game_state: dict):
        """Handle shopping state - buy items at marketplace."""
        buildings = game_state.get("buildings", [])
        
        marketplace = None
        for building in buildings:
            if building.building_type == "marketplace":
                dist = hero.distance_to(building.center_x, building.center_y)
                if dist < TILE_SIZE * 2:
                    marketplace = building
                    break
        
        if not marketplace:
            hero.state = HeroState.IDLE
            return
        
        self.do_shopping(hero, marketplace, game_state)
        hero.state = HeroState.IDLE
    
    def do_shopping(self, hero, marketplace, game_state: dict):
        """Actually perform shopping at a marketplace."""
        economy = game_state.get("economy")
        items = marketplace.get_available_items()
        
        # Priority 1: Buy a potion if we have none
        if hero.potions == 0 and hero.gold >= 20:
            for item in items:
                if item["type"] == "potion":
                    if hero.buy_item(item):
                        if economy:
                            economy.hero_purchase(hero.name, item["name"], item["price"])
                        break
        
        # Priority 2: Buy extra potions if rich
        if hero.gold >= 50 and hero.potions < 2:
            for item in items:
                if item["type"] == "potion" and hero.gold >= item["price"]:
                    if hero.buy_item(item):
                        if economy:
                            economy.hero_purchase(hero.name, item["name"], item["price"])
                        break
        
        # Priority 3: Weapon upgrade
        for item in items:
            if item["type"] == "weapon" and hero.gold >= item["price"]:
                current_attack = hero.weapon.get("attack", 0) if hero.weapon else 0
                if item["attack"] > current_attack:
                    if hero.buy_item(item):
                        if economy:
                            economy.hero_purchase(hero.name, item["name"], item["price"])
                        break
        
        # Priority 4: Armor upgrade
        for item in items:
            if item["type"] == "armor" and hero.gold >= item["price"]:
                current_defense = hero.armor.get("defense", 0) if hero.armor else 0
                if item["defense"] > current_defense:
                    if hero.buy_item(item):
                        if economy:
                            economy.hero_purchase(hero.name, item["name"], item["price"])
                        break
    
    def start_retreat(self, hero, game_state: dict):
        """Start retreating to safety."""
        hero.state = HeroState.RETREATING
        buildings = game_state.get("buildings", [])
        
        for building in buildings:
            if building.building_type in ["castle", "marketplace"]:
                hero.target_position = (building.center_x, building.center_y)
                break
    
    def go_shopping(self, hero, item_name: str, game_state: dict):
        """Send hero to marketplace to buy an item."""
        buildings = game_state.get("buildings", [])
        world = game_state.get("world")
        
        for building in buildings:
            if building.building_type == "marketplace":
                if world:
                    adj = best_adjacent_tile(world, buildings, building, hero.x, hero.y)
                    if adj:
                        hero.target_position = (adj[0] * TILE_SIZE + TILE_SIZE / 2, adj[1] * TILE_SIZE + TILE_SIZE / 2)
                    else:
                        hero.target_position = (building.center_x, building.center_y)
                else:
                    hero.target_position = (building.center_x, building.center_y)
                hero.state = HeroState.MOVING
                hero.target = {"type": "shopping", "item": item_name}
                break
    
    def explore(self, hero, game_state: dict):
        """Send hero to explore within their zone."""
        zone_x, zone_y = self.assign_patrol_zone(hero, game_state)
        angle = random.uniform(0, 2 * math.pi)
        wander_dist = TILE_SIZE * random.uniform(2, 5)
        target_x = zone_x + math.cos(angle) * wander_dist
        target_y = zone_y + math.sin(angle) * wander_dist
        hero.set_target_position(target_x, target_y)

    # -----------------------
    # Bounty pursuit behavior
    # -----------------------

    def _resolve_bounty_from_target(self, target_dict: dict, bounties: list):
        """Find the bounty referenced by hero.target dict."""
        bid = target_dict.get("bounty_id")
        if bid is None:
            # Fallback: stored direct reference (best-effort)
            ref = target_dict.get("bounty_ref")
            if ref in bounties:
                return ref
            return None
        for b in bounties:
            if getattr(b, "bounty_id", None) == bid:
                return b
        return None

    def maybe_take_bounty(self, hero, game_state: dict) -> bool:
        """Pick and start pursuing a bounty if it makes sense. Returns True if a bounty was started."""
        bounties = game_state.get("bounties", [])
        if not bounties:
            return False

        # Avoid changing targets too often
        import pygame
        now_ms = pygame.time.get_ticks()
        last_pick = int(getattr(hero, "_last_bounty_pick_ms", 0))
        if now_ms - last_pick < self.bounty_pick_cooldown_ms:
            return False

        # Don't pursue bounties when hurt; survival + resting logic already handles healing.
        if hero.health_percent < 0.65:
            return False

        buildings = game_state.get("buildings", [])
        enemies = game_state.get("enemies", [])

        best = None
        best_score = -1e9
        for b in bounties:
            # Only consider bounties that are available (avoid dogpiling).
            if hasattr(b, "is_available_for") and not b.is_available_for(hero.name, now_ms, self.bounty_assign_ttl_ms):
                continue
            if hasattr(b, "is_valid") and not b.is_valid(buildings):
                continue

            score = self.score_bounty(hero, b, buildings, enemies)
            if score > best_score:
                best_score = score
                best = b

        # Require some minimum attractiveness so heroes don't constantly wander to tiny bounties
        if best is None or best_score < 0.5:
            hero._last_bounty_pick_ms = now_ms
            return False

        self.start_bounty_pursuit(hero, best, game_state)
        hero._last_bounty_pick_ms = now_ms
        return True

    def score_bounty(self, hero, bounty, buildings: list, enemies: list) -> float:
        """Heuristic bounty scoring: reward vs distance vs risk, with class biases + noise."""
        try:
            goal_x, goal_y = bounty.get_goal_position(buildings) if hasattr(bounty, "get_goal_position") else (bounty.x, bounty.y)
            dist_tiles = max(0.1, float(hero.distance_to(goal_x, goal_y)) / float(TILE_SIZE))
        except Exception:
            dist_tiles = 10.0

        reward = float(getattr(bounty, "reward", 0))
        risk = float(bounty.estimate_risk(enemies)) if hasattr(bounty, "estimate_risk") else 0.0

        # Class bias tuning (prototype)
        cls = getattr(hero, "hero_class", "warrior")
        reward_w = 1.0
        dist_w = 1.0
        risk_w = 1.0
        type_bonus = 0.0

        if cls == "rogue":
            reward_w = 1.45
            dist_w = 0.85
            risk_w = 1.05
        elif cls == "wizard":
            reward_w = 1.15
            dist_w = 1.05
            risk_w = 1.15
        elif cls == "ranger":
            reward_w = 1.05
            dist_w = 0.95
            risk_w = 1.0
        else:  # warrior and others
            reward_w = 1.0
            dist_w = 1.0
            risk_w = 1.0

        btype = getattr(bounty, "bounty_type", "explore")
        if cls == "rogue" and btype == "explore":
            type_bonus += 1.0
        if cls == "wizard" and btype == "defend_building":
            type_bonus += 0.4

        # Reward grows sublinearly; distance is a smooth penalty; risk subtracts.
        base = (reward_w * math.sqrt(max(0.0, reward)) + type_bonus) / (1.0 + dist_w * (dist_tiles ** 1.1))
        base -= risk_w * 0.35 * risk

        # Add a small per-hero randomness to reduce synchronized picks.
        base += random.uniform(-0.15, 0.15)
        return base

    def start_bounty_pursuit(self, hero, bounty, game_state: dict):
        """Set hero to pursue the bounty."""
        buildings = game_state.get("buildings", [])
        world = game_state.get("world")

        # Assign the bounty so others generally avoid it for a short while.
        if hasattr(bounty, "assign"):
            bounty.assign(hero.name)

        goal_x, goal_y = (float(getattr(bounty, "x", hero.x)), float(getattr(bounty, "y", hero.y)))
        if hasattr(bounty, "get_goal_position"):
            goal_x, goal_y = bounty.get_goal_position(buildings)

        # If the bounty targets a building, go to an adjacent tile so heroes don't try to stand inside it.
        target_building = None
        if getattr(bounty, "bounty_type", "") in ("attack_lair", "defend_building"):
            target_building = getattr(bounty, "target", None)

        if world and target_building is not None:
            adj = best_adjacent_tile(world, buildings, target_building, hero.x, hero.y)
            if adj:
                goal_x = adj[0] * TILE_SIZE + TILE_SIZE / 2
                goal_y = adj[1] * TILE_SIZE + TILE_SIZE / 2

        hero.target_position = (goal_x, goal_y)
        import pygame
        hero.target = {
            "type": "bounty",
            "bounty_id": getattr(bounty, "bounty_id", None),
            "bounty_type": getattr(bounty, "bounty_type", "explore"),
            # Keep a direct reference as fallback for headless tests
            "bounty_ref": bounty,
            "started_ms": pygame.time.get_ticks(),
        }
        hero.state = HeroState.MOVING
    
    def send_home_to_rest(self, hero, game_state: dict):
        """Send hero home to rest and heal."""
        if hero.home_building:
            buildings = game_state.get("buildings", [])
            world = game_state.get("world")
            if world:
                adj = best_adjacent_tile(world, buildings, hero.home_building, hero.x, hero.y)
                if adj:
                    hero.target_position = (adj[0] * TILE_SIZE + TILE_SIZE / 2, adj[1] * TILE_SIZE + TILE_SIZE / 2)
                else:
                    hero.target_position = (hero.home_building.center_x, hero.home_building.center_y)
            else:
                hero.target_position = (hero.home_building.center_x, hero.home_building.center_y)
            hero.state = HeroState.MOVING
            hero.target = {"type": "going_home"}
    
    def handle_resting(self, hero, dt: float, game_state: dict):
        """Handle hero resting at home."""
        if hero.home_building and hero.home_building.is_damaged:
            hero.pop_out_of_building()
            return
        
        if hero.home_building:
            dist = hero.distance_to(hero.home_building.center_x, hero.home_building.center_y)
            if dist > TILE_SIZE * 2:
                hero.finish_resting()
                return
        
        still_resting = hero.update_resting(dt)
        
        if not still_resting:
            hero.state = HeroState.IDLE
    
    def defend_home_building(self, hero, game_state: dict):
        """Hero defends their damaged home building."""
        enemies = game_state.get("enemies", [])
        
        if not hero.home_building:
            return
        
        building = hero.home_building
        
        nearest_enemy = None
        nearest_dist = float('inf')
        
        for enemy in enemies:
            if enemy.is_alive:
                dist_to_building = enemy.distance_to(building.center_x, building.center_y)
                if dist_to_building < TILE_SIZE * 5:
                    dist_to_hero = hero.distance_to(enemy.x, enemy.y)
                    if dist_to_hero < nearest_dist:
                        nearest_dist = dist_to_hero
                        nearest_enemy = enemy
        
        if nearest_enemy:
            if nearest_dist <= hero.attack_range:
                hero.target = nearest_enemy
                hero.state = HeroState.FIGHTING
            else:
                hero.target = nearest_enemy
                hero.set_target_position(nearest_enemy.x, nearest_enemy.y)
        else:
            dist_to_home = hero.distance_to(building.center_x, building.center_y)
            if dist_to_home > TILE_SIZE * 2:
                hero.set_target_position(building.center_x + TILE_SIZE, building.center_y)
            else:
                hero.state = HeroState.IDLE

    def defend_neutral_building_if_visible(self, hero, game_state: dict) -> bool:
        """
        If a neutral building is under attack within the hero's "visible" radius,
        the hero may choose to defend it depending on class.
        """
        buildings = game_state.get("buildings", [])
        enemies = game_state.get("enemies", [])

        # Don't interrupt explicit activities like shopping/going_home.
        if hero.target and isinstance(hero.target, dict):
            if hero.target.get("type") in ["going_home", "shopping"]:
                return False

        visibility_radius = TILE_SIZE * 6
        # Class-based willingness to respond
        cls = getattr(hero, "hero_class", "warrior")
        willingness = {
            "warrior": 1.0,
            "ranger": 0.85,
            "wizard": 0.75,
            "rogue": 0.55,
        }.get(cls, 0.8)

        # Find closest attacked neutral building within visibility.
        candidate = None
        candidate_dist = float("inf")
        for b in buildings:
            if not getattr(b, "is_neutral", False):
                continue
            if getattr(b, "hp", 0) <= 0:
                continue
            if not getattr(b, "is_under_attack", False):
                continue
            dist = hero.distance_to(b.center_x, b.center_y)
            if dist <= visibility_radius and dist < candidate_dist:
                candidate = b
                candidate_dist = dist

        if not candidate:
            return False

        # Stochastic willingness (keeps behavior varied and class-flavored).
        if random.random() > float(willingness):
            return False

        # Find nearest enemy near that building.
        target_enemy = None
        target_dist = float("inf")
        for e in enemies:
            if not getattr(e, "is_alive", False):
                continue
            d = e.distance_to(candidate.center_x, candidate.center_y)
            if d < TILE_SIZE * 6 and d < target_dist:
                target_enemy = e
                target_dist = d

        if target_enemy:
            dist_to_hero = hero.distance_to(target_enemy.x, target_enemy.y)
            if dist_to_hero <= hero.attack_range:
                hero.target = target_enemy
                hero.state = HeroState.FIGHTING
                return True
            hero.target = target_enemy
            hero.set_target_position(target_enemy.x, target_enemy.y)
            hero.state = HeroState.MOVING
            return True

        # If we can't find an enemy, move to the building to "investigate/defend".
        hero.target = {"type": "defend_neutral", "building": candidate}
        hero.set_target_position(candidate.center_x + TILE_SIZE, candidate.center_y)
        hero.state = HeroState.MOVING
        return True

    def defend_castle(self, hero, game_state: dict, castle):
        """Send hero to defend the castle when it's damaged."""
        enemies = game_state.get("enemies", [])

        target_enemy = None
        target_dist = float("inf")
        for enemy in enemies:
            if enemy.is_alive:
                dist_to_castle = enemy.distance_to(castle.center_x, castle.center_y)
                if dist_to_castle < target_dist:
                    target_dist = dist_to_castle
                    target_enemy = enemy

        if target_enemy:
            dist_to_hero = hero.distance_to(target_enemy.x, target_enemy.y)
            if dist_to_hero <= hero.attack_range:
                hero.target = target_enemy
                hero.state = HeroState.FIGHTING
                return
            hero.target = target_enemy
            hero.set_target_position(target_enemy.x, target_enemy.y)
            hero.state = HeroState.MOVING
            return

        dist_to_castle = hero.distance_to(castle.center_x, castle.center_y)
        if dist_to_castle > TILE_SIZE * 3:
            hero.target = {"type": "defend_castle"}
            hero.set_target_position(castle.center_x + TILE_SIZE, castle.center_y)
            hero.state = HeroState.MOVING
        else:
            hero.state = HeroState.IDLE
