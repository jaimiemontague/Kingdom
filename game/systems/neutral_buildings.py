"""
NeutralBuildingSystem

Auto-spawns neutral civilian buildings near the castle based on hero count.
"""

from __future__ import annotations

from config import BUILDING_SIZES, TILE_SIZE
from game.entities.neutral_buildings import House, Farm, FoodStand
from game.entities.builder_peasant import BuilderPeasant
from game.sim.determinism import get_rng
from game.systems.protocol import GameSystem, SystemContext


def _building_type_str(building_type: object) -> str:
    """Normalize enum or str building_type for comparisons (WK32 R2)."""
    if building_type is None:
        return ""
    return str(getattr(building_type, "value", building_type))


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
    an existing building (or another same-tick placement) is strictly less than ``min_tile_gap``.

    With ``min_tile_gap == 2``: closest tiles of two footprints must not be edge- or
    corner-adjacent (Chebyshev 0 or 1). A value of 2 means there is at least one empty grid
    cell between the two rectangles (the usual "1-tile gap" read on a grid).
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
        want = str(building_type)
        return sum(
            1
            for b in buildings
            if _building_type_str(getattr(b, "building_type", None)) == want and getattr(b, "hp", 1) > 0
        )

    def _find_castle(self, buildings: list) -> object | None:
        for building in buildings:
            bt = getattr(building, "building_type", None)
            if getattr(bt, "value", bt) == "castle":
                return building
        return None

    def _find_marketplace(self, buildings: list) -> object | None:
        """Return the first constructed marketplace, or None."""
        for b in buildings or []:
            if _building_type_str(getattr(b, "building_type", None)) != "marketplace":
                continue
            if getattr(b, "is_constructed", False):
                return b
        return None

    def update(self, ctx: SystemContext, dt: float) -> None:
        """Protocol update hook for neutral building simulation."""
        castle = self._find_castle(ctx.buildings)
        self.tick(dt, ctx.buildings, ctx.heroes, getattr(ctx, "peasants", []), castle)

    def tick(self, dt: float, buildings: list, heroes: list, peasants: list, castle) -> None:
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

        # WK43: despawn builders that have returned to the castle.
        if peasants is not None:
            peasants[:] = [
                p
                for p in peasants
                if getattr(p, "is_alive", True) and not getattr(p, "should_despawn", False)
            ]

        # WK43/WK46/WK46+: builder-only plots are constructed by BuilderPeasants.
        #
        # Throughput: allow up to N plots/builders concurrently so large hero counts can ramp faster.
        MAX_CONCURRENT_BUILDER_PLOTS = 3
        MAX_CONCURRENT_BUILDERS = 3

        pending_builder_plots = [
            b
            for b in (buildings or [])
            if getattr(b, "requires_builder_peasant", False)
            and getattr(b, "hp", 0) > 0
            and not getattr(b, "is_constructed", False)
        ]

        # Spawn replacement/new builders for pending plots, up to MAX_CONCURRENT_BUILDERS, without duplicates.
        active_builders = [p for p in (peasants or []) if isinstance(p, BuilderPeasant)]
        active_builders_by_plot_id = {
            id(getattr(p, "target_building", None))
            for p in active_builders
            if getattr(p, "target_building", None) is not None and getattr(getattr(p, "target_building", None), "hp", 0) > 0
        }

        if pending_builder_plots and peasants is not None:
            pending_builder_plots.sort(
                key=lambda b: (getattr(b, "placed_time_ms", 0), int(getattr(b, "grid_x", 0)), int(getattr(b, "grid_y", 0)))
            )
            for plot in pending_builder_plots:
                if len(active_builders) >= int(MAX_CONCURRENT_BUILDERS):
                    break
                if id(plot) in active_builders_by_plot_id:
                    continue
                peasants.append(BuilderPeasant.spawn_from_castle(castle=castle, target_building=plot))
                active_builders.append(peasants[-1])
                active_builders_by_plot_id.add(id(plot))

        hero_count = len([h for h in (heroes or []) if getattr(h, "is_alive", False)])
        want_houses = max(0, hero_count)
        # WK34: farms at half rate to prioritize houses.
        want_farms = max(0, hero_count // 2)
        want_food = max(0, hero_count // 3)

        cur_houses = self._count(buildings, "house")
        cur_farms = self._count(buildings, "farm")
        cur_food = self._count(buildings, "food_stand")

        # Spawn pacing
        self._spawn_timer += float(dt)
        if self._spawn_timer < self.spawn_interval_sec:
            return
        self._spawn_timer = 0.0

        # If we already have enough pending builder-only plots, don't spawn more this tick.
        if len(pending_builder_plots) >= int(MAX_CONCURRENT_BUILDER_PLOTS):
            return

        # Spawn one per tick (keeps “popping up” gradual and avoids spikes).
        #
        # Queue policy (WK46 throughput): with up to 3 concurrent builders, we should not wait for
        # all houses to finish before starting food/farm. We enforce:
        # - First, ensure at most one "in-flight" plot exists for each demanded type (house, food, farm).
        # - Then, fill remaining in-flight slots by priority: house -> food_stand -> farm.

        def _pending_count(bt: str) -> int:
            return sum(1 for b in pending_builder_plots if _building_type_str(getattr(b, "building_type", "")) == bt)

        pending_house = _pending_count("house")
        pending_food = _pending_count("food_stand")
        pending_farm = _pending_count("farm")

        def _needs(bt: str) -> bool:
            if bt == "house":
                return cur_houses < want_houses
            if bt == "food_stand":
                return cur_food < want_food
            if bt == "farm":
                return cur_farms < want_farms
            return False

        def _pick_next_type() -> str | None:
            # Rule set (player-facing):
            # - With multiple builder slots, don't wait for all houses to finish before starting food/farm.
            # - After at least one of a type has been introduced, follow strict priority:
            #   house > food_stand > farm (farm is always the lowest priority queue).
            #
            # To avoid starving farms forever, we "introduce" the first farm once when:
            # there is farm demand, there is already at least one house+food underway, and there are no farms at all yet.

            if _needs("house") and pending_house == 0:
                return "house"
            if _needs("food_stand") and pending_food == 0:
                return "food_stand"

            # Introduce the first farm once (so farms can start existing), but do not re-prioritize farms after that.
            if (
                _needs("farm")
                and pending_farm == 0
                and int(cur_farms) == 0
                and pending_house > 0
                and pending_food > 0
            ):
                return "farm"

            # Main priority once underway: house, then food, then farm.
            if _needs("house"):
                return "house"
            if _needs("food_stand"):
                return "food_stand"
            if _needs("farm"):
                return "farm"
            return None

        bt = _pick_next_type()
        if bt is None:
            return

        if bt == "house":
            spot = self._find_spot(
                castle=castle,
                buildings=buildings,
                size=(1, 1),
                min_r=3,
                max_r=10,
                shuffle_within_ring=False,  # "as tightly as they can"
            )
            if spot:
                plot = House(*spot, is_constructed=False)
                buildings.append(plot)
                if peasants is not None:
                    if sum(1 for p in peasants if isinstance(p, BuilderPeasant)) < int(MAX_CONCURRENT_BUILDERS):
                        peasants.append(BuilderPeasant.spawn_from_castle(castle=castle, target_building=plot))
            return

        if bt == "food_stand":
            market = self._find_marketplace(buildings)
            spot = None
            # WK34: first 2 food stands try to spawn very near the marketplace (2–3 tiles).
            if cur_food < 2 and market is not None:
                market_gx = int(getattr(market, "grid_x", 0))
                market_gy = int(getattr(market, "grid_y", 0))
                mw, mh = getattr(market, "size", (1, 1))
                market_cx = market_gx + int(mw) // 2
                market_cy = market_gy + int(mh) // 2

                class _MarketProxy:
                    grid_x = market_cx
                    grid_y = market_cy
                    size = (1, 1)

                spot = self._find_spot(
                    castle=_MarketProxy(),
                    buildings=buildings,
                    size=(1, 1),
                    min_r=2,
                    max_r=3,
                    shuffle_within_ring=True,
                )

            if spot is None:
                spot = self._find_spot(
                    castle=castle,
                    buildings=buildings,
                    size=(1, 1),
                    min_r=3,
                    max_r=18,
                    shuffle_within_ring=True,
                )
            if spot:
                plot = FoodStand(*spot, is_constructed=False)
                buildings.append(plot)
                if peasants is not None:
                    if sum(1 for p in peasants if isinstance(p, BuilderPeasant)) < int(MAX_CONCURRENT_BUILDERS):
                        peasants.append(BuilderPeasant.spawn_from_castle(castle=castle, target_building=plot))
            return

        if bt == "farm":
            fw, fh = BUILDING_SIZES.get("farm", (3, 2))
            spot = self._find_spot(
                castle=castle,
                buildings=buildings,
                size=(int(fw), int(fh)),
                min_r=8,
                max_r=18,
                shuffle_within_ring=True,
            )
            if spot:
                plot = Farm(*spot, is_constructed=False)
                buildings.append(plot)
                if peasants is not None:
                    if sum(1 for p in peasants if isinstance(p, BuilderPeasant)) < int(MAX_CONCURRENT_BUILDERS):
                        peasants.append(BuilderPeasant.spawn_from_castle(castle=castle, target_building=plot))
            return


