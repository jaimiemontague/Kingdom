"""WK69 Round B-1: entity-separation service extracted from SimEngine (behavior-preserving move).

Takes the live SimEngine as ``sim`` and reads/writes its state exactly as the
former ``SimEngine._apply_entity_separation`` method did. SimEngine keeps a
one-line delegating wrapper so callers/tests are unchanged.

This module must NOT import ``game.sim_engine`` at runtime (no import cycle): it
takes ``sim`` as a duck-typed parameter and only imports the same leaf helpers
the original method used.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # type-only; avoids a runtime import cycle with game.sim_engine
    from game.sim_engine import SimEngine


def apply_entity_separation(sim: "SimEngine", dt: float) -> None:
    # R2-B: Throttle to every 2 frames — sub-pixel pushes are dt-scaled,
    # so skipping alternating frames has zero visual impact.
    tick = getattr(sim, '_separation_tick', 0)
    sim._separation_tick = tick + 1
    if tick % 2 != 0:
        return

    import math

    min_dist_px = 16.0
    strength_per_sec = 250.0
    max_step = 120.0 * dt
    cell = min_dist_px

    alive = []
    for lst in (sim.heroes, sim.enemies, sim.peasants, sim.guards):
        alive.extend(e for e in lst if getattr(e, "is_alive", True))
    if sim.tax_collector and getattr(sim.tax_collector, "is_alive", True):
        alive.append(sim.tax_collector)
    if len(alive) < 2:
        return

    grid: dict[tuple[int, int], list[int]] = {}
    for idx, ent in enumerate(alive):
        if getattr(ent, "is_inside_building", False):
            continue
        cx = int(ent.x // cell)
        cy = int(ent.y // cell)
        key = (cx, cy)
        bucket = grid.get(key)
        if bucket is None:
            grid[key] = [idx]
        else:
            bucket.append(idx)

    for key, indices in grid.items():
        kx, ky = key
        neighbours: list[int] = []
        for ox in range(kx - 1, kx + 2):
            for oy in range(ky - 1, ky + 2):
                nb = grid.get((ox, oy))
                if nb is not None:
                    neighbours.extend(nb)

        for i in indices:
            ent = alive[i]
            dx_sum, dy_sum = 0.0, 0.0
            ex, ey = ent.x, ent.y
            for j in neighbours:
                if j == i:
                    continue
                other = alive[j]
                dx = ex - other.x
                dy = ey - other.y
                d2 = dx * dx + dy * dy
                if d2 < min_dist_px * min_dist_px and d2 > 1e-12:
                    dist = math.sqrt(d2)
                    push = (min_dist_px - dist) * strength_per_sec * dt / dist
                    dx_sum += dx * push
                    dy_sum += dy * push
            if dx_sum != 0 or dy_sum != 0:
                step = math.sqrt(dx_sum * dx_sum + dy_sum * dy_sum)
                if step > max_step:
                    scale = max_step / step
                    dx_sum *= scale
                    dy_sum *= scale
                ent.x += dx_sum
                ent.y += dy_sum
