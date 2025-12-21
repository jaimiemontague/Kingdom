"""
Thin, stable data contracts for UI/AI inspection.

These are intentionally small "struct-like" dataclasses so:
- gameplay systems can share data without tight coupling or import cycles
- state is easy to serialize later (save/load + future MP boundaries)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass(slots=True)
class HeroDecisionRecord:
    """
    A single, last-known decision snapshot for a hero.

    Keep this light: it's meant for UI/debugging and "why did you do that?" clarity,
    not for full replay logging.
    """

    action: str
    reason: str
    at_ms: int
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, now_ms: Optional[int] = None) -> dict[str, Any]:
        d = asdict(self)
        if now_ms is not None:
            try:
                d["age_ms"] = max(0, int(now_ms) - int(self.at_ms))
            except Exception:
                d["age_ms"] = 0
        return d


@dataclass(slots=True)
class HeroIntentSnapshot:
    """
    A small UI/AI-facing view of a hero's current intent + last decision.
    """

    intent: str
    last_decision: Optional[HeroDecisionRecord] = None

    def to_dict(self, now_ms: Optional[int] = None) -> dict[str, Any]:
        return {
            "intent": str(self.intent),
            "last_decision": None if self.last_decision is None else self.last_decision.to_dict(now_ms=now_ms),
        }


@dataclass(slots=True)
class BountyEvalSnapshot:
    """
    A small UI-facing evaluation of a bounty.

    This is deterministic-friendly: no wall-clock, no RNG.
    """

    bounty_id: int
    responders: int
    attractiveness_score: float
    attractiveness_tier: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "bounty_id": int(self.bounty_id),
            "responders": int(self.responders),
            "attractiveness_score": float(self.attractiveness_score),
            "attractiveness_tier": str(self.attractiveness_tier),
        }


