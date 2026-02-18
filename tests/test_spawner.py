from __future__ import annotations

from game.sim.determinism import set_sim_seed
from game.systems.spawner import EnemySpawner


def test_no_spawn_during_initial_warmup(make_world) -> None:
    set_sim_seed(1)
    spawner = EnemySpawner(make_world())
    spawner.initial_no_spawn_ms = 100
    spawner.first_wave_interval_ms = 1

    spawned = spawner.spawn(0.05)  # 50ms

    assert spawned == []
    assert spawner.total_spawned == 0


def test_first_wave_spawns_skeleton_archer(make_world) -> None:
    class DummySkeletonArcher:
        def __init__(self, x: float, y: float) -> None:
            self.x = float(x)
            self.y = float(y)

    class DummyGoblin:
        def __init__(self, x: float, y: float) -> None:
            self.x = float(x)
            self.y = float(y)

    set_sim_seed(2)
    spawner = EnemySpawner(make_world())
    import game.systems.spawner as spawner_module
    spawner_module.SkeletonArcher = DummySkeletonArcher
    spawner_module.Goblin = DummyGoblin
    spawner.initial_no_spawn_ms = 0
    spawner.first_wave_interval_ms = 1

    spawned = spawner.spawn(0.002)  # 2ms

    assert len(spawned) == 1
    assert isinstance(spawned[0], DummySkeletonArcher)
    assert spawner.total_spawned == 1
    assert spawner._spawned_first_wave_archer is True


def test_wave_counter_increments_each_ten_spawns(make_world) -> None:
    class DummySkeletonArcher:
        def __init__(self, x: float, y: float) -> None:
            self.x = float(x)
            self.y = float(y)

    class DummyGoblin:
        def __init__(self, x: float, y: float) -> None:
            self.x = float(x)
            self.y = float(y)

    set_sim_seed(3)
    spawner = EnemySpawner(make_world())
    import game.systems.spawner as spawner_module
    spawner_module.SkeletonArcher = DummySkeletonArcher
    spawner_module.Goblin = DummyGoblin
    spawner.initial_no_spawn_ms = 0
    spawner.first_wave_interval_ms = 1
    spawner.spawn_interval = 1
    spawner._spawned_first_wave_archer = True
    spawner.enemies_per_wave = 10

    spawned = spawner.spawn(0.002)

    assert len(spawned) == 10
    assert spawner.total_spawned == 10
    assert spawner.wave_number == 2


def test_enemy_per_wave_cap_applied_when_wave_grows(make_world) -> None:
    class DummySkeletonArcher:
        def __init__(self, x: float, y: float) -> None:
            self.x = float(x)
            self.y = float(y)

    class DummyGoblin:
        def __init__(self, x: float, y: float) -> None:
            self.x = float(x)
            self.y = float(y)

    set_sim_seed(4)
    spawner = EnemySpawner(make_world())
    import game.systems.spawner as spawner_module
    spawner_module.SkeletonArcher = DummySkeletonArcher
    spawner_module.Goblin = DummyGoblin
    spawner.initial_no_spawn_ms = 0
    spawner.first_wave_interval_ms = 1
    spawner.spawn_interval = 1
    spawner._spawned_first_wave_archer = True
    spawner.wave_number = 20
    spawner.total_spawned = 9
    spawner.enemies_per_wave = 1

    spawned = spawner.spawn(0.002)

    assert len(spawned) == 1
    assert spawner.total_spawned == 10
    assert spawner.wave_number == 21
    assert spawner.enemies_per_wave == 4


def test_spawn_positions_are_deterministic_for_same_seed(make_world) -> None:
    set_sim_seed(99)
    spawner_a = EnemySpawner(make_world())
    positions_a = [spawner_a.get_spawn_position() for _ in range(5)]

    set_sim_seed(99)
    spawner_b = EnemySpawner(make_world())
    positions_b = [spawner_b.get_spawn_position() for _ in range(5)]

    assert positions_a == positions_b
