from __future__ import annotations

from game.entities.buildings.base import Building
from game.entities.hero import Hero
from game.events import EventBus, GameEventType
from game.ui.pin_alert_watcher import (
    LOW_HEALTH_COOLDOWN_MS,
    PinAlertWatcher,
)
from game.ui.pin_slot import PinSlot


def test_hero_level_up_emits_and_payloads_have_hero_id() -> None:
    bus = EventBus()
    received: list[dict] = []
    bus.subscribe(GameEventType.HERO_LEVEL_UP, received.append)
    h = Hero(0.0, 0.0, hero_class="warrior", hero_id="test_h1", name="TestHero")
    h.set_event_bus(bus)
    h.level_up()
    bus.flush()
    assert len(received) == 1
    assert received[0]["hero_id"] == "test_h1"
    assert received[0]["new_level"] == 2
    assert received[0]["hero_name"] == "TestHero"


def test_hero_level_up_no_bus_does_not_raise() -> None:
    h = Hero(0.0, 0.0, hero_class="warrior", hero_id="safe")
    h.level_up()


def test_hero_entered_building_payload_has_hero_id() -> None:
    bus = EventBus()
    captured: list[dict] = []
    bus.subscribe(GameEventType.HERO_ENTERED_BUILDING, captured.append)
    inn = Building(0, 0, "inn")
    inn.set_event_bus(bus)
    hero = Hero(10.0, 10.0, hero_id="b1", name="Bria")
    inn.on_hero_enter(hero)
    bus.flush()
    assert len(captured) == 1
    assert captured[0]["hero_id"] == "b1"
    assert captured[0]["hero"] is hero


def test_pin_alert_watcher_matches_by_hero_id() -> None:
    pin = PinSlot()
    pin.pin("p1", 100)
    pin.pinned_name = "Aldric"
    messages: list[str] = []

    def add_msg(text: str, color: tuple[int, int, int]) -> None:
        messages.append(text)

    w = PinAlertWatcher(pin, add_msg)
    assert w._matches({"hero_id": "p1"})
    assert not w._matches({"hero_id": "other"})
    h = Hero(0.0, 0.0, hero_id="p1")
    assert w._matches({"hero": h})


def test_pin_alert_watcher_matches_by_name_fallback() -> None:
    pin = PinSlot()
    pin.pin("p1", 100)
    pin.pinned_name = "Lyra"
    w = PinAlertWatcher(pin, lambda t, c: None)
    assert w._matches({"hero": "Lyra"})
    assert not w._matches({"hero": "SomeoneElse"})


def test_low_health_cooldown_respects_30s_window() -> None:
    pin = PinSlot()
    pin.pin("h1", 0)
    pin.pinned_name = "X"

    class FakeVitals:
        health_percent = 0.10

    class FakeProf:
        vitals = FakeVitals()

    messages: list[str] = []

    def add_msg(text: str, color: tuple[int, int, int]) -> None:
        messages.append(text)

    w = PinAlertWatcher(pin, add_msg)
    profiles = {"h1": FakeProf()}
    w.check_low_health(profiles, now_ms=1000)
    w.check_low_health(profiles, now_ms=5000)
    assert len(messages) == 1
    w.check_low_health(profiles, now_ms=1000 + LOW_HEALTH_COOLDOWN_MS + 500)
    assert len(messages) == 2


def test_pin_slot_has_low_health_and_pinned_name_fields() -> None:
    p = PinSlot()
    assert hasattr(p, "low_health_alerted_ms")
    assert hasattr(p, "pinned_name")
    assert p.low_health_alerted_ms == 0
    assert p.pinned_name == ""
