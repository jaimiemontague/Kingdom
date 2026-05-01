"""WK49: bounded profile memory, known-place dedupe, career counters."""

from __future__ import annotations

from game.entities.hero import Hero
from game.sim.hero_profile import HeroMemoryEntry
from game.systems import hero_memory as hm
from game.systems.bounty import Bounty


def test_profile_memory_caps_at_max_entries() -> None:
    hero = Hero(0.0, 0.0, hero_class="warrior", hero_id="mem_cap")
    n = hm.PROFILE_MEMORY_MAX_ENTRIES + 5
    for i in range(n):
        hero.record_profile_memory(
            event_type="test",
            sim_time_ms=1000 + i,
            summary=f"e{i}",
        )
    assert len(hero.profile_memory) == hm.PROFILE_MEMORY_MAX_ENTRIES
    assert hero.profile_memory[0].summary == "e5"
    assert hero.profile_memory[-1].summary == f"e{n - 1}"


def test_known_place_dedupes_and_tracks_visits() -> None:
    hero = Hero(0.0, 0.0, hero_class="warrior", hero_id="places")
    assert hero.profile_career["places_discovered"] == 0
    p1 = hero.remember_known_place(
        place_type="marketplace",
        display_name="Market",
        tile=(2, 3),
        world_pos=(64.0, 96.0),
        sim_time_ms=100,
        building_type="marketplace",
        grid_x=2,
        grid_y=3,
    )
    assert hero.profile_career["places_discovered"] == 1
    assert p1.visits == 1
    assert p1.first_seen_ms == 100
    p2 = hero.remember_known_place(
        place_type="marketplace",
        display_name="Market",
        tile=(2, 3),
        world_pos=(64.0, 96.0),
        sim_time_ms=500,
        building_type="marketplace",
        grid_x=2,
        grid_y=3,
    )
    assert hero.profile_career["places_discovered"] == 1
    assert len(hero.known_places) == 1
    assert p2.visits == 2
    assert p2.first_seen_ms == 100
    assert p2.last_seen_ms == 500
    assert p2.last_visited_ms == 500


def test_known_places_trim_oldest_when_over_cap(monkeypatch) -> None:
    monkeypatch.setattr(hm, "KNOWN_PLACES_MAX_ENTRIES", 2)
    hero = Hero(0.0, 0.0, hero_class="warrior", hero_id="trim")
    hero.remember_known_place(
        place_type="inn",
        display_name="A",
        tile=(0, 0),
        world_pos=(0.0, 0.0),
        sim_time_ms=10,
        building_type="inn",
        grid_x=0,
        grid_y=0,
    )
    hero.remember_known_place(
        place_type="inn",
        display_name="B",
        tile=(1, 0),
        world_pos=(32.0, 0.0),
        sim_time_ms=20,
        building_type="inn",
        grid_x=1,
        grid_y=0,
    )
    hero.remember_known_place(
        place_type="inn",
        display_name="C",
        tile=(2, 0),
        world_pos=(64.0, 0.0),
        sim_time_ms=30,
        building_type="inn",
        grid_x=2,
        grid_y=0,
    )
    assert len(hero.known_places) == 2
    assert "inn:0:0" not in hero.known_places


def test_add_gold_tracks_gross_career_counter() -> None:
    hero = Hero(0.0, 0.0, hero_class="warrior", hero_id="gold")
    hero.add_gold(100)
    assert hero.profile_career["gold_earned"] == 100
    hero.add_gold(0)
    assert hero.profile_career["gold_earned"] == 100


def test_buy_item_increments_purchases_made() -> None:
    hero = Hero(0.0, 0.0, hero_class="warrior", hero_id="shop")
    hero.gold = 50
    hero.buy_item({"name": "Healing Potion", "type": "potion", "price": 20, "effect": 50})
    assert hero.profile_career["purchases_made"] == 1


def test_on_attack_landed_increments_enemies_defeated() -> None:
    hero = Hero(0.0, 0.0, hero_class="warrior", hero_id="atk")
    enemy = type("E", (), {"enemy_type": "goblin"})()
    hero.on_attack_landed(enemy, damage=5, killed=True)
    assert hero.profile_career["enemies_defeated"] == 1
    hero.on_attack_landed(enemy, damage=5, killed=False)
    assert hero.profile_career["enemies_defeated"] == 1


def test_bounty_claim_increments_bounties_claimed() -> None:
    hero = Hero(0.0, 0.0, hero_class="warrior", hero_id="bty")
    b = Bounty(0.0, 0.0, reward=50, bounty_type="explore")
    assert b.claim(hero) is True
    assert hero.profile_career["bounties_claimed"] == 1


def test_record_profile_memory_entry_carries_hero_id() -> None:
    hero = Hero(0.0, 0.0, hero_class="warrior", hero_id="sid")
    e = hero.record_profile_memory(event_type="x", sim_time_ms=1, summary="s")
    assert isinstance(e, HeroMemoryEntry)
    assert e.hero_id == "sid"
