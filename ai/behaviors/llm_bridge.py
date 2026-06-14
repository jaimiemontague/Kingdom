"""LLM decision bridge behavior extracted from ``BasicAI``."""

from __future__ import annotations

from typing import Any

from config import LLM_DECISION_COOLDOWN, QUEST_DECLINE_COOLDOWN_MS, TILE_SIZE
from ai.behaviors import hunger
from ai.behaviors.view_compat import as_ai_view, view_to_legacy_context
from ai.context_builder import ContextBuilder
from ai.decision_moments import (
    consult_suppressed_by_request_state,
    determine_decision_moment,
)
from ai.quest_chain_context import select_focus_quest_chain
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


def _commit_accept_bounty(ai: Any, hero: Any, view: Any, target: str) -> bool:
    """WK134: resolve an LLM ``accept_bounty`` decision to a real bounty commit.

    Mirrors the heuristic ``bounty_pursuit.maybe_take_bounty`` COMMIT path
    (availability/validity filters + ``start_bounty_pursuit`` + pick-timestamp),
    but NOT its gating (cooldowns / health / min-score): the LLM was only
    offered ``accept_bounty`` while the IDLE_SEEKING_ACTIVITY moment held, and
    the strategic choice is the model's — this resolver only picks WHICH bounty.

    Selection is deterministic (no RNG draw — keeps any future digest scenario
    with bounties stable): the ``target`` string is matched against bounty ids
    first (the prompt's ``bounty_options`` carry ``id``), else the nearest
    valid available bounty wins (same nearest convention as
    ``_resolve_move_target``).

    Returns True iff the hero committed to a bounty.
    """
    # Lazy import (mirrors the quest_offer import below): bounty_pursuit is a
    # behaviors sibling; keeping it out of top-level imports avoids any
    # load-order surprise for the direct-prompt chat path.
    from ai.behaviors import bounty_pursuit

    view = as_ai_view(view)
    bounties = list(view.bounties or [])
    if not bounties:
        return False

    now_ms = sim_now_ms()
    buildings = view.buildings or []
    ttl_ms = int(getattr(ai, "bounty_assign_ttl_ms", 15_000) or 15_000)

    candidates = []
    for bounty in bounties:
        if hasattr(bounty, "is_available_for") and not bounty.is_available_for(
            hero.name, now_ms, ttl_ms
        ):
            continue
        if hasattr(bounty, "is_valid") and not bounty.is_valid(buildings):
            continue
        candidates.append(bounty)
    if not candidates:
        return False

    chosen = None
    want_id = str(target or "").strip()
    if want_id:
        for bounty in candidates:
            if str(getattr(bounty, "bounty_id", "")) == want_id:
                chosen = bounty
                break
    if chosen is None:

        def _dist(b: Any) -> float:
            try:
                gx, gy = (
                    b.get_goal_position(buildings)
                    if hasattr(b, "get_goal_position")
                    else (b.x, b.y)
                )
                return float(hero.distance_to(gx, gy))
            except Exception:
                return float("inf")

        chosen = min(candidates, key=_dist)

    bounty_pursuit.start_bounty_pursuit(ai, hero, chosen, view)
    hero._last_bounty_pick_ms = now_ms
    return True


def _live_sim_from_view(view: Any) -> Any:
    sink = getattr(view, "commands", None)
    return getattr(sink, "_sim", None)


def _quest_chain_focus_from_context(context: dict, hero: Any, target: str = "") -> dict | None:
    chains = list(context.get("quest_chains") or [])
    if not chains:
        return None

    want = str(target or "").strip().lower()
    if want:
        for chain in chains:
            chain_values = {
                str(chain.get("chain_id", "")).strip().lower(),
                str(chain.get("chain_type", "")).strip().lower(),
                str(chain.get("name", "")).strip().lower(),
                str(chain.get("target_id", "")).strip().lower(),
                str(chain.get("target_name", "")).strip().lower(),
                str(chain.get("current_phase_id", "")).strip().lower(),
                str(chain.get("current_phase_title", "")).strip().lower(),
            }
            if want in chain_values:
                return chain

    return select_focus_quest_chain(hero, chains)


def _quest_chain_move_to_phase(ai: Any, hero: Any, focus: dict) -> bool:
    target_position = focus.get("target_position")
    if not isinstance(target_position, (list, tuple)) or len(target_position) != 2:
        return False
    try:
        tx = float(target_position[0])
        ty = float(target_position[1])
    except (TypeError, ValueError):
        return False

    chain_id = str(focus.get("chain_id", "") or "")
    phase_id = str(focus.get("current_phase_id", "") or "")
    phase_title = str(focus.get("current_phase_title", "") or "")
    target_id = str(focus.get("target_id", "") or "")
    target_name = str(focus.get("target_name", "") or "")

    hero.target = {
        "type": "visit_poi",
        "quest_chain_id": chain_id,
        "quest_chain_phase_id": phase_id,
        "quest_chain_phase_title": phase_title,
        "target_id": target_id,
        "target_name": target_name,
        "started_ms": sim_now_ms(),
    }
    hero.set_target_position(tx, ty)
    ai.set_intent(hero, "pursuing_quest_chain")
    return True


