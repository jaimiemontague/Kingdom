"""
Buff / aura system.

Minimal reusable hero buff model. The original Royal Gardens aura producer was
removed in WK114 Round B; the generic Buff infrastructure here is retained for
future aura sources, and BuffSystem.update still prunes expired hero buffs.
"""

from __future__ import annotations

from dataclasses import dataclass

from game.sim.timebase import now_ms as sim_now_ms
from game.systems.protocol import GameSystem, SystemContext


@dataclass
class Buff:
    name: str
    atk_delta: int = 0
    def_delta: int = 0
    expires_at_ms: int = 0  # pygame.time.get_ticks() timestamp

    def is_expired(self, now_ms: int) -> bool:
        return now_ms >= int(self.expires_at_ms)


class BuffSystem(GameSystem):
    """Applies/refreshes aura-style buffs and prunes expired buffs."""

    # Keep aura buffs short-lived so they naturally expire shortly after leaving range,
    # while still being refreshed each tick when inside the aura.
    AURA_REFRESH_SECONDS = 1.25

    def update(self, ctx: SystemContext, dt: float) -> None:
        _ = dt
        heroes = ctx.heroes
        now_ms = sim_now_ms()

        # Prune expired buffs to keep hero stats stable and avoid drift/stacking.
        # (The Royal Gardens aura — the only aura producer — was removed in WK114 Round B;
        # the generic Buff infrastructure below remains for future aura sources.)
        for hero in heroes:
            if not getattr(hero, "is_alive", True):
                continue
            if hasattr(hero, "remove_expired_buffs"):
                hero.remove_expired_buffs(now_ms)


