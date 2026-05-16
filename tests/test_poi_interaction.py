"""Tests for WK56 POI interaction system handlers."""

from __future__ import annotations

from config import TILE_SIZE
from game.sim.determinism import set_sim_seed
from game.sim.timebase import set_sim_now_ms


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _MockPOIDefinition:
    def __init__(
        self,
        *,
        poi_type="poi_shrine",
        display_name="Test POI",
        building_type="",
        size=(1, 1),
        difficulty_tier=1,
        rarity="common",
        interaction_type="shrine",
        is_persistent=False,
        vision_radius=5,
        description="A test POI.",
        zone_affinity="plains",
        elevation_preference="flat",
    ):
        self.poi_type = poi_type
        self.display_name = display_name
        self.building_type = building_type
        self.size = size
        self.difficulty_tier = difficulty_tier
        self.rarity = rarity
        self.interaction_type = interaction_type
        self.is_persistent = is_persistent
        self.vision_radius = vision_radius
        self.description = description
        self.zone_affinity = zone_affinity
        self.elevation_preference = elevation_preference


class _MockPOI:
    def __init__(
        self,
        *,
        grid_x=10,
        grid_y=10,
        poi_def=None,
        is_discovered=True,
        is_depleted=False,
        is_interacted=False,
        interaction_count=0,
        cooldown_remaining=0.0,
        last_interaction_tick=0,
    ):
        self.grid_x = grid_x
        self.grid_y = grid_y
        self.poi_def = poi_def or _MockPOIDefinition()
        self.is_discovered = is_discovered
        self.is_depleted = is_depleted
        self.is_interacted = is_interacted
        self.interaction_count = interaction_count
        self.cooldown_remaining = cooldown_remaining
        self.last_interaction_tick = last_interaction_tick
        self.is_poi = True


class _MockHero:
    def __init__(
        self,
        *,
        name="Tester",
        hp=100,
        max_hp=100,
        gold=0,
        world_x=10.5 * TILE_SIZE,
        world_y=10.5 * TILE_SIZE,
    ):
        self.name = name
        self.hp = hp
        self.max_hp = max_hp
        self.gold = gold
        self.world_x = world_x
        self.world_y = world_y
        self.x = world_x
        self.y = world_y
        self.is_alive = True
        self.buff_calls: list[dict] = []

    def apply_or_refresh_buff(self, *, name, atk_delta, duration_s, now_ms):
        self.buff_calls.append({
            "name": name,
            "atk_delta": atk_delta,
            "duration_s": duration_s,
            "now_ms": now_ms,
        })


class _MockWorld:
    def __init__(self, *, width=50, height=50):
        self.width = width
        self.height = height
        self.reveal_calls: list[tuple] = []

    def _reveal_circle(self, gx, gy, radius):
        self.reveal_calls.append((gx, gy, radius))


class _MockEventBus:
    def __init__(self):
        self.events: list[dict] = []

    def emit(self, payload):
        self.events.append(dict(payload))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_system():
    """Create a POIInteractionSystem with deterministic seed and sim time."""
    set_sim_seed(42)
    set_sim_now_ms(1000)
    from game.systems.poi_interaction import POIInteractionSystem
    return POIInteractionSystem()


def _place_hero_near_poi(poi, offset_tiles=0.5):
    """Return a hero placed just inside interaction range of the given POI."""
    size = getattr(poi.poi_def, "size", (1, 1))
    cx = (poi.grid_x + size[0] / 2.0) * TILE_SIZE
    cy = (poi.grid_y + size[1] / 2.0) * TILE_SIZE
    return _MockHero(world_x=cx + offset_tiles * TILE_SIZE, world_y=cy)


# ---------------------------------------------------------------------------
# Tests: Shrine
# ---------------------------------------------------------------------------


def test_shrine_heals_to_max():
    system = _make_system()
    poi = _MockPOI(poi_def=_MockPOIDefinition(interaction_type="shrine", difficulty_tier=1))
    hero = _place_hero_near_poi(poi)
    hero.hp = hero.max_hp // 2  # 50% HP

    system.check_interactions(
        [hero], [poi], _MockWorld(), None, _MockEventBus(), dt=0.016,
    )

    assert hero.hp == hero.max_hp


