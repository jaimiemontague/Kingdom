"""
Autonomy contract for the Studio Gateway.

This encodes the default round taxonomy (R0..R5), time budgets, stop conditions,
and escalation policy in a machine-readable way so the orchestrator can enforce it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Sequence


class EscalationKind(str, Enum):
    """When Agent 01 should ask the human instead of deciding."""

    DIRECTIONAL = "directional"  # vision, scope cuts, major tradeoffs, go/no-go
    EXECUTIONAL = "executional"  # should be answerable by Agent 01


class RoundId(str, Enum):
    R0_SETUP = "R0_SETUP"
    R1_CONTRACTS = "R1_CONTRACTS"
    R2_PLAN_CONFIRM = "R2_PLAN_CONFIRM"
    R3_BUILD_A_INTEGRATE = "R3_BUILD_A_INTEGRATE"
    R4_BUILD_B_POLISH = "R4_BUILD_B_POLISH"
    R5_RELEASE_CANDIDATE = "R5_RELEASE_CANDIDATE"


@dataclass(frozen=True)
class RoundDefinition:
    round_id: RoundId
    title: str
    purpose: str
    required_agents: tuple[str, ...]
    min_minutes: int
    max_minutes: int
    required_acks: tuple[str, ...] = ()


@dataclass(frozen=True)
class StopConditions:
    """
    Encodes what “good enough” means.

    These are evaluated by the orchestrator at R5 and can also be used as early
    exit criteria for smaller sprints.
    """

    acceptance_criteria_met: bool = True
    required_gates_passed: bool = True
    no_open_p0_p1_bugs: bool = True
    final_report_ready: bool = True


@dataclass(frozen=True)
class GateDefinition:
    gate_id: str
    title: str
    command: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class AutonomyContract:
    """
    The default “sprint loop” contract.

    - Enforces at least 5 rounds (R0..R5).
    - Provides time budgets so total work is bounded (target 30–60 minutes).
    """

    rounds: tuple[RoundDefinition, ...] = field(default_factory=tuple)
    gates: tuple[GateDefinition, ...] = field(default_factory=tuple)
    stop: StopConditions = field(default_factory=StopConditions)

    def round(self, rid: RoundId) -> RoundDefinition:
        for r in self.rounds:
            if r.round_id == rid:
                return r
        raise KeyError(rid)


def default_contract() -> AutonomyContract:
    # NOTE: Agent ids are stringly-typed to stay compatible with your existing studio naming.
    rounds: list[RoundDefinition] = [
        RoundDefinition(
            round_id=RoundId.R0_SETUP,
            title="Setup",
            purpose="Create sprint id, roster (Active/Consult/Silent), DoD gates, and initial brief.",
            required_agents=("agent_01",),
            min_minutes=2,
            max_minutes=6,
            required_acks=(),
        ),
        RoundDefinition(
            round_id=RoundId.R1_CONTRACTS,
            title="Contracts",
            purpose="Acceptance criteria, interfaces/contracts, repro harness, risks; PM locks decisions.",
            required_agents=("agent_01", "agent_02", "agent_03", "agent_11", "agent_12"),
            min_minutes=8,
            max_minutes=15,
            required_acks=("agent_02", "agent_03", "agent_11", "agent_12"),
        ),
        RoundDefinition(
            round_id=RoundId.R2_PLAN_CONFIRM,
            title="Implementation plan confirmation",
            purpose="Implementers confirm files, tests, integration order, and rollback plan.",
            required_agents=("agent_01",),
            min_minutes=4,
            max_minutes=10,
        ),
        RoundDefinition(
            round_id=RoundId.R3_BUILD_A_INTEGRATE,
            title="Build A: implementation + integration",
            purpose="Implement, integrate, run gates; fail-fast on regressions.",
            required_agents=("agent_01",),
            min_minutes=8,
            max_minutes=18,
        ),
        RoundDefinition(
            round_id=RoundId.R4_BUILD_B_POLISH,
            title="Build B: polish / edge cases",
            purpose="Second pass for regressions, UX polish, docs updates; keep scope tight.",
            required_agents=("agent_01",),
            min_minutes=4,
            max_minutes=12,
        ),
        RoundDefinition(
            round_id=RoundId.R5_RELEASE_CANDIDATE,
            title="Release candidate",
            purpose="Final gates, patch notes/versioning rules, and ship-candidate report.",
            required_agents=("agent_01",),
            min_minutes=4,
            max_minutes=10,
        ),
    ]

    # Default gates reuse your existing tooling.
    gates: list[GateDefinition] = [
        GateDefinition(
            gate_id="qa_smoke_quick",
            title="QA smoke (quick)",
            command=("python", "tools/qa_smoke.py", "--quick"),
            required=True,
        ),
    ]

    return AutonomyContract(rounds=tuple(rounds), gates=tuple(gates), stop=StopConditions())


def total_budget_minutes(contract: AutonomyContract, *, use_max: bool) -> int:
    minutes = 0
    for r in contract.rounds:
        minutes += r.max_minutes if use_max else r.min_minutes
    return minutes


def validate_contract(contract: AutonomyContract) -> None:
    rids = [r.round_id for r in contract.rounds]
    if len(rids) != len(set(rids)):
        raise ValueError("AutonomyContract.rounds contains duplicate round_id values")
    if len(rids) < 5:
        raise ValueError("AutonomyContract must contain at least 5 rounds")
    if not contract.gates:
        raise ValueError("AutonomyContract must include at least one gate definition")

