"""Shared quest-chain AI context helpers.

These helpers keep quest-chain prompt data bounded and deterministic while
staying on the AI side of the boundary. They never mutate sim state.
"""

from __future__ import annotations

from typing import Any, Iterable

from game.content.quest_chains import get_chain_def
from game.sim.timebase import now_ms as sim_now_ms

_MAX_CHAIN_HISTORY = 8
_MAX_PHASE_HISTORY = 4
_MAX_QUEST_CHAINS = 3


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _norm_str(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _target_position(value: Any) -> tuple[float, float] | None:
    if value in (None, ""):
        return None
    if isinstance(value, tuple) and len(value) == 2:
        try:
            return (float(value[0]), float(value[1]))
        except (TypeError, ValueError):
            return None
    if isinstance(value, list) and len(value) == 2:
        try:
            return (float(value[0]), float(value[1]))
        except (TypeError, ValueError):
            return None
    return None


def _history_summary(entry: Any) -> dict[str, Any]:
    return {
        "event": _norm_str(_value(entry, "event", "")),
        "phase_id": _norm_str(_value(entry, "phase_id", "")),
        "phase_title": _norm_str(_value(entry, "phase_title", "")),
        "status": _norm_str(_value(entry, "status", "")),
        "hero_id": _value(entry, "hero_id", None),
        "target_id": _norm_str(_value(entry, "target_id", "")),
        "target_name": _norm_str(_value(entry, "target_name", "")),
        "target_position": _target_position(_value(entry, "target_position", None)),
        "at_ms": _safe_int(_value(entry, "at_ms", _value(entry, "time_ms", 0))),
    }


def _phase_summary(phase: Any) -> dict[str, Any]:
    history_raw = list(_value(phase, "history", ()) or ())
    return {
        "phase_id": _norm_str(_value(phase, "phase_id", "")),
        "title": _norm_str(_value(phase, "title", "")),
        "objective_type": _norm_str(_value(phase, "objective_type", "")),
        "status": _norm_str(_value(phase, "status", "")),
        "assigned_hero_id": _value(phase, "assigned_hero_id", None),
        "target_id": _norm_str(_value(phase, "target_id", "")),
        "target_name": _norm_str(_value(phase, "target_name", "")),
        "target_position": _target_position(_value(phase, "target_position", None)),
        "history": tuple(_history_summary(entry) for entry in history_raw[:_MAX_PHASE_HISTORY]),
    }


def summarize_quest_chain(chain: Any) -> dict[str, Any]:
    """Return a primitive-only quest-chain snapshot for prompt use."""
    chain_type = _norm_str(_value(chain, "chain_type", ""))
    definition = None
    reward_gold = 0
    difficulty_tier = 0
    if chain_type:
        try:
            definition = get_chain_def(chain_type)
        except Exception:
            definition = None
    if definition is not None:
        try:
            reward_gold = _safe_int(getattr(definition.reward_profile, "gold", 0))
        except Exception:
            reward_gold = 0
        difficulty_tier = _safe_int(getattr(definition, "difficulty_tier", 0))

    phases_raw = list(_value(chain, "phases", ()) or ())
    phases = tuple(_phase_summary(phase) for phase in phases_raw)
    history_source = _value(chain, "history", None)
    if history_source in (None, ()):
        # Summaries built earlier in the prompt stack carry this field as
        # ``phase_history``. Preserve it when re-summarizing a snapshot dict so
        # the focused quest-chain prompt block keeps the actual chain history.
        history_source = _value(chain, "phase_history", ())
    history_raw = list(history_source or ())
    phase_history = tuple(_history_summary(entry) for entry in history_raw[:_MAX_CHAIN_HISTORY])

    return {
        "chain_id": _safe_int(_value(chain, "chain_id", 0)),
        "chain_type": chain_type,
        "name": _norm_str(_value(chain, "name", "")),
        "status": _norm_str(_value(chain, "status", "")),
        "assigned_hero_id": _value(chain, "assigned_hero_id", None),
        "current_phase_id": _norm_str(_value(chain, "current_phase_id", "")),
        "current_phase_title": _norm_str(_value(chain, "current_phase_title", "")),
        "current_objective_type": _norm_str(_value(chain, "current_objective_type", "")),
        "target_id": _norm_str(_value(chain, "target_id", "")),
        "target_name": _norm_str(_value(chain, "target_name", "")),
        "target_position": _target_position(_value(chain, "target_position", None)),
        "reward_gold": reward_gold,
        "stakes": {
            "difficulty_tier": difficulty_tier,
            "phase_count": len(phases),
        },
        "phases": phases,
        "phase_history": phase_history,
    }


def summarize_quest_chains(chains: Iterable[Any] | None) -> list[dict[str, Any]]:
    """Summarize quest chains and keep the list bounded/sorted for prompts."""
    if not chains:
        return []
    summaries = [summarize_quest_chain(chain) for chain in chains]

    def _rank(chain: dict[str, Any]) -> tuple[int, int, str]:
        status = _norm_str(chain.get("status", ""))
        if status == "active":
            pri = 0
        elif status == "offered":
            pri = 1
        else:
            pri = 2
        return (pri, _safe_int(chain.get("chain_id", 0)), _norm_str(chain.get("name", "")))

    summaries.sort(key=_rank)
    return summaries[:_MAX_QUEST_CHAINS]


def select_focus_quest_chain(hero: Any, chains: Iterable[Any] | None) -> dict[str, Any] | None:
    """Pick the quest chain the AI should focus on right now.

    Active chains assigned to this hero win first, then any other active chain,
    then an offered chain not currently on this hero's local decline cooldown.
    """
    summaries = summarize_quest_chains(chains)
    if not summaries:
        return None

    hero_id = _norm_str(_value(hero, "hero_id", _value(hero, "id", "")))
    decline_map = getattr(hero, "_quest_chain_decline_until_ms", None) or {}
    now = int(sim_now_ms())

    if hero_id:
        for chain in summaries:
            if _norm_str(chain.get("status", "")) != "active":
                continue
            if _norm_str(chain.get("assigned_hero_id", "")) == hero_id:
                return chain

    for chain in summaries:
        if _norm_str(chain.get("status", "")) == "active":
            return chain

    for chain in summaries:
        if _norm_str(chain.get("status", "")) != "offered":
            continue
        chain_id = _safe_int(chain.get("chain_id", 0))
        if now < _safe_int(decline_map.get(chain_id, decline_map.get(str(chain_id), 0)), 0):
            continue
        return chain

    return None


def quest_chain_status_allowed_actions(chain: dict[str, Any], *, survival_forced: bool) -> tuple[str, ...]:
    """Return the bounded verbs the model may use for a chain snapshot."""
    if survival_forced:
        return ("retreat_to_heal",)

    status = _norm_str(chain.get("status", ""))
    if status == "active":
        return ("continue_phase", "retreat_to_heal")
    if status == "offered":
        return ("accept_chain", "decline_chain")
    return ()


def quest_chain_action_meanings(chain: dict[str, Any], allowed_actions: Iterable[str]) -> dict[str, str]:
    """Return compact, structured action semantics for the prompt."""
    allowed = [str(action).strip().lower() for action in allowed_actions if str(action).strip()]
    out: dict[str, str] = {}
    phase_title = _norm_str(chain.get("current_phase_title", "")) or _norm_str(chain.get("current_phase_id", ""))
    target_name = _norm_str(chain.get("target_name", "")) or _norm_str(chain.get("target_id", ""))
    chain_name = _norm_str(chain.get("name", "")) or _norm_str(chain.get("chain_type", ""))

    for action in allowed:
        if action == "continue_phase":
            out[action] = (
                f"stay on the current phase for {chain_name}"
                + (f" ({phase_title})" if phase_title else "")
                + (f" toward {target_name}" if target_name else "")
            )
        elif action == "retreat_to_heal":
            out[action] = "break off to safety, heal, and resupply before resuming the chain"
        elif action == "accept_chain":
            out[action] = "start the offered chain"
        elif action == "decline_chain":
            out[action] = "turn down the offered chain"
    return out


def quest_chain_prompt_block(chain: dict[str, Any], allowed_actions: Iterable[str]) -> dict[str, Any]:
    """Build the focused quest-chain prompt block from a summarized chain."""
    block = dict(chain)
    meanings = quest_chain_action_meanings(chain, allowed_actions)
    if meanings:
        block["action_meanings"] = meanings
    return block
