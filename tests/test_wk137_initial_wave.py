"""WK137 T1 — scripted initial goblin wave + Goblin Warchief boss.

Sprint: wk137_initial_goblin_wave
Round:  r1 (r2: clustered-spawn structural fix; r3: clustered_near spawn-distance)
Owner:  Agent 05 (GameplaySystemsDesigner)

Covers:
  1. Warchief stat spec-math + constructed instance attrs.
  2. Timing — no events before 20s; wave_incoming "Goblin Warband" at ~20s;
     enemies at ~30s (past the WK128 stagger drain).
  3. Composition (NORMAL) — exactly INITIAL_WAVE.goblin_count goblins + 1 warchief.
  3b. Clustered spawn (r3) — every initial-wave enemy lands within a few tiles of a
      single NEAR-CASTLE anchor (direction="clustered_near"): the anchor sits
      spawn_dist_tiles from the castle centre and every enemy is inside the playable
      interior. (r2 spawned at the map edge; r3 spawns near the castle so the wave
      engages level-1 heroes — see the r3 balance log.)
  3c. Anchor distance — the cluster centroid lands within
      [spawn_dist_tiles - jitter - 1, spawn_dist_tiles + jitter + 1] tiles of the castle.
  3d. Table waves are NOT near-castle-clustered — a "Goblin Horde" all_edges table
      wave spreads across the map (proving table directions are untouched).
  4. One-shot — nothing again by 60s.
  5. Table UNSHIFTED — _next_table_index == 0 after the initial wave; the
     "Goblin Raid" table wave still arrives at ~120s.
  6. Kill-switch — enabled=False (module-attr patch of the config object).
  7. Difficulty counts — EASY 6 goblins/1 warchief, HARD 15 goblins/2 warchiefs.

Harness mirrors tests/test_wk61_r11_wolf_pack_spawn.py (stub SystemContext with an
event-collecting EventBus); module-attr monkeypatch of the config object mirrors the
spawner_module.Goblin patch style in tests/test_spawner.py.
"""

from __future__ import annotations

from types import SimpleNamespace

from config import INITIAL_WAVE, InitialWaveConfig, WAVE_EVENT
from game.entities.enemy import ENEMY_STATS, Goblin, GoblinWarchief
from game.events import EventBus
from game.sim.determinism import set_sim_seed
from game.systems.difficulty import DifficultySystem, DifficultyLevel
from game.systems.protocol import SystemContext
from game.systems.wave_events import WaveEventSystem
import game.systems.wave_events as wave_events_module


def _make_ctx(enemies: list | None = None) -> SystemContext:
    return SystemContext(
        heroes=[],
        enemies=list(enemies or []),
        buildings=[],
        world=None,
        economy=SimpleNamespace(player_gold=0),
        event_bus=EventBus(),
    )


