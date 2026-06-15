"""WK142 rescue/revenge prompt-context pins."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from ai.behaviors.view_compat import view_to_legacy_context
from ai.context_builder import ContextBuilder
from ai.decision_moments import moment_idle_seeking_activity
from ai.profile_context_adapter import build_llm_context_for_moment
from ai.prompt_packs import build_autonomous_user_prompt, build_direct_prompt_messages
from game.entities.hero import Hero, HeroState
from game.sim.contracts import BossKillMemory, HeroCaptureState, RescueOpportunitySnapshot, RevengeOpportunitySnapshot
from game.sim.timebase import set_sim_now_ms


NOW_MS = 2_500_000


@pytest.fixture(autouse=True)
def _sim_clock():
    set_sim_now_ms(NOW_MS)
    yield
    set_sim_now_ms(0)


def _hero() -> Hero:
    hero = Hero(128.0, 96.0, hero_class="warrior", hero_id="wk142_prompt", name="Astra")
    hero.state = HeroState.IDLE
    hero.intent = "idle"
    hero.hp = int(hero.max_hp)
    hero.potions = 2
    hero.gold = 120
    hero.weapon = None
    hero.armor = None
    hero.accessory = None
    hero.backpack = []
    hero.personality = "balanced and reliable"
    return hero


def _story_facts() -> tuple[HeroCaptureState, RescueOpportunitySnapshot, BossKillMemory, RevengeOpportunitySnapshot]:
    captured = HeroCaptureState(
        hero_id="wk142_captive",
        hero_name="Astra",
        captor_boss_id="boss_rusk_blackbanner",
        captor_boss_name="Rusk Blackbanner",
        captor_boss_type="bandit_lord",
        location_id="poi_bandit_fortress",
        location_name="Bandit Fortress",
        source_chain_id="chain_blackbanner_cells",
        source_chain_type="blackbanners_toll",
        captured_at_ms=1_000,
        status="captured",
    )
    rescue = RescueOpportunitySnapshot(
        rescue_id="rescue_blackbanner_cells",
        captured_hero_id="wk142_captive",
        captured_hero_name="Astra",
        captor_boss_id="boss_rusk_blackbanner",
        captor_boss_name="Rusk Blackbanner",
        captor_boss_type="bandit_lord",
        target_location_id="poi_bandit_fortress",
        target_location_name="Bandit Fortress",
        current_phase_id="reach_fortress",
        current_phase_title="Reach the Bandit Fortress",
        source_chain_id="chain_blackbanner_cells",
        source_chain_type="blackbanners_toll",
        status="active",
        offered_at_ms=1_100,
    )
    memory = BossKillMemory(
        boss_id="boss_rusk_blackbanner",
        boss_name="Rusk Blackbanner",
        boss_type="bandit_lord",
        fallen_hero_id="wk142_fallen",
        fallen_hero_name="Mira",
        location_id="poi_bandit_fortress",
        location_name="Bandit Fortress",
        killed_at_ms=2_000,
        revenge_chain_id="revenge_rusk_mira",
        status="remembered",
    )
    revenge = RevengeOpportunitySnapshot(
        revenge_id="revenge_rusk_mira",
        boss_id="boss_rusk_blackbanner",
        boss_name="Rusk Blackbanner",
        boss_type="bandit_lord",
        fallen_hero_id="wk142_fallen",
        fallen_hero_name="Mira",
        target_location_id="poi_bandit_fortress",
        target_location_name="Bandit Fortress",
        current_phase_id="avenge_fallen_hero",
        current_phase_title="Avenge Mira",
        revenge_chain_id="revenge_rusk_mira",
        status="active",
        offered_at_ms=2_050,
    )
    return captured, rescue, memory, revenge


def _structured_view(
    hero: Hero,
    *,
    captured_heroes: tuple = (),
    rescue_opportunities: tuple = (),
    boss_kill_memories: tuple = (),
    revenge_opportunities: tuple = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        world=None,
        buildings=[],
        enemies=[],
        heroes=[hero],
        bounties=[],
        pois=[],
        quest_chains=(),
        captured_heroes=captured_heroes,
        rescue_opportunities=rescue_opportunities,
        boss_kill_memories=boss_kill_memories,
        revenge_opportunities=revenge_opportunities,
        boss_encounters=(),
        elite_enemies=(),
        elite_encounters=(),
        castle=None,
        player_gold=hero.gold,
    )


def test_wk142_story_facts_flow_from_structured_view_into_prompt_context():
    hero = _hero()
    captured, rescue, memory, revenge = _story_facts()
    view = _structured_view(
        hero,
        captured_heroes=(captured,),
        rescue_opportunities=(rescue,),
        boss_kill_memories=(memory,),
        revenge_opportunities=(revenge,),
    )

    legacy = view_to_legacy_context(view)
    assert legacy["captured_heroes"][0] == captured
    assert legacy["rescue_opportunities"][0] == rescue
    assert legacy["boss_kill_memories"][0] == memory
    assert legacy["revenge_opportunities"][0] == revenge

    context = ContextBuilder.build_hero_context(hero, legacy)
    moment = moment_idle_seeking_activity(hero, legacy)
    assert moment is not None

    autonomous = build_llm_context_for_moment(hero, legacy, moment, now_ms=NOW_MS)
    prompt = build_autonomous_user_prompt(autonomous)
    blob = json.loads(prompt.split("\n\nRespond", 1)[0])

    assert context["captured_heroes"][0]["hero_id"] == "wk142_captive"
    assert context["rescue_opportunities"][0]["target_location_name"] == "Bandit Fortress"
    assert context["boss_kill_memories"][0]["fallen_hero_name"] == "Mira"
    assert context["revenge_opportunities"][0]["boss_name"] == "Rusk Blackbanner"

    current = blob["context"]["current_situation"]
    assert current["captured_heroes"][0]["hero_name"] == "Astra"
    assert current["rescue_opportunities"][0]["captor_boss_name"] == "Rusk Blackbanner"
    assert current["boss_kill_memories"][0]["fallen_hero_name"] == "Mira"
    assert current["revenge_opportunities"][0]["boss_id"] == "boss_rusk_blackbanner"

    direct_system, direct_prompt = build_direct_prompt_messages(context, [], "Where are the prisoners?")
    assert direct_system.startswith("WK50_DIRECT_PROMPT_V1")
    direct_blob = json.loads(direct_prompt.partition("\n\n")[0])
    assert direct_blob["story_facts"]["captured_heroes"][0]["hero_name"] == "Astra"
    assert direct_blob["story_facts"]["rescue_opportunities"][0]["target_location_name"] == "Bandit Fortress"
    assert direct_blob["story_facts"]["boss_kill_memories"][0]["fallen_hero_name"] == "Mira"
    assert direct_blob["story_facts"]["revenge_opportunities"][0]["boss_name"] == "Rusk Blackbanner"


def test_wk142_story_fact_keys_are_omitted_when_the_view_is_empty():
    hero = _hero()
    view = _structured_view(hero)

    legacy = view_to_legacy_context(view)
    context = ContextBuilder.build_hero_context(hero, legacy)
    moment = moment_idle_seeking_activity(hero, legacy)
    assert moment is not None

    autonomous = build_llm_context_for_moment(hero, legacy, moment, now_ms=NOW_MS)
    prompt = build_autonomous_user_prompt(autonomous)
    blob = json.loads(prompt.split("\n\nRespond", 1)[0])
    direct_system, direct_prompt = build_direct_prompt_messages(context, [], "Hello there.")
    direct_blob = json.loads(direct_prompt.partition("\n\n")[0])

    for key in ("captured_heroes", "rescue_opportunities", "boss_kill_memories", "revenge_opportunities"):
        assert key not in context
        assert key not in autonomous["current_situation"]
        assert key not in blob["context"]["current_situation"]

    assert "story_facts" not in direct_blob
    assert direct_system.startswith("WK50_DIRECT_PROMPT_V1")
