"""Typed AI task contracts (WK64, audit item 15).

Replaces the stringly-typed ``hero.target`` dict with a typed ``HeroTask``
dataclass and a ``TargetType`` enum. During WK64 these COEXIST with the legacy
dict shape:

  * Behaviors CONSTRUCT a HeroTask (type-safe, validated) and then call
    ``assign_hero_task(hero, task)``, which stores ``hero.target = task.to_dict()``.
    ``hero.target`` therefore stays a plain dict everywhere -- no existing
    reader breaks.
  * Arrival handlers CONSUME via ``coerce_task(hero.target)`` to recover a typed
    HeroTask from the dict, then read ``task.payload[...]``.

Critical rule: NEVER store a HeroTask object on ``hero.target``. ~30 call sites
do ``isinstance(hero.target, dict)`` and would silently misbehave. The dict is
the single source of truth; HeroTask is a transient view at the construction
and consumption boundaries.

DO NOT remove the dict compatibility path in this sprint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TargetType(str, Enum):
    """Canonical hero task/target kinds.

    Values MUST equal the legacy ``hero.target["type"]`` strings so ``to_dict``/
    ``from_dict`` round-trip without changing any consumer that still reads the
    dict. This is the complete set found in the WK64 codebase audit -- do not
    rename or remove values.
    """

    BOUNTY = "bounty"
    DIRECT_PROMPT = "direct_prompt"
    VISIT_POI = "visit_poi"
    GOING_HOME = "going_home"
    SHOPPING = "shopping"
    REST_INN = "rest_inn"
    GET_DRINK = "get_drink"
    BUY_MEAL = "buy_meal"
    PATROL = "patrol"
    EXPLORE_FRONTIER = "explore_frontier"
    DEFEND_CASTLE = "defend_castle"
    DEFEND_NEUTRAL = "defend_neutral"
    JOURNEY_EXPLORE = "journey_explore"

    @classmethod
    def from_str(cls, value: str) -> Optional["TargetType"]:
        """Return the matching member, or None if ``value`` is unknown."""
        try:
            return cls(value)
        except ValueError:
            return None


@dataclass(slots=True)
class HeroTask:
    """Typed hero task. Coexists with the legacy dict shape during WK64.

    Attributes:
        type: the TargetType.
        target_id: stable id of the target entity if applicable (else None).
        target_ref: best-effort live object reference (headless tests / fallback).
        started_ms: sim time the task started (0 if the legacy dict omitted it).
        payload: all type-specific extra keys the legacy dict carried, verbatim.
                 e.g. BUY_MEAL -> {"food_stand": <building>}
                      SHOPPING -> {"item", "marketplace", "blacksmith", "shop_building"}
    """

    type: TargetType
    target_id: str | int | None = None
    target_ref: object | None = None
    started_ms: int = 0
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Render to the legacy dict shape that existing consumers read."""
        d: dict[str, Any] = {"type": self.type.value}
        if self.started_ms:
            d["started_ms"] = int(self.started_ms)
        # payload carries the type-specific keys exactly as the old dict did.
        d.update(self.payload)
        return d

    @classmethod
    def from_dict(cls, d: Any) -> "HeroTask | None":
        """Build a HeroTask from a legacy dict. Returns None for non-task input."""
        if not isinstance(d, dict):
            return None
        tt = TargetType.from_str(str(d.get("type", "")))
        if tt is None:
            return None
        payload = {k: v for k, v in d.items() if k not in ("type", "started_ms")}
        return cls(
            type=tt,
            started_ms=int(d.get("started_ms", 0) or 0),
            payload=payload,
        )


def coerce_task(target: Any) -> HeroTask | None:
    """Normalize whatever is on ``hero.target`` into a HeroTask, or None.

    Returns:
        * a HeroTask if ``target`` is already a HeroTask, or a legacy task dict.
        * None if ``target`` is None, or a live entity object (enemy / lair /
          building) -- those are combat targets, NOT tasks, and must be handled
          by the combat path, not the arrival registry.
    """
    if isinstance(target, HeroTask):
        return target
    if isinstance(target, dict):
        return HeroTask.from_dict(target)
    return None


def assign_hero_task(hero: Any, task: HeroTask) -> None:
    """Store a typed task on the hero as the legacy dict (single source of truth).

    This is the ONLY sanctioned way to put a HeroTask onto a hero. It deliberately
    serializes to a dict so every existing ``isinstance(hero.target, dict)`` reader
    keeps working.
    """
    hero.target = task.to_dict()
