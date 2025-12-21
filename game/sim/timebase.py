"""
Simulation time abstraction.

Gameplay code should prefer `now_ms()` over `pygame.time.get_ticks()` so we can:
- drive time from a deterministic fixed-tick clock in the future (lockstep-ready)
- keep UI / rendering free to use real wall-clock time when appropriate
"""

from __future__ import annotations

from typing import Optional

import pygame

_SIM_NOW_MS: Optional[int] = None


def set_sim_now_ms(now_ms: Optional[int]) -> None:
    """
    Set the current simulation time in milliseconds.

    If set to None, `now_ms()` falls back to pygame's real-time ticks.
    """
    global _SIM_NOW_MS
    _SIM_NOW_MS = None if now_ms is None else int(now_ms)


def now_ms() -> int:
    """Return sim time (if provided), otherwise pygame's wall-clock-ish ticks."""
    if _SIM_NOW_MS is not None:
        return int(_SIM_NOW_MS)
    return int(pygame.time.get_ticks())



