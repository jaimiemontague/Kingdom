"""WK138 quest-chain AI policy pins.

These tests keep the AI lane honest: the model may only choose bounded quest
verbs, survival gates win before flavor, and no-chain paths stay inert.
"""

from __future__ import annotations

import math
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from ai.basic_ai import BasicAI
from ai.behaviors.llm_bridge import apply_llm_decision
from ai.context_builder import ContextBuilder
from ai.decision_moments import DecisionMomentType, moment_quest_chain
from ai.llm_brain import LLMBrain
from ai.profile_context_adapter import build_llm_context_for_moment
from config import QUEST_DECLINE_COOLDOWN_MS, TILE_SIZE
from game.content.quest_chains import COLLECT_ITEM, RELIC_OF_THE_OLD_SHRINE, SCOUT_LOCATION
from game.entities.hero import Hero, HeroState
from game.sim.timebase import set_sim_now_ms
from game.systems.protocol import SystemContext
from game.systems.quest_chain import QuestChainSystem


NOW_MS = 2_000_000


@pytest.fixture(autouse=True)
def _sim_clock():
    set_sim_now_ms(NOW_MS)
    yield
    set_sim_now_ms(0)


class _Bus:
    def __init__(self):
        self.events: list[dict] = []

    def emit(self, payload):
        self.events.append(dict(payload))


class _Enemy:
    def __init__(self, x: float, y: float):
        self.x = float(x)
        self.y = float(y)
        self.is_alive = True
        self.enemy_type = "wk138_threat"
        self.hp = 20
        self.max_hp = 20
        self.attack_power = 4
        self.target = None

    def distance_to(self, x: float, y: float) -> float:
        return math.hypot(self.x - float(x), self.y - float(y))


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
    hero = Hero(float(x), float(y), hero_class="warrior", hero_id="wk138_ai", name="Astra")
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


