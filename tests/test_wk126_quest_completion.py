"""WK126-T7 — completion detection for ALL FOUR quest types + failure paths.

One test per type proving detect -> pay -> QUEST_COMPLETED:
- raid_lair        via the LAIR_CLEARED routing hook (on_lair_cleared)
- slay_enemy_type  via the ENEMY_KILLED counter (N-1 kills != done, Nth = done;
                   wrong hero / wrong enemy type never count)
- find_poi         via accepting-hero proximity poll in QuestSystem.update
- explore_far      via the fog SEEN poll around the target tile

Failure paths (PM decision of record: escrow CONSUMED, giver re-armable,
QUEST_FAILED emitted):
- target destroyed before acceptance
- accepting hero dies

All headless, deterministic: sim timebase pinned, no RNG anywhere in the system.
"""
from __future__ import annotations

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from config import QUEST_EXPLORE_REVEAL_RADIUS_TILES, TAX_RATE, TILE_SIZE
from game.events import EventBus, GameEventType
from game.sim.timebase import set_sim_now_ms
from game.systems.economy import EconomySystem
from game.systems.protocol import SystemContext
from game.systems.quest import QuestSystem
from game.world import Visibility


@pytest.fixture(autouse=True)
def _pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    set_sim_now_ms(0)
    yield
    pygame.quit()


def _make_hero(hero_id="wk126_t7_h1", name="Doran", x=100.0, y=100.0):
    from game.entities.hero import Hero

    return Hero(x, y, hero_class="warrior", hero_id=hero_id, name=name)


class _FakeLair:
    building_type = "goblin_camp"
    is_lair = True

    def __init__(self, cx=800.0, cy=800.0, hp=120):
        self.center_x = cx
        self.center_y = cy
        self.x = cx
        self.y = cy
        self.hp = hp


class _FakePOI:
    building_type = "poi_shrine"
    is_poi = True

    def __init__(self, cx=480.0, cy=480.0):
        self.center_x = cx
        self.center_y = cy
        self.x = cx
        self.y = cy
        self.hp = 100


class _StubWorld:
    def __init__(self, w=60, h=60):
        self.width = w
        self.height = h
        self.visibility = [[Visibility.UNSEEN for _ in range(w)] for _ in range(h)]


def _recording_bus():
    bus = EventBus()
    events: list[dict] = []
    bus.subscribe("*", events.append)
    return bus, events


def _ctx(heroes=(), buildings=(), world=None, bus=None):
    return SystemContext(
        heroes=list(heroes),
        enemies=[],
        buildings=list(buildings),
        world=world,
        economy=EconomySystem(),
        event_bus=bus if bus is not None else EventBus(),
    )


def _completed_events(events):
    return [e for e in events if e["type"] == GameEventType.QUEST_COMPLETED.value]


def _failed_events(events):
    return [e for e in events if e["type"] == GameEventType.QUEST_FAILED.value]


# ---------------------------------------------------------------------------
# raid_lair
# ---------------------------------------------------------------------------

def test_raid_lair_completes_on_lair_cleared_and_pays():
    qs = QuestSystem()
    bus, events = _recording_bus()
    hero = _make_hero()
    lair = _FakeLair()
    other_lair = _FakeLair(cx=1200.0, cy=1200.0)
    quest = qs.create_quest("b1", "raid_lair", lair, 140)
    quest.accept(hero)

    # Clearing a DIFFERENT lair does nothing (identity match, like bounties).
    qs.on_lair_cleared(other_lair, [hero], bus)
    assert quest.completed is False

    qs.on_lair_cleared(lair, [hero], bus)
    bus.flush()

    assert quest.completed is True
    tax = int(140 * TAX_RATE)
    assert hero.gold == 140 - tax and hero.taxed_gold == tax
    done = _completed_events(events)
    assert len(done) == 1 and done[0]["quest_type"] == "raid_lair"
    assert done[0]["hero_id"] == hero.hero_id


# ---------------------------------------------------------------------------
# slay_enemy_type
# ---------------------------------------------------------------------------

