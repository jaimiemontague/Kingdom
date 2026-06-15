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


@dataclass(slots=True, frozen=True)
class QuestChainHistorySummary:
    """Small immutable history record for an active quest chain."""

    event: str
    phase_id: str = ""
    phase_title: str = ""
    status: str = ""
    hero_id: str | None = None
    target_id: str = ""
    target_name: str = ""
    target_position: tuple[float, float] | None = None
    at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class QuestChainPhaseSnapshot:
    """Primitive read model for one phase in a quest-chain timeline."""

    phase_id: str
    title: str
    objective_type: str
    status: str
    assigned_hero_id: str | None = None
    target_id: str = ""
    target_name: str = ""
    target_position: tuple[float, float] | None = None
    history: tuple[QuestChainHistorySummary, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class QuestChainSnapshot:
    """Immutable, read-only chain snapshot for AI/view consumers."""

    chain_id: int | str
    chain_type: str
    name: str
    status: str
    assigned_hero_id: str | None = None
    current_phase_id: str = ""
    current_phase_title: str = ""
    current_objective_type: str = ""
    target_id: str = ""
    target_name: str = ""
    target_position: tuple[float, float] | None = None
    phases: tuple[QuestChainPhaseSnapshot, ...] = ()
    history: tuple[QuestChainHistorySummary, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class HeroCaptureState:
    """Primitive capture state for one hero held by a named boss family."""

    hero_id: str
    hero_name: str
    captor_boss_id: str = ""
    captor_boss_name: str = ""
    captor_boss_type: str = ""
    location_id: str = ""
    location_name: str = ""
    source_chain_id: str = ""
    source_chain_type: str = ""
    captured_at_ms: int = 0
    status: str = "captured"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class RescueOpportunitySnapshot:
    """Primitive read model for an active rescue opportunity."""

    rescue_id: str
    captured_hero_id: str
    captured_hero_name: str
    captor_boss_id: str = ""
    captor_boss_name: str = ""
    captor_boss_type: str = ""
    target_location_id: str = ""
    target_location_name: str = ""
    current_phase_id: str = ""
    current_phase_title: str = ""
    source_chain_id: str = ""
    source_chain_type: str = ""
    status: str = "active"
    offered_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class BossKillMemory:
    """Primitive memory record for a named boss killing a hero."""

    boss_id: str
    boss_name: str
    boss_type: str
    fallen_hero_id: str
    fallen_hero_name: str
    location_id: str = ""
    location_name: str = ""
    killed_at_ms: int = 0
    revenge_chain_id: str = ""
    status: str = "remembered"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class RevengeOpportunitySnapshot:
    """Primitive read model for a revenge opportunity against a named boss."""

    revenge_id: str
    boss_id: str
    boss_name: str
    boss_type: str
    fallen_hero_id: str
    fallen_hero_name: str
    target_location_id: str = ""
    target_location_name: str = ""
    current_phase_id: str = ""
    current_phase_title: str = ""
    revenge_chain_id: str = ""
    status: str = "active"
    offered_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class BossMemorySummary:
    """Small immutable memory record for an active boss encounter."""

    event: str
    hero_id: str | None = None
    hero_name: str = ""
    detail: str = ""
    at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class BossEncounterSnapshot:
    """Primitive read model for one active boss encounter."""

    boss_id: str
    boss_type: str
    name: str
    status: str
    current_phase: str
    current_phase_title: str
    hp_pct: float
    position: tuple[float, float] | None = None
    target_hero_id: str | None = None
    latest_telegraph: str = ""
    memory_summaries: tuple[BossMemorySummary, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class EliteEncounterSnapshot:
    """Primitive read model for one active elite enemy."""

    elite_id: str
    base_type: str
    name: str
    status: str
    affixes: tuple[str, ...] = ()
    position: tuple[float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
