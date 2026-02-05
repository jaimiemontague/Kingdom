from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .events import EventBus
from .models import EventKind, GateResult, utc_now_iso


@dataclass
class GateRunner:
    repo_root: Path
    artifacts_dir: Path
    bus: EventBus

    def run_gate(self, *, sprint_id: str, round_id: str, gate: GateResult) -> GateResult:
        out_dir = self.artifacts_dir / sprint_id / "gates" / gate.gate_id
        out_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = out_dir / "stdout.txt"
        stderr_path = out_dir / "stderr.txt"

        self.bus.emit(
            EventKind.GATE_STARTED,
            f"gate started: {gate.gate_id}",
            sprint_id=sprint_id,
            round_id=round_id,
            data={"command": gate.command, "required": gate.required},
        )

        env = os.environ.copy()
        # Keep headless gates safe by default.
        env.setdefault("SDL_VIDEODRIVER", "dummy")
        env.setdefault("SDL_AUDIODRIVER", "dummy")

        started = utc_now_iso()
        with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
            completed = subprocess.run(gate.command, cwd=str(self.repo_root), env=env, stdout=out, stderr=err)

        finished = utc_now_iso()
        gate.started_ts = started
        gate.finished_ts = finished
        gate.exit_code = int(completed.returncode)
        gate.stdout_path = str(stdout_path)
        gate.stderr_path = str(stderr_path)

        self.bus.emit(
            EventKind.GATE_FINISHED,
            f"gate finished: {gate.gate_id} exit_code={gate.exit_code}",
            sprint_id=sprint_id,
            round_id=round_id,
            data={"exit_code": gate.exit_code, "stdout": gate.stdout_path, "stderr": gate.stderr_path},
        )
        return gate

