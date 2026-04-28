from __future__ import annotations

from game.entities.nature import Tree
from game.systems.nature import NatureSystem


def test_tree_growth_steps_over_six_minutes() -> None:
    ns = NatureSystem()
    t = Tree(10, 20, growth_percentage=0.25)
    trees = [t]

    # Before 2 minutes: still 0.25
    ns.tick(119.0, trees)
    assert t.growth_percentage == 0.25

    # Hit 2 minutes: 0.50
    ns.tick(1.0, trees)
    assert t.growth_percentage == 0.50

    # Hit 4 minutes: 0.75
    ns.tick(120.0, trees)
    assert t.growth_percentage == 0.75

    # Hit 6 minutes: 1.0
    ns.tick(120.0, trees)
    assert t.growth_percentage == 1.0

