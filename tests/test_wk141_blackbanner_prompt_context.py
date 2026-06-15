"""WK141 Blackbanner prompt-context pins."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from ai.context_builder import ContextBuilder
from ai.decision_moments import DecisionMomentType, determine_decision_moment
from ai.profile_context_adapter import build_llm_context_for_moment
from ai.prompt_packs import build_autonomous_user_prompt
from game.content.quest_chains import (
    BLACKBANNER_TOLL_TAKER_NAME,
    BLACKBANNERS_TOLL,
    INTERCEPT_TOLL_TAKER,
    SCOUT_FORTRESS,
    SLAY_BLACKBANNER,
)
from game.entities.hero import Hero, HeroState
from game.sim.contracts import (
    BossEncounterSnapshot,
    EliteEncounterSnapshot,
    QuestChainHistorySummary,
    QuestChainPhaseSnapshot,
    QuestChainSnapshot,
)
from game.sim.timebase import set_sim_now_ms


NOW_MS = 2_000_000


@pytest.fixture(autouse=True)
def _sim_clock():
    set_sim_now_ms(NOW_MS)
    yield
    set_sim_now_ms(0)


def _hero(
    *,
    x: float = 128.0,
    y: float = 96.0,
    hp: int | None = None,
    potions: int = 0,
    gold: int = 120,
) -> Hero:
    hero = Hero(float(x), float(y), hero_class="warrior", hero_id="wk141_prompt", name="Astra")
    hero.state = HeroState.IDLE
    hero.intent = "idle"
    hero.hp = int(hero.max_hp if hp is None else hp)
    hero.potions = int(potions)
    hero.gold = int(gold)
    hero.weapon = None
    hero.armor = None
    hero.accessory = None
    hero.backpack = []
    hero.personality = "balanced and reliable"
    return hero


def _building(building_type: str, x: float, y: float, *, items: list[dict] | None = None):
    return SimpleNamespace(
        building_type=building_type,
        center_x=float(x),
        center_y=float(y),
        entity_id=building_type,
        get_available_items=lambda: list(items or []),
    )


def _blackbanner_chain_snapshot(hero_id: str = "wk141_prompt") -> QuestChainSnapshot:
    history = (
        QuestChainHistorySummary(
            event="chain_offered",
            status="offered",
            hero_id=hero_id,
            at_ms=NOW_MS - 3_000,
        ),
        QuestChainHistorySummary(
            event="chain_accepted",
            status="active",
            hero_id=hero_id,
            at_ms=NOW_MS - 2_000,
        ),
        QuestChainHistorySummary(
            event="phase_started",
            phase_id=SCOUT_FORTRESS,
            phase_title="Scout the Bandit Fortress",
            status="completed",
            hero_id=hero_id,
            target_id="poi_blackbanner_fortress",
            target_name="Bandit Fortress",
            target_position=(512.0, 256.0),
            at_ms=NOW_MS - 1_000,
        ),
        QuestChainHistorySummary(
            event="phase_completed",
            phase_id=SCOUT_FORTRESS,
            phase_title="Scout the Bandit Fortress",
            status="completed",
            hero_id=hero_id,
            target_id="poi_blackbanner_fortress",
            target_name="Bandit Fortress",
            target_position=(512.0, 256.0),
            at_ms=NOW_MS - 900,
        ),
        QuestChainHistorySummary(
            event="phase_started",
            phase_id=INTERCEPT_TOLL_TAKER,
            phase_title="Intercept the Toll-Taker",
            status="active",
            hero_id=hero_id,
            target_id="elite_blackbanner_toll_taker",
            target_name=BLACKBANNER_TOLL_TAKER_NAME,
            target_position=(448.0, 224.0),
            at_ms=NOW_MS - 800,
        ),
        QuestChainHistorySummary(
            event="phase_started",
            phase_id=SLAY_BLACKBANNER,
            phase_title="Defeat Rusk Blackbanner",
            status="upcoming",
            hero_id=hero_id,
            target_id="boss_rusk_blackbanner",
            target_name="Rusk Blackbanner",
            target_position=(576.0, 320.0),
            at_ms=NOW_MS - 700,
        ),
    )
    phases = (
        QuestChainPhaseSnapshot(
            phase_id=SCOUT_FORTRESS,
            title="Scout the Bandit Fortress",
            objective_type=SCOUT_FORTRESS,
            status="completed",
            assigned_hero_id=hero_id,
            target_id="poi_blackbanner_fortress",
            target_name="Bandit Fortress",
            target_position=(512.0, 256.0),
            history=history[2:4],
        ),
        QuestChainPhaseSnapshot(
            phase_id=INTERCEPT_TOLL_TAKER,
            title="Intercept the Toll-Taker",
            objective_type=INTERCEPT_TOLL_TAKER,
            status="active",
            assigned_hero_id=hero_id,
            target_id="elite_blackbanner_toll_taker",
            target_name=BLACKBANNER_TOLL_TAKER_NAME,
            target_position=(448.0, 224.0),
            history=history[4:5],
        ),
        QuestChainPhaseSnapshot(
            phase_id="assault_gate",
            title="Assault the Gate",
            objective_type="assault_gate",
            status="upcoming",
            assigned_hero_id=hero_id,
            target_id="gate_blackbanner",
            target_name="Blackbanner Gate",
            target_position=(544.0, 288.0),
            history=(),
        ),
        QuestChainPhaseSnapshot(
            phase_id=SLAY_BLACKBANNER,
            title="Defeat Rusk Blackbanner",
            objective_type=SLAY_BLACKBANNER,
            status="upcoming",
            assigned_hero_id=hero_id,
            target_id="boss_rusk_blackbanner",
            target_name="Rusk Blackbanner",
            target_position=(576.0, 320.0),
            history=history[5:],
        ),
        QuestChainPhaseSnapshot(
            phase_id="claim_reward",
            title="Claim the Spoils",
            objective_type="claim_reward",
            status="upcoming",
            assigned_hero_id=hero_id,
            target_id="castle",
            target_name="Castle",
            target_position=(384.0, 256.0),
            history=(),
        ),
    )
    return QuestChainSnapshot(
        chain_id=141,
        chain_type=BLACKBANNERS_TOLL.chain_type,
        name=BLACKBANNERS_TOLL.display_name,
        status="active",
        assigned_hero_id=hero_id,
        current_phase_id=INTERCEPT_TOLL_TAKER,
        current_phase_title="Intercept the Toll-Taker",
        current_objective_type=INTERCEPT_TOLL_TAKER,
        target_id="elite_blackbanner_toll_taker",
        target_name=BLACKBANNER_TOLL_TAKER_NAME,
        target_position=(448.0, 224.0),
        phases=phases,
        history=history,
    )


def _blackbanner_boss_snapshot(hero_id: str = "wk141_prompt") -> BossEncounterSnapshot:
    return BossEncounterSnapshot(
        boss_id="boss_rusk_blackbanner",
        boss_type="bandit_lord",
        name="Rusk Blackbanner",
        status="active",
        current_phase="toll_banner",
        current_phase_title="Toll Banner",
        hp_pct=0.62,
        position=(576.0, 320.0),
        target_hero_id=hero_id,
        latest_telegraph="toll_banner",
    )


def _blackbanner_elite_snapshot() -> EliteEncounterSnapshot:
    return EliteEncounterSnapshot(
        elite_id="elite_blackbanner_toll_taker",
        base_type="bandit",
        name=BLACKBANNER_TOLL_TAKER_NAME,
        status="active",
        affixes=("banner_bearer", "ironhide"),
        position=(448.0, 224.0),
    )


def _make_game_state(
    hero: Hero,
    *,
    buildings: tuple,
    quest_chains: tuple = (),
    boss_encounters: tuple = (),
    elite_enemies: tuple = (),
    castle=None,
    enemies: tuple = (),
):
    return {
        "buildings": list(buildings),
        "enemies": list(enemies),
        "heroes": [hero],
        "bounties": [],
        "pois": [],
        "castle": castle,
        "quest_chains": list(quest_chains),
        "boss_encounters": list(boss_encounters),
        "elite_enemies": list(elite_enemies),
        "elite_encounters": list(elite_enemies),
        "world": None,
    }


def test_blackbanner_prompt_context_includes_chain_phase_boss_elite_and_phase_history():
    hero = _hero()
    castle = _building("castle", 384.0, 256.0)
    marketplace = _building(
        "marketplace",
        160.0,
        96.0,
        items=[
            {"name": "Healing Potion", "type": "potion", "price": 20},
        ],
    )
    chain = _blackbanner_chain_snapshot(hero.hero_id)
    boss = _blackbanner_boss_snapshot(hero.hero_id)
    elite = _blackbanner_elite_snapshot()
    game_state = _make_game_state(
        hero,
        buildings=(castle, marketplace),
        quest_chains=(chain,),
        boss_encounters=(boss,),
        elite_enemies=(elite,),
        castle=castle,
    )

    moment = determine_decision_moment(hero, game_state, now_ms=NOW_MS)
    assert moment is not None
    assert moment.moment_type == DecisionMomentType.QUEST_CHAIN
    assert moment.allowed_actions == ("continue_phase", "prepare_supplies", "retreat_to_heal")

    context = ContextBuilder.build_hero_context(hero, game_state)
    autonomous = build_llm_context_for_moment(hero, game_state, moment, now_ms=NOW_MS)
    prompt = build_autonomous_user_prompt(autonomous)
    blob = json.loads(prompt.split("\n\nRespond", 1)[0])

    quest_chain = context["quest_chains"][0]
    quest_block = blob["context"]["quest_chain"]

    assert quest_chain["name"] == BLACKBANNERS_TOLL.display_name
    assert quest_chain["current_phase_title"] == "Intercept the Toll-Taker"
    assert quest_chain["current_objective_type"] == INTERCEPT_TOLL_TAKER
    assert quest_chain["known_boss_name"] == "Rusk Blackbanner"
    assert quest_chain["known_boss_phase"] == "Toll Banner"
    assert quest_chain["elite_target_name"] == BLACKBANNER_TOLL_TAKER_NAME
    assert quest_chain["elite_target_base_type"] == "bandit"
    assert quest_chain["reward_gold"] == BLACKBANNERS_TOLL.reward_profile.gold
    assert quest_chain["stakes"] == {"difficulty_tier": 5, "phase_count": 5}
    assert quest_chain["phase_history"][0]["event"] == "chain_offered"
    assert quest_chain["phase_history"][-1]["phase_id"] == SLAY_BLACKBANNER

    assert blob["allowed_actions"] == ["continue_phase", "prepare_supplies", "retreat_to_heal"]
    assert quest_block["name"] == BLACKBANNERS_TOLL.display_name
    assert quest_block["current_phase_title"] == "Intercept the Toll-Taker"
    assert quest_block["current_objective_type"] == INTERCEPT_TOLL_TAKER
    assert quest_block["known_boss_name"] == "Rusk Blackbanner"
    assert quest_block["known_boss_phase"] == "Toll Banner"
    assert quest_block["elite_target_name"] == BLACKBANNER_TOLL_TAKER_NAME
    assert quest_block["elite_target_base_type"] == "bandit"
    assert quest_block["reward_gold"] == BLACKBANNERS_TOLL.reward_profile.gold
    assert quest_block["stakes"] == {"difficulty_tier": 5, "phase_count": 5}
    assert len(quest_block["phase_history"]) >= 5
    assert quest_block["phase_history"][0]["event"] == "chain_offered"
    assert quest_block["phase_history"][4]["phase_id"] == INTERCEPT_TOLL_TAKER
    assert set(quest_block["action_meanings"]) == {
        "continue_phase",
        "prepare_supplies",
        "retreat_to_heal",
    }
    assert "Rusk Blackbanner" in quest_block["action_meanings"]["continue_phase"]
    assert "Rusk Blackbanner" in quest_block["action_meanings"]["prepare_supplies"]
    assert quest_block["action_meanings"]["retreat_to_heal"].startswith("break off to safety")
    assert "Blackbanner's Toll" in prompt
    assert "Rusk Blackbanner" in prompt
    assert BLACKBANNER_TOLL_TAKER_NAME in prompt
