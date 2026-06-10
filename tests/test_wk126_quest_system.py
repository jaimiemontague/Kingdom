"""WK126-T1/T3 — Quest data model + QuestSystem + economy escrow gates.

Covers (per the wk126 plan, T1 + T3 headless gates):
- create / escrow (funding debits the treasury; insufficient gold blocks creation)
- accept / complete / payout (taxed via hero.add_gold — identical to bounty claims)
- test_quest_system_noop_when_empty: QuestSystem.update with NO quests emits no
  events, mutates no state, and draws NO randomness (digest guard #2)
- the SimEngine.create_quest engine action (fund + arm + QUEST_OFFERED + "!" flip)

These are pure-headless unit tests: no GameEngine build needed (the spawn /
engine-integration paths are tests/test_wk126_quest_giver_spawn.py).
"""
from __future__ import annotations

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from config import TAX_RATE
from game.events import EventBus, GameEventType
from game.sim.timebase import set_sim_now_ms
from game.systems.economy import EconomySystem
from game.systems.protocol import SystemContext
from game.systems.quest import Quest, QuestAiInfo, QuestSystem


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    set_sim_now_ms(0)
    yield
    pygame.quit()


def _make_hero(hero_id="wk126_h1", name="Quenton", x=100.0, y=100.0):
    from game.entities.hero import Hero

    return Hero(x, y, hero_class="warrior", hero_id=hero_id, name=name)


class _FakeLair:
    """Duck-typed lair target (identity-matched, like attack_lair bounties)."""

    building_type = "goblin_camp"
    is_lair = True

    def __init__(self, cx=640.0, cy=640.0, hp=120):
        self.center_x = cx
        self.center_y = cy
        self.x = cx
        self.y = cy
        self.hp = hp


def _recording_bus():
    bus = EventBus()
    events: list[dict] = []
    bus.subscribe("*", events.append)
    return bus, events


def _ctx(heroes=(), enemies=(), buildings=(), world=None, economy=None, bus=None):
    return SystemContext(
        heroes=list(heroes),
        enemies=list(enemies),
        buildings=list(buildings),
        world=world,
        economy=economy if economy is not None else EconomySystem(),
        event_bus=bus if bus is not None else EventBus(),
    )


# ---------------------------------------------------------------------------
# Quest model
# ---------------------------------------------------------------------------

def test_quest_creation_and_is_open():
    lair = _FakeLair()
    quest = Quest("b00000007", "raid_lair", lair, 140)
    assert quest.quest_id >= 1
    assert quest.giver_id == "b00000007"
    assert quest.quest_type == "raid_lair"
    assert quest.target is lair
    assert quest.reward == 140
    assert quest.funded is True
    assert quest.accepted_by is None
    assert quest.is_open is True
    assert quest.count == 1 and quest.progress == 0

    info = quest.to_ai_info()
    assert isinstance(info, QuestAiInfo)
    assert info.is_open is True
    assert (info.x, info.y) == (lair.center_x, lair.center_y)


def test_quest_accept_closes_the_offer():
    hero = _make_hero()
    quest = Quest("b1", "raid_lair", _FakeLair(), 60)
    assert quest.accept(hero) is True
    assert quest.accepted_by == hero.hero_id
    assert quest.is_open is False
    # A second hero cannot take an already-accepted offer.
    other = _make_hero(hero_id="wk126_h2", name="Other")
    assert quest.accept(other) is False
    assert quest.accepted_by == hero.hero_id


def test_slay_quest_count_defaults_and_clamps():
    q = Quest("b1", "slay_enemy_type", "goblin", 60, count=3)
    assert q.count == 3
    # Non-slay quests always have count 1 regardless of what was passed.
    q2 = Quest("b1", "raid_lair", _FakeLair(), 60, count=5)
    assert q2.count == 1


# ---------------------------------------------------------------------------
# Digest guard #2 — complete no-op when empty
# ---------------------------------------------------------------------------

def test_quest_system_noop_when_empty():
    """update() with no quests: no events, no RNG draw, no state mutation."""
    from game.sim.determinism import get_rng

    qs = QuestSystem()
    bus, events = _recording_bus()
    ctx = _ctx(heroes=[_make_hero()], bus=bus)

    rng_default_state = get_rng().getstate()
    rng_quest_state = get_rng("quest").getstate()

    for _ in range(10):
        qs.update(ctx, 1 / 60)
    bus.flush()

    assert events == [], "empty QuestSystem.update must emit nothing"
    assert qs.quests == []
    assert qs.total_completed == 0 and qs.total_failed == 0
    assert get_rng().getstate() == rng_default_state, "empty update drew from the default RNG stream"
    assert get_rng("quest").getstate() == rng_quest_state, "empty update drew from a quest RNG stream"


