"""WK132: POIs round-out — 5 new POI types, handlers, placement, rock_density.

Covers:
- Definitions/registry sanity (ids, building_type, size/tier/rarity, prefab
  path STRINGS — prefab JSONs land in parallel via Agent 15, so existence is
  NOT asserted here).
- Zone palette / placement wiring (well everywhere, outpost mountains+canyon,
  windmill frontier, ruins outer zones, dragon cave mountains + unique).
- Handlers: well (all 4 outcomes reachable across seeds, one-time depletion),
  outpost (combat then permanent vision), windmill (one-time knowledge),
  ruins (reveal + cascade + loot), dragon cave (dragon boss, rare+ drop).
- rock_density consumed by worldgen (2.0 zone > 0.5 zone for same seed).
- Digest safety: no RNG drawn when no interaction happens.
"""

from __future__ import annotations

import random

from config import TILE_SIZE
from game.entities.poi import POI_DEFINITIONS, PointOfInterest
from game.sim.determinism import get_rng, set_sim_seed
from game.sim.timebase import set_sim_now_ms
from game.systems import loot as loot_mod
from game.systems.loot import LootSystem
from game.systems.poi_placement import _LEGENDARY_UNIQUE_TYPES, POIPlacementSystem
from game.world_zones import ZONES


NEW_IDS = (
    "mysterious_well",
    "ruined_outpost",
    "windmill_ruin",
    "ancient_ruins",
    "dragon_cave",
)


# ---------------------------------------------------------------------------
# Stubs (mirroring tests/test_poi_interaction.py)
# ---------------------------------------------------------------------------


class _MockHero:
    def __init__(self, *, name="Tester", world_x=0.0, world_y=0.0):
        self.name = name
        self.hp = 100
        self.max_hp = 100
        self.gold = 0
        self.world_x = world_x
        self.world_y = world_y
        self.x = world_x
        self.y = world_y
        self.is_alive = True
        self.received_items = []

    def receive_item(self, item):
        self.received_items.append(item)
        return "stored"


class _MockWorld:
    def __init__(self):
        self.width = 250
        self.height = 250
        self.reveal_calls: list[tuple] = []

    def _reveal_circle(self, gx, gy, radius):
        self.reveal_calls.append((gx, gy, radius))


class _MockEventBus:
    def __init__(self):
        self.events: list[dict] = []

    def emit(self, payload):
        self.events.append(dict(payload))


def _make_system(seed=42):
    set_sim_seed(seed)
    set_sim_now_ms(1000)
    from game.systems.poi_interaction import POIInteractionSystem
    return POIInteractionSystem()


def _make_poi(def_id: str, grid_x=50, grid_y=50, discovered=True) -> PointOfInterest:
    poi = PointOfInterest(grid_x, grid_y, POI_DEFINITIONS[def_id])
    poi.is_discovered = discovered
    return poi


def _hero_at_poi(poi) -> _MockHero:
    size = poi.poi_def.size
    cx = (poi.grid_x + size[0] / 2.0) * TILE_SIZE
    cy = (poi.grid_y + size[1] / 2.0) * TILE_SIZE
    return _MockHero(world_x=cx, world_y=cy)


def _tick(system, heroes, pois, world=None, bus=None, dt=0.016):
    world = world or _MockWorld()
    bus = bus or _MockEventBus()
    system.check_interactions(heroes, pois, world, None, bus, dt)
    return world, bus


# ---------------------------------------------------------------------------
# 1. Definitions / registry sanity
# ---------------------------------------------------------------------------


def test_new_definitions_registered_with_exact_contract():
    expected = {
        # id: (size, tier, rarity, interaction_type)
        "mysterious_well": ((1, 1), 2, "uncommon", "well"),
        "ruined_outpost": ((3, 3), 3, "uncommon", "outpost"),
        "windmill_ruin": ((2, 2), 1, "rare", "windmill"),
        "ancient_ruins": ((5, 5), 3, "rare", "ruins"),
        "dragon_cave": ((3, 3), 5, "legendary", "boss"),
    }
    for short_id, (size, tier, rarity, itype) in expected.items():
        key = f"poi_{short_id}"
        assert key in POI_DEFINITIONS, key
        d = POI_DEFINITIONS[key]
        assert d.poi_type == key
        assert d.building_type == key  # prefab contract: building_type "poi_<id>"
        assert d.size == size, key
        assert d.difficulty_tier == tier, key
        assert d.rarity == rarity, key
        assert d.interaction_type == itype, key
        # Prefab path contract (Agent 15 authors the JSON in parallel — assert
        # the path STRING the renderer fallback will use, not file existence).
        assert f"assets/prefabs/buildings/{d.building_type}_v1.json" == (
            f"assets/prefabs/buildings/poi_{short_id}_v1.json"
        )


