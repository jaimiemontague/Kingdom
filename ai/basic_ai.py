"""
Basic AI state machine for hero movement and combat.
Handles routine behavior, defers important decisions to LLM.
"""
import math
import random
from game.entities.hero import HeroState
from game.systems.pathfinding import find_path, grid_to_world_path
from game.world import Visibility
from config import (
    TILE_SIZE, HEALTH_THRESHOLD_FOR_DECISION, LLM_DECISION_COOLDOWN,
    RANGER_EXPLORE_BLACK_FOG_BIAS, RANGER_FRONTIER_SCAN_RADIUS_TILES, RANGER_FRONTIER_COMMIT_MS,
    BOUNTY_BLACK_FOG_DISTANCE_PENALTY
)
from ai.context_builder import ContextBuilder
from ai.prompt_templates import get_fallback_decision
from game.systems.navigation import best_adjacent_tile
from game.sim.determinism import get_rng
from game.sim.timebase import now_ms as sim_now_ms
from game.sim.hero_guardrails_tunables import (
    STUCK_DISPLACEMENT_TILES_THRESHOLD,
    STUCK_TIME_S,
    UNSTUCK_MAX_ATTEMPTS_PER_TARGET,
    UNSTUCK_BACKOFF_S,
    TARGET_COMMIT_WINDOW_S,
    BOUNTY_COMMIT_WINDOW_S,
)

# Deterministic AI RNG stream (isolated from gameplay RNG).
_AI_RNG = get_rng("ai_basic")

# Debug logging (set to True to see AI decision logs)
DEBUG_AI = False

