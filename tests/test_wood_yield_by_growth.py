from game.entities.builder_peasant import BuilderPeasant
from game.entities.buildings.base import Building


def test_wood_yield_by_growth_thresholds() -> None:
    castle = Building(0, 0, "castle")
    target = Building(1, 1, "house")
    target.is_constructed = False
    target.hp = 1

    bp = BuilderPeasant.spawn_from_castle(castle=castle, target_building=target)

    assert bp._wood_yield_for_growth(1.0) == 10
    assert bp._wood_yield_for_growth(0.99) == 7
    assert bp._wood_yield_for_growth(0.75) == 7
    assert bp._wood_yield_for_growth(0.74) == 5
    assert bp._wood_yield_for_growth(0.50) == 5
    assert bp._wood_yield_for_growth(0.49) == 0

