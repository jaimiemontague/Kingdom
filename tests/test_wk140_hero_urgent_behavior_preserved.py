from __future__ import annotations

from random import Random
from types import SimpleNamespace

from ai import task_router
from ai.behaviors import exploration
from ai.basic_ai import BasicAI
from config import TILE_SIZE
from game.entities.hero import HeroState


class _Hero:
    def __init__(
        self,
        hero_id: str,
        name: str,
        hero_class: str,
        x: float,
        y: float,
        *,
        hp: int = 100,
        max_hp: int = 100,
        gold: int = 0,
    ) -> None:
        self.hero_id = hero_id
        self.name = name
        self.hero_class = hero_class
        self.x = float(x)
        self.y = float(y)
        self.hp = int(hp)
        self.max_hp = int(max_hp)
        self.gold = int(gold)
        self.state = HeroState.IDLE
        self.target = None
        self.target_position = None
        self.intent = "idle"
        self.is_inside_building = False
        self.home_building = None
        self._should_rest = False
        self._can_rest_at_home = True
        self.pending_llm_decision = False
        self.last_llm_decision_time = 0
        self.llm_move_request = None

    @property
    def health_percent(self) -> float:
        return float(self.hp) / float(self.max_hp) if self.max_hp else 1.0

    def distance_to(self, x: float, y: float) -> float:
        from math import hypot

        return hypot(self.x - float(x), self.y - float(y))

    def set_target_position(self, x: float, y: float) -> None:
        self.target_position = (float(x), float(y))

    def should_go_home_to_rest(self) -> bool:
        return bool(self._should_rest)

    def can_rest_at_home(self) -> bool:
        return bool(self._can_rest_at_home)


class _Building:
    def __init__(self, building_type: str, x: float, y: float) -> None:
        self.building_type = building_type
        self.center_x = float(x)
        self.center_y = float(y)
        self.entity_id = building_type


class _FixedRNG:
    def random(self) -> float:
        return 0.99

    def uniform(self, a: float, b: float) -> float:
        return (float(a) + float(b)) / 2.0

    def randrange(self, n: int) -> int:
        return 0


def _make_ai() -> BasicAI:
    ai = BasicAI(llm_brain=None)
    ai._ai_rng = _FixedRNG()
    return ai


def _make_view(hero: _Hero, *, castle=None, buildings=None, enemies=None, bounties=None, pois=None):
    return SimpleNamespace(
        world=None,
        buildings=list(buildings or []),
        enemies=list(enemies or []),
        heroes=[hero],
        bounties=list(bounties or []),
        pois=list(pois or []),
        castle=castle,
        player_gold=0,
    )


def test_fighting_priority_preempts_idle_ambient_paths(monkeypatch) -> None:
    ai = _make_ai()
    hero = _Hero("fight", "Fenna", "warrior", 10 * TILE_SIZE, 10 * TILE_SIZE)
    hero.state = HeroState.FIGHTING
    view = _make_view(hero)
    calls: list[str] = []

    monkeypatch.setattr(ai, "handle_fighting", lambda _hero, _view: calls.append("fight"))
    monkeypatch.setattr(ai, "handle_idle", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("idle should not run")))
    monkeypatch.setattr(ai, "send_home_to_rest", lambda *_a, **_k: calls.append("rest"))
    monkeypatch.setattr(task_router.quest_offer, "maybe_approach_quest_giver", lambda *_a, **_k: None)

    task_router.update_hero(ai, hero, 1 / 60, view)

    assert calls == ["fight"]


def test_low_health_rest_preempts_daily_life(monkeypatch) -> None:
    ai = _make_ai()
    hero = _Hero("rest", "Rhea", "cleric", 10 * TILE_SIZE, 10 * TILE_SIZE, hp=18, max_hp=100)
    hero._should_rest = True
    hero._can_rest_at_home = True
    view = _make_view(hero, castle=_Building("castle", 10 * TILE_SIZE, 10 * TILE_SIZE))
    sent_home: list[str] = []

    monkeypatch.setattr(ai, "handle_idle", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("idle should not run")))
    monkeypatch.setattr(ai, "handle_fighting", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("fight should not run")))
    monkeypatch.setattr(ai, "send_home_to_rest", lambda hero_obj, _view: sent_home.append(hero_obj.name))
    monkeypatch.setattr(task_router.quest_offer, "maybe_approach_quest_giver", lambda *_a, **_k: None)

    task_router.update_hero(ai, hero, 1 / 60, view)

    assert sent_home == ["Rhea"]


def test_shopping_preempts_daily_life_step(monkeypatch) -> None:
    hero = _Hero("shop", "Sera", "rogue", 12 * TILE_SIZE, 12 * TILE_SIZE, gold=80)
    hero.state = HeroState.IDLE
    hero.wants_to_shop = lambda can_sell: True

    marketplace = _Building("marketplace", 14 * TILE_SIZE, 12 * TILE_SIZE)
    marketplace.can_sell_potions = lambda: True
    view = _make_view(hero, buildings=[marketplace])

    ai = SimpleNamespace(
        _ai_rng=_FixedRNG(),
        _debug_log=lambda *_a, **_k: None,
        bounty_behavior=SimpleNamespace(maybe_take_bounty=lambda *_a, **_k: False),
        hunger_behavior=SimpleNamespace(maybe_seek_meal_idle=lambda *_a, **_k: False),
        shopping_behavior=SimpleNamespace(
            find_marketplace_with_potions=lambda buildings: buildings[0] if buildings else None,
            find_blacksmith=lambda *_a, **_k: None,
        ),
    )

    monkeypatch.setattr(exploration, "_idle_daily_life", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("daily life should not run")))

    exploration.handle_idle(ai, hero, view)

    assert hero.state == HeroState.MOVING
    assert isinstance(hero.target, dict)
    assert hero.target["type"] == "shopping"
    assert hero.target_position is not None
