from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from .agents import AgentProfile, LLMProvider, build_default_agent_profiles, provider_from_env
from .events import EventBus, EventSink
from .models import EventKind, RoundState, RoundStatus, SprintState, SprintStatus, utc_now_iso
from .policy import AutonomyContract, RoundDefinition, RoundId, default_contract
from .queueing import LaneQueue
from .state_store import StateStore
from .gates import GateRunner
from .git_ops import GitRunner
from .hooks import HookEvent, HookRegistry


@dataclass
class OrchestratorConfig:
    repo_root: Path
    contract: AutonomyContract

    # lanes
    max_concurrent_global: int = 4

    # Logging integration with your existing studio artifacts
    agent_logs_dir: Optional[Path] = None  # defaults to .cursor/plans/agent_logs

    # Release automation
    enable_auto_merge: bool = False
    automation_paused: bool = False


def _default_agent_logs_dir(repo_root: Path) -> Path:
    return repo_root / ".cursor" / "plans" / "agent_logs"


class Agent01Orchestrator:
    """
    MVP autonomous runner:
    - Creates/updates sprint + round state in .studio_gateway/state.json
    - Emits events to .studio_gateway/events.jsonl
    - Uses a provider (currently mock) to generate agent acknowledgements
    - Advances through R0..R5 as a deterministic state machine

    This intentionally does not attempt to implement code changes yet; it builds the
    orchestration spine first (so later “implementation agents” can be swapped in).
    """

    def __init__(self, cfg: OrchestratorConfig):
        self.cfg = cfg
        self.store = StateStore.default(repo_root=cfg.repo_root)
        self.bus = EventBus(sink=EventSink(self.store.paths.events_jsonl))
        self.queue = LaneQueue(max_concurrent_global=cfg.max_concurrent_global)

        self.profiles: Dict[str, AgentProfile] = build_default_agent_profiles(repo_root=cfg.repo_root)
        self.llm: LLMProvider = provider_from_env()

        self.agent_logs_dir = cfg.agent_logs_dir or _default_agent_logs_dir(cfg.repo_root)
        self.git = GitRunner(repo_root=cfg.repo_root)
        self.gates = GateRunner(repo_root=cfg.repo_root, artifacts_dir=self.store.paths.artifacts_root, bus=self.bus)
        self.hooks = HookRegistry()

    def _load(self) -> None:
        self.store.load()

    def _save(self) -> None:
        self.store.save()

    def _require_sprint(self, sprint_id: str) -> SprintState:
        s = self.store.get_sprint(sprint_id)
        if s is None:
            raise ValueError(f"unknown sprint_id: {sprint_id}")
        return s

    def start_sprint(self, sprint_id: str) -> None:
        self._load()
        s = self._require_sprint(sprint_id)
        if s.status in (SprintStatus.SUCCEEDED, SprintStatus.CANCELLED):
            raise ValueError(f"sprint is not runnable (status={s.status.value})")
        s.status = SprintStatus.RUNNING
        s.current_round = RoundId.R0_SETUP
        self._ensure_round_state(s, RoundId.R0_SETUP)
        self._save()
        self.bus.emit(EventKind.NOTE, "sprint started", sprint_id=sprint_id, data={"round": s.current_round.value})
        self.hooks.emit(HookEvent.SPRINT_START, {"sprint_id": sprint_id, "round": s.current_round.value})

    def step(self, sprint_id: str) -> None:
        """
        Advance the sprint by one step.

        In MVP:
        - Run one full round at a time.
        - After round completes, advance to the next round.
        """

        self._load()
        s = self._require_sprint(sprint_id)
        if s.status != SprintStatus.RUNNING:
            raise ValueError(f"sprint not running (status={s.status.value})")
        if s.current_round is None:
            s.current_round = RoundId.R0_SETUP

        rid = s.current_round
        self._run_round(s, rid)
        next_rid = self._next_round_id(rid)
        s.current_round = next_rid
        if next_rid is None:
            s.status = SprintStatus.SUCCEEDED
            self.bus.emit(EventKind.NOTE, "sprint succeeded (MVP)", sprint_id=sprint_id)
        else:
            self._ensure_round_state(s, next_rid)
        self._save()

    def run_to_completion(self, sprint_id: str) -> None:
        self.start_sprint(sprint_id)
        while True:
            self._load()
            s = self._require_sprint(sprint_id)
            if s.status != SprintStatus.RUNNING:
                break
            if s.current_round is None:
                break
            self.step(sprint_id)

    def _ensure_round_state(self, s: SprintState, rid: RoundId) -> RoundState:
        rd = self.cfg.contract.round(rid)
        if rid.value in s.rounds:
            return s.rounds[rid.value]
        rs = RoundState(round_id=rid, title=rd.title, status=RoundStatus.PENDING)
        s.rounds[rid.value] = rs
        return rs

    def _run_round(self, s: SprintState, rid: RoundId) -> None:
        rs = self._ensure_round_state(s, rid)
        if rs.status == RoundStatus.DONE:
            return

        rs.status = RoundStatus.IN_PROGRESS
        rs.started_ts = rs.started_ts or utc_now_iso()
        self.bus.emit(EventKind.ROUND_STARTED, f"round started: {rid.value}", sprint_id=s.sprint_id, round_id=rid.value)
        self.hooks.emit(HookEvent.ROUND_START, {"sprint_id": s.sprint_id, "round_id": rid.value})

        rd = self.cfg.contract.round(rid)
        # MVP: gather agent ACKs (mock LLM), write them into agent logs.
        acks = self._collect_required_acks(s, rid, rd)
        rs.notes.append(f"acks_collected={sorted(list(acks.keys()))}")

        # Gate execution: run required gates at R3 and again at R5 (release candidate).
        if rid in (RoundId.R3_BUILD_A_INTEGRATE, RoundId.R5_RELEASE_CANDIDATE):
            self._run_gates_for_round(s, rid)

        rs.status = RoundStatus.DONE
        rs.finished_ts = utc_now_iso()
        self.bus.emit(EventKind.ROUND_DONE, f"round done: {rid.value}", sprint_id=s.sprint_id, round_id=rid.value)
        self.hooks.emit(HookEvent.ROUND_DONE, {"sprint_id": s.sprint_id, "round_id": rid.value})

        # Auto-merge policy (MVP): on successful R5 with gates passing, commit changes and push.
        # For now we only commit/push if the working tree is dirty; this is a scaffold for future “agents implement code” rounds.
        if rid == RoundId.R5_RELEASE_CANDIDATE:
            self._attempt_release_merge(s)

    def _run_gates_for_round(self, s: SprintState, rid: RoundId) -> None:
        for gd in self.cfg.contract.gates:
            gate = s.gates.get(gd.gate_id)
            if gate is None:
                from .models import GateResult  # local import to avoid cycles

                gate = GateResult(
                    gate_id=gd.gate_id,
                    title=gd.title,
                    command=list(gd.command),
                    required=gd.required,
                    started_ts=utc_now_iso(),
                )
                s.gates[gd.gate_id] = gate

            gate = self.gates.run_gate(sprint_id=s.sprint_id, round_id=rid.value, gate=gate)
            s.gates[gd.gate_id] = gate
            self.hooks.emit(
                HookEvent.GATE_DONE,
                {"sprint_id": s.sprint_id, "round_id": rid.value, "gate_id": gate.gate_id, "exit_code": gate.exit_code},
            )

            if gate.required and (gate.exit_code or 0) != 0:
                s.status = SprintStatus.FAILED
                s.last_error = f"gate_failed:{gate.gate_id} exit_code={gate.exit_code}"
                self.bus.emit(
                    EventKind.ERROR,
                    "required gate failed; stopping sprint",
                    sprint_id=s.sprint_id,
                    round_id=rid.value,
                    data={"gate_id": gate.gate_id, "exit_code": gate.exit_code},
                )
                break

    def _attempt_release_merge(self, s: SprintState) -> None:
        if not self.cfg.enable_auto_merge or self.cfg.automation_paused:
            return
        # Only proceed if sprint still running/succeeded.
        if s.status == SprintStatus.FAILED:
            return

        # Ensure required gates passed.
        for gd in self.cfg.contract.gates:
            gr = s.gates.get(gd.gate_id)
            if gd.required and (gr is None or (gr.exit_code or 0) != 0):
                return

        # If repo isn't clean, commit and merge.
        try:
            if self.git.is_clean():
                return
        except Exception as e:
            self.bus.emit(EventKind.ERROR, "git status failed", sprint_id=s.sprint_id, data={"error": str(e)})
            return

        branch = f"sg/{s.sprint_id}"
        try:
            self.git.checkout_new_branch(branch, base="main")
            self.git.add_all()
            self.git.commit(f"studio_gateway: sprint {s.sprint_id} release candidate")
            self.git.merge_to_main_and_push(branch)
            self.bus.emit(EventKind.NOTE, "auto-merged and pushed to main", sprint_id=s.sprint_id, data={"branch": branch})
            self.hooks.emit(HookEvent.RELEASE_READY, {"sprint_id": s.sprint_id, "branch": branch})
        except Exception as e:
            self.bus.emit(EventKind.ERROR, "auto-merge failed", sprint_id=s.sprint_id, data={"error": str(e), "branch": branch})
    def _collect_required_acks(self, s: SprintState, rid: RoundId, rd: RoundDefinition) -> Dict[str, str]:
        acks: Dict[str, str] = {}
        for agent_id in rd.required_acks:
            # Lane: serialize per agent per sprint.
            lane = f"session:{agent_id}:{s.sprint_id}"
            system = f"You are {agent_id}. Follow your agent card. Reply in required format."
            prompt = (
                f"Sprint: {s.sprint_id}\n"
                f"Round: {rid.value} — {rd.title}\n"
                f"Purpose: {rd.purpose}\n\n"
                "Please ACK PM decisions for this round and list blockers (max 3).\n"
            )

            def _job(agent_id: str = agent_id) -> str:
                return self.llm.complete(system=system, prompt=prompt)

            jr = self.queue.submit(lane, _job)
            if not jr.ok:
                self.bus.emit(
                    EventKind.ERROR,
                    f"agent ack failed: {agent_id}",
                    sprint_id=s.sprint_id,
                    round_id=rid.value,
                    data={"error": jr.error},
                )
                acks[agent_id] = f"ERROR: {jr.error}"
                continue
            text = str(jr.value or "")
            acks[agent_id] = text
            self._write_agent_log_ack(agent_id=agent_id, sprint_id=s.sprint_id, round_id=rid.value, prompt=prompt, response=text)
        return acks

    def _write_agent_log_ack(self, *, agent_id: str, sprint_id: str, round_id: str, prompt: str, response: str) -> None:
        """
        Minimal writer that appends an entry to the agent's JSON log file.

        We keep this intentionally lightweight; later iterations can adopt your full
        schema v2.0 template for richer fields.
        """

        self.agent_logs_dir.mkdir(parents=True, exist_ok=True)
        path = self.agent_logs_dir / f"{agent_id}_AUTO.json"
        entry = {
            "sprint_id": sprint_id,
            "round_id": round_id,
            "ts": utc_now_iso(),
            "prompt": prompt,
            "response": response,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    def _next_round_id(self, rid: RoundId) -> Optional[RoundId]:
        order = [r.round_id for r in self.cfg.contract.rounds]
        try:
            idx = order.index(rid)
        except ValueError:
            return None
        if idx + 1 >= len(order):
            return None
        return order[idx + 1]


def default_orchestrator(*, repo_root: Path, cfg_override: OrchestratorConfig | None = None) -> Agent01Orchestrator:
    contract = default_contract()
    cfg = cfg_override or OrchestratorConfig(repo_root=repo_root, contract=contract)
    return Agent01Orchestrator(cfg)

