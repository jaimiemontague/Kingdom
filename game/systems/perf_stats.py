"""
Tiny global perf counters for diagnosing runtime slowdowns.

This intentionally stays very lightweight (ints + floats), so it can be left enabled.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _PathStats:
    calls: int = 0
    failures: int = 0
    total_ms: float = 0.0


pathfinding = _PathStats()


def reset_pathfinding() -> None:
    pathfinding.calls = 0
    pathfinding.failures = 0
    pathfinding.total_ms = 0.0










