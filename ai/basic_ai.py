"""
Basic AI state machine for hero movement and combat.
Handles routine behavior, defers important decisions to LLM.
"""

from __future__ import annotations

from ai.behaviors import (
    bounty_pursuit,
    defense,
    exploration,
    journey,
    llm_bridge,
    shopping,
    stuck_recovery,
)
from ai.context_builder import ContextBuilder
from ai.prompt_templates import get_fallback_decision
from config import TILE_SIZE
from game.entities.buildings.types import BuildingType
from game.entities.hero import HeroState
from game.sim.determinism import get_rng
from game.sim.timebase import now_ms as sim_now_ms
from game.systems.navigation import best_adjacent_tile

# Deterministic AI RNG stream (isolated from gameplay RNG).
_AI_RNG = get_rng("ai_basic")

# WK17: Target types that lock in intent — hero does not reconsider until destination reached or attacked.
_COMMITTED_DESTINATION_TYPES = frozenset({
    "going_home",
    "shopping",
    "rest_inn",
    "get_drink",
    "bounty",
    "patrol",
    "explore_frontier",
    "guard_home",
    "patrol_castle",
    "defend_castle",
})

# Debug logging (set to True to see AI decision logs).
DEBUG_AI = False

_last_log = {}


def debug_log(msg, throttle_key=None):
    if not DEBUG_AI:
        return
    # Throttle repeated messages.
    if throttle_key:
        # Use sim time to avoid nondeterministic wall-clock dependencies in sim logic.
        now_ms = sim_now_ms()
        last_ms = int(_last_log.get(throttle_key, 0) or 0)
        if now_ms - last_ms < 1000:
            return
        _last_log[throttle_key] = now_ms
    print(f"[AI] {msg}")


