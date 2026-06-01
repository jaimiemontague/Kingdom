"""WK70 Round C-1 snapshot-equality test (Wave W3, Agent 11 QA).

This is the behavior-preserving guard for the BuildingDef single-source-of-truth
consolidation (Move 10 / kills leak L7). WK70 replaced six+ hand-maintained building maps
with one ``game.content.buildings.BUILDING_DEFS`` table and DERIVED everything else from it.

This test EMBEDS a literal snapshot of the PRE-WK70 building maps (captured verbatim from
``git show HEAD:config.py`` and ``git show HEAD:game/building_factory.py`` at the WK69 commit
``2ee336c``, i.e. the commit immediately before this sprint) and asserts the now-derived
views equal them EXACTLY — both the key set and every value. If a future edit to
``BUILDING_DEFS`` (or the derivation logic) drifts any value or membership, this test fails.

Covers Definition-of-Done item E (plan §4) and the membership invariants in plan §2:
  * config.BUILDING_COSTS / SIZES / COLORS / MAX_OCCUPANTS == post-purge snapshots
  * BuildingFactory.BUILDING_REGISTRY == the post-purge 19 key->class mappings (by __name__)
  * build_catalog_panel.BUILDING_HOTKEYS / PLACEABLE_BUILDINGS == the known values, and
    building_list_panel reads the SAME values
  * the import-time coverage assert holds: {bt.value for bt in BuildingType} <= BUILDING_DEFS
  * lair membership: lairs in SIZES/COLORS, NOT in COSTS/MAX_OCCUPANTS
  * POI membership: the 12 poi_* keys in all four config maps
"""

# ---------------------------------------------------------------------------
# Post-purge literal snapshots (the verbatim values the derivation must reproduce).
# Originally captured from `git show HEAD:config.py` @ WK69 commit 2ee336c; the 8
# WK34 "zombie" building types (gnome_hovel, elven_bungalow, dwarven_settlement,
# ballista_tower, wizard_tower, fairgrounds, library, royal_gardens) were removed
# in WK114 Round B. Counts: COSTS=34, SIZES=39, COLORS=39, MAX_OCCUPANTS=34.
# ---------------------------------------------------------------------------

EXPECTED_COSTS = {
    'castle': 0,
    'warrior_guild': 150,
    'ranger_guild': 175,
    'rogue_guild': 160,
    'wizard_guild': 220,
    'marketplace': 100,
    'blacksmith': 200,
    'inn': 150,
    'trading_post': 250,
    'temple': 400,
    'temple_agrela': 400,
    'temple_dauros': 400,
    'temple_fervus': 400,
    'temple_krypta': 400,
    'temple_krolm': 400,
    'temple_helia': 400,
    'temple_lunord': 400,
    'guardhouse': 300,
    'palace': 0,
    'house': 0,
    'farm': 0,
    'food_stand': 0,
    'poi_shrine': 0,
    'poi_treasure_cache': 0,
    'poi_hermit_hut': 0,
    'poi_gravestone': 0,
    'poi_abandoned_camp': 0,
    'poi_druid_grove': 0,
    'poi_wizard_tower': 0,
    'poi_graveyard': 0,
    'poi_bandit_fortress': 0,
    'poi_cave_entrance': 0,
    'poi_mine_entrance': 0,
    'poi_demon_portal': 0,
}

EXPECTED_SIZES = {
    'castle': (3, 3),
    'warrior_guild': (2, 2),
    'ranger_guild': (2, 2),
    'rogue_guild': (2, 2),
    'wizard_guild': (2, 2),
    'marketplace': (2, 2),
    'blacksmith': (2, 2),
    'inn': (3, 2),
    'trading_post': (2, 2),
    'temple': (3, 4),
    'temple_agrela': (3, 3),
    'temple_dauros': (3, 3),
    'temple_fervus': (3, 3),
    'temple_krypta': (3, 3),
    'temple_krolm': (3, 3),
    'temple_helia': (3, 3),
    'temple_lunord': (3, 3),
    'guardhouse': (2, 2),
    'palace': (3, 3),
    'house': (1, 1),
    'farm': (3, 2),
    'food_stand': (1, 1),
    'goblin_camp': (2, 2),
    'wolf_den': (2, 2),
    'skeleton_crypt': (3, 3),
    'spider_nest': (2, 2),
    'bandit_camp': (3, 3),
    'poi_shrine': (1, 1),
    'poi_treasure_cache': (1, 1),
    'poi_hermit_hut': (1, 1),
    'poi_gravestone': (1, 1),
    'poi_abandoned_camp': (2, 2),
    'poi_druid_grove': (3, 3),
    'poi_wizard_tower': (2, 2),
    'poi_graveyard': (4, 4),
    'poi_bandit_fortress': (5, 5),
    'poi_cave_entrance': (2, 2),
    'poi_mine_entrance': (2, 2),
    'poi_demon_portal': (2, 2),
}

