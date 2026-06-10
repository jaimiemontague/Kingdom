"""LLM decision bridge behavior extracted from ``BasicAI``."""

from __future__ import annotations

from typing import Any

from config import LLM_DECISION_COOLDOWN, TILE_SIZE
from ai.behaviors import hunger
from ai.behaviors.view_compat import as_ai_view, view_to_legacy_context
from ai.context_builder import ContextBuilder
from ai.decision_moments import (
    consult_suppressed_by_request_state,
    determine_decision_moment,
)
from ai.profile_context_adapter import build_llm_context_for_moment
from game.entities.hero import HeroState
from game.sim.timebase import now_ms as sim_now_ms


def _resolve_move_target(target: str, view: Any, hero: Any) -> tuple[float, float] | None:
    """Resolve LLM move_to target string to world (x, y). WK18: used to hook move_to into physical engine."""
    if not target or not isinstance(target, str):
        return None
    view = as_ai_view(view)
    t = target.strip().lower()
    buildings = view.buildings or []
    # Map common names to building_type.
    type_map = {
        "castle": "castle",
        "market": "marketplace",
        "marketplace": "marketplace",
        "inn": "inn",
        "tavern": "inn",
        "blacksmith": "blacksmith",
        "smith": "blacksmith",
        "safety": "castle",  # retreat-like
        "warrior_guild": "warrior_guild",
        "ranger_guild": "ranger_guild",
        "rogue_guild": "rogue_guild",
        "wizard_guild": "wizard_guild",
        "temple": "temple",
    }
    btype = type_map.get(t)
    if not btype:
        return None
    candidates = [b for b in buildings if getattr(b, "building_type", None) == btype]
    if not candidates:
        return None
    # Nearest to hero.
    best = min(candidates, key=lambda b: (hero.x - getattr(b, "center_x", 0)) ** 2 + (hero.y - getattr(b, "center_y", 0)) ** 2)
    return (float(getattr(best, "center_x", 0)), float(getattr(best, "center_y", 0)))


def should_consult_llm(ai: Any, hero: Any, view: Any) -> bool:
    """Determine if we should ask the LLM for a decision (WK50: named decision moments)."""
    view = as_ai_view(view)
    current_time = sim_now_ms()
    moment = determine_decision_moment(hero, view_to_legacy_context(view), now_ms=current_time)
    if moment is None:
        return False
    cooldown_ms = max(LLM_DECISION_COOLDOWN, moment.cooldown_ms)
    if consult_suppressed_by_request_state(hero, current_time, cooldown_ms) is not None:
        return False
    return True


def request_llm_decision(ai: Any, hero: Any, view: Any) -> None:
    """Request a decision from the LLM brain."""
    if ai.llm_brain:
        view = as_ai_view(view)
        now = sim_now_ms()
        legacy = view_to_legacy_context(view)
        moment = determine_decision_moment(hero, legacy, now_ms=now)
        if moment is None:
            return
        base_context = ContextBuilder.build_hero_context(hero, legacy)
        autonomous = build_llm_context_for_moment(hero, legacy, moment, now_ms=now)
        context = {**base_context, "wk50_autonomous": autonomous}
        ai.llm_brain.request_decision(hero.name, context)
        hero.pending_llm_decision = True
        hero.last_llm_decision_time = now
        ai.record_decision(
            hero,
            action="request_llm",
            reason=f"Consulting LLM ({moment.moment_type.value})",
            intent=getattr(hero, "intent", "idle") or "idle",
            inputs_summary=ContextBuilder.build_inputs_summary(base_context),
            source="system",
        )


def apply_llm_decision(
    ai: Any,
    hero: Any,
    decision: dict,
    view: Any,
    *,
    source: str = "llm",
    context: dict | None = None,
) -> None:
    """Apply an LLM decision to the hero (WK18: supports obey_defy and tool_action).

    WK67 Move 5: ``view`` is normally the read-only ``AiGameView`` (AI path). The
    direct-prompt chat path (``game.sim.direct_prompt_exec``) still drives this
    with the legacy UI ``game_state`` dict; :func:`as_ai_view` normalizes either
    form to the view surface the migrated behaviors read.
    """
    view = as_ai_view(view)
    action = decision.get("action", "")
    target = decision.get("target", "")
    tool_action = decision.get("tool_action") or action
    obey_defy = decision.get("obey_defy", "Obey")

    hero.last_llm_action = decision

    if context is None:
        context = ContextBuilder.build_hero_context(hero, view_to_legacy_context(view))
    inputs_summary = ContextBuilder.build_inputs_summary(context)
    reason = decision.get("reasoning", "")
    if not isinstance(reason, str):
        reason = ""

    if hunger.maybe_apply_meal_before_llm_action(ai, hero, view, action):
        return

    # WK126-T6: a staged quest offer (hero standing at a quest-giver) consumes
    # this decision as the accept/decline verdict — the REAL wiring the
    # accept_bounty no-op below never got. Inert unless hero._pending_quest_offer
    # is set (impossible in the WK67 digest scenario — no givers exist). Lazy
    # import: quest_offer imports decision_moments, which this module also
    # imports; keeping it out of the top-level imports avoids any load-order
    # surprise for the direct-prompt chat path.
    from ai.behaviors import quest_offer as _quest_offer

    if _quest_offer.maybe_apply_quest_offer_decision(ai, hero, decision, view, source=source):
        return

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
        ai.defense_behavior.start_retreat(ai, hero, view)
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
        ai.shopping_behavior.go_shopping(ai, hero, target, view)
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
        ai.exploration_behavior.explore(ai, hero, view)
    elif action == "accept_bounty":
        pass
    elif tool_action == "leave_building" or action == "leave_building":
        if getattr(hero, "is_inside_building", False):
            hero.pop_out_of_building()
            setattr(hero, "pending_task", None)
            setattr(hero, "pending_task_building", None)
        ai.set_intent(hero, "idle")
        ai.record_decision(
            hero,
            action="leave_building",
            reason=reason or "Leaving building",
            intent="idle",
            inputs_summary=inputs_summary,
            source=source,
        )
        hero.state = HeroState.IDLE
    elif tool_action == "move_to" or action == "move_to":
        # WK18: Resolve target to (x,y) and set llm_move_request; engine drains into physical state.
        dest = _resolve_move_target(target or "", view, hero)
        if dest is not None:
            hero.llm_move_request = dest
            ai.set_intent(hero, "moving_to_destination")
            ai.record_decision(
                hero,
                action="move_to",
                reason=reason or f"Moving to {target or 'destination'}",
                intent="moving_to_destination",
                inputs_summary=inputs_summary,
                source=source,
            )
        else:
            ai.set_intent(hero, "idle")
            ai.record_decision(
                hero,
                action="move_to",
                reason=reason or f"Moving to {target or 'destination'}",
                intent="idle",
                inputs_summary=inputs_summary,
                source=source,
            )
            ai.exploration_behavior.explore(ai, hero, view)
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
