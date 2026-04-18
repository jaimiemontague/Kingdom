"""
NeutralBuildingSystem

Auto-spawns neutral civilian buildings near the castle based on hero count.
"""

from __future__ import annotations

from config import TILE_SIZE
from game.entities.neutral_buildings import House, Farm, FoodStand
from game.sim.determinism import get_rng
from game.systems.protocol import GameSystem, SystemContext


def _overlaps_any(buildings: list, gx: int, gy: int, w: int, h: int) -> bool:
    for b in buildings or []:
        if getattr(b, "hp", 1) <= 0:
            continue
        if not hasattr(b, "occupies_tile"):
            continue
        for dx in range(w):
            for dy in range(h):
                if b.occupies_tile(gx + dx, gy + dy):
                    return True
    return False


def _min_chebyshev_between_footprints(
    gx: int, gy: int, w: int, h: int,
    ox: int, oy: int, ow: int, oh: int,
) -> int:
    """Minimum Chebyshev distance between any tile in the two footprints (grid tiles)."""
    best = 10**9
    for tx in range(gx, gx + w):
        for ty in range(gy, gy + h):
            for ux in range(ox, ox + ow):
                for uy in range(oy, oy + oh):
                    d = max(abs(tx - ux), abs(ty - uy))
                    if d < best:
                        best = d
    return best


def _violates_auto_spawn_gap(
    buildings: list,
    gx: int,
    gy: int,
    w: int,
    h: int,
    *,
    pending: list[tuple[int, int, int, int]] | None = None,
    min_tile_gap: int = 2,
) -> bool:
    """
    WK32: auto-spawned buildings need at least one empty tile between footprints (Chebyshev).

    Reject if the minimum Chebyshev distance between any tile of the candidate and any tile of
    an existing building (or another same-tick placement) is strictly less than ``min_tile_gap``
    (2 => adjacent footprints are rejected; one-tile gap is accepted).
    """
    pending = pending or []
    for b in buildings or []:
        if getattr(b, "hp", 1) <= 0:
            continue
        if not hasattr(b, "grid_x"):
            continue
        bw, bh = getattr(b, "size", (1, 1))
        bx, by = int(b.grid_x), int(b.grid_y)
        if _min_chebyshev_between_footprints(gx, gy, w, h, bx, by, int(bw), int(bh)) < int(min_tile_gap):
            return True
    for px, py, pw, ph in pending:
        if _min_chebyshev_between_footprints(gx, gy, w, h, px, py, pw, ph) < int(min_tile_gap):
            return True
    return False


def _ring_positions(cx: int, cy: int, r: int) -> list[tuple[int, int]]:
    """Chebyshev ring around (cx,cy) with radius r (top-left placements)."""
    out: list[tuple[int, int]] = []
    x0, x1 = cx - r, cx + r
    y0, y1 = cy - r, cy + r
    for x in range(x0, x1 + 1):
        out.append((x, y0))
        out.append((x, y1))
    for y in range(y0 + 1, y1):
        out.append((x0, y))
        out.append((x1, y))
    return out


class NeutralBuildingSystem(GameSystem):
    """
    Spawns Houses/Farms/FoodStands and ticks their passive tax generation.

    Caps:
    - 1 House per hero
    - 1 Farm per hero
    - 1 Food Stand per 3 heroes
    """

    def __init__(self, world):
        self.world = world
        self._spawn_timer = 0.0
        self.spawn_interval_sec = 6.0
        self.rng = get_rng("neutral_buildings")

    def _castle_center_tile(self, castle) -> tuple[int, int]:
        gx = getattr(castle, "grid_x", 0)
        gy = getattr(castle, "grid_y", 0)
        size = getattr(castle, "size", (1, 1))
        return (gx + size[0] // 2, gy + size[1] // 2)

    def _find_spot(
        self,
        *,
        castle,
        buildings: list,
        size: tuple[int, int],
        min_r: int,
        max_r: int,
        shuffle_within_ring: bool,
        pending_same_tick: list[tuple[int, int, int, int]] | None = None,
    ) -> tuple[int, int] | None:
        cx, cy = self._castle_center_tile(castle)
        w, h = size

        for r in range(int(min_r), int(max_r) + 1):
            candidates = _ring_positions(cx, cy, r)
            if shuffle_within_ring:
                rng = getattr(self, "rng", get_rng("neutral_buildings"))
                rng.shuffle(candidates)
            for gx, gy in candidates:
                if not self.world.is_buildable(gx, gy, w, h):
                    continue
                if _overlaps_any(buildings, gx, gy, w, h):
                    continue
                if _violates_auto_spawn_gap(buildings, gx, gy, w, h, pending=pending_same_tick):
                    continue
                return (gx, gy)
        return None

    def _count(self, buildings: list, building_type: str) -> int:
        return sum(1 for b in buildings if getattr(b, "building_type", None) == building_type and getattr(b, "hp", 1) > 0)

    def _find_castle(self, buildings: list) -> object | None:
        for building in buildings:
            bt = getattr(building, "building_type", None)
            if getattr(bt, "value", bt) == "castle":
                return building
        return None

    def update(self, ctx: SystemContext, dt: float) -> None:
        """Protocol update hook for neutral building simulation."""
        castle = self._find_castle(ctx.buildings)
        self.tick(dt, ctx.buildings, ctx.heroes, castle)

    def tick(self, dt: float, buildings: list, heroes: list, castle) -> None:
        # Tick tax generation for existing neutral buildings
        for b in buildings:
            if getattr(b, "is_neutral", False) and hasattr(b, "update"):
                try:
                    b.update(dt)
                except TypeError:
                    # Some buildings accept different update signatures; ignore for neutrals.
                    pass

        if not castle:
            return

        hero_count = len([h for h in (heroes or []) if getattr(h, "is_alive", False)])
        want_houses = max(0, hero_count)
        want_farms = max(0, hero_count)
        want_food = max(0, hero_count // 3)

        cur_houses = self._count(buildings, "house")
        cur_farms = self._count(buildings, "farm")
        cur_food = self._count(buildings, "food_stand")

        # Spawn pacing
        self._spawn_timer += float(dt)
        if self._spawn_timer < self.spawn_interval_sec:
            return
        self._spawn_timer = 0.0

        # Spawn one per tick (keeps “popping up” gradual and avoids spikes).
        # Priority: Houses near castle, then FoodStands, then Farms.
        if cur_houses < want_houses:
            spot = self._find_spot(
                castle=castle,
                buildings=buildings,
                size=(1, 1),
                min_r=3,
                max_r=10,
                shuffle_within_ring=False,  # "as tightly as they can"
            )
            if spot:
                buildings.append(House(*spot))
            return

        if cur_food < want_food:
            spot = self._find_spot(
                castle=castle,
                buildings=buildings,
                size=(1, 1),
                min_r=3,
                max_r=18,
                shuffle_within_ring=True,
            )
            if spot:
                buildings.append(FoodStand(*spot))
            return

        if cur_farms < want_farms:
            spot = self._find_spot(
                castle=castle,
                buildings=buildings,
                size=(2, 2),
                min_r=8,
                max_r=18,
                shuffle_within_ring=True,
            )
            if spot:
                buildings.append(Farm(*spot))
            return


