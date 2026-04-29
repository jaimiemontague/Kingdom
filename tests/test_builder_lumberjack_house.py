from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from config import TILE_SIZE
from game.entities.buildings.base import Building
from game.entities.builder_peasant import BuilderPeasant, BuilderPeasantPhase
from game.entities.neutral_buildings import House
from game.world import TileType, Visibility


@dataclass
class _TreeRec:
    tx: int
    ty: int
    growth: float
    chopped: bool = False
    harvested: bool = False


class _FakeSim:
    def __init__(self, world, trees: list[_TreeRec]):
        self.world = world
        self._trees = trees
        self._logs: dict[tuple[int, int], float] = {}

    def find_nearest_choppable_tree_for_builder(self, from_tx: int, from_ty: int):
        best = None
        best_d2 = None
        for t in self._trees:
            if t.chopped:
                continue
            if t.growth < 0.50:
                continue
            if self.world.visibility[t.ty][t.tx] == Visibility.UNSEEN:
                continue
            dx = t.tx - int(from_tx)
            dy = t.ty - int(from_ty)
            d2 = dx * dx + dy * dy
            if best_d2 is None or d2 < best_d2 or (d2 == best_d2 and (t.tx, t.ty) < (best[0], best[1])):
                best_d2 = d2
                best = (t.tx, t.ty, t.growth)
        return best

    def chop_tree_at(self, tx: int, ty: int) -> float:
        for t in self._trees:
            if t.tx == int(tx) and t.ty == int(ty) and not t.chopped:
                t.chopped = True
                self.world.set_tile(int(tx), int(ty), int(TileType.GRASS))
                self._logs[(int(tx), int(ty))] = float(t.growth)
                return float(t.growth)
        raise AssertionError("chop_tree_at called on missing tree")

    def harvest_log_at(self, tx: int, ty: int) -> int:
        g = float(self._logs.pop((int(tx), int(ty))))
        if g >= 1.0:
            return 10
        if g >= 0.75:
            return 7
        if g >= 0.50:
            return 5
        return 0


def _mk_world() -> MagicMock:
    world = MagicMock()
    world.width = 64
    world.height = 64
    world.tiles = [[TileType.GRASS for _ in range(world.width)] for _ in range(world.height)]
    world.visibility = [[Visibility.SEEN for _ in range(world.width)] for _ in range(world.height)]
    world.get_tile = lambda x, y: world.tiles[y][x]  # noqa: ARG005
    world.set_tile = lambda x, y, v: world.tiles[y].__setitem__(x, v)  # noqa: ARG005
    world.tree_growth_lookup = lambda x, y: 1.0  # noqa: ARG005
    world.world_to_grid = lambda wx, wy: (int(wx // TILE_SIZE), int(wy // TILE_SIZE))  # noqa: ARG005
    return world


def test_builder_does_not_build_until_house_wood_threshold_met() -> None:
    world = _mk_world()
    # One eligible tree yields 10, enough for a house.
    world.set_tile(12, 10, int(TileType.TREE))
    sim = _FakeSim(world, trees=[_TreeRec(12, 10, 1.0)])

    castle = Building(10, 10, "castle")
    plot = House(15, 10, is_constructed=False)

    bp = BuilderPeasant.spawn_from_castle(castle=castle, target_building=plot)
    gs = {"castle": castle, "buildings": [castle, plot], "world": world, "sim": sim}

    # Run until the builder has chopped+harvested once.
    for _ in range(200):
        bp.update(0.1, gs)
        if bp.wood_inventory >= 10:
            break

    assert bp.wood_inventory >= 10
    # After wood is met, builder should be on the build path (not stuck in wood loop).
    assert bp.phase in {
        BuilderPeasantPhase.MOVE_TO_PLOT,
        BuilderPeasantPhase.BUILDING,
        BuilderPeasantPhase.RETURN_TO_CASTLE,
        BuilderPeasantPhase.DESPAWN,
    }

    # Ensure it can actually build after wood is acquired.
    for _ in range(200):
        bp.update(0.2, gs)
        if getattr(plot, "is_constructed", False):
            break
    assert plot.is_constructed is True

