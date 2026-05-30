"""WK69 Round B-1 (W2): early-pacing-nudge service extracted from SimEngine (behavior-preserving move).

Takes the live SimEngine as ``sim`` and reads/writes its state exactly as the
former ``SimEngine._maybe_apply_early_pacing_nudge`` / ``_nearest_lair_to``
methods did. SimEngine keeps one-line delegating wrappers so callers/tests are
unchanged. The two move together because the nudge calls the nearest-lair helper.

This module must NOT import ``game.sim_engine`` at runtime (no import cycle): it
takes ``sim`` as a duck-typed parameter and only imports the same leaf helpers
the original methods used.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from config import LAIR_BOUNTY_COST
from game.types import BountyType

if TYPE_CHECKING:  # type-only; avoids a runtime import cycle with game.sim_engine
    from game.sim_engine import SimEngine


def maybe_apply_early_pacing_nudge(sim: "SimEngine", dt: float, castle) -> None:
    if not castle:
        return
    mode = getattr(sim, "_early_nudge_mode", "auto")
    if mode == "off":
        return
    if mode not in ("auto", "force"):
        mode = "auto"
    sim._early_nudge_elapsed_s += float(dt)

    unclaimed = sim.bounty_system.get_unclaimed_bounties()
    has_any_bounty = bool(unclaimed)
    tip_time_s = 0.0 if mode == "force" else 35.0
    starter_time_s = 0.0 if mode == "force" else 90.0

    if (not sim._early_nudge_tip_shown) and (sim._early_nudge_elapsed_s >= tip_time_s) and (not has_any_bounty):
        sim._early_nudge_tip_shown = True
        sim._emit_hud_message("Tip: Press B to place a bounty and guide heroes.", (220, 220, 255))
        sim._emit_hud_message("Try targeting a lair for big stash payouts.", (220, 220, 255))

    if sim._early_nudge_starter_bounty_done:
        return
    if sim._early_nudge_elapsed_s < starter_time_s:
        return
    if has_any_bounty:
        sim._early_nudge_starter_bounty_done = True
        return

    lair = sim._nearest_lair_to(float(castle.center_x), float(castle.center_y))
    if lair is None:
        sim._early_nudge_starter_bounty_done = True
        return

    reward = int(LAIR_BOUNTY_COST) if LAIR_BOUNTY_COST else 75
    if not sim.economy.add_bounty(reward):
        sim._early_nudge_starter_bounty_done = True
        sim._emit_hud_message("Tip: Earn more gold to place bounties that guide heroes.", (220, 220, 255))
        return

    bx = float(getattr(lair, "center_x", getattr(lair, "x", 0.0)))
    by = float(getattr(lair, "center_y", getattr(lair, "y", 0.0)))
    sim.bounty_system.place_bounty(bx, by, reward, BountyType.ATTACK_LAIR.value, target=lair)
    sim._early_nudge_starter_bounty_done = True
    sim._emit_hud_message(f"Starter bounty placed: Clear the lair (+${reward})", (255, 215, 0))


def nearest_lair_to(sim: "SimEngine", x: float, y: float):
    best = None
    best_d2 = None
    for b in sim.buildings:
        if not hasattr(b, "stash_gold"):
            continue
        bx = float(getattr(b, "center_x", getattr(b, "x", 0.0)))
        by = float(getattr(b, "center_y", getattr(b, "y", 0.0)))
        dx = bx - x
        dy = by - y
        d2 = dx * dx + dy * dy
        if best_d2 is None or d2 < best_d2:
            best = b
            best_d2 = d2
    return best
