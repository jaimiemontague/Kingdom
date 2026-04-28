from __future__ import annotations

from game.systems.nature import NatureSystem
from game.world import TileType, World


def test_nature_spawns_saplings_on_cadence_and_marks_tile_tree() -> None:
    w = World()
    ns = NatureSystem()
    trees: list = []

    # 29 seconds: no spawn yet
    ns.tick(29.0, trees, world=w)
    assert len(trees) == 0

    # +1 second: should spawn 1 sapling
    ns.tick(1.0, trees, world=w)
    assert len(trees) == 1
    t = trees[0]
    assert t.growth_percentage == 0.25
    assert w.get_tile(int(t.grid_x), int(t.grid_y)) == TileType.TREE


def test_nature_sapling_cap_is_enforced() -> None:
    w = World()
    ns = NatureSystem()
    ns.sapling_cap = 3
    trees: list = []

    # Advance a long time; should not exceed cap.
    ns.tick(999.0, trees, world=w)
    assert len(trees) == 3

