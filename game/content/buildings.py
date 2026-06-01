"""Single source of truth for static building data (WK70 Round C-1, Move 10 / kills L7).

`BUILDING_DEFS` is the ONLY hand-authored building table. Every other building map
(``config.BUILDING_COSTS/SIZES/COLORS/MAX_OCCUPANTS``, the factory class registry, and
the catalog/hotkey/placeable lists) is DERIVED from this as a byte-identical back-compat
view. This is purely behavior-preserving: the derived dicts have identical keys AND values
to the pre-WK70 hand-maintained copies (guarded by ``tests/test_wk70_building_registry.py``).

Membership rules (encode exactly — readers depend on them):
  - Every ``BuildingType`` enum key is present (guarded by ``assert_building_type_coverage``).
    The 8 WK34 "zombie" types (gnome_hovel/elven_bungalow/dwarven_settlement/ballista_tower/
    wizard_tower/fairgrounds/library/royal_gardens) were deleted in WK114 Round B.
  - The 5 monster lairs (``is_lair=True``) appear in the SIZES/COLORS views but are
    EXCLUDED from the COSTS/MAX_OCCUPANTS views (they currently hit the
    ``Building.__init__`` fallbacks cost=100 / max_occupants=8). The ``cost``/
    ``max_occupants`` fields below record those effective defaults for documentation, but
    the derived COSTS/OCCUPANTS dicts filter lairs out via ``if not d.is_lair``.
  - The 12 POIs (``is_poi=True``, ``cls=None``) appear in all 4 config views.

IMPORT-CYCLE NOTE: ``config`` is imported by ~152 files, and the building classes live in
``game/entities/*`` modules that themselves import ``config`` (e.g. lair.py,
neutral_buildings.py). Importing those classes at module load here would create a cycle
(config -> buildings -> entities -> config). So this module imports NOTHING from
``game.entities`` at load time: ``cls`` is stored as ``None`` and the constructor class for
a key is resolved LAZILY via :func:`building_class_for`, which imports the class map inside
the function. The factory registry derivation in W2 uses that accessor.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BuildingDef:
    """Static, hand-authored data for one building/lair/POI key."""

    type: str
    size: tuple[int, int]
    color: tuple[int, int, int]
    cost: int
    max_occupants: int
    cls: type | None  # constructor; None for castle/house/farm/POIs and resolved lazily
    hotkey: str | None
    placeable: bool
    placeable_order: int  # display order in the build catalog (-1 if not placeable)
    hero_class: str | None  # warrior/ranger/rogue/wizard for guilds, cleric for temple
    is_lair: bool = False
    is_poi: bool = False


def _b(
    type: str,
    size: tuple[int, int],
    color: tuple[int, int, int],
    cost: int,
    max_occupants: int,
    *,
    hotkey: str | None = None,
    placeable: bool = False,
    placeable_order: int = -1,
    hero_class: str | None = None,
    is_lair: bool = False,
    is_poi: bool = False,
) -> BuildingDef:
    """Build a BuildingDef. ``cls`` is always None here (resolved lazily); see module docstring."""
    return BuildingDef(
        type=type,
        size=size,
        color=color,
        cost=cost,
        max_occupants=max_occupants,
        cls=None,
        hotkey=hotkey,
        placeable=placeable,
        placeable_order=placeable_order,
        hero_class=hero_class,
        is_lair=is_lair,
        is_poi=is_poi,
    )


BUILDING_DEFS: dict[str, BuildingDef] = {
    # ── Core / player buildings ──────────────────────────────────────────────
    "castle": _b("castle", (3, 3), (139, 69, 19), 0, 0),
    "warrior_guild": _b(
        "warrior_guild", (2, 2), (178, 34, 34), 150, 4,
        hotkey="1", placeable=True, placeable_order=0, hero_class="warrior",
    ),
    "ranger_guild": _b(
        "ranger_guild", (2, 2), (46, 139, 87), 175, 4,
        hotkey="3", placeable=True, placeable_order=1, hero_class="ranger",
    ),
    "rogue_guild": _b(
        "rogue_guild", (2, 2), (75, 0, 130), 160, 4,
        hotkey="4", placeable=True, placeable_order=2, hero_class="rogue",
    ),
    "wizard_guild": _b(
        "wizard_guild", (2, 2), (147, 112, 219), 220, 4,
        hotkey="5", placeable=True, placeable_order=3, hero_class="wizard",
    ),
    "marketplace": _b(
        "marketplace", (2, 2), (218, 165, 32), 100, 3,
        hotkey="2", placeable=True, placeable_order=4,
    ),
    # Phase 1: Economic Buildings
    "blacksmith": _b(
        "blacksmith", (2, 2), (105, 105, 105), 200, 2,
        hotkey="6", placeable=True, placeable_order=5,
    ),
    "inn": _b(
        "inn", (3, 2), (160, 82, 45), 150, 6,
        hotkey="7", placeable=True, placeable_order=6,
    ),
    "trading_post": _b(
        "trading_post", (2, 2), (255, 140, 0), 250, 0,
        hotkey="8", placeable=True, placeable_order=7,
    ),
    # Phase 2: Temples
    "temple": _b(
        "temple", (3, 4), (220, 200, 150), 400, 4,
        hotkey="T", placeable=True, placeable_order=8, hero_class="cleric",
    ),
    "temple_agrela": _b("temple_agrela", (3, 3), (255, 192, 203), 400, 4),
    "temple_dauros": _b("temple_dauros", (3, 3), (255, 255, 224), 400, 4),
    "temple_fervus": _b("temple_fervus", (3, 3), (50, 205, 50), 400, 4),
    "temple_krypta": _b("temple_krypta", (3, 3), (75, 0, 130), 400, 4),
    "temple_krolm": _b("temple_krolm", (3, 3), (139, 0, 0), 400, 4),
    "temple_helia": _b("temple_helia", (3, 3), (255, 165, 0), 400, 4),
    "temple_lunord": _b("temple_lunord", (3, 3), (176, 196, 222), 400, 4),
    # Phase 4: Defensive Structures
    "guardhouse": _b(
        "guardhouse", (2, 2), (128, 128, 128), 300, 0,
        hotkey="U", placeable=True, placeable_order=9,
    ),
    # Phase 6: Palace
    "palace": _b("palace", (3, 3), (184, 134, 11), 0, 0),
    # Neutral auto-spawn buildings (not player-placeable)
    "house": _b("house", (1, 1), (120, 100, 80), 0, 0),
    "farm": _b("farm", (3, 2), (200, 170, 90), 0, 0),
    "food_stand": _b("food_stand", (1, 1), (210, 120, 60), 0, 0),
    # ── Monster lairs (is_lair) ─────────────────────────────────────────────
    # In SIZES/COLORS only; ABSENT from COSTS/OCCUPANTS (they hit Building.__init__
    # fallbacks cost=100 / max_occupants=8, recorded here for documentation).
    "goblin_camp": _b("goblin_camp", (2, 2), (120, 80, 40), 100, 8, is_lair=True),
    "wolf_den": _b("wolf_den", (2, 2), (90, 90, 90), 100, 8, is_lair=True),
    "skeleton_crypt": _b("skeleton_crypt", (3, 3), (70, 60, 90), 100, 8, is_lair=True),
    "spider_nest": _b("spider_nest", (2, 2), (20, 20, 20), 100, 8, is_lair=True),
    "bandit_camp": _b("bandit_camp", (3, 3), (110, 70, 40), 100, 8, is_lair=True),
    # ── Points of interest (is_poi, cls=None) ───────────────────────────────
    "poi_shrine": _b("poi_shrine", (1, 1), (100, 180, 255), 0, 0, is_poi=True),
    "poi_treasure_cache": _b("poi_treasure_cache", (1, 1), (255, 215, 0), 0, 0, is_poi=True),
    "poi_hermit_hut": _b("poi_hermit_hut", (1, 1), (139, 90, 43), 0, 0, is_poi=True),
    "poi_gravestone": _b("poi_gravestone", (1, 1), (140, 140, 140), 0, 0, is_poi=True),
    "poi_abandoned_camp": _b("poi_abandoned_camp", (2, 2), (160, 120, 80), 0, 0, is_poi=True),
    "poi_druid_grove": _b("poi_druid_grove", (3, 3), (50, 180, 50), 0, 0, is_poi=True),
    "poi_wizard_tower": _b("poi_wizard_tower", (2, 2), (147, 112, 219), 0, 2, is_poi=True),
    "poi_graveyard": _b("poi_graveyard", (4, 4), (90, 90, 110), 0, 0, is_poi=True),
    "poi_bandit_fortress": _b("poi_bandit_fortress", (5, 5), (139, 69, 19), 0, 6, is_poi=True),
    "poi_cave_entrance": _b("poi_cave_entrance", (2, 2), (80, 60, 40), 0, 4, is_poi=True),
    "poi_mine_entrance": _b("poi_mine_entrance", (2, 2), (100, 80, 60), 0, 4, is_poi=True),
    "poi_demon_portal": _b("poi_demon_portal", (2, 2), (180, 30, 30), 0, 4, is_poi=True),
}


# Lazy class-name map for resolving BuildingDef.cls without an import cycle (see docstring).
# Keys here mirror the current BuildingFactory.BUILDING_REGISTRY (19 player/neutral classes).
# castle/house/farm and the POIs are intentionally absent (cls=None for them). Lairs are
# constructed via the lair-spawn path, not the building factory, so they are absent too.
_CLASS_NAMES: dict[str, str] = {
    "warrior_guild": "WarriorGuild",
    "ranger_guild": "RangerGuild",
    "rogue_guild": "RogueGuild",
    "wizard_guild": "WizardGuild",
    "marketplace": "Marketplace",
    "food_stand": "FoodStand",
    "blacksmith": "Blacksmith",
    "inn": "Inn",
    "trading_post": "TradingPost",
    "temple": "Temple",
    "temple_agrela": "TempleAgrela",
    "temple_dauros": "TempleDauros",
    "temple_fervus": "TempleFervus",
    "temple_krypta": "TempleKrypta",
    "temple_krolm": "TempleKrolm",
    "temple_helia": "TempleHelia",
    "temple_lunord": "TempleLunord",
    "guardhouse": "Guardhouse",
    "palace": "Palace",
}


def building_class_for(key: str) -> type | None:
    """Return the constructor class for a building key, or None.

    Lazy by design: imports the entity class map inside the function so this module has no
    load-time dependency on ``game.entities`` (which would cycle through ``config``). Used by
    the W2 factory-registry derivation. Returns None for keys with no factory class
    (castle/house/farm, lairs, POIs).
    """
    name = _CLASS_NAMES.get(key)
    if name is None:
        return None
    from game import entities as _entities  # local import breaks the config<->buildings cycle
    from game.entities.neutral_buildings import FoodStand as _FoodStand

    if name == "FoodStand":
        return _FoodStand
    return getattr(_entities, name, None)


def _building_type_values() -> set[str]:
    """Load BuildingType's values from game/entities/buildings/types.py WITHOUT importing the
    game.entities package.

    Importing ``game.entities.buildings.types`` the normal way would run the
    ``game.entities`` / ``game.entities.buildings`` package ``__init__``s, which pull base.py
    (imports config) and hero.py -> game.systems (imports config) — a cycle, since config
    imports THIS module while initializing. ``types.py`` itself only imports ``enum``, so we
    load just that file by path.
    """
    import importlib.util
    import os

    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # repo root (../../..)
    path = os.path.join(here, "game", "entities", "buildings", "types.py")
    spec = importlib.util.spec_from_file_location("_buildingdef_types_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {bt.value for bt in module.BuildingType}


def assert_building_type_coverage() -> None:
    """WK70 coverage guard: every BuildingType enum value must appear in BUILDING_DEFS."""
    missing = _building_type_values() - set(BUILDING_DEFS)
    assert not missing, f"BUILDING_DEFS is missing BuildingType enum keys: {sorted(missing)}"


# Run the coverage guard at import (cycle-free; see _building_type_values docstring).
assert_building_type_coverage()
