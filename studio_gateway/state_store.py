from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .models import SprintState, sprint_from_dict, to_jsonable


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


@dataclass
class StorePaths:
    root: Path

    @property
    def state_json(self) -> Path:
        return self.root / "state.json"

    @property
    def events_jsonl(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def artifacts_root(self) -> Path:
        return self.root / "artifacts"


class StateStore:
    """
    File-backed store.

    - state.json: canonical control-plane state (sprints, rounds, gate results)
    - events.jsonl: append-only event stream
    - artifacts/: stdout/stderr bundles and round artifacts
    """

    def __init__(self, paths: StorePaths):
        self.paths = paths
        self._sprints: Dict[str, SprintState] = {}

    @classmethod
    def default(cls, *, repo_root: Path) -> "StateStore":
        return cls(StorePaths(root=repo_root / ".studio_gateway"))

    def load(self) -> None:
        p = self.paths.state_json
        if not p.exists():
            self._sprints = {}
            return
        raw = json.loads(p.read_text(encoding="utf-8"))
        sprints: Dict[str, SprintState] = {}
        for sid, sd in (raw.get("sprints") or {}).items():
            sprints[sid] = sprint_from_dict(sd)
        self._sprints = sprints

    def save(self) -> None:
        payload = {"sprints": {sid: to_jsonable(s) for sid, s in self._sprints.items()}}
        _atomic_write_text(self.paths.state_json, json.dumps(payload, indent=2, sort_keys=True))

    def get_sprint(self, sprint_id: str) -> Optional[SprintState]:
        return self._sprints.get(sprint_id)

    def upsert_sprint(self, s: SprintState) -> None:
        self._sprints[s.sprint_id] = s

    def list_sprints(self) -> Dict[str, SprintState]:
        return dict(self._sprints)

