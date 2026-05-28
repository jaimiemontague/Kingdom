"""WK61-R11-BUG-001: Wolf Pack wave spawns Wolf enemies even near enemy cap."""

from __future__ import annotations

from types import SimpleNamespace

from config import MAX_ALIVE_ENEMIES, WAVE_EVENT
from game.entities.enemy import Goblin, Wolf
from game.events import EventBus
from game.sim.determinism import set_sim_seed
from game.systems.protocol import SystemContext
from game.systems.wave_events import WaveEventSystem


def _make_ctx(enemies: list | None = None) -> SystemContext:
    return SystemContext(
        heroes=[],
        enemies=list(enemies or []),
        buildings=[],
        world=None,
        economy=SimpleNamespace(player_gold=0),
        event_bus=EventBus(),
    )


def _advance_to_wolf_pack(waves: WaveEventSystem, ctx: SystemContext) -> None:
    """Advance sim until Wolf Pack adds Wolf instances (clears blocking waves)."""
    dt = 0.1
    max_sec = 600.0
    elapsed = 0.0
    while elapsed <= max_sec:
        waves.update(ctx, dt)
        wolves = [e for e in ctx.enemies if isinstance(e, Wolf)]
        if len(wolves) >= 3:
            return
        # Headless: simulate player clearing an active wave so the next event can spawn.
        if waves._active_wave_def is not None:
            for enemy in list(waves._active_wave_enemies):
                if getattr(enemy, "is_alive", False):
                    enemy.hp = 0
            waves.update(ctx, dt)
            wolves = [e for e in ctx.enemies if isinstance(e, Wolf)]
            if len(wolves) >= 3:
                return
        elapsed += dt

    wolves = [e for e in ctx.enemies if isinstance(e, Wolf)]
    raise AssertionError(f"Wolf Pack never spawned wolves within {max_sec}s (got {len(wolves)})")


def test_wolf_pack_spawns_wolf_instances() -> None:
    set_sim_seed(7)
    waves = WaveEventSystem()
    ctx = _make_ctx()

    _advance_to_wolf_pack(waves, ctx)

    wolves = [e for e in ctx.enemies if isinstance(e, Wolf)]
    assert len(wolves) >= 3, f"expected >=3 Wolf instances, got {len(wolves)}"


def test_wolf_pack_reserves_slots_when_at_cap() -> None:
    set_sim_seed(11)
    wave_cap = int(MAX_ALIVE_ENEMIES * WAVE_EVENT.max_enemy_cap_overflow)
    filler = [Goblin(float(i), float(i)) for i in range(wave_cap)]
    waves = WaveEventSystem()
    ctx = _make_ctx(filler)

    _advance_to_wolf_pack(waves, ctx)

    wolves = [e for e in ctx.enemies if isinstance(e, Wolf)]
    assert len(wolves) >= 3, "Wolf Pack must spawn wolves even when map was at wave cap"
