from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class HookEvent(str, Enum):
    SPRINT_START = "sprint_start"
    ROUND_START = "round_start"
    ROUND_DONE = "round_done"
    GATE_START = "gate_start"
    GATE_DONE = "gate_done"
    RELEASE_READY = "release_ready"


HookHandler = Callable[[Dict[str, Any]], None]


@dataclass
class HookRegistry:
    """
    Minimal plugin/hook surface.

    Future expansion points:
    - load hooks from `studio_gateway/hooks/*.py` or configured directories
    - add enable/disable + requirements metadata (OpenClaw-style)
    """

    handlers: Dict[HookEvent, List[HookHandler]]

    def __init__(self) -> None:
        self.handlers = {e: [] for e in HookEvent}

    def register(self, event: HookEvent, handler: HookHandler) -> None:
        self.handlers[event].append(handler)

    def emit(self, event: HookEvent, payload: Dict[str, Any]) -> None:
        for h in list(self.handlers.get(event, [])):
            try:
                h(payload)
            except Exception:
                # Hooks are non-fatal by default in MVP.
                continue

