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
    INITIAL_WAVE as _initial_cfg,
)
from game.entities.enemy import (
    Goblin,
    GoblinWarchief,
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
from game.systems.spawner import spawn_stagger_cap

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


def _jitter_around_anchor(rng, agx: int, agy: int, count: int,
                          jitter_tiles: int) -> list[tuple[float, float]]:
    """``count`` world positions in a +/- ``jitter_tiles`` box around a tile anchor.

    Shared core of both clustered placements: each enemy is the ``(agx, agy)`` tile
    anchor plus a small deterministic per-axis jitter (``rng.randint``), clamped to
    the playable interior, then converted to world coords. The RNG draw pattern (two
    ``randint`` per enemy when jitter > 0) is identical for the edge and the near
    variant — only the anchor differs.
    """
    j = max(0, int(jitter_tiles))
    out: list[tuple[float, float]] = []
    for _ in range(count):
        jx = rng.randint(-j, j) if j else 0
        jy = rng.randint(-j, j) if j else 0
        gx = max(1, min(MAP_WIDTH - 2, agx + jx))
        gy = max(1, min(MAP_HEIGHT - 2, agy + jy))
        out.append((gx * TILE_SIZE + TILE_SIZE // 2, gy * TILE_SIZE + TILE_SIZE // 2))
    return out


def _clustered_positions(rng, edge: str, count: int, jitter_tiles: int) -> list[tuple[float, float]]:
    """WK137 r2: ``count`` spawn positions tightly clustered around ONE edge anchor.

    One ``_edge_position`` anchor is drawn, then each enemy is jittered around it
    (+/- ``jitter_tiles``), so the whole wave arrives as a pack from the same edge and
    focus-fires the hero line — instead of the strung-out trickle a per-enemy edge
    draw produced (diagnosed at 222t initial spread, heroes mopped up at full HP).
    Used ONLY by the scripted initial wave's ``direction="clustered_edge"``; table
    waves never reach here, so their RNG draw order is untouched.
    """
    ax, ay = _edge_position(rng, edge)
    agx = int(round((ax - TILE_SIZE // 2) / TILE_SIZE))
    agy = int(round((ay - TILE_SIZE // 2) / TILE_SIZE))
    return _jitter_around_anchor(rng, agx, agy, count, jitter_tiles)


def _near_anchor_tile(rng, castle_gx: int, castle_gy: int,
                      dist_tiles: int) -> tuple[int, int]:
    """WK137 r3: a tile anchor ``dist_tiles`` from the castle along a random bearing.

    Draws ONE continuous bearing ``theta`` in [0, 2*pi) via ``rng.uniform`` (one RNG
    draw — continuous so the 10-seed matrix gets varied approach directions, not just
    4/8 compass picks), places the anchor at ``castle + dist*(cos, sin)``, then clamps
    the tile inside the playable interior leaving a 2-tile margin so the +/- jitter box
    still lands in-bounds. Spawning a short distance from the castle (instead of the map
    edge) makes the pack engage while heroes are still level 1 — the regime the plan's
    balance math assumed.
    """
    theta = rng.uniform(0.0, 2.0 * math.pi)
    d = max(1, int(dist_tiles))
    agx = int(round(castle_gx + d * math.cos(theta)))
    agy = int(round(castle_gy + d * math.sin(theta)))
    agx = max(2, min(MAP_WIDTH - 3, agx))
    agy = max(2, min(MAP_HEIGHT - 3, agy))
    return agx, agy


def _castle_center_tile(ctx) -> tuple[int, int]:
    """Locate the castle centre as a tile coordinate (mirrors the spawner lookup).

    Prefers ``ctx.castle`` (already resolved by the sim's context builder), falls back
    to scanning ``ctx.buildings`` for a ``building_type == "castle"``, and finally to
    the map centre if no castle exists (matches ``EnemySpawner._get_first_wave_spawn_position``).
    """
    castle = getattr(ctx, "castle", None)
    if castle is None:
        castle = next(
            (b for b in getattr(ctx, "buildings", []) or []
             if getattr(b, "building_type", None) == "castle"),
            None,
        )
    if castle is not None:
        cx = getattr(castle, "center_x", None)
        cy = getattr(castle, "center_y", None)
        if cx is not None and cy is not None:
            return (int(round(cx / TILE_SIZE)), int(round(cy / TILE_SIZE)))
    return (MAP_WIDTH // 2, MAP_HEIGHT // 2)


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
        # WK128: stagger wave bursts — queued (enemy_cls, wx, wy) plans released a
        # few constructions per tick (cap 0 = legacy single-tick burst).
        self.stagger_cap: int = spawn_stagger_cap()
        self._pending_spawns: list[tuple] = []
        # WK137: scripted initial assault (fires once, before the scheduled table).
        self._initial_wave_done: bool = False
        self._initial_warning_emitted: bool = False

    # ------------------------------------------------------------------
    # Protocol
    # ------------------------------------------------------------------

    def update(self, ctx: SystemContext, dt: float) -> None:
        self.elapsed_sec += dt
        elapsed_min = self.elapsed_sec / 60.0

        # WK128: release queued wave spawns a few per tick.
        if self._pending_spawns:
            self._drain_pending_spawns(ctx)

        # WK137: one-shot scripted initial assault (independent of the WK60 table).
        self._update_initial_wave(ctx)

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

        # Check for wave clear (not while staggered spawns are still queued)
        if self._active_wave_def is not None and not self._wave_clear_checked and not self._pending_spawns:
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

    def _update_initial_wave(self, ctx: SystemContext) -> None:
        """WK137: one-shot scripted wave at INITIAL_WAVE.trigger_sec (sim-seconds).

        Digest guard: before the warning moment this does float compares only —
        no RNG draws, no state writes (WK67 window is ticks 0-300 = 5 sim-sec;
        warning fires at trigger-10s=20s, spawn at 30s, both outside it).
        """
        if self._initial_wave_done or not _initial_cfg.enabled:
            return
        trigger = _initial_cfg.trigger_sec
        if (not self._initial_warning_emitted
                and self.elapsed_sec >= trigger - _wave_cfg.warning_seconds):
            self._initial_warning_emitted = True
            ctx.event_bus.emit({
                "type": "wave_incoming",
                "name": _initial_cfg.name,
                "seconds": _wave_cfg.warning_seconds,
            })
        if self.elapsed_sec >= trigger and self._active_wave_def is None:
            event_def = WaveEventDef(
                name=_initial_cfg.name,
                minute=trigger / 60.0,
                composition=[(Goblin, _initial_cfg.goblin_count), (GoblinWarchief, 1)],
                direction="clustered_near",
                reward_gold=_initial_cfg.reward_gold,
            )
            self._spawn_wave(event_def, ctx, advance_table=False)
            self._initial_wave_done = True
            ctx.event_bus.emit({
                "type": "hud_message",
                "text": "The Goblin Warchief leads the assault!",
                "color": (255, 80, 80),
            })

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

    def _drain_pending_spawns(self, ctx: SystemContext) -> None:
        """WK128: construct and register at most ``stagger_cap`` queued enemies."""
        cap = self.stagger_cap
        batch = self._pending_spawns if cap <= 0 else self._pending_spawns[:cap]
        self._pending_spawns = [] if cap <= 0 else self._pending_spawns[cap:]
        for enemy_cls, wx, wy in batch:
            enemy = enemy_cls(wx, wy)
            # Apply difficulty HP/damage multipliers to newly spawned wave enemies
            # WK72: scaling consolidated into DifficultySystem.apply_to_enemy
            if self.difficulty is not None:
                self.difficulty.apply_to_enemy(enemy)
            ctx.enemies.append(enemy)
            self._active_wave_enemies.append(enemy)

    def _spawn_wave(self, event_def: WaveEventDef, ctx: SystemContext, *, advance_table: bool = True) -> None:
        """Plan and register enemies for a wave event (construction staggered)."""
        self._active_wave_def = event_def
        self._wave_clear_checked = False

        # Difficulty multiplier on enemy counts
        count_mult = 1.0
        if self.difficulty is not None:
            count_mult = self.difficulty.get_multiplier("wave_event_count")

        # Determine spawn positions based on direction
        edges = ["top", "bottom", "left", "right"]
        plan: list[tuple] = []
        if event_def.direction == "clustered_near":
            # WK137 r3: scripted-initial-wave-only path — the cluster spawns a short
            # DISTANCE (spawn_dist_tiles) from the castle along a random bearing, then
            # jitters each enemy around that near-anchor. This makes the pack engage
            # the hero line ~35-40 s in, while heroes are still level 1 (the regime the
            # plan's balance math assumed) instead of after a ~30 s edge-to-town march
            # that lets rangers level up to 140-160 hp. Separate branch so the
            # random_edge/all_edges RNG draw order below is byte-identical for table
            # waves. RNG draw order here: ONE uniform (bearing) then two randint per
            # enemy (the cluster jitter).
            castle_gx, castle_gy = _castle_center_tile(ctx)
            agx, agy = _near_anchor_tile(
                self.rng, castle_gx, castle_gy, _initial_cfg.spawn_dist_tiles)
            total = sum(max(1, int(round(bc * count_mult)))
                        for _, bc in event_def.composition)
            cluster = _jitter_around_anchor(
                self.rng, agx, agy, total, _initial_cfg.cluster_jitter_tiles)
            idx = 0
            for enemy_cls, base_count in event_def.composition:
                adjusted_count = max(1, int(round(base_count * count_mult)))
                for _ in range(adjusted_count):
                    wx, wy = cluster[idx]
                    idx += 1
                    plan.append((enemy_cls, wx, wy))
        elif event_def.direction == "clustered_edge":
            # WK137 r2: scripted-initial-wave-only path — ONE edge anchor, all enemies
            # jittered tightly around it so the wave engages as a pack. Separate branch
            # so the random_edge/all_edges RNG draw order below is byte-identical.
            chosen_edge = self.rng.choice(edges)
            total = sum(max(1, int(round(bc * count_mult)))
                        for _, bc in event_def.composition)
            cluster = _clustered_positions(
                self.rng, chosen_edge, total, _initial_cfg.cluster_jitter_tiles)
            idx = 0
            for enemy_cls, base_count in event_def.composition:
                adjusted_count = max(1, int(round(base_count * count_mult)))
                for _ in range(adjusted_count):
                    wx, wy = cluster[idx]
                    idx += 1
                    plan.append((enemy_cls, wx, wy))
        else:
            if event_def.direction == "random_edge":
                chosen_edge = self.rng.choice(edges)
                spawn_edges = [chosen_edge]
            elif event_def.direction == "all_edges":
                spawn_edges = list(edges)
            else:
                # nearest_lair fallback to random_edge
                spawn_edges = [self.rng.choice(edges)]

            # WK128: plan the full wave now (RNG draws in legacy order so positions and
            # composition are identical to the single-tick burst); construct staggered.
            for enemy_cls, base_count in event_def.composition:
                adjusted_count = max(1, int(round(base_count * count_mult)))
                for i in range(adjusted_count):
                    edge = spawn_edges[i % len(spawn_edges)]
                    wx, wy = _edge_position(self.rng, edge)
                    plan.append((enemy_cls, wx, wy))

        # Add to shared enemy list (wave events can exceed normal cap by overflow factor).
        # WK61-R11: reserve slots so themed compositions (e.g. Wolf Pack) are not dropped.
        wave_cap = int(MAX_ALIVE_ENEMIES * _wave_cfg.max_enemy_cap_overflow)
        needed = len(plan)
        self._reserve_wave_spawn_slots(ctx, needed, wave_cap)
        alive_count = len([e for e in ctx.enemies if getattr(e, "is_alive", False)])
        remaining = max(0, wave_cap - alive_count)
        if remaining < len(plan):
            plan = plan[:remaining]

        self._active_wave_enemies = []
        self._active_wave_reward = event_def.reward_gold
        self._pending_spawns.extend(plan)
        # Release the first batch on the fire tick (all of it in burst mode).
        self._drain_pending_spawns(ctx)

        if advance_table:
            # Advance index for next wave
            self._next_table_index += 1
            self._warning_emitted = False

        # Emit HUD toast
        ctx.event_bus.emit({
            "type": "hud_message",
            "text": f"INCOMING: {event_def.name}!",
            "color": (255, 100, 100),
        })
