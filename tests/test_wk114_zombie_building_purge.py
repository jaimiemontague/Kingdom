"""WK114 Round B — zombie-building purge seam test (Agent 11 QA).

Pins the post-purge invariant after the 8 WK34 "zombie" building types were
removed (Sovereign-authorized 2026-05-31). These types were defined + partially
wired but never spawned / never placeable; the Sovereign ruled keep-vs-purge =
PURGE. This test fails loudly if any of the 8 sneaks back into the registry, the
enum, the entity packages, or the factory — and it asserts the co-resident KEPT
types (guardhouse, palace, the guilds, etc.) survived intact.

See `.cursor/plans/wk114_round_b_zombie_building_purge.plan.md` §3 (NEW seam test).
"""
from __future__ import annotations

import pytest

from game.building_factory import BuildingFactory
from game.content.buildings import (
    BUILDING_DEFS,
    assert_building_type_coverage,
)
from game.entities.buildings.types import BuildingType
import game.entities as game_entities
import game.entities.buildings as game_entities_buildings


# The 8 purged WK34 "zombie" building types.
ZOMBIE_TYPE_STRINGS = [
    "gnome_hovel",
    "elven_bungalow",
    "dwarven_settlement",
    "ballista_tower",
    "wizard_tower",
    "fairgrounds",
    "library",
    "royal_gardens",
]

# Their corresponding BuildingType enum member names.
ZOMBIE_ENUM_NAMES = [
    "GNOME_HOVEL",
    "ELVEN_BUNGALOW",
    "DWARVEN_SETTLEMENT",
    "BALLISTA_TOWER",
    "WIZARD_TOWER",
    "FAIRGROUNDS",
    "LIBRARY",
    "ROYAL_GARDENS",
]

# Their entity-class names (formerly in dwellings.py / defensive.py / special.py).
ZOMBIE_CLASS_NAMES = [
    "GnomeHovel",
    "ElvenBungalow",
    "DwarvenSettlement",
    "BallistaTower",
    "WizardTower",
    "Fairgrounds",
    "Library",
    "RoyalGardens",
]

# Co-resident KEPT types that MUST survive the purge (subset of BUILDING_DEFS).
KEPT_TYPES = {
    "guardhouse",
    "palace",
    "warrior_guild",
    "ranger_guild",
    "marketplace",
    "temple",
    "house",
    "farm",
}


@pytest.mark.parametrize("type_str", ZOMBIE_TYPE_STRINGS)
def test_zombie_type_absent_from_building_defs(type_str: str) -> None:
    assert type_str not in BUILDING_DEFS, (
        f"{type_str!r} must be purged from BUILDING_DEFS"
    )


@pytest.mark.parametrize("enum_name", ZOMBIE_ENUM_NAMES)
def test_zombie_enum_member_absent(enum_name: str) -> None:
    assert getattr(BuildingType, enum_name, None) is None, (
        f"BuildingType.{enum_name} must be purged"
    )


@pytest.mark.parametrize("class_name", ZOMBIE_CLASS_NAMES)
def test_zombie_class_not_importable_from_entities(class_name: str) -> None:
    assert not hasattr(game_entities, class_name), (
        f"game.entities must not re-export {class_name}"
    )


@pytest.mark.parametrize("class_name", ZOMBIE_CLASS_NAMES)
def test_zombie_class_not_importable_from_entities_buildings(class_name: str) -> None:
    assert not hasattr(game_entities_buildings, class_name), (
        f"game.entities.buildings must not export {class_name}"
    )


def test_factory_registry_excludes_zombies_and_records_length() -> None:
    registry = BuildingFactory.BUILDING_REGISTRY
    class_names = {cls.__name__ for cls in registry.values()}
    for type_str in ZOMBIE_TYPE_STRINGS:
        assert type_str not in registry, f"{type_str!r} must not be a factory key"
    for class_name in ZOMBIE_CLASS_NAMES:
        assert class_name not in class_names, (
            f"{class_name} must not be a factory-registered class"
        )
    # Record the live post-purge length (was 27 pre-purge, 19 after).
    assert len(registry) == 19, (
        f"factory BUILDING_REGISTRY length must be 19 post-purge, got {len(registry)}"
    )


def test_kept_types_present_in_building_defs() -> None:
    assert KEPT_TYPES <= set(BUILDING_DEFS), (
        f"kept types missing from BUILDING_DEFS: {KEPT_TYPES - set(BUILDING_DEFS)}"
    )


def test_building_type_coverage_assert_passes() -> None:
    # enum values ⊆ BUILDING_DEFS — must not raise after the purge.
    assert_building_type_coverage()


def test_purge_candidate_flag_fully_removed() -> None:
    """No `purge_candidate` residue remains in the buildings source-of-truth."""
    from game.content import buildings as buildings_module

    with open(buildings_module.__file__, "r", encoding="utf-8-sig") as fh:
        src = fh.read()
    assert "purge_candidate" not in src, (
        "purge_candidate must be fully removed from game/content/buildings.py"
    )