EXPECTED_COLORS = {
    'castle': (139, 69, 19),
    'warrior_guild': (178, 34, 34),
    'ranger_guild': (46, 139, 87),
    'rogue_guild': (75, 0, 130),
    'wizard_guild': (147, 112, 219),
    'marketplace': (218, 165, 32),
    'blacksmith': (105, 105, 105),
    'inn': (160, 82, 45),
    'trading_post': (255, 140, 0),
    'temple': (220, 200, 150),
    'temple_agrela': (255, 192, 203),
    'temple_dauros': (255, 255, 224),
    'temple_fervus': (50, 205, 50),
    'temple_krypta': (75, 0, 130),
    'temple_krolm': (139, 0, 0),
    'temple_helia': (255, 165, 0),
    'temple_lunord': (176, 196, 222),
    'guardhouse': (128, 128, 128),
    'palace': (184, 134, 11),
    'house': (120, 100, 80),
    'farm': (200, 170, 90),
    'food_stand': (210, 120, 60),
    'goblin_camp': (120, 80, 40),
    'wolf_den': (90, 90, 90),
    'skeleton_crypt': (70, 60, 90),
    'spider_nest': (20, 20, 20),
    'bandit_camp': (110, 70, 40),
    'poi_shrine': (100, 180, 255),
    'poi_treasure_cache': (255, 215, 0),
    'poi_hermit_hut': (139, 90, 43),
    'poi_gravestone': (140, 140, 140),
    'poi_abandoned_camp': (160, 120, 80),
    'poi_druid_grove': (50, 180, 50),
    'poi_wizard_tower': (147, 112, 219),
    'poi_graveyard': (90, 90, 110),
    'poi_bandit_fortress': (139, 69, 19),
    'poi_cave_entrance': (80, 60, 40),
    'poi_mine_entrance': (100, 80, 60),
    'poi_demon_portal': (180, 30, 30),
}

EXPECTED_MAX_OCCUPANTS = {
    'castle': 0,
    'warrior_guild': 4,
    'ranger_guild': 4,
    'rogue_guild': 4,
    'wizard_guild': 4,
    'marketplace': 3,
    'blacksmith': 2,
    'inn': 6,
    'trading_post': 0,
    'temple': 4,
    'temple_agrela': 4,
    'temple_dauros': 4,
    'temple_fervus': 4,
    'temple_krypta': 4,
    'temple_krolm': 4,
    'temple_helia': 4,
    'temple_lunord': 4,
    'guardhouse': 0,
    'palace': 0,
    'house': 0,
    'farm': 0,
    'food_stand': 0,
    'poi_shrine': 0,
    'poi_treasure_cache': 0,
    'poi_hermit_hut': 0,
    'poi_gravestone': 0,
    'poi_abandoned_camp': 0,
    'poi_druid_grove': 0,
    'poi_wizard_tower': 2,
    'poi_graveyard': 0,
    'poi_bandit_fortress': 6,
    'poi_cave_entrance': 4,
    'poi_mine_entrance': 4,
    'poi_demon_portal': 4,
}

# Post-purge factory registry (19 key -> class __name__).
# Originally from `git show HEAD:game/building_factory.py` @ WK69 commit 2ee336c;
# the 8 WK34 zombie mappings were removed in WK114 Round B.
EXPECTED_REGISTRY_CLASSNAMES = {
    'warrior_guild': 'WarriorGuild',
    'ranger_guild': 'RangerGuild',
    'rogue_guild': 'RogueGuild',
    'wizard_guild': 'WizardGuild',
    'marketplace': 'Marketplace',
    'food_stand': 'FoodStand',
    'blacksmith': 'Blacksmith',
    'inn': 'Inn',
    'trading_post': 'TradingPost',
    'temple': 'Temple',
    'temple_agrela': 'TempleAgrela',
    'temple_dauros': 'TempleDauros',
    'temple_fervus': 'TempleFervus',
    'temple_krypta': 'TempleKrypta',
    'temple_krolm': 'TempleKrolm',
    'temple_helia': 'TempleHelia',
    'temple_lunord': 'TempleLunord',
    'guardhouse': 'Guardhouse',
    'palace': 'Palace',
}

