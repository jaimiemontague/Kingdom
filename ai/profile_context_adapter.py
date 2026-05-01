"""
Profile + tactical context for autonomous LLM decision moments (WK50 Phase 2A).

Produces bounded JSON-ready dicts — no raw entity objects in output.
"""

from __future__ import annotations

from typing import Any

from ai.context_builder import ContextBuilder
from ai.decision_moments import DecisionMoment, DecisionMomentType
from game.sim.hero_profile import HeroProfileSnapshot, build_hero_profile_snapshot


_MAX_PLACES = 8
_MAX_MEMORY = 10
_MAX_ENEMIES = 5
_MAX_ALLIES = 5
_MAX_BOUNTIES = 5


def _compact_profile_dict(snapshot: HeroProfileSnapshot) -> dict[str, Any]:
    d = snapshot.to_dict()
    # Drop last_decision blob from prompt to save tokens; situation uses tactical context.
    d.pop("last_decision", None)
    # Bounded copies live under known_places / recent_memory at top level.
    d["known_places_count"] = len(snapshot.known_places)
    d["recent_memory_count"] = len(snapshot.recent_memory)
    d.pop("known_places", None)
    d.pop("recent_memory", None)
    return d


def _sort_places_for_moment(
    places: tuple[Any, ...], moment: DecisionMoment
) -> tuple[Any, ...]:
    def rank(p: Any) -> tuple[int, int, str]:
        slug = str(getattr(p, "place_type", "") or "").lower()
        pri = 2
        if moment.moment_type == DecisionMomentType.LOW_HEALTH_COMBAT:
            if slug in {"castle", "inn"}:
                pri = 0
            elif slug in {"marketplace", "blacksmith"}:
                pri = 1
        elif moment.moment_type == DecisionMomentType.POST_COMBAT_INJURED:
            if slug in {"castle", "inn", "marketplace"}:
                pri = 0
        elif moment.moment_type == DecisionMomentType.SHOPPING_OPPORTUNITY:
            if slug in {"marketplace", "blacksmith"}:
                pri = 0
        elif moment.moment_type == DecisionMomentType.RESTED_AND_READY:
            if slug == "castle":
                pri = 0
        lm = int(getattr(p, "last_seen_ms", 0) or 0)
        pid = str(getattr(p, "place_id", ""))
        return (pri, -lm, pid)

    return tuple(sorted(places, key=rank))[:_MAX_PLACES]


def _filter_known_places(snapshot: HeroProfileSnapshot, moment: DecisionMoment) -> list[dict[str, Any]]:
    ordered = _sort_places_for_moment(snapshot.known_places, moment)
    out: list[dict[str, Any]] = []
    for p in ordered:
        out.append(
            {
                "place_id": str(getattr(p, "place_id", "")),
                "place_type": str(getattr(p, "place_type", "")),
                "display_name": str(getattr(p, "display_name", "")),
                "tile": tuple(getattr(p, "tile", (0, 0))),
                "last_seen_ms": int(getattr(p, "last_seen_ms", 0) or 0),
            }
        )
    return out


def _filter_recent_memory(snapshot: HeroProfileSnapshot, moment: DecisionMoment) -> list[dict[str, Any]]:
    entries = list(snapshot.recent_memory)
    if moment.moment_type == DecisionMomentType.POST_COMBAT_INJURED:
        entries.sort(
            key=lambda e: (-int(getattr(e, "importance", 1) or 1), -int(getattr(e, "sim_time_ms", 0) or 0))
        )
    else:
        entries.sort(key=lambda e: (-int(getattr(e, "sim_time_ms", 0) or 0), int(getattr(e, "entry_id", 0) or 0)))
    out: list[dict[str, Any]] = []
    for e in entries[:_MAX_MEMORY]:
        out.append(
            {
                "entry_id": int(getattr(e, "entry_id", 0) or 0),
                "event_type": str(getattr(e, "event_type", "")),
                "sim_time_ms": int(getattr(e, "sim_time_ms", 0) or 0),
                "summary": str(getattr(e, "summary", ""))[:200],
                "importance": int(getattr(e, "importance", 1) or 1),
            }
        )
    return out


def _compact_situation(hero: Any, game_state: dict) -> dict[str, Any]:
    full = ContextBuilder.build_hero_context(hero, game_state)
    enemies = list(full.get("nearby_enemies") or [])[:_MAX_ENEMIES]
    allies = list(full.get("nearby_allies") or [])[:_MAX_ALLIES]
    bounties = list(full.get("bounty_options") or [])[:_MAX_BOUNTIES]
    return {
        "current_state": full.get("current_state"),
        "current_location_label": full.get("current_location"),
        "situation": full.get("situation"),
        "nearby_enemies": enemies,
        "nearby_allies": allies,
        "bounty_options": bounties,
        "shop_items": full.get("shop_items") if full.get("shop_items") else [],
        "distances": full.get("distances", {}),
        "hero_stat_block": full.get("hero_stat_block", ""),
    }


def build_llm_context_for_moment(
    hero: Any,
    game_state: dict,
    moment: DecisionMoment,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    snapshot = build_hero_profile_snapshot(hero, None, now_ms=now_ms)
    profile_core = _compact_profile_dict(snapshot)
    return {
        "moment": moment.to_prompt_dict(),
        "hero_profile": profile_core,
        "current_situation": _compact_situation(hero, game_state),
        "known_places": _filter_known_places(snapshot, moment),
        "recent_memory": _filter_recent_memory(snapshot, moment),
        "allowed_actions": list(moment.allowed_actions),
    }
