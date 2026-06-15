from __future__ import annotations

from random import Random
from types import SimpleNamespace

from ai import task_router
from ai.behaviors import bounty_pursuit, exploration
from ai.basic_ai import BasicAI
from config import TILE_SIZE
from game.entities.hero import HeroState
from game.systems.bounty import Bounty


class _Hero:
    def __init__(
        self,
        hero_id: str,
        name: str,
        x: float,
        y: float,
        *,
        hp: int = 100,
        max_hp: int = 100,
    ) -> None:
        self.hero_id = hero_id
        self.name = name
        self.hero_class = "warrior"
        self.x = float(x)
        self.y = float(y)
        self.hp = int(hp)
        self.max_hp = int(max_hp)
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
        self._bounty_commit_until_ms = 0
        self._last_bounty_pick_ms = 0

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

    def add_gold(self, amount: int) -> None:
        _ = amount


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


def _make_view(hero: _Hero, bounty: Bounty, *, castle=None):
    return SimpleNamespace(
        world=None,
        buildings=[castle] if castle is not None else [],
        enemies=[],
        heroes=[hero],
        bounties=[bounty],
        pois=[],
        castle=castle,
        player_gold=0,
    )


def _start_bounty(ai: BasicAI, hero: _Hero, bounty: Bounty, view: SimpleNamespace) -> None:
    bounty_pursuit.start_bounty_pursuit(ai, hero, bounty, view)
    hero.state = HeroState.IDLE


def test_bounty_commitment_survives_transient_idle_and_home_rest(monkeypatch) -> None:
    ai = _make_ai()
    hero = _Hero("bounty", "Bram", 10 * TILE_SIZE, 10 * TILE_SIZE)
    hero._should_rest = True
    hero._can_rest_at_home = True
    bounty = Bounty(16 * TILE_SIZE, 10 * TILE_SIZE, reward=100, bounty_type="explore")
    view = _make_view(hero, bounty, castle=SimpleNamespace(center_x=10 * TILE_SIZE, center_y=10 * TILE_SIZE))
    sent_home: list[str] = []

    monkeypatch.setattr("ai.behaviors.bounty_pursuit.sim_now_ms", lambda: 1_000)
    monkeypatch.setattr("ai.task_router.sim_now_ms", lambda: 1_000)
    monkeypatch.setattr(ai, "handle_idle", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("idle should not run")))
    monkeypatch.setattr(ai, "send_home_to_rest", lambda hero_obj, _view: sent_home.append(hero_obj.name))

    _start_bounty(ai, hero, bounty, view)
    task_router.update_hero(ai, hero, 1 / 60, view)

    assert sent_home == []
    assert hero.state == HeroState.MOVING
    assert isinstance(hero.target, dict)
    assert hero.target["type"] == "bounty"
    assert bounty_pursuit.bounty_commitment_active(hero, view, now_ms=1_000) is True


def test_bounty_commitment_yields_to_urgent_survival(monkeypatch) -> None:
    ai = _make_ai()
    hero = _Hero("survival", "Sora", 10 * TILE_SIZE, 10 * TILE_SIZE, hp=18, max_hp=100)
    hero._should_rest = True
    hero._can_rest_at_home = True
    bounty = Bounty(16 * TILE_SIZE, 10 * TILE_SIZE, reward=100, bounty_type="explore")
    view = _make_view(hero, bounty, castle=SimpleNamespace(center_x=10 * TILE_SIZE, center_y=10 * TILE_SIZE))
    sent_home: list[str] = []

    monkeypatch.setattr("ai.behaviors.bounty_pursuit.sim_now_ms", lambda: 1_000)
    monkeypatch.setattr("ai.task_router.sim_now_ms", lambda: 1_000)
    monkeypatch.setattr(ai, "handle_idle", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("idle should not run")))
    monkeypatch.setattr(ai, "send_home_to_rest", lambda hero_obj, _view: sent_home.append(hero_obj.name))

    _start_bounty(ai, hero, bounty, view)
    task_router.update_hero(ai, hero, 1 / 60, view)

    assert sent_home == ["Sora"]
    assert bounty_pursuit.bounty_commitment_active(hero, view, now_ms=1_000) is False


def test_bounty_commitment_ends_on_invalidation_or_timeout(monkeypatch) -> None:
    ai = _make_ai()
    hero = _Hero("ending", "Tara", 10 * TILE_SIZE, 10 * TILE_SIZE)
    bounty = Bounty(16 * TILE_SIZE, 10 * TILE_SIZE, reward=100, bounty_type="explore")
    view = _make_view(hero, bounty, castle=SimpleNamespace(center_x=10 * TILE_SIZE, center_y=10 * TILE_SIZE))

    monkeypatch.setattr("ai.behaviors.bounty_pursuit.sim_now_ms", lambda: 1_000)

    _start_bounty(ai, hero, bounty, view)
    bounty.claimed = True
    assert bounty_pursuit.bounty_commitment_active(hero, view, now_ms=1_000) is False
    assert bounty_pursuit.resume_committed_bounty(ai, hero, view) is False
    assert exploration._idle_clear_dangling_bounty(ai, hero, view) is False
    assert hero.target is None
    assert hero.target_position is None

    _start_bounty(ai, hero, bounty, view)
    hero._bounty_commit_until_ms = 500
    bounty.claimed = False
    assert bounty_pursuit.bounty_commitment_active(hero, view, now_ms=1_000) is False
    assert bounty_pursuit.resume_committed_bounty(ai, hero, view) is False
    assert exploration._idle_clear_dangling_bounty(ai, hero, view) is False
    assert hero.target is None
    assert hero.target_position is None