def test_shrine_applies_buff():
    system = _make_system()
    poi = _MockPOI(poi_def=_MockPOIDefinition(interaction_type="shrine", difficulty_tier=1))
    hero = _place_hero_near_poi(poi)

    system.check_interactions(
        [hero], [poi], _MockWorld(), None, _MockEventBus(), dt=0.016,
    )

    assert len(hero.buff_calls) == 1
    call = hero.buff_calls[0]
    assert call["name"] == "poi_shrine"
    assert call["duration_s"] == 90.0
    assert call["atk_delta"] > 0


def test_shrine_buff_scales_with_tier():
    results = {}
    for tier in (1, 3, 5):
        system = _make_system()
        poi = _MockPOI(poi_def=_MockPOIDefinition(interaction_type="shrine", difficulty_tier=tier))
        hero = _place_hero_near_poi(poi)

        system.check_interactions(
            [hero], [poi], _MockWorld(), None, _MockEventBus(), dt=0.016,
        )

        assert len(hero.buff_calls) == 1
        results[tier] = hero.buff_calls[0]["atk_delta"]

    # buff_attack = 2 * max(1, (tier+1)//2) => tier1: 2, tier3: 4, tier5: 6
    assert results[1] == 2
    assert results[3] == 4
    assert results[5] == 6


def test_shrine_sets_cooldown():
    system = _make_system()
    poi = _MockPOI(poi_def=_MockPOIDefinition(interaction_type="shrine", difficulty_tier=1))
    hero = _place_hero_near_poi(poi)

    system.check_interactions(
        [hero], [poi], _MockWorld(), None, _MockEventBus(), dt=0.016,
    )

    assert poi.cooldown_remaining > 0


# ---------------------------------------------------------------------------
# Tests: Loot
# ---------------------------------------------------------------------------


def test_loot_gives_gold():
    system = _make_system()
    poi = _MockPOI(poi_def=_MockPOIDefinition(interaction_type="loot", difficulty_tier=1))
    hero = _place_hero_near_poi(poi)
    initial_gold = hero.gold

    system.check_interactions(
        [hero], [poi], _MockWorld(), None, _MockEventBus(), dt=0.016,
    )

    assert hero.gold > initial_gold


def test_loot_scales_by_tier():
    golds = {}
    for tier in (1, 3, 5):
        system = _make_system()
        poi = _MockPOI(poi_def=_MockPOIDefinition(interaction_type="loot", difficulty_tier=tier))
        hero = _place_hero_near_poi(poi)

        system.check_interactions(
            [hero], [poi], _MockWorld(), None, _MockEventBus(), dt=0.016,
        )

        golds[tier] = hero.gold

    # All tiers give positive gold and higher tiers give more (in expectation).
    assert golds[1] > 0
    assert golds[3] > 0
    assert golds[5] > 0
    # tier 3 min (60) > tier 1 max (50), so tier 3 always >= tier 1
    assert golds[3] >= golds[1]
    assert golds[5] >= golds[3]


def test_loot_depletes_poi():
    system = _make_system()
    poi = _MockPOI(poi_def=_MockPOIDefinition(interaction_type="loot", difficulty_tier=1))
    hero = _place_hero_near_poi(poi)

    system.check_interactions(
        [hero], [poi], _MockWorld(), None, _MockEventBus(), dt=0.016,
    )

    assert poi.is_depleted is True


# ---------------------------------------------------------------------------
# Tests: Combat
# ---------------------------------------------------------------------------


def test_combat_emits_event_with_spawn_info():
    system = _make_system()
    poi = _MockPOI(poi_def=_MockPOIDefinition(
        interaction_type="combat", difficulty_tier=2,
    ))
    hero = _place_hero_near_poi(poi)
    bus = _MockEventBus()

    system.check_interactions(
        [hero], [poi], _MockWorld(), None, bus, dt=0.016,
    )

    combat_events = [e for e in bus.events if e.get("type") == "poi_combat_triggered"]
    assert len(combat_events) == 1
    event = combat_events[0]
    assert event["spawn_count"] >= 2
    assert isinstance(event["enemy_types"], list)
    assert len(event["enemy_types"]) > 0


