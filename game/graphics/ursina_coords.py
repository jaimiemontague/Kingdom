"""Sim pixel ↔ Ursina floor-plane X/Z helpers (WK41 mechanical split)."""

SCALE = 32.0


def sim_px_to_world_xz(px_x: float, px_y: float) -> tuple[float, float]:
    """Map sim pixel coords to the X/Z floor (Y-up world)."""
    return px_x / SCALE, -px_y / SCALE


def px_to_world(px_x: float, px_y: float) -> tuple[float, float]:
    """Backward-compatible name: returns (world_x, world_z) for the floor plane."""
    return sim_px_to_world_xz(px_x, px_y)
