"""
WK50 R17: End-to-end direct prompt integration — ContextBuilder → mock provider →
validate_direct_prompt_output → apply_validated_direct_prompt_physical.

Catches false refusals (e.g. buy potions with gold + known market) that only show up
when the full hero_context is applied.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from ai.context_builder import ContextBuilder
from ai.direct_prompt_validator import validate_direct_prompt_output
from ai.llm_brain import LLMBrain
from ai.prompt_packs import build_direct_prompt_messages
from ai.providers.mock_provider import MockProvider
from config import MAP_HEIGHT, MAP_WIDTH, TILE_SIZE
from game.entities import Inn, RangerGuild
from game.entities.buildings.economic import Marketplace
from game.entities.hero import Hero
from game.sim.direct_prompt_commit import DIRECT_PROMPT_TARGET_TYPE
from game.sim.direct_prompt_exec import apply_validated_direct_prompt_physical
from game.sim.timebase import set_sim_now_ms


def _drain_conversation(brain: LLMBrain, hero_key: str, *, max_wait_s: float = 4.0) -> dict | None:
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        r = brain.get_conversation_response(hero_key)
        if r is not None:
            return r
        time.sleep(0.01)
    return None


def _base_layout():
    cx, cy = MAP_WIDTH // 2 - 1, MAP_HEIGHT // 2 - 1
    ranger_guild = RangerGuild(cx - 6, cy + 8)
    market = Marketplace(cx + 40, cy + 40)
    market.potions_researched = True
    market.potion_price = 15
    return cx, cy, ranger_guild, market


def _game_state(hero: Hero, buildings: list, world_size: tuple[int, int] | None = None):
    w, h = world_size if world_size else (MAP_WIDTH, MAP_HEIGHT)
    return {
        "heroes": [hero],
        "buildings": buildings,
        "enemies": [],
        "bounties": [],
        "castle": None,
        "world": SimpleNamespace(width=w, height=h),
    }


def _assert_no_false_refusal(out: dict) -> None:
    assert out.get("refusal_reason") in ("", None), f"unexpected refusal: {out.get('refusal_reason')}"
    assert out.get("obey_defy") == "Obey", f"expected Obey, got {out.get('obey_defy')!r} body={out!r}"
    if str(out.get("interpreted_intent") or "") != "status_report":
        assert out.get("tool_action") is not None, f"expected a physical tool, got {out!r}"


@pytest.fixture(autouse=True)
def _sim_clock():
    set_sim_now_ms(10_000)
    try:
        yield
    finally:
        set_sim_now_ms(None)


def test_integration_buy_potions_far_from_market_remembers_shop_llm_brain():
    """Ranger with 25g, marketplace in memory, far away — should march to shop (not refuse)."""
    _, _, ranger_guild, market = _base_layout()
    hero = Hero(
        float(ranger_guild.center_x),
        float(ranger_guild.center_y),
        hero_class="ranger",
        hero_id="dp_far_shop",
        name="RangerNova",
    )
    hero.home_building = ranger_guild
    hero.gold = 25
    hero.remember_known_place(
        place_type="marketplace",
        display_name="Market",
        tile=(market.grid_x, market.grid_y),
        world_pos=(market.center_x, market.center_y),
        sim_time_ms=10_000,
        building_type="marketplace",
        grid_x=market.grid_x,
        grid_y=market.grid_y,
    )
    gs = _game_state(hero, [ranger_guild, market])
    ctx = ContextBuilder.build_hero_context(hero, gs)
    assert ctx["situation"]["can_shop"] is False

    brain = LLMBrain(provider_name="mock")
    try:
        brain.request_conversation(hero.name, ctx, [], "buy potions sovereign")
        out = _drain_conversation(brain, hero.name)
        assert out is not None, "conversation timeout"
        _assert_no_false_refusal(out)
        assert out["interpreted_intent"] in ("buy_potions", "go_to_known_place") or out["tool_action"] in (
            "move_to",
            "buy_item",
        )
        assert out["tool_action"] == "move_to"
    finally:
        brain.stop()

    class _FakeAI:
        def set_intent(self, hero, label: str) -> None:
            hero.intent = label

        def record_decision(self, hero, **kwargs) -> None:
            pass

    hero2 = Hero(
        float(ranger_guild.center_x),
        float(ranger_guild.center_y),
        hero_class="ranger",
        hero_id="dp_far_shop2",
        name="RangerNova",
    )
    hero2.home_building = ranger_guild
    hero2.gold = 25
    hero2.remember_known_place(
        place_type="marketplace",
        display_name="Market",
        tile=(market.grid_x, market.grid_y),
        world_pos=(market.center_x, market.center_y),
        sim_time_ms=10_000,
        building_type="marketplace",
        grid_x=market.grid_x,
        grid_y=market.grid_y,
    )
    gs2 = _game_state(hero2, [ranger_guild, market])
    ctx2 = ContextBuilder.build_hero_context(hero2, gs2)
    sys_p, user_p = build_direct_prompt_messages(ctx2, [], "buy potions")
    raw = json.loads(MockProvider().complete(sys_p, user_p))
    validated = validate_direct_prompt_output(raw, ctx2, "buy potions")
    assert apply_validated_direct_prompt_physical(
        _FakeAI(), hero2, validated, gs2, player_message="buy potions", source="chat"
    )
    assert isinstance(hero2.target, dict)
    assert hero2.target.get("type") == DIRECT_PROMPT_TARGET_TYPE
    assert hero2.target.get("sub_intent") == "buy_potions"


def test_integration_buy_potions_adjacent_to_market_affordable_llm_brain():
    """Hero at marketplace with 25g and 15g potions — must not false-refuse (WK50-BUG-008)."""
    _, _, ranger_guild, market = _base_layout()
    hero = Hero(
        float(market.center_x) + TILE_SIZE * 2,
        float(market.center_y),
        hero_class="ranger",
        hero_id="dp_near_shop",
        name="RangerEdge",
    )
    hero.home_building = ranger_guild
    hero.gold = 25
    hero.remember_known_place(
        place_type="marketplace",
        display_name="Market",
        tile=(market.grid_x, market.grid_y),
        world_pos=(market.center_x, market.center_y),
        sim_time_ms=10_000,
        building_type="marketplace",
        grid_x=market.grid_x,
        grid_y=market.grid_y,
    )
    gs = _game_state(hero, [ranger_guild, market])
    ctx = ContextBuilder.build_hero_context(hero, gs)
    assert ctx["situation"]["can_shop"] is True
    assert any("potion" in str(i.get("name", "")).lower() for i in ctx.get("shop_items", []))

    brain = LLMBrain(provider_name="mock")
    try:
        brain.request_conversation(hero.name, ctx, [], "buy potions please")
        out = _drain_conversation(brain, hero.name)
        assert out is not None
        _assert_no_false_refusal(out)
        assert out["tool_action"] == "buy_item"
        assert out["interpreted_intent"] == "buy_potions"
    finally:
        brain.stop()


def test_validator_promotes_buy_potions_to_buy_item_when_in_range():
    """If mock/pre-step emitted move_to, full hero_context should still resolve buy_item in range."""
    _, _, ranger_guild, market = _base_layout()
    hero = Hero(
        float(market.center_x),
        float(market.center_y),
        hero_class="ranger",
        hero_id="dp_promo",
        name="RangerPromo",
    )
    hero.home_building = ranger_guild
    hero.gold = 25
    gs = _game_state(hero, [ranger_guild, market])
    ctx = ContextBuilder.build_hero_context(hero, gs)
    raw_llm = {
        "spoken_response": "Stocking up.",
        "interpreted_intent": "buy_potions",
        "tool_action": "move_to",
        "target_kind": "known_place",
        "target_id": "",
        "target_description": "Market",
        "obey_defy": "Obey",
        "refusal_reason": "",
        "safety_assessment": "safe",
        "confidence": 0.9,
    }
    out = validate_direct_prompt_output(raw_llm, ctx, "buy potions")
    assert out["tool_action"] == "buy_item"
    assert out["obey_defy"] == "Obey"


def test_integration_go_home_ranger_llm_brain_and_exec():
    from ai.basic_ai import BasicAI

    _, _, ranger_guild, market = _base_layout()
    hero = Hero(
        float(market.center_x) + 200.0,
        float(market.center_y) + 200.0,
        hero_class="ranger",
        hero_id="dp_home",
        name="RangerHome",
    )
    hero.home_building = ranger_guild
    hero.gold = 30
    gs = _game_state(hero, [ranger_guild, market])
    ctx = ContextBuilder.build_hero_context(hero, gs)

    brain = LLMBrain(provider_name="mock")
    try:
        brain.request_conversation(hero.name, ctx, [], "go home")
        out = _drain_conversation(brain, hero.name)
        assert out is not None
        _assert_no_false_refusal(out)
        assert out["tool_action"] == "move_to"
        assert out["interpreted_intent"] == "return_home"
    finally:
        brain.stop()

    ai = BasicAI(llm_brain=None)
    sys_p, user_p = build_direct_prompt_messages(ctx, [], "go home")
    validated = validate_direct_prompt_output(json.loads(MockProvider().complete(sys_p, user_p)), ctx, "go home")
    assert apply_validated_direct_prompt_physical(
        ai, hero, validated, gs, player_message="go home", source="chat"
    )
    assert isinstance(hero.target, dict) and hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE


def test_integration_explore_east_llm_brain_and_exec():
    from game.entities.hero import HeroState

    _, _, ranger_guild, market = _base_layout()
    hero = Hero(
        float(ranger_guild.center_x),
        float(ranger_guild.center_y),
        hero_class="ranger",
        hero_id="dp_east",
        name="RangerEast",
    )
    hero.home_building = ranger_guild
    hero.state = HeroState.IDLE
    gs = _game_state(hero, [ranger_guild, market], world_size=(24, 24))

    ctx = ContextBuilder.build_hero_context(hero, gs)
    brain = LLMBrain(provider_name="mock")
    try:
        brain.request_conversation(hero.name, ctx, [], "explore east")
        out = _drain_conversation(brain, hero.name)
        assert out is not None
        _assert_no_false_refusal(out)
        assert out["tool_action"] == "explore"
        assert out["interpreted_intent"] == "explore_direction"
    finally:
        brain.stop()

    class _FakeAI:
        def set_intent(self, hero, label: str) -> None:
            hero.intent = label

        def record_decision(self, hero, **kwargs) -> None:
            pass

    sys_p, user_p = build_direct_prompt_messages(ctx, [], "explore east")
    validated = validate_direct_prompt_output(json.loads(MockProvider().complete(sys_p, user_p)), ctx, "explore east")
    assert apply_validated_direct_prompt_physical(
        _FakeAI(), hero, validated, gs, player_message="explore east", source="chat"
    )
    assert hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE
    assert hero.target.get("sub_intent") == "explore_direction"


def test_integration_status_report_llm_brain():
    _, _, ranger_guild, market = _base_layout()
    hero = Hero(
        float(ranger_guild.center_x),
        float(ranger_guild.center_y),
        hero_class="ranger",
        hero_id="dp_stat",
        name="RangerStat",
    )
    hero.home_building = ranger_guild
    gs = _game_state(hero, [ranger_guild, market])
    ctx = ContextBuilder.build_hero_context(hero, gs)

    brain = LLMBrain(provider_name="mock")
    try:
        brain.request_conversation(hero.name, ctx, [], "how are you doing?")
        out = _drain_conversation(brain, hero.name)
        assert out is not None
        assert out["interpreted_intent"] == "status_report"
        assert out["tool_action"] is None
        assert out["obey_defy"] == "Obey"
    finally:
        brain.stop()


def test_integration_seek_healing_llm_brain():
    _, _, ranger_guild, market = _base_layout()
    hero = Hero(
        float(ranger_guild.center_x),
        float(ranger_guild.center_y),
        hero_class="ranger",
        hero_id="dp_heal",
        name="RangerHeal",
    )
    hero.home_building = ranger_guild
    hero.hp = max(1, hero.max_hp // 3)
    gs = _game_state(hero, [ranger_guild, market])
    ctx = ContextBuilder.build_hero_context(hero, gs)

    brain = LLMBrain(provider_name="mock")
    try:
        brain.request_conversation(hero.name, ctx, [], "I need healing")
        out = _drain_conversation(brain, hero.name)
        assert out is not None
        assert out["interpreted_intent"] == "seek_healing"
        _assert_no_false_refusal(out)
        assert out["tool_action"] in ("use_potion", "retreat", "move_to")
    finally:
        brain.stop()


def test_integration_go_to_inn_llm_brain():
    cx, cy, ranger_guild, market = _base_layout()
    inn = Inn(cx + 5, cy - 5)
    hero = Hero(
        float(ranger_guild.center_x),
        float(ranger_guild.center_y),
        hero_class="ranger",
        hero_id="dp_inn",
        name="RangerInn",
    )
    hero.home_building = ranger_guild
    hero.remember_known_place(
        place_type="inn",
        display_name="The Inn",
        tile=(inn.grid_x, inn.grid_y),
        world_pos=(inn.center_x, inn.center_y),
        sim_time_ms=10_000,
        building_type="inn",
        grid_x=inn.grid_x,
        grid_y=inn.grid_y,
    )
    gs = _game_state(hero, [ranger_guild, market, inn])
    ctx = ContextBuilder.build_hero_context(hero, gs)

    brain = LLMBrain(provider_name="mock")
    try:
        brain.request_conversation(hero.name, ctx, [], "go to the inn")
        out = _drain_conversation(brain, hero.name)
        assert out is not None
        _assert_no_false_refusal(out)
        assert out["interpreted_intent"] == "go_to_known_place"
        assert out["tool_action"] == "move_to"
    finally:
        brain.stop()


def test_integration_rest_until_healed_llm_brain():
    _, _, ranger_guild, market = _base_layout()
    hero = Hero(
        float(ranger_guild.center_x),
        float(ranger_guild.center_y),
        hero_class="ranger",
        hero_id="dp_rest",
        name="RangerRest",
    )
    hero.home_building = ranger_guild
    hero.hp = max(1, hero.max_hp // 2)
    gs = _game_state(hero, [ranger_guild, market])
    ctx = ContextBuilder.build_hero_context(hero, gs)

    brain = LLMBrain(provider_name="mock")
    try:
        brain.request_conversation(hero.name, ctx, [], "rest until healed")
        out = _drain_conversation(brain, hero.name)
        assert out is not None
        # Mock matches plain "heal" before "rest … heal" — phrase hits seek_healing first; still must Obey.
        assert out["interpreted_intent"] in ("rest_until_healed", "seek_healing")
        _assert_no_false_refusal(out)
    finally:
        brain.stop()


def test_validator_rest_until_healed_outdoors_moves_toward_home():
    """rest_until_healed intent with full context (no mock ordering)."""
    from ai.basic_ai import BasicAI

    _, _, ranger_guild, market = _base_layout()
    hero = Hero(
        float(ranger_guild.center_x),
        float(ranger_guild.center_y),
        hero_class="ranger",
        hero_id="dp_rest_val",
        name="RangerRestV",
    )
    hero.home_building = ranger_guild
    gs = _game_state(hero, [ranger_guild, market])
    ctx = ContextBuilder.build_hero_context(hero, gs)
    raw = {
        "spoken_response": "I'll rest.",
        "interpreted_intent": "rest_until_healed",
        "tool_action": None,
        "obey_defy": "Obey",
        "refusal_reason": "",
        "safety_assessment": "safe",
    }
    out = validate_direct_prompt_output(raw, ctx, "rest until healed")
    assert out["interpreted_intent"] == "rest_until_healed"
    _assert_no_false_refusal(out)
    ai = BasicAI(llm_brain=None)
    assert apply_validated_direct_prompt_physical(
        ai, hero, out, gs, player_message="rest until healed", source="chat"
    )
    assert isinstance(hero.target, dict)
    assert hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE


def test_integration_attack_lair_refuses_mvp():
    _, _, ranger_guild, market = _base_layout()
    hero = Hero(
        float(ranger_guild.center_x),
        float(ranger_guild.center_y),
        hero_class="ranger",
        hero_id="dp_atk",
        name="RangerAtk",
    )
    hero.home_building = ranger_guild
    gs = _game_state(hero, [ranger_guild, market])
    ctx = ContextBuilder.build_hero_context(hero, gs)

    brain = LLMBrain(provider_name="mock")
    try:
        brain.request_conversation(hero.name, ctx, [], "attack the lair now")
        out = _drain_conversation(brain, hero.name)
        assert out is not None
        assert out["interpreted_intent"] == "no_action_chat_only"
        assert out["tool_action"] is None
        assert out["obey_defy"] == "Defy"
    finally:
        brain.stop()
