"""WK32: neutral auto-spawn Chebyshev gap between footprints."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from game.entities.buildings.base import Building
from game.sim.determinism import set_sim_seed
from game.systems.neutral_buildings import (
    NeutralBuildingSystem,
    _min_chebyshev_between_footprints,
    _violates_auto_spawn_gap,
)


def test_min_chebyshev_adjacent_one() -> None:
    assert _min_chebyshev_between_footprints(0, 0, 1, 1, 1, 0, 1, 1) == 1


def test_min_chebyshev_one_tile_gap_is_two() -> None:
    assert _min_chebyshev_between_footprints(0, 0, 1, 1, 2, 0, 1, 1) == 2


def test_violates_gap_rejects_adjacent_footprints() -> None:
    other = SimpleNamespace(grid_x=0, grid_y=0, size=(1, 1), hp=100)
    assert _violates_auto_spawn_gap([other], 1, 0, 1, 1) is True
    assert _violates_auto_spawn_gap([other], 2, 0, 1, 1) is False


def test_violates_gap_considers_pending_same_tick() -> None:
    pending = [(2, 0, 1, 1)]
    assert _violates_auto_spawn_gap([], 1, 0, 1, 1, pending=pending) is True
    # (3,0) is Chebyshev 1 from pending tile (2,0); (4,0) is distance 2 — allowed.
    assert _violates_auto_spawn_gap([], 4, 0, 1, 1, pending=pending) is False


def test_neutral_autospawn_pairwise_min_chebyshev_ge2_vs_castle_and_each_other() -> None:
    """WK32 revised 2026-04-18: long-run NeutralBuildingSystem spawns respect >=1-tile gap."""
    set_sim_seed(12345)
    world = MagicMock()
    world.is_buildable = lambda gx, gy, w, h: True  # noqa: ARG005 — open meadow

    nbs = NeutralBuildingSystem(world)
    castle = Building(50, 50, "castle")
    castle.size = (2, 2)

    class _Hero:
        is_alive = True

    heroes = [_Hero() for _ in range(12)]
    buildings: list = [castle]

    for _ in range(500):
        nbs.tick(6.0, buildings, heroes, castle)

    alive = [b for b in buildings if getattr(b, "hp", 1) > 0 and hasattr(b, "grid_x")]
    assert len(alive) >= 6
    for i, a in enumerate(alive):
        for b in alive[i + 1 :]:
            aw, ah = int(a.size[0]), int(a.size[1])
            bw, bh = int(b.size[0]), int(b.size[1])
            d = _min_chebyshev_between_footprints(
                int(a.grid_x), int(a.grid_y), aw, ah,
                int(b.grid_x), int(b.grid_y), bw, bh,
            )
            assert d >= 2, (
                f"min Chebyshev {d} between {getattr(a, 'building_type', a)}"
                f"@{a.grid_x},{a.grid_y} ({aw}x{ah}) and "
                f"{getattr(b, 'building_type', b)}@{b.grid_x},{b.grid_y} ({bw}x{bh})"
            )
