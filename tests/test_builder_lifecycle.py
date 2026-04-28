from __future__ import annotations

from unittest.mock import MagicMock

from game.entities.buildings.base import Building
from game.entities.peasant import Peasant
from game.systems.neutral_buildings import NeutralBuildingSystem


class _Hero:
    is_alive = True


def test_builder_peasant_constructs_plot_and_despawns() -> None:
    world = MagicMock()
    world.is_buildable = lambda gx, gy, w, h: True  # noqa: ARG005

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
    gs = {"castle": castle, "buildings": buildings}
    regular.update(0.2, gs)
    assert regular.target_building is None

    # Drive the builder until construction completes.
    for _ in range(80):
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

