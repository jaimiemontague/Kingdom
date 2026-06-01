"""WK112 — differential golden characterization of validate_direct_prompt_output.

Pins the EXACT output dict for a 38-case matrix covering every branch of the
validator (raw-fallback, deferred-combat, allow-list gating, critical-HP redirect,
all 8 intents + their sub-branches, output-tail post-processing). The golden was
captured from the pre-WK112 HEAD code and is embedded as a JSON literal (NOT read
from git — so it stays valid after the refactor commits; cf. the "no git show HEAD
in parity tests" rule). The WK112 per-intent handler-table decomposition must
reproduce every dict byte-for-byte.
"""
from __future__ import annotations

import inspect
import json

import pytest

from ai import direct_prompt_validator as dpv
from ai.direct_prompt_validator import validate_direct_prompt_output


def _ctx(**overrides):
    base = {
        "hero": {
            "name": "Aldric", "class": "warrior", "level": 2, "hp": 80,
            "max_hp": 100, "health_percent": 80, "gold": 50,
        },
        "inventory": {"potions": 2},
        "situation": {
            "in_combat": False, "low_health": False, "critical_health": False,
            "has_potions": True, "can_shop": False, "near_safety": True,
        },
        "current_location": "outdoors",
        "distances": {"castle": 3.0, "marketplace": 12.0},
        "known_places_llm": [
            {"place_id": "castle:main", "place_type": "castle", "display_name": "Castle"},
            {"place_id": "inn:1", "place_type": "inn", "display_name": "The Inn"},
            {"place_id": "market:1", "place_type": "marketplace", "display_name": "Market"},
        ],
        "shop_items": [],
    }
    base.update(overrides)
    return base


def _sit(**kw):
    s = {
        "in_combat": False, "low_health": False, "critical_health": False,
        "has_potions": True, "can_shop": False, "near_safety": True,
    }
    s.update(kw)
    return s


def _guild_ctx():
    c = _ctx()
    c["hero_home_place_id"] = "ranger_guild:10:12"
    c["hero"] = {**c["hero"], "class": "ranger", "home_building_type": "ranger_guild"}
    c["known_places_llm"] = [
        {"place_id": "castle:main", "place_type": "castle", "display_name": "Castle"},
        {"place_id": "ranger_guild:10:12", "place_type": "ranger_guild", "display_name": "Ranger Guild"},
    ]
    return c


def _synthetic_guild_ctx():
    c = _ctx()
    c["hero_home_place_id"] = "ranger_guild:5:3"
    c["hero"] = {**c["hero"], "class": "ranger", "home_building_type": "ranger_guild"}
    c["known_places_llm"] = [
        {"place_id": "ranger_guild:5:3", "place_type": "ranger_guild", "display_name": "Ranger Guild"},
    ]
    return c


def _no_home_ctx(near_safety=True, can_shop=False):
    c = _ctx(situation=_sit(near_safety=near_safety, can_shop=can_shop))
    c["known_places_llm"] = []
    return c


def _critical_goto_no_home_ctx():
    c = _ctx()
    c["situation"] = _sit(low_health=True, critical_health=True, has_potions=False, near_safety=False)
    c["known_places_llm"] = []
    return c


