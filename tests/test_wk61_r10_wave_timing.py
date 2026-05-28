"""WK61-R10: spawner first-wave timing uses config-driven R10 pacing."""

from __future__ import annotations

from config import SPAWNER_FIRST_WAVE_INTERVAL_MS, SPAWNER_INITIAL_NO_SPAWN_MS
from game.sim.determinism import set_sim_seed
from game.systems.spawner import EnemySpawner


def test_first_enemy_spawn_within_r10_budget(make_world) -> None:
    class DummySkeletonArcher:
        def __init__(self, x: float, y: float) -> None:
            self.x = float(x)
            self.y = float(y)

    class DummyGoblin:
        def __init__(self, x: float, y: float) -> None:
            self.x = float(x)
            self.y = float(y)

    set_sim_seed(42)
    spawner = EnemySpawner(make_world())
    import game.systems.spawner as spawner_module

    spawner_module.SkeletonArcher = DummySkeletonArcher
    spawner_module.Goblin = DummyGoblin

    max_spawn_ms = SPAWNER_INITIAL_NO_SPAWN_MS + SPAWNER_FIRST_WAVE_INTERVAL_MS + 50
    spawned = []
    dt = 0.05
    steps = 0
    while steps * dt * 1000 <= max_spawn_ms + 100:
        batch = spawner.spawn(dt)
        if batch:
            spawned.extend(batch)
            break
        steps += 1

    assert spawned, "expected first wave enemy within R10 spawn budget"
    assert spawner.elapsed_ms <= max_spawn_ms
    assert spawner.initial_no_spawn_ms == SPAWNER_INITIAL_NO_SPAWN_MS
    assert spawner.first_wave_interval_ms == SPAWNER_FIRST_WAVE_INTERVAL_MS
