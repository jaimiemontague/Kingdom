"""Per-task duration ranges for building interactions (WK11). All rolls use get_rng for determinism."""

from __future__ import annotations

from typing import Any

# (min_seconds, max_seconds) per task key
TASK_DURATION_RANGES: dict[str, tuple[int, int]] = {
    "buy_potion": (8, 12),
    "buy_weapon": (12, 18),
    "buy_armor": (16, 22),
    "shopping": (8, 22),  # generic (marketplace/blacksmith) until purchase decided on exit
    "research": (10, 15),
    "rest_inn": (10, 20),
    "get_drink": (8, 15),
}


def roll_duration_seconds(task_key: str, rng: Any) -> int:
    """Roll a duration in seconds for the given task using the provided RNG. Returns min_s if task unknown."""
    entry = TASK_DURATION_RANGES.get(task_key)
    if not entry:
        min_s, max_s = 8, 12  # safe default
    else:
        min_s, max_s = entry
    return int(rng.randint(min_s, max_s))
