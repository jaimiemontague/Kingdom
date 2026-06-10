"""
Basic AI state machine for hero movement and combat.
Handles routine behavior, defers important decisions to LLM.
"""

from __future__ import annotations

from ai.behaviors import (
    bounty_pursuit,
    defense,
    exploration,
    hunger,
    journey,
    llm_bridge,
    shopping,
    stuck_recovery,
    support,
)
from ai.behaviors.movement import route_to_building
from config import TILE_SIZE
from game.entities.buildings.types import BuildingType
from game.entities.hero import HeroState
from game.sim.determinism import get_rng
from game.sim.timebase import now_ms as sim_now_ms


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
    "direct_prompt",
    "visit_poi",  # WK55: personality-driven POI visit
    "buy_meal",  # WK61-R10: hunger meal at food stand
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
        self.hunger_behavior = hunger
        self.llm_bridge_behavior = llm_bridge
        self.support_behavior = support
        self._hunger_no_stand_logged_heroes: set[str] = set()

    # -----------------------
    # Intent + decision helpers
    # -----------------------

    def refresh_intent(self, hero, view=None) -> None:
        """
        Keep hero.intent non-empty and update hero.last_decision on meaningful changes.

        Prefer the hero's own intent-derivation contract if available; fall back to a
        lightweight label derived from state/target.
        """
        try:
            if hasattr(hero, "_update_intent_and_decision"):
                # hero._update_intent_and_decision ignores its argument (it reads
                # only hero attributes), so threading the typed view is harmless.
                hero._update_intent_and_decision(view)
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

    def update(self, dt: float, heroes: list, view):
        """Update AI for all heroes.

        WK67 Move 5 (L3): ``view`` is a read-only :class:`AiGameView` built by
        ``SimEngine.build_ai_view`` — NOT the live UI ``game_state`` dict. The AI
        no longer holds ``world``/``economy``/``sim``/``engine``; it reads the
        typed view (``view.world`` is a read-only ``WorldView``).
        """
        for hero in heroes:
            if not hero.is_alive:
                continue
            self.update_hero(hero, dt, view)

    def update_hero(self, hero, dt: float, view):
        """Update AI for a single hero."""
        from ai import task_router
        return task_router.update_hero(self, hero, dt, view)

    def handle_idle(self, hero, view):
        self.exploration_behavior.handle_idle(self, hero, view)

    def handle_moving(self, hero, view):
        self.bounty_behavior.handle_moving(self, hero, view)

    def handle_fighting(self, hero, view):
        from ai.behaviors import combat
        return combat.handle_fighting(self, hero, view)

    def handle_retreating(self, hero, view):
        from ai.behaviors import recovery
        return recovery.handle_retreating(self, hero, view)

    def _finalize_deferred_task(self, hero, view):
        from ai.behaviors import recovery
        return recovery.finalize_deferred_task(self, hero, view)

    def handle_shopping(self, hero, view):
        """Handle shopping state - wait inside or buy at marketplace/blacksmith (WK11: deferred purchase on exit)."""
        if hero.is_inside_building:
            return  # Wait for inside_timer to expire; finalize_deferred_task runs on pop-out
        buildings = view.buildings

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

        started_journey = self.shopping_behavior.do_shopping(self, hero, shop, view)
        if started_journey:
            return
        hero.state = HeroState.IDLE

    def send_home_to_rest(self, hero, view):
        """Send hero home to rest and heal; prefer Inn if closer (WK11)."""
        buildings = view.buildings
        world = view.world

        # WK11: Prefer Inn when closer than home guild.
        inns = [b for b in buildings if getattr(b, "building_type", None) == BuildingType.INN and getattr(b, "is_constructed", True)]
        if inns and hero.home_building:
            hero_dist_home = hero.distance_to(hero.home_building.center_x, hero.home_building.center_y)
            closest_inn = min(inns, key=lambda b: hero.distance_to(b.center_x, b.center_y))
            if hero.distance_to(closest_inn.center_x, closest_inn.center_y) < hero_dist_home:
                route_to_building(hero, world, buildings, closest_inn)
                hero.state = HeroState.MOVING
                hero.target = {"type": "rest_inn", "inn": closest_inn}
                return

        if hero.home_building:
            route_to_building(hero, world, buildings, hero.home_building)
            hero.state = HeroState.MOVING
            hero.target = {"type": "going_home"}

    def handle_resting(self, hero, dt: float, view):
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
