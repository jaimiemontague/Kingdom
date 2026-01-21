"""
Render-only context helpers (UI/system; determinism-safe).

This module provides a tiny, global render context for values that are useful during
rendering but should not be threaded through every render() call.

Important:
- This must never affect simulation outcomes.
- Treat these values as best-effort hints for rendering only.
"""

from __future__ import annotations

_RENDER_ZOOM: float = 1.0


def set_render_zoom(z: float | None) -> None:
    """Set current render zoom (engine.zoom)."""
    global _RENDER_ZOOM
    try:
        zz = float(z) if z is not None else 1.0
    except Exception:
        zz = 1.0
    if not zz or zz <= 0:
        zz = 1.0
    _RENDER_ZOOM = zz


def get_render_zoom() -> float:
    """Get current render zoom (engine.zoom)."""
    return float(_RENDER_ZOOM or 1.0)

