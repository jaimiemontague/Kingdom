"""
Validate autonomous LLM JSON decisions against DecisionMoment allowlists (WK50 Phase 2A).

Invalid or incomplete payloads return None so callers can use get_fallback_decision().
"""

from __future__ import annotations

from typing import Any

from ai.decision_moments import DecisionMoment

_ACTIONS_NEEDING_TARGET = frozenset({"move_to", "buy_item"})


def _norm_action(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    return s or None


def _norm_target(raw: Any) -> str:
    if raw is None:
        return ""
    return str(raw).strip()


def validate_autonomous_decision(raw: dict[str, Any] | None, moment: DecisionMoment) -> dict[str, Any] | None:
    """
    If valid, return a normalized decision dict compatible with apply_llm_decision / fallback shape.
    Otherwise None.
    """
    if not isinstance(raw, dict):
        return None
    allowed = moment.allowed_actions_set()
    action = _norm_action(raw.get("action"))
    if action is None or action not in allowed:
        return None
    target = _norm_target(raw.get("target"))
    if action in _ACTIONS_NEEDING_TARGET and not target:
        return None
    reasoning = raw.get("reasoning", "")
    if not isinstance(reasoning, str):
        reasoning = str(reasoning)
    reasoning = reasoning.strip()[:500]

    conf = raw.get("confidence", 0.0)
    try:
        cf = float(conf)
    except (TypeError, ValueError):
        cf = 0.0
    cf = max(0.0, min(1.0, cf))

    mem_used = raw.get("memory_used")
    if mem_used is None:
        mem_list: list[str] = []
    elif isinstance(mem_used, list):
        mem_list = [str(x) for x in mem_used][:16]
    else:
        mem_list = [str(mem_used)]

    pers = raw.get("personality_influence", "")
    if not isinstance(pers, str):
        pers = str(pers)
    pers = pers.strip()[:200]

    return {
        "action": action,
        "target": target,
        "reasoning": reasoning or f"chosen {action} for {moment.moment_type.value}",
        "confidence": cf,
        "memory_used": mem_list,
        "personality_influence": pers,
        "obey_defy": "Obey",
        "tool_action": action,
    }
