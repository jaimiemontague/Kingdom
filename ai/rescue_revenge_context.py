"""Structured WK142 rescue/revenge AI context helpers."""

from __future__ import annotations

from typing import Any, Iterable

_MAX_CAPTURED_HEROES = 3
_MAX_RESCUE_OPPORTUNITIES = 3
_MAX_BOSS_KILL_MEMORIES = 3
_MAX_REVENGE_OPPORTUNITIES = 3


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


def _sort_key(entry: dict[str, Any], *, time_key: str, secondary_key: str) -> tuple[int, str]:
    return (-_safe_int(entry.get(time_key, 0)), _norm_str(entry.get(secondary_key, "")))


def summarize_captured_hero(capture: Any) -> dict[str, Any]:
    return {
        "hero_id": _norm_str(_value(capture, "hero_id", "")),
        "hero_name": _norm_str(_value(capture, "hero_name", "")),
        "captor_boss_id": _norm_str(_value(capture, "captor_boss_id", "")),
        "captor_boss_name": _norm_str(_value(capture, "captor_boss_name", "")),
        "captor_boss_type": _norm_str(_value(capture, "captor_boss_type", "")),
        "location_id": _norm_str(_value(capture, "location_id", "")),
        "location_name": _norm_str(_value(capture, "location_name", "")),
        "source_chain_id": _norm_str(_value(capture, "source_chain_id", "")),
        "source_chain_type": _norm_str(_value(capture, "source_chain_type", "")),
        "captured_at_ms": _safe_int(_value(capture, "captured_at_ms", 0)),
        "status": _norm_str(_value(capture, "status", "")),
    }


def summarize_captured_heroes(captured_heroes: Iterable[Any] | None) -> list[dict[str, Any]]:
    if not captured_heroes:
        return []
    summaries = [summarize_captured_hero(capture) for capture in captured_heroes if capture is not None]
    summaries.sort(key=lambda row: _sort_key(row, time_key="captured_at_ms", secondary_key="hero_id"))
    return summaries[:_MAX_CAPTURED_HEROES]


def summarize_rescue_opportunity(opportunity: Any) -> dict[str, Any]:
    return {
        "rescue_id": _norm_str(_value(opportunity, "rescue_id", "")),
        "captured_hero_id": _norm_str(_value(opportunity, "captured_hero_id", "")),
        "captured_hero_name": _norm_str(_value(opportunity, "captured_hero_name", "")),
        "captor_boss_id": _norm_str(_value(opportunity, "captor_boss_id", "")),
        "captor_boss_name": _norm_str(_value(opportunity, "captor_boss_name", "")),
        "captor_boss_type": _norm_str(_value(opportunity, "captor_boss_type", "")),
        "target_location_id": _norm_str(_value(opportunity, "target_location_id", "")),
        "target_location_name": _norm_str(_value(opportunity, "target_location_name", "")),
        "current_phase_id": _norm_str(_value(opportunity, "current_phase_id", "")),
        "current_phase_title": _norm_str(_value(opportunity, "current_phase_title", "")),
        "source_chain_id": _norm_str(_value(opportunity, "source_chain_id", "")),
        "source_chain_type": _norm_str(_value(opportunity, "source_chain_type", "")),
        "status": _norm_str(_value(opportunity, "status", "")),
        "offered_at_ms": _safe_int(_value(opportunity, "offered_at_ms", 0)),
    }


def summarize_rescue_opportunities(opportunities: Iterable[Any] | None) -> list[dict[str, Any]]:
    if not opportunities:
        return []
    summaries = [summarize_rescue_opportunity(opportunity) for opportunity in opportunities if opportunity is not None]
    summaries.sort(key=lambda row: _sort_key(row, time_key="offered_at_ms", secondary_key="rescue_id"))
    return summaries[:_MAX_RESCUE_OPPORTUNITIES]


def summarize_boss_kill_memory(memory: Any) -> dict[str, Any]:
    return {
        "boss_id": _norm_str(_value(memory, "boss_id", "")),
        "boss_name": _norm_str(_value(memory, "boss_name", "")),
        "boss_type": _norm_str(_value(memory, "boss_type", "")),
        "fallen_hero_id": _norm_str(_value(memory, "fallen_hero_id", "")),
        "fallen_hero_name": _norm_str(_value(memory, "fallen_hero_name", "")),
        "location_id": _norm_str(_value(memory, "location_id", "")),
        "location_name": _norm_str(_value(memory, "location_name", "")),
        "killed_at_ms": _safe_int(_value(memory, "killed_at_ms", 0)),
        "revenge_chain_id": _norm_str(_value(memory, "revenge_chain_id", "")),
        "status": _norm_str(_value(memory, "status", "")),
    }


def summarize_boss_kill_memories(memories: Iterable[Any] | None) -> list[dict[str, Any]]:
    if not memories:
        return []
    summaries = [summarize_boss_kill_memory(memory) for memory in memories if memory is not None]
    summaries.sort(key=lambda row: _sort_key(row, time_key="killed_at_ms", secondary_key="boss_id"))
    return summaries[:_MAX_BOSS_KILL_MEMORIES]


def summarize_revenge_opportunity(opportunity: Any) -> dict[str, Any]:
    return {
        "revenge_id": _norm_str(_value(opportunity, "revenge_id", "")),
        "boss_id": _norm_str(_value(opportunity, "boss_id", "")),
        "boss_name": _norm_str(_value(opportunity, "boss_name", "")),
        "boss_type": _norm_str(_value(opportunity, "boss_type", "")),
        "fallen_hero_id": _norm_str(_value(opportunity, "fallen_hero_id", "")),
        "fallen_hero_name": _norm_str(_value(opportunity, "fallen_hero_name", "")),
        "target_location_id": _norm_str(_value(opportunity, "target_location_id", "")),
        "target_location_name": _norm_str(_value(opportunity, "target_location_name", "")),
        "current_phase_id": _norm_str(_value(opportunity, "current_phase_id", "")),
        "current_phase_title": _norm_str(_value(opportunity, "current_phase_title", "")),
        "revenge_chain_id": _norm_str(_value(opportunity, "revenge_chain_id", "")),
        "status": _norm_str(_value(opportunity, "status", "")),
        "offered_at_ms": _safe_int(_value(opportunity, "offered_at_ms", 0)),
    }


def summarize_revenge_opportunities(opportunities: Iterable[Any] | None) -> list[dict[str, Any]]:
    if not opportunities:
        return []
    summaries = [summarize_revenge_opportunity(opportunity) for opportunity in opportunities if opportunity is not None]
    summaries.sort(key=lambda row: _sort_key(row, time_key="offered_at_ms", secondary_key="revenge_id"))
    return summaries[:_MAX_REVENGE_OPPORTUNITIES]


def summarize_story_facts(
    *,
    captured_heroes: Iterable[Any] | None = None,
    rescue_opportunities: Iterable[Any] | None = None,
    boss_kill_memories: Iterable[Any] | None = None,
    revenge_opportunities: Iterable[Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return the WK142 story facts in compact, prompt-friendly form."""
    facts: dict[str, list[dict[str, Any]]] = {}

    captured = summarize_captured_heroes(captured_heroes)
    if captured:
        facts["captured_heroes"] = captured

    rescue = summarize_rescue_opportunities(rescue_opportunities)
    if rescue:
        facts["rescue_opportunities"] = rescue

    memories = summarize_boss_kill_memories(boss_kill_memories)
    if memories:
        facts["boss_kill_memories"] = memories

    revenge = summarize_revenge_opportunities(revenge_opportunities)
    if revenge:
        facts["revenge_opportunities"] = revenge

    return facts