# Pre-WK70 catalog/hotkey/placeable literals (3 byte-identical copies collapsed to one).
# Source: plan §2 + the pre-WK70 build_catalog_panel.py / building_list_panel.py.
EXPECTED_HOTKEYS = {
    'warrior_guild': '1',
    'marketplace': '2',
    'ranger_guild': '3',
    'rogue_guild': '4',
    'wizard_guild': '5',
    'blacksmith': '6',
    'inn': '7',
    'trading_post': '8',
    'temple': 'T',
    'guardhouse': 'U',
}

EXPECTED_PLACEABLE = [
    'warrior_guild',
    'ranger_guild',
    'rogue_guild',
    'wizard_guild',
    'marketplace',
    'blacksmith',
    'inn',
    'trading_post',
    'temple',
    'guardhouse',
]

# The 5 monster lairs and the 12 POIs (plan §2 membership invariants).
LAIRS = {'goblin_camp', 'wolf_den', 'skeleton_crypt', 'spider_nest', 'bandit_camp'}
POIS = {
    'poi_shrine', 'poi_treasure_cache', 'poi_hermit_hut', 'poi_gravestone',
    'poi_abandoned_camp', 'poi_druid_grove', 'poi_wizard_tower', 'poi_graveyard',
    'poi_bandit_fortress', 'poi_cave_entrance', 'poi_mine_entrance', 'poi_demon_portal',
}


# ---------------------------------------------------------------------------
# Sanity on the embedded snapshot itself (catch a bad copy/paste in this file).
# ---------------------------------------------------------------------------

def test_snapshot_self_consistency():
    """The embedded literals match the documented pre-WK70 counts and shape."""
    assert len(EXPECTED_COSTS) == 34
    assert len(EXPECTED_SIZES) == 39
    assert len(EXPECTED_COLORS) == 39
    assert len(EXPECTED_MAX_OCCUPANTS) == 34
    assert len(EXPECTED_REGISTRY_CLASSNAMES) == 19
    assert len(EXPECTED_HOTKEYS) == 10
    assert len(EXPECTED_PLACEABLE) == 10
    # SIZES/COLORS share the same 39-key set; COSTS/OCCUPANTS share the same 34-key set.
    assert set(EXPECTED_SIZES) == set(EXPECTED_COLORS)
    assert set(EXPECTED_COSTS) == set(EXPECTED_MAX_OCCUPANTS)
    # The 39-key set is exactly the 34-key set plus the 5 lairs.
    assert set(EXPECTED_SIZES) - set(EXPECTED_COSTS) == LAIRS


# ---------------------------------------------------------------------------
# DoD E: the 4 derived config views == the pre-WK70 snapshots (keys + every value).
# ---------------------------------------------------------------------------

def test_config_costs_byte_identical():
    import config
    assert config.BUILDING_COSTS == EXPECTED_COSTS
    # Explicit key-set check so a key drift gives a clear diff, not just a value mismatch.
    assert set(config.BUILDING_COSTS) == set(EXPECTED_COSTS)


def test_config_sizes_byte_identical():
    import config
    assert config.BUILDING_SIZES == EXPECTED_SIZES
    assert set(config.BUILDING_SIZES) == set(EXPECTED_SIZES)


def test_config_colors_byte_identical():
    import config
    assert config.BUILDING_COLORS == EXPECTED_COLORS
    assert set(config.BUILDING_COLORS) == set(EXPECTED_COLORS)


def test_config_max_occupants_byte_identical():
    import config
    assert config.BUILDING_MAX_OCCUPANTS == EXPECTED_MAX_OCCUPANTS
    assert set(config.BUILDING_MAX_OCCUPANTS) == set(EXPECTED_MAX_OCCUPANTS)


# ---------------------------------------------------------------------------
# DoD E: the derived factory registry == the pre-WK70 27 class mappings (by __name__).
# Order-independent (compare key->classname dicts).
# ---------------------------------------------------------------------------

def test_factory_registry_19_class_mappings():
    from game.building_factory import BuildingFactory
    registry = BuildingFactory.BUILDING_REGISTRY
    derived = {key: cls.__name__ for key, cls in registry.items()}
    assert derived == EXPECTED_REGISTRY_CLASSNAMES
    assert len(registry) == 19
    # POIs and castle/house/farm must NOT be in the placement registry.
    for absent in ('castle', 'house', 'farm', *POIS, *LAIRS):
        assert absent not in registry