class BasicAI:
    """Coordinator for hero AI state updates and behavior modules."""

    def __init__(self, llm_brain=None):
        self.llm_brain = llm_brain
        # Track each hero's personal patrol zone (assigned on first idle).
        self.hero_zones = {}  # hero.name -> (center_x, center_y)

        # Bounty pursuit tuning (prototype-friendly constants).
        self.bounty_assign_ttl_ms = 15000
        self.bounty_pick_cooldown_ms = 2500
        self.bounty_max_pursue_ms = 35000
        self.bounty_claim_radius_px = TILE_SIZE * 2
        # Journey tuning (post-shopping exploration/assault).
        self.journey_trigger_window_ms = 10000
        self.journey_cooldown_ms = 45000

        # Shared deterministic RNG + debug logger passed through coordinator.
        self._ai_rng = _AI_RNG
        self._debug_log = debug_log

        # Behavior modules (no module-to-module imports; coordination stays here).
        self.bounty_behavior = bounty_pursuit
        self.defense_behavior = defense
        self.journey_behavior = journey
        self.stuck_recovery_behavior = stuck_recovery
        self.exploration_behavior = exploration
        self.shopping_behavior = shopping
        self.llm_bridge_behavior = llm_bridge

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

        # Fallback (older hero versions).
        intent = "idle"
        target = getattr(hero, "target", None)
        if isinstance(target, dict):
            target_type = target.get("type")
            if target_type == "bounty":
                intent = "pursuing_bounty"
            elif target_type == "shopping":
                intent = "shopping"
            elif target_type == "going_home":
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

    def _is_committed_destination(self, hero) -> bool:
        """True when hero is MOVING toward a destination we should not reconsider (WK17 intent conviction)."""
        if hero.state != HeroState.MOVING:
            return False
        target = getattr(hero, "target", None)
        if not isinstance(target, dict):
            return False
        return target.get("type") in _COMMITTED_DESTINATION_TYPES

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

        We keep compatibility with the thin ``HeroDecisionRecord`` contract by packing
        extra metadata into the ``context`` dict.
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
                # Older signature (without named args).
                hero.record_decision(str(action), str(reason))

    def update(self, dt: float, heroes: list, game_state: dict):
        """Update AI for all heroes."""
        for hero in heroes:
            if not hero.is_alive:
                continue
            self.update_hero(hero, dt, game_state)

    def update_hero(self, hero, dt: float, game_state: dict):
        """Update AI for a single hero."""
        # Keep intent non-empty even if we make no decision this tick.
        self.refresh_intent(hero, game_state)

        # WK2 Build A: stuck detection + deterministic recovery.
        self.stuck_recovery_behavior._update_stuck_and_recover(self, hero, game_state)

        # WK15: Castle under attack — urgent priority: drop everything (including popping out) and defend.
        castle = game_state.get("castle")
        if castle and getattr(castle, "is_under_attack", False):
            if getattr(hero, "is_inside_building", False):
                hero.pop_out_of_building()
                setattr(hero, "pending_task", None)
                setattr(hero, "pending_task_building", None)
            self.defense_behavior.defend_castle(self, hero, game_state, castle)
            return

        # WK11: Finalize deferred task when hero just left a building (pending_task set, not inside).
        if not hero.is_inside_building:
            pending = getattr(hero, "pending_task", None)
            pending_building = getattr(hero, "pending_task_building", None)
            if pending and pending_building:
                self._finalize_deferred_task(hero, game_state)
                return

        # Handle resting state first (doesn't need LLM).
        if hero.state == HeroState.RESTING:
            self.handle_resting(hero, dt, game_state)
            return

        # Priority: defend castle if damaged or under attack (unless already fighting).
        castle = game_state.get("castle")
        if castle and (castle.is_damaged or getattr(castle, "is_under_attack", False)) and hero.state != HeroState.FIGHTING:
            self.defense_behavior.defend_castle(self, hero, game_state, castle)
            return

        # WK15: Warriors prioritize defending economic buildings (farm, food_stand) under attack.
        if hero.state != HeroState.FIGHTING and getattr(hero, "hero_class", "") == "warrior":
            if self.defense_behavior.defend_economic_building_warrior(self, hero, game_state):
                return

        # Priority: defend home building if it's damaged.
        if hero.home_building and hero.home_building.is_damaged and hero.state != HeroState.FIGHTING:
            self.defense_behavior.defend_home_building(self, hero, game_state)
            return

        # Priority: defend nearby neutral buildings if under attack.
        if hero.state != HeroState.FIGHTING:
            if self.defense_behavior.defend_neutral_building_if_visible(self, hero, game_state):
                return

        # Check if hero should go home to rest (priority check, only if home is safe).
        if hero.state == HeroState.IDLE and hero.should_go_home_to_rest():
            if hero.can_rest_at_home():
                # Bugfix v1.3.4: don't route to Inn/home to rest if enemies are nearby
                # and the hero isn't critically low HP. Let the state machine engage instead.
                enemies = game_state.get("enemies", [])
                combat_guard_radius = TILE_SIZE * 5  # ~5 tiles / 160px
                enemies_nearby = any(
                    getattr(e, "is_alive", False) and hero.distance_to(e.x, e.y) <= combat_guard_radius
                    for e in enemies
                )
                if enemies_nearby and hero.health_percent > 0.25:
                    self._debug_log(
                        f"{hero.name} -> skipping rest (enemies nearby, hp={hero.health_percent:.0%})",
                        throttle_key=f"{hero.name}_skip_rest_enemy",
                    )
                else:
                    self.send_home_to_rest(hero, game_state)
                    return

        # WK17: Intent conviction — do not consult or apply LLM when hero is committed to a destination.
        if not self._is_committed_destination(hero):
            # Check if we need an LLM decision.
            if self.llm_bridge_behavior.should_consult_llm(self, hero, game_state):
                # If no LLM brain is wired, still choose via deterministic fallback so
                # the no-LLM path produces stable intent/decision logging.
                if self.llm_brain:
                    self.llm_bridge_behavior.request_llm_decision(self, hero, game_state)
                else:
                    context = ContextBuilder.build_hero_context(hero, game_state)
                    decision = get_fallback_decision(context)
                    self.llm_bridge_behavior.apply_llm_decision(
                        self,
                        hero,
                        decision,
                        game_state,
                        source="fallback",
                        context=context,
                    )

            # Handle LLM decision response.
            if hero.pending_llm_decision and self.llm_brain:
                decision = self.llm_brain.get_decision(hero.name)
                if decision:
                    context = ContextBuilder.build_hero_context(hero, game_state)
                    src = "mock" if getattr(self.llm_brain, "provider_name", None) == "mock" else "llm"
                    self.llm_bridge_behavior.apply_llm_decision(
                        self, hero, decision, game_state, source=src, context=context
                    )
                    hero.pending_llm_decision = False
        else:
            # Committed to destination: do not apply a stale pending decision when we later become IDLE.
            if hero.pending_llm_decision:
                hero.pending_llm_decision = False

        # State machine behavior.
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

    def handle_idle(self, hero, game_state: dict):
        self.exploration_behavior.handle_idle(self, hero, game_state)

    def handle_moving(self, hero, game_state: dict):
        self.bounty_behavior.handle_moving(self, hero, game_state)

    def handle_fighting(self, hero, game_state: dict):
        """Handle fighting state."""
        # V1.3 extension: prefer using potions before health gets too low.
        if hero.health_percent < 0.6 and hero.potions > 0:
            hero.use_potion()
            self._debug_log(f"{hero.name} -> using potion in combat (health={hero.health_percent:.1%})")

        # Check if target is still valid.
        if hero.target and hasattr(hero.target, "is_alive"):
            if not hero.target.is_alive:
                hero.target = None
                hero.state = HeroState.IDLE
                return

            # Check if target in range.
            dist = hero.distance_to(hero.target.x, hero.target.y)
            if dist > hero.attack_range:
                # Move towards target (for lairs/buildings, approach adjacent tile to avoid unreachable goals).
                buildings = game_state.get("buildings", [])
                world = game_state.get("world")

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

    def handle_retreating(self, hero, game_state: dict):
        """Handle retreating state - flee to safety."""
        buildings = game_state.get("buildings", [])

        # V1.3 extension: use potion during retreat if available and health is low.
        if hero.health_percent < 0.7 and hero.potions > 0:
            hero.use_potion()
            self._debug_log(f"{hero.name} -> using potion while retreating (health={hero.health_percent:.1%})")

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

    def _finalize_deferred_task(self, hero, game_state: dict) -> None:
        """Run deferred task on pop-out (WK11): shopping purchase, get_drink payment, or clear rest_inn."""
        pending = getattr(hero, "pending_task", None)
        pending_building = getattr(hero, "pending_task_building", None)
        if not pending or not pending_building:
            return
        if pending == "shopping":
            self.shopping_behavior.do_shopping(self, hero, pending_building, game_state)
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

    def handle_shopping(self, hero, game_state: dict):
        """Handle shopping state - wait inside or buy at marketplace/blacksmith (WK11: deferred purchase on exit)."""
        if hero.is_inside_building:
            return  # Wait for inside_timer to expire; finalize_deferred_task runs on pop-out
        buildings = game_state.get("buildings", [])

        shop = None
        for building in buildings:
            if building.building_type in ["marketplace", "blacksmith"]:
                dist = hero.distance_to(building.center_x, building.center_y)
                if dist < TILE_SIZE * 2:
                    shop = building
                    break

        if not shop:
            hero.state = HeroState.IDLE
            return

        started_journey = self.shopping_behavior.do_shopping(self, hero, shop, game_state)
        if started_journey:
            return
        hero.state = HeroState.IDLE

    def send_home_to_rest(self, hero, game_state: dict):
        """Send hero home to rest and heal; prefer Inn if closer (WK11)."""
        buildings = game_state.get("buildings", [])
        world = game_state.get("world")

        # WK11: Prefer Inn when closer than home guild.
        inns = [b for b in buildings if getattr(b, "building_type", None) == BuildingType.INN and getattr(b, "is_constructed", True)]
        if inns and hero.home_building:
            hero_dist_home = hero.distance_to(hero.home_building.center_x, hero.home_building.center_y)
            closest_inn = min(inns, key=lambda b: hero.distance_to(b.center_x, b.center_y))
            if hero.distance_to(closest_inn.center_x, closest_inn.center_y) < hero_dist_home:
                adj = best_adjacent_tile(world, buildings, closest_inn, hero.x, hero.y) if world else None
                if adj:
                    hero.target_position = (
                        adj[0] * TILE_SIZE + TILE_SIZE / 2,
                        adj[1] * TILE_SIZE + TILE_SIZE / 2,
                    )
                else:
                    hero.target_position = (closest_inn.center_x, closest_inn.center_y)
                hero.state = HeroState.MOVING
                hero.target = {"type": "rest_inn", "inn": closest_inn}
                return

        if hero.home_building:
            if world:
                adj = best_adjacent_tile(world, buildings, hero.home_building, hero.x, hero.y)
                if adj:
                    hero.target_position = (
                        adj[0] * TILE_SIZE + TILE_SIZE / 2,
                        adj[1] * TILE_SIZE + TILE_SIZE / 2,
                    )
                else:
                    hero.target_position = (hero.home_building.center_x, hero.home_building.center_y)
            else:
                hero.target_position = (hero.home_building.center_x, hero.home_building.center_y)
            hero.state = HeroState.MOVING
            hero.target = {"type": "going_home"}

    def handle_resting(self, hero, dt: float, game_state: dict):
        """Handle hero resting at home or inn."""
        rest_building = hero.inside_building or hero.home_building
        if rest_building and getattr(rest_building, "is_damaged", False):
            hero.pop_out_of_building()
            return

        if rest_building:
            dist = hero.distance_to(rest_building.center_x, rest_building.center_y)
            if dist > TILE_SIZE * 2:
                hero.finish_resting()
                return

        still_resting = hero.update_resting(dt)

        if not still_resting:
            hero.state = HeroState.IDLE