# (case_id, raw, ctx, player_message) — MUST match the §4 golden keys exactly.
CASES = [
    ("raw_not_dict", "just a string", _ctx(), ""),
    ("deferred_attack_lair", {"spoken_response": "I'll charge!", "interpreted_intent": "attack_known_lair", "tool_action": "fight"}, _ctx(), ""),
    ("deferred_attack_prefix", {"interpreted_intent": "attack_goblin_camp", "tool_action": "fight"}, _ctx(), ""),
    ("status_report", {"spoken_response": "All well.", "interpreted_intent": "status_report"}, _ctx(), "how are you"),
    ("no_action_chat_only", {"spoken_response": "Hello.", "interpreted_intent": "no_action_chat_only"}, _ctx(), "hi"),
    ("return_home_castle_default", {"spoken_response": "Home.", "interpreted_intent": "return_home", "tool_action": "move_to"}, _ctx(), "go home"),
    ("return_home_guild", {"spoken_response": "To my hall.", "interpreted_intent": "return_home", "tool_action": "move_to"}, _guild_ctx(), "go home"),
    ("return_home_synthetic_guild_only", {"interpreted_intent": "return_home", "tool_action": "move_to"}, _synthetic_guild_ctx(), "head home"),
    ("return_home_no_home_near_safety_shop", {"interpreted_intent": "return_home", "tool_action": "move_to"}, _no_home_ctx(near_safety=True, can_shop=True), "go home"),
    ("return_home_no_home_not_safe", {"interpreted_intent": "return_home", "tool_action": "move_to"}, _no_home_ctx(near_safety=False, can_shop=False), "go home"),
    ("seek_healing_potion", {"interpreted_intent": "seek_healing"}, _ctx(situation=_sit(low_health=True, has_potions=True)), "heal up"),
    ("seek_healing_retreat_home", {"interpreted_intent": "seek_healing"}, _ctx(situation=_sit(low_health=True, has_potions=False)), "heal up"),
    ("seek_healing_no_home", {"interpreted_intent": "seek_healing"}, _no_home_ctx(near_safety=True, can_shop=False), "heal up"),
    ("go_to_known_place_found", {"interpreted_intent": "go_to_known_place", "tool_action": "move_to", "target_id": "inn:1", "target_description": "The Inn"}, _ctx(), "go to inn"),
    ("go_to_known_place_unknown", {"interpreted_intent": "go_to_known_place", "tool_action": "move_to", "target_id": "nowhere:xx", "target_description": "Moon"}, _ctx(), "go to moon"),
    ("buy_potions_shop_afford", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _ctx(situation=_sit(can_shop=True), shop_items=[{"name": "Health Potion", "type": "potion", "price": 20, "can_afford": True}]), "buy a potion"),
    ("buy_potions_shop_cant_afford_has_gold", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _ctx(situation=_sit(can_shop=True), shop_items=[{"name": "Health Potion", "price": 100, "can_afford": False}]), "buy a potion"),
    ("buy_potions_shop_cant_afford_no_gold", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _ctx(situation=_sit(can_shop=True), hero={**_ctx()["hero"], "gold": 0}, shop_items=[{"name": "Health Potion", "price": 100, "can_afford": False}]), "buy a potion"),
    ("buy_potions_shop_no_potion", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _ctx(situation=_sit(can_shop=True), shop_items=[{"name": "Short Sword", "price": 10, "can_afford": True}]), "buy a potion"),
    ("buy_potions_catalog_fallback", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _ctx(situation=_sit(can_shop=True), shop_items=[], market_catalog_items=[{"name": "Health Potion", "price": 20, "can_afford": True}]), "buy a potion"),
    ("buy_potions_no_shop_market_known", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _ctx(situation=_sit(can_shop=False)), "buy a potion"),
    ("buy_potions_no_shop_no_market", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _no_home_ctx(near_safety=True, can_shop=False), "buy a potion"),
    ("explore_compass_in_message", {"interpreted_intent": "explore_direction", "tool_action": "explore"}, _ctx(), "explore east please"),
    ("explore_no_compass", {"interpreted_intent": "explore_direction", "tool_action": "explore"}, _ctx(), "explore the frontier"),
    ("explore_compass_in_target_desc", {"interpreted_intent": "explore_direction", "tool_action": "explore", "target_description": "north"}, _ctx(), "scout"),
    ("rest_indoors", {"interpreted_intent": "rest_until_healed"}, _ctx(current_location="inn"), "rest"),
    ("rest_outdoors_home", {"interpreted_intent": "rest_until_healed"}, _ctx(current_location="outdoors"), "rest"),
    ("rest_outdoors_no_home", {"interpreted_intent": "rest_until_healed"}, _no_home_ctx(), "rest"),
    ("critical_explore_has_potion", {"spoken_response": "I scout east!", "interpreted_intent": "explore_direction", "tool_action": "explore"}, _ctx(situation=_sit(low_health=True, critical_health=True, has_potions=True, near_safety=False)), "explore east"),
    ("critical_explore_no_potion_home", {"interpreted_intent": "explore_direction", "tool_action": "explore"}, _ctx(situation=_sit(low_health=True, critical_health=True, has_potions=False, near_safety=False)), "explore east"),
    ("critical_goto_no_potion_no_home", {"interpreted_intent": "go_to_known_place", "tool_action": "move_to", "target_id": "inn:1"}, _critical_goto_no_home_ctx(), "go to inn"),
    ("unsupported_intent", {"interpreted_intent": "frobnicate", "tool_action": "move_to"}, _ctx(), "do a thing"),
    ("fight_tool_noncombat_intent", {"interpreted_intent": "return_home", "tool_action": "fight"}, _ctx(), "go home"),
    ("unknown_tool_value", {"interpreted_intent": "return_home", "tool_action": "teleport"}, _ctx(), "go home"),
    ("invalid_obey_defy", {"interpreted_intent": "status_report", "obey_defy": "Maybe"}, _ctx(), "status"),
    ("confidence_clamp_high", {"interpreted_intent": "status_report", "confidence": 5.0}, _ctx(), "status"),
    ("confidence_nonnumeric", {"interpreted_intent": "status_report", "confidence": "abc"}, _ctx(), "status"),
    ("physical_clears_refusal_forces_obey", {"spoken_response": "Nay", "interpreted_intent": "return_home", "tool_action": "move_to", "obey_defy": "Defy", "refusal_reason": "should_not_appear"}, _ctx(), "go home"),
]

