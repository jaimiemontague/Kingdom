from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .models import Event, EventKind, to_jsonable, utc_now_iso


@dataclass
class EventSink:
    path: Path

    def append(self, e: Event) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(to_jsonable(e), sort_keys=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def tail(self, *, max_lines: int = 200) -> list[Event]:
        if not self.path.exists():
            return []
        # Simple tail for small files; acceptable for MVP.
        lines = self.path.read_text(encoding="utf-8").splitlines()[-max_lines:]
        out: list[Event] = []
        for ln in lines:
            try:
                d = json.loads(ln)
                out.append(
                    Event(
                        ts=d.get("ts") or utc_now_iso(),
                        kind=EventKind(d.get("kind") or EventKind.NOTE.value),
                        message=d.get("message") or "",
                        sprint_id=d.get("sprint_id"),
                        round_id=d.get("round_id"),
                        data=dict(d.get("data") or {}),
                    )
                )
            except Exception:
                continue
        return out


class EventBus:
    def __init__(self, *, sink: EventSink):
        self._sink = sink

    def emit(
        self,
        kind: EventKind,
        message: str,
        *,
        sprint_id: Optional[str] = None,
        round_id: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> None:
        self._sink.append(
            Event(
                ts=utc_now_iso(),
                kind=kind,
                message=message,
                sprint_id=sprint_id,
                round_id=round_id,
                data=data or {},
            )
        )

    def recent(self, *, max_lines: int = 200) -> list[Event]:
        return self._sink.tail(max_lines=max_lines)

