"""WK52: Watches the event bus for pinned-hero events and fires HUD alerts."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from game.ui.hud import HUD
    from game.ui.pin_slot import PinSlot

LOW_HEALTH_THRESHOLD = 0.25
LOW_HEALTH_COOLDOWN_MS = 30_000


class PinAlertWatcher:
    """
    Subscribes to EventBus and dispatches toast + recall-flash for pinned-hero events.

    ``hud_or_add_message`` is either a :class:`HUD` instance (production) or a callable
    ``(text, color) -> None`` (tests / lightweight wiring).
    """

    def __init__(self, pin_slot: "PinSlot", hud_or_add_message: Any) -> None:
        self._pin = pin_slot
        add_m = getattr(hud_or_add_message, "add_message", None)
        if callable(add_m):
            self._hud: HUD | None = hud_or_add_message
            self._add_message_fn = None
        else:
            self._hud = None
            self._add_message_fn = hud_or_add_message

    def subscribe(self, event_bus) -> None:
        """Attach to EventBus. Safe to call before or after heroes spawn."""
        from game.events import GameEventType

        event_bus.subscribe(GameEventType.HERO_LEVEL_UP, self._on_level_up)
        event_bus.subscribe(GameEventType.HERO_ENTERED_BUILDING, self._on_entered_building)
        event_bus.subscribe(GameEventType.BOUNTY_CLAIMED, self._on_bounty_claimed)

    def check_low_health(self, profiles: dict, now_ms: int) -> None:
        """Called every HUD render frame. Fires at most once per LOW_HEALTH_COOLDOWN_MS."""
        if self._pin.hero_id is None or self._pin.is_fallen():
            return
        prof = profiles.get(self._pin.hero_id)
        if prof is None:
            return
        health_pct = float(getattr(getattr(prof, "vitals", None), "health_percent", 1.0))
        if health_pct > LOW_HEALTH_THRESHOLD:
            return
        if (
            self._pin.low_health_alerted_ms != 0
            and now_ms - self._pin.low_health_alerted_ms < LOW_HEALTH_COOLDOWN_MS
        ):
            return
        self._pin.low_health_alerted_ms = now_ms
        name = self._pin.pinned_name or "Hero"
        self._fire(f"⚠ {name} is low health! ({int(health_pct * 100)}%)", (255, 80, 80))

    def _on_level_up(self, event: dict) -> None:
        if not self._matches(event):
            return
        name = event.get("hero_name") or self._pin.pinned_name or "Hero"
        level = event.get("new_level", "?")
        self._fire(f"⭐ {name} reached Level {level}!", (255, 220, 50))

    def _on_entered_building(self, event: dict) -> None:
        if not self._matches(event):
            return
        building = event.get("building")
        bt = str(getattr(building, "building_type", "") or "").lower()
        if "inn" not in bt and "tavern" not in bt:
            return
        name = self._pin.pinned_name or "Hero"
        self._fire(f"🍺 {name} checked into the inn.", (150, 200, 255))

    def _on_bounty_claimed(self, event: dict) -> None:
        if not self._matches(event):
            return
        name = self._pin.pinned_name or event.get("hero") or "Hero"
        reward = int(event.get("reward", 0))
        self._fire(f"✓ {name} claimed a bounty! (+{reward}g)", (100, 255, 150))

    def _matches(self, event: dict) -> bool:
        """True if the event concerns the currently pinned hero."""
        if self._pin.hero_id is None or self._pin.is_fallen():
            return False
        eid = str(event.get("hero_id", "") or "")
        if eid:
            return eid == self._pin.hero_id
        hero_obj = event.get("hero")
        if hero_obj is not None and not isinstance(hero_obj, str):
            oid = str(getattr(hero_obj, "hero_id", "") or "")
            if oid:
                return oid == self._pin.hero_id
        hname = str(event.get("hero") if isinstance(event.get("hero"), str) else "")
        hname = hname or str(event.get("hero_name", "") or "")
        return bool(hname and hname == self._pin.pinned_name)

    def _fire(self, text: str, color: tuple[int, int, int]) -> None:
        if self._hud is not None:
            self._hud.add_message(text, color)
            self._hud.trigger_recall_flash()
        else:
            assert self._add_message_fn is not None
            self._add_message_fn(text, color)