# ---------------------------------------------------------------------------
# DoD E/F: catalog/hotkey/placeable derive to the known values, and
# building_list_panel reads the SAME values (no second hand-maintained copy).
# ---------------------------------------------------------------------------

def test_build_catalog_hotkeys_and_placeable():
    from game.ui import build_catalog_panel
    assert build_catalog_panel.BUILDING_HOTKEYS == EXPECTED_HOTKEYS
    assert build_catalog_panel.PLACEABLE_BUILDINGS == EXPECTED_PLACEABLE
    # Placeable order is load-bearing (display order != hotkey order) — assert list equality
    # above already covers order; this makes the intent explicit.
    assert list(build_catalog_panel.PLACEABLE_BUILDINGS) == EXPECTED_PLACEABLE


def test_building_list_panel_reads_same_values():
    from game.ui import build_catalog_panel
    from game.ui import building_list_panel
    # building_list_panel imports the catalog's symbols (no duplicate copy).
    assert building_list_panel.BUILDING_HOTKEYS is build_catalog_panel.BUILDING_HOTKEYS
    assert building_list_panel.PLACEABLE_BUILDINGS is build_catalog_panel.PLACEABLE_BUILDINGS
    assert building_list_panel.BUILDING_HOTKEYS == EXPECTED_HOTKEYS
    assert building_list_panel.PLACEABLE_BUILDINGS == EXPECTED_PLACEABLE


def test_input_handler_hotkey_reverse_map():
    """The input_handler dispatch derives {event_key: type} from BUILDING_DEFS.

    Pre-WK70 the chain matched lowercased keys ('t'/'u'); the catalog dict stores 'T'/'U'.
    The reverse map must be lowercased and map back to the same 10 placeable buildings.
    """
    from game import input_handler
    reverse = input_handler.BUILD_HOTKEY_TO_TYPE
    # Every catalog hotkey (lowercased) must resolve to its building.
    for building, key in EXPECTED_HOTKEYS.items():
        assert reverse[key.lower()] == building
    assert set(reverse.values()) == set(EXPECTED_PLACEABLE)
    assert len(reverse) == 10


# ---------------------------------------------------------------------------
# DoD F: the import-time coverage assert holds.
# ---------------------------------------------------------------------------

def test_building_type_coverage_subset():
    from game.content.buildings import BUILDING_DEFS
    from game.entities.buildings.types import BuildingType
    enum_values = {bt.value for bt in BuildingType}
    assert enum_values <= set(BUILDING_DEFS)
    # And the explicit import-time guard runs without raising.
    from game.content.buildings import assert_building_type_coverage
    assert_building_type_coverage()


# ---------------------------------------------------------------------------
# Plan §2 membership invariants (lairs / POIs per view).
# ---------------------------------------------------------------------------

def test_lair_membership_invariant():
    import config
    sizes, colors = set(config.BUILDING_SIZES), set(config.BUILDING_COLORS)
    costs, occ = set(config.BUILDING_COSTS), set(config.BUILDING_MAX_OCCUPANTS)
    # Lairs appear in SIZES + COLORS ...
    assert LAIRS <= sizes
    assert LAIRS <= colors
    # ... but are ABSENT from COSTS + MAX_OCCUPANTS (so they hit Building.__init__ defaults).
    assert LAIRS.isdisjoint(costs)
    assert LAIRS.isdisjoint(occ)


def test_poi_membership_invariant():
    import config
    costs, sizes = set(config.BUILDING_COSTS), set(config.BUILDING_SIZES)
    colors, occ = set(config.BUILDING_COLORS), set(config.BUILDING_MAX_OCCUPANTS)
    assert len(POIS) == 12
    # The 12 poi_* keys are present in ALL FOUR config maps.
    assert POIS <= costs
    assert POIS <= sizes
    assert POIS <= colors
    assert POIS <= occ


def test_buildingdefs_is_single_source_and_flags_consistent():
    """BUILDING_DEFS flags must agree with the derived-view membership (defends F)."""
    from game.content.buildings import BUILDING_DEFS
    lair_keys = {k for k, d in BUILDING_DEFS.items() if d.is_lair}
    poi_keys = {k for k, d in BUILDING_DEFS.items() if d.is_poi}
    assert lair_keys == LAIRS
    assert poi_keys == POIS
