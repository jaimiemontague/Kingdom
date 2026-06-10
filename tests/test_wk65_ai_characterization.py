"""WK65 Round 0 (Wave 1) — AI decision characterization pins.

These tests pin the *observable* behavior of the AI decision surface so that the
Wave-2 deletion of the legacy LLM-prompt path is provably inert, and so that the
later Round-D refactor (TaskRouter / AI file splits) cannot silently change
these contracts.

GREEN on the current, unmodified code. Owned by Agent 06 (AIBehaviorDirector).

What is pinned (see ``.cursor/plans/wk65_round0_deslop_foundation.plan.md`` §"Agent 06"):

1. **Autonomous decision path (the SURVIVING path).** With the mock provider, a
   hero consult is driven through the *live* autonomous branch of
   ``LLMBrain._process_request`` -> ``_process_autonomous_decision_request``,
   reached when ``context["wk50_autonomous"]`` is a dict. The shape/keys of the
   resulting decision dict are pinned. Wave 2 deletes the *non*-autonomous branch
   of ``_process_request`` (the ``build_summary`` / ``build_decision_prompt`` /
   ``SYSTEM_PROMPT`` legacy path); because that branch is only reached when
   ``wk50_autonomous`` is absent, exercising the autonomous path here proves the
   deletion does not change this behavior.

2. **``get_fallback_decision``** — well-formed deterministic fallback for every
   documented branch (no/invalid LLM response).

3. **``ContextBuilder.build_hero_context`` keys** — the top-level context dict
   shape for a constructed hero + game_state (pins ``context_builder`` for Round D).

4. **``validate_direct_prompt_output``** — verdicts for canonical inputs including
   the deferred-combat early-return and the critical-health redirect (the audit
   flags these two as fragile, so they are pinned to exact field values).
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from ai.context_builder import ContextBuilder
from ai.decision_moments import determine_decision_moment
from ai.direct_prompt_validator import validate_direct_prompt_output
from ai.llm_brain import LLMBrain
from ai.profile_context_adapter import build_llm_context_for_moment
from ai.prompt_templates import VALID_ACTIONS, get_fallback_decision
from config import MAP_HEIGHT, MAP_WIDTH
from game.entities import RangerGuild
from game.entities.buildings.economic import Marketplace
from game.entities.hero import Hero, HeroState
from game.sim.timebase import set_sim_now_ms


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _sim_clock():
    """ContextBuilder / decision moments read sim time; pin it deterministically."""
    set_sim_now_ms(10_000)
    try:
        yield
    finally:
        set_sim_now_ms(None)


def _drain_decision(brain: LLMBrain, hero_key: str, *, max_wait_s: float = 5.0) -> dict | None:
    """Poll the brain's async decision queue like the engine does."""
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        decision = brain.get_decision(hero_key)
        if decision is not None:
            return decision
        time.sleep(0.01)
    return None


def _direct_ctx(**overrides) -> dict:
    """Minimal hero_context shape consumed by validate_direct_prompt_output.

    Mirrors the canonical fixture in tests/test_wk50_phase2b_direct_prompt_contracts.py.
    """
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
            {"place_id": "castle:main", "place_type": "castle", "display_name": "Castle"},
            {"place_id": "inn:1", "place_type": "inn", "display_name": "The Inn"},
            {"place_id": "market:1", "place_type": "marketplace", "display_name": "Market"},
        ],
        "shop_items": [],
    }
    base.update(overrides)
    return base


# Exact set of top-level keys produced by validate_direct_prompt_output().
_DIRECT_OUTPUT_KEYS = frozenset(
    {
        "spoken_response",
        "interpreted_intent",
        "tool_action",
        "action",
        "target",
        "target_kind",
        "target_id",
        "target_description",
        "obey_defy",
        "refusal_reason",
        "safety_assessment",
        "confidence",
    }
)


# ===========================================================================
# 1. Autonomous decision path — the path that SURVIVES the Wave-2 deletion
# ===========================================================================

