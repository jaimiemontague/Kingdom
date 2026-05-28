"""WK61-R11-BUG-002: starter food_stand exists near marketplace at game start."""

from __future__ import annotations

from config import STARTING_BUILDINGS


def test_starting_buildings_includes_food_stand_near_marketplace() -> None:
    types = [entry[0] for entry in STARTING_BUILDINGS]
    assert "food_stand" in types
    assert "marketplace" in types

    market = next(entry for entry in STARTING_BUILDINGS if entry[0] == "marketplace")
    food = next(entry for entry in STARTING_BUILDINGS if entry[0] == "food_stand")
    _, mx, my = market
    _, fx, fy = food
    assert abs(fx - mx) <= 4 and abs(fy - my) <= 4, "food_stand should be near marketplace"
