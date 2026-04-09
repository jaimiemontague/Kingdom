"""Per-task duration ranges for building interactions (WK11; WK24 tuned shopping/buy_potion). All rolls use get_rng for determinism."""

from __future__ import annotations

from typing import Any

# (min_seconds, max_seconds) per task key (WK24-BUG-007: buy_potion / shopping targets in wk24_ui_and_renderer_polish.plan.md)
TASK_DURATION_RANGES: dict[str, tuple[int, int]] = {
    "buy_potion": (3, 6),
    "buy_weapon": (6, 12),
    "buy_armor": (8, 14),
    "shopping": (4, 8),  # blacksmith / non-marketplace shopping until purchase on exit
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