def test_autonomous_decision_path_live_shape_and_keys():
    """The live autonomous branch (wk50_autonomous dict) returns a well-formed
    decision dict whose shape/keys are pinned.

    This drives LLMBrain._process_request -> _process_autonomous_decision_request.
    The legacy non-autonomous branch (deleted in Wave 2) is NOT reached because
    wk50_autonomous is a dict, so this pin proves that deletion is inert.
    """
    hero = Hero(10.0, 10.0, name="Brainy", hero_id="wk65_auto1")
    hero.state = HeroState.FIGHTING
    hero.hp = 20
    hero.max_hp = 100
    hero.potions = 2
    gs = {"buildings": [], "enemies": [], "heroes": [hero], "bounties": []}

    moment = determine_decision_moment(hero, gs, now_ms=50_000)
    assert moment is not None
    allowed = moment.allowed_actions_set()
    aut = build_llm_context_for_moment(hero, gs, moment, now_ms=50_000)
    base = ContextBuilder.build_hero_context(hero, gs)
    context = {**base, "wk50_autonomous": aut}

    brain = LLMBrain(provider_name="mock")
    try:
        brain.request_decision(hero.name, context)
        decision = _drain_decision(brain, hero.name)
    finally:
        brain.stop()

    assert decision is not None, "autonomous decision timed out"
    # Exact key set produced by validate_autonomous_decision (the surviving validator).
    assert set(decision.keys()) == {
        "action",
        "target",
        "reasoning",
        "confidence",
        "memory_used",
        "personality_influence",
        "obey_defy",
        "tool_action",
    }
    # Action is constrained to the moment's allowlist; tool_action mirrors action.
    assert decision["action"] in allowed
    assert decision["tool_action"] == decision["action"]
    assert decision["obey_defy"] == "Obey"
    # Field types/bounds (do not over-pin volatile numeric content).
    assert isinstance(decision["target"], str)
    assert isinstance(decision["reasoning"], str) and decision["reasoning"]
    assert isinstance(decision["memory_used"], list)
    assert isinstance(decision["personality_influence"], str)
    assert isinstance(decision["confidence"], float)
    assert 0.0 <= decision["confidence"] <= 1.0
    # Deterministic mock reasoning tag for this moment type.
    assert "mock autonomous" in decision["reasoning"]


def test_autonomous_decision_path_invalid_action_falls_back():
    """When the provider returns an action outside the moment allowlist, the live
    autonomous path returns get_fallback_decision(context) (well-formed fallback).

    This pins the autonomous-path fallback contract, which also survives Wave 2.
    """
    hero = Hero(10.0, 10.0, name="Brainy2", hero_id="wk65_auto2")
    hero.state = HeroState.FIGHTING
    hero.hp = 20
    hero.max_hp = 100
    hero.potions = 2
    gs = {"buildings": [], "enemies": [], "heroes": [hero], "bounties": []}

    moment = determine_decision_moment(hero, gs, now_ms=50_000)
    assert moment is not None
    aut = build_llm_context_for_moment(hero, gs, moment, now_ms=50_000)
    base = ContextBuilder.build_hero_context(hero, gs)
    context = {**base, "wk50_autonomous": aut}

    class _DisallowedActionProvider:
        name = "disallowed"

        def complete(self, system_prompt: str, user_prompt: str, timeout: float = 5.0) -> str:
            # "explore" is not in the LOW_HEALTH_COMBAT allowlist (fight/retreat/use_potion).
            return json.dumps(
                {"action": "explore", "target": "", "reasoning": "not allowed here"}
            )

    brain = LLMBrain(provider_name="mock")
    brain.provider = _DisallowedActionProvider()
    try:
        brain.request_decision(hero.name, context)
        decision = _drain_decision(brain, hero.name)
    finally:
        brain.stop()

    assert decision is not None, "autonomous fallback timed out"
    # Fallback for critical-health-with-potion (hp=20%, potions=2).
    assert decision["action"] == "use_potion"
    assert decision["action"] in VALID_ACTIONS
    assert "Fallback" in decision.get("reasoning", "")


# ===========================================================================
# 2. get_fallback_decision — deterministic, well-formed per documented branch
# ===========================================================================

def _fallback_ctx(*, situation: dict, potions: int = 0, gold: int = 100,
                  shop_items: list | None = None) -> dict:
    sit = {
        "in_combat": False,
        "low_health": False,
        "critical_health": False,
        "has_potions": potions > 0,
        "can_shop": False,
        "near_safety": False,
        "enemies_nearby": False,
        "outnumbered": False,
        "hunger_urgent": False,
        "can_afford_meal": False,
    }
    sit.update(situation)
    return {
        "situation": sit,
        "hero": {"gold": gold},
        "inventory": {"potions": potions},
        "shop_items": shop_items or [],
    }


def _assert_well_formed_decision(decision: dict) -> None:
    assert isinstance(decision, dict)
    assert set(decision.keys()) == {"action", "target", "reasoning"}
    assert isinstance(decision["action"], str) and decision["action"]
    assert isinstance(decision["target"], str)
    assert isinstance(decision["reasoning"], str) and decision["reasoning"]


def test_fallback_critical_health_with_potion():
    out = get_fallback_decision(_fallback_ctx(situation={"critical_health": True}, potions=2))
    _assert_well_formed_decision(out)
    assert out == {
        "action": "use_potion",
        "target": "",
        "reasoning": "Fallback: Critical health, using potion",
    }