def _decline_quest_chain(ai: Any, hero: Any, focus: dict, *, source: str, reason: str, inputs_summary: dict) -> None:
    chain_id = str(focus.get("chain_id", "") or "")
    decline_map = getattr(hero, "_quest_chain_decline_until_ms", None)
    if decline_map is None:
        decline_map = {}
        hero._quest_chain_decline_until_ms = decline_map
    until = int(sim_now_ms()) + int(QUEST_DECLINE_COOLDOWN_MS)
    decline_map[chain_id] = until
    ai.record_decision(
        hero,
        action="decline_chain",
        reason=reason or f"Declined quest chain {focus.get('name', chain_id)}",
        intent=getattr(hero, "intent", "idle") or "idle",
        inputs_summary=inputs_summary,
        source=source,
    )


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
        # WK134: discard any stale undelivered response (e.g. from a request the
        # pending-decision watchdog abandoned) so a late answer to an OLD moment
        # is never misread as the answer to THIS one.
        ai.llm_brain.get_decision(hero.name)
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

    if action in {"accept_chain", "continue_phase", "decline_chain", "retreat_to_heal"}:
        focus = _quest_chain_focus_from_context(context, hero, target)
        if focus is None:
            ai._debug_log(
                f"{hero.name} received quest_chain action={action!r} without a focus chain",
                throttle_key=f"{hero.name}_quest_chain_missing_focus",
            )
            return

        status = str(focus.get("status", "") or "").lower()
        chain_name = str(focus.get("name", "") or focus.get("chain_type", "") or "quest chain")
        chain_id = str(focus.get("chain_id", "") or "")
        if action == "retreat_to_heal":
            ai.set_intent(hero, "returning_to_safety")
            ai.record_decision(
                hero,
                action="retreat_to_heal",
                reason=reason or f"Retreating from {chain_name}",
                intent="returning_to_safety",
                inputs_summary=inputs_summary,
                source=source,
            )
            ai.defense_behavior.start_retreat(ai, hero, view)
            return

        if action == "decline_chain":
            if status != "offered":
                ai._debug_log(
                    f"{hero.name} decline_chain ignored for non-offered chain {chain_id or chain_name}",
                    throttle_key=f"{hero.name}_quest_chain_decline_non_offered",
                )
                return
            _decline_quest_chain(ai, hero, focus, source=source, reason=reason, inputs_summary=inputs_summary)
            return

        if action == "accept_chain":
            if status != "offered":
                ai._debug_log(
                    f"{hero.name} accept_chain ignored for non-offered chain {chain_id or chain_name}",
                    throttle_key=f"{hero.name}_quest_chain_accept_non_offered",
                )
                return
            sim = _live_sim_from_view(view)
            quest_chain_system = getattr(sim, "quest_chain_system", None) if sim is not None else None
            if quest_chain_system is None:
                ai._debug_log(
                    f"{hero.name} accept_chain: no quest_chain_system available",
                    throttle_key=f"{hero.name}_quest_chain_accept_no_system",
                )
                return
            accepted = quest_chain_system.accept_chain(
                chain_id,
                hero=hero,
                event_bus=getattr(sim, "event_bus", None),
                now_ms=sim_now_ms(),
            )
            if not accepted:
                ai._debug_log(
                    f"{hero.name} accept_chain: chain {chain_id or chain_name} no longer available",
                    throttle_key=f"{hero.name}_quest_chain_accept_failed",
                )
                return
            ai.record_decision(
                hero,
                action="accept_chain",
                reason=reason or f"Accepting quest chain {chain_name}",
                intent="pursuing_quest_chain",
                inputs_summary=inputs_summary,
                source=source,
            )
            _quest_chain_move_to_phase(
                ai,
                hero,
                focus,
            )
            return

        if action == "continue_phase":
            if status != "active":
                ai._debug_log(
                    f"{hero.name} continue_phase ignored for non-active chain {chain_id or chain_name}",
                    throttle_key=f"{hero.name}_quest_chain_continue_non_active",
                )
                return
            ai.record_decision(
                hero,
                action="continue_phase",
                reason=reason or f"Continuing quest chain {chain_name}",
                intent="pursuing_quest_chain",
                inputs_summary=inputs_summary,
                source=source,
            )
            moved = _quest_chain_move_to_phase(
                ai,
                hero,
                focus,
            )
            if not moved:
                ai._debug_log(
                    f"{hero.name} continue_phase: no usable target on chain {chain_id or chain_name}",
                    throttle_key=f"{hero.name}_quest_chain_continue_no_target",
                )
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
        # WK134: previously a dead no-op while IDLE_SEEKING_ACTIVITY offered
        # accept_bounty to the LLM. Now routes through the bounty-pursuit
        # commit path; with no resolvable bounty it degrades to explore (same
        # shape as the unresolvable move_to fallback below).
        if _commit_accept_bounty(ai, hero, view, target or ""):
            ai.set_intent(hero, "pursuing_bounty")
            ai.record_decision(
                hero,
                action="accept_bounty",
                reason=reason or "Accepting a bounty",
                intent="pursuing_bounty",
                inputs_summary=inputs_summary,
                source=source,
            )
        else:
            ai._debug_log(
                f"{hero.name} accept_bounty: no valid bounty available; exploring instead",
                throttle_key=f"{hero.name}_accept_bounty_fallback",
            )
            ai.set_intent(hero, "idle")
            ai.record_decision(
                hero,
                action="accept_bounty",
                reason=reason or "No valid bounty available; exploring",
                intent="idle",
                inputs_summary=inputs_summary,
                source=source,
            )
            ai.exploration_behavior.explore(ai, hero, view)
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
