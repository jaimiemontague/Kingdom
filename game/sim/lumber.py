"""WK69 Round B-1: lumber/tree-economy service extracted from SimEngine (behavior-preserving move).

Holds the whole tree/log cluster that used to live inline on ``SimEngine``:
init/lookup of sim Tree entities, footprint clearing, the deterministic
choppable-tree search, chopping, and log harvesting. Each function takes the
live SimEngine as ``sim`` and reads/writes its state exactly as the former
methods did via ``self``. SimEngine keeps one-line delegating wrappers so
callers (tests, ``game/entities/builder_peasant.py`` via the LumberOps surface,
and ``setup_initial_state``) are unchanged.

This module must NOT import ``game.sim_engine`` at runtime (no import cycle): it
takes ``sim`` as a duck-typed parameter and only imports the same leaf helpers
the original methods used.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from game.entities.nature import LogStack, Tree

if TYPE_CHECKING:  # type-only; avoids a runtime import cycle with game.sim_engine
    from game.sim_engine import SimEngine


def wood_yield_for_growth(growth: float) -> int:
    g = float(growth)
    if g >= 1.0:
        return 10
    if g >= 0.75:
        return 7
    if g >= 0.50:
        return 5
    return 0


def init_trees_from_world(sim: "SimEngine") -> None:
    """WK44: Build sim tree entities from world TileType.TREE grid."""
    try:
        from game.world import TileType
    except Exception:
        return
    sim.trees = []
    for ty in range(int(getattr(sim.world, "height", 0))):
        row = sim.world.tiles[ty]
        for tx in range(int(getattr(sim.world, "width", 0))):
            if int(row[tx]) == int(TileType.TREE):
                # Startup trees are mature. Only newly spawned trees after startup should be saplings.
                sim.trees.append(Tree(int(tx), int(ty), growth_percentage=1.0, growth_ms_accum=10**9))
    sim._tree_growth_by_tile = {t.key: float(getattr(t, "growth_percentage", 0.25)) for t in sim.trees}
    # Mythos S5: keep the blocking-tile set (growth >= 0.75) in lockstep after the
    # bulk replace above (see SimEngine._rebuild_tree_blocking_set).
    rebuild = getattr(sim, "_rebuild_tree_blocking_set", None)
    if callable(rebuild):
        rebuild()


def tree_growth_lookup(sim: "SimEngine", tx: int, ty: int) -> float:
    """World callback: return current tree growth for a tile (0..1)."""
    return float(sim._tree_growth_by_tile.get((int(tx), int(ty)), 1.0))


def remove_trees_in_footprint(sim: "SimEngine", grid_x: int, grid_y: int, w_tiles: int, h_tiles: int) -> int:
    """WK45: when placing a building, remove any Tree entities under its footprint."""
    gx = int(grid_x)
    gy = int(grid_y)
    w = max(0, int(w_tiles))
    h = max(0, int(h_tiles))
    if w <= 0 or h <= 0 or not sim.trees:
        return 0

    removed_keys: set[tuple[int, int]] = set()
    kept: list[Tree] = []
    for t in sim.trees:
        tx, ty = int(getattr(t, "grid_x", 0)), int(getattr(t, "grid_y", 0))
        if gx <= tx < (gx + w) and gy <= ty < (gy + h):
            removed_keys.add((tx, ty))
        else:
            kept.append(t)

    if not removed_keys:
        return 0

    sim.trees = kept

    # If the underlying tile is a TREE tile, clear it so we don't leave a "tree" behind
    # with no Tree entity/growth entry (which would default to growth=1.0 and block forever).
    try:
        from game.world import TileType

        for tx, ty in removed_keys:
            if int(sim.world.get_tile(int(tx), int(ty))) == int(TileType.TREE):
                sim.world.set_tile(int(tx), int(ty), int(TileType.GRASS))
    except Exception:
        pass

    # Keep lookup consistent immediately (used by World.is_buildable/is_walkable).
    # Mythos S5: _remove_tree_growth also drops the key from the blocking-tile set
    # (getattr-guarded: duck-typed fake sims in tests may lack the helper).
    _rm = getattr(sim, "_remove_tree_growth", None)
    for k in removed_keys:
        if callable(_rm):
            _rm(k)
        else:
            sim._tree_growth_by_tile.pop(k, None)

    return len(removed_keys)


def find_nearest_choppable_tree_for_builder(sim: "SimEngine", from_tx: int, from_ty: int) -> tuple[int, int, float] | None:
    """Return (tx, ty, growth) for the nearest choppable tree tile, or None.

    Rules (WK46 plan):
    - Must be a sim Tree entity at the tile.
    - Must have growth >= 0.50.
    - Must be on a tile with Visibility != UNSEEN (SEEN or VISIBLE).
    - Deterministic selection with stable tie-breaking.

    Distance metric: Chebyshev (grid-feel; matches plan suggestion).
    """
    if not sim.trees:
        return None

    tx0 = int(from_tx)
    ty0 = int(from_ty)

    world = sim.world
    vis_grid = getattr(world, "visibility", None)
    if vis_grid is None:
        return None

    best: tuple[int, int, float] | None = None
    best_d: int | None = None

    # Determinism: iterate in stable order.
    for t in sorted(sim.trees, key=lambda _t: (int(getattr(_t, "grid_y", 0)), int(getattr(_t, "grid_x", 0)))):
        tx = int(getattr(t, "grid_x", 0))
        ty = int(getattr(t, "grid_y", 0))
        if not (0 <= tx < int(getattr(world, "width", 0)) and 0 <= ty < int(getattr(world, "height", 0))):
            continue

        try:
            if vis_grid[ty][tx] == 0:  # Visibility.UNSEEN
                continue
        except Exception:
            continue

        g = float(sim._tree_growth_by_tile.get((tx, ty), float(getattr(t, "growth_percentage", 1.0))))
        if g < 0.50:
            continue

        d = max(abs(tx - tx0), abs(ty - ty0))
        if best_d is None or d < best_d:
            best_d = d
            best = (tx, ty, g)
        elif d == best_d and best is not None:
            # Tie-break deterministically by tile key.
            if (ty, tx) < (best[1], best[0]):
                best = (tx, ty, g)

    return best


def chop_tree_at(sim: "SimEngine", tx: int, ty: int) -> float | None:
    """Remove a Tree at (tx,ty), clear world tile to GRASS, and spawn a LogStack record."""
    tx_i = int(tx)
    ty_i = int(ty)
    key = (tx_i, ty_i)
    if not sim.trees:
        return None

    # Find + remove the tree entity.
    tree: Tree | None = None
    kept: list[Tree] = []
    for t in sim.trees:
        if (int(getattr(t, "grid_x", 0)), int(getattr(t, "grid_y", 0))) == key:
            tree = t
        else:
            kept.append(t)
    if tree is None:
        return None
    sim.trees = kept

    g = float(sim._tree_growth_by_tile.get(key, float(getattr(tree, "growth_percentage", 1.0))))

    # Clear tile + lookup immediately (prevents invisible blockers).
    try:
        from game.world import TileType

        if int(sim.world.get_tile(tx_i, ty_i)) == int(TileType.TREE):
            sim.world.set_tile(tx_i, ty_i, int(TileType.GRASS))
    except Exception:
        pass
    # Mythos S5: _remove_tree_growth also drops the key from the blocking-tile set
    # (getattr-guarded: duck-typed fake sims in tests may lack the helper).
    _rm = getattr(sim, "_remove_tree_growth", None)
    if callable(_rm):
        _rm(key)
    else:
        sim._tree_growth_by_tile.pop(key, None)

    # Ensure a single log stack per tile.
    sim.log_stacks = [ls for ls in sim.log_stacks if ls.key != key]
    sim.log_stacks.append(LogStack(tx_i, ty_i, source_tree_growth=g))
    return g


def harvest_log_at(sim: "SimEngine", tx: int, ty: int) -> int:
    """Remove the LogStack at (tx,ty) and return wood yield based on its recorded growth."""
    tx_i = int(tx)
    ty_i = int(ty)
    key = (tx_i, ty_i)
    for i, ls in enumerate(list(sim.log_stacks)):
        if ls.key == key:
            g = float(getattr(ls, "source_tree_growth", 1.0))
            # Remove this one.
            try:
                sim.log_stacks.pop(i)
            except Exception:
                sim.log_stacks = [x for x in sim.log_stacks if x.key != key]
            return int(wood_yield_for_growth(g))
    return 0
