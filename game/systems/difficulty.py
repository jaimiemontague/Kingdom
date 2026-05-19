"""
WK60 Feature 8: Difficulty system (Easy / Normal / Hard).

Provides runtime-adjustable difficulty multipliers that affect monster-related
values only (spawn rates, enemy stats, wave sizes). Economy values (gold costs,
hero costs, building prices, bounty costs) are never affected.

Usage:
    from game.systems.difficulty import DifficultySystem, DifficultyLevel
    difficulty = DifficultySystem()
    mult = difficulty.get_multiplier("enemy_hp")       # 1.0 on Normal
    difficulty.set_difficulty(DifficultyLevel.HARD)
    mult = difficulty.get_multiplier("enemy_hp")       # 1.3 on Hard
"""

from __future__ import annotations

from enum import Enum

from config import DIFFICULTY as _cfg, DEV_MODE as _DEV_MODE


class DifficultyLevel(str, Enum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


# Multiplier tables keyed by difficulty level.
# Keys: spawn_interval, enemies_per_wave, enemy_hp, enemy_damage, wave_event_count
_MULTIPLIERS: dict[DifficultyLevel, dict[str, float]] = {
    DifficultyLevel.EASY: {
        "spawn_interval": _cfg.easy_spawn_interval_mult,      # 1.5 — 50% slower spawns
        "enemies_per_wave": _cfg.easy_enemy_count_mult,        # 0.6 — 40% fewer enemies
        "enemy_hp": _cfg.easy_enemy_hp_mult,                   # 0.7 — 30% less HP
        "enemy_damage": _cfg.easy_enemy_damage_mult,           # 0.7 — 30% less damage
        "wave_event_count": _cfg.easy_enemy_count_mult,        # 0.6 — 40% fewer enemies in wave events
    },
    DifficultyLevel.NORMAL: {
        "spawn_interval": 1.0,
        "enemies_per_wave": 1.0,
        "enemy_hp": 1.0,
        "enemy_damage": 1.0,
        "wave_event_count": 1.0,
    },
    DifficultyLevel.HARD: {
        "spawn_interval": _cfg.hard_spawn_interval_mult,      # 0.7 — 30% faster spawns
        "enemies_per_wave": _cfg.hard_enemy_count_mult,        # 1.5 — 50% more enemies
        "enemy_hp": _cfg.hard_enemy_hp_mult,                   # 1.3 — 30% more HP
        "enemy_damage": _cfg.hard_enemy_damage_mult,           # 1.3 — 30% more damage
        "wave_event_count": _cfg.hard_enemy_count_mult,        # 1.5 — 50% more enemies in wave events
    },
}


class DifficultySystem:
    """
    Runtime difficulty manager.

    - ``get_multiplier(key)`` returns the active multiplier for a given stat key.
    - ``set_difficulty(level)`` changes difficulty (unless locked).
    - ``lock_difficulty()`` prevents further changes.
    """

    def __init__(self, default_level: DifficultyLevel | None = None):
        if default_level is None:
            if _DEV_MODE:
                # WK60 Feature 9: dev mode defaults to Easy
                default_level = DifficultyLevel.EASY
            else:
                _map = {"easy": DifficultyLevel.EASY, "normal": DifficultyLevel.NORMAL, "hard": DifficultyLevel.HARD}
                default_level = _map.get(_cfg.default_difficulty, DifficultyLevel.NORMAL)
        self.current: DifficultyLevel = default_level
        self.locked: bool = False

    def get_multiplier(self, key: str) -> float:
        """Return the multiplier for *key* at the current difficulty level.

        Unknown keys return 1.0 (no scaling).
        """
        table = _MULTIPLIERS.get(self.current)
        if table is None:
            return 1.0
        return table.get(key, 1.0)

    def set_difficulty(self, level: DifficultyLevel) -> bool:
        """Change difficulty. Returns False if locked."""
        if self.locked:
            return False
        self.current = level
        return True

    def lock_difficulty(self) -> None:
        """Lock difficulty so it cannot be changed for the rest of the game."""
        self.locked = True
