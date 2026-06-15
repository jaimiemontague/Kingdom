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

_CLUSTER_TILE_SPAN = 4
_RECENT_TARGET_COOLDOWN_MS = 45_000

_CLASS_BIAS: dict[str, dict[str, float]] = {
    "warrior": {
        "monster_patrol": 8.0,
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
        "safe_rest": -4.0,
    },
    "cautious and strategic": {
        "safe_rest": 6.0,
        "home_or_guild_time": 4.0,
        "social_linger": 3.0,
        "monster_patrol": -5.0,
        "wilderness_explore": -2.0,
    },
    "greedy but cowardly": {
        "opportunity_check": 6.0,
        "poi_scout": 5.0,
        "kingdom_roam": 3.0,
        "social_linger": 1.0,
        "monster_patrol": -2.0,
    },
    "balanced and reliable": {
        "kingdom_roam": 4.0,
        "social_linger": 3.0,
        "road_watch": 2.0,
        "opportunity_check": 1.0,
    },
}

_MOTIVE_BASE_SCORE: dict[str, float] = {
    "kingdom_roam": 7.0,
    "wilderness_explore": 9.0,
    "poi_scout": 8.0,
    "monster_patrol": 8.5,
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
        "target_cooldowns": dict(mem.get("target_cooldowns", {}) or {}),
        "motive_cooldowns": dict(mem.get("motive_cooldowns", {}) or {}),
        "motive_counts": dict(mem.get("motive_counts", {}) or {}),
        "last_cluster_key": str(mem.get("last_cluster_key", "") or ""),
    }


def build_daily_life_candidates(ai: Any, hero: Any, view: Any, *, now_ms: int | None = None) -> list[AmbientCandidate]:
    """Enumerate candidate ambient daily-life choices for ``hero``."""
    view = as_ai_view(view)
    now_ms = int(sim_now_ms() if now_ms is None else now_ms)
    buildings = list(getattr(view, "buildings", ()) or ())
    heroes = list(getattr(view, "heroes", ()) or ())
    pois = list(getattr(view, "pois", ()) or ())
    enemies = [e for e in (getattr(view, "enemies", ()) or ()) if getattr(e, "is_alive", False)]
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

    monster = _pick_monster_patrol_target(hero, enemies, buildings)
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


def score_daily_life_candidate(ai: Any, hero: Any, candidate: AmbientCandidate, view: Any, *, now_ms: int | None = None) -> float:
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
    elif candidate.motive == "safe_rest":
        score += max(0.0, 16.0 - dist_tiles)
    elif candidate.motive == "social_linger":
        score += max(0.0, 12.0 - dist_tiles)
    elif candidate.motive == "opportunity_check":
        score += max(0.0, 13.0 - dist_tiles)
    elif candidate.motive == "home_or_guild_time":
        score += max(0.0, 14.0 - dist_tiles)
    elif candidate.motive == "road_watch":
        score += max(0.0, 10.0 - abs(dist_tiles - 6.0))

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


def try_daily_life(ai: Any, hero: Any, view: Any) -> bool:
    """Choose or continue a deterministic ambient daily-life activity."""
    view = as_ai_view(view)
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
    if now_ms < int(mem.get("commit_until_ms", 0) or 0):
        if _reapply_ambient_target(ai, hero, view, mem, now_ms=now_ms):
            return True

    candidates = build_daily_life_candidates(ai, hero, view, now_ms=now_ms)
    if not candidates:
        return False

    best: AmbientCandidate | None = None
    best_score = -1e9
    for candidate in candidates:
        score = score_daily_life_candidate(ai, hero, candidate, view, now_ms=now_ms)
        if score > best_score:
            best = candidate
            best_score = score
        elif best is not None and abs(score - best_score) < 1e-9:
            if candidate.target_key < best.target_key:
                best = candidate
                best_score = score

    if best is None or best_score < 5.0:
        return False

    _apply_ambient_candidate(ai, hero, view, best, now_ms=now_ms)
    return True


def _apply_ambient_candidate(ai: Any, hero: Any, view: Any, candidate: AmbientCandidate, *, now_ms: int) -> None:
    view = as_ai_view(view)
    mem = get_ambient_memory(hero)
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

    _write_ambient_memory(hero, candidate, now_ms=now_ms)
    _record_ambient_decision(
        ai,
        hero,
        action=candidate.motive,
        reason=f"daily life: {candidate.motive} -> {candidate.detail or candidate.primitive}",
        intent=getattr(hero, "intent", "idle") or "idle",
        inputs_summary={
            "motive": candidate.motive,
            "target_key": candidate.target_key,
            "target_xy": tuple(round(float(v), 3) for v in candidate.target_xy),
            "commit_until_ms": int(now_ms + int(candidate.commit_ms)),
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
    if primitive in {"going_home", "rest_inn", "get_drink", "patrol"} and target_ref is not None:
        buildings = list(getattr(view, "buildings", ()) or ())
        world = getattr(view, "world", None)
        route_to_building(hero, world, buildings, target_ref)
    else:
        hero.set_target_position(float(target_xy[0]), float(target_xy[1]))
    if motive in {"safe_rest", "home_or_guild_time"}:
        hero.state = HeroState.MOVING
        _set_ambient_intent(ai, hero, "returning_to_safety")
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


def _pick_monster_patrol_target(hero: Any, enemies: list[Any], buildings: list[Any]) -> Any | None:
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
        if slug not in {"herald_post", "marketplace", "blacksmith", "trading_post"}:
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