# Byte-exact golden captured from pre-WK112 HEAD (PM capture 2026-05-31).
_GOLDEN_JSON = r"""
{
  "raw_not_dict": {"spoken_response": "I could not make sense of that, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 0.0},
  "deferred_attack_lair": {"spoken_response": "I'll charge!", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "mvp_combat_deferred", "safety_assessment": "deferred", "confidence": 0.0},
  "deferred_attack_prefix": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "mvp_combat_deferred", "safety_assessment": "deferred", "confidence": 0.0},
  "status_report": {"spoken_response": "All well.", "interpreted_intent": "status_report", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 0.0},
  "no_action_chat_only": {"spoken_response": "Hello.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 0.0},
  "return_home_castle_default": {"spoken_response": "Home.", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "castle", "target_kind": "known_place", "target_id": "castle:main", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "return_home_guild": {"spoken_response": "To my hall.", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "ranger_guild", "target_kind": "known_place", "target_id": "ranger_guild:10:12", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "return_home_synthetic_guild_only": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "ranger_guild", "target_kind": "known_place", "target_id": "ranger_guild:5:3", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "return_home_no_home_near_safety_shop": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "castle", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "return_home_no_home_not_safe": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "return_home", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_known_home", "safety_assessment": "impossible", "confidence": 0.0},
  "seek_healing_potion": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "seek_healing", "tool_action": "use_potion", "action": "use_potion", "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "seek_healing_retreat_home": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "seek_healing", "tool_action": "retreat", "action": "retreat", "target": "castle", "target_kind": "known_place", "target_id": "castle:main", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "seek_healing_no_home": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "seek_healing", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_safe_haven_known", "safety_assessment": "impossible", "confidence": 0.0},
  "go_to_known_place_found": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "go_to_known_place", "tool_action": "move_to", "action": "move_to", "target": "inn", "target_kind": "known_place", "target_id": "inn:1", "target_description": "The Inn", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "go_to_known_place_unknown": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "Moon", "obey_defy": "Defy", "refusal_reason": "unknown_place", "safety_assessment": "unknown_target", "confidence": 0.0},
  "buy_potions_shop_afford": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "buy_potions", "tool_action": "buy_item", "action": "buy_item", "target": "Health Potion", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "buy_potions_shop_cant_afford_has_gold": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "insufficient_gold", "safety_assessment": "impossible", "confidence": 0.0},
  "buy_potions_shop_cant_afford_no_gold": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_gold", "safety_assessment": "impossible", "confidence": 0.0},
  "buy_potions_shop_no_potion": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_potions_here", "safety_assessment": "impossible", "confidence": 0.0},
  "buy_potions_catalog_fallback": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "buy_potions", "tool_action": "buy_item", "action": "buy_item", "target": "Health Potion", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "buy_potions_no_shop_market_known": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "buy_potions", "tool_action": "move_to", "action": "move_to", "target": "marketplace", "target_kind": "known_place", "target_id": "market:1", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "buy_potions_no_shop_no_market": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_market_known", "safety_assessment": "impossible", "confidence": 0.0},
  "explore_compass_in_message": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "explore_direction", "tool_action": "explore", "action": "explore", "target": "", "target_kind": "direction", "target_id": "", "target_description": "east", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "explore_no_compass": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "unknown_heading", "safety_assessment": "unknown_target", "confidence": 0.0},
  "explore_compass_in_target_desc": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "explore_direction", "tool_action": "explore", "action": "explore", "target": "", "target_kind": "direction", "target_id": "", "target_description": "north", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "rest_indoors": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "rest_until_healed", "tool_action": "leave_building", "action": "leave_building", "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "rest_outdoors_home": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "rest_until_healed", "tool_action": "move_to", "action": "move_to", "target": "castle", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "rest_outdoors_no_home": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "rest_until_healed", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_known_rest_place", "safety_assessment": "impossible", "confidence": 0.0},
  "critical_explore_has_potion": {"spoken_response": "I scout east!", "interpreted_intent": "seek_healing", "tool_action": "use_potion", "action": "use_potion", "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "critical_redirect", "confidence": 0.0},
  "critical_explore_no_potion_home": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "seek_healing", "tool_action": "retreat", "action": "retreat", "target": "castle", "target_kind": "known_place", "target_id": "castle:main", "target_description": "Castle", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "critical_redirect", "confidence": 0.0},
  "critical_goto_no_potion_no_home": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "seek_healing", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_safe_haven_known", "safety_assessment": "impossible", "confidence": 0.0},
  "unsupported_intent": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 0.0},
  "fight_tool_noncombat_intent": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "castle", "target_kind": "known_place", "target_id": "castle:main", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "unknown_tool_value": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "castle", "target_kind": "known_place", "target_id": "castle:main", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "invalid_obey_defy": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "status_report", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 0.0},
  "confidence_clamp_high": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "status_report", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 1.0},
  "confidence_nonnumeric": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "status_report", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 0.0},
  "physical_clears_refusal_forces_obey": {"spoken_response": "Nay", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "castle", "target_kind": "known_place", "target_id": "castle:main", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0}
}
"""

