"""WK142 Blackbanner duplicate-suppression and cleanup tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.content.bosses import RUSK_BLACKBANNER_BOSS_DEF
from game.content.quest_chains import (
    AVENGE_FALLEN_HERO,
    BLACKBANNER_RESCUE,
    BLACKBANNER_REVENGE,
    BLACKBANNER_TOLL_TAKER_NAME,
    BLACKBANNERS_TOLL,
)
from game.entities.enemy import BanditLord
from game.entities.hero import HeroState
from game.sim.contracts import HeroCaptureState
from game.sim.timebase import set_sim_now_ms
from game.systems.boss_encounter import BossEncounterSystem
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

    class _Bus:
        def emit(self, event: dict) -> None:
            events.append(event)

        def subscribe(self, topic, callback) -> None:
            _ = (topic, callback)

    return _Bus(), events


def _make_context(heroes: list[_Hero], enemies: list[object], fortresses: list[object], castle: object | None, bus) -> SystemContext:
    return SystemContext(
        heroes=heroes,
        enemies=enemies,
        buildings=[] if castle is None else [castle],
        world=None,
        economy=None,
        event_bus=bus,
        pois=fortresses,
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


def test_blackbanner_rescue_offers_deduplicate_and_clean_stale_capture():
    quest_system = QuestChainSystem()
    captive = _Hero(hero_id="wk142_captive", name="Astra", x=160.0, y=160.0)
    rescuer = _Hero(hero_id="wk142_rescuer", name="Bryn", x=64.0, y=64.0)
    fortress = _fortress_target()
    castle = _castle_target()
    bus, events = _recording_bus()
    ctx = _make_context([captive, rescuer], [], [fortress], castle, bus)

    set_sim_now_ms(1000)
    toll_chain = quest_system.offer_blackbanners_toll(ctx=ctx, hero=captive, event_bus=bus, now_ms=1000)
    assert toll_chain.chain_type == BLACKBANNERS_TOLL.chain_type
    assert quest_system.accept_chain(toll_chain.chain_id, hero=captive, event_bus=bus, now_ms=1000) is True

    captor = _BlackbannerKiller()
    first_capture = quest_system.capture_blackbanner_hero(
        captive,
        killer=captor,
        source_chain=toll_chain,
        ctx=ctx,
        event_bus=bus,
        now_ms=1100,
    )
    second_capture = quest_system.capture_blackbanner_hero(
        captive,
        killer=captor,
        source_chain=toll_chain,
        ctx=ctx,
        event_bus=bus,
        now_ms=1110,
    )
    assert second_capture is first_capture
    assert len([chain for chain in quest_system.chains if chain.chain_type == BLACKBANNER_RESCUE.chain_type]) == 1

    rescue_chain = next(chain for chain in quest_system.chains if chain.chain_type == BLACKBANNER_RESCUE.chain_type)
    assert rescue_chain.status == "offered"
    assert quest_system.get_active_rescue_opportunity_snapshots()[0].status == "offered"

    captive.release_capture(rescued_at_ms=1200)
    quest_system._captured_heroes.pop(captive.hero_id, None)
    set_sim_now_ms(1200)
    quest_system.update(ctx, 1 / 60)

    assert rescue_chain.status == "failed"
    assert quest_system.get_active_captured_hero_snapshots() == ()
    assert quest_system.get_active_rescue_opportunity_snapshots() == ()
    assert quest_system.get_active_chain_snapshots() == ()
    assert set(chain.chain_type for chain in quest_system.failed_chains) == {
        BLACKBANNERS_TOLL.chain_type,
        BLACKBANNER_RESCUE.chain_type,
    }
    assert [event["type"] for event in events if event["type"].startswith("quest_chain")]


def test_blackbanner_revenge_offers_deduplicate_and_clean_stale_boss():
    quest_system = QuestChainSystem()
    boss_system = BossEncounterSystem()
    fallen = _Hero(hero_id="wk142_fallen", name="Mira", x=192.0, y=192.0)
    avenger = _Hero(hero_id="wk142_avenger", name="Lyra", x=224.0, y=224.0)
    boss = BanditLord(384.0, 256.0)
    bus, events = _recording_bus()
    ctx = _make_context([fallen, avenger], [boss], [], None, bus)

    set_sim_now_ms(2000)
    boss_system.register_boss(boss, boss_def=RUSK_BLACKBANNER_BOSS_DEF, event_bus=bus, now_ms=2000)
    first_revenge = quest_system.record_blackbanner_revenge(
        boss=boss,
        hero=fallen,
        ctx=ctx,
        event_bus=bus,
        now_ms=2050,
    )
    second_revenge = quest_system.record_blackbanner_revenge(
        boss=boss,
        hero=fallen,
        ctx=ctx,
        event_bus=bus,
        now_ms=2060,
    )
    assert first_revenge is not None
    assert second_revenge is first_revenge
    assert len([chain for chain in quest_system.chains if chain.chain_type == BLACKBANNER_REVENGE.chain_type]) == 1
    assert quest_system.get_active_revenge_opportunity_snapshots()[0].current_phase_id == AVENGE_FALLEN_HERO

    boss.target = avenger
    boss.hp = 0
    set_sim_now_ms(2100)
    boss_system.update(ctx, 1 / 60)
    set_sim_now_ms(2200)
    quest_system.update(ctx, 1 / 60)

    assert first_revenge.status == "failed"
    assert boss_system.get_active_boss_snapshots() == ()
    assert boss_system.get_active_boss_kill_memory_snapshots() == ()
    assert boss_system.get_active_revenge_opportunity_snapshots() == ()
    assert quest_system.get_active_revenge_opportunity_snapshots() == ()
    assert quest_system.get_active_chain_snapshots() == ()
    assert quest_system.failed_chains == [first_revenge]
    assert [event["type"] for event in events if event["type"].startswith("boss")]
