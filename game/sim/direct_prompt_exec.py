"""
WK50 Phase 2B: apply validated direct-prompt tool actions with engine-side target resolution.

Chat text is shown from ``spoken_response`` in the engine; physical effects use only
validated fields, with move targets resolved here (known-place ids, compass explore).

WK68 Wave R4 (finishes Move 5): the chat path no longer consumes the live
``get_game_state()`` UI dict (which carried the mutable ``sim``/``world``/
``economy``/``engine``). ``game.engine`` now drives this with the read-only
``AiGameView`` from ``SimEngine.build_ai_view()``. The view-or-dict input is
normalized once at the boundary via :func:`ai.behaviors.view_compat.as_ai_view`
and projected to the legacy ``game_state``-shaped dict the in-module resolvers
(:func:`resolve_move_destination` / :func:`resolve_explore_direction_target`) and
the LLM-context builder still take. That projected dict is built fresh from the
view and carries NO ``economy``/``sim``/``engine`` — closing the last L3 read
leak on the chat path. The legacy-dict callers (the WK50 integration/resolve
tests) keep working: ``as_ai_view`` wraps a dict in a read-only adapter, so the
same projection is produced either way.
"""

from __future__ import annotations

from typing import Any

from ai.behaviors.llm_bridge import apply_llm_decision
from ai.behaviors.view_compat import as_ai_view, view_to_legacy_context
from ai.context_builder import ContextBuilder

from game.sim.direct_prompt_commit import (
    DIRECT_PROMPT_TARGET_TYPE,
    attach_direct_prompt_move,
)
from game.sim.direct_prompt_targets import (
    parse_compass_direction,
    resolve_explore_direction_target,
    resolve_move_destination,
    strip_untrusted_spatial_fields,
)


def _commit_snapshot(hero: Any) -> tuple[Any, bool]:
    return (
        getattr(hero, "llm_move_request", None),
        bool(getattr(hero, "is_inside_building", False)),
    )


def _infer_physical_after_llm(
    hero: Any, prior_rq: Any, was_inside: bool, tool: str
) -> bool:
    """True when fallback ``apply_llm_decision`` likely applied a physical effect."""
    target = getattr(hero, "target", None)
    if isinstance(target, dict) and target.get("type") == DIRECT_PROMPT_TARGET_TYPE:
        return True
    rq = getattr(hero, "llm_move_request", None)
    tl = (tool or "").strip().lower()
    if tl in ("move_to", "retreat", "explore") and rq is not None and rq != prior_rq:
        return True
    if tl in ("use_potion", "buy_item", "fight"):
        return True
    if tl == "leave_building":
        return was_inside and not bool(getattr(hero, "is_inside_building", False))
    return False


