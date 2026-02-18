from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import pytest

from config import TILE_SIZE
from game.systems.economy import EconomySystem


@dataclass
class FakeWorld:
    blocked_tiles: set[tuple[int, int]]

    def is_walkable(self, x: int, y: int) -> bool:
        return (int(x), int(y)) not in self.blocked_tiles


class FakeHero:
    def __init__(
        self,
        *,
        name: str = "Hero",
        x: float = 0.0,
        y: float = 0.0,
        attack: int = 10,
        attack_range: float = float(TILE_SIZE * 2),
        hp: int = 100,
    ) -> None:
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.hp = int(hp)
        self.max_hp = int(hp)
        self.attack = int(attack)
        self.attack_range = float(attack_range)
        self.attack_cooldown = 0
        self.attack_cooldown_max = 1000
        self.can_attack = True
        self.is_inside_building = False
        self.attack_blocked_reason = ""
        self._inside_attack_blocks = 0
        self.is_ranged_attacker = False
        self._ranged_spec: dict[str, object] = {
            "kind": "arrow",
            "color": (200, 200, 200),
            "size_px": 2,
        }
        self.target = None
        self.gold = 0
        self.xp = 0
        self.buffs: list[dict[str, object]] = []

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def distance_to(self, x: float, y: float) -> float:
        return math.hypot(self.x - float(x), self.y - float(y))

    def add_gold(self, amount: int) -> None:
        self.gold += int(amount)

    def add_xp(self, amount: int) -> None:
        self.xp += int(amount)

    def compute_attack_damage(self, target: object | None = None) -> int:
        _ = target
        return int(self.attack)

    def on_attack_landed(self, target: object | None = None, damage: int = 0, killed: bool = False) -> None:
        _ = (target, damage, killed)

    def get_ranged_spec(self) -> dict[str, object]:
        return dict(self._ranged_spec)

    def apply_or_refresh_buff(
        self,
        *,
        name: str,
        atk_delta: int = 0,
        def_delta: int = 0,
        duration_s: float = 1.0,
        now_ms: int,
    ) -> None:
        expires_at_ms = int(now_ms + float(duration_s) * 1000.0)
        for buff in self.buffs:
            if buff["name"] == name:
                buff["atk_delta"] = int(atk_delta)
                buff["def_delta"] = int(def_delta)
                buff["expires_at_ms"] = expires_at_ms
                return
        self.buffs.append(
            {
                "name": name,
                "atk_delta": int(atk_delta),
                "def_delta": int(def_delta),
                "expires_at_ms": expires_at_ms,
            }
        )

    def remove_expired_buffs(self, now_ms: int) -> None:
        self.buffs = [buff for buff in self.buffs if int(buff["expires_at_ms"]) > int(now_ms)]


class FakeEnemy:
    def __init__(
        self,
        *,
        x: float = 0.0,
        y: float = 0.0,
        enemy_type: str = "goblin",
        hp: int = 30,
        attack_power: int = 5,
        gold_reward: int = 10,
        xp_reward: int = 25,
    ) -> None:
        self.x = float(x)
        self.y = float(y)
        self.enemy_type = str(enemy_type)
        self.hp = int(hp)
        self.max_hp = int(hp)
        self.attack_power = int(attack_power)
        self.gold_reward = int(gold_reward)
        self.xp_reward = int(xp_reward)
        self.attackers: set[str] = set()
        self.target = None

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def register_attacker(self, hero: FakeHero) -> None:
        self.attackers.add(str(hero.name))

    def take_damage(self, amount: int) -> bool:
        self.hp = max(0, self.hp - int(amount))
        return self.hp <= 0


class FakeBuilding:
    def __init__(
        self,
        *,
        grid_x: int = 0,
        grid_y: int = 0,
        building_type: str = "marketplace",
        hp: int = 200,
        max_hp: int | None = None,
        is_lair: bool = False,
    ) -> None:
        self.grid_x = int(grid_x)
        self.grid_y = int(grid_y)
        self.building_type = str(building_type)
        self.hp = int(hp)
        self.max_hp = int(max_hp if max_hp is not None else hp)
        self.is_lair = bool(is_lair)
        self.is_constructed = True
        self.construction_started = True
        self.is_damaged = self.hp < self.max_hp
        self.is_under_attack = False
        self.x = float(self.grid_x * TILE_SIZE)
        self.y = float(self.grid_y * TILE_SIZE)
        self.center_x = self.x + TILE_SIZE
        self.center_y = self.y + TILE_SIZE
        self.clear_gold = 0
        self.threat_level = 1

    def take_damage(self, amount: int, attacker: object | None = None) -> bool:
        _ = attacker
        self.hp = max(0, self.hp - int(amount))
        self.is_damaged = self.hp < self.max_hp
        return self.hp <= 0

    def on_cleared(self, hero: object | None = None) -> dict[str, int]:
        _ = hero
        return {"gold": int(self.clear_gold), "threat_level": int(self.threat_level)}


@pytest.fixture
def make_world() -> Callable[..., FakeWorld]:
    def _factory(*, blocked_tiles: set[tuple[int, int]] | None = None) -> FakeWorld:
        return FakeWorld(blocked_tiles=set(blocked_tiles or set()))

    return _factory


@pytest.fixture
def make_hero() -> Callable[..., FakeHero]:
    def _factory(**kwargs) -> FakeHero:
        return FakeHero(**kwargs)

    return _factory


@pytest.fixture
def make_enemy() -> Callable[..., FakeEnemy]:
    def _factory(**kwargs) -> FakeEnemy:
        return FakeEnemy(**kwargs)

    return _factory


@pytest.fixture
def make_building() -> Callable[..., FakeBuilding]:
    def _factory(**kwargs) -> FakeBuilding:
        return FakeBuilding(**kwargs)

    return _factory


@pytest.fixture
def make_economy() -> Callable[..., EconomySystem]:
    def _factory(*, player_gold: int | None = None) -> EconomySystem:
        economy = EconomySystem()
        if player_gold is not None:
            economy.player_gold = int(player_gold)
        return economy

    return _factory
