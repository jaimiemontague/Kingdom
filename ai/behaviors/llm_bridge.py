"""LLM decision bridge behavior extracted from ``BasicAI``."""

from __future__ import annotations

from typing import Any

from config import HEALTH_THRESHOLD_FOR_DECISION, LLM_DECISION_COOLDOWN, TILE_SIZE
from ai.context_builder import ContextBuilder
from game.entities.hero import HeroState
from game.sim.timebase import now_ms as sim_now_ms


def should_consult_llm(ai: Any, hero: Any, game_state: dict) -> bool:
    """Determine if we should ask the LLM for a decision."""
    current_time = sim_now_ms()

    # Respect cooldown.
    if current_time - hero.last_llm_decision_time < LLM_DECISION_COOLDOWN:
        return False

    # Don't stack requests.
    if hero.pending_llm_decision:
        return False

    # Critical decision points:
    # 1. Health is low during combat.
    if hero.state == HeroState.FIGHTING and hero.health_percent < HEALTH_THRESHOLD_FOR_DECISION:
        return True

    # 2. Has gold and near marketplace.
    if hero.gold >= 30:
        for building in game_state.get("buildings", []):
            if building.building_type == "marketplace":
                dist = hero.distance_to(building.center_x, building.center_y)
                if dist < TILE_SIZE * 6:
                    return True

    return False


def request_llm_decision(ai: Any, hero: Any, game_state: dict) -> None:
    """Request a decision from the LLM brain."""
    if ai.llm_brain:
        context = ContextBuilder.build_hero_context(hero, game_state)
        ai.llm_brain.request_decision(hero.name, context)
        hero.pending_llm_decision = True
        hero.last_llm_decision_time = sim_now_ms()
        ai.record_decision(
            hero,
            action="request_llm",
            reason="Consulting LLM for decision",
            intent=getattr(hero, "intent", "idle") or "idle",
            inputs_summary=ContextBuilder.build_inputs_summary(context),
            source="system",
        )


def apply_llm_decision(
    ai: Any,
    hero: Any,
    decision: dict,
    game_state: dict,
    *,
    source: str = "llm",
    context: dict | None = None,
) -> None:
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
        ai.set_intent(hero, "returning_to_safety")
        ai.record_decision(
            hero,
            action="retreat",
            reason=reason or "Retreating",
            intent="returning_to_safety",
            inputs_summary=inputs_summary,
            source=source,
        )
        ai.defense_behavior.start_retreat(ai, hero, game_state)
    elif action == "fight":
        ai.set_intent(hero, "engaging_enemy")
        ai.record_decision(
            hero,
            action="fight",
            reason=reason or "Fighting",
            intent="engaging_enemy",
            inputs_summary=inputs_summary,
            source=source,
        )
        hero.state = HeroState.FIGHTING
    elif action == "buy_item":
        ai.set_intent(hero, "shopping")
        ai.record_decision(
            hero,
            action="buy_item",
            reason=reason or f"Buying {target}",
            intent="shopping",
            inputs_summary=inputs_summary,
            source=source,
        )
        ai.shopping_behavior.go_shopping(ai, hero, target, game_state)
    elif action == "use_potion":
        ai.record_decision(
            hero,
            action="use_potion",
            reason=reason or "Using potion",
            intent=getattr(hero, "intent", "idle") or "idle",
            inputs_summary=inputs_summary,
            source=source,
        )
        hero.use_potion()
    elif action == "explore":
        ai.set_intent(hero, "idle")
        ai.record_decision(
            hero,
            action="explore",
            reason=reason or "Exploring",
            intent="idle",
            inputs_summary=inputs_summary,
            source=source,
        )
        ai.exploration_behavior.explore(ai, hero, game_state)
    elif action == "accept_bounty":
        pass
    else:
        ai._debug_log(
            f"{hero.name} received unknown LLM action={action!r}; ignoring",
            throttle_key=f"{hero.name}_unknown_llm_action",
        )
        ai.record_decision(
            hero,
            action=str(action or "unknown"),
            reason="Unknown LLM action; ignored",
            intent=getattr(hero, "intent", "idle") or "idle",
            inputs_summary=inputs_summary,
            source=source,
        )