def test_definition_count_is_17():
    assert len(POI_DEFINITIONS) == 17


def test_new_handlers_registered():
    from game.systems.poi_interaction import _HANDLERS
    for itype in ("well", "outpost", "windmill", "ruins", "boss"):
        assert itype in _HANDLERS, itype


# ---------------------------------------------------------------------------
# 2. Placement / palette wiring
# ---------------------------------------------------------------------------


def test_zone_palette_wiring():
    palettes = {z.zone_id: z.poi_palette for z in ZONES}
    # Well: all zones (+ frontier).
    for zid in ("castle_town", "darkwood", "mountains", "canyon_land"):
        assert "poi_mysterious_well" in palettes[zid], zid
    assert "poi_mysterious_well" in POIPlacementSystem._FRONTIER_PALETTE
    # Outpost: mountains + canyon only.
    assert "poi_ruined_outpost" in palettes["mountains"]
    assert "poi_ruined_outpost" in palettes["canyon_land"]
    assert "poi_ruined_outpost" not in palettes["castle_town"]
    assert "poi_ruined_outpost" not in palettes["darkwood"]
    # Windmill: frontier ring only.
    assert "poi_windmill_ruin" in POIPlacementSystem._FRONTIER_PALETTE
    for zid in palettes:
        assert "poi_windmill_ruin" not in palettes[zid], zid
    # Ruins: any outer zone, not castle town.
    for zid in ("darkwood", "mountains", "canyon_land"):
        assert "poi_ancient_ruins" in palettes[zid], zid
    assert "poi_ancient_ruins" not in palettes["castle_town"]
    # Dragon cave: highest-tier zone (mountains), unique per map.
    assert "poi_dragon_cave" in palettes["mountains"]
    assert "poi_dragon_cave" not in palettes["castle_town"]
    assert "poi_dragon_cave" not in palettes["darkwood"]
    assert "poi_dragon_cave" in _LEGENDARY_UNIQUE_TYPES
    # All palette entries resolve to real definitions.
    for zid, pal in palettes.items():
        for pt in pal:
            assert pt in POI_DEFINITIONS, f"{zid}: {pt}"
    for pt in POIPlacementSystem._FRONTIER_PALETTE:
        assert pt in POI_DEFINITIONS, pt


class _OpenWorld:
    """Everything walkable/buildable; no elevation — placement smoke world."""

    def is_walkable(self, x, y):
        return True

    def is_buildable(self, x, y):
        return True


def test_placement_smoke_each_new_type_placeable_and_dragon_unique():
    set_sim_seed(7)
    placed_types_all_seeds: set[str] = set()
    for seed in range(1, 13):
        rng = random.Random(seed)
        pois = POIPlacementSystem().generate_pois(_OpenWorld(), [], [], rng)
        assert pois, "no POIs placed"
        type_counts: dict[str, int] = {}
        for p in pois:
            type_counts[p.poi_def.poi_type] = type_counts.get(p.poi_def.poi_type, 0) + 1
            assert p.poi_def.poi_type in POI_DEFINITIONS
        assert type_counts.get("poi_dragon_cave", 0) <= 1, "dragon cave must be unique"
        # Budget stays modest: previous cap was ~ 3 + 8*3 + 8 = 35; allow +6.
        assert len(pois) <= 41, len(pois)
        placed_types_all_seeds.update(type_counts)
    # Every new type actually places on at least one seed.
    for short_id in NEW_IDS:
        assert f"poi_{short_id}" in placed_types_all_seeds, short_id


# ---------------------------------------------------------------------------
# 3. Mysterious Well
# ---------------------------------------------------------------------------


