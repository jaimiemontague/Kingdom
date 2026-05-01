"""WK51: UI-only pinned hero slot (presentation layer — never touched by sim code)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

PIN_FALLEN_DISPLAY_MS = 10_000


@dataclass
class PinSlot:
    """UI-only pinned-hero slot."""

    hero_id: Optional[str] = None
    pinned_at_ms: int = 0
    fallen_since_ms: Optional[int] = None

    def pin(self, hero_id: str, now_ms: int) -> None:
        self.hero_id = str(hero_id)
        self.pinned_at_ms = int(now_ms)
        self.fallen_since_ms = None

    def unpin(self) -> None:
        self.hero_id = None
        self.pinned_at_ms = 0
        self.fallen_since_ms = None

    def update_liveness(self, hero_alive: bool, now_ms: int) -> None:
        if self.hero_id is None:
            return
        if not hero_alive and self.fallen_since_ms is None:
            self.fallen_since_ms = int(now_ms)
        if self.fallen_since_ms is not None:
            if int(now_ms) - int(self.fallen_since_ms) >= PIN_FALLEN_DISPLAY_MS:
                self.unpin()

    def is_fallen(self) -> bool:
        return self.fallen_since_ms is not None
