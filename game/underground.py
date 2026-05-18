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
    # --- WK57 fields: world coordinate offsets within underground area ---
    world_offset_x: int = 0  # tile offset from entrance (within underground area)
    world_offset_z: int = 0  # tile offset from entrance (deeper = larger z)


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
    # --- WK57 fields: layout bounding box and grids ---
    total_width: int = 0   # bounding box width in tiles
    total_height: int = 0  # bounding box height in tiles
    walkability: list[list[bool]] = field(default_factory=list)  # True=walkable
    floor_heightmap: list[list[float]] = field(default_factory=list)  # Perlin noise cave floor

    def compute_layout(self, rng=None):
        """Assign world offsets to chambers and build walkability + floor heightmap.

        Layout: chambers stacked vertically (deeper = larger z offset).
        Each chamber is centered on x=0 relative to entrance.
        Corridors connect adjacent chambers vertically.
        """
        from config import (
            UNDERGROUND_CHAMBER_SPACING,
            UNDERGROUND_CORRIDOR_WIDTH,
            UNDERGROUND_CAVE_NOISE_AMP,
            UNDERGROUND_CAVE_NOISE_FREQ,
            UNDERGROUND_DEPTH,
        )
        if rng is None:
            rng = get_rng("underground_layout")

        # 1. Assign chamber positions (vertical stack, centered on x=0)
        max_w = 0
        z_cursor = 0
        for ch in self.chambers:
            ch.world_offset_x = -(ch.width // 2)  # center horizontally
            ch.world_offset_z = z_cursor
            z_cursor += ch.height + UNDERGROUND_CHAMBER_SPACING
            max_w = max(max_w, ch.width)

        self.total_width = max_w + 4  # padding
        self.total_height = z_cursor + 2  # padding

        # 2. Build walkability grid (True = walkable tile)
        self.walkability = [
            [False for _ in range(self.total_width)]
            for _ in range(self.total_height)
        ]
        # Center offset so x=0 maps to grid center
        cx = self.total_width // 2

        for ch in self.chambers:
            for dz in range(ch.height):
                for dx in range(ch.width):
                    gx = cx + ch.world_offset_x + dx
                    gz = ch.world_offset_z + dz
                    if 0 <= gx < self.total_width and 0 <= gz < self.total_height:
                        self.walkability[gz][gx] = True

        # Mark corridors between connected chambers
        for i, ch in enumerate(self.chambers):
            if i + 1 < len(self.chambers):
                next_ch = self.chambers[i + 1]
                corridor_start_z = ch.world_offset_z + ch.height
                corridor_end_z = next_ch.world_offset_z
                for gz in range(corridor_start_z, corridor_end_z):
                    for dx in range(UNDERGROUND_CORRIDOR_WIDTH):
                        gx = cx - UNDERGROUND_CORRIDOR_WIDTH // 2 + dx
                        if 0 <= gx < self.total_width and 0 <= gz < self.total_height:
                            self.walkability[gz][gx] = True

        # 3. Build floor heightmap (Perlin noise for bumpy cave floor)
        try:
            from noise import pnoise2
        except ImportError:
            pnoise2 = None

        self.floor_heightmap = []
        for gz in range(self.total_height):
            row = []
            for gx in range(self.total_width):
                if pnoise2 is not None:
                    n = pnoise2(
                        gx * UNDERGROUND_CAVE_NOISE_FREQ,
                        gz * UNDERGROUND_CAVE_NOISE_FREQ,
                        octaves=2,
                        base=hash(self.area_id) % 1000,
                    )
                    h = -UNDERGROUND_DEPTH + (n + 1.0) * 0.5 * UNDERGROUND_CAVE_NOISE_AMP
                else:
                    h = -UNDERGROUND_DEPTH
                row.append(h)
            self.floor_heightmap.append(row)

        return self


# ---------------------------------------------------------------------------
# WK57 Wave 5E: Underground Hero Retreat Logic
# ---------------------------------------------------------------------------

def check_underground_hero_retreat(hero, underground_areas: dict) -> bool:
    """Check if an underground hero should retreat to the surface.

    Returns True if the hero began ascending, False otherwise.
    Triggers ascent when:
    - Hero HP < 30% of max HP
    - All chambers in their area are cleared
    """
    hero_layer = getattr(hero, "layer", 0)
    area_id = getattr(hero, "underground_area_id", None)
    if hero_layer != -1 or area_id is None:
        return False

    area = underground_areas.get(area_id)
    if area is None:
        # Area missing -- force ascent to avoid stuck hero
        if hasattr(hero, "begin_ascent"):
            hero.begin_ascent()
        return True

    # Retreat if low HP (< 30% max)
    hero_hp = getattr(hero, "hp", 0)
    hero_max_hp = getattr(hero, "max_hp", 1)
    if hero_max_hp > 0 and hero_hp < hero_max_hp * 0.3:
        if hasattr(hero, "begin_ascent"):
            hero.begin_ascent()
        return True

    # Retreat if all chambers are cleared
    if area.chambers and all(ch.is_cleared for ch in area.chambers):
        if hasattr(hero, "begin_ascent"):
            hero.begin_ascent()
        return True

    return False


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
    area.compute_layout(rng)
    return area
