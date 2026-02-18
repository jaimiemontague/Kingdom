from __future__ import annotations

from game.events import EventBus, GameEventType
from game.systems.combat import CombatSystem
from game.systems.protocol import SystemContext


def _make_context(*, heroes: list, enemies: list, buildings: list) -> SystemContext:
    return SystemContext(
        heroes=heroes,
        enemies=enemies,
        buildings=buildings,
        world=object(),
        economy=object(),
        event_bus=EventBus(),
    )


def _events_of_type(events: list[dict], event_type: GameEventType) -> list[dict]:
    return [event for event in events if event.get("type") == event_type.value]


def test_hero_attack_applies_damage_and_emits_event(make_hero, make_enemy) -> None:
    combat = CombatSystem()
    hero = make_hero(name="A", x=0, y=0, attack=12, attack_range=80)
    enemy = make_enemy(x=10, y=0, hp=30)
    ctx = _make_context(heroes=[hero], enemies=[enemy], buildings=[])

    combat.update(ctx, dt=0.016)
    events = combat.get_emitted_events()

    assert enemy.hp == 18
    assert hero.attack_cooldown == hero.attack_cooldown_max
    assert len(_events_of_type(events, GameEventType.HERO_ATTACK)) == 1


def test_kill_distributes_gold_and_grants_xp(make_hero, make_enemy) -> None:
    combat = CombatSystem()
    killer = make_hero(name="Killer", x=0, y=0, attack=99, attack_range=80)
    ally = make_hero(name="Ally", x=8, y=0, attack=1, attack_range=10)
    enemy = make_enemy(x=10, y=0, hp=40, gold_reward=11, xp_reward=25)
    ctx = _make_context(heroes=[killer, ally], enemies=[enemy], buildings=[])

    combat.update(ctx, dt=0.016)
    events = combat.get_emitted_events()
    killed_events = _events_of_type(events, GameEventType.ENEMY_KILLED)

    assert enemy.hp == 0
    assert killer.xp == 25
    assert killer.gold + ally.gold == 11
    assert len(killed_events) == 1
    assert killed_events[0]["gold_split"] == 2


def test_ranged_attacker_emits_projectile_event(make_hero, make_enemy) -> None:
    combat = CombatSystem()
    ranger = make_hero(name="Ranger", x=0, y=0, attack=7, attack_range=120)
    ranger.is_ranged_attacker = True
    ranger._ranged_spec = {"kind": "arrow", "color": (10, 20, 30), "size_px": 3}
    enemy = make_enemy(x=20, y=0, hp=50)
    ctx = _make_context(heroes=[ranger], enemies=[enemy], buildings=[])

    combat.update(ctx, dt=0.016)
    projectile_events = _events_of_type(combat.get_emitted_events(), GameEventType.RANGED_PROJECTILE)

    assert len(projectile_events) == 1
    assert projectile_events[0]["projectile_kind"] == "arrow"
    assert projectile_events[0]["size_px"] == 3


def test_castle_destroyed_event_emitted_for_zero_hp_castle(make_building) -> None:
    combat = CombatSystem()
    castle = make_building(building_type="castle", hp=0)
    ctx = _make_context(heroes=[], enemies=[], buildings=[castle])

    combat.update(ctx, dt=0.016)
    events = combat.get_emitted_events()

    assert len(_events_of_type(events, GameEventType.CASTLE_DESTROYED)) == 1


def test_hero_inside_building_cannot_attack(make_hero, make_enemy) -> None:
    combat = CombatSystem()
    hero = make_hero(name="Blocked", x=0, y=0, attack=20, attack_range=80)
    hero.can_attack = False
    hero.is_inside_building = True
    enemy = make_enemy(x=10, y=0, hp=30)
    ctx = _make_context(heroes=[hero], enemies=[enemy], buildings=[])

    combat.update(ctx, dt=0.016)
    events = combat.get_emitted_events()

    assert enemy.hp == 30
    assert len(_events_of_type(events, GameEventType.HERO_ATTACK)) == 0
    assert hero._inside_attack_blocks >= 1


def test_lair_combat_emits_attack_and_clear_events(make_hero, make_building) -> None:
    combat = CombatSystem()
    hero = make_hero(name="LairHunter", x=0, y=0, attack=80, attack_range=120)
    lair = make_building(building_type="goblin_lair", hp=60, is_lair=True)
    lair.center_x = 30.0
    lair.center_y = 0.0
    lair.clear_gold = 50
    lair.threat_level = 2
    hero.target = lair
    ctx = _make_context(heroes=[hero], enemies=[], buildings=[lair])

    combat.update(ctx, dt=0.016)
    events = combat.get_emitted_events()

    assert lair.hp == 0
    assert len(_events_of_type(events, GameEventType.HERO_ATTACK_LAIR)) == 1
    assert len(_events_of_type(events, GameEventType.LAIR_CLEARED)) == 1


def test_enemy_retargets_attacker_when_current_target_is_building(make_hero, make_enemy, make_building) -> None:
    combat = CombatSystem()
    hero = make_hero(name="Retargeter", x=0, y=0, attack=5, attack_range=80)
    enemy = make_enemy(x=10, y=0, hp=30)
    enemy.target = make_building(building_type="inn", hp=200)
    ctx = _make_context(heroes=[hero], enemies=[enemy], buildings=[])

    combat.update(ctx, dt=0.016)

    assert enemy.target is hero