def test_slay_counter_n_minus_1_not_done_nth_completes():
    qs = QuestSystem()
    bus, events = _recording_bus()
    hero = _make_hero()
    quest = qs.create_quest("b1", "slay_enemy_type", "goblin", 60, count=3)
    quest.accept(hero)

    qs.on_enemy_killed("goblin", hero, bus)
    qs.on_enemy_killed("goblin", hero, bus)
    bus.flush()
    assert quest.progress == 2
    assert quest.completed is False, "N-1 kills must NOT complete the quest"
    assert _completed_events(events) == []

    qs.on_enemy_killed("goblin", hero, bus)
    bus.flush()
    assert quest.progress == 3
    assert quest.completed is True, "the Nth kill completes"
    assert len(_completed_events(events)) == 1
    tax = int(60 * TAX_RATE)
    assert hero.gold == 60 - tax


def test_slay_counter_ignores_wrong_hero_and_wrong_type():
    qs = QuestSystem()
    bus, _events = _recording_bus()
    hero = _make_hero()
    bystander = _make_hero(hero_id="wk126_t7_h2", name="Bystander")
    quest = qs.create_quest("b1", "slay_enemy_type", "goblin", 60, count=2)
    quest.accept(hero)

    qs.on_enemy_killed("goblin", bystander, bus)   # wrong hero
    qs.on_enemy_killed("skeleton", hero, bus)      # wrong type
    qs.on_enemy_killed("goblin", None, bus)        # no killer resolved
    assert quest.progress == 0 and quest.completed is False


# ---------------------------------------------------------------------------
# find_poi
# ---------------------------------------------------------------------------

def test_find_poi_completes_on_accepting_hero_arrival():
    qs = QuestSystem()
    bus, events = _recording_bus()
    poi = _FakePOI(cx=480.0, cy=480.0)
    hero = _make_hero(x=poi.center_x + 20 * TILE_SIZE, y=poi.center_y)  # far away
    quest = qs.create_quest("b1", "find_poi", poi, 60)
    quest.accept(hero)
    ctx = _ctx(heroes=[hero], buildings=[poi], bus=bus)

    qs.update(ctx, 1 / 60)
    bus.flush()
    assert quest.completed is False, "hero is far from the POI — must not complete"

    hero.x = poi.center_x + TILE_SIZE  # within the 2-tile arrival radius
    hero.y = poi.center_y
    qs.update(ctx, 1 / 60)
    bus.flush()

    assert quest.completed is True
    done = _completed_events(events)
    assert len(done) == 1 and done[0]["quest_type"] == "find_poi"
    assert hero.gold == 60 - int(60 * TAX_RATE)


# ---------------------------------------------------------------------------
# explore_far
# ---------------------------------------------------------------------------

def test_explore_far_completes_when_tiles_seen_and_hero_nearby():
    qs = QuestSystem()
    bus, events = _recording_bus()
    world = _StubWorld()
    target = (40, 40)
    target_px = ((target[0] + 0.5) * TILE_SIZE, (target[1] + 0.5) * TILE_SIZE)
    hero = _make_hero(x=5 * TILE_SIZE, y=5 * TILE_SIZE)  # far from the frontier
    quest = qs.create_quest("b1", "explore_far", target, 140)
    quest.accept(hero)
    ctx = _ctx(heroes=[hero], buildings=[], world=world, bus=bus)

    # Unrevealed -> not complete.
    qs.update(ctx, 1 / 60)
    assert quest.completed is False

    # Reveal the tile + radius, but the hero is still far away -> not complete
    # (the ACCEPTING hero must be the one nearby).
    r = int(QUEST_EXPLORE_REVEAL_RADIUS_TILES)
    for gy in range(target[1] - r, target[1] + r + 1):
        for gx in range(target[0] - r, target[0] + r + 1):
            world.visibility[gy][gx] = Visibility.SEEN
    qs.update(ctx, 1 / 60)
    assert quest.completed is False, "revealed without the accepting hero nearby must not complete"

    # Hero walks to the frontier -> completes.
    hero.x, hero.y = target_px
    qs.update(ctx, 1 / 60)
    bus.flush()
    assert quest.completed is True
    done = _completed_events(events)
    assert len(done) == 1 and done[0]["quest_type"] == "explore_far"
    assert hero.gold == 140 - int(140 * TAX_RATE)


def test_explore_far_partial_reveal_not_done():
    qs = QuestSystem()
    bus, _events = _recording_bus()
    world = _StubWorld()
    target = (30, 30)
    hero = _make_hero(x=(target[0] + 0.5) * TILE_SIZE, y=(target[1] + 0.5) * TILE_SIZE)
    quest = qs.create_quest("b1", "explore_far", target, 60)
    quest.accept(hero)
    # Only the center tile seen — the radius is not fully revealed.
    world.visibility[target[1]][target[0]] = Visibility.SEEN
    qs.update(_ctx(heroes=[hero], world=world, bus=bus), 1 / 60)
    assert quest.completed is False


