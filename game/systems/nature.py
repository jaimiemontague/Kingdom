"""
WK44 Stage 2: NatureSystem

Deterministic growth simulation for Tree entities.

Design notes:
- Growth is discrete: 0.25 -> 0.50 -> 0.75 -> 1.00.
- Total time is ~6 minutes, implemented as 3 transitions at 2 minutes each.

WK45 Stage 2.5:
- Spawn new saplings over time (1 per 30s global cadence, cap 50 total trees).
- Saplings immediately set the world tile to TileType.TREE, but remain non-blocking until growth >= 0.75
  (blocking is enforced by World via tree_growth_lookup; integration owned by Agent 03).
"""

from __future__ import annotations

from typing import Any

from game.entities.nature import Tree
from game.sim.determinism import get_rng


class NatureSystem:
    def __init__(self) -> None:
        self.stage_duration_ms = 2 * 60 * 1000  # 2 minutes per stage transition
        # WK45: sapling spawning cadence + cap
        self.sapling_interval_ms = 30 * 1000
        # Cap is on TOTAL tree entities (including starting forests). Keep it comfortably
        # above the world-gen starting tree count so spawns can happen during playtests.
        self.sapling_cap = 1000
        self._sapling_spawn_ms_accum = 0
        self.rng = get_rng("nature")

    def tick(self, dt: float, trees: list[Tree], *, world: Any | None = None, buildings: list | None = None) -> None:
        add_ms = int(round(float(dt) * 1000.0))
        if add_ms <= 0:
            return

        # WK45: spawn saplings first so they can start growing immediately this tick.
        self._sapling_spawn_ms_accum += add_ms
        while self._sapling_spawn_ms_accum >= self.sapling_interval_ms and len(trees) < int(self.sapling_cap):
            self._sapling_spawn_ms_accum -= int(self.sapling_interval_ms)
            if world is None:
                break
            if self._try_spawn_sapling(world=world, buildings=buildings, trees=trees) is None:
                # If no valid spot, stop spending accumulated time this tick.
                break

        if not trees:
            return

        for t in trees:
            if t.growth_percentage >= 1.0:
                t.growth_percentage = 1.0
                continue

            t.growth_ms_accum = int(t.growth_ms_accum) + add_ms
            stage = int(t.growth_ms_accum // int(self.stage_duration_ms))
            stage = max(0, min(3, stage))  # 0..3 corresponds to 0.25..1.0
            t.growth_percentage = (stage + 1) * 0.25

    def _try_spawn_sapling(self, *, world: Any, buildings: list | None, trees: list[Tree]) -> tuple[int, int] | None:
        # Import locally to avoid pulling pygame-heavy world module into pure-sim contexts unexpectedly.
        from game.world import TileType

        buildings = buildings or []
        existing = {t.key for t in trees}

        def _occupied_by_building(tx: int, ty: int) -> bool:
            for b in buildings:
                if getattr(b, "hp", 1) <= 0:
                    continue
                occ = getattr(b, "occupies_tile", None)
                if callable(occ) and occ(int(tx), int(ty)):
                    return True
            return False

        def _valid(tx: int, ty: int) -> bool:
            if (int(tx), int(ty)) in existing:
                return False
            if getattr(world, "get_tile")(int(tx), int(ty)) != TileType.GRASS:
                return False
            if not getattr(world, "is_buildable")(int(tx), int(ty), 1, 1):
                return False
            if _occupied_by_building(int(tx), int(ty)):
                return False
            return True

        # Prefer near existing trees (within radius N). Fallback to uniform random grass.
        radius = 6
        if trees:
            for _ in range(80):
                anchor = trees[self.rng.randrange(0, len(trees))]
                tx = int(anchor.grid_x) + int(self.rng.randint(-radius, radius))
                ty = int(anchor.grid_y) + int(self.rng.randint(-radius, radius))
                if not (0 <= tx < int(getattr(world, "width", 0)) and 0 <= ty < int(getattr(world, "height", 0))):
                    continue
                if _valid(tx, ty):
                    getattr(world, "set_tile")(int(tx), int(ty), TileType.TREE)
                    trees.append(Tree(int(tx), int(ty), growth_percentage=0.25))
                    return (int(tx), int(ty))

        for _ in range(400):
            tx = int(self.rng.randint(0, int(getattr(world, "width", 1)) - 1))
            ty = int(self.rng.randint(0, int(getattr(world, "height", 1)) - 1))
            if _valid(tx, ty):
                getattr(world, "set_tile")(int(tx), int(ty), TileType.TREE)
                trees.append(Tree(int(tx), int(ty), growth_percentage=0.25))
                return (int(tx), int(ty))

        return None

    @staticmethod
    def remove_trees_in_footprint(*, trees: list[Tree], grid_x: int, grid_y: int, w: int, h: int) -> int:
        """Helper for integration: remove any trees within a rectangular building footprint."""
        if not trees:
            return 0
        want = {(x, y) for x in range(int(grid_x), int(grid_x) + int(w)) for y in range(int(grid_y), int(grid_y) + int(h))}
        before = len(trees)
        trees[:] = [t for t in trees if t.key not in want]
        return before - len(trees)