def _castle_tile_world() -> tuple[float, float]:
    """World coords of the map-centre castle tile (matches sim setup_initial_state)."""
    from config import TILE_SIZE, MAP_WIDTH, MAP_HEIGHT
    gx, gy = MAP_WIDTH // 2, MAP_HEIGHT // 2
    return (gx * TILE_SIZE + TILE_SIZE // 2, gy * TILE_SIZE + TILE_SIZE // 2)


def _make_ctx_with_castle(enemies: list | None = None) -> SystemContext:
    """Like ``_make_ctx`` but with a stub castle at the map centre so the
    ``clustered_near`` path resolves a real castle anchor (mirrors the live sim,
    where ``ctx.castle`` is set by ``SimEngine._build_system_context``)."""
    cx, cy = _castle_tile_world()
    castle = SimpleNamespace(building_type="castle", center_x=cx, center_y=cy,
                             is_alive=True)
    ctx = _make_ctx(enemies)
    ctx.buildings = [castle]
    ctx.castle = castle
    return ctx


class _EventView:
    """Live view of every event the wave system has emitted on this bus.

    EventBus.emit() only *queues* events (delivery is on flush()); nothing in
    these wave-system tests flushes, so the queue accumulates the full history.
    Reading ``ctx.event_bus._queue`` directly is therefore the simplest reliable
    collector and avoids any flush-timing coupling.
    """

    def __init__(self, ctx: SystemContext):
        self._bus = ctx.event_bus

    def __iter__(self):
        return iter(list(self._bus._queue))

    def of_type(self, ev_type: str) -> list[dict]:
        return [e for e in self._bus._queue if e.get("type") == ev_type]


def _collect_events(ctx: SystemContext) -> _EventView:
    return _EventView(ctx)


def _drain_until_no_pending(waves: WaveEventSystem, ctx: SystemContext, dt: float = 0.05,
                            max_ticks: int = 200) -> None:
    """Tick past the WK128 staggered construction until _pending_spawns is empty."""
    ticks = 0
    while waves._pending_spawns and ticks < max_ticks:
        waves.update(ctx, dt)
        ticks += 1


# ---------------------------------------------------------------------------
# Case 1 — warchief stats honor the spec
# ---------------------------------------------------------------------------

def test_warchief_stats_spec_math() -> None:
    gob = ENEMY_STATS["goblin"]
    wc = ENEMY_STATS["goblin_warchief"]

    assert wc.hp == 2 * gob.hp == 60
    assert gob.attack_power == 10  # GOBLIN_ATTACK * 2
    assert wc.attack_power == 15 == int(1.5 * gob.attack_power)
    assert wc.speed == gob.speed
    assert wc.is_boss is True
    assert wc.name == "The Goblin Warchief"
    assert wc.size == 24


def test_warchief_instance_attrs() -> None:
    e = GoblinWarchief(0.0, 0.0)
    assert e.hp == 60
    assert e.max_hp == 60
    assert e.attack_power == 15
    assert e.enemy_type == "goblin_warchief"
    assert getattr(e, "name", None) == "The Goblin Warchief"
    assert getattr(e, "is_boss", False) is True


# ---------------------------------------------------------------------------
# Case 2 — timing
# ---------------------------------------------------------------------------

def test_initial_wave_timing() -> None:
    set_sim_seed(7)
    waves = WaveEventSystem()  # no difficulty => count multiplier 1.0
    ctx = _make_ctx()
    events = _collect_events(ctx)

    dt = 0.05
    # Advance to just under 20s: no warning, no enemies.
    while waves.elapsed_sec < 19.9:
        waves.update(ctx, dt)
    assert not [e for e in events if e["type"] == "wave_incoming"], "warning fired before 20s"
    assert len(ctx.enemies) == 0, "enemies spawned before 20s"

    # Step across the 20.0 boundary — wave_incoming "Goblin Warband" must arrive.
    while waves.elapsed_sec < 20.1:
        waves.update(ctx, dt)
    incoming = [e for e in events if e["type"] == "wave_incoming"]
    assert len(incoming) == 1, f"expected 1 wave_incoming by 20.1s, got {len(incoming)}"
    assert incoming[0]["name"] == "Goblin Warband"
    assert len(ctx.enemies) == 0, "enemies spawned at warning time (20s), should be 30s"

    # Step across the 30.0 boundary, then drain the WK128 stagger.
    while waves.elapsed_sec < 30.1:
        waves.update(ctx, dt)
    _drain_until_no_pending(waves, ctx, dt)
    assert len(ctx.enemies) > 0, "no enemies after the 30s trigger"


# ---------------------------------------------------------------------------
# Case 3 — composition (NORMAL / no difficulty => count multiplier 1.0)
# ---------------------------------------------------------------------------

def test_initial_wave_composition_normal() -> None:
    set_sim_seed(7)
    waves = WaveEventSystem(difficulty=DifficultySystem(DifficultyLevel.NORMAL))
    ctx = _make_ctx()
    _collect_events(ctx)

    dt = 0.05
    while waves.elapsed_sec < 30.1:
        waves.update(ctx, dt)
    _drain_until_no_pending(waves, ctx, dt)

    goblins = [e for e in ctx.enemies if getattr(e, "enemy_type", None) == "goblin"]
    warchiefs = [e for e in ctx.enemies if getattr(e, "enemy_type", None) == "goblin_warchief"]
    assert len(goblins) == INITIAL_WAVE.goblin_count
    assert len(warchiefs) == 1


# ---------------------------------------------------------------------------
# Case 3b — clustered spawn (WK137 r2 structural fix)
# ---------------------------------------------------------------------------

def _fire_initial_wave_near_castle() -> tuple[WaveEventSystem, SystemContext, list]:
    """Fire the initial wave with a real castle anchor; return (waves, ctx, wave_enemies)."""
    set_sim_seed(7)
    waves = WaveEventSystem(difficulty=DifficultySystem(DifficultyLevel.NORMAL))
    ctx = _make_ctx_with_castle()
    _collect_events(ctx)
    dt = 0.05
    while waves.elapsed_sec < 30.1:
        waves.update(ctx, dt)
    _drain_until_no_pending(waves, ctx, dt)
    wave = [e for e in ctx.enemies
            if getattr(e, "enemy_type", None) in ("goblin", "goblin_warchief")]
    return waves, ctx, wave


def test_initial_wave_is_clustered() -> None:
    """WK137 r3: the initial wave lands as a tight pack around ONE near-castle anchor.

    Diagnosed root cause of the r1 balance miss: the old random_edge path drew a
    fresh edge position PER enemy, so the wave was strung out ~220 tiles and the
    heroes mopped it up at full HP. The clustered_near path must keep every enemy
    within a few tiles of each other AND every position inside the playable interior.
    """
    from config import TILE_SIZE, MAP_WIDTH, MAP_HEIGHT

    _waves, _ctx, wave = _fire_initial_wave_near_castle()
    assert len(wave) == INITIAL_WAVE.goblin_count + 1

    xs = [e.x for e in wave]
    ys = [e.y for e in wave]
    spread_tiles = max(
        (max(xs) - min(xs)) / TILE_SIZE,
        (max(ys) - min(ys)) / TILE_SIZE,
    )
    # Jitter is +/- cluster_jitter_tiles on each axis around one anchor, so the
    # per-axis extent is at most 2 * jitter tiles. Allow a +1 tile cushion.
    max_extent = 2 * INITIAL_WAVE.cluster_jitter_tiles + 1
    assert spread_tiles <= max_extent, (
        f"initial wave not clustered: per-axis spread {spread_tiles:.1f} tiles "
        f"> allowed {max_extent} (jitter={INITIAL_WAVE.cluster_jitter_tiles})"
    )

    # All spawn positions must stay inside the playable interior.
    for e in wave:
        assert TILE_SIZE < e.x < (MAP_WIDTH - 1) * TILE_SIZE
        assert TILE_SIZE < e.y < (MAP_HEIGHT - 1) * TILE_SIZE


# ---------------------------------------------------------------------------
# Case 3c — anchor distance: the cluster sits spawn_dist_tiles from the castle
# ---------------------------------------------------------------------------

def test_initial_wave_anchor_distance_from_castle() -> None:
    """WK137 r3: the cluster centroid lands ~spawn_dist_tiles from the castle centre.

    The bearing is random per seed, but the radius is fixed: every enemy is the
    near-anchor +/- jitter, so the centroid distance must land within
    [dist - jitter - 1, dist + jitter + 1] tiles of the castle.
    """
    import math
    from config import TILE_SIZE

    _waves, _ctx, wave = _fire_initial_wave_near_castle()
    ccx, ccy = _castle_tile_world()
    cen_x = sum(e.x for e in wave) / len(wave)
    cen_y = sum(e.y for e in wave) / len(wave)
    dist_tiles = math.hypot(cen_x - ccx, cen_y - ccy) / TILE_SIZE

    d = INITIAL_WAVE.spawn_dist_tiles
    j = INITIAL_WAVE.cluster_jitter_tiles
    lo, hi = d - j - 1, d + j + 1
    assert lo <= dist_tiles <= hi, (
        f"cluster centroid {dist_tiles:.1f} tiles from castle, expected in "
        f"[{lo}, {hi}] (spawn_dist_tiles={d}, jitter={j})"
    )
    # And every individual enemy is within the anchor distance band too.
    for e in wave:
        de = math.hypot(e.x - ccx, e.y - ccy) / TILE_SIZE
        assert (d - 2 * j - 2) <= de <= (d + 2 * j + 2), (
            f"enemy {de:.1f} tiles from castle, outside the near-anchor band"
        )


# ---------------------------------------------------------------------------
# Case 3d — table waves are NOT near-castle-clustered (own direction untouched)
# ---------------------------------------------------------------------------

def test_table_wave_is_not_near_castle_clustered() -> None:
    """A table wave ("Goblin Horde", all_edges) spreads across the map, NOT around
    the castle — proving the clustered_near branch is initial-wave-only and table
    directions are byte-untouched."""
    from config import TILE_SIZE, MAP_WIDTH, MAP_HEIGHT
    from game.systems.wave_events import WaveEventDef
    from game.entities.enemy import Goblin, Wolf

    set_sim_seed(7)
    waves = WaveEventSystem(difficulty=DifficultySystem(DifficultyLevel.NORMAL))
    ctx = _make_ctx_with_castle()

    # Drive a table-style all_edges wave directly through the public spawn path.
    horde = WaveEventDef(
        name="Goblin Horde", minute=99.0,
        composition=[(Goblin, 16), (Wolf, 4)], direction="all_edges", reward_gold=100,
    )
    waves._spawn_wave(horde, ctx)
    _drain_until_no_pending(waves, ctx)

    enemies = [e for e in ctx.enemies if getattr(e, "is_alive", False)]
    assert len(enemies) >= 16

    ccx, ccy = _castle_tile_world()
    import math
    near = sum(1 for e in enemies
               if math.hypot(e.x - ccx, e.y - ccy) / TILE_SIZE
               <= INITIAL_WAVE.spawn_dist_tiles + INITIAL_WAVE.cluster_jitter_tiles + 1)
    # An all_edges table wave spawns on the map perimeter (~125 tiles out): essentially
    # none of it should land inside the initial wave's small near-castle radius.
    assert near == 0, (
        f"{near} table-wave enemies landed in the near-castle radius — table wave "
        f"got near-clustered (clustered_near leaked into a non-initial direction)"
    )
    # And the table wave is genuinely spread out (all_edges => >> jitter extent).
    xs = [e.x for e in enemies]
    ys = [e.y for e in enemies]
    spread_tiles = max((max(xs) - min(xs)) / TILE_SIZE, (max(ys) - min(ys)) / TILE_SIZE)
    assert spread_tiles > 2 * INITIAL_WAVE.cluster_jitter_tiles + 1


# ---------------------------------------------------------------------------
# Case 4 — one-shot
# ---------------------------------------------------------------------------

def test_initial_wave_is_one_shot() -> None:
    set_sim_seed(7)
    waves = WaveEventSystem(difficulty=DifficultySystem(DifficultyLevel.NORMAL))
    ctx = _make_ctx()
    _collect_events(ctx)

    dt = 0.05
    while waves.elapsed_sec < 30.1:
        waves.update(ctx, dt)
    _drain_until_no_pending(waves, ctx, dt)

    count_after_spawn = len([e for e in ctx.enemies
                             if getattr(e, "enemy_type", None) == "goblin_warchief"])
    assert count_after_spawn == 1
    assert waves._initial_wave_done is True

    # Kill the spawned wave so the one-active-wave gate is free, then run on to 60s.
    for e in list(ctx.enemies):
        e.hp = 0
    waves.update(ctx, dt)  # let wave-clear bookkeeping run
    while waves.elapsed_sec < 60.0:
        waves.update(ctx, dt)
    _drain_until_no_pending(waves, ctx, dt)

    warchiefs = [e for e in ctx.enemies
                 if getattr(e, "enemy_type", None) == "goblin_warchief"
                 and getattr(e, "is_alive", False)]
    assert len(warchiefs) == 0, "a second initial wave (warchief) fired before 60s"
    assert waves._initial_wave_done is True


# ---------------------------------------------------------------------------
# Case 5 — table unshifted; "Goblin Raid" still arrives at ~120s
# ---------------------------------------------------------------------------

def test_table_unshifted_after_initial_wave() -> None:
    set_sim_seed(7)
    waves = WaveEventSystem(difficulty=DifficultySystem(DifficultyLevel.NORMAL))
    ctx = _make_ctx()
    events = _collect_events(ctx)

    dt = 0.05
    # Fire the initial wave (30s), then clear it so the table wave can proceed.
    while waves.elapsed_sec < 30.1:
        waves.update(ctx, dt)
    _drain_until_no_pending(waves, ctx, dt)
    assert waves._next_table_index == 0, "initial wave shifted the table index"

    for e in list(ctx.enemies):
        e.hp = 0
    waves.update(ctx, dt)

    # WAVE_EVENT.first_event_minute = 2.0 => "Goblin Raid" fires at ~120s.
    while waves.elapsed_sec < 121.0:
        waves.update(ctx, dt)
        # Keep the lane clear so the table wave can actually fire and report.
        if waves._active_wave_def is not None and waves._active_wave_def.name != "Goblin Warband":
            for e in list(ctx.enemies):
                e.hp = 0

    raid_msgs = [e for e in events
                 if e["type"] == "hud_message" and "Goblin Raid" in e.get("text", "")]
    assert raid_msgs, "table 'Goblin Raid' wave never fired at ~120s — schedule moved"


# ---------------------------------------------------------------------------
# Case 6 — kill-switch (enabled=False, module-attr patch)
# ---------------------------------------------------------------------------

def test_initial_wave_kill_switch(monkeypatch) -> None:
    set_sim_seed(7)
    monkeypatch.setattr(wave_events_module, "_initial_cfg",
                        InitialWaveConfig(enabled=False))
    waves = WaveEventSystem(difficulty=DifficultySystem(DifficultyLevel.NORMAL))
    ctx = _make_ctx()
    events = _collect_events(ctx)

    dt = 0.05
    while waves.elapsed_sec < 35.0:
        waves.update(ctx, dt)
    _drain_until_no_pending(waves, ctx, dt)

    warchiefs = [e for e in ctx.enemies if getattr(e, "enemy_type", None) == "goblin_warchief"]
    assert len(warchiefs) == 0, "kill-switch off but warchief still spawned"
    assert not [e for e in events
                if e["type"] == "wave_incoming" and e.get("name") == "Goblin Warband"]
    assert waves._initial_wave_done is False


# ---------------------------------------------------------------------------
# Case 7 — difficulty counts (EASY / HARD)
# ---------------------------------------------------------------------------

def _spawn_initial_wave_with_difficulty(level: DifficultyLevel) -> SystemContext:
    set_sim_seed(7)
    waves = WaveEventSystem(difficulty=DifficultySystem(level))
    ctx = _make_ctx()
    _collect_events(ctx)
    dt = 0.05
    while waves.elapsed_sec < 30.1:
        waves.update(ctx, dt)
    _drain_until_no_pending(waves, ctx, dt)
    return ctx


def test_initial_wave_difficulty_counts() -> None:
    # Counts derive from the shipped goblin_count via the difficulty count
    # multiplier (computed dynamically so an r2 retune of goblin_count keeps the
    # test honest): EASY x0.6, HARD x1.5; warchief base 1 -> EASY max(1,round(0.6))=1,
    # HARD round(1.5)=2 (intended escalation).
    base = INITIAL_WAVE.goblin_count
    exp_easy = max(1, round(base * 0.6))
    exp_hard = max(1, round(base * 1.5))

    easy_ctx = _spawn_initial_wave_with_difficulty(DifficultyLevel.EASY)
    easy_goblins = [e for e in easy_ctx.enemies if getattr(e, "enemy_type", None) == "goblin"]
    easy_warchiefs = [e for e in easy_ctx.enemies
                      if getattr(e, "enemy_type", None) == "goblin_warchief"]
    assert len(easy_goblins) == exp_easy
    assert len(easy_warchiefs) == 1

    hard_ctx = _spawn_initial_wave_with_difficulty(DifficultyLevel.HARD)
    hard_goblins = [e for e in hard_ctx.enemies if getattr(e, "enemy_type", None) == "goblin"]
    hard_warchiefs = [e for e in hard_ctx.enemies
                      if getattr(e, "enemy_type", None) == "goblin_warchief"]
    assert len(hard_goblins) == exp_hard
    assert len(hard_warchiefs) == 2