# ---------------------------------------------------------------------------
# Failure paths (escrow consumed, giver re-armable, QUEST_FAILED)
# ---------------------------------------------------------------------------

def test_target_gone_before_acceptance_fails_and_consumes_escrow():
    qs = QuestSystem()
    bus, events = _recording_bus()
    economy = EconomySystem()
    assert economy.fund_quest(140) is True
    gold_after_escrow = economy.player_gold

    lair = _FakeLair()
    quest = qs.create_quest("b1", "raid_lair", lair, 140)
    assert quest.is_open

    # The lair dies before any hero takes the offer (not in buildings anymore).
    ctx = SystemContext(
        heroes=[], enemies=[], buildings=[], world=None, economy=economy, event_bus=bus
    )
    qs.update(ctx, 1 / 60)
    bus.flush()

    failed = _failed_events(events)
    assert len(failed) == 1 and failed[0]["reason"] == "target_gone"
    assert economy.player_gold == gold_after_escrow, "escrow is CONSUMED on failure (no refund)"
    # Giver re-armable: the failed quest no longer blocks a new offer.
    assert qs.quests == [] and qs.has_open_quest_for("b1") is False


def test_accepting_hero_death_fails_quest():
    qs = QuestSystem()
    bus, events = _recording_bus()
    hero = _make_hero()
    lair = _FakeLair()
    quest = qs.create_quest("b1", "raid_lair", lair, 60)
    quest.accept(hero)

    hero.hp = 0  # is_alive is a property over hp
    qs.update(_ctx(heroes=[hero], buildings=[lair], bus=bus), 1 / 60)
    bus.flush()

    failed = _failed_events(events)
    assert len(failed) == 1 and failed[0]["reason"] == "hero_died"
    assert hero.gold == 0, "no payout on failure"
    assert qs.quests == [], "failed quests are cleaned up (giver re-armable)"


def test_giver_destroyed_fails_open_quest_and_clears_it():
    """WK133 QA fix: post destroyed -> its OPEN offer fails (escrow consumed,
    QUEST_FAILED, dropped from the active set so view.quests stops carrying it)."""
    qs = QuestSystem()
    bus, events = _recording_bus()
    economy = EconomySystem()
    assert economy.fund_quest(140) is True
    gold_after_escrow = economy.player_gold

    lair = _FakeLair()
    quest = qs.create_quest("b_post", "raid_lair", lair, 140)
    assert quest.is_open

    qs.on_giver_destroyed("b_post", bus)
    bus.flush()

    failed = _failed_events(events)
    assert len(failed) == 1 and failed[0]["reason"] == "giver_destroyed"
    assert failed[0]["quest_id"] == quest.quest_id
    assert economy.player_gold == gold_after_escrow, "escrow is CONSUMED (PM decision)"
    assert qs.quests == [], "the zombie open quest must be dropped immediately"
    assert qs.get_active_quests() == [], "view.quests must stop carrying it"


def test_giver_destroyed_accepted_quest_survives_and_completes():
    """WK133 QA fix: an ACCEPTED quest outlives its giver — the hero is already
    on the job and completion pays normally."""
    qs = QuestSystem()
    bus, events = _recording_bus()
    hero = _make_hero()
    lair = _FakeLair()
    quest = qs.create_quest("b_post", "raid_lair", lair, 140)
    quest.accept(hero)

    qs.on_giver_destroyed("b_post", bus)
    bus.flush()

    assert _failed_events(events) == [], "an accepted quest must NOT fail with its giver"
    assert quest in qs.get_active_quests(), "the accepted quest survives"

    qs.on_lair_cleared(lair, [hero], bus)
    bus.flush()
    assert quest.completed is True
    assert len(_completed_events(events)) == 1
    assert hero.gold == 140 - int(140 * TAX_RATE), "completion pays normally"


def test_giver_destroyed_other_givers_quests_untouched():
    qs = QuestSystem()
    bus, events = _recording_bus()
    other = qs.create_quest("b_other", "slay_enemy_type", "goblin", 60, count=2)

    qs.on_giver_destroyed("b_post", bus)
    bus.flush()

    assert _failed_events(events) == []
    assert other.is_open and other in qs.get_active_quests()


