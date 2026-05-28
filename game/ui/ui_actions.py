"""Typed UI action dataclass for HUD and input handler action routing.

Replaces ad-hoc string/dict action returns with a single typed structure.
Existing callers that expect str or dict remain compatible via normalize_ui_action().

Introduced in wk62 architecture cleanup (Agent 08).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UIAction:
    """A single typed UI action returned from click/input handlers.

    ``kind`` is the action verb (e.g. ``"quit"``, ``"close_selection"``, ``"pin_hero"``).
    ``payload`` carries optional extra data (hero ref, world coords, etc.).
    """

    kind: str
    payload: object | None = None


def normalize_ui_action(raw: object) -> UIAction | None:
    """Convert legacy string/dict action returns to a UIAction.

    Returns None if *raw* is None or unrecognizable.

    Examples::

        normalize_ui_action("quit")
        # -> UIAction(kind="quit", payload=None)

        normalize_ui_action({"type": "select_hero_at_world", "wx": 100.0, "wy": 200.0})
        # -> UIAction(kind="select_hero_at_world", payload={...})

        normalize_ui_action(UIAction("pin_hero"))
        # -> UIAction(kind="pin_hero", payload=None)  (pass-through)
    """
    if raw is None:
        return None
    if isinstance(raw, UIAction):
        return raw
    if isinstance(raw, str):
        return UIAction(kind=raw)
    if isinstance(raw, dict):
        kind = str(raw.get("type", raw.get("action", "")))
        if not kind:
            return None
        return UIAction(kind=kind, payload=raw)
    return None
