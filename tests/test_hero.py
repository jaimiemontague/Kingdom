from __future__ import annotations

from types import SimpleNamespace

from config import TILE_SIZE
from game.entities.buildings.economic import Inn
from game.entities.hero import Hero, HeroState
from game.systems.buffs import Buff


def test_buy_item_potion_updates_inventory_and_purchase_tracking(monkeypatch) -> None:
    monkeypatch.setattr("game.entities.hero.sim_now_ms", lambda: 12_345)
    hero = Hero(0, 0, hero_class="warrior")
    hero.gold = 100

    ok = hero.buy_item({"name": "Healing Potion", "type": "potion", "price": 20, "effect": 60})

    assert ok is True
    assert hero.gold == 80
    assert hero.potions == 1
    assert hero.potion_heal_amount == 60
    assert hero.last_purchase_ms == 12_345
    assert hero.last_purchase_type == "potion"


def test_buy_item_potion_refunds_when_at_max_capacity(monkeypatch) -> None:
    monkeypatch.setattr("game.entities.hero.sim_now_ms", lambda: 1)
    hero = Hero(0, 0, hero_class="warrior")
    hero.gold = 50
    hero.potions = hero.max_potions

    ok = hero.buy_item({"name": "Healing Potion", "type": "potion", "price": 20, "effect": 50})

    assert ok is False
    assert hero.gold == 50
    assert hero.potions == hero.max_potions


def test_use_potion_heals_and_consumes_one_potion() -> None:
    hero = Hero(0, 0, hero_class="warrior")
    hero.hp = 20
    hero.max_hp = 100
    hero.potions = 1
    hero.potion_heal_amount = 30

    ok = hero.use_potion()

    assert ok is True
    assert hero.hp == 50
    assert hero.potions == 0


def test_take_damage_applies_minimum_damage_even_with_high_defense() -> None:
    hero = Hero(0, 0, hero_class="warrior")
    hero.armor = {"name": "Tank Armor", "defense": 999}
    before_hp = hero.hp

    killed = hero.take_damage(1)

    assert killed is False
    assert hero.hp == before_hp - 1


def test_wants_to_shop_requires_health_and_gold_thresholds() -> None:
    hero = Hero(0, 0, hero_class="warrior")
    hero.hp = hero.max_hp - 1
    hero.gold = 100
    assert hero.wants_to_shop(marketplace_has_potions=True) is False

    hero.hp = hero.max_hp
    hero.gold = 20
    assert hero.wants_to_shop(marketplace_has_potions=True) is False

    hero.gold = 30
    hero.potions = 0
    assert hero.wants_to_shop(marketplace_has_potions=True) is True


def test_update_exits_brief_inside_building_state_when_timer_elapsed() -> None:
    hero = Hero(0, 0, hero_class="warrior")
    building = SimpleNamespace(center_x=100.0, center_y=200.0)
    hero.is_inside_building = True
    hero.inside_building = building
    hero.inside_timer = 0.05
    hero.state = HeroState.IDLE

    hero.update(0.1, game_state={})

    assert hero.is_inside_building is False
    assert hero.inside_building is None
    assert hero.x == building.center_x + TILE_SIZE
    assert hero.y == building.center_y


def test_hero_pending_task_fields_default_to_none() -> None:
    hero = Hero(0, 0, hero_class="warrior")

    assert hero.pending_task is None
    assert hero.pending_task_building is None


def test_inn_resting_tracks_hero_entry_exit_and_fast_heal_rate() -> None:
    hero = Hero(0, 0, hero_class="warrior")
    hero.max_hp = 100
    hero.hp = 90
    hero.gold = 20  # WK18: Inn loiter fee; need gold to stay inside
    inn = Inn(2, 3)

    started = hero.start_resting_at_building(inn)
    assert started is True
    assert hero in inn.heroes_resting

    still_resting = hero.update_resting(1.0)
    assert still_resting is True
    assert hero.hp == 91  # Inn rate: 1 HP per second.

    hero.pop_out_of_building()
    assert hero not in inn.heroes_resting
    assert hero.is_inside_building is False


def test_update_moves_towards_target_position_without_world() -> None:
    hero = Hero(0, 0, hero_class="warrior")
    hero.set_target_position(100.0, 0.0)
    before_x = hero.x

    hero.update(0.1, game_state={})

    assert hero.state == HeroState.MOVING
    assert hero.x > before_x
    assert hero.y == 0.0


def test_attack_property_includes_active_buff(monkeypatch) -> None:
    monkeypatch.setattr("game.entities.hero.sim_now_ms", lambda: 1_000)
    hero = Hero(0, 0, hero_class="warrior")
    base_attack = hero.attack
    hero.buffs.append(Buff(name="test", atk_delta=5, expires_at_ms=2_000))

    assert hero.attack == base_attack + 5


def test_get_stuck_snapshot_reports_expected_contract_fields(monkeypatch) -> None:
    monkeypatch.setattr("game.entities.hero.sim_now_ms", lambda: 5_000)
    hero = Hero(0, 0, hero_class="warrior")
    hero.stuck_active = True
    hero.stuck_since_ms = 4_250
    hero.unstuck_attempts = 2
    hero.stuck_reason = "path_blocked"

    snapshot = hero.get_stuck_snapshot()

    assert snapshot["stuck_active"] is True
    assert snapshot["stuck_since_ms"] == 4_250
    assert snapshot["stuck_age_ms"] == 750
    assert snapshot["unstuck_attempts"] == 2
    assert snapshot["stuck_reason"] == "path_blocked"
