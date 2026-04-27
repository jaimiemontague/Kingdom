"""
Centralized event routing infrastructure.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import Enum
from typing import Any


class GameEventType(str, Enum):
    HERO_ATTACK = "hero_attack"
    RANGED_PROJECTILE = "ranged_projectile"
    ENEMY_KILLED = "enemy_killed"
    HERO_ATTACK_LAIR = "hero_attack_lair"
    LAIR_CLEARED = "lair_cleared"
    CASTLE_DESTROYED = "castle_destroyed"
    BUILDING_PLACED = "building_placed"
    BUILDING_DESTROYED = "building_destroyed"
    BOUNTY_PLACED = "bounty_placed"
    BOUNTY_CLAIMED = "bounty_claimed"
    HERO_ENTERED_BUILDING = "hero_entered_building"
    HERO_EXITED_BUILDING = "hero_exited_building"
    # wk14: interior view feedback (audio; non-authoritative)
    INTERIOR_BUILDING_UNDER_ATTACK = "interior_building_under_attack"
    # wk14: remote exploration (architecture only)
    QUEST_STARTED = "quest_started"
    QUEST_COMPLETED = "quest_completed"
    QUEST_HERO_RETURNED = "quest_hero_returned"
    # wk18: AI/LLM monitoring dev tools — capture prompts and responses for Dev Overlay
    LLM_PROMPT_SENT = "llm_prompt_sent"
    LLM_RESPONSE_RECEIVED = "llm_response_received"
    # wk18: AI/LLM monitoring data tap (Agent 12 emits; Agent 08 Dev Tools overlay consumes)
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    # wk37 Stage2: sim -> presentation bridge for user-facing HUD toasts
    HUD_MESSAGE = "hud_message"


class EventBus:
    """
    Deterministic registration-order event bus.

    Subscribers are called in registration order. Callback exceptions are swallowed
    by the bus so producers do not need per-call-site try/except wrappers.
    """

    def __init__(self):
        self._subscribers: list[tuple[str, Callable[[dict], None]]] = []
        self._queue: list[dict] = []

    @staticmethod
    def _normalize_event_type(event_type: Any) -> str | None:
        if event_type is None:
            return None
        if isinstance(event_type, GameEventType):
            return event_type.value
        if isinstance(event_type, Enum):
            value = getattr(event_type, "value", None)
            if isinstance(value, str):
                return value
            if value is None:
                return None
            return str(value)
        return str(event_type)

    def subscribe(self, event_type: str | GameEventType, callback: Callable[[dict], None]) -> None:
        normalized = self._normalize_event_type(event_type)
        if not normalized:
            return
        self._subscribers.append((normalized, callback))

    def emit(self, event: dict) -> None:
        if not isinstance(event, dict):
            return
        normalized = self._normalize_event_type(event.get("type"))
        if not normalized:
            return
        if event.get("type") != normalized:
            event["type"] = normalized
        self._queue.append(event)

    def emit_batch(self, events: Iterable[dict] | None) -> None:
        if not events:
            return
        for event in events:
            self.emit(event)

    def flush(self) -> None:
        if not self._queue:
            return

        for event in self._queue:
            event_type = event.get("type")
            for subscribed_type, callback in self._subscribers:
                if subscribed_type == "*" or subscribed_type == event_type:
                    try:
                        callback(event)
                    except Exception:
                        # Event subscribers are intentionally sandboxed.
                        pass

        self._queue.clear()
