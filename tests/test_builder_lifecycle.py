from __future__ import annotations

from unittest.mock import MagicMock

from game.world import TileType, Visibility
from game.entities.buildings.base import Building
from game.entities.peasant import Peasant
from game.systems.neutral_buildings import NeutralBuildingSystem


class _Hero:
    is_alive = True


def test_builder_peasant_constructs_plot_and_despawns() -> None:
    world = MagicMock()
    world.width = 128
    world.height = 128
    world.tiles = [[TileType.GRASS for _ in range(world.width)] for _ in range(world.height)]
    world.visibility = [[Visibility.SEEN for _ in range(world.width)] for _ in range(world.height)]
    world.get_tile = lambda x, y: world.tiles[y][x]  # noqa: ARG005
    world.set_tile = lambda x, y, v: world.tiles[y].__setitem__(x, v)  # noqa: ARG005
    world.tree_growth_lookup = lambda x, y: 1.0  # noqa: ARG005
    world.world_to_grid = lambda wx, wy: (int(wx // 32), int(wy // 32))  # noqa: ARG005
    world.is_buildable = lambda gx, gy, w, h: True  # noqa: ARG005
    # Ensure at least one eligible tree exists so the builder can gather wood.
    world.tiles[52][52] = TileType.TREE

    nbs = NeutralBuildingSystem(world)
    castle = Building(50, 50, "castle")
    castle.size = (2, 2)

    heroes = [_Hero() for _ in range(1)]
    buildings: list = [castle]
    peasants: list = []

    # Spawn tick: should create a plot + a BuilderPeasant.
    nbs.tick(6.0, buildings, heroes, peasants, castle)
    plot = next((b for b in buildings if getattr(b, "is_neutral", False) and not getattr(b, "is_constructed", True)), None)
    assert plot is not None
    assert plot.hp == 1
    assert getattr(plot, "requires_builder_peasant", False) is True
    assert len(peasants) == 1

    # Regular peasants must ignore builder-only plots.
    regular = Peasant(castle.center_x, castle.center_y)
    gs = {"castle": castle, "buildings": buildings, "world": world}
    regular.update(0.2, gs)
    assert regular.target_building is None

    # Drive the builder until construction completes (includes chop+harvest time now).
    for _ in range(200):
        for p in list(peasants):
            p.update(0.2, gs)
        if getattr(plot, "is_constructed", False):
            break
    assert plot.is_constructed is True

    # Drive the builder home and ensure NeutralBuildingSystem removes it once it flags despawn.
    for _ in range(120):
        for p in list(peasants):
            p.update(0.2, gs)
        nbs.tick(0.1, buildings, heroes, peasants, castle)
        if not peasants:
            break
    assert peasants == []


def test_builder_replaced_if_dies_mid_construction_and_plot_unblocks() -> None:
    world = MagicMock()
    world.width = 128
    world.height = 128
    world.tiles = [[TileType.GRASS for _ in range(world.width)] for _ in range(world.height)]
    world.visibility = [[Visibility.SEEN for _ in range(world.width)] for _ in range(world.height)]
    world.get_tile = lambda x, y: world.tiles[y][x]  # noqa: ARG005
    world.set_tile = lambda x, y, v: world.tiles[y].__setitem__(x, v)  # noqa: ARG005
    world.tree_growth_lookup = lambda x, y: 1.0  # noqa: ARG005
    world.world_to_grid = lambda wx, wy: (int(wx // 32), int(wy // 32))  # noqa: ARG005
    world.is_buildable = lambda gx, gy, w, h: True  # noqa: ARG005
    # Provide ONE eligible tree so the initial builder can acquire wood and start construction.
    world.tiles[52][52] = TileType.TREE

    nbs = NeutralBuildingSystem(world)
    castle = Building(50, 50, "castle")
    castle.size = (2, 2)

    heroes = [_Hero() for _ in range(1)]
    buildings: list = [castle]
    peasants: list = []

    # Spawn tick: should create a plot + a BuilderPeasant.
    nbs.tick(6.0, buildings, heroes, peasants, castle)
    plot = next((b for b in buildings if getattr(b, "is_neutral", False) and not getattr(b, "is_constructed", True)), None)
    assert plot is not None
    assert getattr(plot, "requires_builder_peasant", False) is True
    assert len(peasants) == 1

    gs = {"castle": castle, "buildings": buildings, "world": world}

    # Drive until construction starts (but not finished).
    for _ in range(80):
        for p in list(peasants):
            p.update(0.2, gs)
        if getattr(plot, "construction_started", False):
            break
    assert getattr(plot, "construction_started", False) is True
    assert getattr(plot, "is_constructed", False) is False

    # Remove trees now: replacement builder must resume building without any wood gathering.
    world.tiles[52][52] = TileType.GRASS

    # Kill the builder mid-build.
    peasants[0].hp = 0
    assert getattr(peasants[0], "is_alive", False) is False

    # Next neutral-buildings tick should prune dead builder and spawn a replacement for the pending plot.
    nbs.tick(0.1, buildings, heroes, peasants, castle)
    assert len(peasants) == 1

    # Replacement builder should be able to complete construction even with no trees available.
    for _ in range(120):
        for p in list(peasants):
            p.update(0.2, gs)
        if getattr(plot, "is_constructed", False):
            break
    assert plot.is_constructed is True


def test_neutral_buildings_allow_up_to_three_concurrent_plots_and_builders() -> None:
    world = MagicMock()
    world.width = 128
    world.height = 128
    world.tiles = [[TileType.GRASS for _ in range(world.width)] for _ in range(world.height)]
    world.visibility = [[Visibility.SEEN for _ in range(world.width)] for _ in range(world.height)]
    world.get_tile = lambda x, y: world.tiles[y][x]  # noqa: ARG005
    world.set_tile = lambda x, y, v: world.tiles[y].__setitem__(x, v)  # noqa: ARG005
    world.tree_growth_lookup = lambda x, y: 1.0  # noqa: ARG005
    world.world_to_grid = lambda wx, wy: (int(wx // 32), int(wy // 32))  # noqa: ARG005
    world.is_buildable = lambda gx, gy, w, h: True  # noqa: ARG005

    nbs = NeutralBuildingSystem(world)
    castle = Building(50, 50, "castle")
    castle.size = (2, 2)

    # High demand: many heroes should want many houses.
    heroes = [_Hero() for _ in range(10)]
    buildings: list = [castle]
    peasants: list = []

    # Call tick multiple times at the spawn interval; system should create up to 3 pending plots
    # and spawn builder peasants for them.
    for _ in range(6):
        nbs.tick(6.0, buildings, heroes, peasants, castle)

    pending = [
        b
        for b in buildings
        if getattr(b, "is_neutral", False)
        and not getattr(b, "is_constructed", True)
        and getattr(b, "requires_builder_peasant", False)
    ]
    builders = [p for p in peasants if p.__class__.__name__ == "BuilderPeasant"]

    assert len(pending) == 3
    assert len(builders) == 3


def test_neutral_buildings_mix_types_before_stacking_houses() -> None:
    world = MagicMock()
    world.width = 128
    world.height = 128
    world.tiles = [[TileType.GRASS for _ in range(world.width)] for _ in range(world.height)]
    world.visibility = [[Visibility.SEEN for _ in range(world.width)] for _ in range(world.height)]
    world.get_tile = lambda x, y: world.tiles[y][x]  # noqa: ARG005
    world.set_tile = lambda x, y, v: world.tiles[y].__setitem__(x, v)  # noqa: ARG005
    world.tree_growth_lookup = lambda x, y: 1.0  # noqa: ARG005
    world.world_to_grid = lambda wx, wy: (int(wx // 32), int(wy // 32))  # noqa: ARG005
    world.is_buildable = lambda gx, gy, w, h: True  # noqa: ARG005

    nbs = NeutralBuildingSystem(world)
    castle = Building(50, 50, "castle")
    castle.size = (2, 2)

    # Demand exists for all three: houses (>=1), food stands (>=1), farms (>=1)
    heroes = [_Hero() for _ in range(6)]  # want_houses=6 want_food=2 want_farms=3
    buildings: list = [castle]
    peasants: list = []

    # After 3 spawn intervals, we should have one pending plot of each type underway.
    for _ in range(3):
        nbs.tick(6.0, buildings, heroes, peasants, castle)

    pending_types = sorted(
        [
            str(getattr(b, "building_type", ""))
            for b in buildings
            if getattr(b, "is_neutral", False)
            and not getattr(b, "is_constructed", True)
            and getattr(b, "requires_builder_peasant", False)
        ]
    )
    assert pending_types == ["farm", "food_stand", "house"]


def test_neutral_buildings_respects_priority_after_one_of_each() -> None:
    world = MagicMock()
    world.width = 128
    world.height = 128
    world.tiles = [[TileType.GRASS for _ in range(world.width)] for _ in range(world.height)]
    world.visibility = [[Visibility.SEEN for _ in range(world.width)] for _ in range(world.height)]
    world.get_tile = lambda x, y: world.tiles[y][x]  # noqa: ARG005
    world.set_tile = lambda x, y, v: world.tiles[y].__setitem__(x, v)  # noqa: ARG005
    world.tree_growth_lookup = lambda x, y: 1.0  # noqa: ARG005
    world.world_to_grid = lambda wx, wy: (int(wx // 32), int(wy // 32))  # noqa: ARG005
    world.is_buildable = lambda gx, gy, w, h: True  # noqa: ARG005

    nbs = NeutralBuildingSystem(world)
    castle = Building(50, 50, "castle")
    castle.size = (2, 2)

    # Demand: 2 food stands, many houses; farms also demanded but we should prioritize houses after the first of each.
    heroes = [_Hero() for _ in range(6)]  # want_houses=6 want_food=2 want_farms=3
    buildings: list = [castle]
    peasants: list = []

    # With mixing policy + cap 3, we expect first 3 spawn intervals to create:
    # 1 house + 1 food + 1 farm.
    for _ in range(3):
        nbs.tick(6.0, buildings, heroes, peasants, castle)

    pending_types = [
        str(getattr(b, "building_type", ""))
        for b in buildings
        if getattr(b, "is_neutral", False)
        and not getattr(b, "is_constructed", True)
        and getattr(b, "requires_builder_peasant", False)
    ]
    assert pending_types.count("food_stand") == 1
    assert pending_types.count("farm") == 1
    assert pending_types.count("house") == 1

    # Simulate the farm finishing and its builder leaving, freeing one slot.
    farm = next(b for b in buildings if getattr(b, "building_type", "") == "farm" and not getattr(b, "is_constructed", True))
    farm.is_constructed = True
    farm.requires_builder_peasant = False
    # Despawn one builder so we have capacity to spawn a new one for the next plot.
    if peasants:
        peasants[0].should_despawn = True
    nbs.tick(0.1, buildings, heroes, peasants, castle)

    # Next spawn interval should pick by priority: house first (not second food).
    nbs.tick(6.0, buildings, heroes, peasants, castle)

    pending_types2 = [
        str(getattr(b, "building_type", ""))
        for b in buildings
        if getattr(b, "is_neutral", False)
        and not getattr(b, "is_constructed", True)
        and getattr(b, "requires_builder_peasant", False)
    ]
    assert pending_types2.count("house") == 2
    assert pending_types2.count("food_stand") == 1
    assert pending_types2.count("farm") == 0