# ---------------------------------------------------------------------------
# Economy escrow (T3)
# ---------------------------------------------------------------------------

def test_fund_quest_debits_treasury_and_logs():
    economy = EconomySystem()
    start = economy.player_gold
    assert economy.fund_quest(140) is True
    assert economy.player_gold == start - 140
    assert {"type": "quest_funded", "amount": 140} in economy.transaction_log


def test_fund_quest_insufficient_gold_blocks():
    economy = EconomySystem()
    economy.player_gold = 50
    assert economy.fund_quest(140) is False
    assert economy.player_gold == 50
    assert all(t.get("type") != "quest_funded" for t in economy.transaction_log)


def test_engine_create_quest_action_funds_and_arms():
    """SimEngine.create_quest = the T9 UI confirm action (tested unbound)."""
    from types import SimpleNamespace

    from game.sim_engine import SimEngine

    economy = EconomySystem()
    qs = QuestSystem()
    bus, events = _recording_bus()
    giver = SimpleNamespace(giver_id="b00000003", is_open=False)
    fake = SimpleNamespace(economy=economy, quest_system=qs, event_bus=bus, quest_givers=[giver])

    start = economy.player_gold
    quest = SimEngine.create_quest(fake, "b00000003", "slay_enemy_type", "goblin", 140, count=5)
    bus.flush()

    assert quest is not None and quest in qs.quests
    assert quest.count == 5
    assert economy.player_gold == start - 140, "escrow must be debited at creation"
    offered = [e for e in events if e["type"] == GameEventType.QUEST_OFFERED.value]
    assert len(offered) == 1
    assert offered[0]["giver_id"] == "b00000003" and offered[0]["reward"] == 140
    assert giver.is_open is True, "the giver's '!' must flip on immediately"
    assert qs.has_open_quest_for("b00000003") is True


def test_engine_create_quest_blocked_when_unaffordable():
    from types import SimpleNamespace

    from game.sim_engine import SimEngine

    economy = EconomySystem()
    economy.player_gold = 10
    qs = QuestSystem()
    bus, events = _recording_bus()
    fake = SimpleNamespace(economy=economy, quest_system=qs, event_bus=bus, quest_givers=[])

    quest = SimEngine.create_quest(fake, "b1", "raid_lair", _FakeLair(), 280)
    bus.flush()

    assert quest is None, "insufficient gold must block creation"
    assert qs.quests == []
    assert economy.player_gold == 10
    assert events == []


# ---------------------------------------------------------------------------
# Complete + payout (taxed via hero.add_gold, like bounty claims)
# ---------------------------------------------------------------------------

def test_complete_pays_accepted_hero_with_tax():
    qs = QuestSystem()
    bus, events = _recording_bus()
    hero = _make_hero()
    lair = _FakeLair()
    quest = qs.create_quest("b1", "raid_lair", lair, 140)
    assert quest.accept(hero)

    qs.on_lair_cleared(lair, [hero], bus)
    bus.flush()

    assert quest.completed is True
    expected_tax = int(140 * TAX_RATE)
    assert hero.gold == 140 - expected_tax, "payout must go through the 25%-tax add_gold path"
    assert hero.taxed_gold == expected_tax
    completed = [e for e in events if e["type"] == GameEventType.QUEST_COMPLETED.value]
    assert len(completed) == 1
    assert completed[0]["hero_id"] == hero.hero_id
    assert completed[0]["reward"] == 140
    # HUD toast rides the event bus too.
    assert any(e["type"] == GameEventType.HUD_MESSAGE.value for e in events)


def test_completed_quest_is_cleaned_up_and_giver_rearmable():
    qs = QuestSystem()
    bus, _events = _recording_bus()
    hero = _make_hero()
    lair = _FakeLair()
    quest = qs.create_quest("b1", "raid_lair", lair, 60)
    quest.accept(hero)
    qs.on_lair_cleared(lair, [hero], bus)

    # The cleanup pass in update() drops finished quests -> giver re-armable.
    qs.update(_ctx(heroes=[hero], buildings=[lair], bus=bus), 1 / 60)
    assert qs.quests == []
    assert qs.has_open_quest_for("b1") is False
    # Re-arming works: a brand-new quest on the same giver is open again.
    q2 = qs.create_quest("b1", "find_poi", lair, 60)
    assert qs.has_open_quest_for("b1") is True and q2.is_open
