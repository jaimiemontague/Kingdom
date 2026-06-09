"""
Simulation time abstraction.

`now_ms()` is the **pause-frozen monotonic sim clock in ALL modes** (WK125).
`SimEngine.update()` is the single authoritative writer: every tick it advances an
accumulator by the (speed-scaled) frame dt and publishes it via `set_sim_now_ms`.
Because `update()` is skipped while paused (lifecycle returns False at multiplier 0
/ menu pause), the clock **freezes on pause** and **never jumps with app uptime or on
resume**. It does NOT fall back to the real wall clock — that fallback (when no value
has been published) only exists for the brief pre-first-`update()` construction window,
which `SimEngine.__init__` now closes by publishing 0 immediately.

Gameplay code should use `now_ms()` so all sim timestamps share one clock and stay
consistent across pause/resume and long sessions.

UI / rendering that needs **real wall-clock time that keeps advancing while paused**
(e.g. an input/conversation cooldown that must elapse during pause) must call
`pygame.time.get_ticks()` directly — see `game/engine.py` `send_player_message`. All
current UI/HUD/audio callers use `now_ms()` only as a delta vs another `now_ms()` stamp,
so pause-freezing those cosmetic timers is correct/expected.
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
    Publish the current pause-frozen sim time in milliseconds.

    `SimEngine.update()` is the sole production writer and calls this every tick in
    ALL modes (deterministic and shipped non-deterministic) with its monotonic
    accumulator, so `now_ms()` is the pause-frozen sim clock everywhere.

    Passing None resets to the construction-window fallback where `now_ms()` reads
    `pygame.time.get_ticks()`; production code does not do this (it would re-expose the
    WK125 wall-clock-vs-stale-stamp bug). It remains for tests that drive sim time
    manually and want to assert the fallback behavior.
    """
    global _SIM_NOW_MS
    _SIM_NOW_MS = None if now_ms is None else int(now_ms)


def now_ms() -> int:
    """Return the pause-frozen sim clock (the published `set_sim_now_ms` value).

    Falls back to `pygame.time.get_ticks()` ONLY before the first value is published
    (the pre-first-`update()` construction window, which `SimEngine.__init__` closes by
    publishing 0). UI wanting real wall-clock time that advances while paused must call
    `pygame.time.get_ticks()` directly, not this function.
    """
    if _SIM_NOW_MS is not None:
        return int(_SIM_NOW_MS)
    return int(pygame.time.get_ticks())