_last_log = {}
def debug_log(msg, throttle_key=None):
    if not DEBUG_AI:
        return
    # Throttle repeated messages
    if throttle_key:
        # Use sim time to avoid nondeterministic wall-clock dependencies in sim logic.
        now_ms = sim_now_ms()
        last_ms = int(_last_log.get(throttle_key, 0) or 0)
        if now_ms - last_ms < 1000:
            return
        _last_log[throttle_key] = now_ms
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
        # Journey tuning (post-shopping exploration/assault)
        self.journey_trigger_window_ms = 10000
        self.journey_cooldown_ms = 45000

    # -----------------------
    # Intent + decision helpers
    # -----------------------

    def refresh_intent(self, hero, game_state: dict | None = None) -> None:
        """
        Keep hero.intent non-empty and update hero.last_decision on meaningful changes.

        Prefer the hero's own intent-derivation contract if available; fall back to a
        lightweight label derived from state/target.
        """
        try:
            if hasattr(hero, "_update_intent_and_decision"):
                hero._update_intent_and_decision(game_state)
                return
        except Exception:
            # Best-effort only; never crash the sim due to intent plumbing.
            pass

        # Fallback (older hero versions)
        intent = "idle"
        t = getattr(hero, "target", None)
        if isinstance(t, dict):
            ttype = t.get("type")
            if ttype == "bounty":
                intent = "pursuing_bounty"
            elif ttype == "shopping":
                intent = "shopping"
            elif ttype == "going_home":
                intent = "returning_to_safety"
        st = getattr(getattr(hero, "state", None), "name", "")
        if st == "FIGHTING":
            intent = "engaging_enemy"
        elif st == "RETREATING":
            intent = "returning_to_safety"
        setattr(hero, "intent", str(intent) or "idle")

    def set_intent(self, hero, intent: str) -> None:
        """Set hero intent label (taxonomy)."""
        setattr(hero, "intent", str(intent or "idle"))

    def record_decision(
        self,
        hero,
        *,
        action: str,
        reason: str,
        intent: str | None = None,
        inputs_summary: dict | None = None,
        source: str | None = None,
        now_ms: int | None = None,
    ) -> None:
        """
        Store a lightweight last-decision snapshot on the hero.

        We keep compatibility with the thin `HeroDecisionRecord` contract by packing
        extra metadata into the `context` dict.
        """
        ctx: dict = {}
        if intent is not None:
            ctx["intent"] = str(intent)
        if source is not None:
            ctx["source"] = str(source)
        if inputs_summary is not None:
            if isinstance(inputs_summary, dict):
                ctx["inputs_summary"] = dict(inputs_summary)
            else:
                ctx["inputs_summary"] = str(inputs_summary)

        if hasattr(hero, "record_decision"):
            try:
                hero.record_decision(action=str(action), reason=str(reason), now_ms=now_ms, context=ctx)
            except TypeError:
                # Older signature (without named args)
                hero.record_decision(str(action), str(reason))
        
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
        angle = (2 * math.pi * idx) / num_heroes + _AI_RNG.uniform(-0.2, 0.2)
        radius = TILE_SIZE * _AI_RNG.uniform(6, 10)  # Spread zones further out
        
        zone_x = base_x + math.cos(angle) * radius
        zone_y = base_y + math.sin(angle) * radius
        
        self.hero_zones[hero.name] = (zone_x, zone_y)
        debug_log(f"{hero.name} assigned zone at ({zone_x:.0f}, {zone_y:.0f}), angle={math.degrees(angle):.0f}deg")
        return (zone_x, zone_y)
    
    def update_hero(self, hero, dt: float, game_state: dict):
        """Update AI for a single hero."""
        enemies = game_state.get("enemies", [])
        buildings = game_state.get("buildings", [])

        # Keep intent non-empty even if we make no decision this tick.
        self.refresh_intent(hero, game_state)

        # WK2 Build A: stuck detection + deterministic recovery.
        self._update_stuck_and_recover(hero, game_state)
        
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
            # If no LLM brain is wired, still choose via deterministic fallback so
            # the no-LLM path produces stable intent/decision logging.
            if self.llm_brain:
                self.request_llm_decision(hero, game_state)
            else:
                context = ContextBuilder.build_hero_context(hero, game_state)
                decision = get_fallback_decision(context)
                self.apply_llm_decision(hero, decision, game_state, source="fallback", context=context)
        
        # Handle LLM decision response
        if hero.pending_llm_decision and self.llm_brain:
            decision = self.llm_brain.get_decision(hero.name)
            if decision:
                context = ContextBuilder.build_hero_context(hero, game_state)
                src = "mock" if getattr(self.llm_brain, "provider_name", None) == "mock" else "llm"
                self.apply_llm_decision(hero, decision, game_state, source=src, context=context)
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
        current_time = sim_now_ms()
        
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
        if self.llm_brain:
            context = ContextBuilder.build_hero_context(hero, game_state)
            self.llm_brain.request_decision(hero.name, context)
            hero.pending_llm_decision = True
            hero.last_llm_decision_time = sim_now_ms()
            self.record_decision(
                hero,
                action="request_llm",
                reason="Consulting LLM for decision",
                intent=getattr(hero, "intent", "idle") or "idle",
                inputs_summary=ContextBuilder.build_inputs_summary(context),
                source="system",
            )
    
    def apply_llm_decision(self, hero, decision: dict, game_state: dict, *, source: str = "llm", context: dict | None = None):
        """Apply an LLM decision to the hero."""
        action = decision.get("action", "")
        target = decision.get("target", "")
        
        hero.last_llm_action = decision

        if context is None:
            context = ContextBuilder.build_hero_context(hero, game_state)
        inputs_summary = ContextBuilder.build_inputs_summary(context)
        reason = decision.get("reasoning", "")
        if not isinstance(reason, str):
            reason = ""
        
        if action == "retreat":
            self.set_intent(hero, "returning_to_safety")
            self.record_decision(hero, action="retreat", reason=reason or "Retreating", intent="returning_to_safety", inputs_summary=inputs_summary, source=source)
            self.start_retreat(hero, game_state)
        elif action == "fight":
            self.set_intent(hero, "engaging_enemy")
            self.record_decision(hero, action="fight", reason=reason or "Fighting", intent="engaging_enemy", inputs_summary=inputs_summary, source=source)
            hero.state = HeroState.FIGHTING
        elif action == "buy_item":
            self.set_intent(hero, "shopping")
            self.record_decision(hero, action="buy_item", reason=reason or f"Buying {target}", intent="shopping", inputs_summary=inputs_summary, source=source)
            self.go_shopping(hero, target, game_state)
        elif action == "use_potion":
            self.record_decision(hero, action="use_potion", reason=reason or "Using potion", intent=getattr(hero, "intent", "idle") or "idle", inputs_summary=inputs_summary, source=source)
            hero.use_potion()
        elif action == "explore":
            self.set_intent(hero, "idle")
            self.record_decision(hero, action="explore", reason=reason or "Exploring", intent="idle", inputs_summary=inputs_summary, source=source)
            self.explore(hero, game_state)
        elif action == "accept_bounty":
            pass
        else:
            debug_log(f"{hero.name} received unknown LLM action={action!r}; ignoring", throttle_key=f"{hero.name}_unknown_llm_action")
            self.record_decision(hero, action=str(action or "unknown"), reason="Unknown LLM action; ignored", intent=getattr(hero, "intent", "idle") or "idle", inputs_summary=inputs_summary, source=source)
    
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
            # WK2 anti-oscillation: respect commitment window unless current target is invalid.
            now_ms = int(sim_now_ms())
            if now_ms < int(getattr(hero, "_target_commit_until_ms", 0) or 0):
                cur = getattr(hero, "target", None)
                if cur is not None and hasattr(cur, "is_alive") and getattr(cur, "is_alive", False):
                    return
            enemies_nearby.sort(key=lambda x: x[1])
            target_enemy, target_dist = enemies_nearby[0]
            debug_log(f"{hero.name} -> sees enemy {target_dist:.0f}px away, engaging!")
            hero.target = target_enemy
            hero._target_commit_until_ms = int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))
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
            # WK6: Rangers use explore() which has black fog frontier bias; others use random wander
            if getattr(hero, "hero_class", None) == "ranger":
                # Check commitment window (prevent rapid re-targeting)
                now_ms = sim_now_ms()
                frontier_commit_until = int(getattr(hero, "_frontier_commit_until_ms", 0) or 0)
                if now_ms >= frontier_commit_until or not hero.target_position:
                    # Not committed or no current target, call explore() which handles frontier logic
                    self.explore(hero, game_state)
            else:
                # Non-Rangers: random wander (original behavior)
                if _AI_RNG.random() < 0.02:  # 2% chance per frame
                    angle = _AI_RNG.uniform(0, 2 * math.pi)
                    wander_dist = TILE_SIZE * _AI_RNG.uniform(1, 3)
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
            now_ms = sim_now_ms()
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
                btype = str(getattr(bounty, "bounty_type", "explore") or "explore")

                # Typed bounties are not proximity-claimed.
                # For attack_lair: reaching the bounty transitions the hero to actually attack the lair.
                if btype == "attack_lair":
                    lair = getattr(bounty, "target", None)
                    if getattr(lair, "is_lair", False) and getattr(lair, "hp", 0) > 0:
                        hero.target = lair
                        # Approach an adjacent tile so we don't path into the lair footprint.
                        world = game_state.get("world")
                        if world:
                            adj = best_adjacent_tile(world, buildings, lair, hero.x, hero.y)
                            if adj:
                                hero.target_position = (adj[0] * TILE_SIZE + TILE_SIZE / 2, adj[1] * TILE_SIZE + TILE_SIZE / 2)
                            else:
                                hero.target_position = (float(getattr(lair, "center_x", goal_x)), float(getattr(lair, "center_y", goal_y)))
                        else:
                            hero.target_position = (float(getattr(lair, "center_x", goal_x)), float(getattr(lair, "center_y", goal_y)))
                        hero.state = HeroState.MOVING
                        # Best-effort breadcrumb for debugging/UX (no hard dependency).
                        setattr(hero, "_active_attack_lair_bounty_id", getattr(bounty, "bounty_id", None))
                        return

                if btype == "explore":
                    if hasattr(bounty, "claim"):
                        bounty.claim(hero)
                    hero.target = None
                    hero.target_position = None
                    hero.state = HeroState.IDLE
                    return
                # Other typed bounties: don't auto-claim here; let their systems resolve completion.
        
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
                        started_journey = self.do_shopping(hero, marketplace, game_state)
                        if started_journey:
                            return
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
                # Move towards target (for lairs/buildings, approach adjacent tile to avoid unreachable goals).
                if getattr(hero.target, "is_lair", False):
                    buildings = game_state.get("buildings", [])
                    world = game_state.get("world")
                    if world:
                        adj = best_adjacent_tile(world, buildings, hero.target, hero.x, hero.y)
                        if adj:
                            hero.target_position = (adj[0] * TILE_SIZE + TILE_SIZE / 2, adj[1] * TILE_SIZE + TILE_SIZE / 2)
                        else:
                            hero.target_position = (hero.target.x, hero.target.y)
                    else:
                        hero.target_position = (hero.target.x, hero.target.y)
                else:
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

        started_journey = self.do_shopping(hero, marketplace, game_state)
        if started_journey:
            return
        hero.state = HeroState.IDLE
    
    def do_shopping(self, hero, marketplace, game_state: dict) -> bool:
        """Actually perform shopping at a marketplace."""
        economy = game_state.get("economy")
        items = marketplace.get_available_items()
        purchased_types: set[str] = set()
        
        # Priority 1: Buy a potion if we have none
        if hero.potions == 0 and hero.gold >= 20:
            for item in items:
                if item["type"] == "potion":
                    if hero.buy_item(item):
                        purchased_types.add("potion")
                        if economy:
                            economy.hero_purchase(hero.name, item["name"], item["price"])
                        break
        
        # Priority 2: Buy extra potions if rich
        if hero.gold >= 50 and hero.potions < 2:
            for item in items:
                if item["type"] == "potion" and hero.gold >= item["price"]:
                    if hero.buy_item(item):
                        purchased_types.add("potion")
                        if economy:
                            economy.hero_purchase(hero.name, item["name"], item["price"])
                        break
        
        # Priority 3: Weapon upgrade
        for item in items:
            if item["type"] == "weapon" and hero.gold >= item["price"]:
                current_attack = hero.weapon.get("attack", 0) if hero.weapon else 0
                if item["attack"] > current_attack:
                    if hero.buy_item(item):
                        purchased_types.add("weapon")
                        if economy:
                            economy.hero_purchase(hero.name, item["name"], item["price"])
                        break
        
        # Priority 4: Armor upgrade
        for item in items:
            if item["type"] == "armor" and hero.gold >= item["price"]:
                current_defense = hero.armor.get("defense", 0) if hero.armor else 0
                if item["defense"] > current_defense:
                    if hero.buy_item(item):
                        purchased_types.add("armor")
                        if economy:
                            economy.hero_purchase(hero.name, item["name"], item["price"])
                        break

        # Post-shopping journey trigger (full health + recent purchase)
        return self._maybe_start_journey(hero, game_state, purchased_types)
    
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

    # -----------------------
    # Journey behavior (v1.3)
    # -----------------------

    def _maybe_start_journey(self, hero, game_state: dict, purchased_types: set[str] | None) -> bool:
        """Start a post-shopping journey if conditions are met."""
        if not purchased_types:
            return False
        if hero.hp < hero.max_hp:
            return False
        last_purchase_ms = getattr(hero, "last_purchase_ms", None)
        if last_purchase_ms is None:
            return False
        now_ms = int(sim_now_ms())
        if (now_ms - int(last_purchase_ms)) > int(self.journey_trigger_window_ms):
            return False
        cooldown_until = int(getattr(hero, "_journey_cooldown_until_ms", 0) or 0)
        if now_ms < cooldown_until:
            return False

        hero_class = str(getattr(hero, "hero_class", "warrior") or "warrior")
        chance = 0.75
        if hero_class == "rogue":
            chance = 0.7
        elif hero_class == "warrior":
            chance = 0.8
        elif hero_class == "ranger":
            chance = 0.85
        if _AI_RNG.random() > float(chance):
            return False

        started = False
        if hero_class == "warrior":
            # Prefer fighting: attack lair more often, else explore deeper fog.
            if _AI_RNG.random() < 0.65:
                started = self._start_journey_attack_lair(hero, game_state)
            if not started:
                started = self._start_journey_explore(hero, game_state, min_tiles=10, max_tiles=30, prefer_far=True, scan_radius=30)
        elif hero_class == "ranger":
            # Prefer exploration: farther fog target, fallback to lair if none found.
            started = self._start_journey_explore(hero, game_state, min_tiles=6, max_tiles=None, prefer_far=True, scan_radius=40)
            if not started and _AI_RNG.random() < 0.25:
                started = self._start_journey_attack_lair(hero, game_state)
        else:
            # Rogue: short, cautious fog step.
            started = self._start_journey_explore(hero, game_state, min_tiles=2, max_tiles=6, prefer_far=False, scan_radius=6)

        if started:
            hero._journey_cooldown_until_ms = int(now_ms + int(self.journey_cooldown_ms))
        return started

    def _start_journey_explore(
        self,
        hero,
        game_state: dict,
        *,
        min_tiles: float | None,
        max_tiles: float | None,
        prefer_far: bool,
        scan_radius: int,
    ) -> bool:
        world = game_state.get("world")
        if not world:
            return False
        candidates = self._find_black_fog_frontier_tiles(
            world,
            hero,
            max_candidates=8,
            scan_radius=int(scan_radius),
            min_dist_tiles=min_tiles,
            max_dist_tiles=max_tiles,
        )
        if not candidates:
            return False

        # Weighted pick: farther for warriors/rangers, closer for rogues.
        weights = []
        for _, _, dist in candidates:
            if prefer_far:
                weights.append(max(0.1, float(dist)))
            else:
                weights.append(1.0 / (float(dist) + 0.1))
        total_weight = float(sum(weights))
        if total_weight <= 0:
            return False
        r = _AI_RNG.uniform(0, total_weight)
        cumsum = 0.0
        selected = None
        for i, w in enumerate(weights):
            cumsum += w
            if r <= cumsum:
                selected = candidates[i]
                break
        if not selected:
            selected = candidates[0]
        gx, gy, _ = selected
        target_x = gx * TILE_SIZE + TILE_SIZE / 2
        target_y = gy * TILE_SIZE + TILE_SIZE / 2
        hero.set_target_position(target_x, target_y)
        hero.target = {"type": "journey_explore", "goal": "black_fog", "grid": (gx, gy)}
        self.set_intent(hero, "idle")
        self.record_decision(
            hero,
            action="journey_explore",
            reason="Post-shopping journey: explore fog",
            intent=getattr(hero, "intent", "idle") or "idle",
            inputs_summary={"trigger": "post_shopping", "goal": "black_fog"},
            source="system",
        )
        return True

    def _start_journey_attack_lair(self, hero, game_state: dict) -> bool:
        buildings = game_state.get("buildings", [])
        world = game_state.get("world")
        if not buildings:
            return False
        best = None
        best_d2 = None
        for b in buildings:
            if not getattr(b, "is_lair", False):
                continue
            if getattr(b, "hp", 0) <= 0:
                continue
            dx = float(getattr(b, "center_x", getattr(b, "x", 0.0))) - float(hero.x)
            dy = float(getattr(b, "center_y", getattr(b, "y", 0.0))) - float(hero.y)
            d2 = dx * dx + dy * dy
            if best is None or (best_d2 is not None and d2 < best_d2):
                best = b
                best_d2 = d2
        if best is None:
            return False

        goal_x = float(getattr(best, "center_x", getattr(best, "x", hero.x)))
        goal_y = float(getattr(best, "center_y", getattr(best, "y", hero.y)))
        if world:
            adj = best_adjacent_tile(world, buildings, best, hero.x, hero.y)
            if adj:
                goal_x = adj[0] * TILE_SIZE + TILE_SIZE / 2
                goal_y = adj[1] * TILE_SIZE + TILE_SIZE / 2
        hero.set_target_position(goal_x, goal_y)
        hero.target = best
        self.set_intent(hero, "attacking_lair")
        self.record_decision(
            hero,
            action="journey_attack_lair",
            reason="Post-shopping journey: attack lair",
            intent=getattr(hero, "intent", "idle") or "idle",
            inputs_summary={"trigger": "post_shopping", "goal": "attack_lair"},
            source="system",
        )
        return True
    
    def _find_black_fog_frontier_tiles(
        self,
        world,
        hero,
        max_candidates: int = 5,
        scan_radius: int | None = None,
        min_dist_tiles: float | None = None,
        max_dist_tiles: float | None = None,
    ):
        """
        Find UNSEEN tiles that are adjacent to SEEN or VISIBLE tiles (black fog frontier).
        Returns list of (grid_x, grid_y, distance_tiles) tuples, sorted by distance (closest first).
        Uses deterministic ordering (stable sort by distance, then by grid coords).
        """
        if not world or not hasattr(world, "visibility"):
            return []
        
        hero_gx = int(hero.x // TILE_SIZE)
        hero_gy = int(hero.y // TILE_SIZE)
        if scan_radius is None:
            scan_radius = RANGER_FRONTIER_SCAN_RADIUS_TILES
        
        candidates = []
        # Scan a square region around hero (bounded for perf)
        for dy in range(-scan_radius, scan_radius + 1):
            for dx in range(-scan_radius, scan_radius + 1):
                gx = hero_gx + dx
                gy = hero_gy + dy
                
                # Bounds check
                if gx < 0 or gx >= world.width or gy < 0 or gy >= world.height:
                    continue
                
                # Check if this tile is UNSEEN (black fog)
                if world.visibility[gy][gx] != Visibility.UNSEEN:
                    continue
                
                # Check if it's adjacent to SEEN or VISIBLE (frontier)
                is_frontier = False
                for adj_dy in [-1, 0, 1]:
                    for adj_dx in [-1, 0, 1]:
                        if adj_dx == 0 and adj_dy == 0:
                            continue
                        adj_gx = gx + adj_dx
                        adj_gy = gy + adj_dy
                        if 0 <= adj_gx < world.width and 0 <= adj_gy < world.height:
                            adj_vis = world.visibility[adj_gy][adj_gx]
                            if adj_vis == Visibility.SEEN or adj_vis == Visibility.VISIBLE:
                                is_frontier = True
                                break
                    if is_frontier:
                        break
                
                if is_frontier:
                    # Calculate distance (squared for comparison, avoid sqrt until needed)
                    dist_sq = dx * dx + dy * dy
                    dist_tiles = math.sqrt(dist_sq)
                    if min_dist_tiles is not None and dist_tiles < float(min_dist_tiles):
                        continue
                    if max_dist_tiles is not None and dist_tiles > float(max_dist_tiles):
                        continue
                    candidates.append((gx, gy, dist_tiles))
        
        # Stable sort: by distance (closest first), then by grid coords (deterministic tie-break)
        candidates.sort(key=lambda c: (c[2], c[1], c[0]))
        
        # Return top N candidates
        return candidates[:max_candidates]
    
    def explore(self, hero, game_state: dict):
        """Send hero to explore within their zone. Rangers prefer black fog frontiers."""
        zone_x, zone_y = self.assign_patrol_zone(hero, game_state)
        
        # WK6: Rangers have exploration bias toward black fog frontiers
        if getattr(hero, "hero_class", None) == "ranger":
            world = game_state.get("world")
            if world:
                # Check commitment window (prevent rapid re-targeting)
                now_ms = sim_now_ms()
                frontier_commit_until = int(getattr(hero, "_frontier_commit_until_ms", 0) or 0)
                if now_ms < frontier_commit_until:
                    # Still committed to current exploration target, continue
                    if hero.target_position:
                        return
                
                # Try to find frontier tiles
                frontier_candidates = self._find_black_fog_frontier_tiles(world, hero, max_candidates=5)
                
                if frontier_candidates and _AI_RNG.random() < RANGER_EXPLORE_BLACK_FOG_BIAS:
                    # Pick a frontier tile (weighted by distance: closer = higher weight)
                    # Use inverse distance as weight (closer = higher weight)
                    weights = [1.0 / (c[2] + 0.1) for c in frontier_candidates]
                    total_weight = sum(weights)
                    if total_weight > 0:
                        r = _AI_RNG.uniform(0, total_weight)
                        cumsum = 0
                        selected = None
                        for i, w in enumerate(weights):
                            cumsum += w
                            if r <= cumsum:
                                selected = frontier_candidates[i]
                                break
                        
                        if selected:
                            gx, gy, _ = selected
                            # Convert grid coords to world coords (center of tile)
                            target_x = gx * TILE_SIZE + TILE_SIZE / 2
                            target_y = gy * TILE_SIZE + TILE_SIZE / 2
                            hero.set_target_position(target_x, target_y)
                            hero.target = {"type": "explore_frontier"}
                            # Set commitment window
                            hero._frontier_commit_until_ms = int(now_ms + RANGER_FRONTIER_COMMIT_MS)
                            debug_log(f"{hero.name} -> exploring black fog frontier at ({gx}, {gy})")
                            return
        
        # Fallback: random wander (original behavior, or if no frontier found)
        angle = _AI_RNG.uniform(0, 2 * math.pi)
        wander_dist = TILE_SIZE * _AI_RNG.uniform(2, 5)
        target_x = zone_x + math.cos(angle) * wander_dist
        target_y = zone_y + math.sin(angle) * wander_dist
        hero.set_target_position(target_x, target_y)
        hero.target = {"type": "patrol"}

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
        now_ms = sim_now_ms()

        # WK2 anti-oscillation: don't rapidly switch bounty objectives.
        if int(now_ms) < int(getattr(hero, "_bounty_commit_until_ms", 0) or 0):
            return False
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

            world = game_state.get("world")
            score = self.score_bounty(hero, b, buildings, enemies, world=world)
            if score > best_score:
                best_score = score
                best = b

        # Require some minimum attractiveness so heroes don't constantly wander to tiny bounties
        if best is None or best_score < 0.15:
            hero._last_bounty_pick_ms = now_ms
            return False

        self.start_bounty_pursuit(hero, best, game_state)
        hero._last_bounty_pick_ms = now_ms
        return True

    def score_bounty(self, hero, bounty, buildings: list, enemies: list, world=None) -> float:
        """Heuristic bounty scoring: reward vs distance vs risk, with class biases + noise."""
        try:
            goal_x, goal_y = bounty.get_goal_position(buildings) if hasattr(bounty, "get_goal_position") else (bounty.x, bounty.y)
            dist_tiles = max(0.1, float(hero.distance_to(goal_x, goal_y)) / float(TILE_SIZE))
        except Exception:
            dist_tiles = 10.0

        # WK6: Check if bounty is in black fog and apply distance penalty (uncertainty), but never exclude
        is_black_fog = False
        if world and hasattr(world, "visibility"):
            try:
                # Get bounty grid coordinates
                bounty_gx = int(goal_x // TILE_SIZE)
                bounty_gy = int(goal_y // TILE_SIZE)
                if 0 <= bounty_gx < world.width and 0 <= bounty_gy < world.height:
                    bounty_vis = world.visibility[bounty_gy][bounty_gx]
                    is_black_fog = (bounty_vis == Visibility.UNSEEN)
            except Exception:
                # If we can't determine, assume not black fog (no penalty)
                pass

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

        # WK6: Apply black fog distance penalty (uncertainty multiplier)
        effective_dist_tiles = dist_tiles * (BOUNTY_BLACK_FOG_DISTANCE_PENALTY if is_black_fog else 1.0)
        
        # Reward grows sublinearly; distance is a smooth penalty; risk subtracts.
        base = (reward_w * math.sqrt(max(0.0, reward)) + type_bonus) / (1.0 + dist_w * (effective_dist_tiles ** 1.1))
        base -= risk_w * 0.35 * risk

        # Add a small per-hero randomness to reduce synchronized picks.
        base += _AI_RNG.uniform(-0.15, 0.15)
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
        hero.target = {
            "type": "bounty",
            "bounty_id": getattr(bounty, "bounty_id", None),
            "bounty_type": getattr(bounty, "bounty_type", "explore"),
            # Keep a direct reference as fallback for headless tests
            "bounty_ref": bounty,
            "started_ms": sim_now_ms(),
        }
        hero._bounty_commit_until_ms = int(sim_now_ms() + int(float(BOUNTY_COMMIT_WINDOW_S) * 1000.0))
        hero.state = HeroState.MOVING

    # -----------------------
    # WK2: Stuck detection + deterministic recovery
    # -----------------------

    def _stuck_target_key(self, hero) -> tuple:
        t = getattr(hero, "target", None)
        if isinstance(t, dict) and t.get("type") == "bounty":
            return ("bounty", t.get("bounty_id"), t.get("bounty_type"))
        if isinstance(t, dict):
            return ("dict", t.get("type"))
        if t is None:
            return ("none",)
        return ("obj", t.__class__.__name__)

    def _update_stuck_and_recover(self, hero, game_state: dict):
        """
        Detect 'intends to move but no progress' using sim-time and apply deterministic recovery steps.

        Locked thresholds (from PM hub wk2_r1):
        - displacement < STUCK_DISPLACEMENT_TILES_THRESHOLD tiles
        - time >= STUCK_TIME_S
        - max attempts per target = UNSTUCK_MAX_ATTEMPTS_PER_TARGET
        - backoff = UNSTUCK_BACKOFF_S
        """
        # Ignore while inside buildings; movement is intentionally paused.
        # Clear stuck state so we don't report "stuck" while a hero is intentionally hidden/paused.
        if bool(getattr(hero, "is_inside_building", False)):
            if bool(getattr(hero, "stuck_active", False)):
                hero.stuck_active = False
                hero.stuck_since_ms = None
                hero.stuck_reason = ""
            return

        state = getattr(hero, "state", None)
        if state not in (HeroState.MOVING, HeroState.RETREATING):
            # Not intending to move => not stuck.
            if bool(getattr(hero, "stuck_active", False)):
                hero.stuck_active = False
                hero.stuck_since_ms = None
                hero.stuck_reason = ""
            return
        if not getattr(hero, "target_position", None):
            return

        now_ms = int(sim_now_ms())

        # Initialize progress fields if missing.
        if not hasattr(hero, "last_progress_ms"):
            hero.last_progress_ms = now_ms
        if not hasattr(hero, "last_progress_pos"):
            hero.last_progress_pos = (float(getattr(hero, "x", 0.0)), float(getattr(hero, "y", 0.0)))

        last_px, last_py = getattr(hero, "last_progress_pos", (float(hero.x), float(hero.y)))
        dx = float(hero.x) - float(last_px)
        dy = float(hero.y) - float(last_py)
        dist_px = (dx * dx + dy * dy) ** 0.5

        displacement_thresh_px = float(TILE_SIZE) * float(STUCK_DISPLACEMENT_TILES_THRESHOLD)
        if dist_px >= displacement_thresh_px:
            hero.last_progress_ms = now_ms
            hero.last_progress_pos = (float(hero.x), float(hero.y))
            hero.stuck_active = False
            hero.stuck_since_ms = None
            hero.stuck_reason = ""
            hero._unstuck_attempts_for_target = 0
            hero._unstuck_target_key = None
            return

        if now_ms - int(getattr(hero, "last_progress_ms", now_ms)) < int(float(STUCK_TIME_S) * 1000.0):
            return

        # Mark stuck (contract fields)
        if not bool(getattr(hero, "stuck_active", False)):
            hero.stuck_active = True
            hero.stuck_since_ms = int(getattr(hero, "last_progress_ms", now_ms))
            hero.stuck_reason = "no_progress"

        # Backoff between attempts
        last_attempt_ms = int(getattr(hero, "_last_unstuck_attempt_ms", 0) or 0)
        if now_ms - last_attempt_ms < int(float(UNSTUCK_BACKOFF_S) * 1000.0):
            return

        key = self._stuck_target_key(hero)
        if getattr(hero, "_unstuck_target_key", None) != key:
            hero._unstuck_target_key = key
            hero._unstuck_attempts_for_target = 0

        attempt_idx = int(getattr(hero, "_unstuck_attempts_for_target", 0) or 0)
        if attempt_idx >= int(UNSTUCK_MAX_ATTEMPTS_PER_TARGET):
            # Fallback: drop target and return to idle patrol.
            hero.stuck_reason = "fallback_idle"
            hero.target = None
            hero.target_position = None
            hero.path = []
            hero._path_goal = None
            hero.state = HeroState.IDLE
            hero.stuck_active = False
            hero.stuck_since_ms = None
            return

        world = game_state.get("world")
        buildings = game_state.get("buildings", [])

        if attempt_idx == 0:
            # Step 1: force replanning.
            hero.stuck_reason = "repath"
            hero.path = []
            hero._path_goal = None
        elif attempt_idx == 1:
            # Step 2: nudge to an adjacent walkable tile (deterministic order).
            hero.stuck_reason = "nudge_adjacent"
            if world:
                gx, gy = world.world_to_grid(hero.x, hero.y)
                candidates = [(gx + 1, gy), (gx - 1, gy), (gx, gy + 1), (gx, gy - 1)]

                blocked = set()
                for b in buildings or []:
                    if getattr(b, "hp", 1) <= 0:
                        continue
                    if getattr(b, "building_type", "") != "castle" and getattr(b, "is_constructed", True) is False:
                        continue
                    bgx = getattr(b, "grid_x", None)
                    bgy = getattr(b, "grid_y", None)
                    size = getattr(b, "size", None)
                    if bgx is None or bgy is None or not size:
                        continue
                    for dx0 in range(size[0]):
                        for dy0 in range(size[1]):
                            blocked.add((bgx + dx0, bgy + dy0))

                for cx, cy in candidates:
                    if (cx, cy) in blocked:
                        continue
                    if not world.is_walkable(cx, cy):
                        continue
                    hero.target_position = (cx * TILE_SIZE + TILE_SIZE / 2, cy * TILE_SIZE + TILE_SIZE / 2)
                    hero.state = HeroState.MOVING
                    break
        else:
            # Step 3: reset goal to an easy patrol objective.
            hero.stuck_reason = "reset_goal"
            hero.target = {"type": "patrol"}
            zone_x, zone_y = self.assign_patrol_zone(hero, game_state)
            hero.target_position = (zone_x, zone_y)
            hero.state = HeroState.MOVING

        hero._unstuck_attempts_for_target = attempt_idx + 1
        hero._last_unstuck_attempt_ms = now_ms
        hero.unstuck_attempts = int(getattr(hero, "unstuck_attempts", 0) or 0) + 1
    
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

        # WK2 anti-oscillation: if currently committed to a valid combat target, don't thrash.
        now_ms = int(sim_now_ms())
        if now_ms < int(getattr(hero, "_target_commit_until_ms", 0) or 0):
            cur = getattr(hero, "target", None)
            if cur is not None and hasattr(cur, "is_alive") and getattr(cur, "is_alive", False):
                return
        
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
                hero._target_commit_until_ms = int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))
                hero.state = HeroState.FIGHTING
            else:
                hero.target = nearest_enemy
                hero._target_commit_until_ms = int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))
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

        # WK2 anti-oscillation: if currently committed to a valid combat target, don't thrash.
        now_ms = int(sim_now_ms())
        if now_ms < int(getattr(hero, "_target_commit_until_ms", 0) or 0):
            cur = getattr(hero, "target", None)
            if cur is not None and hasattr(cur, "is_alive") and getattr(cur, "is_alive", False):
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
        if _AI_RNG.random() > float(willingness):
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
                hero._target_commit_until_ms = int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))
                hero.state = HeroState.FIGHTING
                return True
            hero.target = target_enemy
            hero._target_commit_until_ms = int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))
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

        # WK2 anti-oscillation: if currently committed to a valid combat target, don't thrash.
        now_ms = int(sim_now_ms())
        if now_ms < int(getattr(hero, "_target_commit_until_ms", 0) or 0):
            cur = getattr(hero, "target", None)
            if cur is not None and hasattr(cur, "is_alive") and getattr(cur, "is_alive", False):
                return

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
                hero._target_commit_until_ms = int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))
                hero.state = HeroState.FIGHTING
                return
            hero.target = target_enemy
            hero._target_commit_until_ms = int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))
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
