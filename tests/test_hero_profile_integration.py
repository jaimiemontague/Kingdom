"""WK49 Wave 3: profile snapshots from live heroes + FoW discovery hook."""

from __future__ import annotations

import json

from types import SimpleNamespace

import pygame

from config import TILE_SIZE
from game.engine import GameEngine
from game.entities.hero import Hero
from game.sim.hero_profile import (
    build_hero_profile_snapshot,
    discover_known_buildings_after_fog,
    format_location_compact,
)
from game.systems.hero_memory import stable_place_id


def test_build_hero_profile_snapshot_round_trip_json() -> None:
    hero = Hero(10.0, 20.0, hero_class="warrior", hero_id="snap1", name="Bob")
    prof = build_hero_profile_snapshot(hero, None, now_ms=500_000)
    blob = json.dumps(prof.to_dict())
    assert "snap1" in blob
    assert prof.identity.hero_id == "snap1"


def test_format_location_compact_inside_and_outside() -> None:
    hero = Hero(0.0, 0.0, hero_id="loc")
    assert format_location_compact(hero) == "Out"
    inn = SimpleNamespace(building_type=SimpleNamespace(value="inn"))
    hero.is_inside_building = True
    hero.inside_building = inn
    assert format_location_compact(hero) == "In:inn"


def test_fog_discovery_records_place_once_not_spam_memory() -> None:
    hero = Hero(0.0, 0.0, hero_id="fog1")
    assert stable_place_id("marketplace", 5, 5) == "marketplace:5:5"

    b = SimpleNamespace(
        building_type="marketplace",
        grid_x=5,
        grid_y=5,
        size=(1, 1),
        hp=100,
        is_constructed=True,
        is_lair=False,
        is_neutral=False,
        center_x=168.0,
        center_y=168.0,
    )

    discover_known_buildings_after_fog(
        buildings=[b],
        heroes_world_vision=[(hero, 5, 5, 8)],
        newly_revealed={(5, 5)},
        now_ms=1000,
    )
    assert "marketplace:5:5" in hero.known_places
    mem1 = len(hero.profile_memory)
    assert mem1 >= 1
    assert hero.profile_memory[-1].event_type == "discovered_place"

    discover_known_buildings_after_fog(
        buildings=[b],
        heroes_world_vision=[(hero, 5, 5, 8)],
        newly_revealed={(5, 5)},
        now_ms=2000,
    )
    assert len(hero.profile_memory) == mem1


def test_encounter_discovery_when_visible_without_new_reveals_populates_known_places():
    """Castle/neutral FoW sources can expose tiles without UNSEEN→VISIBLE frontier hits."""
    hero = Hero(0.0, 0.0, hero_id="enc_vis")
    b = SimpleNamespace(
        building_type="marketplace",
        grid_x=5,
        grid_y=5,
        size=(1, 1),
        hp=100,
        is_constructed=True,
        is_lair=False,
        is_neutral=False,
        center_x=168.0,
        center_y=168.0,
    )

    visible = {(5, 5)}

    def tile_vis(tx: int, ty: int) -> bool:
        return (int(tx), int(ty)) in visible

    discover_known_buildings_after_fog(
        buildings=[b],
        heroes_world_vision=[(hero, 5, 5, 8)],
        newly_revealed=(),
        now_ms=500,
        tile_currently_visible=tile_vis,
    )
    assert "marketplace:5:5" in hero.known_places
    mem_n = len(hero.profile_memory)
    assert hero.known_places["marketplace:5:5"].visits == 1

    # Second tick: hero still overlaps visible POI — must NOT respam memory nor bump visits endlessly.
    discover_known_buildings_after_fog(
        buildings=[b],
        heroes_world_vision=[(hero, 5, 5, 8)],
        newly_revealed=(),
        now_ms=750,
        tile_currently_visible=tile_vis,
    )
    assert len(hero.profile_memory) == mem_n
    assert hero.known_places["marketplace:5:5"].visits == 1


def test_known_places_stays_quiet_when_not_visible_even_if_in_sphere_without_frontier():
    hero = Hero(0.0, 0.0, hero_id="dark")
    b = SimpleNamespace(
        building_type="inn",
        grid_x=2,
        grid_y=2,
        size=(1, 1),
        hp=80,
        is_constructed=True,
        is_lair=False,
        is_neutral=False,
        center_x=64.0,
        center_y=64.0,
    )

    discover_known_buildings_after_fog(
        buildings=[b],
        heroes_world_vision=[(hero, 2, 2, 4)],
        newly_revealed=(),
        now_ms=111,
        tile_currently_visible=lambda _x, _y: False,
    )
    assert hero.known_places == {}


def test_get_game_state_exposes_profile_maps() -> None:
    engine = GameEngine(headless=True)
    try:
        gs = engine.get_game_state()
        assert "hero_profiles_by_id" in gs
        assert "selected_hero_profile" in gs
        assert isinstance(gs["hero_profiles_by_id"], dict)
        assert gs["selected_hero_profile"] is None
        castle = gs["castle"]
        assert castle is not None
        probe = Hero(
            float(castle.center_x) + float(TILE_SIZE),
            float(castle.center_y),
            hero_id="int_test",
            name="Ada",
        )
        engine.sim.heroes.append(probe)

        gs_mid = engine.get_game_state()
        assert "int_test" in gs_mid["hero_profiles_by_id"]

        engine.selected_hero = probe
        gs2 = engine.get_game_state()
        hid = "int_test"
        assert hid in gs2["hero_profiles_by_id"]
        sp = gs2["selected_hero_profile"]
        assert sp is not None
        assert getattr(sp, "identity", None) is not None
        assert sp.identity.hero_id == hid
    finally:
        pygame.quit()
