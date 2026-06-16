"""WK120 (roadmap Move 12, faithful form): the per-hero AI decision dispatch ("task
router") extracted verbatim from BasicAI.update_hero. BasicAI keeps a 1-line delegating
wrapper; this function takes the BasicAI instance as ``ai``. Byte-faithful move — no
behavior change (WK67 digest byte-identical).

NOTE: the roadmap's competitive propose()->TaskProposal re-architecture is a separate,
behavior-affecting enhancement (it would shift the WK67 digest) and is intentionally NOT
done here — see the WK120 plan §0."""
from __future__ import annotations

from ai.behaviors import bounty_pursuit, quest_offer
from ai.behaviors.view_compat import as_ai_view, view_to_legacy_context
from ai.context_builder import ContextBuilder
from ai.prompt_templates import get_fallback_decision
from config import TILE_SIZE
from game.entities.hero import HeroState
from game.sim.direct_prompt_commit import (
    clear_direct_prompt_commit,
    expire_direct_prompt_commit_if_timed_out,
)
from game.sim.timebase import now_ms as sim_now_ms

# WK134: watchdog for a hung/slow provider. A pending LLM request whose answer
# has not arrived within this many sim-ms is abandoned (pending_llm_decision
# cleared) so the hero can consult again — otherwise a provider that ignores
# LLM_TIMEOUT (or a wedged worker) suppresses every future consult AND the
# quest-giver approach forever. Sim-time on purpose (deterministic under pause /
# FAST speed); generously above LLM_TIMEOUT (5s wall) and CONVERSATION_TIMEOUT
# (8s wall) even at 2x sim speed.
PENDING_LLM_DECISION_TIMEOUT_MS = 20_000


