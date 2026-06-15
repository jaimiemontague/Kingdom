"""WK142 Blackbanner rescue gameplay tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.content.quest_chains import (
    BLACKBANNER_RESCUE,
    BLACKBANNER_TOLL_TAKER_NAME,
    BLACKBANNERS_TOLL,
    REACH_FORTRESS,
)
from game.entities.hero import HeroState
from game.sim.contracts import HeroCaptureState
from game.sim.timebase import set_sim_now_ms
from game.systems.protocol import SystemContext
from game.systems.quest_chain import QuestChainSystem


@pytest.fixture(autouse=True)
def _sim_time_reset():
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(0)


class _Hero:
    def __init__(self, *, hero_id: str, name: str, x: float = 0.0, y: float = 0.0):
        self.hero_id = hero_id
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.gold = 0
        self.hp = 100
        self.max_hp = 100
        self.is_alive = True
        self.state = HeroState.IDLE
        self.can_attack = True
        self.attack_blocked_reason = ""
        self.is_captured = False
        self.capture_state: HeroCaptureState | None = None

    def distance_to(self, x: float, y: float) -> float:
        dx = self.x - float(x)
        dy = self.y - float(y)
        return (dx * dx + dy * dy) ** 0.5

    def add_gold(self, amount: int) -> None:
        self.gold += int(amount)

    def begin_capture(
        self,
        *,
        captor_boss_id: str = "",
        captor_boss_name: str = "",
        captor_boss_type: str = "",
        location_id: str = "",
        location_name: str = "",
        source_chain_id: str = "",
        source_chain_type: str = "",
        captured_at_ms: int | None = None,
    ) -> HeroCaptureState:
        capture = HeroCaptureState(
            hero_id=str(self.hero_id),
            hero_name=str(self.name),
            captor_boss_id=str(captor_boss_id or ""),
            captor_boss_name=str(captor_boss_name or ""),
            captor_boss_type=str(captor_boss_type or ""),
            location_id=str(location_id or ""),
            location_name=str(location_name or ""),
            source_chain_id=str(source_chain_id or ""),
            source_chain_type=str(source_chain_type or ""),
            captured_at_ms=int(captured_at_ms or 0),
            status="captured",
        )
        self.capture_state = capture
        self.is_captured = True
        self.state = HeroState.CAPTURED
        self.can_attack = False
        self.attack_blocked_reason = "captured"
        return capture

    def release_capture(self, *, rescued_at_ms: int | None = None) -> HeroCaptureState | None:
        _ = rescued_at_ms
        capture = self.capture_state
        self.capture_state = None
        self.is_captured = False
        self.state = HeroState.IDLE
        self.can_attack = True
        self.attack_blocked_reason = ""
        return capture


class _BlackbannerKiller:
    entity_id = "enemy_blackbanner_toll_taker"
    name = BLACKBANNER_TOLL_TAKER_NAME
    enemy_type = "bandit"
    elite_story_name = BLACKBANNER_TOLL_TAKER_NAME


def _recording_bus():
    events: list[dict] = []
    subscriptions: list[tuple[object, object]] = []

    class _Bus:
        def emit(self, event: dict) -> None:
            events.append(event)

        def subscribe(self, topic, callback) -> None:
            subscriptions.append((topic, callback))

    return _Bus(), events, subscriptions


def _make_context(captive: _Hero, rescuer: _Hero, fortress: object, castle: object, bus) -> SystemContext:
    return SystemContext(
        heroes=[captive, rescuer],
        enemies=[],
        buildings=[castle],
        world=None,
        economy=None,
        event_bus=bus,
        pois=[fortress],
        castle=castle,
    )


def _fortress_target() -> SimpleNamespace:
    return SimpleNamespace(
        entity_id="poi_bandit_fortress",
        poi_type="poi_bandit_fortress",
        building_type="poi_bandit_fortress",
        poi_def=SimpleNamespace(display_name="Bandit Fortress"),
        x=384.0,
        y=224.0,
        center_x=384.0,
        center_y=224.0,
    )


def _castle_target() -> SimpleNamespace:
    return SimpleNamespace(
        entity_id="castle",
        building_type="castle",
        name="Castle",
        x=512.0,
        y=320.0,
        center_x=512.0,
        center_y=320.0,
    )


def test_blackbanner_capture_rescue_loop_releases_the_captive_at_the_fortress():
    system = QuestChainSystem()
    captive = _Hero(hero_id="wk142_captive", name="Astra", x=160.0, y=160.0)
    rescuer = _Hero(hero_id="wk142_rescuer", name="Bryn", x=64.0, y=64.0)
    fortress = _fortress_target()
    castle = _castle_target()
    bus, events, subscriptions = _recording_bus()
    ctx = _make_context(captive, rescuer, fortress, castle, bus)

    set_sim_now_ms(1000)
    toll_chain = system.offer_blackbanners_toll(ctx=ctx, hero=captive, event_bus=bus, now_ms=1000)
    assert toll_chain.chain_type == BLACKBANNERS_TOLL.chain_type
    assert toll_chain.status == "offered"

    accepted = system.accept_chain(toll_chain.chain_id, hero=captive, event_bus=bus, now_ms=1000)
    assert accepted is True
    assert toll_chain.status == "active"

    captor = _BlackbannerKiller()
    set_sim_now_ms(1100)
    capture_state = system.capture_blackbanner_hero(
        captive,
        killer=captor,
        source_chain=toll_chain,
        ctx=ctx,
        event_bus=bus,
        now_ms=1100,
    )
    assert capture_state is not None
    assert captive.is_captured is True
    assert captive.capture_state is capture_state
    assert toll_chain.status == "failed"
    assert [chain.chain_type for chain in system.failed_chains] == [BLACKBANNERS_TOLL.chain_type]
    assert len([chain for chain in system.chains if chain.chain_type == BLACKBANNER_RESCUE.chain_type]) == 1

    rescue_chain = next(chain for chain in system.chains if chain.chain_type == BLACKBANNER_RESCUE.chain_type)
    rescue_snapshot = system.get_active_rescue_opportunity_snapshots()
    assert len(rescue_snapshot) == 1
    assert rescue_snapshot[0].captured_hero_id == captive.hero_id
    assert rescue_snapshot[0].current_phase_id == REACH_FORTRESS
    assert rescue_snapshot[0].status == "offered"

    set_sim_now_ms(1150)
    duplicate_capture = system.capture_blackbanner_hero(
        captive,
        killer=captor,
        source_chain=toll_chain,
        ctx=ctx,
        event_bus=bus,
        now_ms=1150,
    )
    assert duplicate_capture is capture_state
    assert len([chain for chain in system.chains if chain.chain_type == BLACKBANNER_RESCUE.chain_type]) == 1

    accepted_rescue = system.accept_chain(rescue_chain.chain_id, ctx=ctx, hero=rescuer, event_bus=bus, now_ms=1200)
    assert accepted_rescue is True
    assert rescue_chain.status == "active"
    assert rescue_chain.current_phase_id == REACH_FORTRESS

    rescuer.x = fortress.center_x
    rescuer.y = fortress.center_y
    set_sim_now_ms(1300)
    system.update(ctx, 1 / 60)

    assert rescue_chain.status == "completed"
    assert rescue_chain.completed_at_ms == 1300
    assert rescuer.gold == BLACKBANNER_RESCUE.reward_profile.gold
    assert captive.is_captured is False
    assert captive.capture_state is None
    assert captive.state == HeroState.IDLE
    assert system.get_active_captured_hero_snapshots() == ()
    assert system.get_active_rescue_opportunity_snapshots() == ()
    assert system.get_active_chain_snapshots() == ()
    assert system.completed_chains == [rescue_chain]
    assert system.failed_chains[0] is toll_chain
    assert [event["type"] for event in events if event["type"].startswith("quest_chain")]  # smoke check
    assert subscriptions  # toll hook wiring was engaged