def test_fallback_critical_health_no_potion():
    out = get_fallback_decision(_fallback_ctx(situation={"critical_health": True}, potions=0))
    _assert_well_formed_decision(out)
    assert out == {
        "action": "retreat",
        "target": "castle",
        "reasoning": "Fallback: Critical health, retreating",
    }


def test_fallback_low_health_in_combat_no_potion():
    out = get_fallback_decision(
        _fallback_ctx(situation={"low_health": True, "in_combat": True}, potions=0)
    )
    _assert_well_formed_decision(out)
    assert out == {
        "action": "retreat",
        "target": "marketplace",
        "reasoning": "Fallback: Low health in combat, retreating",
    }


def test_fallback_can_shop_needs_potion():
    out = get_fallback_decision(
        _fallback_ctx(
            situation={"can_shop": True},
            potions=0,
            shop_items=[{"type": "potion", "can_afford": True, "name": "Health Potion"}],
        )
    )
    _assert_well_formed_decision(out)
    assert out == {
        "action": "buy_item",
        "target": "Health Potion",
        "reasoning": "Fallback: Low on health, buying potion",
    }


def test_fallback_enemies_nearby_healthy():
    out = get_fallback_decision(_fallback_ctx(situation={"enemies_nearby": True}, potions=1))
    _assert_well_formed_decision(out)
    assert out == {
        "action": "fight",
        "target": "",
        "reasoning": "Fallback: Enemies nearby, engaging",
    }


def test_fallback_idle_default():
    out = get_fallback_decision(_fallback_ctx(situation={}, potions=0))
    _assert_well_formed_decision(out)
    assert out == {
        "action": "explore",
        "target": "",
        "reasoning": "Fallback: Nothing to do, exploring",
    }


# ===========================================================================
# 3. build_hero_context — top-level key contract (pins context_builder)
# ===========================================================================

# Exact top-level keys ContextBuilder.build_hero_context produces today.
_HERO_CONTEXT_TOP_KEYS = frozenset(
    {
        "hero",
        "inventory",
        "personality",
        "current_state",
        "nearby_enemies",
        "nearby_allies",
        "available_bounties",
        "bounty_options",
        "shop_items",
        "market_catalog_items",
        "distances",
        "nearby_pois",
        "situation",
        "current_location",
        "building_occupants",
        "building_context",
        "player_is_present",
        "hero_stat_block",
        "hero_home_place_id",
        "known_places_llm",
    }
)

_HERO_SUB_KEYS = frozenset(
    {
        "id",
        "name",
        "class",
        "level",
        "hp",
        "max_hp",
        "health_percent",
        "gold",
        "attack",
        "defense",
        "xp",
        "xp_to_level",
        "home_building_type",
    }
)

_SITUATION_KEYS = frozenset(
    {
        "in_combat",
        "low_health",
        "critical_health",
        "has_potions",
        "can_shop",
        "near_safety",
        "enemies_nearby",
        "outnumbered",
        "hunger_urgent",
        "can_afford_meal",
    }
)


def _build_real_hero_context() -> dict:
    cx, cy = MAP_WIDTH // 2 - 1, MAP_HEIGHT // 2 - 1
    ranger_guild = RangerGuild(cx - 6, cy + 8)
    market = Marketplace(cx + 40, cy + 40)
    market.potions_researched = True
    market.potion_price = 15
    hero = Hero(
        float(ranger_guild.center_x),
        float(ranger_guild.center_y),
        hero_class="ranger",
        hero_id="wk65_ctx",
        name="RangerCtx",
    )
    hero.home_building = ranger_guild
    hero.gold = 25
    gs = {
        "heroes": [hero],
        "buildings": [ranger_guild, market],
        "enemies": [],
        "bounties": [],
        "castle": None,
        "world": SimpleNamespace(width=MAP_WIDTH, height=MAP_HEIGHT),
    }
    return ContextBuilder.build_hero_context(hero, gs)


def test_build_hero_context_top_level_keys():
    ctx = _build_real_hero_context()
    assert set(ctx.keys()) == _HERO_CONTEXT_TOP_KEYS


def test_build_hero_context_hero_and_situation_subkeys():
    ctx = _build_real_hero_context()
    assert set(ctx["hero"].keys()) == _HERO_SUB_KEYS
    assert set(ctx["situation"].keys()) == _SITUATION_KEYS
    # Inventory + stat block contracts that downstream prompt-packs depend on.
    # WK134: accessory + backpack added (WK131 item slots reaching the chat blob).
    assert set(ctx["inventory"].keys()) == {
        "weapon",
        "weapon_attack",
        "armor",
        "armor_defense",
        "potions",
        "accessory",
        "backpack",
    }
    assert isinstance(ctx["hero_stat_block"], str) and ctx["hero_stat_block"]
    assert isinstance(ctx["known_places_llm"], list)
    assert isinstance(ctx["situation"]["in_combat"], bool)


