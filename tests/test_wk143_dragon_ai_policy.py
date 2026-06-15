"""WK143 Ashwing AI policy pins."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from ai.basic_ai import BasicAI
from ai.behaviors.llm_bridge import apply_llm_decision
from ai.context_builder import ContextBuilder
from ai.decision_moments import DecisionMomentType, determine_decision_moment
from ai.llm_brain import LLMBrain
from ai.profile_context_adapter import build_llm_context_for_moment
from game.content.quest_chains import (
    ASHWING_THE_RED_NAME,
    ASHWINGS_HOARD,
    CLAIM_HOARD,
    PREPARE_HUNT,
    SCOUT_DRAGON_CAVE,
    SLAY_ASHWING,
    SLAY_NAMED_BOSS,
)
from game.entities.hero import Hero, HeroState
from game.sim.contracts import (
    BossEncounterSnapshot,
    BossKillMemory,
    QuestChainHistorySummary,
    QuestChainPhaseSnapshot,
    QuestChainSnapshot,
    RevengeOpportunitySnapshot,
)
from game.sim.timebase import set_sim_now_ms


NOW_MS = 3_000_000


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
    hero = Hero(float(x), float(y), hero_class="warrior", hero_id="wk143_dragon", name="Astra")
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


def _building(building_type: str, x: float, y: float, *, items: list[dict] | None = None, potions_researched: bool = False):
    return SimpleNamespace(
        building_type=building_type,
        center_x=float(x),
        center_y=float(y),
        entity_id=building_type,
        potions_researched=bool(potions_researched),
        get_available_items=lambda: list(items or []),
    )


def _dragon_story_facts() -> tuple[BossKillMemory, RevengeOpportunitySnapshot]:
    memory = BossKillMemory(
        boss_id="boss_ashwing_the_red",
        boss_name=ASHWING_THE_RED_NAME,
        boss_type="dragon",
        fallen_hero_id="wk143_fallen",
        fallen_hero_name="Mira",
        location_id="dragon_cave_target",
        location_name="Dragon Cave",
        killed_at_ms=NOW_MS - 2_000,
        revenge_chain_id="revenge_ashwing_mira",
        status="remembered",
    )
    revenge = RevengeOpportunitySnapshot(
        revenge_id="revenge_ashwing_mira",
        boss_id="boss_ashwing_the_red",
        boss_name=ASHWING_THE_RED_NAME,
        boss_type="dragon",
        fallen_hero_id="wk143_fallen",
        fallen_hero_name="Mira",
        target_location_id="dragon_cave_target",
        target_location_name="Dragon Cave",
        current_phase_id="avenge_fallen_hero",
        current_phase_title="Avenge Mira",
        revenge_chain_id="revenge_ashwing_mira",
        status="active",
        offered_at_ms=NOW_MS - 1_950,
    )
    return memory, revenge


def _ashwing_boss_snapshot(hero_id: str = "wk143_dragon") -> BossEncounterSnapshot:
    return BossEncounterSnapshot(
        boss_id="boss_ashwing_the_red",
        boss_type="dragon",
        name=ASHWING_THE_RED_NAME,
        status="active",
        current_phase="air_and_fire",
        current_phase_title="Air and Fire",
        hp_pct=0.58,
        position=(448.0, 320.0),
        target_hero_id=hero_id,
        latest_telegraph="dragon_fire_telegraph",
    )


def _ashwing_chain_snapshot(hero_id: str = "wk143_dragon") -> QuestChainSnapshot:
    history = (
        QuestChainHistorySummary(
            event="chain_offered",
            status="offered",
            hero_id=hero_id,
            at_ms=NOW_MS - 4_000,
        ),
        QuestChainHistorySummary(
            event="chain_accepted",
            status="active",
            hero_id=hero_id,
            at_ms=NOW_MS - 3_500,
        ),
        QuestChainHistorySummary(
            event="phase_started",
            phase_id=SCOUT_DRAGON_CAVE,
            phase_title="Scout the Dragon Cave",
            status="completed",
            hero_id=hero_id,
            target_id="dragon_cave_target",
            target_name="Dragon Cave",
            target_position=(448.0, 320.0),
            at_ms=NOW_MS - 3_000,
        ),
        QuestChainHistorySummary(
            event="phase_completed",
            phase_id=SCOUT_DRAGON_CAVE,
            phase_title="Scout the Dragon Cave",
            status="completed",
            hero_id=hero_id,
            target_id="dragon_cave_target",
            target_name="Dragon Cave",
            target_position=(448.0, 320.0),
            at_ms=NOW_MS - 2_800,
        ),
        QuestChainHistorySummary(
            event="phase_started",
            phase_id=PREPARE_HUNT,
            phase_title="Prepare Against Ashwing's Fire",
            status="completed",
            hero_id=hero_id,
            target_id="dragon_cave_target",
            target_name="Dragon Cave",
            target_position=(448.0, 320.0),
            at_ms=NOW_MS - 2_200,
        ),
        QuestChainHistorySummary(
            event="phase_completed",
            phase_id=PREPARE_HUNT,
            phase_title="Prepare Against Ashwing's Fire",
            status="completed",
            hero_id=hero_id,
            target_id="dragon_cave_target",
            target_name="Dragon Cave",
            target_position=(448.0, 320.0),
            at_ms=NOW_MS - 2_000,
        ),
        QuestChainHistorySummary(
            event="phase_started",
            phase_id=SLAY_ASHWING,
            phase_title=f"Slay {ASHWING_THE_RED_NAME}",
            status="active",
            hero_id=hero_id,
            target_id="boss_ashwing_the_red",
            target_name=ASHWING_THE_RED_NAME,
            target_position=(448.0, 320.0),
            at_ms=NOW_MS - 1_800,
        ),
    )
    phases = (
        QuestChainPhaseSnapshot(
            phase_id=SCOUT_DRAGON_CAVE,
            title="Scout the Dragon Cave",
            objective_type="scout_location",
            status="completed",
            assigned_hero_id=hero_id,
            target_id="dragon_cave_target",
            target_name="Dragon Cave",
            target_position=(448.0, 320.0),
            history=history[2:4],
        ),
        QuestChainPhaseSnapshot(
            phase_id=PREPARE_HUNT,
            title="Prepare Against Ashwing's Fire",
            objective_type=PREPARE_HUNT,
            status="completed",
            assigned_hero_id=hero_id,
            target_id="dragon_cave_target",
            target_name="Dragon Cave",
            target_position=(448.0, 320.0),
            history=history[4:6],
        ),
        QuestChainPhaseSnapshot(
            phase_id=SLAY_ASHWING,
            title=f"Slay {ASHWING_THE_RED_NAME}",
            objective_type=SLAY_NAMED_BOSS,
            status="active",
            assigned_hero_id=hero_id,
            target_id="boss_ashwing_the_red",
            target_name=ASHWING_THE_RED_NAME,
            target_position=(448.0, 320.0),
            history=history[6:],
        ),
        QuestChainPhaseSnapshot(
            phase_id=CLAIM_HOARD,
            title=f"Claim {ASHWINGS_HOARD.display_name}",
            objective_type=CLAIM_HOARD,
            status="upcoming",
            assigned_hero_id=hero_id,
            target_id="dragon_hoard",
            target_name=ASHWINGS_HOARD.display_name,
            target_position=(480.0, 352.0),
            history=(),
        ),
    )
    return QuestChainSnapshot(
        chain_id=143,
        chain_type=ASHWINGS_HOARD.chain_type,
        name=ASHWINGS_HOARD.display_name,
        status="active",
        assigned_hero_id=hero_id,
        current_phase_id=SLAY_ASHWING,
        current_phase_title=f"Slay {ASHWING_THE_RED_NAME}",
        current_objective_type=SLAY_NAMED_BOSS,
        target_id="boss_ashwing_the_red",
        target_name=ASHWING_THE_RED_NAME,
        target_position=(448.0, 320.0),
        phases=phases,
        history=history,
    )


def _make_game_state(
    hero: Hero,
    *,
    buildings: tuple,
    quest_chains: tuple = (),
    boss_encounters: tuple = (),
    boss_kill_memories: tuple = (),
    revenge_opportunities: tuple = (),
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
        "elite_enemies": [],
        "elite_encounters": [],
        "boss_kill_memories": list(boss_kill_memories),
        "revenge_opportunities": list(revenge_opportunities),
        "captured_heroes": [],
        "rescue_opportunities": [],
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


def test_wk143_ashwing_active_chain_continues_when_ready_and_keeps_boss_telegraph_context():
    hero = _hero()
    castle = _building("castle", 384.0, 256.0)
    memory, revenge = _dragon_story_facts()
    chain = _ashwing_chain_snapshot(hero.hero_id)
    boss = _ashwing_boss_snapshot(hero.hero_id)
    game_state = _make_game_state(
        hero,
        buildings=(castle,),
        quest_chains=(chain,),
        boss_encounters=(boss,),
        boss_kill_memories=(memory,),
        revenge_opportunities=(revenge,),
        castle=castle,
    )

    moment = determine_decision_moment(hero, game_state, now_ms=NOW_MS)
    assert moment is not None
    assert moment.moment_type == DecisionMomentType.QUEST_CHAIN
    assert moment.allowed_actions == ("continue_phase", "retreat_to_heal")
    assert ASHWING_THE_RED_NAME in moment.reason

    decision, base_context, autonomous = _brain_decision(hero, game_state, moment)
    assert decision["action"] == "continue_phase"

    quest_chain = base_context["quest_chains"][0]
    assert quest_chain["known_boss_name"] == ASHWING_THE_RED_NAME
    assert quest_chain["known_boss_phase"] == "Air and Fire"
    assert quest_chain["known_boss_telegraph"] == "dragon_fire_telegraph"
    assert autonomous["quest_chain"]["known_boss_name"] == ASHWING_THE_RED_NAME
    assert autonomous["quest_chain"]["known_boss_phase"] == "Air and Fire"
    assert autonomous["quest_chain"]["known_boss_telegraph"] == "dragon_fire_telegraph"
    assert autonomous["current_situation"]["boss_kill_memories"][0]["boss_name"] == ASHWING_THE_RED_NAME
    assert autonomous["current_situation"]["revenge_opportunities"][0]["boss_name"] == ASHWING_THE_RED_NAME

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
    assert hero.target["quest_chain_phase_id"] == SLAY_ASHWING
    assert hero.target["target_name"] == ASHWING_THE_RED_NAME
    assert hero.target_position == (448.0, 320.0)


def test_wk143_ashwing_active_chain_prefers_prepare_supplies_when_out_of_potions():
    hero = _hero(potions=0)
    castle = _building("castle", 384.0, 256.0)
    marketplace = _building(
        "marketplace",
        160.0,
        96.0,
        items=[{"name": "Healing Potion", "type": "potion", "price": 20}],
        potions_researched=True,
    )
    memory, revenge = _dragon_story_facts()
    chain = _ashwing_chain_snapshot(hero.hero_id)
    boss = _ashwing_boss_snapshot(hero.hero_id)
    game_state = _make_game_state(
        hero,
        buildings=(castle, marketplace),
        quest_chains=(chain,),
        boss_encounters=(boss,),
        boss_kill_memories=(memory,),
        revenge_opportunities=(revenge,),
        castle=castle,
    )

    moment = determine_decision_moment(hero, game_state, now_ms=NOW_MS)
    assert moment is not None
    assert moment.allowed_actions == ("continue_phase", "prepare_supplies", "retreat_to_heal")

    decision, base_context, autonomous = _brain_decision(hero, game_state, moment)
    assert decision["action"] == "prepare_supplies"
    assert decision["target"] == "Health Potion"
    assert "Ashwing the Red" in autonomous["quest_chain"]["action_meanings"]["prepare_supplies"]
    assert "Air and Fire" in autonomous["quest_chain"]["action_meanings"]["prepare_supplies"]

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
    assert hero.target["shop_building"] is marketplace
    assert hero.target_position == (marketplace.center_x, marketplace.center_y)


def test_wk143_ashwing_survival_gate_forces_retreat_to_heal_when_critical():
    hero = _hero(hp=max(1, int(_hero().max_hp * 0.2)), potions=0)
    castle = _building("castle", 384.0, 256.0)
    memory, revenge = _dragon_story_facts()
    chain = _ashwing_chain_snapshot(hero.hero_id)
    boss = _ashwing_boss_snapshot(hero.hero_id)
    game_state = _make_game_state(
        hero,
        buildings=(castle,),
        quest_chains=(chain,),
        boss_encounters=(boss,),
        boss_kill_memories=(memory,),
        revenge_opportunities=(revenge,),
        castle=castle,
    )

    moment = determine_decision_moment(hero, game_state, now_ms=NOW_MS)
    assert moment is not None
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
