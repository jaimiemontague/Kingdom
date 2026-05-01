"""
Named autonomous LLM decision moments (WK50 Phase 2A).

Pure policy helpers: sim-time only, no pygame/UI, no hero mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from config import TILE_SIZE
from game.entities.hero import HeroState

# HP band aliases (fractions of max)
_MOMENT_LOW_HP = 0.50
_MOMENT_CRITICAL_HP = 0.25
_MOMENT_RECOVERED_HP = 0.95
_MOMENT_LOSS_RECENT = 0.25  # lost >= 25% max HP since full
_MOMENT_SHOP_GOLD_MIN = 30
_MOMENT_NEAR_SHOP_TILES = 6
_POST_COMBAT_MEMORY_MS = 120_000
_NEAR_ENEMY_POST_COMBAT_TILES = 3.0


class DecisionMomentType(str, Enum):
    LOW_HEALTH_COMBAT = "low_health_combat"
    POST_COMBAT_INJURED = "post_combat_injured"
    RESTED_AND_READY = "rested_and_ready"
    SHOPPING_OPPORTUNITY = "shopping_opportunity"


@dataclass(frozen=True, slots=True)
class DecisionMoment:
    moment_type: DecisionMomentType
    urgency: int
    reason: str
    allowed_actions: tuple[str, ...]
    context_focus: tuple[str, ...]
    cooldown_ms: int

    def allowed_actions_set(self) -> frozenset[str]:
        return frozenset(self.allowed_actions)

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "type": self.moment_type.value,
            "urgency": self.urgency,
            "reason": self.reason,
            "allowed_actions": list(self.allowed_actions),
            "context_focus": list(self.context_focus),
            "cooldown_ms": self.cooldown_ms,
        }


def _hero_state(hero: Any) -> Any:
    return getattr(hero, "state", None)


def _health_fraction(hero: Any) -> float:
    try:
        return float(getattr(hero, "health_percent", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _has_live_enemy_target(hero: Any) -> bool:
    t = getattr(hero, "target", None)
    return t is not None and hasattr(t, "is_alive") and bool(getattr(t, "is_alive", False))


def _nearest_enemy_tiles(hero: Any, game_state: dict) -> float | None:
    best: float | None = None
    for enemy in game_state.get("enemies", []) or []:
        if not getattr(enemy, "is_alive", False):
            continue
        try:
            d = float(hero.distance_to(enemy.x, enemy.y)) / float(TILE_SIZE or 1)
        except Exception:
            continue
        best = d if best is None else min(best, d)
    return best


def _recent_combat_memory(hero: Any, now_ms: int) -> bool:
    mem = getattr(hero, "profile_memory", None) or ()
    for e in mem:
        try:
            ts = int(getattr(e, "sim_time_ms", 0) or 0)
        except (TypeError, ValueError):
            continue
        if now_ms - ts > _POST_COMBAT_MEMORY_MS:
            continue
        et = str(getattr(e, "event_type", "") or "").lower()
        tags = getattr(e, "tags", ()) or ()
        tag_s = " ".join(str(x).lower() for x in tags)
        subj = str(getattr(e, "subject_type", "") or "").lower()
        if "combat" in et or "damage" in et or "combat" in tag_s or subj == "enemy":
            return True
    return False


def _inside_recovery_building(hero: Any) -> bool:
    if not getattr(hero, "is_inside_building", False):
        return False
    inn = getattr(hero, "inside_building", None)
    slug = getattr(getattr(inn, "building_type", None), "value", None)
    if slug is None and inn is not None:
        slug = getattr(inn, "building_type", "")
    slug = str(slug or "").lower()
    return slug in {"castle", "inn", "house", "farm", "elven_bungalow", "dwarven_settlement", "gnome_hovel"}


def _near_marketplace(hero: Any, game_state: dict) -> bool:
    for b in game_state.get("buildings", []) or []:
        if getattr(b, "building_type", None) != "marketplace":
            continue
        try:
            if hero.distance_to(b.center_x, b.center_y) < TILE_SIZE * _MOMENT_NEAR_SHOP_TILES:
                return True
        except Exception:
            continue
    return False


def _shopping_need(hero: Any) -> bool:
    try:
        pots = int(getattr(hero, "potions", 0) or 0)
        max_p = int(getattr(hero, "max_potions", 0) or 0)
    except (TypeError, ValueError):
        pots, max_p = 0, 0
    if max_p > 0 and pots < max_p:
        return True
    return _health_fraction(hero) < 0.99


def moment_low_health_combat(hero: Any) -> DecisionMoment | None:
    if _hero_state(hero) != HeroState.FIGHTING:
        return None
    hp = _health_fraction(hero)
    if hp >= _MOMENT_LOW_HP:
        return None
    urgency = 2 if hp < _MOMENT_CRITICAL_HP else 1
    reason = "critical HP in combat" if urgency == 2 else "low HP while fighting"
    return DecisionMoment(
        moment_type=DecisionMomentType.LOW_HEALTH_COMBAT,
        urgency=urgency,
        reason=reason,
        allowed_actions=("fight", "retreat", "use_potion"),
        context_focus=("enemies", "potions", "health", "allies", "safety"),
        cooldown_ms=4_000,
    )


def moment_post_combat_injured(hero: Any, game_state: dict, now_ms: int) -> DecisionMoment | None:
    if _hero_state(hero) == HeroState.FIGHTING:
        return None
    if _has_live_enemy_target(hero):
        return None
    hp = _health_fraction(hero)
    try:
        max_hp = max(1, int(getattr(hero, "max_hp", 1) or 1))
        cur_hp = int(getattr(hero, "hp", 0) or 0)
    except (TypeError, ValueError):
        max_hp, cur_hp = 1, 0
    lost_frac = 1.0 - (float(cur_hp) / float(max_hp))
    try:
        pots = int(getattr(hero, "potions", 0) or 0)
    except (TypeError, ValueError):
        pots = 0

    injured = (hp < _MOMENT_LOW_HP and pots <= 1) or (lost_frac >= _MOMENT_LOSS_RECENT and hp < 0.90)
    if not injured:
        return None

    near = _nearest_enemy_tiles(hero, game_state)
    if near is not None and near <= _NEAR_ENEMY_POST_COMBAT_TILES and hp > _MOMENT_CRITICAL_HP:
        return None

    if not _recent_combat_memory(hero, now_ms) and not (hp < _MOMENT_LOW_HP and pots <= 1):
        return None

    return DecisionMoment(
        moment_type=DecisionMomentType.POST_COMBAT_INJURED,
        urgency=1,
        reason="wounded after combat; recovery choices",
        allowed_actions=("retreat", "move_to", "buy_item", "use_potion", "explore"),
        context_focus=("safety_places", "supplies", "recent_memory", "shops"),
        cooldown_ms=8_000,
    )


def moment_rested_and_ready(hero: Any) -> DecisionMoment | None:
    st = _hero_state(hero)
    hp = _health_fraction(hero)
    if hp < _MOMENT_RECOVERED_HP:
        return None
    if st == HeroState.RESTING:
        pass
    elif _inside_recovery_building(hero):
        pass
    else:
        return None

    return DecisionMoment(
        moment_type=DecisionMomentType.RESTED_AND_READY,
        urgency=0,
        reason="recovered in safety; choose next objective",
        allowed_actions=("leave_building", "explore", "move_to", "buy_item"),
        context_focus=("bounties", "known_places", "personality", "memory"),
        cooldown_ms=15_000,
    )


def moment_shopping_opportunity(hero: Any, game_state: dict) -> DecisionMoment | None:
    if _hero_state(hero) == HeroState.FIGHTING:
        return None
    try:
        gold = int(getattr(hero, "gold", 0) or 0)
    except (TypeError, ValueError):
        gold = 0
    if gold < _MOMENT_SHOP_GOLD_MIN:
        return None
    if not _near_marketplace(hero, game_state):
        return None
    if not _shopping_need(hero):
        return None

    return DecisionMoment(
        moment_type=DecisionMomentType.SHOPPING_OPPORTUNITY,
        urgency=0,
        reason="near marketplace with gold and a purchase need",
        allowed_actions=("buy_item", "leave_building", "move_to", "explore"),
        context_focus=("shop_items", "gold", "known_places"),
        cooldown_ms=12_000,
    )


def determine_decision_moment(hero: Any, game_state: dict, *, now_ms: int) -> DecisionMoment | None:
    """
    Return the highest-priority decision moment for this hero, or None.

    Ordering: low-health combat > post-combat injured > rested-and-ready > shopping.
    """
    m = moment_low_health_combat(hero)
    if m is not None:
        return m
    m = moment_post_combat_injured(hero, game_state, now_ms)
    if m is not None:
        return m
    m = moment_rested_and_ready(hero)
    if m is not None:
        return m
    return moment_shopping_opportunity(hero, game_state)


def consult_suppressed_by_request_state(hero: Any, now_ms: int, cooldown_ms: int) -> str | None:
    """Return a short reason string if an LLM consult should not start, else None."""
    try:
        last = int(getattr(hero, "last_llm_decision_time", 0) or 0)
    except (TypeError, ValueError):
        last = 0
    if now_ms - last < cooldown_ms:
        return "cooldown"
    if getattr(hero, "pending_llm_decision", False):
        return "pending_request"
    return None


def decision_moment_from_prompt_dict(data: Any) -> DecisionMoment | None:
    """Rebuild a DecisionMoment from ``DecisionMoment.to_prompt_dict()`` JSON."""
    if not isinstance(data, dict):
        return None
    raw_type = data.get("type")
    try:
        moment_type = DecisionMomentType(str(raw_type))
    except (TypeError, ValueError):
        return None
    allowed_raw = data.get("allowed_actions")
    if not isinstance(allowed_raw, list) or not allowed_raw:
        return None
    allowed = tuple(str(x).strip().lower() for x in allowed_raw if str(x).strip())
    if not allowed:
        return None
    focus_raw = data.get("context_focus") or ()
    if isinstance(focus_raw, list):
        context_focus = tuple(str(x) for x in focus_raw)
    elif isinstance(focus_raw, tuple):
        context_focus = tuple(str(x) for x in focus_raw)
    else:
        context_focus = ()
    try:
        urgency = int(data.get("urgency", 0))
    except (TypeError, ValueError):
        urgency = 0
    try:
        cooldown_ms = int(data.get("cooldown_ms", 0))
    except (TypeError, ValueError):
        cooldown_ms = 0
    reason = str(data.get("reason", "") or "")
    return DecisionMoment(
        moment_type=moment_type,
        urgency=urgency,
        reason=reason,
        allowed_actions=allowed,
        context_focus=context_focus,
        cooldown_ms=cooldown_ms,
    )
