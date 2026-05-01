"""WK50 Phase 2B: direct prompt schema, validator, prompt pack, mock provider."""

from __future__ import annotations

import json

from ai.direct_prompt_validator import (
    DEFERRED_COMBAT_INTENTS,
    SUPPORTED_DIRECT_INTENTS,
    validate_direct_prompt_output,
)
from ai.llm_brain import LLMBrain
from ai.prompt_packs import DIRECT_PROMPT_MARK, build_direct_prompt_messages, format_direct_system_prompt
from ai.providers.mock_provider import MockProvider


def _ctx(**overrides):
    base = {
        "hero": {
            "name": "Aldric",
            "class": "warrior",
            "level": 2,
            "hp": 80,
            "max_hp": 100,
            "health_percent": 80,
            "gold": 50,
        },
        "inventory": {"potions": 2},
        "situation": {
            "in_combat": False,
            "low_health": False,
            "critical_health": False,
            "has_potions": True,
            "can_shop": False,
            "near_safety": True,
        },
        "current_location": "outdoors",
        "distances": {"castle": 3.0, "marketplace": 12.0},
        "known_places_llm": [
            {
                "place_id": "castle:main",
                "place_type": "castle",
                "display_name": "Castle",
            },
            {
                "place_id": "inn:1",
                "place_type": "inn",
                "display_name": "The Inn",
            },
            {
                "place_id": "market:1",
                "place_type": "marketplace",
                "display_name": "Market",
            },
        ],
        "shop_items": [],
    }
    base.update(overrides)
    return base


def test_supported_intents_cover_plan_mvp():
    assert "status_report" in SUPPORTED_DIRECT_INTENTS
    assert "return_home" in SUPPORTED_DIRECT_INTENTS
    assert "attack_known_lair" not in SUPPORTED_DIRECT_INTENTS
    assert "attack_known_lair" in DEFERRED_COMBAT_INTENTS


def test_validator_defers_attack_lair():
    out = validate_direct_prompt_output(
        {
            "spoken_response": "I'll charge!",
            "interpreted_intent": "attack_known_lair",
            "tool_action": "fight",
        },
        _ctx(),
    )
    assert out["interpreted_intent"] == "no_action_chat_only"
    assert out["tool_action"] is None


def test_validator_strips_unknown_place_go_to():
    out = validate_direct_prompt_output(
        {
            "spoken_response": "Onward",
            "interpreted_intent": "go_to_known_place",
            "tool_action": "move_to",
            "target_id": "nowhere:xx",
            "target_description": "Moon",
        },
        _ctx(),
    )
    assert out["interpreted_intent"] == "no_action_chat_only"
    assert out["tool_action"] is None


def test_validator_critical_hp_redirects_explore():
    out = validate_direct_prompt_output(
        {
            "spoken_response": "I scout east!",
            "interpreted_intent": "explore_direction",
            "tool_action": "explore",
        },
        _ctx(
            situation={
                "in_combat": False,
                "low_health": True,
                "critical_health": True,
                "has_potions": True,
                "can_shop": False,
                "near_safety": False,
            }
        ),
    )
    assert out["interpreted_intent"] == "seek_healing"
    assert out["tool_action"] == "use_potion"


def test_explore_direction_requires_compass_in_player_message():
    out = validate_direct_prompt_output(
        {
            "spoken_response": "Scouting!",
            "interpreted_intent": "explore_direction",
            "tool_action": "explore",
        },
        _ctx(),
        "explore the frontier",
    )
    assert out["tool_action"] is None
    assert out["obey_defy"] == "Defy"
    assert out["refusal_reason"] == "unknown_heading"


def test_explore_direction_accepts_heading_in_player_message():
    out = validate_direct_prompt_output(
        {
            "spoken_response": "Eastward.",
            "interpreted_intent": "explore_direction",
            "tool_action": "explore",
        },
        _ctx(),
        "explore east please",
    )
    assert out["tool_action"] == "explore"
    assert out["obey_defy"] == "Obey"
    assert out["target_kind"] == "direction"
    assert out["target_description"] == "east"


def test_physical_tool_clears_refusal_and_forces_obey():
    out = validate_direct_prompt_output(
        {
            "spoken_response": "Nay",
            "interpreted_intent": "return_home",
            "tool_action": "move_to",
            "obey_defy": "Defy",
            "refusal_reason": "should_not_appear",
        },
        _ctx(),
    )
    assert out["tool_action"] == "move_to"
    assert out["obey_defy"] == "Obey"
    assert out["refusal_reason"] == ""


def test_buy_potions_no_potion_listing_at_shop():
    situation = {**_ctx()["situation"], "can_shop": True}
    out = validate_direct_prompt_output(
        {"interpreted_intent": "buy_potions", "tool_action": "buy_item"},
        _ctx(
            situation=situation,
            shop_items=[{"name": "Short Sword", "price": 10, "can_afford": True}],
        ),
    )
    assert out["tool_action"] is None
    assert out["refusal_reason"] == "no_potions_here"


def test_buy_potions_insufficient_gold_at_shop():
    situation = {**_ctx()["situation"], "can_shop": True}
    hero = {**_ctx()["hero"], "gold": 5}
    out = validate_direct_prompt_output(
        {"interpreted_intent": "buy_potions", "tool_action": "buy_item"},
        _ctx(
            situation=situation,
            hero=hero,
            shop_items=[{"name": "Health Potion", "price": 100, "can_afford": False}],
        ),
    )
    assert out["tool_action"] is None
    assert out["refusal_reason"] == "insufficient_gold"


def test_direct_prompt_system_mark_and_pack():
    hero_context = _ctx()
    sys_p, user_p = build_direct_prompt_messages(hero_context, [], "go home")
    assert DIRECT_PROMPT_MARK in sys_p
    assert "supported_intents" in user_p
    assert format_direct_system_prompt("Test").startswith(DIRECT_PROMPT_MARK)


def test_mock_provider_direct_phrases_deterministic():
    mp = MockProvider()
    hero_context = _ctx()
    sys_p, user_p = build_direct_prompt_messages(hero_context, [], "attack the lair")
    raw = mp.complete(sys_p, user_p)
    data = json.loads(raw)
    assert data["interpreted_intent"] == "no_action_chat_only"
    assert data.get("tool_action") in (None, "null")

    sys_p2, user_p2 = build_direct_prompt_messages(hero_context, [], "how are you doing?")
    raw2 = mp.complete(sys_p2, user_p2)
    data2 = json.loads(raw2)
    assert data2["interpreted_intent"] == "status_report"


def test_llm_brain_conversation_validates_through_mock():
    brain = LLMBrain(provider_name="mock")
    hero_context = _ctx()
    brain.request_conversation("Aldric", hero_context, [], "go home")
    import time

    for _ in range(200):
        r = brain.get_conversation_response("Aldric")
        if r is not None:
            assert r["interpreted_intent"] == "return_home"
            assert r["tool_action"] == "move_to"
            assert "Sovereign" in (r.get("spoken_response") or "")
            brain.stop()
            return
        time.sleep(0.01)
    brain.stop()
    raise AssertionError("timeout waiting for conversation response")
