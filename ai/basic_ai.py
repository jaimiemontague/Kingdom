"""
Basic AI state machine for hero movement and combat.
Handles routine behavior, defers important decisions to LLM.
"""
import math
import random
from game.entities.hero import HeroState
from game.systems.pathfinding import find_path, grid_to_world_path
from config import TILE_SIZE, HEALTH_THRESHOLD_FOR_DECISION, LLM_DECISION_COOLDOWN


class BasicAI:
    """
    Handles basic hero AI behavior.
    Movement, pathfinding, and combat targeting are handled here.
    Strategic decisions are deferred to the LLM brain.
    """
    
    def __init__(self, llm_brain=None):
        self.llm_brain = llm_brain
        
    def update(self, dt: float, heroes: list, game_state: dict):
        """Update AI for all heroes."""
        for hero in heroes:
            if not hero.is_alive:
                continue
            self.update_hero(hero, dt, game_state)
    
    def update_hero(self, hero, dt: float, game_state: dict):
        """Update AI for a single hero."""
        enemies = game_state.get("enemies", [])
        buildings = game_state.get("buildings", [])
        
        # Handle resting state first (doesn't need LLM)
        if hero.state == HeroState.RESTING:
            self.handle_resting(hero, dt, game_state)
            return
        
        # Priority: Defend home building if it's damaged
        if hero.home_building and hero.home_building.is_damaged:
            self.defend_home_building(hero, game_state)
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
        
        # 3. Idle with no goal
        if hero.state == HeroState.IDLE and not hero.target_position:
            return True
        
        return False
    
    def request_llm_decision(self, hero, game_state: dict):
        """Request a decision from the LLM brain."""
        import pygame
        
        if self.llm_brain:
            context = hero.get_context_for_llm(game_state)
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
            # Find and pursue bounty target
            pass
    
    def handle_idle(self, hero, game_state: dict):
        """Handle idle state - find something to do."""
        enemies = game_state.get("enemies", [])
        buildings = game_state.get("buildings", [])
        
        # Check if hero wants to go shopping (full health, has gold, needs potions)
        if hero.hp >= hero.max_hp:
            marketplace = self.find_marketplace_with_potions(buildings)
            if marketplace and hero.wants_to_shop(marketplace.can_sell_potions()):
                # Go shopping
                hero.target_position = (marketplace.center_x, marketplace.center_y)
                hero.state = HeroState.MOVING
                hero.target = {"type": "shopping", "marketplace": marketplace}
                return
        
        # Look for nearby enemies to fight
        nearest_enemy = None
        nearest_dist = float('inf')
        
        for enemy in enemies:
            if enemy.is_alive:
                dist = hero.distance_to(enemy.x, enemy.y)
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_enemy = enemy
        
        if nearest_enemy and nearest_dist < TILE_SIZE * 8:
            # Move towards enemy
            hero.target = nearest_enemy
            hero.set_target_position(nearest_enemy.x, nearest_enemy.y)
            return
        
        # If no enemies, explore randomly
        if random.random() < 0.01:  # 1% chance per frame to start exploring
            self.explore(hero, game_state)
    
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
        
        # Check if reached destination
        if hero.target_position:
            dist = hero.distance_to(hero.target_position[0], hero.target_position[1])
            if dist < TILE_SIZE // 2:
                # Check if we were going home
                if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "going_home":
                    # Arrived home - transfer taxes and start resting
                    hero.transfer_taxes_to_home()
                    hero.start_resting()
                    hero.target = None
                    hero.target_position = None
                    return
                
                # Check if we were going shopping
                if hero.target and isinstance(hero.target, dict) and hero.target.get("type") == "shopping":
                    # Arrived at marketplace - start shopping
                    marketplace = hero.target.get("marketplace")
                    if marketplace:
                        self.do_shopping(hero, marketplace, game_state)
                    hero.target = None
                    hero.target_position = None
                    hero.state = HeroState.IDLE
                    return
                
                hero.target_position = None
                hero.state = HeroState.IDLE
                return
        
        # Check for enemies in attack range while moving (but not if going home or shopping)
        if hero.target and isinstance(hero.target, dict):
            target_type = hero.target.get("type")
            if target_type in ["going_home", "shopping"]:
                # Don't fight when trying to get home to rest or go shopping
                return
        
        for enemy in enemies:
            if enemy.is_alive:
                dist = hero.distance_to(enemy.x, enemy.y)
                if dist <= hero.attack_range:
                    hero.target = enemy
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
        
        # Find nearest safe building (castle or marketplace)
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
                # Reached safety
                hero.state = HeroState.IDLE
                # Use potion if available and hurt
                if hero.health_percent < 0.7 and hero.potions > 0:
                    hero.use_potion()
            else:
                hero.target_position = (nearest_safe.center_x, nearest_safe.center_y)
    
    def handle_shopping(self, hero, game_state: dict):
        """Handle shopping state - buy items at marketplace."""
        buildings = game_state.get("buildings", [])
        
        # Find marketplace
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
        
        # Get available items
        items = marketplace.get_available_items()
        
        # Priority 1: Buy a potion if we have none and can afford it
        if hero.potions == 0 and hero.gold >= 20:
            for item in items:
                if item["type"] == "potion":
                    if hero.buy_item(item):
                        if economy:
                            economy.hero_purchase(hero.name, item["name"], item["price"])
                        break
        
        # Priority 2: If gold >= 50 and potions < max, maybe buy more potions
        # For now, warriors are practical - buy up to 2 potions total if they can afford it
        if hero.gold >= 50 and hero.potions < 2:
            for item in items:
                if item["type"] == "potion" and hero.gold >= item["price"]:
                    if hero.buy_item(item):
                        if economy:
                            economy.hero_purchase(hero.name, item["name"], item["price"])
                        # Only buy one extra per shopping trip
                        break
        
        # Priority 3: Weapon upgrade if can afford
        for item in items:
            if item["type"] == "weapon" and hero.gold >= item["price"]:
                current_attack = hero.weapon.get("attack", 0) if hero.weapon else 0
                if item["attack"] > current_attack:
                    if hero.buy_item(item):
                        if economy:
                            economy.hero_purchase(hero.name, item["name"], item["price"])
                        break
        
        # Priority 4: Armor upgrade if can afford
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
        
        # Find nearest safe building
        for building in buildings:
            if building.building_type in ["castle", "marketplace"]:
                hero.target_position = (building.center_x, building.center_y)
                break
    
    def go_shopping(self, hero, item_name: str, game_state: dict):
        """Send hero to marketplace to buy an item."""
        buildings = game_state.get("buildings", [])
        
        for building in buildings:
            if building.building_type == "marketplace":
                hero.target_position = (building.center_x, building.center_y)
                hero.state = HeroState.MOVING
                # Store desired item for when we arrive
                hero.target = {"type": "shopping", "item": item_name}
                break
    
    def explore(self, hero, game_state: dict):
        """Send hero to explore a random location."""
        from config import MAP_WIDTH, MAP_HEIGHT
        
        # Pick a random walkable location
        target_x = random.randint(2, MAP_WIDTH - 3) * TILE_SIZE + TILE_SIZE // 2
        target_y = random.randint(2, MAP_HEIGHT - 3) * TILE_SIZE + TILE_SIZE // 2
        
        hero.set_target_position(target_x, target_y)
    
    def send_home_to_rest(self, hero, game_state: dict):
        """Send hero home to rest and heal."""
        if hero.home_building:
            hero.target_position = (hero.home_building.center_x, hero.home_building.center_y)
            hero.state = HeroState.MOVING
            hero.target = {"type": "going_home"}
    
    def handle_resting(self, hero, dt: float, game_state: dict):
        """Handle hero resting at home."""
        # Check if building is damaged - hero will pop out automatically in update_resting
        if hero.home_building and hero.home_building.is_damaged:
            hero.pop_out_of_building()
            return
        
        # Check if still at home
        if hero.home_building:
            dist = hero.distance_to(hero.home_building.center_x, hero.home_building.center_y)
            if dist > TILE_SIZE * 2:
                # Left home somehow, stop resting
                hero.finish_resting()
                return
        
        # Update resting (heals 1 HP every 2 seconds)
        still_resting = hero.update_resting(dt)
        
        if not still_resting:
            # Done resting, become idle
            hero.state = HeroState.IDLE
    
    def defend_home_building(self, hero, game_state: dict):
        """Hero defends their damaged home building."""
        enemies = game_state.get("enemies", [])
        
        if not hero.home_building:
            return
        
        building = hero.home_building
        
        # Find enemies near the building
        nearest_enemy = None
        nearest_dist = float('inf')
        
        for enemy in enemies:
            if enemy.is_alive:
                # Check if enemy is near the building or targeting it
                dist_to_building = enemy.distance_to(building.center_x, building.center_y)
                if dist_to_building < TILE_SIZE * 5:  # Within 5 tiles of building
                    dist_to_hero = hero.distance_to(enemy.x, enemy.y)
                    if dist_to_hero < nearest_dist:
                        nearest_dist = dist_to_hero
                        nearest_enemy = enemy
        
        if nearest_enemy:
            # Attack the enemy threatening our home
            if nearest_dist <= hero.attack_range:
                hero.target = nearest_enemy
                hero.state = HeroState.FIGHTING
            else:
                # Move towards the enemy
                hero.target = nearest_enemy
                hero.set_target_position(nearest_enemy.x, nearest_enemy.y)
        else:
            # No enemies nearby, stay near building
            dist_to_home = hero.distance_to(building.center_x, building.center_y)
            if dist_to_home > TILE_SIZE * 2:
                hero.set_target_position(building.center_x + TILE_SIZE, building.center_y)
            else:
                hero.state = HeroState.IDLE