def test_well_all_four_outcomes_reachable_across_seeds():
    seen: dict[str, int] = {}
    for seed in range(1, 120):
        system = _make_system(seed)
        poi = _make_poi("poi_mysterious_well")
        # An undiscovered POI elsewhere so the reveal outcome has a target.
        hidden = _make_poi("poi_shrine", grid_x=120, grid_y=120, discovered=False)
        hero = _hero_at_poi(poi)
        _, bus = _tick(system, [hero], [poi, hidden])
        well_events = [e for e in bus.events if e.get("interaction_type") == "well"
                       and e.get("type") == "poi_interaction"]
        assert len(well_events) == 1, seed
        ev = well_events[0]
        outcome = ev["outcome"]
        seen[outcome] = seen.get(outcome, 0) + 1
        if outcome == "gold":
            assert ev["gold"] > 0 and hero.gold == ev["gold"]
        elif outcome == "item":
            # roll_poi_drop may miss -> consolation gold instead of an item.
            assert hero.received_items or hero.gold > 0
        elif outcome == "monsters":
            spawns = [e for e in bus.events if e.get("type") == "poi_combat_triggered"]
            assert len(spawns) == 1
            assert 1 <= spawns[0]["spawn_count"] <= 2
        elif outcome == "reveal":
            assert hidden.is_discovered is True
            assert ev["revealed_poi_name"] == "Shrine / Altar"
        else:
            raise AssertionError(f"unknown outcome {outcome}")
        # One-time: depleted immediately.
        assert poi.is_depleted is True and poi.is_interacted is True
    assert set(seen) == {"gold", "item", "monsters", "reveal"}, seen


def test_well_is_one_time():
    system = _make_system(3)
    poi = _make_poi("poi_mysterious_well")
    hero = _hero_at_poi(poi)
    _, bus1 = _tick(system, [hero], [poi])
    assert poi.is_depleted is True
    # Depleted POIs are filtered out — second pass emits nothing.
    _, bus2 = _tick(system, [hero], [poi])
    assert bus2.events == []


# ---------------------------------------------------------------------------
# 4. Ruined Outpost
# ---------------------------------------------------------------------------


def test_outpost_combat_then_permanent_vision():
    system = _make_system(5)
    poi = _make_poi("poi_ruined_outpost")
    hero = _hero_at_poi(poi)

    # Phase 1: triggers a tier-3 combat encounter via poi_combat_triggered.
    _, bus = _tick(system, [hero], [poi])
    spawns = [e for e in bus.events if e.get("type") == "poi_combat_triggered"]
    assert len(spawns) == 1
    assert spawns[0]["spawn_count"] == 3  # tier 3
    assert spawns[0]["enemy_types"] == ["skeleton", "goblin"]
    assert spawns[0]["interaction_type"] == "outpost"
    assert poi.is_interacted is True
    assert poi.grants_vision is False

    # Expire the retry cooldown, then claim (no sim engine -> area is clear).
    system.tick_cooldowns([poi], dt=60.0)
    _, bus2 = _tick(system, [hero], [poi])
    cleared = [e for e in bus2.events if e.get("interaction_type") == "outpost"
               and e.get("cleared")]
    assert len(cleared) == 1
    assert cleared[0]["vision_radius"] == 5
    assert poi.grants_vision is True
    assert poi.poi_def.vision_radius == 5

    # Permanent: nothing further happens.
    system.tick_cooldowns([poi], dt=601.0)
    _, bus3 = _tick(system, [hero], [poi])
    assert bus3.events == []


def test_outpost_not_cleared_while_enemies_alive_nearby():
    from types import SimpleNamespace

    system = _make_system(6)
    poi = _make_poi("poi_ruined_outpost")
    hero = _hero_at_poi(poi)
    cx = (poi.grid_x + 1.5) * TILE_SIZE
    cy = (poi.grid_y + 1.5) * TILE_SIZE
    enemy = SimpleNamespace(x=cx + TILE_SIZE, y=cy, is_alive=True)
    system._sim_engine = SimpleNamespace(enemies=[enemy])

    _tick(system, [hero], [poi])  # phase 1: combat
    system.tick_cooldowns([poi], dt=60.0)
    _, bus = _tick(system, [hero], [poi])  # phase 2 attempt: blocked
    assert poi.grants_vision is False
    assert all(not e.get("cleared") for e in bus.events)

    # Kill the enemy -> claim succeeds.
    enemy.is_alive = False
    system.tick_cooldowns([poi], dt=60.0)
    _, bus2 = _tick(system, [hero], [poi])
    assert poi.grants_vision is True


