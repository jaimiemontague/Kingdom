"""WK138 quest-chain prompt context pins."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from ai.context_builder import ContextBuilder
from ai.decision_moments import DecisionMomentType, moment_idle_seeking_activity, moment_quest_chain
from ai.profile_context_adapter import build_llm_context_for_moment
from ai.prompt_packs import build_autonomous_user_prompt
from game.content.quest_chains import COLLECT_ITEM, RELIC_OF_THE_OLD_SHRINE, SCOUT_LOCATION
from game.entities.hero import Hero, HeroState
from game.sim.contracts import QuestChainHistorySummary, QuestChainPhaseSnapshot, QuestChainSnapshot
from game.sim.timebase import set_sim_now_ms
from game.systems.protocol import SystemContext
from game.systems.quest_chain import QuestChainSystem


NOW_MS = 2_000_000


@pytest.fixture(autouse=True)
def _sim_clock():
    set_sim_now_ms(NOW_MS)
    yield
    set_sim_now_ms(0)


def _target(
    entity_id: str,
    name: str,
    x: float,
    y: float,
    *,
    poi_type: str = "",
    building_type: str = "",
    grid_x: int = 0,
    grid_y: int = 0,
):
    return SimpleNamespace(
        entity_id=entity_id,
        name=name,
        poi_type=poi_type,
        building_type=building_type,
        grid_x=grid_x,
        grid_y=grid_y,
        poi_def=SimpleNamespace(
            display_name=name,
            interaction_type="shrine",
            difficulty_tier=2,
            description=f"{name} for WK138 testing.",
            size=(1, 1),
        ),
        center_x=float(x),
        center_y=float(y),
        x=float(x),
        y=float(y),
    )


def _hero(*, x: float = 128.0, y: float = 96.0) -> Hero:
    hero = Hero(float(x), float(y), hero_class="warrior", hero_id="wk138_prompt", name="Astra")
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


def _make_game_state(
    hero: Hero,
    *,
    buildings: tuple,
    quest_chains: tuple = (),
    enemies: tuple = (),
    pois: tuple = (),
    castle=None,
):
    return {
        "buildings": list(buildings),
        "enemies": list(enemies),
        "heroes": [hero],
        "bounties": [],
        "pois": list(pois),
        "castle": castle,
        "quest_chains": list(quest_chains),
    }


def _active_quest_chain_snapshot(hero_id: str = "wk138_prompt") -> QuestChainSnapshot:
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
            phase_id=SCOUT_LOCATION,
            phase_title="Scout the Ancient Ruins",
            status="active",
            hero_id=hero_id,
            target_id="poi_ancient_ruins",
            target_name="Ancient Ruins",
            target_position=(128.0, 96.0),
            at_ms=NOW_MS - 1_000,
        ),
        QuestChainHistorySummary(
            event="phase_completed",
            phase_id=SCOUT_LOCATION,
            phase_title="Scout the Ancient Ruins",
            status="completed",
            hero_id=hero_id,
            target_id="poi_ancient_ruins",
            target_name="Ancient Ruins",
            target_position=(128.0, 96.0),
            at_ms=NOW_MS - 500,
        ),
        QuestChainHistorySummary(
            event="phase_started",
            phase_id=COLLECT_ITEM,
            phase_title="Recover the Relic",
            status="active",
            hero_id=hero_id,
            target_id="poi_ancient_ruins",
            target_name="Ancient Ruins",
            target_position=(128.0, 96.0),
            at_ms=NOW_MS,
        ),
    )
    phases = (
        QuestChainPhaseSnapshot(
            phase_id=SCOUT_LOCATION,
            title="Scout the Ancient Ruins",
            objective_type=SCOUT_LOCATION,
            status="completed",
            assigned_hero_id=hero_id,
            target_id="poi_ancient_ruins",
            target_name="Ancient Ruins",
            target_position=(128.0, 96.0),
            history=history[2:4],
        ),
        QuestChainPhaseSnapshot(
            phase_id=COLLECT_ITEM,
            title="Recover the Relic",
            objective_type=COLLECT_ITEM,
            status="active",
            assigned_hero_id=hero_id,
            target_id="poi_ancient_ruins",
            target_name="Ancient Ruins",
            target_position=(128.0, 96.0),
            history=history[4:],
        ),
        QuestChainPhaseSnapshot(
            phase_id="deliver_item",
            title="Deliver the Relic",
            objective_type="deliver_item",
            status="upcoming",
            assigned_hero_id=hero_id,
            target_id="castle",
            target_name="Castle",
            target_position=(384.0, 256.0),
            history=(),
        ),
    )
    return QuestChainSnapshot(
        chain_id=17,
        chain_type=RELIC_OF_THE_OLD_SHRINE.chain_type,
        name=RELIC_OF_THE_OLD_SHRINE.display_name,
        status="active",
        assigned_hero_id=hero_id,
        current_phase_id=COLLECT_ITEM,
        current_phase_title="Recover the Relic",
        current_objective_type=COLLECT_ITEM,
        target_id="poi_ancient_ruins",
        target_name="Ancient Ruins",
        target_position=(128.0, 96.0),
        phases=phases,
        history=history,
    )


def _offered_chain_setup():
    hero = _hero()
    origin = _target(
        "poi_ancient_ruins",
        "Ancient Ruins",
        hero.x,
        hero.y,
        poi_type="poi_ancient_ruins",
        building_type="poi_ancient_ruins",
    )
    castle = _target(
        "castle",
        "Castle",
        384.0,
        256.0,
        building_type="castle",
        grid_x=12,
        grid_y=8,
    )
    bus = SimpleNamespace(emit=lambda payload: None)
    system = QuestChainSystem()
    ctx = SystemContext(
        heroes=[hero],
        enemies=[],
        buildings=[castle],
        world=None,
        economy=None,
        event_bus=bus,
        pois=[origin],
        castle=castle,
    )
    chain = system.offer_relic_of_the_old_shrine(ctx=ctx, hero=hero, event_bus=bus, now_ms=NOW_MS)
    return system, chain, hero, origin, castle, bus, ctx


def _parsed_prompt(hero: Hero, game_state: dict, moment):
    context = ContextBuilder.build_hero_context(hero, game_state)
    autonomous = build_llm_context_for_moment(hero, game_state, moment, now_ms=NOW_MS)
    prompt = build_autonomous_user_prompt(autonomous)
    blob = json.loads(prompt.split("\n\nRespond", 1)[0])
    return context, autonomous, blob, prompt


def test_active_chain_prompt_context_includes_bounded_snapshot_and_action_meanings():
    hero = _hero()
    castle = _target(
        "castle",
        "Castle",
        384.0,
        256.0,
        building_type="castle",
        grid_x=12,
        grid_y=8,
    )
    chain = _active_quest_chain_snapshot(hero.hero_id)
    game_state = _make_game_state(hero, buildings=(castle,), quest_chains=(chain,), castle=castle)

    moment = moment_quest_chain(hero, game_state, now_ms=NOW_MS)
    assert moment is not None
    assert moment.moment_type == DecisionMomentType.QUEST_CHAIN

    context, autonomous, blob, prompt = _parsed_prompt(hero, game_state, moment)
    quest_block = blob["context"]["quest_chain"]

    assert blob["allowed_actions"] == ["continue_phase", "retreat_to_heal"]
    assert blob["context"]["current_situation"]["quest_chains"][0]["name"] == RELIC_OF_THE_OLD_SHRINE.display_name
    assert blob["context"]["current_situation"]["quest_chains"][0]["current_phase_id"] == COLLECT_ITEM
    assert blob["context"]["current_situation"]["quest_chains"][0]["phase_history"]

    assert quest_block["chain_id"] == 17
    assert quest_block["chain_type"] == RELIC_OF_THE_OLD_SHRINE.chain_type
    assert quest_block["name"] == RELIC_OF_THE_OLD_SHRINE.display_name
    assert quest_block["current_phase_id"] == COLLECT_ITEM
    assert quest_block["current_phase_title"] == "Recover the Relic"
    assert quest_block["current_objective_type"] == COLLECT_ITEM
    assert quest_block["target_id"] == "poi_ancient_ruins"
    assert quest_block["target_name"] == "Ancient Ruins"
    assert quest_block["target_position"] == [128.0, 96.0]
    assert quest_block["reward_gold"] == RELIC_OF_THE_OLD_SHRINE.reward_profile.gold
    assert quest_block["stakes"] == {"difficulty_tier": 2, "phase_count": 3}
    assert len(quest_block["phases"]) == 3
    assert len(quest_block["phase_history"]) >= 5
    assert quest_block["phases"][0]["history"][0]["event"] == "phase_started"
    assert quest_block["phases"][1]["history"][-1]["event"] == "phase_started"
    assert set(quest_block["action_meanings"]) == {"continue_phase", "retreat_to_heal"}
    assert "Recover the Relic" in quest_block["action_meanings"]["continue_phase"]
    assert "Ancient Ruins" in quest_block["action_meanings"]["continue_phase"]
    assert quest_block["action_meanings"]["retreat_to_heal"].startswith("break off to safety")
    assert set(quest_block) == {
        "chain_id",
        "chain_type",
        "name",
        "status",
        "assigned_hero_id",
        "current_phase_id",
        "current_phase_title",
        "current_objective_type",
        "target_id",
        "target_name",
        "target_position",
        "reward_gold",
        "stakes",
        "phases",
        "phase_history",
        "action_meanings",
    }
    assert "quest_chain" in autonomous
    assert "Relic of the Old Shrine" in prompt
    assert context["quest_chains"][0]["name"] == RELIC_OF_THE_OLD_SHRINE.display_name


def test_no_chain_prompt_omits_chain_block_and_focus_selection(monkeypatch):
    hero = _hero()
    castle = _target(
        "castle",
        "Castle",
        384.0,
        256.0,
        building_type="castle",
        grid_x=12,
        grid_y=8,
    )
    game_state = _make_game_state(hero, buildings=(castle,), castle=castle)
    moment = moment_idle_seeking_activity(hero, game_state)
    assert moment is not None

    def _explode(*args, **kwargs):
        raise AssertionError("quest-chain focus should not be selected for idle prompts")

    monkeypatch.setattr("ai.profile_context_adapter.select_focus_quest_chain", _explode)

    context, autonomous, blob, prompt = _parsed_prompt(hero, game_state, moment)
    assert "quest_chain" not in autonomous
    assert "quest_chain" not in blob["context"]
    assert "quest_chains" not in blob["context"]["current_situation"]
    assert blob["allowed_actions"] == list(moment.allowed_actions)
    assert "Relic of the Old Shrine" not in prompt
    assert "phase_history" not in prompt
    assert "quest_chains" not in context
