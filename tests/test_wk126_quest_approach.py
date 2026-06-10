"""WK126-T5 — quest-giver approach behavior (Agent 06).

THE key digest proof lives here (plan T5 acceptance): with NO quest-givers on
the view, ``maybe_approach_quest_giver`` returns False WITHOUT drawing from
``ai._ai_rng`` — asserted by comparing the RNG's full internal state before and
after the call. Consuming the seeded stream when no giver exists would shift
every downstream draw and break the WK67 300-tick AI-decision digest even
though no hero moved (plan "CENTRAL CONSTRAINT" rule 1).

Also covered: the exact guard ordering (health / commitment / cooldowns /
candidates all return False BEFORE any RNG draw), the decline-cooldown skip,
the failed-roll approach cooldown, and the successful commit shape
(quest_offer target dict + MOVING + commit window + approach cooldown).

All sim-time is pinned via ``game.sim.timebase.set_sim_now_ms`` (restored after
each test) — no wall-clock anywhere.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from config import (
    QUEST_APPROACH_COOLDOWN_MS,
    QUEST_GIVER_INTERACT_PX,
    QUEST_OFFER_COMMIT_MS,
    TILE_SIZE,
)
from game.entities.hero import HeroState
from game.sim.timebase import set_sim_now_ms
from game.systems.quest import QuestGiverAiInfo

from ai.basic_ai import BasicAI
from ai.behaviors.quest_offer import maybe_approach_quest_giver

_NOW_MS = 1_000_000


@pytest.fixture(autouse=True)
def _pinned_sim_clock():
    set_sim_now_ms(_NOW_MS)
    yield
    set_sim_now_ms(None)


class _FakeHero:
    """Minimal hero surface the approach behavior reads/writes."""

    def __init__(self, x=100.0, y=100.0, health_percent=1.0):
        self.name = "TestHero"
        self.hero_id = "wk126_h1"
        self.x = x
        self.y = y
        self.health_percent = health_percent
        self.state = HeroState.IDLE
        self.target = None
        self.target_position = None
        self.is_inside_building = False
        self.pending_llm_decision = False
        self._pending_quest_offer = None
        self._quest_decline_until_ms = {}
        self._quest_approach_cooldown_until_ms = 0
        self._quest_offer_commit_until_ms = 0

    def distance_to(self, x, y):
        return ((self.x - x) ** 2 + (self.y - y) ** 2) ** 0.5

    def set_target_position(self, x, y):
        self.target_position = (float(x), float(y))


class _CountingRng:
    """RNG stub recording every draw; returns a scripted value."""

    def __init__(self, value=0.0):
        self.value = value
        self.draws = 0

    def random(self):
        self.draws += 1
        return self.value

    def uniform(self, a, b):  # pragma: no cover — approach never calls it
        self.draws += 1
        return a

    def randrange(self, n):  # pragma: no cover
        self.draws += 1
        return 0


def _giver(gid="b00000007", x=200.0, y=100.0, is_open=True):
    return QuestGiverAiInfo(
        giver_id=gid, x=x, y=y, is_open=is_open,
        interact_radius=float(QUEST_GIVER_INTERACT_PX),
    )


def _view(quest_givers=(), quests=()):
    return SimpleNamespace(
        world=None,
        heroes=(),
        enemies=(),
        buildings=(),
        bounties=(),
        pois=(),
        player_gold=0,
        castle=None,
        wave=0,
        quests=tuple(quests),
        quest_givers=tuple(quest_givers),
        commands=None,
    )


def _ai_with_rng(rng):
    ai = BasicAI(llm_brain=None)
    ai._ai_rng = rng
    return ai


# ---------------------------------------------------------------------------
# THE digest proof: no givers -> False, REAL RNG state byte-identical
# ---------------------------------------------------------------------------

def test_no_givers_returns_false_without_rng_draw():
    """Guard (a): empty view.quest_givers is a complete no-op — the REAL seeded
    ai._ai_rng position must be unchanged (the WK67 digest-safety proof)."""
    ai = BasicAI(llm_brain=None)
    ai._ai_rng.seed(3)
    hero = _FakeHero()
    state_before = ai._ai_rng.getstate()

    result = maybe_approach_quest_giver(ai, hero, _view(quest_givers=()))

    assert result is False
    assert ai._ai_rng.getstate() == state_before, (
        "maybe_approach_quest_giver consumed the seeded AI RNG with NO quest-"
        "givers present — this shifts every downstream draw and breaks the "
        "WK67 AI-decision digest (plan CENTRAL CONSTRAINT rule 1)."
    )
    # And zero hero mutation.
    assert hero.target is None
    assert hero.target_position is None
    assert hero.state == HeroState.IDLE
    assert hero._quest_approach_cooldown_until_ms == 0
    assert hero._quest_offer_commit_until_ms == 0


def test_no_givers_short_circuits_before_other_guards():
    """Guard (a) runs FIRST: even a hero that would fail every later guard
    (hurt, committed, cooldowned) gets the same silent False with no draw."""
    rng = _CountingRng(0.0)
    ai = _ai_with_rng(rng)
    hero = _FakeHero(health_percent=0.1)
    hero.state = HeroState.MOVING
    hero.target = {"type": "bounty"}
    hero._quest_approach_cooldown_until_ms = _NOW_MS + 99_999

    assert maybe_approach_quest_giver(ai, hero, _view()) is False
    assert rng.draws == 0


# ---------------------------------------------------------------------------
# Guards (b)-(e): all pre-RNG (no draw on any early-out)
# ---------------------------------------------------------------------------

def test_health_gate_blocks_before_rng():
    rng = _CountingRng(0.0)
    ai = _ai_with_rng(rng)
    hero = _FakeHero(health_percent=0.5)  # < QUEST_MIN_ACCEPT_HEALTH_PCT (0.65)

    assert maybe_approach_quest_giver(ai, hero, _view([_giver()])) is False
    assert rng.draws == 0
    assert hero.target is None


def test_committed_hero_blocks_before_rng():
    rng = _CountingRng(0.0)
    ai = _ai_with_rng(rng)
    hero = _FakeHero()
    hero.state = HeroState.MOVING
    hero.target = {"type": "bounty", "bounty_id": 1}

    assert maybe_approach_quest_giver(ai, hero, _view([_giver()])) is False
    assert rng.draws == 0


def test_approach_cooldown_blocks_before_rng():
    rng = _CountingRng(0.0)
    ai = _ai_with_rng(rng)
    hero = _FakeHero()
    hero._quest_approach_cooldown_until_ms = _NOW_MS + 1

    assert maybe_approach_quest_giver(ai, hero, _view([_giver()])) is False
    assert rng.draws == 0


def test_declined_giver_is_skipped_without_rng():
    """Guard (d): a giver on this hero's 15-min decline cooldown is not a
    candidate; with no other giver the function returns False with NO draw."""
    rng = _CountingRng(0.0)
    ai = _ai_with_rng(rng)
    hero = _FakeHero()
    giver = _giver(gid="b00000007")
    hero._quest_decline_until_ms = {"b00000007": _NOW_MS + 900_000}

    assert maybe_approach_quest_giver(ai, hero, _view([giver])) is False
    assert rng.draws == 0
    assert hero.target is None


def test_closed_giver_not_a_candidate():
    rng = _CountingRng(0.0)
    ai = _ai_with_rng(rng)
    hero = _FakeHero()

    assert maybe_approach_quest_giver(ai, hero, _view([_giver(is_open=False)])) is False
    assert rng.draws == 0


def test_out_of_range_giver_not_a_candidate():
    rng = _CountingRng(0.0)
    ai = _ai_with_rng(rng)
    hero = _FakeHero(x=0.0, y=0.0)
    far = _giver(x=TILE_SIZE * 100.0, y=TILE_SIZE * 100.0)

    assert maybe_approach_quest_giver(ai, hero, _view([far])) is False
    assert rng.draws == 0


# ---------------------------------------------------------------------------
# Guard (f): the roll is LAST, and exactly one draw happens
# ---------------------------------------------------------------------------

def test_forced_roll_commits_to_quest_offer():
    rng = _CountingRng(0.0)  # < QUEST_APPROACH_CHANCE -> proceed
    ai = _ai_with_rng(rng)
    hero = _FakeHero()
    giver = _giver(gid="b00000007", x=200.0, y=100.0)

    result = maybe_approach_quest_giver(ai, hero, _view([giver]))

    assert result is True
    assert rng.draws == 1, "exactly ONE RNG draw (the occasionally gate) is allowed"
    assert hero.target == {"type": "quest_offer", "giver_id": "b00000007", "started_ms": _NOW_MS}
    assert hero.state == HeroState.MOVING
    assert hero.target_position == (200.0, 100.0)
    assert hero._quest_offer_commit_until_ms == _NOW_MS + QUEST_OFFER_COMMIT_MS
    assert hero._quest_approach_cooldown_until_ms == _NOW_MS + QUEST_APPROACH_COOLDOWN_MS


def test_failed_roll_sets_cooldown_but_no_commit():
    rng = _CountingRng(0.99)  # >= QUEST_APPROACH_CHANCE -> "not this time"
    ai = _ai_with_rng(rng)
    hero = _FakeHero()

    result = maybe_approach_quest_giver(ai, hero, _view([_giver()]))

    assert result is False
    assert rng.draws == 1
    assert hero.target is None
    assert hero.state == HeroState.IDLE
    # The failed roll arms the approach cooldown so the hero re-rolls at most
    # once per QUEST_APPROACH_COOLDOWN_MS, not every tick.
    assert hero._quest_approach_cooldown_until_ms == _NOW_MS + QUEST_APPROACH_COOLDOWN_MS
    assert hero._quest_offer_commit_until_ms == 0


def test_nearest_candidate_wins():
    rng = _CountingRng(0.0)
    ai = _ai_with_rng(rng)
    hero = _FakeHero(x=0.0, y=0.0)
    near = _giver(gid="b_near", x=TILE_SIZE * 2.0, y=0.0)
    far = _giver(gid="b_far", x=TILE_SIZE * 10.0, y=0.0)

    assert maybe_approach_quest_giver(ai, hero, _view([far, near])) is True
    assert hero.target["giver_id"] == "b_near"


def test_patrol_wander_is_preemptible_but_frontier_commit_is_not():
    rng = _CountingRng(0.0)
    ai = _ai_with_rng(rng)

    patroller = _FakeHero()
    patroller.state = HeroState.MOVING
    patroller.target = {"type": "patrol"}
    assert maybe_approach_quest_giver(ai, patroller, _view([_giver()])) is True

    rng2 = _CountingRng(0.0)
    ai2 = _ai_with_rng(rng2)
    ranger = _FakeHero()
    ranger.state = HeroState.MOVING
    ranger.target = {"type": "explore_frontier"}
    assert maybe_approach_quest_giver(ai2, ranger, _view([_giver()])) is False
    assert rng2.draws == 0


def test_quest_offer_registered_as_committed_destination():
    """quest_offer is in _COMMITTED_DESTINATION_TYPES (intent conviction) and in
    the typed TargetType vocabulary (arrival registry dispatch)."""
    from ai.basic_ai import _COMMITTED_DESTINATION_TYPES
    from ai.contracts import TargetType

    assert "quest_offer" in _COMMITTED_DESTINATION_TYPES
    assert TargetType.from_str("quest_offer") == TargetType.QUEST_OFFER

    from ai.arrival_handlers import ARRIVAL_HANDLERS, handle_quest_offer_arrival

    assert ARRIVAL_HANDLERS[TargetType.QUEST_OFFER] is handle_quest_offer_arrival