def test_combat_spawn_count_scales_with_tier():
    system = _make_system()
    poi = _MockPOI(poi_def=_MockPOIDefinition(
        interaction_type="combat", difficulty_tier=4,
    ))
    hero = _place_hero_near_poi(poi)
    bus = _MockEventBus()

    system.check_interactions(
        [hero], [poi], _MockWorld(), None, bus, dt=0.016,
    )

    combat_events = [e for e in bus.events if e.get("type") == "poi_combat_triggered"]
    assert len(combat_events) == 1
    assert combat_events[0]["spawn_count"] >= 4


def test_combat_marks_interacted():
    system = _make_system()
    poi = _MockPOI(poi_def=_MockPOIDefinition(interaction_type="combat", difficulty_tier=1))
    hero = _place_hero_near_poi(poi)

    system.check_interactions(
        [hero], [poi], _MockWorld(), None, _MockEventBus(), dt=0.016,
    )

    assert poi.is_interacted is True


def test_combat_doesnt_retrigger():
    system = _make_system()
    poi = _MockPOI(
        poi_def=_MockPOIDefinition(interaction_type="combat", difficulty_tier=1),
        is_interacted=True,
    )
    hero = _place_hero_near_poi(poi)
    bus = _MockEventBus()

    system.check_interactions(
        [hero], [poi], _MockWorld(), None, bus, dt=0.016,
    )

    combat_events = [e for e in bus.events if e.get("type") == "poi_combat_triggered"]
    assert len(combat_events) == 0


# ---------------------------------------------------------------------------
# Tests: Knowledge
# ---------------------------------------------------------------------------


def test_knowledge_reveals_fog():
    system = _make_system()
    poi = _MockPOI(poi_def=_MockPOIDefinition(interaction_type="knowledge", difficulty_tier=1))
    hero = _place_hero_near_poi(poi)
    world = _MockWorld()

    system.check_interactions(
        [hero], [poi], world, None, _MockEventBus(), dt=0.016,
    )

    assert len(world.reveal_calls) == 1
    gx, gy, radius = world.reveal_calls[0]
    assert gx == poi.grid_x
    assert gy == poi.grid_y
    assert radius == 15


def test_knowledge_discovers_nearby_poi():
    system = _make_system()
    # Knowledge POI at (10, 10)
    knowledge_poi = _MockPOI(
        grid_x=10, grid_y=10,
        poi_def=_MockPOIDefinition(interaction_type="knowledge", difficulty_tier=1),
    )
    # Nearby undiscovered POI within 15 tiles
    nearby_poi = _MockPOI(
        grid_x=15, grid_y=10,
        poi_def=_MockPOIDefinition(
            interaction_type="shrine", display_name="Hidden Shrine",
        ),
        is_discovered=False,
    )
    hero = _place_hero_near_poi(knowledge_poi)

    system.check_interactions(
        [hero], [knowledge_poi, nearby_poi], _MockWorld(), None, _MockEventBus(), dt=0.016,
    )

    assert nearby_poi.is_discovered is True


def test_knowledge_no_cascade_when_no_undiscovered():
    system = _make_system()
    knowledge_poi = _MockPOI(
        grid_x=10, grid_y=10,
        poi_def=_MockPOIDefinition(interaction_type="knowledge", difficulty_tier=1),
    )
    # All other POIs already discovered
    other_poi = _MockPOI(
        grid_x=12, grid_y=10,
        poi_def=_MockPOIDefinition(interaction_type="shrine"),
        is_discovered=True,
    )
    hero = _place_hero_near_poi(knowledge_poi)
    bus = _MockEventBus()

    # Should not crash
    system.check_interactions(
        [hero], [knowledge_poi, other_poi], _MockWorld(), None, bus, dt=0.016,
    )

    # Knowledge interaction still happens
    interaction_events = [
        e for e in bus.events
        if e.get("type") == "poi_interaction" and e.get("interaction_type") == "knowledge"
    ]
    assert len(interaction_events) == 1
    assert interaction_events[0].get("revealed_poi_name") is None