def apply_validated_direct_prompt_physical(
    ai: Any,
    hero: Any,
    decision: dict[str, Any],
    view_or_game_state: Any,
    *,
    player_message: str,
    source: str = "chat",
) -> bool:
    """
    Mirror ``apply_llm_decision`` but resolve ``move_to`` via hero known-place ids first
    and ``explore_direction`` via deterministic compass targets (no RNG wander).

    Returns whether a physical sim effect was committed (movement commit, potion, shop
    intent, etc.) for UI feedback.

    WK68 R4: ``view_or_game_state`` is the read-only :class:`AiGameView` on the live
    chat path (``game.engine`` passes ``SimEngine.build_ai_view()``); legacy callers
    (WK50 tests) still pass a ``game_state`` dict. Both are normalized to a single
    AiGameView surface via :func:`as_ai_view`. The in-module resolvers + the LLM
    context builder take a ``game_state``-shaped dict, so we project the view to that
    shape ONCE here (carrying NO ``economy``/``sim``/``engine``); the view itself is
    handed to :func:`apply_llm_decision`, which accepts view-or-dict directly.
    """
    view = as_ai_view(view_or_game_state)
    game_state = view_to_legacy_context(view)
    sanitized = strip_untrusted_spatial_fields(decision)
    tool = sanitized.get("tool_action") or sanitized.get("action")
    intent = str(sanitized.get("interpreted_intent") or "")
    action = sanitized.get("action") or ""

    if tool == "move_to" or action == "move_to":
        dest = resolve_move_destination(hero, game_state, sanitized)
        context = ContextBuilder.build_hero_context(hero, game_state)
        inputs_summary = ContextBuilder.build_inputs_summary(context)
        reason = sanitized.get("reasoning", "") or "Direct prompt movement"
        if not isinstance(reason, str):
            reason = str(reason)
        if dest is not None:
            sub_intent = str(intent or "go_to_known_place").strip() or "go_to_known_place"
            attach_direct_prompt_move(hero, sub_intent=sub_intent, wx=dest[0], wy=dest[1])
            ai.set_intent(hero, "moving_to_destination")
            ai.record_decision(
                hero,
                action="move_to",
                reason=reason or "Moving (direct prompt)",
                intent="moving_to_destination",
                inputs_summary=inputs_summary,
                source=source,
            )
            return True
        prior_rq, was_inside = _commit_snapshot(hero)
        apply_llm_decision(ai, hero, sanitized, view, source=source, context=context)
        eff = str(sanitized.get("tool_action") or sanitized.get("action") or "move_to").strip().lower()
        return _infer_physical_after_llm(hero, prior_rq, was_inside, eff)

    if (tool == "explore" or action == "explore") and intent == "explore_direction":
        context = ContextBuilder.build_hero_context(hero, game_state)
        inputs_summary = ContextBuilder.build_inputs_summary(context)
        reason = sanitized.get("reasoning", "") or "Exploring (directed)"
        if not isinstance(reason, str):
            reason = str(reason)
        dirn = parse_compass_direction(
            player_message,
            str(sanitized.get("target_description") or ""),
            str(sanitized.get("target_id") or ""),
        )
        if dirn:
            dest = resolve_explore_direction_target(hero, game_state, dirn)
            if dest is not None:
                attach_direct_prompt_move(
                    hero, sub_intent="explore_direction", wx=dest[0], wy=dest[1]
                )
                ai.set_intent(hero, "moving_to_destination")
                ai.record_decision(
                    hero,
                    action="explore",
                    reason=f"{reason} [{dirn}]",
                    intent="moving_to_destination",
                    inputs_summary=inputs_summary,
                    source=source,
                )
                return True
        prior_rq, was_inside = _commit_snapshot(hero)
        apply_llm_decision(ai, hero, sanitized, view, source=source, context=context)
        eff = str(sanitized.get("tool_action") or sanitized.get("action") or "explore").strip().lower()
        return _infer_physical_after_llm(hero, prior_rq, was_inside, eff)

    tl = (tool or "").strip().lower()
    ac = (action or "").strip().lower()

    # R16: Long-journey sovereign lock for shopping / retreat (same pattern as move_to + explore).
    if tl == "buy_item" or ac == "buy_item":
        merged = dict(sanitized)
        if not str(merged.get("action") or "").strip():
            merged["action"] = "buy_item"
        prior_rq, was_inside = _commit_snapshot(hero)
        apply_llm_decision(ai, hero, merged, view, source=source)
        tp = getattr(hero, "target_position", None)
        if tp is None:
            return _infer_physical_after_llm(hero, prior_rq, was_inside, "buy_item")
        sub = str(intent or "buy_potions").strip() or "buy_potions"
        attach_direct_prompt_move(hero, sub_intent=sub, wx=float(tp[0]), wy=float(tp[1]))
        return True

    if tl == "retreat" or ac == "retreat":
        merged = dict(sanitized)
        if not str(merged.get("action") or "").strip():
            merged["action"] = "retreat"
        prior_rq, was_inside = _commit_snapshot(hero)
        apply_llm_decision(ai, hero, merged, view, source=source)
        tp = getattr(hero, "target_position", None)
        if tp is None:
            return _infer_physical_after_llm(hero, prior_rq, was_inside, "retreat")
        sub = str(intent or "seek_healing").strip() or "retreat"
        attach_direct_prompt_move(hero, sub_intent=sub, wx=float(tp[0]), wy=float(tp[1]))
        return True

    prior_rq, was_inside = _commit_snapshot(hero)
    apply_llm_decision(ai, hero, sanitized, view, source=source)
    eff = str(sanitized.get("tool_action") or sanitized.get("action") or "").strip().lower()
    return _infer_physical_after_llm(hero, prior_rq, was_inside, eff)