# ===========================================================================
# 4. validate_direct_prompt_output — fragile verdicts pinned (audit-flagged)
# ===========================================================================

def test_validate_direct_deferred_combat_early_return():
    """Any attack_* intent is forced to a no-action chat-only deferral.

    Audit-flagged as fragile: pin the exact early-return verdict so a refactor
    cannot silently let combat commands through.
    """
    out = validate_direct_prompt_output(
        {
            "spoken_response": "I will charge the lair!",
            "interpreted_intent": "attack_known_lair",
            "tool_action": "fight",
        },
        _direct_ctx(),
    )
    assert set(out.keys()) == _DIRECT_OUTPUT_KEYS
    assert out["interpreted_intent"] == "no_action_chat_only"
    assert out["tool_action"] is None
    assert out["action"] is None
    assert out["obey_defy"] == "Defy"
    assert out["refusal_reason"] == "mvp_combat_deferred"
    assert out["safety_assessment"] == "deferred"
    assert out["target"] == ""
    assert out["spoken_response"]  # non-empty in-character refusal


def test_validate_direct_attack_prefix_also_deferred():
    """The early return triggers for any intent starting with 'attack_', not just
    the explicit DEFERRED_COMBAT_INTENTS members."""
    out = validate_direct_prompt_output(
        {
            "spoken_response": "Death to them!",
            "interpreted_intent": "attack_the_horde",  # not in the named set
            "tool_action": "fight",
        },
        _direct_ctx(),
    )
    assert out["interpreted_intent"] == "no_action_chat_only"
    assert out["tool_action"] is None
    assert out["obey_defy"] == "Defy"
    assert out["refusal_reason"] == "mvp_combat_deferred"


def test_validate_direct_critical_health_redirect_with_potion():
    """Critical HP + explore/go_to + has_potions -> seek_healing/use_potion.

    Audit-flagged fragile redirect: pin exact verdict fields.
    """
    crit = {
        "in_combat": False,
        "low_health": True,
        "critical_health": True,
        "has_potions": True,
        "can_shop": False,
        "near_safety": False,
    }
    out = validate_direct_prompt_output(
        {
            "spoken_response": "I scout east!",
            "interpreted_intent": "explore_direction",
            "tool_action": "explore",
        },
        _direct_ctx(situation=crit),
    )
    assert set(out.keys()) == _DIRECT_OUTPUT_KEYS
    assert out["interpreted_intent"] == "seek_healing"
    assert out["tool_action"] == "use_potion"
    assert out["action"] == "use_potion"
    assert out["obey_defy"] == "Obey"
    assert out["safety_assessment"] == "critical_redirect"
    assert out["refusal_reason"] == ""


def test_validate_direct_critical_health_redirect_no_potion_retreats_home():
    """Critical HP + go_to + NO potions + a known safe haven -> seek_healing/retreat home."""
    crit = {
        "in_combat": False,
        "low_health": True,
        "critical_health": True,
        "has_potions": False,
        "can_shop": False,
        "near_safety": False,
    }
    ctx = _direct_ctx(situation=crit, inventory={"potions": 0})
    out = validate_direct_prompt_output(
        {
            "spoken_response": "Onward to the inn!",
            "interpreted_intent": "go_to_known_place",
            "tool_action": "move_to",
            "target_id": "inn:1",
        },
        ctx,
    )
    assert out["interpreted_intent"] == "seek_healing"
    assert out["tool_action"] == "retreat"
    assert out["obey_defy"] == "Obey"
    assert out["safety_assessment"] == "critical_redirect"


def test_validate_direct_status_report_no_physical_action():
    """A benign status_report yields no tool_action and Obey."""
    out = validate_direct_prompt_output(
        {
            "spoken_response": "I stand ready, my liege.",
            "interpreted_intent": "status_report",
            "tool_action": None,
        },
        _direct_ctx(),
    )
    assert set(out.keys()) == _DIRECT_OUTPUT_KEYS
    assert out["interpreted_intent"] == "status_report"
    assert out["tool_action"] is None
    assert out["action"] is None
    assert out["obey_defy"] == "Obey"
    assert out["refusal_reason"] == ""


def test_validate_direct_non_dict_raw_safe_fallback():
    """A non-dict LLM payload is coerced to a safe no-action chat-only response."""
    out = validate_direct_prompt_output("totally not json", _direct_ctx())
    assert set(out.keys()) == _DIRECT_OUTPUT_KEYS
    assert out["interpreted_intent"] == "no_action_chat_only"
    assert out["tool_action"] is None
    assert out["action"] is None
    assert out["obey_defy"] == "Obey"
    assert out["spoken_response"]  # non-empty fallback line
