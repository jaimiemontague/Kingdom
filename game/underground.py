"""Underground layer system for cave/mine POI interiors.

WK57: Data model for underground areas. Currently uses the interior overlay
approach (2D modal view) when heroes enter cave/mine POIs. The vertical
stacking renderer (3D underground below Y=0) is designed but deferred.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from game.sim.determinism import get_rng


@dataclass
class UndergroundChamber:
    """A room in an underground area."""

    chamber_id: str
    name: str
    depth_level: int  # 0 = entrance, 1+ = deeper
    width: int  # tiles
    height: int  # tiles
    enemies: list = field(default_factory=list)  # enemy type strings
    loot_gold: int = 0
    is_explored: bool = False
    is_cleared: bool = False
    connections: list[str] = field(default_factory=list)  # connected chamber_ids


@dataclass
class UndergroundArea:
    """An underground area attached to a cave/mine entrance POI."""

    area_id: str
    entrance_poi_type: str  # "poi_cave_entrance" or "poi_mine_entrance"
    entrance_grid_x: int
    entrance_grid_y: int
    chambers: list[UndergroundChamber] = field(default_factory=list)
    max_depth: int = 3
    difficulty_tier: int = 3
    is_generated: bool = False


def generate_underground_area(poi, rng=None) -> UndergroundArea:
    """Procedurally generate an underground area for a cave/mine entrance POI.

    Creates a linear chain of 3-5 chambers with increasing difficulty.
    """
    if rng is None:
        rng = get_rng("underground_gen")

    poi_def = getattr(poi, "poi_def", None)
    poi_type = poi_def.poi_type if poi_def else "poi_cave_entrance"
    difficulty = poi_def.difficulty_tier if poi_def else 3

    area = UndergroundArea(
        area_id=f"underground_{poi.grid_x}_{poi.grid_y}",
        entrance_poi_type=poi_type,
        entrance_grid_x=poi.grid_x,
        entrance_grid_y=poi.grid_y,
        difficulty_tier=difficulty,
    )

    num_chambers = rng.randint(3, 5)
    area.max_depth = num_chambers - 1

    is_mine = "mine" in poi_type

    for i in range(num_chambers):
        # Enemies scale with depth
        enemy_count = min(i + 1, 4)
        if is_mine:
            enemies = ["goblin"] * enemy_count
        else:
            enemies = ["skeleton"] * max(1, enemy_count - 1) + ["spider"] * min(
                1, enemy_count
            )

        # Loot scales with depth
        base_gold = 10 + i * 15
        loot = rng.randint(base_gold, base_gold + 20)

        chamber = UndergroundChamber(
            chamber_id=f"chamber_{i}",
            name=f"{'Mine Shaft' if is_mine else 'Cave Chamber'} {i + 1}",
            depth_level=i,
            width=rng.randint(4, 8),
            height=rng.randint(4, 8),
            enemies=enemies,
            loot_gold=loot,
            connections=[f"chamber_{i-1}"] if i > 0 else [],
        )
        if i > 0:
            area.chambers[i - 1].connections.append(f"chamber_{i}")
        area.chambers.append(chamber)

    area.is_generated = True
    return area
