"""
WK50 R11 / R15: Sovereign direct-prompt movement commit (sim-side).

Accepted chat commands that resolve to physical movement set a ``hero.target``
of type ``direct_prompt`` so routine AI (bounty pursuit, idle explore) cannot
overwrite the sovereign goal. R15: commitment persists for the whole journey,
not a short sim-time TTL, until arrival or overrides (castle defense, prolonged
pathing stall).
"""

from __future__ import annotations

from typing import Any

from game.entities.hero import HeroState
from game.sim.timebase import now_ms as sim_now_ms

DIRECT_PROMPT_TARGET_TYPE = "direct_prompt"

# Orphan-target cleanup only (non-MOVING): stale dict left without active routing.
DIRECT_PROMPT_COMMIT_TTL_MS = 120_000

# If pathing detects stuck continuously for this long, drop commit to avoid soft-lock.
DIRECT_PROMPT_STUCK_ABORT_MS = 90_000


def _abort_direct_prompt_routing(hero: Any) -> None:
    """Clear sovereign routing metadata (same outward effect as legacy TTL expiry)."""
    hero.target = None
    if hero.state == HeroState.MOVING:
        hero.target_position = None
        hero.state = HeroState.IDLE


def attach_direct_prompt_move(
    hero: Any,
    *,
    sub_intent: str,
    wx: float,
    wy: float,
    now_ms: int | None = None,
) -> None:
    """Mark a sovereign movement commitment and apply coordinates immediately."""
    t = int(now_ms) if now_ms is not None else int(sim_now_ms())
    hero.target = {
        "type": DIRECT_PROMPT_TARGET_TYPE,
        "sub_intent": str(sub_intent or "go_to_known_place"),
        "started_ms": t,
    }
    hero.set_target_position(float(wx), float(wy))


def clear_direct_prompt_commit(hero: Any) -> None:
    """Drop sovereign movement metadata (does not alter position or path)."""
    target = getattr(hero, "target", None)
    if isinstance(target, dict) and target.get("type") == DIRECT_PROMPT_TARGET_TYPE:
        hero.target = None


def expire_direct_prompt_commit_if_timed_out(
    hero: Any, *, ttl_ms: int = DIRECT_PROMPT_COMMIT_TTL_MS
) -> None:
    """
    Bound sovereign commits without cutting short long trips.

    - While MOVING toward a set ``target_position``, do not TTL-expire; arrival
      handlers drop the dict.
    - If ``stuck_active`` persists past ``DIRECT_PROMPT_STUCK_ABORT_MS``, clear
      routing (escape hatch for failed paths).
    - For inconsistent IDLE/orphan targets, TTL still trims stale metadata.
    """
    target = getattr(hero, "target", None)
    if not isinstance(target, dict) or target.get("type") != DIRECT_PROMPT_TARGET_TYPE:
        return

    tp = getattr(hero, "target_position", None)
    if hero.state == HeroState.MOVING and tp is not None:
        if getattr(hero, "stuck_active", False):
            since = getattr(hero, "stuck_since_ms", None)
            if since is not None:
                dwell = int(sim_now_ms()) - int(since)
                if dwell >= int(DIRECT_PROMPT_STUCK_ABORT_MS):
                    _abort_direct_prompt_routing(hero)
        return

    started = int(target.get("started_ms", 0) or 0)
    if int(sim_now_ms()) - started <= int(ttl_ms):
        return
    _abort_direct_prompt_routing(hero)