def update_hero(ai, hero, dt: float, view) -> None:
    """Update AI for a single hero."""
    # WK67 Move 5: the sim drives this with an AiGameView. A few callers/tests
    # may still pass the legacy game_state dict; normalize to the view surface.
    view = as_ai_view(view)
    # Keep intent non-empty even if we make no decision this tick.
    ai.refresh_intent(hero, view)
    expire_direct_prompt_commit_if_timed_out(hero)

    if getattr(hero, "is_captured", False) or hero.state == HeroState.CAPTURED:
        hero.pending_llm_decision = False
        return

    # WK2 Build A: stuck detection + deterministic recovery.
    ai.stuck_recovery_behavior._update_stuck_and_recover(ai, hero, view)

    # WK15: Castle under attack — urgent priority: drop everything (including popping out) and defend.
    castle = view.castle
    if castle and getattr(castle, "is_under_attack", False):
        clear_direct_prompt_commit(hero)
        if getattr(hero, "is_inside_building", False):
            hero.pop_out_of_building()
            setattr(hero, "pending_task", None)
            setattr(hero, "pending_task_building", None)
        ai.defense_behavior.defend_castle(ai, hero, view, castle)
        return

    # WK11: Finalize deferred task when hero just left a building (pending_task set, not inside).
    if not hero.is_inside_building:
        pending = getattr(hero, "pending_task", None)
        pending_building = getattr(hero, "pending_task_building", None)
        if pending and pending_building:
            ai._finalize_deferred_task(hero, view)
            return

    # Handle resting state first (doesn't need LLM).
    if hero.state == HeroState.RESTING:
        if bounty_pursuit.bounty_commitment_active(hero, view, now_ms=sim_now_ms()):
            if ai.bounty_behavior.resume_committed_bounty(ai, hero, view):
                return
        ai.handle_resting(hero, dt, view)
        return

    # Priority: defend castle when actually threatened (unless already fighting).
    # WK127-T1: was `castle.is_damaged or is_under_attack` — a merely-chipped
    # castle with no enemies near must NOT hijack every hero, forever.
    # building_threatened checks is_under_attack first, then enemies within
    # 6 tiles — one tile wider than the home-guild gate (5) because the castle
    # is the kingdom anchor and defend_castle pulls heroes from anywhere.
    castle = view.castle
    if (
        castle
        and ai.defense_behavior.building_threatened(view, castle, 6)
        and hero.state != HeroState.FIGHTING
    ):
        clear_direct_prompt_commit(hero)
        ai.defense_behavior.defend_castle(ai, hero, view, castle)
        return

    # WK15: Warriors prioritize defending economic buildings (farm, food_stand) under attack.
    if hero.state != HeroState.FIGHTING and getattr(hero, "hero_class", "") == "warrior":
        if ai.defense_behavior.defend_economic_building_warrior(ai, hero, view):
            return

    # WK124-T4b: Clerics seek and support wounded/fighting allies. Returns False
    # (no takeover, no state change) when no ally needs support, so the cleric
    # falls through to her default behavior. This is inert in the WK67 digest
    # scenario (nobody wounded, no combat) → digest byte-identical. Class-gated.
    if hero.state != HeroState.FIGHTING and getattr(hero, "hero_class", "") == "cleric":
        if ai.support_behavior.cleric_seek_and_support(ai, hero, view):
            return

    # Priority: defend home building when actually threatened.
    # WK127-T1: was `is_damaged` (any missing HP, forever) — with repairs
    # stalled that pinned heroes IDLE at their guild permanently. 5 tiles =
    # the radius defend_home_building already scans for its target.
    if (
        hero.home_building
        and ai.defense_behavior.building_threatened(view, hero.home_building, 5)
        and hero.state != HeroState.FIGHTING
    ):
        ai.defense_behavior.defend_home_building(ai, hero, view)
        return

    # Priority: defend nearby neutral buildings if under attack.
    if hero.state != HeroState.FIGHTING:
        if ai.defense_behavior.defend_neutral_building_if_visible(ai, hero, view):
            return

    # WK61-R12: hunger meals for all non-retreating heroes (including FIGHTING when HP > critical).
    if hero.state not in (HeroState.RETREATING, HeroState.DEAD):
        if ai.hunger_behavior.tick_meal_hunger(ai, hero, view):
            target = getattr(hero, "target", None)
            if isinstance(target, dict) and target.get("type") == "buy_meal":
                return

    # Healthy heroes with a live bounty commitment should keep that promise
    # before any passive rest/home handling can steal the tick.
    if hero.state == HeroState.IDLE:
        if bounty_pursuit.bounty_commitment_active(hero, view, now_ms=sim_now_ms()):
            if ai.bounty_behavior.resume_committed_bounty(ai, hero, view):
                return

    # Check if hero should go home to rest (priority check, only if home is safe).
    if hero.state == HeroState.IDLE and hero.should_go_home_to_rest():
        if hero.can_rest_at_home():
            if ai.bounty_behavior.resume_committed_bounty(ai, hero, view):
                return
            # Bugfix v1.3.4: don't route to Inn/home to rest if enemies are nearby
            # and the hero isn't critically low HP. Let the state machine engage instead.
            enemies = view.enemies
            combat_guard_radius = TILE_SIZE * 5  # ~5 tiles / 160px
            enemies_nearby = any(
                getattr(e, "is_alive", False) and hero.distance_to(e.x, e.y) <= combat_guard_radius
                for e in enemies
            )
            if enemies_nearby and hero.health_percent > 0.25:
                ai._debug_log(
                    f"{hero.name} -> skipping rest (enemies nearby, hp={hero.health_percent:.0%})",
                    throttle_key=f"{hero.name}_skip_rest_enemy",
                )
            else:
                ai.send_home_to_rest(hero, view)
                return

    # WK17: Intent conviction — do not consult or apply LLM when hero is committed to a destination.
    if not ai._is_committed_destination(hero):
        # Check if we need an LLM decision.
        if ai.llm_bridge_behavior.should_consult_llm(ai, hero, view):
            # If no LLM brain is wired, still choose via deterministic fallback so
            # the no-LLM path produces stable intent/decision logging.
            if ai.llm_brain:
                ai.llm_bridge_behavior.request_llm_decision(ai, hero, view)
            else:
                context = ContextBuilder.build_hero_context(hero, view_to_legacy_context(view))
                decision = get_fallback_decision(context)
                ai.llm_bridge_behavior.apply_llm_decision(
                    ai,
                    hero,
                    decision,
                    view,
                    source="fallback",
                    context=context,
                )

        # Handle LLM decision response.
        if hero.pending_llm_decision and ai.llm_brain:
            decision = ai.llm_brain.get_decision(hero.name)
            if decision:
                context = ContextBuilder.build_hero_context(hero, view_to_legacy_context(view))
                src = "mock" if getattr(ai.llm_brain, "provider_name", None) == "mock" else "llm"
                ai.llm_bridge_behavior.apply_llm_decision(
                    ai, hero, decision, view, source=src, context=context
                )
                hero.pending_llm_decision = False
            else:
                # WK134 watchdog: never let a hung provider wedge this hero —
                # pending_llm_decision must ALWAYS clear (see constant above).
                last = int(getattr(hero, "last_llm_decision_time", 0) or 0)
                if sim_now_ms() - last > PENDING_LLM_DECISION_TIMEOUT_MS:
                    hero.pending_llm_decision = False
                    ai._debug_log(
                        f"{hero.name} -> abandoned stale LLM request (> "
                        f"{PENDING_LLM_DECISION_TIMEOUT_MS}ms, provider slow/hung)",
                        throttle_key=f"{hero.name}_llm_pending_timeout",
                    )
    else:
        # Committed to destination: do not apply a stale pending decision when we later become IDLE.
        if hero.pending_llm_decision:
            hero.pending_llm_decision = False

    # State machine behavior.
    if hero.state == HeroState.IDLE:
        ai.handle_idle(hero, view)
    elif hero.state == HeroState.MOVING:
        ai.handle_moving(hero, view)
    elif hero.state == HeroState.FIGHTING:
        ai.handle_fighting(hero, view)
    elif hero.state == HeroState.RETREATING:
        ai.handle_retreating(hero, view)
    elif hero.state == HeroState.SHOPPING:
        ai.handle_shopping(hero, view)

    # WK126-T5: LOWEST-priority tier — occasional walk to an open quest-giver.
    # Runs AFTER the state dispatch so every higher tier (survival, defense,
    # hunger, rest, bounty, shopping, enemy engage, drink, POI) has already
    # claimed the hero if it wanted to; it may only preempt the terminal
    # patrol/idle wander (enforced inside via the preemptible-target guard).
    # DIGEST RAIL: the function's FIRST guard is `if not view.quest_givers:
    # return False` — no RNG draw, no sim-time read, no hero mutation when no
    # givers exist, so the WK67 digest scenario is byte-identical.
    quest_offer.maybe_approach_quest_giver(ai, hero, view)