def _make_view(game_state: dict, sim: object | None = None):
    return SimpleNamespace(
        **{k: v for k, v in game_state.items() if k != "quest_chains"},
        quest_chains=tuple(game_state.get("quest_chains") or ()),
        commands=None if sim is None else SimpleNamespace(_sim=sim),
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


def _offer_context():
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
    bus = _Bus()
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


def _active_context():
    system, chain, hero, origin, castle, bus, ctx = _offer_context()
    system.accept_chain(chain.chain_id, hero=hero, event_bus=bus, now_ms=NOW_MS)
    hero.x = float(origin.center_x)
    hero.y = float(origin.center_y)
    set_sim_now_ms(NOW_MS + 1_000)
    system.update(ctx, 1 / 60)
    return system, chain, hero, origin, castle, bus, ctx


def test_no_quest_chains_skip_focus_selection_without_touching_focus_logic(monkeypatch):
    hero = _hero()
    game_state = _make_game_state(hero, buildings=())

    def _explode(*args, **kwargs):
        raise AssertionError("select_focus_quest_chain should not run without quest chains")

    monkeypatch.setattr("ai.decision_moments.select_focus_quest_chain", _explode)
    assert moment_quest_chain(hero, game_state, now_ms=NOW_MS) is None


def test_active_chain_mock_brain_continues_phase_and_sets_pursuit_target():
    system, chain, hero, origin, castle, bus, _ = _active_context()
    quest_chains = system.get_active_chain_snapshots()
    game_state = _make_game_state(hero, buildings=(castle,), quest_chains=quest_chains, castle=castle)

    moment = moment_quest_chain(hero, game_state, now_ms=NOW_MS)
    assert moment is not None
    assert moment.moment_type == DecisionMomentType.QUEST_CHAIN
    assert moment.allowed_actions == ("continue_phase", "retreat_to_heal")

    decision, base_context, autonomous = _brain_decision(hero, game_state, moment)
    assert decision["action"] == "continue_phase"

    focus = autonomous["quest_chain"]
    assert focus["chain_id"] == chain.chain_id
    assert focus["current_phase_id"] == COLLECT_ITEM
    assert focus["current_phase_title"] == "Recover the Relic"

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
    assert isinstance(hero.target, dict)
    assert hero.target["type"] == "visit_poi"
    assert hero.target["quest_chain_id"] == str(chain.chain_id)
    assert hero.target_position == (origin.center_x, origin.center_y)


def test_low_health_active_chain_forces_retreat_to_heal():
    system, chain, hero, origin, castle, bus, _ = _active_context()
    hero.hp = max(1, int(hero.max_hp * 0.40))
    hero.potions = 0
    enemy = _Enemy(hero.x + TILE_SIZE * 2.0, hero.y)
    quest_chains = system.get_active_chain_snapshots()
    game_state = _make_game_state(
        hero,
        buildings=(castle,),
        enemies=(enemy,),
        quest_chains=quest_chains,
        castle=castle,
    )

    moment = moment_quest_chain(hero, game_state, now_ms=NOW_MS)
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

    assert hero.state == HeroState.RETREATING
    assert hero.intent == "returning_to_safety"
    assert hero.target_position == (castle.center_x, castle.center_y)


def test_offered_chain_accepts_high_reward_and_claims_live_chain():
    system, chain, hero, origin, castle, bus, _ = _offer_context()
    quest_chains = system.get_active_chain_snapshots()
    game_state = _make_game_state(hero, buildings=(castle,), quest_chains=quest_chains, castle=castle)

    moment = moment_quest_chain(hero, game_state, now_ms=NOW_MS)
    assert moment is not None
    assert set(moment.allowed_actions) == {"accept_chain", "decline_chain"}

    decision, base_context, autonomous = _brain_decision(hero, game_state, moment)
    assert decision["action"] == "accept_chain"
    assert autonomous["quest_chain"]["reward_gold"] == RELIC_OF_THE_OLD_SHRINE.reward_profile.gold

    ai = BasicAI(llm_brain=None)
    apply_llm_decision(
        ai,
        hero,
        decision,
        _make_view(game_state, SimpleNamespace(quest_chain_system=system, event_bus=bus)),
        source="mock",
        context=base_context,
    )

    active = system.get_active_chain_snapshots()[0]
    assert chain.status == "active"
    assert active.status == "active"
    assert hero.intent == "pursuing_quest_chain"
    assert hero.target["type"] == "visit_poi"
    assert hero.target["quest_chain_id"] == str(chain.chain_id)
    assert hero.target_position == (origin.center_x, origin.center_y)


def test_offered_chain_declines_low_reward_and_arms_cooldown(monkeypatch):
    low_reward_def = SimpleNamespace(
        reward_profile=SimpleNamespace(gold=10),
        difficulty_tier=2,
    )
    monkeypatch.setattr("ai.quest_chain_context.get_chain_def", lambda chain_type: low_reward_def)

    system, chain, hero, origin, castle, bus, _ = _offer_context()
    quest_chains = system.get_active_chain_snapshots()
    game_state = _make_game_state(hero, buildings=(castle,), quest_chains=quest_chains, castle=castle)

    moment = moment_quest_chain(hero, game_state, now_ms=NOW_MS)
    assert moment is not None
    assert set(moment.allowed_actions) == {"accept_chain", "decline_chain"}

    decision, base_context, autonomous = _brain_decision(hero, game_state, moment)
    assert decision["action"] == "decline_chain"
    assert autonomous["quest_chain"]["reward_gold"] == 10

    ai = BasicAI(llm_brain=None)
    apply_llm_decision(
        ai,
        hero,
        decision,
        _make_view(game_state, SimpleNamespace(quest_chain_system=system, event_bus=bus)),
        source="mock",
        context=base_context,
    )

    assert chain.status == "offered"
    assert hero.intent == "idle"
    assert hero.state == HeroState.IDLE
    assert hero.target_position is None
    assert hero._quest_chain_decline_until_ms[str(chain.chain_id)] == NOW_MS + QUEST_DECLINE_COOLDOWN_MS