GOLDEN = json.loads(_GOLDEN_JSON)


@pytest.mark.parametrize("case_id", [c[0] for c in CASES])
def test_validator_output_matches_golden(case_id):
    raw, ctx, msg = next((r, c, m) for cid, r, c, m in CASES if cid == case_id)
    got = validate_direct_prompt_output(raw, ctx, msg)
    assert got == GOLDEN[case_id], (
        f"WK112 behavior drift for case '{case_id}':\n got={got}\n exp={GOLDEN[case_id]}"
    )


def test_every_case_has_golden_and_vice_versa():
    case_ids = {c[0] for c in CASES}
    assert case_ids == set(GOLDEN), (
        f"CASES/GOLDEN key mismatch: only-in-cases={case_ids - set(GOLDEN)} "
        f"only-in-golden={set(GOLDEN) - case_ids}"
    )
    assert len(CASES) == 38


def test_public_signature_unchanged():
    sig = inspect.signature(validate_direct_prompt_output)
    assert list(sig.parameters) == ["raw", "hero_context", "player_message"]
    assert sig.parameters["player_message"].default == ""


def test_intent_handler_table_covers_all_supported_intents():
    """Structural pin: after the decomposition the dispatch table must exist and
    cover every supported intent + the two tool-clearing chat intents."""
    table = dpv._INTENT_HANDLERS
    for intent in dpv.SUPPORTED_DIRECT_INTENTS:
        assert intent in table, f"intent '{intent}' missing a handler in _INTENT_HANDLERS"
    # The 8 keys are exactly the former if/elif branches.
    assert set(table) == {
        "status_report", "no_action_chat_only", "return_home", "seek_healing",
        "go_to_known_place", "buy_potions", "explore_direction", "rest_until_healed",
    }
    for fn in table.values():
        assert callable(fn)
