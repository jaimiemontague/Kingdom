"""
WK60 Feature 1: Wave Events System (Make It Fun).

Fires named siege events on a timer, layered on top of the existing trickle spawner.
Every N minutes a themed burst of enemies spawns from a map edge with a pre-warning
emitted via EventBus so the HUD (Agent 08, R2) can show a toast.

Integration:
    - ``WaveEventSystem`` follows the ``GameSystem`` protocol (update(ctx, dt)).
    - Emits ``wave_incoming`` (10 s before) and ``wave_cleared`` events on the EventBus.
    - Reads difficulty multipliers from a shared ``DifficultySystem`` instance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from config import (
    MAP_WIDTH,
    MAP_HEIGHT,
    MAX_ALIVE_ENEMIES,
    TILE_SIZE,
    WAVE_EVENT as _wave_cfg,
)
from game.entities.enemy import (
    Goblin,
    Wolf,
    Skeleton,
    SkeletonArcher,
    Spider,
    Bandit,
    BanditLord,
    DemonOverlord,
)
from game.sim.determinism import get_rng
from game.systems.protocol import GameSystem, SystemContext

if TYPE_CHECKING:
    from game.systems.difficulty import DifficultySystem


# ---------------------------------------------------------------------------
# Wave event table
# ---------------------------------------------------------------------------

@dataclass
class WaveEventDef:
    """Static definition of a single wave event."""
    name: str
    minute: float
    composition: list[tuple[type, int]]  # (EnemyClass, count) pairs
    direction: str  # "random_edge" | "nearest_lair" | "all_edges"
    reward_gold: int = 50


# Starting wave table (values from the plan -- will be tuned in Phase 2)
_WAVE_TABLE: list[WaveEventDef] = [
    WaveEventDef("Goblin Raid",       3.0,  [(Goblin, 8)],                              "random_edge",  40),
    WaveEventDef("Wolf Pack",         5.5,  [(Wolf, 6), (Goblin, 4)],                   "random_edge",  55),
    WaveEventDef("Skeleton Patrol",   8.0,  [(Skeleton, 6), (SkeletonArcher, 4)],       "random_edge",  70),
    WaveEventDef("Spider Swarm",     11.0,  [(Spider, 12), (Goblin, 4)],                 "random_edge",  60),
    WaveEventDef("Bandit Ambush",    14.0,  [(Bandit, 6), (SkeletonArcher, 4)],         "random_edge",  80),
    WaveEventDef("Goblin Horde",     17.0,  [(Goblin, 16), (Wolf, 4)],                   "all_edges",   100),
    WaveEventDef("Boss Wave",        20.0,  [(BanditLord, 2), (Bandit, 8)],             "random_edge", 150),
    WaveEventDef("Demon Siege",      25.0,  [(DemonOverlord, 1), (Skeleton, 6)],        "all_edges",   250),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edge_position(rng, edge: str) -> tuple[float, float]:
    """Return a world-coordinate spawn position on the given map edge."""
    if edge == "top":
        gx = rng.randint(2, MAP_WIDTH - 3)
        gy = 1
    elif edge == "bottom":
        gx = rng.randint(2, MAP_WIDTH - 3)
        gy = MAP_HEIGHT - 2
    elif edge == "left":
        gx = 1
        gy = rng.randint(2, MAP_HEIGHT - 3)
    else:  # right
        gx = MAP_WIDTH - 2
        gy = rng.randint(2, MAP_HEIGHT - 3)
    return (gx * TILE_SIZE + TILE_SIZE // 2, gy * TILE_SIZE + TILE_SIZE // 2)


# ---------------------------------------------------------------------------
# WaveEventSystem
# ---------------------------------------------------------------------------

class WaveEventSystem(GameSystem):
    """
    Fires scheduled wave events and manages the warning -> spawn -> clear lifecycle.
    """

    def __init__(self, difficulty: "DifficultySystem | None" = None):
        self.difficulty = difficulty
        self.rng = get_rng("wave_events")
        self.elapsed_sec: float = 0.0
        self._next_table_index: int = 0
        self._cycle_count: int = 0  # how many times the table has cycled
        self._warning_emitted: bool = False
        self._active_wave_enemies: list = []
        self._active_wave_def: WaveEventDef | None = None
        self._active_wave_reward: int = 0
        self._wave_clear_checked: bool = False

    # ------------------------------------------------------------------
    # Protocol
    # ------------------------------------------------------------------

    def update(self, ctx: SystemContext, dt: float) -> None:
        self.elapsed_sec += dt
        elapsed_min = self.elapsed_sec / 60.0

        event_def = self._current_event_def()
        if event_def is None:
            # All events exhausted and not cycling? Shouldn't happen but be safe.
            return

        target_minute = event_def.minute
        warning_before = _wave_cfg.warning_seconds / 60.0  # 10 s in minutes

        # Emit warning
        if not self._warning_emitted and elapsed_min >= (target_minute - warning_before):
            self._warning_emitted = True
            ctx.event_bus.emit({
                "type": "wave_incoming",
                "name": event_def.name,
                "seconds": _wave_cfg.warning_seconds,
            })

        # Spawn the wave
        if elapsed_min >= target_minute and self._active_wave_def is None:
            self._spawn_wave(event_def, ctx)

        # Check for wave clear
        if self._active_wave_def is not None and not self._wave_clear_checked:
            alive = [e for e in self._active_wave_enemies if getattr(e, "is_alive", False)]
            if len(alive) == 0:
                self._wave_clear_checked = True
                reward = self._active_wave_reward
                # Deposit gold to player treasury
                if hasattr(ctx.economy, "player_gold"):
                    ctx.economy.player_gold += reward
                ctx.event_bus.emit({
                    "type": "wave_cleared",
                    "name": self._active_wave_def.name,
                    "reward": reward,
                })
                ctx.event_bus.emit({
                    "type": "hud_message",
                    "text": f"Wave Cleared! +{reward} Gold",
                    "color": (255, 215, 0),
                })
                # Reset for next wave
                self._active_wave_def = None
                self._active_wave_enemies = []
                self._active_wave_reward = 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _current_event_def(self) -> WaveEventDef | None:
        """Return the next wave event definition, cycling with escalation after the table ends."""
        if self._next_table_index < len(_WAVE_TABLE):
            base = _WAVE_TABLE[self._next_table_index]
            minute = _wave_cfg.first_event_minute + self._next_table_index * _wave_cfg.interval_minutes
            return WaveEventDef(
                name=base.name,
                minute=minute,
                composition=base.composition,
                direction=base.direction,
                reward_gold=base.reward_gold,
            )
        # Cycle: replay the table with increasing count multipliers
        cycle_idx = (self._next_table_index - len(_WAVE_TABLE)) % len(_WAVE_TABLE)
        base = _WAVE_TABLE[cycle_idx]
        # Each full cycle adds +0.5x to enemy counts
        cycle_num = 1 + (self._next_table_index - len(_WAVE_TABLE)) // len(_WAVE_TABLE)
        count_mult = 1.0 + cycle_num * 0.5
        # Compute the minute for this cycling event
        last_minute = _wave_cfg.first_event_minute + (len(_WAVE_TABLE) - 1) * _wave_cfg.interval_minutes
        extra_minutes = (self._next_table_index - len(_WAVE_TABLE) + 1) * _wave_cfg.interval_minutes
        new_minute = last_minute + extra_minutes
        new_comp = [(cls, max(1, int(round(count * count_mult)))) for cls, count in base.composition]
        return WaveEventDef(
            name=base.name,
            minute=new_minute,
            composition=new_comp,
            direction=base.direction,
            reward_gold=int(base.reward_gold * (1.0 + cycle_num * 0.25)),
        )

    def _reserve_wave_spawn_slots(self, ctx: SystemContext, needed: int, wave_cap: int) -> None:
        """Free enemy slots deterministically so wave spawns are not truncated to zero."""
        if needed <= 0:
            return
        alive_count = len([e for e in ctx.enemies if getattr(e, "is_alive", False)])
        room = max(0, wave_cap - alive_count)
        if room >= needed:
            return
        slots_to_free = needed - room
        freed = 0
        trimmed: list = []
        for enemy in ctx.enemies:
            if freed < slots_to_free and getattr(enemy, "is_alive", False):
                freed += 1
                continue
            trimmed.append(enemy)
        ctx.enemies[:] = trimmed

    def _spawn_wave(self, event_def: WaveEventDef, ctx: SystemContext) -> None:
        """Instantiate and register enemies for a wave event."""
        self._active_wave_def = event_def
        self._wave_clear_checked = False
        spawned: list = []

        # Difficulty multiplier on enemy counts
        count_mult = 1.0
        if self.difficulty is not None:
            count_mult = self.difficulty.get_multiplier("wave_event_count")

        # Difficulty multipliers for enemy stats
        hp_mult = 1.0
        dmg_mult = 1.0
        if self.difficulty is not None:
            hp_mult = self.difficulty.get_multiplier("enemy_hp")
            dmg_mult = self.difficulty.get_multiplier("enemy_damage")

        # Determine spawn positions based on direction
        edges = ["top", "bottom", "left", "right"]
        if event_def.direction == "random_edge":
            chosen_edge = self.rng.choice(edges)
            spawn_edges = [chosen_edge]
        elif event_def.direction == "all_edges":
            spawn_edges = list(edges)
        else:
            # nearest_lair fallback to random_edge
            spawn_edges = [self.rng.choice(edges)]

        for enemy_cls, base_count in event_def.composition:
            adjusted_count = max(1, int(round(base_count * count_mult)))
            for i in range(adjusted_count):
                edge = spawn_edges[i % len(spawn_edges)]
                wx, wy = _edge_position(self.rng, edge)
                enemy = enemy_cls(wx, wy)
                # Apply difficulty HP/damage multipliers to newly spawned wave enemies
                if hp_mult != 1.0:
                    enemy.max_hp = max(1, int(round(enemy.max_hp * hp_mult)))
                    enemy.hp = enemy.max_hp
                if dmg_mult != 1.0:
                    enemy.attack_power = max(1, int(round(enemy.attack_power * dmg_mult)))
                spawned.append(enemy)

        # Add to shared enemy list (wave events can exceed normal cap by overflow factor).
        # WK61-R11: reserve slots so themed compositions (e.g. Wolf Pack) are not dropped.
        wave_cap = int(MAX_ALIVE_ENEMIES * _wave_cfg.max_enemy_cap_overflow)
        needed = len(spawned)
        self._reserve_wave_spawn_slots(ctx, needed, wave_cap)
        alive_count = len([e for e in ctx.enemies if getattr(e, "is_alive", False)])
        remaining = max(0, wave_cap - alive_count)
        added = spawned[:remaining] if remaining < len(spawned) else spawned
        ctx.enemies.extend(added)

        self._active_wave_enemies = list(added)
        self._active_wave_reward = event_def.reward_gold

        # Advance index for next wave
        self._next_table_index += 1
        self._warning_emitted = False

        # Emit HUD toast
        ctx.event_bus.emit({
            "type": "hud_message",
            "text": f"INCOMING: {event_def.name}!",
            "color": (255, 100, 100),
        })
