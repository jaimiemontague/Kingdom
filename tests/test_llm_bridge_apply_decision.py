"""Regression: apply_llm_decision uses HeroState (fight / leave_building / move_to paths)."""

from __future__ import annotations

from types import SimpleNamespace

from ai.behaviors.llm_bridge import apply_llm_decision
from game.entities.hero import Hero, HeroState


def _market(x: float, y: float) -> SimpleNamespace:
    return SimpleNamespace(center_x=x, center_y=y, building_type="marketplace", hp=100)


class _FakeAI:
    def __init__(self) -> None:
        self.explore_calls = 0
        self.defense_behavior = SimpleNamespace(start_retreat=lambda *a, **k: None)
        self.shopping_behavior = SimpleNamespace(go_shopping=lambda *a, **k: None)
        self.exploration_behavior = SimpleNamespace(explore=self._explore)
        self.llm_brain = None

    def _explore(self, ai, hero, game_state):
        self.explore_calls += 1

    def set_intent(self, hero, label: str) -> None:
        hero.intent = label

    def record_decision(self, hero, **kwargs) -> None:
        pass

    def _debug_log(self, msg: str, throttle_key: str = "") -> None:
        pass


def test_apply_fight_sets_fighting_state():
    ai = _FakeAI()
    hero = Hero(0.0, 0.0, name="T", hero_id="t_fight")
    hero.state = HeroState.IDLE
    gs: dict = {"buildings": [], "enemies": [], "heroes": [hero], "bounties": []}
    apply_llm_decision(ai, hero, {"action": "fight"}, gs, source="mock")
    assert hero.state == HeroState.FIGHTING


def test_apply_leave_building_sets_idle_state():
    ai = _FakeAI()
    hero = Hero(10.0, 10.0, name="T", hero_id="t_leave")
    hero.state = HeroState.RESTING
    hero.is_inside_building = True
    gs: dict = {"buildings": [], "enemies": [], "heroes": [hero], "bounties": []}
    apply_llm_decision(ai, hero, {"action": "leave_building", "tool_action": "leave_building"}, gs, source="mock")
    assert hero.state == HeroState.IDLE
    assert hero.is_inside_building is False


def test_apply_move_to_resolved_sets_llm_move_request():
    ai = _FakeAI()
    hero = Hero(0.0, 0.0, name="T", hero_id="t_move")
    hero.state = HeroState.IDLE
    m = _market(100.0, 200.0)
    gs: dict = {"buildings": [m], "enemies": [], "heroes": [hero], "bounties": []}
    apply_llm_decision(ai, hero, {"action": "move_to", "target": "market"}, gs, source="mock")
    assert hero.llm_move_request == (100.0, 200.0)
    assert ai.explore_calls == 0


def test_apply_move_to_unresolved_falls_back_to_explore():
    ai = _FakeAI()
    hero = Hero(0.0, 0.0, name="T", hero_id="t_move_fb")
    hero.state = HeroState.IDLE
    gs: dict = {"buildings": [], "enemies": [], "heroes": [hero], "bounties": []}
    apply_llm_decision(ai, hero, {"action": "move_to", "target": "castle"}, gs, source="mock")
    assert hero.llm_move_request is None
    assert ai.explore_calls == 1
