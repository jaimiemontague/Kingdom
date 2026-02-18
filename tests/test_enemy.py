from __future__ import annotations

from types import SimpleNamespace

from game.entities.enemy import Enemy, EnemyState, Goblin, SkeletonArcher
from game.entities.hero import HeroState


def test_find_target_ignores_resting_heroes_and_peasants_inside_castle() -> None:
    enemy = Enemy(0, 0, enemy_type="goblin")
    resting_hero = SimpleNamespace(is_alive=True, state=HeroState.RESTING, x=4.0, y=0.0)
    active_hero = SimpleNamespace(is_alive=True, state=HeroState.IDLE, x=100.0, y=0.0)
    inside_castle_peasant = SimpleNamespace(is_alive=True, is_inside_castle=True, x=2.0, y=0.0)
    guard = SimpleNamespace(is_alive=True, x=8.0, y=0.0)

    target = enemy.find_target(
        heroes=[resting_hero, active_hero],
        peasants=[inside_castle_peasant],
        buildings=[],
        guards=[guard],
    )

    assert target is guard


def test_find_target_prefers_nearest_available_peasant() -> None:
    enemy = Enemy(0, 0, enemy_type="goblin")
    peasant = SimpleNamespace(is_alive=True, is_inside_castle=False, x=5.0, y=0.0)
    hero = SimpleNamespace(is_alive=True, state=HeroState.IDLE, x=7.0, y=0.0)

    target = enemy.find_target(heroes=[hero], peasants=[peasant], buildings=[], guards=[])

    assert target is peasant


def test_find_target_can_choose_building_with_resting_hero_inside() -> None:
    enemy = Enemy(0, 0, enemy_type="goblin")
    inn = SimpleNamespace(
        hp=200,
        is_targetable=True,
        center_x=20.0,
        center_y=0.0,
        building_type="inn",
        is_neutral=False,
    )
    resting_hero = SimpleNamespace(
        is_alive=True,
        state=HeroState.RESTING,
        x=inn.center_x,
        y=inn.center_y,
        home_building=inn,
    )

    target = enemy.find_target(heroes=[resting_hero], peasants=[], buildings=[inn], guards=[])

    assert target is inn


def test_take_damage_sets_dead_state_and_trigger() -> None:
    enemy = Goblin(0, 0)

    killed = enemy.take_damage(enemy.hp + 1)

    assert killed is True
    assert enemy.state == EnemyState.DEAD
    assert enemy._render_anim_trigger == "dead"


def test_skeleton_archer_do_attack_emits_projectile_event() -> None:
    archer = SkeletonArcher(0, 0)
    target = SimpleNamespace(x=12.0, y=0.0, hp=30)

    def _take_damage(amount: int) -> None:
        target.hp -= int(amount)

    target.take_damage = _take_damage
    archer.target = target
    archer.attack_cooldown = 0

    archer.do_attack()

    assert target.hp < 30
    assert archer._last_ranged_event is not None
    assert archer._last_ranged_event["type"] == "ranged_projectile"
    assert archer._last_ranged_event["from_x"] == archer.x
    assert archer._last_ranged_event["to_x"] == target.x


def test_skeleton_archer_kites_away_when_too_close(monkeypatch) -> None:
    monkeypatch.setattr("game.entities.enemy.now_ms", lambda: 1_000)
    archer = SkeletonArcher(0, 0)
    target = SimpleNamespace(x=10.0, y=0.0, is_alive=True)
    target.take_damage = lambda amount: None
    archer.target = target
    archer.attack_cooldown = 500  # avoid immediate attack branch
    start_x = archer.x

    archer.update(dt=0.1, heroes=[], peasants=[], buildings=[], guards=[], world=None)

    assert archer.state == EnemyState.MOVING
    assert archer._kite_attempts == 1
    assert archer.x < start_x