# ---------------------------------------------------------------------------
# Tests: NPC
# ---------------------------------------------------------------------------


def test_npc_includes_narrative():
    system = _make_system()
    poi = _MockPOI(poi_def=_MockPOIDefinition(
        interaction_type="npc",
        description="The old sage speaks of distant lands.",
    ))
    hero = _place_hero_near_poi(poi)
    bus = _MockEventBus()

    system.check_interactions(
        [hero], [poi], _MockWorld(), None, bus, dt=0.016,
    )

    npc_events = [
        e for e in bus.events
        if e.get("type") == "poi_interaction" and e.get("interaction_type") == "npc"
    ]
    assert len(npc_events) == 1
    assert npc_events[0]["narrative"] == "The old sage speaks of distant lands."


# ---------------------------------------------------------------------------
# Tests: Dungeon
# ---------------------------------------------------------------------------


def test_dungeon_includes_narrative():
    system = _make_system()
    poi = _MockPOI(poi_def=_MockPOIDefinition(interaction_type="dungeon", difficulty_tier=1))
    hero = _place_hero_near_poi(poi)
    bus = _MockEventBus()

    system.check_interactions(
        [hero], [poi], _MockWorld(), None, bus, dt=0.016,
    )

    dungeon_events = [
        e for e in bus.events
        if e.get("type") == "poi_interaction" and e.get("interaction_type") == "dungeon"
    ]
    assert len(dungeon_events) == 1
    narrative = dungeon_events[0]["narrative"]
    assert "entrance" in narrative.lower()
    assert len(narrative) > 10


# ---------------------------------------------------------------------------
# Tests: Standard event fields
# ---------------------------------------------------------------------------


def test_all_events_have_standard_fields():
    """Every handler emits events containing hero_name, poi_name, and interaction_type."""
    interaction_types = ["shrine", "loot", "combat", "knowledge", "npc", "dungeon"]
    for itype in interaction_types:
        system = _make_system()
        poi = _MockPOI(poi_def=_MockPOIDefinition(
            interaction_type=itype, difficulty_tier=2,
            display_name=f"POI_{itype}",
        ))
        hero = _place_hero_near_poi(poi)
        hero.name = "StandardFieldHero"
        bus = _MockEventBus()

        system.check_interactions(
            [hero], [poi], _MockWorld(), None, bus, dt=0.016,
        )

        # At least one event must have been emitted
        assert len(bus.events) > 0, f"No events emitted for interaction_type={itype}"
        # Check the first event with interaction_type set
        typed_events = [e for e in bus.events if "interaction_type" in e]
        assert len(typed_events) > 0, f"No event with interaction_type for {itype}"
        event = typed_events[0]
        assert event["hero_name"] == "StandardFieldHero", f"hero_name missing for {itype}"
        assert event["poi_name"] == f"POI_{itype}", f"poi_name missing for {itype}"
        assert event["interaction_type"] == itype, f"interaction_type wrong for {itype}"


# ---------------------------------------------------------------------------
# Tests: Filtering in check_interactions
# ---------------------------------------------------------------------------


def test_depleted_poi_skipped():
    system = _make_system()
    poi = _MockPOI(
        poi_def=_MockPOIDefinition(interaction_type="loot", difficulty_tier=1),
        is_depleted=True,
    )
    hero = _place_hero_near_poi(poi)
    bus = _MockEventBus()

    system.check_interactions(
        [hero], [poi], _MockWorld(), None, bus, dt=0.016,
    )

    assert len(bus.events) == 0
    # Gold should not change
    assert hero.gold == 0


def test_undiscovered_poi_skipped():
    system = _make_system()
    poi = _MockPOI(
        poi_def=_MockPOIDefinition(interaction_type="shrine", difficulty_tier=1),
        is_discovered=False,
    )
    hero = _place_hero_near_poi(poi)
    bus = _MockEventBus()

    system.check_interactions(
        [hero], [poi], _MockWorld(), None, bus, dt=0.016,
    )

    assert len(bus.events) == 0
    # HP should remain unchanged (hero starts at max)
    assert hero.hp == hero.max_hp
