"""WK50 Phase 2A: decision moments, profile context adapter, prompts, validator."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

from ai.behaviors import llm_bridge
from ai.context_builder import ContextBuilder
from ai.decision_moments import (
    DecisionMomentType,
    consult_suppressed_by_request_state,
    decision_moment_from_prompt_dict,
    determine_decision_moment,
    moment_low_health_combat,
)
from ai.llm_brain import LLMBrain
from ai.decision_output_validator import validate_autonomous_decision
from ai.prompt_packs import AUTONOMOUS_SYSTEM_PROMPT, build_autonomous_user_prompt
from ai.profile_context_adapter import build_llm_context_for_moment
from config import LLM_DECISION_COOLDOWN, TILE_SIZE
from game.entities.hero import Hero, HeroState


def _market(x: float, y: float) -> SimpleNamespace:
    return SimpleNamespace(center_x=x, center_y=y, building_type="marketplace", hp=100)


def _enemy(x: float, y: float, *, alive: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        x=x,
        y=y,
        is_alive=alive,
        enemy_type="goblin",
        target=None,
        hp=20,
        max_hp=20,
        attack_power=2,
    )


def test_low_health_combat_moment_only_allowed_actions():
    h = Hero(0.0, 0.0, name="Test", hero_id="t1")
    h.state = HeroState.FIGHTING
    h.hp = 20
    h.max_hp = 100
    m = moment_low_health_combat(h)
    assert m is not None
    assert m.moment_type == DecisionMomentType.LOW_HEALTH_COMBAT
    assert set(m.allowed_actions) == {"fight", "retreat", "use_potion"}


def test_determine_moment_priority_low_health_over_shopping():
    h = Hero(50.0, 50.0, name="Test", hero_id="t2")
    h.state = HeroState.FIGHTING
    h.hp = 20
    h.max_hp = 100
    h.gold = 100
    gs = {"buildings": [_market(50.0, 50.0)], "enemies": [], "heroes": [h], "bounties": []}
    m = determine_decision_moment(h, gs, now_ms=10_000)
    assert m is not None
    assert m.moment_type == DecisionMomentType.LOW_HEALTH_COMBAT


def test_post_combat_injured_requires_signal_and_uses_profile_memory():
    h = Hero(100.0, 100.0, name="Test", hero_id="t3")
    h.state = HeroState.IDLE
    h.hp = 40
    h.max_hp = 100
    h.potions = 0
    h.target = None
    h.record_profile_memory(
        event_type="combat_end",
        sim_time_ms=9_000,
        summary="Survived a skirmish",
        tags=("combat",),
        importance=2,
    )
    gs = {"buildings": [], "enemies": [], "heroes": [h], "bounties": []}
    m = determine_decision_moment(h, gs, now_ms=10_000)
    assert m is not None
    assert m.moment_type == DecisionMomentType.POST_COMBAT_INJURED
    assert "move_to" in m.allowed_actions


def test_consult_suppressed_cooldown_and_pending():
    h = Hero(0.0, 0.0, name="Test", hero_id="t4")
    h.last_llm_decision_time = 100
    h.pending_llm_decision = False
    assert consult_suppressed_by_request_state(h, now_ms=100, cooldown_ms=1000) == "cooldown"
    h.last_llm_decision_time = 0
    h.pending_llm_decision = True
    assert consult_suppressed_by_request_state(h, now_ms=5000, cooldown_ms=LLM_DECISION_COOLDOWN) == "pending_request"


def test_validator_rejects_disallowed_action_and_accepts_valid():
    from ai.decision_moments import DecisionMoment

    moment = DecisionMoment(
        moment_type=DecisionMomentType.LOW_HEALTH_COMBAT,
        urgency=1,
        reason="test",
        allowed_actions=("fight", "retreat", "use_potion"),
        context_focus=(),
        cooldown_ms=1000,
    )
    assert validate_autonomous_decision({"action": "explore"}, moment) is None
    good = validate_autonomous_decision(
        {"action": "retreat", "target": "", "reasoning": "flee", "confidence": 0.9},
        moment,
    )
    assert good is not None
    assert good["action"] == "retreat"


def test_validator_requires_target_for_move_to():
    from ai.decision_moments import DecisionMoment

    moment = DecisionMoment(
        moment_type=DecisionMomentType.POST_COMBAT_INJURED,
        urgency=0,
        reason="test",
        allowed_actions=("move_to", "use_potion"),
        context_focus=(),
        cooldown_ms=1,
    )
    assert validate_autonomous_decision({"action": "move_to", "target": ""}, moment) is None
    ok = validate_autonomous_decision({"action": "move_to", "target": "castle"}, moment)
    assert ok is not None
    assert ok["target"] == "castle"


def test_autonomous_prompt_pack_strings():
    assert "identity" in AUTONOMOUS_SYSTEM_PROMPT
    assert "current situation" in AUTONOMOUS_SYSTEM_PROMPT
    assert "known places" in AUTONOMOUS_SYSTEM_PROMPT
    assert "allowed_actions" in AUTONOMOUS_SYSTEM_PROMPT
    assert "JSON" in AUTONOMOUS_SYSTEM_PROMPT
    ctx = {
        "moment": {"type": "low_health_combat", "allowed_actions": ["fight"]},
        "allowed_actions": ["fight", "retreat"],
        "hero_profile": {"identity": {"name": "Aria"}},
        "current_situation": {},
        "known_places": [],
        "recent_memory": [],
    }
    up = build_autonomous_user_prompt(ctx)
    assert "Aria" in up
    assert "retreat" in up
    json.loads(up.split("\n\nRespond")[0].strip())


def test_autonomous_user_prompt_embeddings_include_situation_and_known_places():
    h = Hero(10.0, 10.0, name="PromptHero", hero_id="ph1")
    h.state = HeroState.FIGHTING
    h.hp = 20
    h.max_hp = 100
    h.remember_known_place(
        place_type="inn",
        display_name="Red Lion Inn",
        tile=(5, 5),
        world_pos=(200.0, 200.0),
        sim_time_ms=1000,
    )
    moment = moment_low_health_combat(h)
    assert moment is not None
    gs = {"buildings": [], "enemies": [_enemy(15.0, 10.0)], "heroes": [h], "bounties": []}
    ctx = build_llm_context_for_moment(h, gs, moment, now_ms=5000)
    up = build_autonomous_user_prompt(ctx)
    outer = json.loads(up.split("\n\nRespond")[0].strip())
    inner = outer["context"]
    assert outer["allowed_actions"] == ctx["allowed_actions"]
    assert "Red Lion Inn" in json.dumps(inner["known_places"])
    assert inner["moment"]["allowed_actions"] == list(moment.allowed_actions)
    assert "nearby_enemies" in inner["current_situation"]
    assert isinstance(inner["hero_profile"].get("identity"), dict)


def test_rested_and_ready_moment_when_resting_and_high_hp():
    h = Hero(0.0, 0.0, name="Resty", hero_id="rest1")
    h.state = HeroState.RESTING
    h.hp = 100
    h.max_hp = 100
    gs = {"buildings": [], "enemies": [], "heroes": [h], "bounties": []}
    m = determine_decision_moment(h, gs, now_ms=10_000)
    assert m is not None
    assert m.moment_type.name == "RESTED_AND_READY"
    assert "leave_building" in m.allowed_actions


def test_shopping_opportunity_when_idle_near_market_with_gold_need():
    px, py = 100.0, 100.0
    h = Hero(px, py, name="Shopper", hero_id="shop1")
    h.state = HeroState.IDLE
    h.hp = int(h.max_hp)
    h.gold = 100
    h.potions = 2
    gs = {"buildings": [_market(px, py)], "enemies": [], "heroes": [h], "bounties": []}
    m = determine_decision_moment(h, gs, now_ms=10_000)
    assert m is not None
    assert m.moment_type.name == "SHOPPING_OPPORTUNITY"
    assert "buy_item" in m.allowed_actions


def test_consult_suppression_cleared_when_ready():
    h = Hero(0.0, 0.0, name="Clr", hero_id="cclr")
    h.last_llm_decision_time = 0
    h.pending_llm_decision = False
    assert consult_suppressed_by_request_state(h, now_ms=5000, cooldown_ms=1000) is None


def test_profile_context_bounds_and_post_combat_memory_order():
    h = Hero(100.0, 100.0, name="Test", hero_id="t5")
    h.state = HeroState.IDLE
    h.hp = 40
    h.max_hp = 100
    h.potions = 0
    for i, imp in enumerate([1, 3, 2]):
        h.record_profile_memory(
            event_type="note",
            sim_time_ms=1000 + i,
            summary=f"ev{i}",
            importance=imp,
            tags=("combat",) if i == 0 else (),
        )
    gs = {"buildings": [], "enemies": [], "heroes": [h], "bounties": []}
    m = determine_decision_moment(h, gs, now_ms=5000)
    assert m is not None
    ctx = build_llm_context_for_moment(h, gs, m, now_ms=5000)
    assert len(ctx["known_places"]) <= 8
    assert len(ctx["recent_memory"]) <= 10
    assert "hero_profile" in ctx
    assert ctx["hero_profile"].get("known_places") is None
    assert "nearby_enemies" in ctx["current_situation"]


def test_post_combat_suppressed_when_enemy_on_top():
    h = Hero(0.0, 0.0, name="Test", hero_id="t6")
    h.state = HeroState.IDLE
    h.hp = 40
    h.max_hp = 100
    h.potions = 0
    h.record_profile_memory(event_type="hit", sim_time_ms=99_000, summary="ow", tags=("combat",))
    gs = {"buildings": [], "enemies": [_enemy(0.0, 0.0)], "heroes": [h], "bounties": []}
    m = determine_decision_moment(h, gs, now_ms=100_000)
    assert m is None or m.moment_type != DecisionMomentType.POST_COMBAT_INJURED


def test_decision_moment_from_prompt_dict_roundtrip():
    h = Hero(0.0, 0.0, name="R", hero_id="r1")
    h.state = HeroState.FIGHTING
    h.hp = 20
    h.max_hp = 100
    moment = moment_low_health_combat(h)
    assert moment is not None
    back = decision_moment_from_prompt_dict(moment.to_prompt_dict())
    assert back is not None
    assert back.moment_type == moment.moment_type
    assert back.allowed_actions == moment.allowed_actions


def test_should_consult_llm_named_moment_respects_cooldown_and_pending():
    from game.sim import timebase

    h = Hero(0.0, 0.0, name="Gate", hero_id="g1")
    h.state = HeroState.FIGHTING
    h.hp = 20
    h.max_hp = 100
    h.pending_llm_decision = False
    gs = {"buildings": [], "enemies": [], "heroes": [h], "bounties": []}
    moment_cd = 4_000  # LOW_HEALTH_COMBAT moment cooldown
    try:
        timebase.set_sim_now_ms(100_000)
        h.last_llm_decision_time = 0
        assert llm_bridge.should_consult_llm(None, h, gs) is True

        h.last_llm_decision_time = 100_000 - (moment_cd - 500)
        assert llm_bridge.should_consult_llm(None, h, gs) is False

        h.last_llm_decision_time = 0
        h.pending_llm_decision = True
        assert llm_bridge.should_consult_llm(None, h, gs) is False
    finally:
        timebase.set_sim_now_ms(None)


def test_llm_brain_autonomous_path_validates_against_moment():
    h = Hero(10.0, 10.0, name="Brainy", hero_id="b1")
    h.state = HeroState.FIGHTING
    h.hp = 20
    h.max_hp = 100
    h.potions = 2
    gs = {"buildings": [], "enemies": [], "heroes": [h], "bounties": []}
    moment = determine_decision_moment(h, gs, now_ms=50_000)
    assert moment is not None
    aut = build_llm_context_for_moment(h, gs, moment, now_ms=50_000)
    base = ContextBuilder.build_hero_context(h, gs)
    context = {**base, "wk50_autonomous": aut}
    brain = LLMBrain(provider_name="mock")

    brain.request_decision(h.name, context)
    decision = None
    for _ in range(100):
        decision = brain.get_decision(h.name)
        if decision:
            break
        time.sleep(0.02)
    brain.stop()
    assert decision is not None
    assert decision["action"] in moment.allowed_actions_set()


def test_llm_brain_autonomous_invalid_action_falls_back():
    h = Hero(10.0, 10.0, name="Brainy2", hero_id="b2")
    h.state = HeroState.FIGHTING
    h.hp = 20
    h.max_hp = 100
    h.potions = 2
    gs = {"buildings": [], "enemies": [], "heroes": [h], "bounties": []}
    moment = determine_decision_moment(h, gs, now_ms=50_000)
    assert moment is not None
    aut = build_llm_context_for_moment(h, gs, moment, now_ms=50_000)
    base = ContextBuilder.build_hero_context(h, gs)
    context = {**base, "wk50_autonomous": aut}

    class BadProvider:
        name = "bad"

        def complete(self, system_prompt: str, user_prompt: str, timeout: float = 5.0) -> str:
            return json.dumps(
                {
                    "action": "explore",
                    "target": "",
                    "reasoning": "disallowed for this moment",
                }
            )

    brain = LLMBrain(provider_name="mock")
    brain.provider = BadProvider()
    brain.request_decision(h.name, context)
    decision = None
    for _ in range(100):
        decision = brain.get_decision(h.name)
        if decision:
            break
        time.sleep(0.02)
    brain.stop()
    assert decision is not None
    assert decision["action"] == "use_potion"
    assert "Fallback" in decision.get("reasoning", "")