def test_engine_destroying_post_with_open_quest_fails_it():
    """Engine wiring: the sim_engine giver-cull hook routes into
    QuestSystem.on_giver_destroyed (QUEST_FAILED + gone from the active set
    that feeds view.quests)."""
    from game.engine import GameEngine
    from game.entities.buildings.base import Building

    engine = GameEngine(headless=True)
    try:
        castle = next(
            b for b in engine.sim.buildings if getattr(b, "building_type", None) == "castle"
        )
        post = Building(int(castle.grid_x) + 6, int(castle.grid_y), "herald_post")
        post.is_constructed = True
        post.construction_started = True
        engine.sim.buildings.append(post)
        engine.update(1 / 60)
        assert len(engine.sim.quest_givers) == 1
        giver_id = engine.sim.quest_givers[0].giver_id

        engine.sim.economy.player_gold = 10_000
        quest = engine.sim.create_quest(giver_id, "explore_far", (40, 40), 100)
        assert quest is not None and quest.is_open

        events: list[dict] = []
        engine.sim.event_bus.subscribe("*", events.append)

        post.hp = 0  # destroyed
        engine.update(1 / 60)

        assert engine.sim.quest_givers == [], "the post's NPC is culled"
        failed = _failed_events(events)
        assert len(failed) == 1 and failed[0]["reason"] == "giver_destroyed"
        assert engine.sim.quest_system.get_active_quests() == [], (
            "no zombie open quest may remain for view.quests"
        )
    finally:
        pygame.quit()


# ---------------------------------------------------------------------------
# WK133 QA gap 1 — idle raider re-pin
# ---------------------------------------------------------------------------

def test_idle_raider_repinned_at_live_lair():
    """An accepted raid_lair hero who comes out of combat IDLE with no target is
    re-pointed at the (still-alive) lair by QuestSystem.update."""
    from game.entities.hero import HeroState

    qs = QuestSystem()
    bus, _events = _recording_bus()
    hero = _make_hero()
    lair = _FakeLair(cx=800.0, cy=800.0)
    quest = qs.create_quest("b1", "raid_lair", lair, 140)
    quest.accept(hero)

    hero.state = HeroState.IDLE
    hero.target = None
    qs.update(_ctx(heroes=[hero], buildings=[lair], bus=bus), 1 / 60)

    assert hero.target is lair, "the idle raider must be re-pinned on the lair"
    assert hero.state == HeroState.MOVING
    assert quest.completed is False and quest.failed is False


def test_busy_raider_never_hijacked_by_repin():
    from game.entities.hero import HeroState

    qs = QuestSystem()
    bus, _events = _recording_bus()
    hero = _make_hero()
    lair = _FakeLair()
    quest = qs.create_quest("b1", "raid_lair", lair, 140)
    quest.accept(hero)

    sentinel = object()
    for busy_state in (HeroState.FIGHTING, HeroState.RESTING, HeroState.SHOPPING):
        hero.state = busy_state
        hero.target = sentinel
        qs.update(_ctx(heroes=[hero], buildings=[lair], bus=bus), 1 / 60)
        assert hero.target is sentinel and hero.state == busy_state, (
            f"re-pin must not hijack a {busy_state.name} hero"
        )
    # IDLE but already carrying a target (e.g. mid-engagement handoff): leave it.
    hero.state = HeroState.IDLE
    hero.target = sentinel
    qs.update(_ctx(heroes=[hero], buildings=[lair], bus=bus), 1 / 60)
    assert hero.target is sentinel and hero.state == HeroState.IDLE
    # IDLE but WOUNDED (< 60% HP): keep the retreat/rest cycle, no re-pin.
    hero.target = None
    hero.hp = int(hero.max_hp * 0.5)
    qs.update(_ctx(heroes=[hero], buildings=[lair], bus=bus), 1 / 60)
    assert hero.target is None and hero.state == HeroState.IDLE, (
        "a wounded idle raider must NOT be thrown back at the lair"
    )


def test_lair_cleared_before_acceptance_fails_open_offer():
    qs = QuestSystem()
    bus, events = _recording_bus()
    lair = _FakeLair()
    qs.create_quest("b1", "raid_lair", lair, 60)

    qs.on_lair_cleared(lair, [], bus)
    bus.flush()

    failed = _failed_events(events)
    assert len(failed) == 1 and failed[0]["reason"] == "target_gone"
    assert _completed_events(events) == []