def test_cleared_outpost_is_fog_revealer():
    """The fog service treats a cleared outpost like building vision."""
    from types import SimpleNamespace
    from game.sim.fog import update_fog_of_war

    poi = _make_poi("poi_ruined_outpost", grid_x=40, grid_y=40)

    captured: list = []

    class _FogWorld:
        fog_disabled = False

        def world_to_grid(self, wx, wy):
            return int(wx // TILE_SIZE), int(wy // TILE_SIZE)

        def update_visibility(self, revealers, return_new_reveals=False):
            captured.extend(revealers)
            return set() if return_new_reveals else None

    def _run(p):
        captured.clear()
        sim = SimpleNamespace(
            world=_FogWorld(), buildings=[p], heroes=[], peasants=[], guards=[],
            _fog_tick_counter=2, _fog_revealers_snapshot=None,
        )
        update_fog_of_war(sim)
        return list(captured)

    # Uncleared: POIs do not reveal fog.
    assert _run(poi) == []
    # Cleared: permanent 5-tile revealer at the POI centre.
    poi.grants_vision = True
    revealers = _run(poi)
    assert len(revealers) == 1
    assert revealers[0][2] == 5


# ---------------------------------------------------------------------------
# 5. Windmill Ruin
# ---------------------------------------------------------------------------


def test_windmill_one_time_knowledge_small_reveal():
    system = _make_system(9)
    poi = _make_poi("poi_windmill_ruin")
    hero = _hero_at_poi(poi)
    world, bus = _tick(system, [hero], [poi])

    assert world.reveal_calls == [(poi.grid_x, poi.grid_y, 8)]
    events = [e for e in bus.events if e.get("interaction_type") == "windmill"]
    assert len(events) == 1
    assert events[0]["narrative"]  # flavor text present
    assert poi.is_interacted is True
    assert poi.is_depleted is False  # ruin stays on the map (persistent)

    # One-time: cooldown expiry does not re-fire (is_interacted guard).
    system.tick_cooldowns([poi], dt=601.0)
    world2, bus2 = _tick(system, [hero], [poi])
    assert world2.reveal_calls == []
    assert bus2.events == []


# ---------------------------------------------------------------------------
# 6. Ancient Ruins
# ---------------------------------------------------------------------------


def test_ruins_reveal_cascade_gold_and_item():
    system = _make_system(11)
    # Guarantee the item roll (scripted loot rng: random() < 0.35, choice -> pool[0]).

    class _ScriptedRng:
        def random(self):
            return 0.01

        def choice(self, seq):
            return seq[0]

    system._loot_system = LootSystem(rng=_ScriptedRng())
    poi = _make_poi("poi_ancient_ruins", grid_x=60, grid_y=60)
    hidden = _make_poi("poi_gravestone", grid_x=68, grid_y=60, discovered=False)
    hero = _hero_at_poi(poi)
    world, bus = _tick(system, [hero], [poi, hidden])

    # Fog reveal 15 at the ruins.
    assert world.reveal_calls == [(60, 60, 15)]
    # Cascade discovery of the nearest undiscovered POI.
    assert hidden.is_discovered is True
    events = [e for e in bus.events if e.get("interaction_type") == "ruins"]
    assert len(events) == 1
    ev = events[0]
    assert ev["revealed_poi_name"] == "Overgrown Gravestone"
    # Tier-3 gold (60..150) + tier-3 item = uncommon pool[0] (long_bow).
    assert ev["gold"] >= 60 and hero.gold == ev["gold"]
    assert ev["item_name"] == "Long Bow"
    assert hero.received_items and hero.received_items[0].rarity == "uncommon"
    # One-time, but the ruins remain as a landmark.
    assert poi.is_interacted is True and poi.is_depleted is False


# ---------------------------------------------------------------------------
# 7. Dragon Cave
# ---------------------------------------------------------------------------


def test_dragon_cave_spawns_dragon_boss():
    system = _make_system(13)
    poi = _make_poi("poi_dragon_cave", grid_x=70, grid_y=30)
    hero = _hero_at_poi(poi)
    _, bus = _tick(system, [hero], [poi])

    boss_events = [e for e in bus.events if e.get("type") == "boss_spawned"]
    assert len(boss_events) == 1
    boss = boss_events[0]["boss"]
    assert boss.enemy_type == "dragon"
    assert boss.is_boss is True
    assert boss.name == "The Dragon"
    # ~1.3x DemonOverlord (hp 500 -> 650, atk 30 -> 39).
    assert boss.hp == 650 and boss.max_hp == 650
    assert boss.attack_power == 39
    assert poi.is_interacted is True
    # One-time spawn: no re-trigger.
    system.tick_cooldowns([poi], dt=601.0)
    _, bus2 = _tick(system, [hero], [poi])
    assert [e for e in bus2.events if e.get("type") == "boss_spawned"] == []


def test_dragon_always_drops_rare_plus_on_kill():
    assert "dragon" in loot_mod.BOSS_ENEMY_TYPES
    set_sim_seed(17)
    ls = LootSystem()
    for _ in range(20):
        item = ls.roll_enemy_drop("dragon")
        assert item is not None
        assert item.rarity in ("rare", "legendary")


# ---------------------------------------------------------------------------
# 8. rock_density consumed in worldgen
# ---------------------------------------------------------------------------


class _RockWorld:
    """Minimal all-grass world for generate_rock_scatter."""

    def __init__(self, size=120):
        from game.world import TileType
        self.width = size
        self.height = size
        self.tiles = [[TileType.GRASS for _ in range(size)] for _ in range(size)]


def _count_rocks_with_density(density: float, seed: int = 31) -> int:
    import game.worldgen as worldgen

    class _Zone:
        terrain_bias = {"rock_density": density}

    orig = worldgen.get_zone_blend
    worldgen.get_zone_blend = lambda x, y, cx, cy: (_Zone(), 1.0)
    try:
        set_sim_seed(seed)
        world = _RockWorld()
        worldgen.generate_rock_scatter(world)
        return len(world.rock_tiles)
    finally:
        worldgen.get_zone_blend = orig


def test_rock_density_bias_consumed():
    low = _count_rocks_with_density(0.5)
    high = _count_rocks_with_density(2.0)
    assert high > low, (low, high)
    assert low > 0  # baseline density still produces some rocks


def test_rock_scatter_deterministic_and_isolated_stream():
    a = _count_rocks_with_density(1.0, seed=99)
    b = _count_rocks_with_density(1.0, seed=99)
    assert a == b
    # Dedicated stream: world_gen sequence is untouched by rock scatter.
    set_sim_seed(99)
    before = get_rng("world_gen").random()
    _count_rocks_with_density(1.0, seed=99)
    set_sim_seed(99)
    assert get_rng("world_gen").random() == before


def test_world_generation_populates_rock_tiles():
    import game.worldgen as worldgen
    from game.world import TileType

    set_sim_seed(23)
    world = _RockWorld(size=100)
    world.rng = random.Random(23)
    worldgen.generate_terrain(world)
    assert hasattr(world, "rock_tiles")
    for (x, y) in world.rock_tiles:
        assert world.tiles[y][x] == TileType.GRASS  # rocks only on grass


# ---------------------------------------------------------------------------
# 9. Digest safety: no RNG draws without an interaction
# ---------------------------------------------------------------------------


def test_no_rng_drawn_when_no_interaction():
    system = _make_system(42)
    inter_state = system._rng.getstate()
    loot_state = system._loot_system._rng.getstate()

    # Hero far away from every POI (also one undiscovered + one depleted).
    far_hero = _MockHero(world_x=5.0, world_y=5.0)
    pois = [
        _make_poi("poi_mysterious_well", grid_x=200, grid_y=200),
        _make_poi("poi_ancient_ruins", grid_x=150, grid_y=150, discovered=False),
        _make_poi("poi_ruined_outpost", grid_x=100, grid_y=220),
    ]
    pois[2].is_depleted = True
    for _ in range(50):
        _tick(system, [far_hero], pois)
        system.tick_cooldowns(pois, dt=0.05)

    assert system._rng.getstate() == inter_state
    assert system._loot_system._rng.getstate() == loot_state
    for p in pois[:1]:
        assert p.is_interacted is False
