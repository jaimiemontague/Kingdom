"""WK141 Blackbanner AI policy pins."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from ai.basic_ai import BasicAI
from ai.behaviors.llm_bridge import apply_llm_decision
from ai.context_builder import ContextBuilder
from ai.decision_moments import DecisionMomentType, determine_decision_moment
from ai.llm_brain import LLMBrain
from ai.profile_context_adapter import build_llm_context_for_moment
from config import TILE_SIZE
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
    potions: int = 2,
    gold: int = 120,
) -> Hero:
    hero = Hero(float(x), float(y), hero_class="warrior", hero_id="wk141_blackbanner", name="Astra")
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


def _blackbanner_chain_snapshot(hero_id: str = "wk141_blackbanner") -> QuestChainSnapshot:
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


def _blackbanner_boss_snapshot(hero_id: str = "wk141_blackbanner") -> BossEncounterSnapshot:
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
    enemies: tuple = (),
    boss_encounters: tuple = (),
    elite_enemies: tuple = (),
    castle=None,
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


def _make_view(game_state: dict):
    return SimpleNamespace(
        **{k: v for k, v in game_state.items() if k != "quest_chains"},
        quest_chains=tuple(game_state.get("quest_chains") or ()),
        commands=None,
    )


def _brain_decision(hero: Hero, game_state: dict, moment):
    base_context = ContextBuilder.build_hero_context(hero, game_state)
    autonomous = build_llm_context_for_moment(hero, game_state, moment, now_ms=NOW_MS)
    brain = LLMBrain("mock")
    try:
        decision = brain._process_request(hero.name, {**base_context, "wk50_autonomous": autonomous})
    finally:
        brain.stop()
    return decision, base_context, autonomous


def test_blackbanner_active_chain_outranks_daily_life_and_continues_phase():
    hero = _hero()
    castle = _building("castle", 384.0, 256.0)
    chain = _blackbanner_chain_snapshot(hero.hero_id)
    boss = _blackbanner_boss_snapshot(hero.hero_id)
    elite = _blackbanner_elite_snapshot()
    game_state = _make_game_state(
        hero,
        buildings=(castle,),
        quest_chains=(chain,),
        boss_encounters=(boss,),
        elite_enemies=(elite,),
        castle=castle,
    )

    moment = determine_decision_moment(hero, game_state, now_ms=NOW_MS)
    assert moment is not None
    assert moment.moment_type == DecisionMomentType.QUEST_CHAIN
    assert moment.allowed_actions == ("continue_phase", "retreat_to_heal")
    assert "Blackbanner's Toll" in moment.reason

    decision, base_context, autonomous = _brain_decision(hero, game_state, moment)
    assert decision["action"] == "continue_phase"
    assert autonomous["quest_chain"]["known_boss_name"] == "Rusk Blackbanner"
    assert autonomous["quest_chain"]["elite_target_name"] == BLACKBANNER_TOLL_TAKER_NAME
    assert autonomous["quest_chain"]["stakes"] == {"difficulty_tier": 5, "phase_count": 5}
    assert autonomous["quest_chain"]["phase_history"][0]["event"] == "chain_offered"

    ai = BasicAI(llm_brain=None)
    apply_llm_decision(
        ai,
        hero,
        decision,
        _make_view(game_state),
        source="mock",
        context=base_context,
    )

    assert hero.intent == "pursuing_quest_chain"
    assert hero.target["type"] == "visit_poi"
    assert hero.target["quest_chain_phase_id"] == INTERCEPT_TOLL_TAKER
    assert hero.target["target_name"] == BLACKBANNER_TOLL_TAKER_NAME
    assert hero.target_position == (448.0, 224.0)


def test_blackbanner_active_chain_no_potions_prefers_prepare_supplies_before_pressing_on():
    hero = _hero(potions=0)
    castle = _building("castle", 384.0, 256.0)
    marketplace = _building(
        "marketplace",
        160.0,
        96.0,
        items=[
            {"name": "Healing Potion", "type": "potion", "price": 20},
            {"name": "Iron Sword", "type": "weapon", "price": 80, "attack": 6},
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
    assert moment.allowed_actions == ("continue_phase", "prepare_supplies", "retreat_to_heal")

    decision, base_context, autonomous = _brain_decision(hero, game_state, moment)
    assert decision["action"] == "prepare_supplies"
    assert decision["target"] == "Health Potion"
    assert "Rusk Blackbanner" in autonomous["quest_chain"]["action_meanings"]["prepare_supplies"]

    ai = BasicAI(llm_brain=None)
    apply_llm_decision(
        ai,
        hero,
        decision,
        _make_view(game_state),
        source="mock",
        context=base_context,
    )

    assert hero.intent == "shopping"
    assert hero.state == HeroState.MOVING
    assert hero.target["type"] == "shopping"
    assert hero.target["item"] == "Health Potion"
    assert hero.target["marketplace"] is marketplace
    assert hero.target["shop_building"] is marketplace
    assert hero.target_position == (marketplace.center_x, marketplace.center_y)


def test_blackbanner_low_health_with_no_potions_forces_retreat_to_heal():
    hero = _hero(hp=max(1, int(_hero().max_hp * 0.40)), potions=0)
    castle = _building("castle", 384.0, 256.0)
    enemy = SimpleNamespace(
        x=hero.x + TILE_SIZE * 2.0,
        y=hero.y,
        is_alive=True,
        enemy_type="bandit",
        hp=20,
        max_hp=20,
        attack_power=4,
        target=None,
    )
    chain = _blackbanner_chain_snapshot(hero.hero_id)
    boss = _blackbanner_boss_snapshot(hero.hero_id)
    elite = _blackbanner_elite_snapshot()
    game_state = _make_game_state(
        hero,
        buildings=(castle,),
        enemies=(enemy,),
        quest_chains=(chain,),
        boss_encounters=(boss,),
        elite_enemies=(elite,),
        castle=castle,
    )

    moment = determine_decision_moment(hero, game_state, now_ms=NOW_MS)
    assert moment is not None
    assert moment.moment_type == DecisionMomentType.QUEST_CHAIN
    assert moment.allowed_actions == ("retreat_to_heal",)

    decision, base_context, autonomous = _brain_decision(hero, game_state, moment)
    assert decision["action"] == "retreat_to_heal"
    assert autonomous["quest_chain"]["action_meanings"] == {
        "retreat_to_heal": "break off to safety, heal, and resupply before resuming the chain"
    }

    ai = BasicAI(llm_brain=None)
    apply_llm_decision(
        ai,
        hero,
        decision,
        _make_view(game_state),
        source="mock",
        context=base_context,
    )

    assert hero.intent == "returning_to_safety"
    assert hero.state == HeroState.RETREATING
    assert hero.target_position == (castle.center_x, castle.center_y)
