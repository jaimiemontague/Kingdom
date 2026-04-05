"""
WK20 — Ursina input debug telemetry (Agent 12 / Tools).

Activated when environment variable KINGDOM_URSINA_DEBUG_INPUT=1.
Emits a single WK20_INPUT line per left-mouse-button press (rising edge).
Telemetry only; does not touch simulation state.
"""

from __future__ import annotations

import os

ENV_KEY = "KINGDOM_URSINA_DEBUG_INPUT"


def is_ursina_debug_input_enabled() -> bool:
    return os.environ.get(ENV_KEY, "").strip() == "1"


def print_wk20_input_line(
    *,
    raw_sx: float,
    raw_sy: float,
    pygame_x: int,
    pygame_y: int,
    ui_hit: str | int | None = None,
    world_xz: tuple[float, float] | None = None,
    tile: tuple[int, int] | None = None,
) -> None:
    """Emit one structured WK20_INPUT line to stdout."""

    def fmt_wxz(t: tuple[float, float] | None) -> str:
        if t is None:
            return "(na,na)"
        wx, wz = t
        return f"({wx:.4f},{wz:.4f})"

    def fmt_tile(t: tuple[int, int] | None) -> str:
        if t is None:
            return "(na,na)"
        return f"({t[0]},{t[1]})"

    uh = "na" if ui_hit is None else str(ui_hit)
    line = (
        f"WK20_INPUT raw_ursina=({raw_sx:.6f},{raw_sy:.6f}) "
        f"pygame=({pygame_x},{pygame_y}) ui_hit={uh} "
        f"world_xz={fmt_wxz(world_xz)} tile={fmt_tile(tile)}"
    )
    print(line, flush=True)


def maybe_print_wk20_input_on_lmb(
    *,
    mouse_left_pressed_edge: bool,
    raw_sx: float,
    raw_sy: float,
    pygame_xy: tuple[int, int],
    ui_hit: str | int | None = None,
    world_xz: tuple[float, float] | None = None,
    tile: tuple[int, int] | None = None,
) -> None:
    """If env is set and this is the first frame of LMB down, print one WK20_INPUT line."""
    if not mouse_left_pressed_edge:
        return
    if not is_ursina_debug_input_enabled():
        return
    print_wk20_input_line(
        raw_sx=raw_sx,
        raw_sy=raw_sy,
        pygame_x=pygame_xy[0],
        pygame_y=pygame_xy[1],
        ui_hit=ui_hit,
        world_xz=world_xz,
        tile=tile,
    )
