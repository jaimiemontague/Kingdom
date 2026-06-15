"""WK143 Ashwing prompt-context pins."""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from ai.context_builder import ContextBuilder
from ai.decision_moments import DecisionMomentType, determine_decision_moment
from ai.profile_context_adapter import build_llm_context_for_moment
from ai.prompt_packs import build_autonomous_user_prompt
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


NOW_MS = 3_100_000


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
    hero = Hero(float(x), float(y), hero_class="warrior", hero_id="wk143_prompt", name="Astra")
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


def _dragon_story_facts() -> tuple[BossKillMemory, RevengeOpportunitySnapshot]:
    memory = BossKillMemory(
        boss_id="boss_ashwing_the_red",
        boss_name=ASHWING_THE_RED_NAME,
        boss_type="dragon",
        fallen_hero_id="wk143_fallen",
        fallen_hero_name="Mira",
        location_id="dragon_cave_target",
        location_name="Dragon Cave",
        killed_at_ms=NOW_MS - 2_500,
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
        offered_at_ms=NOW_MS - 2_400,
    )
    return memory, revenge


def _ashwing_boss_snapshot(hero_id: str = "wk143_prompt") -> BossEncounterSnapshot:
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


def _ashwing_chain_snapshot(hero_id: str = "wk143_prompt") -> QuestChainSnapshot:
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
    quest_chains: tuple = (),
    boss_encounters: tuple = (),
    boss_kill_memories: tuple = (),
    revenge_opportunities: tuple = (),
    enemies: tuple = (),
):
    return {
        "buildings": [],
        "enemies": list(enemies),
        "heroes": [hero],
        "bounties": [],
        "pois": [],
        "castle": None,
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


def _parsed_prompt(hero: Hero, game_state: dict, moment):
    context = ContextBuilder.build_hero_context(hero, game_state)
    autonomous = build_llm_context_for_moment(hero, game_state, moment, now_ms=NOW_MS)
    prompt = build_autonomous_user_prompt(autonomous)
    blob = json.loads(prompt.split("\n\nRespond", 1)[0])
    return context, autonomous, blob, prompt


def test_wk143_ashwing_prompt_context_keeps_boss_telegraph_and_separate_victory_memory():
    hero = _hero()
    memory, revenge = _dragon_story_facts()
    chain = _ashwing_chain_snapshot(hero.hero_id)
    boss = _ashwing_boss_snapshot(hero.hero_id)
    game_state = _make_game_state(
        hero,
        quest_chains=(chain,),
        boss_encounters=(boss,),
        boss_kill_memories=(memory,),
        revenge_opportunities=(revenge,),
    )

    moment = determine_decision_moment(hero, game_state, now_ms=NOW_MS)
    assert moment is not None
    assert moment.moment_type == DecisionMomentType.QUEST_CHAIN
    assert moment.allowed_actions == ("continue_phase", "retreat_to_heal")

    context, autonomous, blob, prompt = _parsed_prompt(hero, game_state, moment)
    quest_chain = context["quest_chains"][0]
    quest_block = blob["context"]["quest_chain"]

    assert quest_chain["known_boss_name"] == ASHWING_THE_RED_NAME
    assert quest_chain["known_boss_phase"] == "Air and Fire"
    assert quest_chain["known_boss_telegraph"] == "dragon_fire_telegraph"
    assert blob["context"]["current_situation"]["quest_chains"][0]["known_boss_telegraph"] == "dragon_fire_telegraph"
    assert autonomous["quest_chain"]["known_boss_telegraph"] == "dragon_fire_telegraph"
    assert quest_block["known_boss_telegraph"] == "dragon_fire_telegraph"

    assert context["boss_kill_memories"][0]["boss_name"] == ASHWING_THE_RED_NAME
    assert context["revenge_opportunities"][0]["boss_name"] == ASHWING_THE_RED_NAME
    assert blob["context"]["current_situation"]["boss_kill_memories"][0]["boss_name"] == ASHWING_THE_RED_NAME
    assert blob["context"]["current_situation"]["revenge_opportunities"][0]["boss_name"] == ASHWING_THE_RED_NAME

    assert blob["allowed_actions"] == ["continue_phase", "retreat_to_heal"]
    assert set(quest_block["action_meanings"]) == {"continue_phase", "retreat_to_heal"}
    assert "Air and Fire" in quest_block["action_meanings"]["continue_phase"]
    assert "dragon_fire_telegraph" in quest_block["action_meanings"]["continue_phase"]
    assert "Ashwing the Red" in prompt
    assert "dragon_fire_telegraph" in prompt


def test_wk143_ashwing_prompt_context_omits_dragon_only_facts_without_boss_snapshot():
    hero = _hero()
    memory, revenge = _dragon_story_facts()
    chain = _ashwing_chain_snapshot(hero.hero_id)
    game_state = _make_game_state(
        hero,
        quest_chains=(chain,),
        boss_kill_memories=(memory,),
        revenge_opportunities=(revenge,),
    )

    moment = determine_decision_moment(hero, game_state, now_ms=NOW_MS)
    assert moment is not None
    assert moment.allowed_actions == ("continue_phase", "retreat_to_heal")

    context, autonomous, blob, prompt = _parsed_prompt(hero, game_state, moment)

    for key in (
        "known_boss_id",
        "known_boss_name",
        "known_boss_phase",
        "known_boss_hp_pct",
        "known_boss_position",
        "known_boss_telegraph",
    ):
        assert key not in context["quest_chains"][0]
        assert key not in autonomous["quest_chain"]
        assert key not in blob["context"]["quest_chain"]

    assert context["boss_kill_memories"][0]["boss_name"] == ASHWING_THE_RED_NAME
    assert context["revenge_opportunities"][0]["boss_name"] == ASHWING_THE_RED_NAME
    assert blob["context"]["current_situation"]["boss_kill_memories"][0]["boss_name"] == ASHWING_THE_RED_NAME
    assert blob["context"]["current_situation"]["revenge_opportunities"][0]["boss_name"] == ASHWING_THE_RED_NAME
    assert "dragon_fire_telegraph" not in prompt
    assert "telegraph:" not in blob["context"]["quest_chain"]["action_meanings"]["continue_phase"]
