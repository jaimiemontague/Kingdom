"""
Cleric heal system (WK124-T4a).

Each tick, every alive cleric off cooldown heals the nearest WOUNDED allied hero
within ``CLERIC_HEAL_RADIUS_TILES`` and emits a ``HERO_HEAL`` event for VFX/audio.
If no ally is wounded, the system is a NO-OP (no state change) — this is what
keeps it inert in the WK67 AI-decision digest scenario (warrior/ranger/cleric
near the castle, no enemies, all full-HP).

Determinism: timing comes from ``game.sim.timebase.now_ms`` (sim clock), never
``time.time()``; there is NO randomness. Target selection breaks ties with a
stable key ``(round(dist, 3), ally.hero_id)`` so two equidistant allies always
resolve to the same hero across runs.

Modeled on ``CombatSystem._run_combat`` (game/systems/combat.py) and the
``GameSystem`` / ``SystemContext`` interface shared by the other tick systems
(game/systems/buffs.py, combat.py).
"""

from __future__ import annotations

from collections.abc import Callable

from config import (
    TILE_SIZE,
    CLERIC_HEAL_RADIUS_TILES,
    CLERIC_HEAL_AMOUNT,
    CLERIC_HEAL_COOLDOWN_MS,
    CLERIC_HEAL_MIN_TARGET_PCT,
)
from game.events import GameEventType
from game.sim.timebase import now_ms as sim_now_ms
from game.systems.protocol import GameSystem, SystemContext


class ClericHealSystem(GameSystem):
    """Heals wounded allied heroes for each cleric, off a per-cleric cooldown."""

    def update(self, ctx: SystemContext, dt: float) -> None:
        _ = dt
        heroes = ctx.heroes
        if not heroes:
            return

        def emit(event: dict) -> None:
            if ctx.event_bus is not None:
                ctx.event_bus.emit(event)

        self._run_heals(heroes, emit)

    def _run_heals(self, heroes: list, emit_event: Callable[[dict], None]) -> None:
        now = int(sim_now_ms())
        heal_radius = float(CLERIC_HEAL_RADIUS_TILES) * TILE_SIZE

        for cleric in heroes:
            if getattr(cleric, "hero_class", None) != "cleric":
                continue
            if not getattr(cleric, "is_alive", False):
                continue
            if int(getattr(cleric, "_heal_cooldown_until_ms", 0)) > now:
                continue

            # Find the nearest wounded allied hero in range (stable tiebreak).
            best = None
            best_key = None
            for ally in heroes:
                if ally is cleric:
                    continue
                if not getattr(ally, "is_alive", False):
                    continue
                if float(getattr(ally, "health_percent", 1.0)) >= float(CLERIC_HEAL_MIN_TARGET_PCT):
                    continue
                dist = cleric.distance_to(ally.x, ally.y)
                if dist > heal_radius:
                    continue
                key = (round(dist, 3), str(getattr(ally, "hero_id", "")))
                if best_key is None or key < best_key:
                    best_key = key
                    best = ally

            # No wounded ally in range -> no state change (keeps the digest inert).
            if best is None:
                continue

            best.heal(int(CLERIC_HEAL_AMOUNT))
            cleric._heal_cooldown_until_ms = now + int(CLERIC_HEAL_COOLDOWN_MS)
            emit_event(
                {
                    "type": GameEventType.HERO_HEAL.value,
                    "x": best.x,
                    "y": best.y,
                    "from_x": cleric.x,
                    "from_y": cleric.y,
                    "amount": int(CLERIC_HEAL_AMOUNT),
                }
            )
