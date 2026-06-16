"""Deterministic hero daily-life ambient motive scoring.

This module stays AI-owned and keeps per-hero ambient memory keyed by
``hero.hero_id``. It chooses among non-urgent daily-life motives when the
existing idle priority checks have already fallen through.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math
import zlib

from config import TILE_SIZE
from game.entities.buildings.types import BuildingType
from game.entities.hero import HeroState
from game.sim.timebase import now_ms as sim_now_ms
from game.systems.navigation import best_adjacent_tile

from ai.behaviors.movement import route_to_building
from ai.behaviors.poi_awareness import score_poi_for_personality
from ai.behaviors.view_compat import as_ai_view


_AMBIENT_MEMORY: dict[str, dict[str, Any]] = {}

_AMBIENT_TRACE_LIMIT = 20
_AMBIENT_SWITCH_THRESHOLD = 6.0
_AMBIENT_MIN_DWELL_MS = 8_000
_CRITICAL_HEALTH_BYPASS_PCT = 0.25

_CLUSTER_TILE_SPAN = 4
_RECENT_TARGET_COOLDOWN_MS = 45_000

_CLASS_BIAS: dict[str, dict[str, float]] = {
    "warrior": {
        "monster_patrol": 8.0,
        "rescue_hero": 2.0,
        "revenge_hero": 6.0,
        "road_watch": 5.0,
        "safe_rest": 4.0,
        "home_or_guild_time": 3.0,
        "kingdom_roam": 2.0,
        "social_linger": 1.0,
        "opportunity_check": 1.0,
        "poi_scout": 0.5,
        "wilderness_explore": 0.5,
    },
    "ranger": {
        "wilderness_explore": 10.0,
        "poi_scout": 7.0,
        "rescue_hero": 7.0,
        "revenge_hero": 2.0,
        "road_watch": 4.0,
        "kingdom_roam": 4.0,
        "monster_patrol": 3.0,
        "opportunity_check": 2.0,
        "safe_rest": 1.0,
        "social_linger": 0.0,
        "home_or_guild_time": 1.0,
    },
    "rogue": {
        "poi_scout": 9.0,
        "opportunity_check": 8.0,
        "rescue_hero": 4.0,
        "revenge_hero": 1.0,
        "kingdom_roam": 5.0,
        "social_linger": 3.0,
        "road_watch": 2.0,
        "wilderness_explore": 1.0,
        "monster_patrol": 1.0,
        "safe_rest": 0.5,
        "home_or_guild_time": 0.5,
    },
    "cleric": {
        "safe_rest": 9.0,
        "home_or_guild_time": 7.0,
        "social_linger": 6.0,
        "rescue_hero": 7.0,
        "revenge_hero": -4.0,
        "kingdom_roam": 2.0,
        "road_watch": 2.0,
        "opportunity_check": 1.0,
        "monster_patrol": 0.5,
        "poi_scout": 0.5,
        "wilderness_explore": 0.5,
    },
    "wizard": {
        "poi_scout": 6.0,
        "opportunity_check": 5.0,
        "rescue_hero": 2.0,
        "revenge_hero": 5.0,
        "wilderness_explore": 4.0,
        "kingdom_roam": 3.0,
        "social_linger": 2.0,
        "home_or_guild_time": 2.0,
        "safe_rest": 2.0,
        "road_watch": 1.0,
        "monster_patrol": 1.0,
    },
}

_PERSONALITY_BIAS: dict[str, dict[str, float]] = {
    "brave and aggressive": {
        "monster_patrol": 6.0,
        "road_watch": 4.0,
        "wilderness_explore": 2.0,
        "rescue_hero": 1.0,
        "revenge_hero": 5.0,
        "safe_rest": -4.0,
    },
    "cautious and strategic": {
        "safe_rest": 6.0,
        "home_or_guild_time": 4.0,
        "social_linger": 3.0,
        "rescue_hero": 4.0,
        "revenge_hero": -8.0,
        "monster_patrol": -5.0,
        "wilderness_explore": -2.0,
    },
    "greedy but cowardly": {
        "opportunity_check": 6.0,
        "poi_scout": 5.0,
        "kingdom_roam": 3.0,
        "social_linger": 1.0,
        "rescue_hero": 1.0,
        "revenge_hero": -6.0,
        "monster_patrol": -2.0,
    },
    "balanced and reliable": {
        "kingdom_roam": 4.0,
        "social_linger": 3.0,
        "road_watch": 2.0,
        "opportunity_check": 1.0,
        "rescue_hero": 3.0,
        "revenge_hero": 2.0,
    },
}

_MOTIVE_BASE_SCORE: dict[str, float] = {
    "kingdom_roam": 7.0,
    "wilderness_explore": 9.0,
    "poi_scout": 8.0,
    "monster_patrol": 8.5,
    "rescue_hero": 11.5,
    "revenge_hero": 12.5,
    "safe_rest": 6.0,
    "social_linger": 5.5,
    "opportunity_check": 6.5,
    "home_or_guild_time": 5.5,
    "road_watch": 5.5,
}

_MOTIVE_COMMIT_MS: dict[str, int] = {
    "kingdom_roam": 18_000,
    "wilderness_explore": 28_000,
    "poi_scout": 20_000,
    "monster_patrol": 20_000,
    "rescue_hero": 24_000,
    "revenge_hero": 26_000,
    "safe_rest": 24_000,
    "social_linger": 16_000,
    "opportunity_check": 16_000,
    "home_or_guild_time": 20_000,
    "road_watch": 18_000,
}

_MOTIVE_TARGET_COOLDOWN_MS: dict[str, int] = {
    "kingdom_roam": 60_000,
    "wilderness_explore": 90_000,
    "poi_scout": 75_000,
    "monster_patrol": 60_000,
    "rescue_hero": 90_000,
    "revenge_hero": 90_000,
    "safe_rest": 90_000,
    "social_linger": 45_000,
    "opportunity_check": 60_000,
    "home_or_guild_time": 75_000,
    "road_watch": 45_000,
}


def _set_ambient_intent(ai: Any, hero: Any, intent: str) -> None:
    """Set hero intent through BasicAI when present, else fall back safely."""
    setter = getattr(ai, "set_intent", None)
    if callable(setter):
        try:
            setter(hero, intent)
            return
        except Exception:
            pass
    setattr(hero, "intent", str(intent or "idle"))


def _record_ambient_decision(
    ai: Any,
    hero: Any,
    *,
    action: str,
    reason: str,
    intent: str,
    inputs_summary: dict[str, Any],
    now_ms: int,
) -> None:
    """Record a decision through BasicAI when available, else the hero contract."""
    recorder = getattr(ai, "record_decision", None)
    if callable(recorder):
        try:
            recorder(
                hero,
                action=action,
                reason=reason,
                intent=intent,
                inputs_summary=inputs_summary,
                source="heuristic",
                now_ms=now_ms,
            )
            return
        except Exception:
            pass

    hero_recorder = getattr(hero, "record_decision", None)
    if callable(hero_recorder):
        try:
            hero_recorder(
                action=action,
                reason=reason,
                now_ms=now_ms,
                context={
                    "intent": intent,
                    "source": "heuristic",
                    "inputs_summary": dict(inputs_summary),
                },
            )
        except Exception:
            pass


@dataclass(frozen=True, slots=True)
class AmbientCandidate:
    motive: str
    target_key: str
    target_xy: tuple[float, float]
    primitive: str
    target_ref: Any | None = None
    base_score: float = 0.0
    commit_ms: int = 0
    cooldown_ms: int = 0
    cluster_key: str = ""
    detail: str = ""


def reset_ambient_memory(hero_id: str | None = None) -> None:
    """Clear ambient memory for one hero or the whole module (test helper)."""
    if hero_id is None:
        _AMBIENT_MEMORY.clear()
        return
    _AMBIENT_MEMORY.pop(str(hero_id), None)


def get_ambient_memory(hero: Any) -> dict[str, Any]:
    """Return the mutable memory bucket for ``hero``."""
    key = _hero_key(hero)
    mem = _AMBIENT_MEMORY.get(key)
    if mem is None:
        mem = {
            "active_motive": "",
            "active_target_key": "",
            "active_target_xy": None,
            "active_primitive": "",
            "commit_until_ms": 0,
            "active_significance": 0.0,
            "last_switch_ms": 0,
            "switch_count": 0,
            "behavior_trace": [],
            "target_cooldowns": {},
            "motive_cooldowns": {},
            "motive_counts": {},
            "last_cluster_key": "",
        }
        _AMBIENT_MEMORY[key] = mem
    return mem


def get_ambient_snapshot(hero: Any) -> dict[str, Any]:
    """Test/UI-friendly snapshot of the current ambient memory."""
    mem = get_ambient_memory(hero)
    return {
        "hero_id": _hero_key(hero),
        "active_motive": str(mem.get("active_motive", "") or ""),
        "active_target_key": str(mem.get("active_target_key", "") or ""),
        "active_target_xy": mem.get("active_target_xy"),
        "active_primitive": str(mem.get("active_primitive", "") or ""),
        "commit_until_ms": int(mem.get("commit_until_ms", 0) or 0),
        "active_significance": float(mem.get("active_significance", 0.0) or 0.0),
        "last_switch_ms": int(mem.get("last_switch_ms", 0) or 0),
        "switch_count": int(mem.get("switch_count", 0) or 0),
        "behavior_trace": [dict(entry) for entry in list(mem.get("behavior_trace", []) or [])],
        "target_cooldowns": dict(mem.get("target_cooldowns", {}) or {}),
        "motive_cooldowns": dict(mem.get("motive_cooldowns", {}) or {}),
        "motive_counts": dict(mem.get("motive_counts", {}) or {}),
        "last_cluster_key": str(mem.get("last_cluster_key", "") or ""),
    }


def build_daily_life_candidates(ai: Any, hero: Any, view: Any, *, now_ms: int | None = None) -> list[AmbientCandidate]:
    """Enumerate candidate ambient daily-life choices for ``hero``."""
    view = as_ai_view(view)
    if getattr(hero, "is_captured", False) or getattr(hero, "state", None) == HeroState.CAPTURED:
        return []
    now_ms = int(sim_now_ms() if now_ms is None else now_ms)
    buildings = list(getattr(view, "buildings", ()) or ())
    heroes = list(getattr(view, "heroes", ()) or ())
    pois = list(getattr(view, "pois", ()) or ())
    enemies = [e for e in (getattr(view, "enemies", ()) or ()) if getattr(e, "is_alive", False)]
    boss_encounters = list(getattr(view, "boss_encounters", ()) or ())
    world = getattr(view, "world", None)
    castle = getattr(view, "castle", None)
    home = getattr(hero, "home_building", None)

    candidates: list[AmbientCandidate] = []

    roam_anchor = _pick_roam_anchor(hero, castle, buildings)
    if roam_anchor is not None:
        candidates.append(
            _candidate_for_building(
                hero,
                motive="kingdom_roam",
                primitive="patrol",
                building=roam_anchor,
                now_ms=now_ms,
                detail="kingdom landmark",
            )
        )

    frontier = _pick_frontier(hero, world)
    if frontier is not None:
        gx, gy = frontier
        target_xy = (gx * TILE_SIZE + TILE_SIZE / 2, gy * TILE_SIZE + TILE_SIZE / 2)
        candidates.append(
            AmbientCandidate(
                motive="wilderness_explore",
                target_key=f"frontier:{gx}:{gy}",
                target_xy=target_xy,
                primitive="explore_frontier",
                base_score=14.0 + min(16.0, _distance_tiles(hero, *target_xy)),
                commit_ms=_commit_ms(hero, "wilderness_explore", f"frontier:{gx}:{gy}"),
                cooldown_ms=_MOTIVE_TARGET_COOLDOWN_MS["wilderness_explore"],
                cluster_key=_cluster_key(*target_xy),
                detail="black-fog frontier",
            )
        )

    poi = _pick_poi(hero, pois)
    if poi is not None:
        poi_def = getattr(poi, "poi_def", None)
        pcx, pcy = _poi_center_world(poi)
        poi_score = score_poi_for_personality(hero, poi, dist_tiles=_distance_tiles(hero, pcx, pcy))
        candidates.append(
            AmbientCandidate(
                motive="poi_scout",
                target_key=_entity_key("poi", poi),
                target_xy=(pcx, pcy),
                primitive="visit_poi",
                target_ref=poi,
                base_score=10.0 + float(poi_score) * 18.0,
                commit_ms=_commit_ms(hero, "poi_scout", _entity_key("poi", poi)),
                cooldown_ms=_MOTIVE_TARGET_COOLDOWN_MS["poi_scout"],
                cluster_key=_cluster_key(pcx, pcy),
                detail=str(getattr(poi_def, "display_name", "poi")),
            )
        )

    monster = _pick_monster_patrol_target(hero, enemies, buildings, boss_encounters)
    if monster is not None:
        mx, my = _target_center(monster)
        d_tiles = _distance_tiles(hero, mx, my)
        base = 12.0 + max(0.0, 16.0 - abs(d_tiles - 8.0))
        candidates.append(
            AmbientCandidate(
                motive="monster_patrol",
                target_key=_entity_key("threat", monster),
                target_xy=(mx, my),
                primitive="move_enemy",
                target_ref=monster,
                base_score=base,
                commit_ms=_commit_ms(hero, "monster_patrol", _entity_key("threat", monster)),
                cooldown_ms=_MOTIVE_TARGET_COOLDOWN_MS["monster_patrol"],
                cluster_key=_cluster_key(mx, my),
                detail=str(getattr(monster, "name", getattr(monster, "building_type", "threat"))),
            )
        )

    rescue_opportunities = list(getattr(view, "rescue_opportunities", ()) or ())
    for rescue in rescue_opportunities:
        rescue_dict = rescue if isinstance(rescue, dict) else getattr(rescue, "to_dict", lambda: None)()
        if not isinstance(rescue_dict, dict):
            continue
        target_ref, target_xy, rescue_key, rescue_detail = _resolve_rescue_target(hero, rescue_dict, buildings, pois)
        if target_ref is None or target_xy is None:
            continue
        rx, ry = target_xy
        d_tiles = _distance_tiles(hero, rx, ry)
        base = 11.0 + max(0.0, 14.0 - abs(d_tiles - 10.0))
        candidates.append(
            AmbientCandidate(
                motive="rescue_hero",
                target_key=rescue_key or _entity_key("rescue", target_ref),
                target_xy=(rx, ry),
                primitive="visit_poi",
                target_ref=target_ref,
                base_score=base,
                commit_ms=_commit_ms(hero, "rescue_hero", rescue_key or _entity_key("rescue", target_ref)),
                cooldown_ms=_MOTIVE_TARGET_COOLDOWN_MS["rescue_hero"],
                cluster_key=_cluster_key(rx, ry),
                detail=rescue_detail,
            )
        )

    revenge_opportunities = list(getattr(view, "revenge_opportunities", ()) or ())
    for revenge in revenge_opportunities:
        revenge_dict = revenge if isinstance(revenge, dict) else getattr(revenge, "to_dict", lambda: None)()
        if not isinstance(revenge_dict, dict):
            continue
        target_ref, target_xy, revenge_key, revenge_detail = _resolve_revenge_target(
            hero,
            revenge_dict,
            boss_encounters,
            enemies,
        )
        if target_ref is None or target_xy is None:
            continue
        rx, ry = target_xy
        d_tiles = _distance_tiles(hero, rx, ry)
        base = 24.0 + max(0.0, 18.0 - abs(d_tiles - 12.0))
        if getattr(target_ref, "boss_id", None) or getattr(target_ref, "boss_name", None):
            base += 4.0
        if getattr(hero, "hero_class", "") == "warrior":
            base += 2.0
        candidates.append(
            AmbientCandidate(
                motive="revenge_hero",
                target_key=revenge_key or _entity_key("revenge", target_ref),
                target_xy=(rx, ry),
                primitive="move_enemy",
                target_ref=target_ref,
                base_score=base,
                commit_ms=_commit_ms(hero, "revenge_hero", revenge_key or _entity_key("revenge", target_ref)),
                cooldown_ms=_MOTIVE_TARGET_COOLDOWN_MS["revenge_hero"],
                cluster_key=_cluster_key(rx, ry),
                detail=revenge_detail,
            )
        )

    rest_target, rest_primitive = _pick_safe_rest_target(hero, castle, home, buildings)
    if rest_target is not None:
        rx, ry = _target_center(rest_target)
        d_tiles = _distance_tiles(hero, rx, ry)
        hp_pct = float(getattr(hero, "health_percent", 1.0) or 1.0)
        base = 12.0 + max(0.0, 18.0 - d_tiles)
        if hp_pct < 0.50:
            base += 14.0
        elif hp_pct < 0.80:
            base += 5.0
        candidates.append(
            AmbientCandidate(
                motive="safe_rest",
                target_key=_entity_key("rest", rest_target),
                target_xy=(rx, ry),
                primitive=rest_primitive,
                target_ref=rest_target,
                base_score=base,
                commit_ms=_commit_ms(hero, "safe_rest", _entity_key("rest", rest_target)),
                cooldown_ms=_MOTIVE_TARGET_COOLDOWN_MS["safe_rest"],
                cluster_key=_cluster_key(rx, ry),
                detail=str(getattr(rest_target, "building_type", "rest")),
            )
        )

    social_target = _pick_social_target(hero, buildings)
    if social_target is not None:
        sx, sy = _target_center(social_target)
        d_tiles = _distance_tiles(hero, sx, sy)
        base = 8.0 + max(0.0, 12.0 - d_tiles)
        if _building_slug(social_target) == "inn" and float(getattr(hero, "gold", 0) or 0) >= 10.0:
            base += 3.0
        candidates.append(
            AmbientCandidate(
                motive="social_linger",
                target_key=_entity_key("social", social_target),
                target_xy=(sx, sy),
                primitive="get_drink" if _building_slug(social_target) == "inn" else "patrol",
                target_ref=social_target,
                base_score=base,
                commit_ms=_commit_ms(hero, "social_linger", _entity_key("social", social_target)),
                cooldown_ms=_MOTIVE_TARGET_COOLDOWN_MS["social_linger"],
                cluster_key=_cluster_key(sx, sy),
                detail=str(getattr(social_target, "building_type", "social")),
            )
        )

    opportunity_target = _pick_opportunity_target(hero, buildings, view)
    if opportunity_target is not None:
        ox, oy = _target_center(opportunity_target)
        d_tiles = _distance_tiles(hero, ox, oy)
        base = 9.0 + max(0.0, 14.0 - d_tiles)
        if str(getattr(hero, "hero_class", "") or "") == "rogue":
            base += 4.0
        if float(getattr(hero, "gold", 0) or 0) >= 50.0:
            base += 2.0
        candidates.append(
            AmbientCandidate(
                motive="opportunity_check",
                target_key=_entity_key("opp", opportunity_target),
                target_xy=(ox, oy),
                primitive="patrol",
                target_ref=opportunity_target,
                base_score=base,
                commit_ms=_commit_ms(hero, "opportunity_check", _entity_key("opp", opportunity_target)),
                cooldown_ms=_MOTIVE_TARGET_COOLDOWN_MS["opportunity_check"],
                cluster_key=_cluster_key(ox, oy),
                detail=str(getattr(opportunity_target, "building_type", "opportunity")),
            )
        )

    home_target = _pick_home_or_guild_target(hero, buildings, home)
    if home_target is not None:
        hx, hy = _target_center(home_target)
        d_tiles = _distance_tiles(hero, hx, hy)
        base = 8.0 + max(0.0, 16.0 - d_tiles)
        if getattr(hero, "damage_since_left_home", 0) >= 10:
            base += 4.0
        candidates.append(
            AmbientCandidate(
                motive="home_or_guild_time",
                target_key=_entity_key("home", home_target),
                target_xy=(hx, hy),
                primitive="going_home" if home_target is home or _building_slug(home_target) == "inn" else "patrol",
                target_ref=home_target,
                base_score=base,
                commit_ms=_commit_ms(hero, "home_or_guild_time", _entity_key("home", home_target)),
                cooldown_ms=_MOTIVE_TARGET_COOLDOWN_MS["home_or_guild_time"],
                cluster_key=_cluster_key(hx, hy),
                detail=str(getattr(home_target, "building_type", "home")),
            )
        )

    road_target = _pick_road_watch_point(hero, castle, buildings)
    if road_target is not None:
        rx, ry = road_target
        d_tiles = _distance_tiles(hero, rx, ry)
        base = 7.0 + max(0.0, 12.0 - abs(d_tiles - 6.0))
        candidates.append(
            AmbientCandidate(
                motive="road_watch",
                target_key=f"road:{int(rx)}:{int(ry)}",
                target_xy=(rx, ry),
                primitive="patrol",
                base_score=base,
                commit_ms=_commit_ms(hero, "road_watch", f"road:{int(rx)}:{int(ry)}"),
                cooldown_ms=_MOTIVE_TARGET_COOLDOWN_MS["road_watch"],
                cluster_key=_cluster_key(rx, ry),
                detail="road waypoint",
            )
        )

    return candidates


def score_daily_life_candidate(
    ai: Any,
    hero: Any,
    candidate: AmbientCandidate,
    view: Any,
    *,
    now_ms: int | None = None,
    ignore_memory_penalties: bool = False,
) -> float:
    """Score one ambient candidate. Higher is better."""
    view = as_ai_view(view)
    now_ms = int(sim_now_ms() if now_ms is None else now_ms)
    mem = get_ambient_memory(hero)
    score = float(candidate.base_score)

    score += _CLASS_BIAS.get(str(getattr(hero, "hero_class", "") or ""), {}).get(candidate.motive, 0.0)
    score += _PERSONALITY_BIAS.get(str(getattr(hero, "personality", "") or ""), {}).get(candidate.motive, 0.0)

    hp_pct = float(getattr(hero, "health_percent", 1.0) or 1.0)
    if candidate.motive == "safe_rest":
        if hp_pct < 0.50:
            score += 20.0
        elif hp_pct < 0.80:
            score += 8.0
        else:
            score -= 2.0
    elif candidate.motive in {"monster_patrol", "wilderness_explore"} and hp_pct < 0.50:
        score -= 8.0
    elif candidate.motive == "rescue_hero":
        if hp_pct < 0.45:
            score -= 6.0
        elif hp_pct < 0.75:
            score += 4.0
        else:
            score += 10.0
    elif candidate.motive == "revenge_hero":
        if hp_pct < 0.60:
            score -= 10.0
        elif hp_pct < 0.80:
            score += 2.0
        else:
            score += 8.0
    elif candidate.motive in {"opportunity_check", "social_linger"} and hp_pct < 0.40:
        score -= 4.0

    if float(getattr(hero, "gold", 0) or 0) >= 50.0 and candidate.motive == "opportunity_check":
        score += 3.0
    if float(getattr(hero, "gold", 0) or 0) >= 10.0 and candidate.motive == "social_linger":
        score += 2.0

    # Distance shapers keep the motives visually distinct.
    dist_tiles = _distance_tiles(hero, *candidate.target_xy)
    if candidate.motive == "kingdom_roam":
        score += min(12.0, dist_tiles)
    elif candidate.motive == "wilderness_explore":
        score += min(18.0, dist_tiles)
    elif candidate.motive == "poi_scout":
        score += max(0.0, 12.0 - abs(dist_tiles - 8.0))
    elif candidate.motive == "monster_patrol":
        score += max(0.0, 14.0 - abs(dist_tiles - 10.0))
        if getattr(candidate.target_ref, "is_boss", False):
            score += 6.0
    elif candidate.motive == "safe_rest":
        score += max(0.0, 16.0 - dist_tiles)
    elif candidate.motive == "social_linger":
        score += max(0.0, 12.0 - dist_tiles)
    elif candidate.motive == "opportunity_check":
        score += max(0.0, 13.0 - dist_tiles)
    elif candidate.motive == "rescue_hero":
        score += max(0.0, 14.0 - abs(dist_tiles - 10.0))
    elif candidate.motive == "revenge_hero":
        score += max(0.0, 16.0 - abs(dist_tiles - 12.0))
    elif candidate.motive == "home_or_guild_time":
        score += max(0.0, 14.0 - dist_tiles)
    elif candidate.motive == "road_watch":
        score += max(0.0, 10.0 - abs(dist_tiles - 6.0))

    if not ignore_memory_penalties:
        recent_targets = dict(mem.get("target_cooldowns", {}) or {})
        recent_until = int(recent_targets.get(candidate.target_key, 0) or 0)
        if now_ms < recent_until:
            score -= 100.0

        motive_cooldowns = dict(mem.get("motive_cooldowns", {}) or {})
        motive_until = int(motive_cooldowns.get(candidate.motive, 0) or 0)
        if now_ms < motive_until:
            score -= 8.0

    score -= _crowding_penalty(candidate, hero, view)
    score += _stable_tiebreak(hero, candidate)
    return score


def _find_active_ambient_candidate(candidates: list[AmbientCandidate], mem: dict[str, Any]) -> AmbientCandidate | None:
    active_motive = str(mem.get("active_motive", "") or "")
    active_target_key = str(mem.get("active_target_key", "") or "")
    if not active_motive or not active_target_key:
        return None
    for candidate in candidates:
        if candidate.motive == active_motive and candidate.target_key == active_target_key:
            return candidate
    return None


def _pick_best_ambient_candidate(
    ai: Any,
    hero: Any,
    view: Any,
    candidates: list[AmbientCandidate],
    *,
    now_ms: int,
    exclude: AmbientCandidate | None = None,
    motive: str | None = None,
    ignore_memory_penalties: bool = False,
) -> tuple[AmbientCandidate | None, float]:
    best: AmbientCandidate | None = None
    best_score = -1e9
    for candidate in candidates:
        if exclude is not None and candidate.motive == exclude.motive and candidate.target_key == exclude.target_key:
            continue
        if motive is not None and candidate.motive != motive:
            continue
        score = score_daily_life_candidate(
            ai,
            hero,
            candidate,
            view,
            now_ms=now_ms,
            ignore_memory_penalties=ignore_memory_penalties,
        )
        if score > best_score:
            best = candidate
            best_score = score
        elif best is not None and abs(score - best_score) < 1e-9 and candidate.target_key < best.target_key:
            best = candidate
            best_score = score
    return best, best_score


def _append_behavior_trace(
    mem: dict[str, Any],
    *,
    now_ms: int,
    from_motive: str,
    to_motive: str,
    reason: str,
    significance_delta: float,
    from_target_key: str = "",
    to_target_key: str = "",
) -> None:
    trace = list(mem.get("behavior_trace", []) or [])
    trace.append(
        {
            "t": int(now_ms),
            "from": str(from_motive or ""),
            "to": str(to_motive or ""),
            "reason": str(reason or ""),
            "significance_delta": round(float(significance_delta), 3),
            "from_target_key": str(from_target_key or ""),
            "to_target_key": str(to_target_key or ""),
        }
    )
    if len(trace) > _AMBIENT_TRACE_LIMIT:
        trace = trace[-_AMBIENT_TRACE_LIMIT:]
    mem["behavior_trace"] = trace


def _finalize_ambient_selection(
    hero: Any,
    candidate: AmbientCandidate,
    *,
    now_ms: int,
    significance: float,
    previous_motive: str,
    previous_target_key: str,
    reason: str,
    significance_delta: float,
) -> None:
    mem = get_ambient_memory(hero)
    _write_ambient_memory(hero, candidate, now_ms=now_ms)
    if previous_motive or previous_target_key:
        if previous_motive != candidate.motive or previous_target_key != candidate.target_key:
            mem["switch_count"] = int(mem.get("switch_count", 0) or 0) + 1
    mem["last_switch_ms"] = int(now_ms)
    mem["active_significance"] = round(float(significance), 3)
    _append_behavior_trace(
        mem,
        now_ms=now_ms,
        from_motive=previous_motive,
        to_motive=candidate.motive,
        reason=reason,
        significance_delta=significance_delta,
        from_target_key=previous_target_key,
        to_target_key=candidate.target_key,
    )


def _continue_ambient_behavior(
    ai: Any,
    hero: Any,
    view: Any,
    candidate: AmbientCandidate,
    *,
    now_ms: int,
    current_significance: float,
    significance_delta: float,
    reason: str,
) -> bool:
    mem = get_ambient_memory(hero)
    if not _reapply_ambient_target(ai, hero, view, mem, now_ms=now_ms):
        return False
    mem["active_significance"] = round(float(current_significance), 3)
    _append_behavior_trace(
        mem,
        now_ms=now_ms,
        from_motive=candidate.motive,
        to_motive=candidate.motive,
        reason=reason,
        significance_delta=significance_delta,
        from_target_key=candidate.target_key,
        to_target_key=candidate.target_key,
    )
    _record_ambient_decision(
        ai,
        hero,
        action=candidate.motive,
        reason=f"daily life hold: {candidate.motive} -> {candidate.detail or candidate.primitive} ({reason})",
        intent=getattr(hero, "intent", "idle") or "idle",
        inputs_summary={
            "motive": candidate.motive,
            "target_key": candidate.target_key,
            "target_xy": tuple(round(float(v), 3) for v in candidate.target_xy),
            "current_significance": round(float(current_significance), 3),
            "significance_delta": round(float(significance_delta), 3),
            "last_switch_ms": int(mem.get("last_switch_ms", 0) or 0),
            "switch_count": int(mem.get("switch_count", 0) or 0),
        },
        now_ms=now_ms,
    )
    return True


def try_daily_life(ai: Any, hero: Any, view: Any) -> bool:
    """Choose or continue a deterministic ambient daily-life activity."""
    view = as_ai_view(view)
    if getattr(hero, "is_captured", False) or getattr(hero, "state", None) == HeroState.CAPTURED:
        return False
    now_ms = int(sim_now_ms())

    # Digest-safe activation gate: keep WK67's first few sim-seconds byte-stable
    # while the new ambient layer warms up later in play.
    if now_ms < 6_000:
        return False

    # Never step on live bounty commitments.
    if getattr(hero, "target", None) and isinstance(getattr(hero, "target", None), dict):
        if getattr(hero.target, "get", lambda *_: None)("type") == "bounty":
            from ai.behaviors import bounty_pursuit

            if bounty_pursuit.bounty_commitment_active(hero, view, now_ms=now_ms):
                return False

    mem = get_ambient_memory(hero)
    candidates = build_daily_life_candidates(ai, hero, view, now_ms=now_ms)
    if not candidates:
        return False

    current = _find_active_ambient_candidate(candidates, mem)
    if current is None:
        best, best_score = _pick_best_ambient_candidate(ai, hero, view, candidates, now_ms=now_ms)
        if best is None or best_score < 5.0:
            return False
        _apply_ambient_candidate(
            ai,
            hero,
            view,
            best,
            now_ms=now_ms,
            significance=best_score,
            previous_motive=str(mem.get("active_motive", "") or ""),
            previous_target_key=str(mem.get("active_target_key", "") or ""),
            reason="initial_selection",
            significance_delta=0.0,
        )
        return True

    current_score = score_daily_life_candidate(
        ai,
        hero,
        current,
        view,
        now_ms=now_ms,
        ignore_memory_penalties=True,
    )
    best, best_score = _pick_best_ambient_candidate(ai, hero, view, candidates, now_ms=now_ms, exclude=current)

    hp_pct = float(getattr(hero, "health_percent", 1.0) or 1.0)
    if hp_pct <= _CRITICAL_HEALTH_BYPASS_PCT:
        if current.motive == "safe_rest":
            return _continue_ambient_behavior(
                ai,
                hero,
                view,
                current,
                now_ms=now_ms,
                current_significance=current_score,
                significance_delta=0.0,
                reason="urgent_safety_hold",
            )
        urgent_candidate, urgent_score = _pick_best_ambient_candidate(
            ai,
            hero,
            view,
            candidates,
            now_ms=now_ms,
            motive="safe_rest",
            ignore_memory_penalties=True,
        )
        if urgent_candidate is not None and urgent_candidate.target_key != current.target_key:
            _apply_ambient_candidate(
                ai,
                hero,
                view,
                urgent_candidate,
                now_ms=now_ms,
                significance=urgent_score,
                previous_motive=current.motive,
                previous_target_key=current.target_key,
                reason="urgent_safety_bypass",
                significance_delta=urgent_score - current_score,
            )
            return True

    if best is not None:
        dwell_ms = int(now_ms) - int(mem.get("last_switch_ms", 0) or 0)
        significance_delta = float(best_score - current_score)
        if significance_delta >= _AMBIENT_SWITCH_THRESHOLD and dwell_ms >= _AMBIENT_MIN_DWELL_MS:
            _apply_ambient_candidate(
                ai,
                hero,
                view,
                best,
                now_ms=now_ms,
                significance=best_score,
                previous_motive=current.motive,
                previous_target_key=current.target_key,
                reason="significance_overwhelm",
                significance_delta=significance_delta,
            )
            return True
        hold_reason = "commit_hold" if now_ms < int(mem.get("commit_until_ms", 0) or 0) else "hysteresis_hold"
        return _continue_ambient_behavior(
            ai,
            hero,
            view,
            current,
            now_ms=now_ms,
            current_significance=current_score,
            significance_delta=significance_delta,
            reason=hold_reason,
        )

    return _continue_ambient_behavior(
        ai,
        hero,
        view,
        current,
        now_ms=now_ms,
        current_significance=current_score,
        significance_delta=0.0,
        reason="stable_hold",
    )


def _apply_ambient_target(ai: Any, hero: Any, view: Any, candidate: AmbientCandidate) -> None:
    view = as_ai_view(view)
    buildings = list(getattr(view, "buildings", ()) or ())
    world = getattr(view, "world", None)
    target_ref = candidate.target_ref

    if candidate.motive == "wilderness_explore":
        hero.set_target_position(*candidate.target_xy)
        hero.target = {"type": "explore_frontier"}
        hero.state = HeroState.MOVING
        _set_ambient_intent(ai, hero, "idle")
    elif candidate.motive == "poi_scout":
        hero.set_target_position(*candidate.target_xy)
        hero.target = {"type": "visit_poi", "poi": target_ref}
        hero.state = HeroState.MOVING
        _set_ambient_intent(ai, hero, "idle")
    elif candidate.motive == "monster_patrol":
        hero.set_target_position(*candidate.target_xy)
        hero.target = target_ref
        hero.state = HeroState.MOVING
        _set_ambient_intent(ai, hero, "engaging_enemy" if getattr(target_ref, "is_alive", False) else "idle")
    elif candidate.motive == "rescue_hero":
        if target_ref is not None and _building_slug(target_ref) in {"castle", "inn", "house", "herald_post", "marketplace", "blacksmith", "trading_post"}:
            route_to_building(hero, world, buildings, target_ref)
        else:
            hero.set_target_position(*candidate.target_xy)
        hero.target = {
            "type": "visit_poi",
            "rescue_id": candidate.target_key,
            "target_location": candidate.detail,
            "target_ref": target_ref,
        }
        hero.state = HeroState.MOVING
        _set_ambient_intent(ai, hero, "idle")
    elif candidate.motive == "revenge_hero":
        hero.target = target_ref
        hero.set_target_position(*candidate.target_xy)
        hero.state = HeroState.MOVING
        _set_ambient_intent(ai, hero, "engaging_enemy")
    elif candidate.motive == "safe_rest":
        if target_ref is not None:
            route_to_building(hero, world, buildings, target_ref)
        if _building_slug(target_ref) == "inn":
            hero.target = {"type": "rest_inn", "inn": target_ref}
        else:
            hero.target = {"type": "going_home"}
        hero.state = HeroState.MOVING
        _set_ambient_intent(ai, hero, "returning_to_safety")
    elif candidate.motive == "social_linger":
        if target_ref is not None:
            route_to_building(hero, world, buildings, target_ref)
        if _building_slug(target_ref) == "inn":
            hero.target = {"type": "get_drink", "inn": target_ref}
        else:
            hero.target = {"type": "patrol"}
        hero.state = HeroState.MOVING
        _set_ambient_intent(ai, hero, "idle")
    elif candidate.motive == "opportunity_check":
        if target_ref is not None:
            route_to_building(hero, world, buildings, target_ref)
        hero.target = {"type": "patrol"}
        hero.state = HeroState.MOVING
        _set_ambient_intent(ai, hero, "idle")
    elif candidate.motive == "home_or_guild_time":
        if target_ref is not None:
            route_to_building(hero, world, buildings, target_ref)
        if target_ref is hero.home_building:
            hero.target = {"type": "going_home"}
            _set_ambient_intent(ai, hero, "returning_to_safety")
        elif _building_slug(target_ref) == "inn":
            hero.target = {"type": "rest_inn", "inn": target_ref}
            _set_ambient_intent(ai, hero, "returning_to_safety")
        else:
            hero.target = {"type": "patrol"}
            _set_ambient_intent(ai, hero, "idle")
        hero.state = HeroState.MOVING
    elif candidate.motive == "road_watch":
        hero.set_target_position(*candidate.target_xy)
        hero.target = {"type": "patrol"}
        hero.state = HeroState.MOVING
        _set_ambient_intent(ai, hero, "idle")
    else:  # kingdom_roam
        if target_ref is not None:
            route_to_building(hero, world, buildings, target_ref)
        hero.target = {"type": "patrol"}
        hero.state = HeroState.MOVING
        _set_ambient_intent(ai, hero, "idle")

def _apply_ambient_candidate(
    ai: Any,
    hero: Any,
    view: Any,
    candidate: AmbientCandidate,
    *,
    now_ms: int,
    significance: float,
    previous_motive: str,
    previous_target_key: str,
    reason: str,
    significance_delta: float,
) -> None:
    _apply_ambient_target(ai, hero, view, candidate)
    _finalize_ambient_selection(
        hero,
        candidate,
        now_ms=now_ms,
        significance=significance,
        previous_motive=previous_motive,
        previous_target_key=previous_target_key,
        reason=reason,
        significance_delta=significance_delta,
    )
    mem = get_ambient_memory(hero)
    _record_ambient_decision(
        ai,
        hero,
        action=candidate.motive,
        reason=f"daily life: {candidate.motive} -> {candidate.detail or candidate.primitive} ({reason})",
        intent=getattr(hero, "intent", "idle") or "idle",
        inputs_summary={
            "motive": candidate.motive,
            "target_key": candidate.target_key,
            "target_xy": tuple(round(float(v), 3) for v in candidate.target_xy),
            "commit_until_ms": int(now_ms + int(candidate.commit_ms)),
            "active_significance": round(float(significance), 3),
            "significance_delta": round(float(significance_delta), 3),
            "last_switch_ms": int(mem.get("last_switch_ms", 0) or 0),
            "switch_count": int(mem.get("switch_count", 0) or 0),
        },
        now_ms=now_ms,
    )


def _reapply_ambient_target(ai: Any, hero: Any, view: Any, mem: dict[str, Any], *, now_ms: int) -> bool:
    motive = str(mem.get("active_motive", "") or "")
    target_xy = mem.get("active_target_xy")
    target_ref = mem.get("active_target_ref", None)
    primitive = str(mem.get("active_primitive", "") or "")
    if not motive or not isinstance(target_xy, (tuple, list)) or len(target_xy) != 2:
        return False
    if motive == "revenge_hero" and target_ref is not None and not getattr(target_ref, "is_alive", False):
        return False
    if primitive in {"going_home", "rest_inn", "get_drink", "patrol"} and target_ref is not None:
        buildings = list(getattr(view, "buildings", ()) or ())
        world = getattr(view, "world", None)
        route_to_building(hero, world, buildings, target_ref)
    elif motive == "rescue_hero" and target_ref is not None:
        buildings = list(getattr(view, "buildings", ()) or ())
        world = getattr(view, "world", None)
        if _building_slug(target_ref) in {"castle", "inn", "house", "herald_post", "marketplace", "blacksmith", "trading_post"}:
            route_to_building(hero, world, buildings, target_ref)
            hero.target = {
                "type": "visit_poi",
                "rescue_id": str(mem.get("active_target_key", "") or ""),
                "target_location": str(getattr(target_ref, "name", "") or getattr(target_ref, "display_name", "") or ""),
                "target_ref": target_ref,
            }
        else:
            hero.set_target_position(float(target_xy[0]), float(target_xy[1]))
            hero.target = {
                "type": "visit_poi",
                "rescue_id": str(mem.get("active_target_key", "") or ""),
                "target_location": str(getattr(target_ref, "name", "") or getattr(target_ref, "display_name", "") or ""),
                "target_ref": target_ref,
            }
    elif motive == "revenge_hero" and target_ref is not None:
        hero.target = target_ref
        hero.set_target_position(float(target_xy[0]), float(target_xy[1]))
    else:
        hero.set_target_position(float(target_xy[0]), float(target_xy[1]))
    if motive in {"safe_rest", "home_or_guild_time"}:
        hero.state = HeroState.MOVING
        _set_ambient_intent(ai, hero, "returning_to_safety")
    elif motive == "revenge_hero":
        hero.state = HeroState.MOVING
        _set_ambient_intent(ai, hero, "engaging_enemy")
    else:
        hero.state = HeroState.MOVING
    ai._debug_log(f"{hero.name} -> continuing ambient {motive}")
    return True


def _write_ambient_memory(hero: Any, candidate: AmbientCandidate, *, now_ms: int) -> None:
    mem = get_ambient_memory(hero)
    commit_until = int(now_ms + int(candidate.commit_ms))
    cooldowns = dict(mem.get("target_cooldowns", {}) or {})
    cooldowns[candidate.target_key] = int(now_ms + int(candidate.cooldown_ms))
    motive_cooldowns = dict(mem.get("motive_cooldowns", {}) or {})
    motive_cooldowns[candidate.motive] = int(now_ms + int(candidate.cooldown_ms))
    motive_counts = dict(mem.get("motive_counts", {}) or {})
    motive_counts[candidate.motive] = int(motive_counts.get(candidate.motive, 0) or 0) + 1
    mem.update(
        {
            "active_motive": candidate.motive,
            "active_target_key": candidate.target_key,
            "active_target_xy": tuple(float(v) for v in candidate.target_xy),
            "active_target_ref": candidate.target_ref,
            "active_primitive": candidate.primitive,
            "commit_until_ms": commit_until,
            "target_cooldowns": cooldowns,
            "motive_cooldowns": motive_cooldowns,
            "motive_counts": motive_counts,
            "last_cluster_key": candidate.cluster_key,
        }
    )


def _entity_identity_strings(entity: Any) -> set[str]:
    values: set[str] = set()
    for attr in (
        "entity_id",
        "hero_id",
        "boss_id",
        "rescue_id",
        "revenge_id",
        "target_location_id",
        "captured_hero_id",
        "fallen_hero_id",
        "name",
        "display_name",
        "building_type",
        "poi_type",
        "captor_boss_id",
        "captor_boss_name",
        "captured_hero_name",
        "boss_name",
        "location_name",
        "target_location_name",
    ):
        value = str(getattr(entity, attr, "") or "").strip()
        if value:
            values.add(value.lower())
    poi_def = getattr(entity, "poi_def", None)
    if poi_def is not None:
        value = str(getattr(poi_def, "display_name", "") or "").strip()
        if value:
            values.add(value.lower())
    return values


def _pick_best_matching_entity(hero: Any, candidates: list[Any], labels: set[str]) -> Any | None:
    scored: list[tuple[float, str, Any]] = []
    for entity in candidates:
        if entity is None:
            continue
        if not _entity_identity_strings(entity).intersection(labels):
            continue
        x, y = _target_center(entity)
        scored.append((_distance_tiles(hero, x, y), _entity_key("story", entity), entity))
    if not scored:
        return None
    scored.sort(key=lambda row: (row[0], row[1]))
    return scored[0][2]


def _resolve_rescue_target(
    hero: Any,
    rescue: dict[str, Any],
    buildings: list[Any],
    pois: list[Any],
) -> tuple[Any | None, tuple[float, float] | None, str, str]:
    labels = {
        str(rescue.get("rescue_id", "")).strip().lower(),
        str(rescue.get("captured_hero_id", "")).strip().lower(),
        str(rescue.get("captured_hero_name", "")).strip().lower(),
        str(rescue.get("captor_boss_id", "")).strip().lower(),
        str(rescue.get("captor_boss_name", "")).strip().lower(),
        str(rescue.get("target_location_id", "")).strip().lower(),
        str(rescue.get("target_location_name", "")).strip().lower(),
    }
    labels.discard("")
    target = _pick_best_matching_entity(hero, [*buildings, *pois], labels)
    if target is None:
        return (None, None, "", "")
    tx, ty = _target_center(target)
    rescue_id = str(rescue.get("rescue_id", "") or rescue.get("captured_hero_id", "") or rescue.get("target_location_id", "") or "")
    detail = str(rescue.get("captured_hero_name", "") or rescue.get("target_location_name", "") or rescue_id or "rescue")
    return (target, (tx, ty), rescue_id, detail)


def _resolve_revenge_target(
    hero: Any,
    revenge: dict[str, Any],
    boss_encounters: list[Any],
    enemies: list[Any],
) -> tuple[Any | None, tuple[float, float] | None, str, str]:
    labels = {
        str(revenge.get("revenge_id", "")).strip().lower(),
        str(revenge.get("boss_id", "")).strip().lower(),
        str(revenge.get("boss_name", "")).strip().lower(),
        str(revenge.get("fallen_hero_id", "")).strip().lower(),
        str(revenge.get("fallen_hero_name", "")).strip().lower(),
        str(revenge.get("target_location_id", "")).strip().lower(),
        str(revenge.get("target_location_name", "")).strip().lower(),
    }
    labels.discard("")
    target = _pick_best_matching_entity(hero, [*boss_encounters, *enemies], labels)
    if target is None or not getattr(target, "is_alive", False):
        return (None, None, "", "")
    tx, ty = _target_center(target)
    revenge_id = str(revenge.get("revenge_id", "") or revenge.get("revenge_chain_id", "") or revenge.get("boss_id", "") or "")
    detail = str(revenge.get("boss_name", "") or revenge.get("fallen_hero_name", "") or revenge_id or "revenge")
    return (target, (tx, ty), revenge_id, detail)


def _candidate_for_building(
    hero: Any,
    *,
    motive: str,
    primitive: str,
    building: Any,
    now_ms: int,
    detail: str,
) -> AmbientCandidate:
    x, y = _target_center(building)
    d_tiles = _distance_tiles(hero, x, y)
    base = float(_MOTIVE_BASE_SCORE.get(motive, 5.0))
    if motive == "kingdom_roam":
        base += min(10.0, d_tiles)
    elif motive == "social_linger":
        base += max(0.0, 12.0 - d_tiles)
    elif motive == "opportunity_check":
        base += max(0.0, 14.0 - d_tiles)
    elif motive == "home_or_guild_time":
        base += max(0.0, 14.0 - d_tiles)
    elif motive == "safe_rest":
        base += max(0.0, 16.0 - d_tiles)
    return AmbientCandidate(
        motive=motive,
        target_key=_entity_key("building", building),
        target_xy=(x, y),
        primitive=primitive,
        target_ref=building,
        base_score=base,
        commit_ms=_commit_ms(hero, motive, _entity_key("building", building)),
        cooldown_ms=_MOTIVE_TARGET_COOLDOWN_MS[motive],
        cluster_key=_cluster_key(x, y),
        detail=detail,
    )


def _pick_roam_anchor(hero: Any, castle: Any, buildings: list[Any]) -> Any | None:
    anchors = [castle] if castle is not None else []
    anchors.extend(
        b
        for b in buildings
        if _building_slug(b) in {
            "inn",
            "marketplace",
            "blacksmith",
            "trading_post",
            "warrior_guild",
            "ranger_guild",
            "rogue_guild",
            "wizard_guild",
            "temple",
            "temple_agrela",
            "temple_dauros",
            "temple_fervus",
            "temple_krypta",
            "temple_krolm",
            "temple_helia",
            "temple_lunord",
            "guardhouse",
            "palace",
            "house",
            "farm",
            "food_stand",
            "herald_post",
        }
    )
    if not anchors:
        return None
    return _pick_best_by_score(hero, anchors, motive="kingdom_roam")


def _pick_frontier(hero: Any, world: Any) -> tuple[int, int] | None:
    if world is None:
        return None
    from ai.behaviors import exploration

    frontier = exploration._find_black_fog_frontier_tiles(world, hero, max_candidates=6)
    if not frontier:
        return None
    frontier.sort(key=lambda row: (-row[2], row[1], row[0]))
    gx, gy, _ = frontier[0]
    return (int(gx), int(gy))


def _pick_poi(hero: Any, pois: list[Any]) -> Any | None:
    if not pois:
        return None
    scored: list[tuple[float, str, Any]] = []
    for poi in pois:
        if not getattr(poi, "is_discovered", False) and not getattr(poi, "is_seen", False):
            continue
        if getattr(poi, "is_depleted", False):
            continue
        pcx, pcy = _poi_center_world(poi)
        score = score_poi_for_personality(hero, poi, dist_tiles=_distance_tiles(hero, pcx, pcy))
        scored.append((float(score), _entity_key("poi", poi), poi))
    if not scored:
        return None
    scored.sort(key=lambda row: (-row[0], row[1]))
    return scored[0][2]


def _pick_monster_patrol_target(
    hero: Any,
    enemies: list[Any],
    buildings: list[Any],
    boss_encounters: list[Any],
) -> Any | None:
    scored: list[tuple[float, str, Any]] = []
    for enemy in enemies:
        if not getattr(enemy, "is_alive", False):
            continue
        dist = _distance_tiles(hero, float(getattr(enemy, "x", 0.0)), float(getattr(enemy, "y", 0.0)))
        if dist < 5.0:
            continue
        score = 20.0 + max(0.0, 16.0 - abs(dist - 8.0))
        scored.append((score, _entity_key("enemy", enemy), enemy))
    for building in buildings:
        if not getattr(building, "is_lair", False):
            continue
        if int(getattr(building, "hp", 0) or 0) <= 0:
            continue
        dist = _distance_tiles(hero, float(getattr(building, "center_x", 0.0)), float(getattr(building, "center_y", 0.0)))
        score = 18.0 + max(0.0, 16.0 - abs(dist - 10.0))
        scored.append((score, _entity_key("lair", building), building))
    for boss in boss_encounters:
        if str(getattr(boss, "status", "") or "").lower() not in {"active", "engaged"}:
            continue
        bx, by = _target_center(boss)
        dist = _distance_tiles(hero, bx, by)
        if dist < 3.0:
            continue
        score = 18.0 + max(0.0, 14.0 - abs(dist - 12.0))
        scored.append((score, _entity_key("boss", boss), boss))
    if not scored:
        return None
    scored.sort(key=lambda row: (-row[0], row[1]))
    return scored[0][2]


def _pick_safe_rest_target(hero: Any, castle: Any, home: Any, buildings: list[Any]) -> tuple[Any | None, str]:
    candidates = [b for b in (home, castle, *buildings) if b is not None]
    scored: list[tuple[float, str, Any]] = []
    for building in candidates:
        slug = _building_slug(building)
        if slug not in {
            "castle",
            "inn",
            "house",
            "temple",
            "temple_agrela",
            "temple_dauros",
            "temple_fervus",
            "temple_krypta",
            "temple_krolm",
            "temple_helia",
            "temple_lunord",
        }:
            continue
        if getattr(building, "is_under_attack", False):
            continue
        dist = _distance_tiles(hero, float(getattr(building, "center_x", 0.0)), float(getattr(building, "center_y", 0.0)))
        hp_pct = float(getattr(hero, "health_percent", 1.0) or 1.0)
        score = 10.0 + max(0.0, 16.0 - dist)
        if hp_pct < 0.50:
            score += 12.0
        scored.append((score, _entity_key("rest", building), building))
    if not scored:
        return (None, "")
    scored.sort(key=lambda row: (-row[0], row[1]))
    target = scored[0][2]
    slug = _building_slug(target)
    return (target, "rest_inn" if slug == "inn" else "going_home")


def _pick_social_target(hero: Any, buildings: list[Any]) -> Any | None:
    candidates = []
    for building in buildings:
        slug = _building_slug(building)
        if slug not in {"inn", "castle", "marketplace", "trading_post", "warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild"}:
            continue
        if getattr(building, "is_under_attack", False):
            continue
        candidates.append(building)
    if not candidates:
        return None
    return _pick_best_by_score(hero, candidates, motive="social_linger")


def _pick_opportunity_target(hero: Any, buildings: list[Any], view: Any) -> Any | None:
    candidates = []
    for building in buildings:
        slug = _building_slug(building)
        if slug not in {"castle", "herald_post", "marketplace", "blacksmith", "trading_post"}:
            continue
        if getattr(building, "is_under_attack", False):
            continue
        candidates.append(building)
    if not candidates:
        return None
    return _pick_best_by_score(hero, candidates, motive="opportunity_check")


def _pick_home_or_guild_target(hero: Any, buildings: list[Any], home: Any) -> Any | None:
    if home is not None:
        return home
    class_slug = str(getattr(hero, "hero_class", "") or "").lower()
    guild_slug = f"{class_slug}_guild" if class_slug else ""
    candidates = [b for b in buildings if _building_slug(b) == guild_slug]
    if not candidates:
        return None
    return _pick_best_by_score(hero, candidates, motive="home_or_guild_time")


def _pick_road_watch_point(hero: Any, castle: Any, buildings: list[Any]) -> tuple[float, float] | None:
    if castle is None:
        return None
    target = _pick_roam_anchor(hero, castle, buildings)
    if target is None:
        return (float(getattr(castle, "center_x", 0.0)), float(getattr(castle, "center_y", 0.0)))
    cx = float(getattr(castle, "center_x", 0.0))
    cy = float(getattr(castle, "center_y", 0.0))
    tx, ty = _target_center(target)
    # A deterministic point along the route between castle and target.
    mid_x = cx * 0.65 + tx * 0.35
    mid_y = cy * 0.65 + ty * 0.35
    return (mid_x, mid_y)


def _pick_best_by_score(hero: Any, items: list[Any], *, motive: str) -> Any | None:
    scored: list[tuple[float, str, Any]] = []
    for item in items:
        x, y = _target_center(item)
        dist = _distance_tiles(hero, x, y)
        score = _MOTIVE_BASE_SCORE.get(motive, 5.0) + max(0.0, 12.0 - dist)
        if motive == "kingdom_roam":
            score += dist
        elif motive == "social_linger":
            score += max(0.0, 10.0 - dist)
        elif motive == "opportunity_check":
            score += max(0.0, 14.0 - dist)
        elif motive == "home_or_guild_time":
            score += max(0.0, 14.0 - dist)
        elif motive == "safe_rest":
            score += max(0.0, 16.0 - dist)
        scored.append((score, _entity_key("target", item), item))
    if not scored:
        return None
    scored.sort(key=lambda row: (-row[0], row[1]))
    return scored[0][2]


def _crowding_penalty(candidate: AmbientCandidate, hero: Any, view: Any) -> float:
    heroes = list(getattr(view, "heroes", ()) or ())
    if not heroes:
        return 0.0
    cluster = candidate.cluster_key
    if not cluster:
        return 0.0
    penalty = 0.0
    for other in heroes:
        if other is hero or not getattr(other, "is_alive", True):
            continue
        other_key = _hero_active_cluster(other)
        if other_key == cluster:
            penalty += 6.0
        other_target_xy = _hero_active_target_xy(other)
        if other_target_xy is not None and _cluster_key(*other_target_xy) == cluster:
            penalty += 3.0
        if other_target_xy is not None:
            od = math.hypot(float(candidate.target_xy[0]) - float(other_target_xy[0]), float(candidate.target_xy[1]) - float(other_target_xy[1])) / float(TILE_SIZE)
            if od < 3.5:
                penalty += 2.0
    return penalty


def _hero_active_cluster(hero: Any) -> str:
    mem = _AMBIENT_MEMORY.get(_hero_key(hero))
    if mem is not None:
        return str(mem.get("last_cluster_key", "") or "")
    return _cluster_key(*getattr(hero, "target_position", (0.0, 0.0))) if getattr(hero, "target_position", None) else ""


def _hero_active_target_xy(hero: Any) -> tuple[float, float] | None:
    mem = _AMBIENT_MEMORY.get(_hero_key(hero))
    if mem is not None and isinstance(mem.get("active_target_xy"), (tuple, list)):
        xy = mem.get("active_target_xy")
        return (float(xy[0]), float(xy[1]))
    tp = getattr(hero, "target_position", None)
    if isinstance(tp, (tuple, list)) and len(tp) == 2:
        return (float(tp[0]), float(tp[1]))
    return None


def _stable_tiebreak(hero: Any, candidate: AmbientCandidate) -> float:
    salt = zlib.crc32(f"{_hero_key(hero)}:{candidate.target_key}:{candidate.motive}".encode("utf-8"))
    return (salt % 997) / 9970.0


def _commit_ms(hero: Any, motive: str, target_key: str) -> int:
    salt = zlib.crc32(f"{_hero_key(hero)}:{motive}:{target_key}".encode("utf-8"))
    base = int(_MOTIVE_COMMIT_MS.get(motive, 15_000))
    return base + int(salt % max(1, base // 3))


def _hero_key(hero: Any) -> str:
    key = str(getattr(hero, "hero_id", "") or getattr(hero, "name", "") or "")
    if key:
        return key
    return f"hero-{id(hero)}"


def _building_slug(building: Any) -> str:
    bt = getattr(building, "building_type", None)
    if hasattr(bt, "value"):
        bt = getattr(bt, "value", bt)
    return str(bt or "").lower()


def _entity_key(prefix: str, entity: Any) -> str:
    ident = getattr(entity, "entity_id", None)
    if ident is None:
        ident = getattr(entity, "hero_id", None)
    if ident is None:
        ident = getattr(entity, "name", None)
    if ident is None:
        ident = f"{int(getattr(entity, 'grid_x', 0) or 0)}:{int(getattr(entity, 'grid_y', 0) or 0)}"
    return f"{prefix}:{ident}"


def _target_center(entity: Any) -> tuple[float, float]:
    if entity is None:
        return (0.0, 0.0)
    pos = getattr(entity, "position", None)
    if isinstance(pos, (tuple, list)) and len(pos) == 2:
        return (float(pos[0]), float(pos[1]))
    return (
        float(getattr(entity, "center_x", getattr(entity, "x", 0.0))),
        float(getattr(entity, "center_y", getattr(entity, "y", 0.0))),
    )


def _poi_center_world(poi: Any) -> tuple[float, float]:
    poi_def = getattr(poi, "poi_def", None)
    size = getattr(poi_def, "size", (1, 1)) if poi_def else (1, 1)
    cx = (getattr(poi, "grid_x", 0) + size[0] / 2) * TILE_SIZE
    cy = (getattr(poi, "grid_y", 0) + size[1] / 2) * TILE_SIZE
    return (float(cx), float(cy))


def _distance_tiles(hero: Any, x: float, y: float) -> float:
    try:
        return float(hero.distance_to(float(x), float(y))) / float(TILE_SIZE)
    except Exception:
        return 0.0


def _cluster_key(x: float, y: float) -> str:
    return f"{int(float(x) // (TILE_SIZE * _CLUSTER_TILE_SPAN))}:{int(float(y) // (TILE_SIZE * _CLUSTER_TILE_SPAN))}"
