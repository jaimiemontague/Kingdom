"""Shared quest-chain AI context helpers.

These helpers keep quest-chain prompt data bounded and deterministic while
staying on the AI side of the boundary. They never mutate sim state.
"""

from __future__ import annotations

from typing import Any, Iterable

from game.content.quest_chains import ASHWING_THE_RED_NAME, get_chain_def
from game.sim.timebase import now_ms as sim_now_ms

_MAX_CHAIN_HISTORY = 8
_MAX_PHASE_HISTORY = 4
_MAX_QUEST_CHAINS = 3
# Extra boss-facing fields that should survive the quest-chain re-summarize
# pass when they are present on a structured snapshot.
_BOSS_EXTRA_FIELDS = (
    "known_boss_id",
    "known_boss_name",
    "known_boss_phase",
    "known_boss_hp_pct",
    "known_boss_position",
    "known_boss_telegraph",
    "elite_target_id",
    "elite_target_name",
    "elite_target_status",
    "elite_target_position",
    "elite_target_base_type",
)


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


def _first_snapshot(items: Iterable[Any] | None) -> Any | None:
    if not items:
        return None
    for item in items:
        if item is None:
            continue
        status = _norm_str(_value(item, "status", "")).lower()
        if status in {"active", "revealed"}:
            return item
    for item in items:
        if item is not None:
            return item
    return None


def _snapshot_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _snapshot_position_value(value: Any) -> tuple[float, float] | None:
    return _target_position(value)


def attach_blackbanner_chain_facts(
    chain: Any,
    *,
    boss_encounters: Iterable[Any] | None = None,
    elite_enemies: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Attach Blackbanner-specific boss / elite facts to a quest-chain summary.

    The enrichment is only added for ``blackbanners_toll`` and only when the
    corresponding boss / elite snapshots exist. Keeping this here lets the
    prompt stack preserve the richer facts through the existing quest-chain
    summarization passes without changing the generic WK138 relic path.
    """
    summary = dict(chain)
    if _norm_str(summary.get("chain_type", "")) != "blackbanners_toll":
        return summary

    boss = _first_snapshot(boss_encounters)
    if boss is not None:
        summary["known_boss_id"] = _norm_str(_value(boss, "boss_id", ""))
        summary["known_boss_name"] = _norm_str(_value(boss, "name", ""))
        summary["known_boss_phase"] = _norm_str(
            _value(boss, "current_phase_title", _value(boss, "current_phase", ""))
        )
        summary["known_boss_hp_pct"] = _snapshot_float(_value(boss, "hp_pct", 0.0), 0.0)
        summary["known_boss_position"] = _snapshot_position_value(_value(boss, "position", None))

    elite = _first_snapshot(elite_enemies)
    if elite is not None:
        summary["elite_target_id"] = _norm_str(_value(elite, "elite_id", ""))
        summary["elite_target_name"] = _norm_str(_value(elite, "name", ""))
        summary["elite_target_status"] = _norm_str(_value(elite, "status", ""))
        summary["elite_target_position"] = _snapshot_position_value(_value(elite, "position", None))
        summary["elite_target_base_type"] = _norm_str(_value(elite, "base_type", ""))

    return summary


def attach_ashwing_chain_facts(
    chain: Any,
    *,
    boss_encounters: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Attach Ashwing-specific boss facts to a quest-chain summary.

    Ashwing uses the same structured chain snapshot path as the other quest
    chains. The boss snapshot carries the danger-facing facts the AI should see
    once the dragon is revealed: identity, current boss phase, health, and the
    latest telegraph. The hunt itself still comes from the quest phase target,
    so we only enrich when a matching dragon snapshot is present.
    """
    summary = dict(chain)
    if _norm_str(summary.get("chain_type", "")) != "ashwings_hoard":
        return summary

    selected = None
    fallback = None
    for boss in boss_encounters or ():
        if boss is None:
            continue
        status = _norm_str(_value(boss, "status", "")).lower()
        if status not in {"active", "revealed", "engaged"}:
            if fallback is None:
                fallback = boss
            continue
        boss_type = _norm_str(_value(boss, "boss_type", _value(boss, "base_enemy_type", ""))).lower()
        boss_name = _norm_str(_value(boss, "name", "")).lower()
        if boss_type == "dragon" or boss_name == ASHWING_THE_RED_NAME.lower():
            selected = boss
            break
        if fallback is None:
            fallback = boss
    boss = selected or fallback
    if boss is None:
        return summary

    summary["known_boss_id"] = _norm_str(_value(boss, "boss_id", ""))
    summary["known_boss_name"] = _norm_str(_value(boss, "name", ""))
    summary["known_boss_phase"] = _norm_str(
        _value(boss, "current_phase_title", _value(boss, "current_phase", ""))
    )
    summary["known_boss_hp_pct"] = _snapshot_float(_value(boss, "hp_pct", 0.0), 0.0)
    summary["known_boss_position"] = _snapshot_position_value(_value(boss, "position", None))
    summary["known_boss_telegraph"] = _norm_str(_value(boss, "latest_telegraph", ""))
    return summary


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
        **{
            key: (
                _target_position(_value(chain, key, None))
                if key.endswith("_position")
                else _snapshot_float(_value(chain, key, 0.0), 0.0)
                if key == "known_boss_hp_pct"
                else _norm_str(_value(chain, key, ""))
            )
            for key in _BOSS_EXTRA_FIELDS
            if _value(chain, key, None) not in (None, "", (), [])
        },
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


def quest_chain_status_allowed_actions(
    chain: dict[str, Any],
    *,
    survival_forced: bool,
    needs_supplies: bool = False,
) -> tuple[str, ...]:
    """Return the bounded verbs the model may use for a chain snapshot."""
    if survival_forced:
        return ("retreat_to_heal",)

    status = _norm_str(chain.get("status", ""))
    if status == "active":
        if needs_supplies:
            return ("continue_phase", "prepare_supplies", "retreat_to_heal")
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
    boss_name = _norm_str(chain.get("known_boss_name", ""))
    boss_phase = _norm_str(chain.get("known_boss_phase", ""))
    boss_telegraph = _norm_str(chain.get("known_boss_telegraph", ""))
    elite_name = _norm_str(chain.get("elite_target_name", ""))

    for action in allowed:
        if action == "continue_phase":
            out[action] = (
                f"stay on the current phase for {chain_name}"
                + (f" ({phase_title})" if phase_title else "")
                + (f" toward {target_name}" if target_name else "")
                + (f"; boss known: {boss_name}" if boss_name else "")
                + (f"; boss phase: {boss_phase}" if boss_phase else "")
                + (f"; telegraph: {boss_telegraph}" if boss_telegraph else "")
                + (f"; elite target: {elite_name}" if elite_name else "")
            )
        elif action == "prepare_supplies":
            out[action] = (
                "break off to resupply at a market or blacksmith before resuming the chain"
            )
            if boss_name:
                out[action] += f" against {boss_name}"
            if boss_phase:
                out[action] += f" while it is in {boss_phase}"
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
