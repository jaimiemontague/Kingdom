from __future__ import annotations

from game.sim_engine import SimEngine
from game.entities.builder_peasant import BuilderPeasant
from game.entities.neutral_buildings import House


def test_regular_peasant_respawn_not_suppressed_by_builder_peasants() -> None:
    sim = SimEngine()
    sim.setup_initial_state()
    castle = next(b for b in sim.buildings if getattr(b, "building_type", None) == "castle")

    # Put two alive BuilderPeasants into the sim.
    plot1 = House(int(getattr(castle, "grid_x", 0)) + 5, int(getattr(castle, "grid_y", 0)) + 5, is_constructed=False)
    plot2 = House(int(getattr(castle, "grid_x", 0)) + 6, int(getattr(castle, "grid_y", 0)) + 5, is_constructed=False)
    sim.buildings.extend([plot1, plot2])
    sim.peasants = [
        BuilderPeasant.spawn_from_castle(castle=castle, target_building=plot1),
        BuilderPeasant.spawn_from_castle(castle=castle, target_building=plot2),
    ]

    # No regular peasants alive -> should respawn one within ~5s even though builders exist.
    gs = {"castle": castle, "buildings": sim.buildings, "world": sim.world, "sim": sim}
    sim.update(5.1, gs)

    regular_alive = [
        p for p in sim.peasants if getattr(p, "is_alive", False) and not isinstance(p, BuilderPeasant)
    ]
    assert len(regular_alive) >= 1

