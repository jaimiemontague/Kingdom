"""Cleric support behavior (WK124-T4b).

The cleric (``hero_class == "cleric"``) seeks out and moves to support a friendly
hero who is **wounded** or **in combat**, so she can heal them (the heal itself is
applied by ``game/systems/cleric_heal.py``, Agent 05's deterministic system —
this module only steers the cleric toward an ally that needs help).

Modeled on ``ai/behaviors/defense.py::defend_home_building`` (same
``_commit_until_ms`` anti-thrash pattern, same ``set_target_position`` +
``state = MOVING`` move-toward shape).

DIGEST SAFETY (WK67 keystone): ``cleric_seek_and_support`` is a **pure read** when
no ally needs support — it makes ZERO state changes and returns ``False`` so the
cleric falls through to her existing default behavior. In the 300-tick WK67 digest
scenario nobody is wounded and there is no combat, so this always returns ``False``
with no mutation → Cora's decisions are byte-identical → digest unchanged. Wire it
ONLY as a ``hero_class == "cleric"``-gated branch so no other class is affected.
"""

from __future__ import annotations

from typing import Any

from config import CLERIC_HEAL_MIN_TARGET_PCT
from game.entities.hero import HeroState
from game.sim.hero_guardrails_tunables import TARGET_COMMIT_WINDOW_S
from game.sim.timebase import now_ms as sim_now_ms

from ai.behaviors.view_compat import as_ai_view


def _commit_until_ms(now_ms: int) -> int:
    """Anti-oscillation commit deadline (sim-time ms), matching defense.py."""
    return int(now_ms + int(float(TARGET_COMMIT_WINDOW_S) * 1000.0))


def _ally_needs_support(cleric: Any, ally: Any) -> bool:
    """True iff ``ally`` is a distinct, living friendly hero that is wounded
    (``health_percent < CLERIC_HEAL_MIN_TARGET_PCT``) OR in combat
    (``state == HeroState.FIGHTING``). Pure read — no side effects."""
    if ally is cleric:
        return False
    if not getattr(ally, "is_alive", False):
        return False
    try:
        wounded = float(ally.health_percent) < float(CLERIC_HEAL_MIN_TARGET_PCT)
    except Exception:
        wounded = False
    in_combat = getattr(ally, "state", None) == HeroState.FIGHTING
    return bool(wounded or in_combat)


def cleric_seek_and_support(ai: Any, hero: Any, view: Any) -> bool:
    """Move the cleric toward the nearest ally that needs support.

    Returns ``True`` (and steers the cleric: ``set_target_position`` +
    ``state = MOVING``, with an anti-thrash commit window) iff there is a friendly
    hero in ``view.heroes`` that is wounded or fighting. Returns ``False`` AND
    makes NO state change when no ally needs support — the cleric then keeps her
    existing default behavior (this no-op-when-idle property is what keeps Cora
    inert in the WK67 digest scenario).
    """
    view = as_ai_view(view)

    # WK2 anti-oscillation: if already committed to a valid combat target, don't
    # thrash (mirror defense.py). Only honored for live entity targets.
    now_ms = int(sim_now_ms())
    if now_ms < int(getattr(hero, "_target_commit_until_ms", 0) or 0):
        cur = getattr(hero, "target", None)
        if cur is not None and hasattr(cur, "is_alive") and getattr(cur, "is_alive", False):
            return True

    # Find the nearest ally that is wounded or in combat (pure scan, no mutation).
    nearest_ally = None
    nearest_dist = float("inf")
    for ally in view.heroes:
        if not _ally_needs_support(hero, ally):
            continue
        dist = hero.distance_to(ally.x, ally.y)
        if dist < nearest_dist:
            nearest_dist = dist
            nearest_ally = ally

    # No ally needs support: pure read, NO state change, fall through to default.
    if nearest_ally is None:
        return False

    # Steer the cleric toward the ally (move-toward, like defend_home_building).
    hero.set_target_position(nearest_ally.x, nearest_ally.y)
    hero.state = HeroState.MOVING
    hero.target = {"type": "support_ally"}
    hero._target_commit_until_ms = _commit_until_ms(now_ms)
    ai._debug_log(f"{hero.name} -> supporting wounded/fighting ally at {nearest_dist:.0f}px")
    return True
