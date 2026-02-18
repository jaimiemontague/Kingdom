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
_TIME_MULTIPLIER: float = 1.0


def set_time_multiplier(m: float) -> None:
    """Set simulation speed multiplier. Clamped to [0.0, 4.0]. Applied at engine level."""
    global _TIME_MULTIPLIER
    _TIME_MULTIPLIER = max(0.0, min(4.0, float(m)))


def get_time_multiplier() -> float:
    """Return current simulation speed multiplier (0 = paused, 1 = normal/fast)."""
    return _TIME_MULTIPLIER


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







