"""
Buff / aura system.

Agent 3: minimal reusable hero buff model + a first aura (Royal Gardens).
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass
class Buff:
    name: str
    atk_delta: int = 0
    def_delta: int = 0
    expires_at_ms: int = 0  # pygame.time.get_ticks() timestamp

    def is_expired(self, now_ms: int) -> bool:
        return now_ms >= int(self.expires_at_ms)


class BuffSystem:
    """Applies/refreshes aura-style buffs and prunes expired buffs."""

    # Keep aura buffs short-lived so they naturally expire shortly after leaving range,
    # while still being refreshed each tick when inside the aura.
    AURA_REFRESH_SECONDS = 1.25

    def update(self, heroes: list, buildings: list):
        now_ms = pygame.time.get_ticks()

        # Prune expired buffs first to keep hero stats stable and avoid drift/stacking.
        for hero in heroes:
            if not getattr(hero, "is_alive", True):
                continue
            if hasattr(hero, "remove_expired_buffs"):
                hero.remove_expired_buffs(now_ms)

        # Apply auras.
        for building in buildings:
            if getattr(building, "building_type", None) != "royal_gardens":
                continue

            atk = int(getattr(building, "buff_attack_bonus", 0))
            df = int(getattr(building, "buff_defense_bonus", 0))
            duration_s = float(getattr(building, "buff_duration", self.AURA_REFRESH_SECONDS))
            duration_s = min(duration_s, self.AURA_REFRESH_SECONDS)

            if not hasattr(building, "get_heroes_in_range"):
                continue

            for hero in building.get_heroes_in_range(heroes):
                if hasattr(hero, "apply_or_refresh_buff"):
                    hero.apply_or_refresh_buff(
                        name="royal_gardens_aura",
                        atk_delta=atk,
                        def_delta=df,
                        duration_s=duration_s,
                        now_ms=now_ms,
                    )


