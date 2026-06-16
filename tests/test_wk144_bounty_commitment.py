from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai import task_router
from ai.basic_ai import BasicAI
from ai.behaviors import bounty_pursuit
from config import TILE_SIZE
from game.entities.hero import HeroState
from game.systems.bounty import Bounty


class _FixedRNG:
    def random(self) -> float:
        return 0.99

    def uniform(self, a: float, b: float) -> float:
        return (float(a) + float(b)) / 2.0


class _Hero:
    def __init__(
        self,
        hero_id: str = "hero-1",
        name: str = "Aerin",
        *,
        x: float = 0.0,
        y: float = 0.0,
        hp: int = 100,
        max_hp: int = 100,
    ) -> None:
        self.hero_id = hero_id
        self.name = name
        self.hero_class = "warrior"
        self.personality = "balanced and reliable"
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


def _make_ai(monkeypatch) -> BasicAI:
    ai = BasicAI(llm_brain=None)
    ai._ai_rng = _FixedRNG()
    ai._debug_log = lambda *_a, **_k: None
    ai.stuck_recovery_behavior._update_stuck_and_recover = lambda *_a, **_k: None
    ai.defense_behavior.building_threatened = lambda *_a, **_k: False
    ai.defense_behavior.defend_castle = lambda *_a, **_k: None
    ai.defense_behavior.defend_economic_building_warrior = lambda *_a, **_k: False
    ai.defense_behavior.defend_home_building = lambda *_a, **_k: None
    ai.defense_behavior.defend_neutral_building_if_visible = lambda *_a, **_k: False
    monkeypatch.setattr(ai.hunger_behavior, "tick_meal_hunger", lambda *_a, **_k: False)
    monkeypatch.setattr(ai.llm_bridge_behavior, "should_consult_llm", lambda *_a, **_k: False)
    monkeypatch.setattr(task_router.quest_offer, "maybe_approach_quest_giver", lambda *_a, **_k: None)
    return ai


def _make_view(hero: _Hero, bounty: Bounty, *, castle=None) -> SimpleNamespace:
    buildings = [castle] if castle is not None else []
    return SimpleNamespace(
        world=None,
        buildings=buildings,
        enemies=[],
        heroes=[hero],
        bounties=[bounty],
        pois=[],
        castle=castle,
        quest_givers=[],
    )


def _start_bounty(ai: BasicAI, hero: _Hero, bounty: Bounty, view: SimpleNamespace) -> None:
    bounty_pursuit.start_bounty_pursuit(ai, hero, bounty, view)


def test_live_bounty_commitment_preempts_resting_and_home_route(monkeypatch) -> None:
    ai = _make_ai(monkeypatch)
    hero = _Hero("bounty", "Bram", x=10 * TILE_SIZE, y=10 * TILE_SIZE)
    hero._should_rest = True
    hero._can_rest_at_home = True
    bounty = Bounty(16 * TILE_SIZE, 10 * TILE_SIZE, reward=100, bounty_type="explore")
    view = _make_view(hero, bounty, castle=SimpleNamespace(center_x=10 * TILE_SIZE, center_y=10 * TILE_SIZE))
    sent_home: list[str] = []

    monkeypatch.setattr("ai.behaviors.bounty_pursuit.sim_now_ms", lambda: 1_000)
    monkeypatch.setattr("ai.task_router.sim_now_ms", lambda: 1_000)

    _start_bounty(ai, hero, bounty, view)
    hero.state = HeroState.RESTING
    hero.intent = "returning_to_safety"
    hero.target_position = (0.0, 0.0)

    monkeypatch.setattr(ai, "handle_resting", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("rest should not run")))
    monkeypatch.setattr(ai, "handle_idle", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("idle should not run")))
    monkeypatch.setattr(ai, "send_home_to_rest", lambda hero_obj, _view: sent_home.append(hero_obj.name))

    task_router.update_hero(ai, hero, 1 / 60, view)

    assert sent_home == []
    assert hero.state == HeroState.MOVING
    assert hero.target["type"] == "bounty"
    assert hero.target_position == (16 * TILE_SIZE, 10 * TILE_SIZE)
    assert hero.intent == "pursuing_bounty"


def test_resume_committed_bounty_reasserts_target_position_and_intent(monkeypatch) -> None:
    ai = _make_ai(monkeypatch)
    hero = _Hero("resume", "Rana", x=2 * TILE_SIZE, y=2 * TILE_SIZE)
    bounty = Bounty(6 * TILE_SIZE, 4 * TILE_SIZE, reward=120, bounty_type="explore")
    view = _make_view(hero, bounty)

    monkeypatch.setattr("ai.behaviors.bounty_pursuit.sim_now_ms", lambda: 2_000)
    _start_bounty(ai, hero, bounty, view)

    hero.state = HeroState.IDLE
    hero.intent = "returning_to_safety"
    hero.target_position = (0.0, 0.0)
    hero._bounty_commit_until_ms = 10_000

    assert bounty_pursuit.resume_committed_bounty(ai, hero, view) is True
    assert hero.state == HeroState.MOVING
    assert hero.target["type"] == "bounty"
    assert hero.target_position == (6 * TILE_SIZE, 4 * TILE_SIZE)
    assert hero.intent == "pursuing_bounty"


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("claimed", "claimed"),
        ("expired", "timeout"),
        ("invalid", "invalid"),
    ],
)
def test_stale_claimed_or_invalid_bounty_is_not_resumed(monkeypatch, setup: str, reason: str) -> None:
    ai = _make_ai(monkeypatch)
    hero = _Hero("stale", "Sera", x=5 * TILE_SIZE, y=5 * TILE_SIZE)
    hero.target_position = (1.0, 1.0)
    bounty = Bounty(8 * TILE_SIZE, 6 * TILE_SIZE, reward=90, bounty_type="explore")
    if setup == "invalid":
        bounty = Bounty(8 * TILE_SIZE, 6 * TILE_SIZE, reward=90, bounty_type="attack_lair")
        hero.target_position = (1.0, 1.0)
    view = _make_view(hero, bounty)

    monkeypatch.setattr("ai.behaviors.bounty_pursuit.sim_now_ms", lambda: 3_000)
    _start_bounty(ai, hero, bounty, view)

    if setup == "claimed":
        bounty.claimed = True
    elif setup == "expired":
        hero._bounty_commit_until_ms = 2_000
    elif setup == "invalid":
        bounty.target = None

    hero.state = HeroState.IDLE
    hero.intent = "returning_to_safety"
    before_target_position = hero.target_position

    assert bounty_pursuit.bounty_commitment_active(hero, view, now_ms=3_000) is False
    assert bounty_pursuit.resume_committed_bounty(ai, hero, view) is False
    assert hero.target_position == before_target_position
    assert hero.state == HeroState.IDLE
    assert hero.intent == "returning_to_safety"
