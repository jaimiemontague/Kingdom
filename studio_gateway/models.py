from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from .policy import RoundId


class SprintStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"


class RoundStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class EventKind(str, Enum):
    SPRINT_CREATED = "sprint_created"
    ROUND_STARTED = "round_started"
    ROUND_DONE = "round_done"
    GATE_STARTED = "gate_started"
    GATE_FINISHED = "gate_finished"
    NOTE = "note"
    ERROR = "error"


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass
class Event:
    ts: str
    kind: EventKind
    message: str
    sprint_id: Optional[str] = None
    round_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GateResult:
    gate_id: str
    title: str
    command: list[str]
    required: bool
    started_ts: str
    finished_ts: Optional[str] = None
    exit_code: Optional[int] = None
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None


@dataclass
class TaskState:
    task_id: str
    title: str
    owner_agent: str
    status: str = "pending"  # pending|in_progress|blocked|done|cancelled
    created_ts: str = field(default_factory=utc_now_iso)
    updated_ts: str = field(default_factory=utc_now_iso)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoundState:
    round_id: RoundId
    title: str
    status: RoundStatus = RoundStatus.PENDING
    started_ts: Optional[str] = None
    finished_ts: Optional[str] = None
    notes: list[str] = field(default_factory=list)
    tasks: Dict[str, TaskState] = field(default_factory=dict)  # key: task_id


@dataclass
class SprintState:
    sprint_id: str
    title: str
    created_ts: str
    status: SprintStatus = SprintStatus.CREATED
    current_round: Optional[RoundId] = None
    rounds: Dict[str, RoundState] = field(default_factory=dict)  # key: RoundId.value
    gates: Dict[str, GateResult] = field(default_factory=dict)  # key: gate_id
    artifacts_dir: Optional[str] = None
    last_error: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def ensure_round(self, rs: RoundState) -> None:
        self.rounds.setdefault(rs.round_id.value, rs)


def to_jsonable(obj: Any) -> Any:
    # Dataclasses
    if hasattr(obj, "__dataclass_fields__"):
        d = asdict(obj)
        # Preserve Enum string values
        if isinstance(obj, (SprintState, RoundState, GateResult, Event)):
            pass
        return d
    # Enums
    if isinstance(obj, Enum):
        return obj.value
    # Dict/list primitives
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_jsonable(v) for v in obj]
    return obj


def sprint_from_dict(d: Dict[str, Any]) -> SprintState:
    s = SprintState(
        sprint_id=d["sprint_id"],
        title=d.get("title", d["sprint_id"]),
        created_ts=d["created_ts"],
        status=SprintStatus(d.get("status", SprintStatus.CREATED.value)),
        current_round=RoundId(d["current_round"]) if d.get("current_round") else None,
        rounds={},
        gates={},
        artifacts_dir=d.get("artifacts_dir"),
        last_error=d.get("last_error"),
        meta=d.get("meta", {}),
    )

    for rid, rd in (d.get("rounds") or {}).items():
        rs = RoundState(
            round_id=RoundId(rd["round_id"]),
            title=rd.get("title", rid),
            status=RoundStatus(rd.get("status", RoundStatus.PENDING.value)),
            started_ts=rd.get("started_ts"),
            finished_ts=rd.get("finished_ts"),
            notes=list(rd.get("notes") or []),
            tasks={},
        )
        for tid, td in (rd.get("tasks") or {}).items():
            rs.tasks[tid] = TaskState(
                task_id=td.get("task_id", tid),
                title=td.get("title", tid),
                owner_agent=td.get("owner_agent", "agent_01"),
                status=td.get("status", "pending"),
                created_ts=td.get("created_ts") or utc_now_iso(),
                updated_ts=td.get("updated_ts") or td.get("created_ts") or utc_now_iso(),
                details=dict(td.get("details") or {}),
            )
        s.rounds[rid] = rs

    for gid, gd in (d.get("gates") or {}).items():
        gr = GateResult(
            gate_id=gd["gate_id"],
            title=gd.get("title", gid),
            command=list(gd.get("command") or []),
            required=bool(gd.get("required", True)),
            started_ts=gd["started_ts"],
            finished_ts=gd.get("finished_ts"),
            exit_code=gd.get("exit_code"),
            stdout_path=gd.get("stdout_path"),
            stderr_path=gd.get("stderr_path"),
        )
        s.gates[gid] = gr

    return s

