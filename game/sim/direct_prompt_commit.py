"""
WK50 R11: Sovereign direct-prompt movement commit (sim-side).

Accepted chat commands that resolve to physical movement set a short-lived
``hero.target`` of type ``direct_prompt`` so routine AI (bounty pursuit, idle
explore) does not keep stale ``target`` dicts that override the sovereign goal.
"""

from __future__ import annotations

from typing import Any

from game.sim.timebase import now_ms as sim_now_ms

DIRECT_PROMPT_TARGET_TYPE = "direct_prompt"

# Hard cap (sim ms): sovereign orders should not pin routing forever if stuck.
DIRECT_PROMPT_COMMIT_TTL_MS = 120_000


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
    """Clear expired sovereign commits and stop orphan MOVING state."""
    from game.entities.hero import HeroState

    target = getattr(hero, "target", None)
    if not isinstance(target, dict) or target.get("type") != DIRECT_PROMPT_TARGET_TYPE:
        return
    started = int(target.get("started_ms", 0) or 0)
    if int(sim_now_ms()) - started <= int(ttl_ms):
        return
    hero.target = None
    if hero.state == HeroState.MOVING:
        hero.target_position = None
        hero.state = HeroState.IDLE
