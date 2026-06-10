"""WK126-T6 — LLM accept/decline at the quest-giver + 15-sim-min decline cooldown.

Covers (plan T6 acceptance):
- forced ACCEPT assigns the quest (``quest.accepted_by``), sets the hero's
  objective target per quest type, and emits QUEST_STARTED;
- forced DECLINE sets ``hero._quest_decline_until_ms[giver_id] = now + 900_000``
  (15 SIM-minutes), emits QUEST_DECLINED, clears the staged offer, and the
  approach selector then SKIPS that giver for <15 min and re-considers it after
  (sim clock advanced);
- the ``llm_brain=None`` path is a DETERMINISTIC ACCEPT (decision of record);
- the seeded MockProvider quest-offer responder drives both verdicts
  deterministically (reward >= 50g accepts, below declines) and the verdict
  SURVIVES the full llm_brain parse/validate pipeline;
- the QUEST_OFFER decision moment fires only while an offer is staged, and the
  quest-offer context block (type/target/reward/distance/decision_rule) is
  injected ONLY for that moment (other prompts byte-unchanged — digest-safe).

ACTION-CARRIER NOTE: accept/decline ride the existing tool-action verbs
('explore' = accept_quest, 'retreat' = decline_quest) because
``llm_brain._parse_response`` / ``validate_autonomous_decision`` (outside the
WK133 lane) hard-reject unknown action strings — see ai/decision_moments.py.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from config import (
    QUEST_DECLINE_COOLDOWN_MS,
    QUEST_GIVER_INTERACT_PX,
    TILE_SIZE,
)
from game.entities.hero import HeroState
from game.sim.timebase import set_sim_now_ms
from game.systems.quest import Quest, QuestAiInfo, QuestGiverAiInfo, QuestSystem

from ai.basic_ai import BasicAI
from ai.behaviors.quest_offer import (
    begin_quest_offer_decision,
    maybe_approach_quest_giver,
    maybe_apply_quest_offer_decision,
)
from ai.decision_moments import (
    QUEST_OFFER_ACCEPT_ACTION,
    QUEST_OFFER_DECLINE_ACTION,
    DecisionMomentType,
    determine_decision_moment,
)

_NOW_MS = 2_000_000
_GIVER_ID = "b00000007"


@pytest.fixture(autouse=True)
def _pinned_sim_clock():
    set_sim_now_ms(_NOW_MS)
    yield
    set_sim_now_ms(None)


@pytest.fixture(autouse=True)
def _reset_quest_ids():
    Quest._NEXT_ID = 1
    yield
    Quest._NEXT_ID = 1


class _Bus:
    def __init__(self):
        self.events = []

    def emit(self, payload):
        self.events.append(dict(payload))

    def of_type(self, etype):
        return [e for e in self.events if e.get("type") == etype]


class _FakeHero:
    def __init__(self, x=100.0, y=100.0):
        self.name = "QuestHero"
        self.hero_id = "wk126_h1"
        self.x = x
        self.y = y
        self.health_percent = 1.0
        self.state = HeroState.IDLE
        self.intent = "idle"
        self.target = None
        self.target_position = None
        self.is_inside_building = False
        self.pending_llm_decision = False
        self.is_alive = True
        self._pending_quest_offer = None
        self._quest_decline_until_ms = {}
        self._quest_approach_cooldown_until_ms = 0
        self._quest_offer_commit_until_ms = 0
        self._frontier_commit_until_ms = 0

    def distance_to(self, x, y):
        return ((self.x - x) ** 2 + (self.y - y) ** 2) ** 0.5

    def set_target_position(self, x, y):
        self.target_position = (float(x), float(y))


def _lair(x=800.0, y=800.0):
    return SimpleNamespace(
        entity_id="lair_001", is_lair=True, hp=200,
        center_x=x, center_y=y, x=x - 32, y=y - 32, building_type="rat_lair",
    )


def _setup(quest_type="raid_lair", target=None, reward=140, count=1):
    """A live QuestSystem behind a sim stub + the boundary view tuples."""
    qs = QuestSystem()
    bus = _Bus()
    if target is None:
        target = _lair()
    quest = qs.create_quest(_GIVER_ID, quest_type, target, reward, count=count)
    sim = SimpleNamespace(quest_system=qs, event_bus=bus)

    giver = QuestGiverAiInfo(
        giver_id=_GIVER_ID, x=200.0, y=100.0, is_open=True,
        interact_radius=float(QUEST_GIVER_INTERACT_PX),
    )
    view = SimpleNamespace(
        world=None,
        heroes=(),
        enemies=(),
        buildings=(target,) if quest_type == "raid_lair" else (),
        bounties=(),
        pois=(),
        player_gold=0,
        castle=None,
        wave=0,
        quests=(quest.to_ai_info(),),
        quest_givers=(giver,),
        commands=SimpleNamespace(_sim=sim),  # the sim-owned sink shape
    )
    return qs, quest, bus, view


def _stage_offer(hero, quest, expires_in_ms=30_000):
    hero._pending_quest_offer = {
        "giver_id": _GIVER_ID,
        "quest_id": int(quest.quest_id),
        "quest_type": str(quest.quest_type),
        "target": quest.target_summary(),
        "reward": int(quest.reward),
        "count": int(quest.count),
        "x": float(quest.get_goal_position()[0]),
        "y": float(quest.get_goal_position()[1]),
        "staged_ms": _NOW_MS,
        "expires_ms": _NOW_MS + expires_in_ms,
    }


# ---------------------------------------------------------------------------
# llm_brain=None: arrival resolves to a DETERMINISTIC ACCEPT (decision of record)
# ---------------------------------------------------------------------------

def test_no_llm_arrival_is_deterministic_accept_raid_lair():
    qs, quest, bus, view = _setup("raid_lair")
    ai = BasicAI(llm_brain=None)
    hero = _FakeHero()

    begin_quest_offer_decision(ai, hero, _GIVER_ID, view)

    assert quest.accepted_by == hero.hero_id
    started = bus.of_type("quest_started")
    assert len(started) == 1
    assert started[0]["quest_id"] == quest.quest_id
    assert started[0]["hero_id"] == hero.hero_id
    # raid objective: the live lair becomes the hero target, hero is MOVING.
    assert hero.target is quest.target
    assert hero.state == HeroState.MOVING
    assert hero.target_position is not None
    # The staged offer is consumed.
    assert hero._pending_quest_offer is None


def test_arrival_handler_dispatch_reaches_decision():
    """dispatch_arrival routes a quest_offer target through the new handler."""
    from ai.arrival_handlers import dispatch_arrival

    qs, quest, bus, view = _setup("raid_lair")
    ai = BasicAI(llm_brain=None)
    hero = _FakeHero()
    hero.state = HeroState.MOVING
    hero.target = {"type": "quest_offer", "giver_id": _GIVER_ID, "started_ms": _NOW_MS}
    hero.target_position = (200.0, 100.0)

    assert dispatch_arrival(ai, hero, view) is True
    assert quest.accepted_by == hero.hero_id  # no-LLM deterministic accept
    assert len(bus.of_type("quest_started")) == 1


# ---------------------------------------------------------------------------
# Forced decline: 15-sim-min per-giver cooldown + QUEST_DECLINED + re-consider
# ---------------------------------------------------------------------------

def test_forced_decline_sets_15_min_cooldown_and_event():
    qs, quest, bus, view = _setup("raid_lair")
    ai = BasicAI(llm_brain=None)
    hero = _FakeHero()
    _stage_offer(hero, quest)

    consumed = maybe_apply_quest_offer_decision(
        ai, hero, {"action": QUEST_OFFER_DECLINE_ACTION, "reasoning": "not today"},
        view, source="mock",
    )

    assert consumed is True
    assert hero._quest_decline_until_ms[_GIVER_ID] == _NOW_MS + QUEST_DECLINE_COOLDOWN_MS
    assert QUEST_DECLINE_COOLDOWN_MS == 900_000  # 15 SIM-minutes, the locked contract
    declined = bus.of_type("quest_declined")
    assert len(declined) == 1
    assert declined[0]["giver_id"] == _GIVER_ID
    # Quest stays open for OTHER heroes; this hero's staged offer is cleared.
    assert quest.is_open
    assert hero._pending_quest_offer is None
    assert hero._quest_offer_commit_until_ms == 0
    assert len(bus.of_type("quest_started")) == 0


def test_declined_giver_skipped_then_reconsidered_after_15_min():
    """The approach selector skips the declined giver for <15 sim-min and
    re-considers it once the cooldown elapses (sim clock advanced)."""
    qs, quest, bus, view = _setup("raid_lair")
    ai = BasicAI(llm_brain=None)

    class _ZeroRng:
        def random(self):
            return 0.0  # always passes the occasionally gate

    ai._ai_rng = _ZeroRng()
    hero = _FakeHero()
    _stage_offer(hero, quest)
    maybe_apply_quest_offer_decision(
        ai, hero, {"action": QUEST_OFFER_DECLINE_ACTION}, view, source="mock"
    )

    # 1 sim-ms before the cooldown elapses: still skipped.
    set_sim_now_ms(_NOW_MS + QUEST_DECLINE_COOLDOWN_MS - 1)
    assert maybe_approach_quest_giver(ai, hero, view) is False
    assert hero.target is None

    # At/after the cooldown: the giver is a candidate again.
    set_sim_now_ms(_NOW_MS + QUEST_DECLINE_COOLDOWN_MS)
    assert maybe_approach_quest_giver(ai, hero, view) is True
    assert hero.target["type"] == "quest_offer"
    assert hero.target["giver_id"] == _GIVER_ID


def test_decline_quest_literal_action_also_declines():
    """Future-proofing: a literal 'decline_quest' action (if a later pipeline
    lets it through) maps to decline as well."""
    qs, quest, bus, view = _setup("raid_lair")
    ai = BasicAI(llm_brain=None)
    hero = _FakeHero()
    _stage_offer(hero, quest)

    assert maybe_apply_quest_offer_decision(
        ai, hero, {"action": "decline_quest"}, view, source="llm"
    ) is True
    assert _GIVER_ID in hero._quest_decline_until_ms
    assert quest.is_open


# ---------------------------------------------------------------------------
# Forced accept: objective target per quest type
# ---------------------------------------------------------------------------

def test_accept_find_poi_sets_visit_poi_target():
    poi = SimpleNamespace(entity_id="poi_001", center_x=640.0, center_y=320.0)
    qs, quest, bus, view = _setup("find_poi", target=poi)
    ai = BasicAI(llm_brain=None)
    hero = _FakeHero()
    _stage_offer(hero, quest)

    assert maybe_apply_quest_offer_decision(
        ai, hero, {"action": QUEST_OFFER_ACCEPT_ACTION}, view, source="mock"
    ) is True
    assert quest.accepted_by == hero.hero_id
    assert isinstance(hero.target, dict) and hero.target["type"] == "visit_poi"
    assert hero.target["poi"] is poi
    assert hero.target_position == (640.0, 320.0)
    assert hero.state == HeroState.MOVING


def test_accept_explore_far_sets_frontier_leg_with_commit():
    qs, quest, bus, view = _setup("explore_far", target=(40, 50))
    ai = BasicAI(llm_brain=None)
    hero = _FakeHero()
    _stage_offer(hero, quest)

    assert maybe_apply_quest_offer_decision(
        ai, hero, {"action": QUEST_OFFER_ACCEPT_ACTION}, view, source="mock"
    ) is True
    assert quest.accepted_by == hero.hero_id
    assert hero.target == {"type": "explore_frontier"}
    assert hero.target_position == ((40 + 0.5) * TILE_SIZE, (50 + 0.5) * TILE_SIZE)
    assert hero._frontier_commit_until_ms > _NOW_MS  # long travel commit
    assert hero.state == HeroState.MOVING


def test_accept_slay_assigns_quest_and_resumes_roaming():
    qs, quest, bus, view = _setup("slay_enemy_type", target="goblin", count=5)
    ai = BasicAI(llm_brain=None)
    hero = _FakeHero()
    _stage_offer(hero, quest)

    assert maybe_apply_quest_offer_decision(
        ai, hero, {"action": QUEST_OFFER_ACCEPT_ACTION}, view, source="mock"
    ) is True
    assert quest.accepted_by == hero.hero_id
    assert len(bus.of_type("quest_started")) == 1
    # No fixed objective: the hero roams/hunts (explore set a wander target);
    # kills are counted by QuestSystem.on_enemy_killed.
    assert hero._pending_quest_offer is None
    assert hero.target_position is not None


def test_accept_when_offer_already_taken_is_clean_noop():
    """The offer vanished between staging and the verdict: no crash, no decline
    cooldown, staged offer cleared."""
    qs, quest, bus, view = _setup("raid_lair")
    other = _FakeHero()
    other.hero_id = "someone_else"
    quest.accept(other)

    ai = BasicAI(llm_brain=None)
    hero = _FakeHero()
    _stage_offer(hero, quest)

    assert maybe_apply_quest_offer_decision(
        ai, hero, {"action": QUEST_OFFER_ACCEPT_ACTION}, view, source="mock"
    ) is True
    assert quest.accepted_by == "someone_else"
    assert hero._pending_quest_offer is None
    assert _GIVER_ID not in hero._quest_decline_until_ms
    assert len(bus.of_type("quest_started")) == 0


def test_no_pending_offer_means_bridge_branch_is_inert():
    qs, quest, bus, view = _setup("raid_lair")
    ai = BasicAI(llm_brain=None)
    hero = _FakeHero()  # nothing staged

    assert maybe_apply_quest_offer_decision(
        ai, hero, {"action": QUEST_OFFER_ACCEPT_ACTION}, view, source="llm"
    ) is False
    assert quest.is_open


# ---------------------------------------------------------------------------
# QUEST_OFFER decision moment + prompt context block
# ---------------------------------------------------------------------------

def test_quest_offer_moment_fires_only_while_staged():
    qs, quest, bus, view = _setup("raid_lair")
    hero = _FakeHero()
    gs = {"enemies": [], "buildings": [], "heroes": [hero]}

    before = determine_decision_moment(hero, gs, now_ms=_NOW_MS)
    assert before is None or before.moment_type != DecisionMomentType.QUEST_OFFER

    _stage_offer(hero, quest)
    m = determine_decision_moment(hero, gs, now_ms=_NOW_MS)
    assert m is not None and m.moment_type == DecisionMomentType.QUEST_OFFER
    assert set(m.allowed_actions) == {QUEST_OFFER_ACCEPT_ACTION, QUEST_OFFER_DECLINE_ACTION}

    # Expired offers stop firing.
    expired = determine_decision_moment(hero, gs, now_ms=_NOW_MS + 30_001)
    assert expired is None or expired.moment_type != DecisionMomentType.QUEST_OFFER

    # And combat suppresses the moment.
    hero.state = HeroState.FIGHTING
    hero.health_percent = 1.0
    fight = determine_decision_moment(hero, gs, now_ms=_NOW_MS)
    assert fight is None or fight.moment_type != DecisionMomentType.QUEST_OFFER


def test_prompt_context_carries_quest_offer_block_only_for_quest_moment():
    from game.entities.hero import Hero

    from ai.decision_moments import moment_quest_offer
    from ai.profile_context_adapter import build_llm_context_for_moment

    qs, quest, bus, view = _setup("raid_lair", reward=140)
    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="wk126_ph", name="Prompter")
    hero.state = HeroState.IDLE
    _stage_offer(hero, quest)
    gs = {"enemies": [], "buildings": [], "heroes": [hero], "bounties": [], "pois": [], "world": None}

    moment = moment_quest_offer(hero, now_ms=_NOW_MS)
    assert moment is not None
    ctx = build_llm_context_for_moment(hero, gs, moment, now_ms=_NOW_MS)
    block = ctx.get("quest_offer")
    assert isinstance(block, dict)
    assert block["quest_type"] == "raid_lair"
    assert block["reward_gold"] == 140
    assert block["target"] == "lair_001"
    assert "objective_distance_tiles" in block
    # The carrier contract is spelled out for the model.
    assert QUEST_OFFER_ACCEPT_ACTION in block["decision_rule"]
    assert QUEST_OFFER_DECLINE_ACTION in block["decision_rule"]
    assert "accept_quest" in block["decision_rule"]
    assert "decline_quest" in block["decision_rule"]

    # Non-quest moments: the key is OMITTED entirely (other prompts unchanged).
    from ai.decision_moments import DecisionMoment

    other = DecisionMoment(
        moment_type=DecisionMomentType.IDLE_SEEKING_ACTIVITY,
        urgency=0,
        reason="test",
        allowed_actions=("explore",),
        context_focus=(),
        cooldown_ms=1000,
    )
    ctx2 = build_llm_context_for_moment(hero, gs, other, now_ms=_NOW_MS)
    assert "quest_offer" not in ctx2


# ---------------------------------------------------------------------------
# MockProvider quest-offer responder + full llm_brain parse/validate survival
# ---------------------------------------------------------------------------

def _mock_quest_prompt(reward_gold: int) -> str:
    blob = {
        "task": "Choose the best next action for this decision moment.",
        "context": {
            "moment": {
                "type": "quest_offer",
                "allowed_actions": [QUEST_OFFER_ACCEPT_ACTION, QUEST_OFFER_DECLINE_ACTION],
            },
            "quest_offer": {"quest_type": "raid_lair", "reward_gold": reward_gold},
            "allowed_actions": [QUEST_OFFER_ACCEPT_ACTION, QUEST_OFFER_DECLINE_ACTION],
        },
        "allowed_actions": [QUEST_OFFER_ACCEPT_ACTION, QUEST_OFFER_DECLINE_ACTION],
    }
    return json.dumps(blob, indent=2) + "\n\nRespond with a single JSON object."


def test_mock_responder_accepts_funded_and_declines_miserly():
    from ai.providers.mock_provider import MockProvider

    provider = MockProvider()
    rich = json.loads(provider._mock_autonomous_decision(_mock_quest_prompt(140)))
    poor = json.loads(provider._mock_autonomous_decision(_mock_quest_prompt(10)))

    assert rich["action"] == QUEST_OFFER_ACCEPT_ACTION
    assert "accept_quest" in rich["reasoning"]
    assert poor["action"] == QUEST_OFFER_DECLINE_ACTION
    assert "decline_quest" in poor["reasoning"]


def test_mock_verdict_survives_llm_brain_parse_and_validate():
    """End-to-end through LLMBrain._process_request (synchronous): the carrier
    action must survive _parse_response (ToolAction vocab) AND
    validate_autonomous_decision (moment allowlist) — i.e. NOT be munged into a
    generic fallback decision."""
    from game.entities.hero import Hero

    from ai.decision_moments import moment_quest_offer
    from ai.llm_brain import LLMBrain
    from ai.profile_context_adapter import build_llm_context_for_moment

    qs_rich, quest_rich, _, _ = _setup("raid_lair", reward=140)

    hero = Hero(100.0, 100.0, hero_class="warrior", hero_id="wk126_mh", name="Mockling")
    hero.state = HeroState.IDLE
    _stage_offer(hero, quest_rich)
    gs = {"enemies": [], "buildings": [], "heroes": [hero], "bounties": [], "pois": [], "world": None}

    moment = moment_quest_offer(hero, now_ms=_NOW_MS)
    aut = build_llm_context_for_moment(hero, gs, moment, now_ms=_NOW_MS)
    context = {
        "hero": {"name": hero.name, "health_percent": 100, "gold": 0},
        "inventory": {"potions": 0},
        "situation": {
            "critical_health": False, "low_health": False, "in_combat": False,
            "can_shop": False, "enemies_nearby": False,
        },
        "shop_items": [],
        "wk50_autonomous": aut,
    }

    brain = LLMBrain("mock")
    try:
        decision = brain._process_request(hero.name, context)
    finally:
        brain.stop()

    assert decision["action"] == QUEST_OFFER_ACCEPT_ACTION, (
        "the mock quest verdict was munged by parse/validate — the carrier "
        "contract broke"
    )
    assert "accept_quest" in decision.get("reasoning", "")


def test_bridge_apply_routes_decision_to_quest_branch():
    """apply_llm_decision consumes the verdict via the quest branch (the REAL
    wiring, unlike the accept_bounty no-op precedent)."""
    from ai.behaviors.llm_bridge import apply_llm_decision

    qs, quest, bus, view = _setup("raid_lair")
    ai = BasicAI(llm_brain=None)
    hero = _FakeHero()
    _stage_offer(hero, quest)

    apply_llm_decision(
        ai,
        hero,
        {"action": QUEST_OFFER_DECLINE_ACTION, "reasoning": "too risky", "target": ""},
        view,
        source="mock",
        context={"hero": {}, "inventory": {}, "situation": {}},
    )

    assert hero._quest_decline_until_ms[_GIVER_ID] == _NOW_MS + QUEST_DECLINE_COOLDOWN_MS
    assert len(bus.of_type("quest_declined")) == 1
    # The generic 'retreat' action was NOT executed (no retreat state change).
    assert hero.state == HeroState.IDLE
