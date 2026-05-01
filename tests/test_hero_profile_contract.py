"""Contract tests for ``game.sim.hero_profile`` (WK49 profile read model)."""

from __future__ import annotations

import json

from game.sim.hero_profile import (
    HeroCareerSnapshot,
    HeroIdentitySnapshot,
    HeroInventorySnapshot,
    HeroMemoryEntry,
    HeroNarrativeSeedSnapshot,
    HeroProfileSnapshot,
    HeroProgressionSnapshot,
    HeroVitalsSnapshot,
    KnownPlaceSnapshot,
    format_target_label,
    safe_percent,
    sort_known_places,
    sort_memory_entries,
)


def _minimal_profile(**kwargs) -> HeroProfileSnapshot:
    identity = HeroIdentitySnapshot(
        hero_id="h1",
        name="A",
        hero_class="warrior",
        personality="bold",
        level=2,
    )
    progression = HeroProgressionSnapshot(xp=10, xp_to_level=100, xp_percent=0.1)
    vitals = HeroVitalsSnapshot(
        hp=50,
        max_hp=100,
        health_percent=0.5,
        attack=5,
        defense=3,
        speed=1.0,
    )
    inventory = HeroInventorySnapshot(
        gold=20,
        taxed_gold=2,
        potions=1,
        max_potions=3,
        weapon_name="sword",
        weapon_attack=4,
        armor_name="leather",
        armor_defense=2,
    )
    base = dict(
        identity=identity,
        progression=progression,
        vitals=vitals,
        inventory=inventory,
        career=HeroCareerSnapshot(),
        narrative=HeroNarrativeSeedSnapshot(),
        current_state="IDLE",
        current_intent="idle",
        current_location="Outdoors",
        current_target="none",
    )
    base.update(kwargs)
    return HeroProfileSnapshot(**base)


def test_safe_percent_bounds():
    assert safe_percent(25, 100) == 0.25
    assert safe_percent(0, 0) == 0.0
    assert safe_percent(200, 100) == 1.0


def test_sort_known_places_and_memory_ordering():
    p2 = KnownPlaceSnapshot(
        place_id="b",
        place_type="inn",
        display_name="Inn",
        tile=(1, 2),
        world_pos=(10.0, 20.0),
        first_seen_ms=200,
        last_seen_ms=200,
    )
    p1 = KnownPlaceSnapshot(
        place_id="a",
        place_type="shop",
        display_name="Shop",
        tile=(3, 4),
        world_pos=(30.0, 40.0),
        first_seen_ms=200,
        last_seen_ms=250,
    )
    p0 = KnownPlaceSnapshot(
        place_id="z",
        place_type="lair",
        display_name="Lair",
        tile=(0, 0),
        world_pos=(0.0, 0.0),
        first_seen_ms=100,
        last_seen_ms=100,
    )
    ordered = sort_known_places((p2, p0, p1))
    assert [x.place_id for x in ordered] == ["z", "a", "b"]

    m2 = HeroMemoryEntry(entry_id=2, hero_id="h1", event_type="x", sim_time_ms=50, summary="b")
    m1 = HeroMemoryEntry(entry_id=1, hero_id="h1", event_type="x", sim_time_ms=100, summary="a")
    m0 = HeroMemoryEntry(entry_id=3, hero_id="h1", event_type="x", sim_time_ms=100, summary="c")
    mem = sort_memory_entries((m2, m0, m1))
    assert [(e.sim_time_ms, e.entry_id) for e in mem] == [(50, 2), (100, 1), (100, 3)]


def test_format_target_label_dict_and_enemy():
    class _E:
        enemy_type = "skeleton"
        is_alive = True

    assert format_target_label(_E()) == "enemy:skeleton"
    assert format_target_label(type("T", (), {"target": {"type": "bounty", "bounty_id": 7, "bounty_type": "explore"}})()) == "bounty:explore:7"
    assert format_target_label(type("T", (), {"target": None})()) == "none"


def test_to_dict_json_serializable_and_tuple_order():
    mem = (
        HeroMemoryEntry(entry_id=1, hero_id="h1", event_type="discovered_place", sim_time_ms=10, summary="saw inn"),
    )
    places = (
        KnownPlaceSnapshot(
            place_id="inn:1:2",
            place_type="inn",
            display_name="Inn",
            tile=(1, 2),
            world_pos=(1.0, 2.0),
            first_seen_ms=10,
            last_seen_ms=10,
        ),
    )
    snap = _minimal_profile(
        known_places=places,
        recent_memory=mem,
        last_decision={"action": "idle", "reason": "test", "at_ms": 0, "context": {}},
    )
    d = snap.to_dict()
    json.dumps(d)
    assert list(d["known_places"][0].keys())[:3] == ["place_id", "place_type", "display_name"]
    assert d["recent_memory"][0]["hero_id"] == "h1"
    assert tuple(d["recent_memory"][0]["tags"]) == ()
    assert [p["place_id"] for p in d["known_places"]] == ["inn:1:2"]


def test_optional_defaults_stable():
    snap = _minimal_profile()
    assert snap.known_places == ()
    assert snap.recent_memory == ()
    assert snap.last_decision is None
    assert snap.to_dict()["last_decision"] is None
